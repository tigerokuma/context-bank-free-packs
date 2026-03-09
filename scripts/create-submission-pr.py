from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from free_pack_common import canonicalize_repo_url, parse_skill_frontmatter


IGNORED_FILENAMES = {
    ".DS_Store",
    "Thumbs.db",
}

SEGMENT_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class SubmissionError(RuntimeError):
    pass


def humanize_slug(slug: str) -> str:
    words = [segment for segment in slug.replace("_", "-").split("-") if segment]
    return " ".join(word.capitalize() for word in words) or slug


def sanitize_branch_segment(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9._-]+", "-", value.strip().lower())
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized or "submission"


def run_git(
    repo_root: Path,
    *args: str,
    check: bool = True,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        capture_output=capture_output,
        check=check,
    )


def run_python(
    repo_root: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=check,
    )


def ensure_relative_to(root: Path, target: Path, label: str) -> Path:
    try:
        return target.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise SubmissionError(f"{label} must stay inside {root}") from exc


def require_frontmatter_value(frontmatter: dict[str, Any], key: str) -> Any:
    value = frontmatter.get(key)
    if value in (None, "", []):
        raise SubmissionError(f"source SKILL.md frontmatter must include `{key}`")
    return value


def normalize_tags(value: Any) -> list[str]:
    if isinstance(value, list):
        tags = [str(item).strip() for item in value if str(item).strip()]
    elif isinstance(value, str):
        tags = [item.strip() for item in value.split(",") if item.strip()]
    else:
        tags = []

    if not tags:
        raise SubmissionError("source SKILL.md frontmatter must include non-empty `tags`")

    return tags


def ensure_no_hidden_content(relative_path: Path) -> None:
    for part in relative_path.parts:
        if part in IGNORED_FILENAMES:
            return
        if part.startswith("."):
            raise SubmissionError(
                f"hidden files or directories are not allowed in submissions: {relative_path.as_posix()}"
            )


def copy_pack_directory(source_pack_path: Path, target_pack_path: Path) -> None:
    if target_pack_path.exists():
        shutil.rmtree(target_pack_path)
    target_pack_path.mkdir(parents=True, exist_ok=True)

    for source_path in sorted(source_pack_path.rglob("*")):
        relative_path = source_path.relative_to(source_pack_path)

        if any(part in IGNORED_FILENAMES for part in relative_path.parts):
            continue

        ensure_no_hidden_content(relative_path)

        if source_path.is_symlink():
            raise SubmissionError(f"symlinks are not allowed in submissions: {relative_path.as_posix()}")

        destination_path = target_pack_path / relative_path
        if source_path.is_dir():
            destination_path.mkdir(parents=True, exist_ok=True)
            continue

        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)


def build_manifest(
    *,
    creator_handle: str,
    pack_slug: str,
    title: str,
    summary: str,
    category: str,
    tags: list[str],
    central_repo_url: str,
    central_base_branch: str,
) -> dict[str, Any]:
    pack_dir = f"packs/{creator_handle}/{pack_slug}"
    return {
        "schemaVersion": 1,
        "pack": {
            "slug": pack_slug,
            "creatorHandle": creator_handle,
            "title": title,
            "summary": summary,
            "category": category,
            "tags": tags,
            "priceType": "free",
        },
        "source": {
            "type": "internal_repo",
            "repoUrl": central_repo_url,
            "path": pack_dir,
        },
        "support": {
            "homepage": f"{central_repo_url}/tree/{central_base_branch}/{pack_dir}",
            "issues": f"{central_repo_url}/issues",
        },
    }


def write_manifest(target_pack_path: Path, manifest: dict[str, Any]) -> None:
    manifest_path = target_pack_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n")


def list_pack_files(pack_path: Path, repo_root: Path) -> list[str]:
    files = [
        path.relative_to(repo_root).as_posix()
        for path in sorted(pack_path.rglob("*"))
        if path.is_file()
    ]
    if not files:
        raise SubmissionError(f"submission pack directory is empty: {pack_path}")
    return files


def validate_submission_pack(
    central_repo_root: Path,
    central_repo_url: str,
    pack_path: Path,
) -> str:
    changed_files_path = central_repo_root / ".submission-changed-files.txt"
    changed_files = list_pack_files(pack_path, central_repo_root)
    changed_files_path.write_text("\n".join(changed_files) + "\n")
    try:
        result = run_python(
            central_repo_root,
            "scripts/validate-free-pack.py",
            "--repo-root",
            ".",
            "--repo-url",
            central_repo_url,
            "--changed-files-file",
            changed_files_path.name,
        )
    except subprocess.CalledProcessError as exc:
        output = "\n".join(part for part in [exc.stdout, exc.stderr] if part).strip()
        raise SubmissionError(output or "central validator failed") from exc
    finally:
        changed_files_path.unlink(missing_ok=True)

    return result.stdout.strip()


def get_git_status(repo_root: Path, pack_dir: str) -> str:
    result = run_git(
        repo_root,
        "status",
        "--short",
        "--untracked-files=all",
        "--",
        pack_dir,
    )
    return result.stdout.strip()


def configure_git_identity(repo_root: Path) -> None:
    run_git(repo_root, "config", "user.name", "context-bank-submission-bot")
    run_git(repo_root, "config", "user.email", "context-bank-submission-bot@users.noreply.github.com")


def branch_exists(repo_root: Path, branch_name: str) -> bool:
    result = run_git(
        repo_root,
        "ls-remote",
        "--exit-code",
        "--heads",
        "origin",
        branch_name,
        check=False,
    )
    return result.returncode == 0


def fetch_branch(repo_root: Path, branch_name: str) -> None:
    run_git(repo_root, "fetch", "origin", branch_name)


def create_commit(repo_root: Path, pack_dir: str, message: str) -> str:
    run_git(repo_root, "add", "-A", "--", pack_dir)
    run_git(repo_root, "commit", "-m", message)
    result = run_git(repo_root, "rev-parse", "HEAD")
    return result.stdout.strip()


def push_branch(repo_root: Path, branch_name: str, branch_already_exists: bool) -> None:
    if branch_already_exists:
        run_git(repo_root, "push", "--force-with-lease", "origin", f"HEAD:refs/heads/{branch_name}")
        return

    run_git(repo_root, "push", "-u", "origin", f"HEAD:refs/heads/{branch_name}")


def github_request(
    *,
    method: str,
    url: str,
    token: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    data = None
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "context-bank-free-pack-submission",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SubmissionError(f"GitHub API request failed ({exc.code} {exc.reason}): {body}") from exc

    if not raw:
        return None
    return json.loads(raw)


def find_open_pull_request(
    *,
    central_repo: str,
    central_repo_owner: str,
    base_branch: str,
    branch_name: str,
    token: str,
) -> dict[str, Any] | None:
    encoded = urllib.parse.urlencode(
        {
            "state": "open",
            "head": f"{central_repo_owner}:{branch_name}",
            "base": base_branch,
        }
    )
    response = github_request(
        method="GET",
        url=f"https://api.github.com/repos/{central_repo}/pulls?{encoded}",
        token=token,
    )
    if isinstance(response, list) and response:
        return response[0]
    return None


def create_or_update_pull_request(
    *,
    central_repo: str,
    base_branch: str,
    branch_name: str,
    token: str,
    title: str,
    body: str,
    existing_pr: dict[str, Any] | None,
) -> dict[str, Any]:
    if existing_pr is not None:
        return github_request(
            method="PATCH",
            url=f"https://api.github.com/repos/{central_repo}/pulls/{existing_pr['number']}",
            token=token,
            payload={
                "title": title,
                "body": body,
                "base": base_branch,
            },
        )

    return github_request(
        method="POST",
        url=f"https://api.github.com/repos/{central_repo}/pulls",
        token=token,
        payload={
            "title": title,
            "body": body,
            "base": base_branch,
            "head": branch_name,
            "maintainer_can_modify": True,
        },
    )


def build_pr_body(
    *,
    submission_type: str,
    creator_handle: str,
    pack_slug: str,
    pack_dir: str,
    category: str,
    summary: str,
    source_repository: str,
    source_ref: str,
    source_pack_path: str,
    source_pack_url: str,
    verification_output: str,
) -> str:
    new_checked = "x" if submission_type == "new" else " "
    update_checked = "x" if submission_type == "update" else " "
    short_ref = source_ref[:7]
    return "\n".join(
        [
            "## Free Pack Submission",
            "",
            "### Submission Type",
            f"- [{new_checked}] New free pack",
            f"- [{update_checked}] Update to an existing free pack",
            "",
            "### Required Metadata",
            f"- Creator handle: `{creator_handle}`",
            f"- Pack slug: `{pack_slug}`",
            f"- Pack directory: `{pack_dir}`",
            f"- Category: `{category}`",
            "- Confirmation that `priceType=free` in both `manifest.json` and `SKILL.md`: yes",
            "",
            "### Submission Provenance",
            "- Submission mode: trusted source repo automation",
            f"- Source repository: `{source_repository}`",
            f"- Source commit: `{source_ref}` (`{short_ref}`)",
            f"- Source pack path: `{source_pack_path}`",
            f"- Source pack URL: {source_pack_url}",
            "",
            "### Pack Summary",
            summary,
            "",
            "### Verification",
            "```text",
            verification_output or "central validator passed",
            "```",
            "",
            "### Scope Checklist",
            f"- [x] This PR changes exactly one pack directory under `{pack_dir}`",
            "- [x] `manifest.json` is present",
            "- [x] `SKILL.md` is present",
            "- [x] This pack is free and safe for public review",
            "- [x] No executables, symlinks, or hidden secrets are included",
            "- [x] I did not include paid-pack logic or private marketplace code",
        ]
    )


def write_output(path: Path | None, payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    if path is None:
        sys.stdout.write(rendered)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or update a free-pack submission PR in the central repo.")
    parser.add_argument("--source-repo-root", required=True, help="Root path of the trusted source repository.")
    parser.add_argument("--source-pack-path", required=True, help="Pack directory path inside the source repository.")
    parser.add_argument("--source-repository", required=True, help="GitHub repository in owner/repo format.")
    parser.add_argument("--source-ref", required=True, help="Source repository commit SHA or ref for traceability.")
    parser.add_argument("--central-repo-root", required=True, help="Checked-out central repository root path.")
    parser.add_argument("--central-repo", required=True, help="Central GitHub repository in owner/repo format.")
    parser.add_argument("--central-repo-url", required=True, help="Canonical public URL of the central repo.")
    parser.add_argument("--central-base-branch", default="main", help="Default branch for central repo PRs.")
    parser.add_argument("--creator-handle", required=True, help="Creator handle for the published pack path.")
    parser.add_argument("--pack-slug", help="Override slug. Defaults to the source pack directory name.")
    parser.add_argument("--pack-title", help="Override manifest title. Defaults to SKILL.md name/title.")
    parser.add_argument("--pack-summary", help="Override manifest summary. Defaults to SKILL.md description.")
    parser.add_argument("--submission-branch", help="Override submission branch name.")
    parser.add_argument("--github-token", help="GitHub token with contents:write and pull_requests:write on the central repo.")
    parser.add_argument("--output-json", help="Optional path for JSON output.")
    parser.add_argument("--dry-run", action="store_true", help="Prepare the submission without commit, push, or PR creation.")
    args = parser.parse_args()

    source_repo_root = Path(args.source_repo_root).resolve()
    source_pack_path = (source_repo_root / args.source_pack_path).resolve()
    ensure_relative_to(source_repo_root, source_pack_path, "source pack path")
    central_repo_root = Path(args.central_repo_root).resolve()
    central_repo_url = canonicalize_repo_url(args.central_repo_url)
    output_path = Path(args.output_json).resolve() if args.output_json else None

    if not source_pack_path.is_dir():
        raise SubmissionError(f"source pack directory does not exist: {source_pack_path}")

    skill_path = source_pack_path / "SKILL.md"
    if not skill_path.is_file():
        raise SubmissionError(f"source pack is missing SKILL.md: {skill_path}")

    source_frontmatter, frontmatter_errors = parse_skill_frontmatter(skill_path)
    if frontmatter_errors:
        raise SubmissionError("; ".join(frontmatter_errors))

    price_type = require_frontmatter_value(source_frontmatter, "priceType")
    if price_type != "free":
        raise SubmissionError("trusted source repo submissions only support `priceType=free`")

    pack_slug = args.pack_slug or source_pack_path.name
    creator_handle = args.creator_handle
    if not SEGMENT_RE.fullmatch(creator_handle):
        raise SubmissionError("creator handle must match ^[a-z0-9][a-z0-9-]*$")
    if not SEGMENT_RE.fullmatch(pack_slug):
        raise SubmissionError("pack slug must match ^[a-z0-9][a-z0-9-]*$")
    title = (
        args.pack_title
        or source_frontmatter.get("title")
        or source_frontmatter.get("name")
        or humanize_slug(pack_slug)
    )
    summary = args.pack_summary or source_frontmatter.get("description")
    if not isinstance(summary, str) or not summary.strip():
        raise SubmissionError("pack summary is required; provide SKILL.md frontmatter `description` or --pack-summary")

    category = str(require_frontmatter_value(source_frontmatter, "category")).strip()
    tags = normalize_tags(source_frontmatter.get("tags"))

    pack_dir = f"packs/{creator_handle}/{pack_slug}"
    target_pack_path = central_repo_root / pack_dir
    submission_type = "update" if target_pack_path.exists() else "new"
    source_repository = args.source_repository.strip()
    source_pack_url = f"https://github.com/{source_repository}/tree/{args.source_ref}/{args.source_pack_path}"

    copy_pack_directory(source_pack_path, target_pack_path)
    manifest = build_manifest(
        creator_handle=creator_handle,
        pack_slug=pack_slug,
        title=str(title).strip(),
        summary=summary.strip(),
        category=category,
        tags=tags,
        central_repo_url=central_repo_url,
        central_base_branch=args.central_base_branch,
    )
    write_manifest(target_pack_path, manifest)

    verification_output = validate_submission_pack(central_repo_root, central_repo_url, target_pack_path)
    status_output = get_git_status(central_repo_root, pack_dir)

    branch_name = args.submission_branch or "/".join(
        [
            "submission",
            sanitize_branch_segment(source_repository.replace("/", "-")),
            sanitize_branch_segment(f"{creator_handle}-{pack_slug}"),
        ]
    )

    result: dict[str, Any] = {
        "status": "prepared",
        "submissionType": submission_type,
        "centralRepo": args.central_repo,
        "centralRepoUrl": central_repo_url,
        "baseBranch": args.central_base_branch,
        "branch": branch_name,
        "packDirectory": pack_dir,
        "source": {
            "repository": source_repository,
            "ref": args.source_ref,
            "packPath": args.source_pack_path,
            "packUrl": source_pack_url,
        },
        "manifest": manifest,
        "verification": verification_output,
    }

    if not status_output:
        result["status"] = "skipped"
        result["reason"] = "central repo already matches generated submission payload"
        write_output(output_path, result)
        return 0

    if args.dry_run:
        result["status"] = "dry_run"
        result["reason"] = "submission prepared locally; commit/push/pr creation skipped"
        write_output(output_path, result)
        return 0

    if not args.github_token:
        raise SubmissionError("--github-token is required unless --dry-run is used")

    configure_git_identity(central_repo_root)
    branch_already_exists = branch_exists(central_repo_root, branch_name)
    run_git(central_repo_root, "checkout", "-B", branch_name)

    if branch_already_exists:
        fetch_branch(central_repo_root, branch_name)

    run_git(central_repo_root, "add", "-A", "--", pack_dir)
    existing_pr = find_open_pull_request(
        central_repo=args.central_repo,
        central_repo_owner=args.central_repo.split("/", 1)[0],
        base_branch=args.central_base_branch,
        branch_name=branch_name,
        token=args.github_token,
    )

    if branch_already_exists:
        diff_to_branch = run_git(
            central_repo_root,
            "diff",
            "--cached",
            "--quiet",
            f"origin/{branch_name}",
            "--",
            pack_dir,
            check=False,
        )
        if diff_to_branch.returncode == 0 and existing_pr is not None:
            result["status"] = "skipped"
            result["reason"] = "existing open PR already matches the generated submission payload"
            result["pullRequest"] = {
                "number": existing_pr["number"],
                "url": existing_pr["html_url"],
            }
            write_output(output_path, result)
            return 0

    commit_message = f"chore: submit {creator_handle}/{pack_slug} from {source_repository}@{args.source_ref[:7]}"
    commit_sha = create_commit(central_repo_root, pack_dir, commit_message)
    push_branch(central_repo_root, branch_name, branch_already_exists)

    pr_title = f"[free-pack] Submit {creator_handle}/{pack_slug}"
    pr_body = build_pr_body(
        submission_type=submission_type,
        creator_handle=creator_handle,
        pack_slug=pack_slug,
        pack_dir=pack_dir,
        category=category,
        summary=summary.strip(),
        source_repository=source_repository,
        source_ref=args.source_ref,
        source_pack_path=args.source_pack_path,
        source_pack_url=source_pack_url,
        verification_output=verification_output,
    )
    pull_request = create_or_update_pull_request(
        central_repo=args.central_repo,
        base_branch=args.central_base_branch,
        branch_name=branch_name,
        token=args.github_token,
        title=pr_title,
        body=pr_body,
        existing_pr=existing_pr,
    )

    result["status"] = "updated" if existing_pr is not None else "created"
    result["commit"] = commit_sha
    result["pullRequest"] = {
        "number": pull_request["number"],
        "url": pull_request["html_url"],
    }
    write_output(output_path, result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SubmissionError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, indent=2, ensure_ascii=True))
        raise SystemExit(1)
