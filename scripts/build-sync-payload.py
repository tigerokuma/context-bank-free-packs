from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from free_pack_common import (
    canonicalize_repo_url,
    classify_changed_files,
    iso_utc_now,
    read_changed_files,
    validate_pack_directory,
)


def build_pack_payload(pack_dir: str, manifest: dict, skill_frontmatter: dict, repo_url: str, ref: str) -> dict:
    return {
        "schemaVersion": 1,
        "generatedAt": iso_utc_now(),
        "pack": manifest["pack"],
        "source": {
            "type": "internal_repo",
            "repoUrl": repo_url,
            "ref": ref,
            "path": pack_dir,
        },
        "support": manifest.get("support", {}),
        "skill": {
            "title": skill_frontmatter.get("title") or skill_frontmatter.get("name") or manifest["pack"]["title"],
            "category": skill_frontmatter.get("category") or manifest["pack"]["category"],
            "priceType": skill_frontmatter.get("priceType") or manifest["pack"]["priceType"],
        },
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build normalized marketplace sync payloads.")
    parser.add_argument("--repo-root", required=True, help="Repository root path.")
    parser.add_argument("--repo-url", required=True, help="Public repository URL.")
    parser.add_argument("--ref", required=True, help="Merged commit SHA.")
    parser.add_argument("--changed-files-file", required=True, help="Changed files list.")
    parser.add_argument("--output-dir", required=True, help="Directory for generated payloads.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    repo_url = canonicalize_repo_url(args.repo_url)
    changed_files = read_changed_files(Path(args.changed_files_file))
    output_dir = Path(args.output_dir).resolve()

    pack_dirs, invalid_pack_paths, _, _ = classify_changed_files(changed_files)

    errors = [f"{path}: changed file path must match packs/<creator>/<slug>/" for path in invalid_pack_paths]
    payloads: list[dict] = []
    removed_pack_dirs: list[str] = []

    for pack_dir in sorted(pack_dirs):
        if not (repo_root / pack_dir).exists():
            removed_pack_dirs.append(pack_dir)
            continue

        pack_errors, manifest, skill_frontmatter = validate_pack_directory(repo_root, pack_dir, repo_url)
        errors.extend(pack_errors)
        if manifest is None or skill_frontmatter is None:
            continue

        payload = build_pack_payload(pack_dir, manifest, skill_frontmatter, repo_url, args.ref)
        payloads.append(payload)

        creator = manifest["pack"]["creatorHandle"]
        slug = manifest["pack"]["slug"]
        write_json(output_dir / "packs" / f"{creator}--{slug}.json", payload)

    if errors:
        print("Marketplace sync scaffold failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    summary = {
        "schemaVersion": 1,
        "generatedAt": iso_utc_now(),
        "repoUrl": repo_url,
        "ref": args.ref,
        "packCount": len(payloads),
        "removedPackDirs": removed_pack_dirs,
        "packs": payloads,
    }
    write_json(output_dir / "index.json", summary)

    print(f"Generated {len(payloads)} normalized payload(s) in {output_dir}")
    if removed_pack_dirs:
        print(f"Skipped removed pack directories: {', '.join(removed_pack_dirs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
