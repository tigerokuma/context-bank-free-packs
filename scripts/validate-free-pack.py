from __future__ import annotations

import argparse
import sys
from pathlib import Path

from free_pack_common import canonicalize_repo_url, classify_changed_files, read_changed_files, validate_pack_directory


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate changed free-pack directories for public PRs.")
    parser.add_argument("--repo-root", required=True, help="Repository root path.")
    parser.add_argument("--repo-url", required=True, help="Expected public repository URL.")
    parser.add_argument(
        "--changed-files-file",
        required=True,
        help="Path to a newline-delimited file list from git diff --name-only.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    expected_repo_url = canonicalize_repo_url(args.repo_url)
    changed_files = read_changed_files(Path(args.changed_files_file))

    pack_dirs, invalid_pack_paths, _, disallowed_other = classify_changed_files(changed_files)

    if not pack_dirs:
        print("No pack directories changed; skipping free-pack validation.")
        if invalid_pack_paths:
            print("Invalid pack-like paths detected:")
            for path in invalid_pack_paths:
                print(f"  - {path}")
            return 1
        return 0

    errors: list[str] = []

    if invalid_pack_paths:
        errors.extend(
            f"{path}: changed file path must match packs/<creator>/<slug>/" for path in invalid_pack_paths
        )

    if len(pack_dirs) != 1:
        joined = ", ".join(sorted(pack_dirs))
        errors.append(f"Submission PRs must change exactly one pack directory. Found: {joined}")

    if disallowed_other:
        errors.append("Submission PRs may not change unrelated files:")
        errors.extend(f"  - {path}" for path in disallowed_other)

    for pack_dir in sorted(pack_dirs):
        pack_errors, _, _ = validate_pack_directory(repo_root, pack_dir, expected_repo_url)
        errors.extend(pack_errors)

    if errors:
        print("Free-pack validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Validated free pack successfully: {next(iter(pack_dirs))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
