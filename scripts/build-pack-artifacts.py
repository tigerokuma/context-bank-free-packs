from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, parse, request
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from free_pack_common import canonicalize_repo_url, iso_utc_now, validate_pack_directory


FIXED_ZIP_TIMESTAMP = (2020, 1, 1, 0, 0, 0)
RELEASE_TAG = "pack-artifacts"


@dataclass(frozen=True)
class PreparedPackArtifact:
    creator_handle: str
    slug: str
    source_path: str
    source_ref: str
    asset_name: str
    artifact_path: Path
    artifact_url: str
    sha256: str
    size_bytes: int


class GitHubApiError(RuntimeError):
    pass


def run_git(repo_root: Path, *args: str) -> str:
    command = ["git", "-C", str(repo_root), *args]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "git_command_failed"
        raise RuntimeError(f"{' '.join(command)}: {message}")
    return completed.stdout.strip()


def list_pack_directories(repo_root: Path) -> list[str]:
    packs_root = repo_root / "packs"
    pack_dirs: list[str] = []

    if not packs_root.is_dir():
        return pack_dirs

    for creator_dir in sorted(path for path in packs_root.iterdir() if path.is_dir()):
        for pack_dir in sorted(path for path in creator_dir.iterdir() if path.is_dir()):
            pack_dirs.append(pack_dir.relative_to(repo_root).as_posix())

    return pack_dirs


def build_release_download_url(repository: str, release_tag: str, asset_name: str) -> str:
    return f"https://github.com/{repository}/releases/download/{release_tag}/{asset_name}"


def build_directory_entry(path: str) -> ZipInfo:
    info = ZipInfo(filename=path, date_time=FIXED_ZIP_TIMESTAMP)
    info.create_system = 3
    info.compress_type = ZIP_DEFLATED
    info.external_attr = (0o40755 << 16) | 0x10
    return info


def build_file_entry(path: str) -> ZipInfo:
    info = ZipInfo(filename=path, date_time=FIXED_ZIP_TIMESTAMP)
    info.create_system = 3
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    return info


def iter_pack_entries(pack_root: Path) -> tuple[list[str], list[Path]]:
    directories: list[str] = ["."]
    files: list[Path] = []

    for path in sorted(pack_root.rglob("*")):
        relative_path = path.relative_to(pack_root)
        if path.is_dir():
            directories.append(relative_path.as_posix())
            continue
        if path.is_file():
            files.append(path)

    return directories, files


def create_deterministic_zip(pack_root: Path, archive_root: str, output_path: Path) -> None:
    directories, files = iter_pack_entries(pack_root)

    with ZipFile(output_path, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(build_directory_entry(f"{archive_root}/"), b"")
        for directory in directories:
            if directory == ".":
                continue
            archive.writestr(build_directory_entry(f"{archive_root}/{directory}/"), b"")
        for file_path in files:
            relative_path = file_path.relative_to(pack_root).as_posix()
            archive.writestr(
                build_file_entry(f"{archive_root}/{relative_path}"),
                file_path.read_bytes(),
            )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def github_request(
    method: str,
    url: str,
    *,
    token: str | None,
    json_body: dict[str, Any] | None = None,
    binary_body: bytes | None = None,
    accept: str = "application/vnd.github+json",
    content_type: str | None = None,
) -> Any:
    headers = {
        "Accept": accept,
        "User-Agent": "context-bank-pack-artifacts",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None

    if json_body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(json_body).encode("utf-8")
    elif binary_body is not None:
        if content_type is not None:
            headers["Content-Type"] = content_type
        data = binary_body

    req = request.Request(url, data=data, headers=headers, method=method)

    try:
        with request.urlopen(req) as response:
            raw = response.read()
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise GitHubApiError(f"github_api_error:{exc.code}:{url}:{body}") from exc
    except error.URLError as exc:
        raise GitHubApiError(f"github_api_unreachable:{url}:{exc}") from exc

    if not raw:
        return None

    decoded = raw.decode("utf-8")
    try:
        return json.loads(decoded)
    except json.JSONDecodeError:
        return decoded


def get_or_create_release(repository: str, release_tag: str, token: str) -> dict[str, Any]:
    api_base = f"https://api.github.com/repos/{repository}"
    try:
        release = github_request(
            "GET",
            f"{api_base}/releases/tags/{parse.quote(release_tag, safe='')}",
            token=token,
        )
        if not isinstance(release, dict):
            raise GitHubApiError("invalid_release_lookup_response")
        return release
    except GitHubApiError as exc:
        if "github_api_error:404:" not in str(exc):
            raise

    created = github_request(
        "POST",
        f"{api_base}/releases",
        token=token,
        json_body={
            "tag_name": release_tag,
            "name": release_tag,
            "body": "Pack-only ZIP artifacts for approved free packs.",
            "draft": False,
            "prerelease": False,
        },
    )
    if not isinstance(created, dict):
        raise GitHubApiError("invalid_release_create_response")
    return created


def upload_asset(upload_url_template: str, asset_name: str, artifact_path: Path, token: str) -> dict[str, Any]:
    upload_url = upload_url_template.split("{", 1)[0]
    query = parse.urlencode({"name": asset_name})
    response = github_request(
        "POST",
        f"{upload_url}?{query}",
        token=token,
        binary_body=artifact_path.read_bytes(),
        accept="application/vnd.github+json",
        content_type="application/zip",
    )
    if not isinstance(response, dict):
        raise GitHubApiError("invalid_asset_upload_response")
    return response


def prepare_pack_artifacts(
    repo_root: Path,
    repo_url: str,
    repository: str,
    release_tag: str,
    staging_dir: Path,
) -> list[PreparedPackArtifact]:
    errors: list[str] = []
    prepared: list[PreparedPackArtifact] = []

    for pack_dir in list_pack_directories(repo_root):
        pack_errors, manifest, _ = validate_pack_directory(repo_root, pack_dir, repo_url)
        if pack_errors:
            errors.extend(pack_errors)
            continue
        if manifest is None:
            errors.append(f"{pack_dir}: manifest_validation_failed")
            continue

        source_ref = run_git(repo_root, "log", "-1", "--format=%H", "--", pack_dir)
        if not source_ref:
            errors.append(f"{pack_dir}: missing_source_ref")
            continue

        creator_handle = manifest["pack"]["creatorHandle"]
        slug = manifest["pack"]["slug"]
        archive_root = f"{creator_handle}-{slug}"
        asset_name = f"{creator_handle}--{slug}--{source_ref[:7]}.zip"
        artifact_path = staging_dir / asset_name
        create_deterministic_zip(repo_root / pack_dir, archive_root, artifact_path)

        prepared.append(
            PreparedPackArtifact(
                creator_handle=creator_handle,
                slug=slug,
                source_path=pack_dir,
                source_ref=source_ref,
                asset_name=asset_name,
                artifact_path=artifact_path,
                artifact_url=build_release_download_url(repository, release_tag, asset_name),
                sha256=sha256_file(artifact_path),
                size_bytes=artifact_path.stat().st_size,
            )
        )

    if errors:
        raise RuntimeError("pack_artifact_build_failed:\n- " + "\n- ".join(errors))

    return sorted(prepared, key=lambda entry: (entry.creator_handle, entry.slug))


def build_catalog_payload(release_tag: str, prepared: list[PreparedPackArtifact]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "generatedAt": iso_utc_now(),
        "releaseTag": release_tag,
        "packs": [
            {
                "creatorHandle": pack.creator_handle,
                "slug": pack.slug,
                "sourcePath": pack.source_path,
                "sourceRef": pack.source_ref,
                "assetName": pack.asset_name,
                "artifactUrl": pack.artifact_url,
                "sha256": pack.sha256,
                "sizeBytes": pack.size_bytes,
            }
            for pack in prepared
        ],
    }


def write_catalog(output_path: Path, release_tag: str, prepared: list[PreparedPackArtifact]) -> None:
    payload = build_catalog_payload(release_tag, prepared)
    if output_path.is_file():
        try:
            existing = json.loads(output_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = None

        if isinstance(existing, dict):
            comparable_existing = {
                key: value for key, value in existing.items() if key != "generatedAt"
            }
            comparable_next = {
                key: value for key, value in payload.items() if key != "generatedAt"
            }
            if comparable_existing == comparable_next:
                return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def publish_artifacts(
    repository: str,
    release_tag: str,
    prepared: list[PreparedPackArtifact],
    token: str,
) -> list[PreparedPackArtifact]:
    release = get_or_create_release(repository, release_tag, token)
    upload_url = release.get("upload_url")
    if not isinstance(upload_url, str) or not upload_url:
        raise GitHubApiError("release_upload_url_missing")

    existing_assets = {
        asset.get("name"): asset
        for asset in release.get("assets", [])
        if isinstance(asset, dict) and isinstance(asset.get("name"), str)
    }
    published: list[PreparedPackArtifact] = []

    for pack in prepared:
        asset = existing_assets.get(pack.asset_name)
        if asset is None:
            asset = upload_asset(upload_url, pack.asset_name, pack.artifact_path, token)
        else:
            remote_size = asset.get("size")
            if isinstance(remote_size, int) and remote_size != pack.size_bytes:
                raise GitHubApiError(
                    f"existing_asset_size_mismatch:{pack.asset_name}:{remote_size}:{pack.size_bytes}"
                )
            remote_digest = asset.get("digest")
            if isinstance(remote_digest, str) and remote_digest.startswith("sha256:"):
                digest_value = remote_digest.split(":", 1)[1]
                if digest_value and digest_value != pack.sha256:
                    raise GitHubApiError(
                        f"existing_asset_sha256_mismatch:{pack.asset_name}:{digest_value}:{pack.sha256}"
                    )
        browser_download_url = asset.get("browser_download_url")
        if isinstance(browser_download_url, str) and browser_download_url:
            artifact_url = browser_download_url
        else:
            artifact_url = pack.artifact_url
        published.append(
            PreparedPackArtifact(
                creator_handle=pack.creator_handle,
                slug=pack.slug,
                source_path=pack.source_path,
                source_ref=pack.source_ref,
                asset_name=pack.asset_name,
                artifact_path=pack.artifact_path,
                artifact_url=artifact_url,
                sha256=asset.get("digest", "").split(":", 1)[1]
                if isinstance(asset.get("digest"), str) and asset.get("digest", "").startswith("sha256:")
                else pack.sha256,
                size_bytes=asset.get("size") if isinstance(asset.get("size"), int) else pack.size_bytes,
            )
        )

    return published


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and publish pack-only GitHub release artifacts.")
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument("--repo-url", required=True, help="Canonical public repository URL.")
    parser.add_argument("--github-repository", required=True, help="Repository slug in owner/name form.")
    parser.add_argument(
        "--catalog-output",
        default="catalogs/pack-artifacts.json",
        help="Output path for the generated catalog.",
    )
    parser.add_argument(
        "--release-tag",
        default=RELEASE_TAG,
        help="GitHub release tag used for pack artifacts.",
    )
    parser.add_argument(
        "--github-token",
        default=os.environ.get("GITHUB_TOKEN"),
        help="GitHub token with contents:write access. Defaults to GITHUB_TOKEN.",
    )
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="Generate artifacts and catalog without calling the GitHub Releases API.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    repo_url = canonicalize_repo_url(args.repo_url)
    catalog_output = (repo_root / args.catalog_output).resolve()

    try:
        with tempfile.TemporaryDirectory(prefix="pack-artifacts-") as tmp_dir:
            prepared = prepare_pack_artifacts(
                repo_root=repo_root,
                repo_url=repo_url,
                repository=args.github_repository,
                release_tag=args.release_tag,
                staging_dir=Path(tmp_dir),
            )

            published = prepared
            if not args.skip_upload:
                if not args.github_token:
                    raise RuntimeError("github_token_required_for_release_upload")
                published = publish_artifacts(
                    repository=args.github_repository,
                    release_tag=args.release_tag,
                    prepared=prepared,
                    token=args.github_token,
                )

            write_catalog(catalog_output, args.release_tag, published)
    except Exception as exc:
        print(f"Pack artifact publishing failed: {exc}", file=sys.stderr)
        return 1

    print(f"Generated {catalog_output.relative_to(repo_root)} for {len(prepared)} pack(s)")
    if args.skip_upload:
        print("Skipped GitHub release upload")
    return 0


if __name__ == "__main__":
    sys.exit(main())
