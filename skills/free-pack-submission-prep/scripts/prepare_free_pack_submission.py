#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_ROOT = REPO_ROOT / "scripts"

if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from free_pack_common import (  # noqa: E402
    ALLOWED_CATEGORIES,
    BLOCKED_EXTENSIONS,
    BLOCKED_PATTERNS,
    IGNORED_FILENAMES,
    SEGMENT_RE,
    TAG_RE,
    canonicalize_repo_url,
    parse_skill_frontmatter,
)


DEFAULT_REPO_URL = "https://github.com/tigerokuma/context-bank-free-packs"
DEFAULT_BASE_BRANCH = "main"


class PrepError(RuntimeError):
    pass


@dataclass(frozen=True)
class CandidateFile:
    source_path: Path
    relative_path: Path
    normalize_permissions: bool


def slugify_segment(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized or "pack"


def humanize_slug(slug: str) -> str:
    words = [part for part in slug.split("-") if part]
    return " ".join(word.capitalize() for word in words) or slug


def sanitize_summary(value: str) -> str:
    collapsed = " ".join(value.split())
    if not collapsed:
        return ""
    if len(collapsed) <= 240:
        return collapsed
    return collapsed[:237].rstrip() + "..."


def normalize_tag(value: str) -> str | None:
    tag = slugify_segment(value)[:50].strip("-")
    if not tag or not TAG_RE.fullmatch(tag):
        return None
    return tag


def split_tags(raw_value: str) -> list[str]:
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def resolve_target_pack_dir(target_value: str) -> tuple[Path, str, str]:
    raw_target = Path(target_value)
    target_path = raw_target if raw_target.is_absolute() else REPO_ROOT / raw_target
    target_path = target_path.resolve()

    try:
        relative = target_path.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise PrepError(f"target pack dir must stay inside {REPO_ROOT}") from exc

    parts = relative.parts
    if len(parts) != 3 or parts[0] != "packs":
        raise PrepError("target pack dir must match packs/<creator>/<slug>")

    creator_handle, pack_slug = parts[1], parts[2]
    if not SEGMENT_RE.fullmatch(creator_handle):
        raise PrepError(f"invalid creator handle `{creator_handle}` in target pack dir")
    if not SEGMENT_RE.fullmatch(pack_slug):
        raise PrepError(f"invalid pack slug `{pack_slug}` in target pack dir")

    return target_path, creator_handle, pack_slug


def load_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def extract_body_from_markdown(text: str) -> str:
    if not text.startswith("---\n"):
        return text.strip()

    lines = text.splitlines()
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[index + 1 :]).strip()
    return text.strip()


def load_skill_source(source_dir: Path) -> tuple[dict, str, list[str]]:
    skill_path = source_dir / "SKILL.md"
    if not skill_path.is_file():
        return {}, "", []

    text = skill_path.read_text()
    frontmatter, errors = parse_skill_frontmatter(skill_path)
    body = extract_body_from_markdown(text)
    return frontmatter, body, errors


def first_markdown_paragraph(path: Path) -> str:
    if not path.is_file():
        return ""

    lines: list[str] = []
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line:
            if lines:
                break
            continue
        if line.startswith("#"):
            continue
        lines.append(line)

    return " ".join(lines)


def inspect_source_tree(source_dir: Path) -> tuple[list[CandidateFile], list[str], list[str], list[str]]:
    candidates: list[CandidateFile] = []
    warnings: list[str] = []
    errors: list[str] = []
    preserved_top_level: set[str] = set()

    for current_root, dirnames, filenames in os.walk(source_dir, topdown=True, followlinks=False):
        current_path = Path(current_root)

        filtered_dirs: list[str] = []
        for dirname in sorted(dirnames):
            child_path = current_path / dirname
            relative_child = child_path.relative_to(source_dir)

            if child_path.is_symlink():
                errors.append(f"{relative_child.as_posix()}/: symlink directories are not allowed")
                continue

            if dirname in IGNORED_FILENAMES or dirname.startswith("."):
                warnings.append(f"{relative_child.as_posix()}/: skipped hidden or junk directory")
                continue

            filtered_dirs.append(dirname)

        dirnames[:] = filtered_dirs

        for filename in sorted(filenames):
            file_path = current_path / filename
            relative_path = file_path.relative_to(source_dir)

            if file_path.is_symlink():
                errors.append(f"{relative_path.as_posix()}: symlinks are not allowed")
                continue

            if filename in IGNORED_FILENAMES or any(part in IGNORED_FILENAMES for part in relative_path.parts):
                warnings.append(f"{relative_path.as_posix()}: skipped junk OS file")
                continue

            if any(part.startswith(".") for part in relative_path.parts):
                warnings.append(f"{relative_path.as_posix()}: skipped hidden file")
                continue

            if file_path.suffix.lower() in BLOCKED_EXTENSIONS:
                errors.append(
                    f"{relative_path.as_posix()}: blocked executable file extension `{file_path.suffix.lower()}`"
                )
                continue

            try:
                raw = file_path.read_bytes()
            except OSError as exc:
                errors.append(f"{relative_path.as_posix()}: failed to read file ({exc})")
                continue

            if b"\x00" not in raw:
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    text = ""

                if text:
                    blocked_content = False
                    for label, pattern in BLOCKED_PATTERNS:
                        if pattern.search(text):
                            errors.append(f"{relative_path.as_posix()}: blocked pattern detected ({label})")
                            blocked_content = True
                            break
                    if blocked_content:
                        continue

            preserved_top_level.add(relative_path.parts[0])
            candidates.append(
                CandidateFile(
                    source_path=file_path,
                    relative_path=relative_path,
                    normalize_permissions=bool(file_path.stat().st_mode & 0o111),
                )
            )

    return candidates, sorted(warnings), sorted(errors), sorted(preserved_top_level)


def infer_category(title: str, summary: str, candidate_files: list[CandidateFile]) -> str:
    haystack = " ".join(
        [title.lower(), summary.lower(), " ".join(path.relative_path.as_posix().lower() for path in candidate_files)]
    )
    category_keywords = {
        "analysis": {"analysis", "analytics", "benchmark", "forecast"},
        "automation": {"automation", "workflow", "ops", "pipeline", "agent"},
        "business": {"business", "sales", "finance", "revenue"},
        "developer-tools": {"developer", "dev", "code", "sdk", "api", "tooling"},
        "education": {"learn", "lesson", "study", "education", "tutorial"},
        "investing": {"stocks", "investing", "equity", "market", "portfolio"},
        "marketing": {"marketing", "seo", "growth", "campaign"},
        "operations": {"operations", "runbook", "incident", "support"},
        "productivity": {"productivity", "notes", "planning", "tasks"},
        "research": {"research", "paper", "literature", "references"},
        "sports": {"sports", "baseball", "soccer", "basketball", "team"},
        "writing": {"writing", "copy", "prompt", "editorial", "blog"},
        "agriculture": {"agriculture", "farming", "crop"},
    }

    scores = {category: 0 for category in category_keywords}
    for category, keywords in category_keywords.items():
        for keyword in keywords:
            if keyword in haystack:
                scores[category] += 1

    best_category, best_score = max(scores.items(), key=lambda item: item[1])
    return best_category if best_score > 0 else "productivity"


def infer_tags(
    explicit_tags: list[str] | None,
    pack_slug: str,
    title: str,
    category: str,
    candidate_files: list[CandidateFile],
) -> list[str]:
    raw_values: list[str] = []
    if explicit_tags:
        raw_values.extend(explicit_tags)
    else:
        raw_values.extend(pack_slug.split("-"))
        raw_values.append(pack_slug)
        raw_values.extend(word.lower() for word in re.findall(r"[A-Za-z0-9]+", title) if len(word) >= 4)
        raw_values.append(category)
        if "free-pack" not in raw_values:
            raw_values.append("free-pack")
        for candidate in candidate_files:
            top_level = candidate.relative_path.parts[0]
            if top_level in {"examples", "prompts", "assets"}:
                raw_values.append(top_level.rstrip("s"))

    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in raw_values:
        tag = normalize_tag(raw_value)
        if not tag or tag in seen:
            continue
        seen.add(tag)
        normalized.append(tag)
        if len(normalized) >= 8:
            break

    if not normalized:
        normalized = ["free-pack", category]
    return normalized


def choose_summary(
    override: str | None,
    manifest: dict | None,
    frontmatter: dict,
    skill_body: str,
    source_dir: Path,
    title: str,
) -> str:
    if override:
        return sanitize_summary(override)

    manifest_summary = manifest and manifest.get("pack", {}).get("summary")
    if isinstance(manifest_summary, str) and manifest_summary.strip():
        return sanitize_summary(manifest_summary)

    description = frontmatter.get("description")
    if isinstance(description, str) and description.strip():
        return sanitize_summary(description)

    skill_paragraph = first_markdown_paragraph(source_dir / "SKILL.md")
    if skill_paragraph:
        return sanitize_summary(skill_paragraph)

    readme_paragraph = first_markdown_paragraph(source_dir / "README.md")
    if readme_paragraph:
        return sanitize_summary(readme_paragraph)

    body_paragraph = " ".join(line.strip() for line in skill_body.splitlines() if line.strip())
    if body_paragraph:
        return sanitize_summary(body_paragraph)

    return sanitize_summary(f"Free pack for {title}.")


def choose_title(
    override: str | None,
    manifest: dict | None,
    frontmatter: dict,
    pack_slug: str,
) -> str:
    if override and override.strip():
        return " ".join(override.split())

    manifest_title = manifest and manifest.get("pack", {}).get("title")
    if isinstance(manifest_title, str) and manifest_title.strip():
        return " ".join(manifest_title.split())

    for key in ("title", "name"):
        value = frontmatter.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())

    return humanize_slug(pack_slug)


def choose_category(
    override: str | None,
    manifest: dict | None,
    frontmatter: dict,
    title: str,
    summary: str,
    candidate_files: list[CandidateFile],
) -> str:
    if override:
        normalized = override.strip()
        if normalized not in ALLOWED_CATEGORIES:
            allowed = ", ".join(sorted(ALLOWED_CATEGORIES))
            raise PrepError(f"category must be one of: {allowed}")
        return normalized

    manifest_category = manifest and manifest.get("pack", {}).get("category")
    if isinstance(manifest_category, str) and manifest_category in ALLOWED_CATEGORIES:
        return manifest_category

    skill_category = frontmatter.get("category")
    if isinstance(skill_category, str) and skill_category in ALLOWED_CATEGORIES:
        return skill_category

    return infer_category(title, summary, candidate_files)


def choose_tags(
    override: str | None,
    manifest: dict | None,
    frontmatter: dict,
    pack_slug: str,
    title: str,
    category: str,
    candidate_files: list[CandidateFile],
) -> list[str]:
    explicit_tags: list[str] | None = None
    if override:
        explicit_tags = split_tags(override)
    else:
        manifest_tags = manifest and manifest.get("pack", {}).get("tags")
        if isinstance(manifest_tags, list) and manifest_tags:
            explicit_tags = [str(item) for item in manifest_tags if str(item).strip()]
        else:
            skill_tags = frontmatter.get("tags")
            if isinstance(skill_tags, list) and skill_tags:
                explicit_tags = [str(item) for item in skill_tags if str(item).strip()]
            elif isinstance(skill_tags, str) and skill_tags.strip():
                explicit_tags = split_tags(skill_tags)

    return infer_tags(explicit_tags, pack_slug, title, category, candidate_files)


def build_manifest(
    *,
    creator_handle: str,
    pack_slug: str,
    title: str,
    summary: str,
    category: str,
    tags: list[str],
    repo_url: str,
    base_branch: str,
) -> dict:
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
            "repoUrl": canonicalize_repo_url(repo_url),
            "path": pack_dir,
        },
        "support": {
            "homepage": f"{canonicalize_repo_url(repo_url)}/tree/{base_branch}/{pack_dir}",
            "issues": f"{canonicalize_repo_url(repo_url)}/issues",
        },
    }


def render_skill_markdown(
    *,
    title: str,
    creator_handle: str,
    pack_slug: str,
    summary: str,
    category: str,
    tags: list[str],
    body: str,
    preserved_top_level: list[str],
) -> str:
    if not body.strip():
        body_lines = [
            f"# {title}",
            "",
            summary,
            "",
            "## What It Includes",
        ]
        if preserved_top_level:
            for entry in preserved_top_level:
                body_lines.append(f"- `{entry}`")
        else:
            body_lines.append("- `manifest.json`")
            body_lines.append("- `SKILL.md`")
        body_lines.extend(
            [
                "",
                "## Safe Usage Notes",
                "",
                "- keep files reviewable and public-safe",
                "- do not include secrets, symlinks, or executable installers",
            ]
        )
        body = "\n".join(body_lines)
    else:
        body = body.strip()

    frontmatter_lines = [
        "---",
        f'name: {json.dumps(title, ensure_ascii=True)}',
        f'slug: {json.dumps(pack_slug, ensure_ascii=True)}',
        f'creatorHandle: {json.dumps(creator_handle, ensure_ascii=True)}',
        f'category: {json.dumps(category, ensure_ascii=True)}',
        'priceType: "free"',
        "tags:",
    ]
    frontmatter_lines.extend(f"  - {json.dumps(tag, ensure_ascii=True)}" for tag in tags)
    frontmatter_lines.append(f'description: {json.dumps(summary, ensure_ascii=True)}')
    frontmatter_lines.append("---")
    frontmatter_lines.append("")
    frontmatter_lines.append(body)
    return "\n".join(frontmatter_lines).rstrip() + "\n"


def copy_candidates_to_stage(stage_dir: Path, candidates: list[CandidateFile]) -> list[str]:
    normalized_permissions: list[str] = []
    for candidate in candidates:
        destination_path = stage_dir / candidate.relative_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(candidate.source_path, destination_path)
        destination_path.chmod(0o644)
        if candidate.normalize_permissions:
            normalized_permissions.append(candidate.relative_path.as_posix())
    return normalized_permissions


def validate_with_central_script(target_path: Path, repo_url: str) -> str:
    changed_files = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in sorted(target_path.rglob("*"))
        if path.is_file()
    ]

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        handle.write("\n".join(changed_files) + "\n")
        changed_files_file = Path(handle.name)

    try:
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "validate-free-pack.py"),
                "--repo-root",
                str(REPO_ROOT),
                "--repo-url",
                canonicalize_repo_url(repo_url),
                "--changed-files-file",
                str(changed_files_file),
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    finally:
        changed_files_file.unlink(missing_ok=True)

    output = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part).strip()
    if result.returncode != 0:
        raise PrepError(output or "central validator failed")
    return output


def install_stage(stage_dir: Path, target_path: Path, allow_replace: bool, repo_url: str) -> None:
    target_parent = target_path.parent
    target_parent.mkdir(parents=True, exist_ok=True)

    if target_path.exists() and not allow_replace:
        raise PrepError(f"target pack dir already exists: {target_path}. Use --force to replace it.")

    with tempfile.TemporaryDirectory(prefix="free-pack-swap-") as swap_dir:
        backup_path = Path(swap_dir) / "backup"

        if target_path.exists():
            shutil.move(str(target_path), str(backup_path))

        shutil.move(str(stage_dir), str(target_path))

        try:
            validate_with_central_script(target_path, repo_url)
        except Exception:
            if target_path.exists():
                shutil.rmtree(target_path)
            if backup_path.exists():
                shutil.move(str(backup_path), str(target_path))
            raise


def build_report(
    *,
    target_path: Path,
    title: str,
    summary: str,
    category: str,
    tags: list[str],
    warnings: list[str],
    errors: list[str],
    preserved_top_level: list[str],
    validation_output: str | None,
    normalized_permissions: list[str],
) -> dict:
    return {
        "targetPackDir": target_path.relative_to(REPO_ROOT).as_posix(),
        "metadata": {
            "creatorHandle": target_path.parts[-2],
            "slug": target_path.parts[-1],
            "title": title,
            "summary": summary,
            "category": category,
            "tags": tags,
        },
        "preservedTopLevelEntries": preserved_top_level,
        "warnings": warnings,
        "errors": errors,
        "normalizedExecutablePermissions": normalized_permissions,
        "validationOutput": validation_output,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare a PR-ready free-pack submission from arbitrary local files.")
    parser.add_argument("--source-dir", required=True, help="Source directory containing the contributor files.")
    parser.add_argument("--target-pack-dir", required=True, help="Target pack dir, usually packs/<creator>/<slug>.")
    parser.add_argument("--repo-url", default=DEFAULT_REPO_URL, help="Canonical central repo URL for manifest generation.")
    parser.add_argument("--base-branch", default=DEFAULT_BASE_BRANCH, help="Base branch used for support.homepage.")
    parser.add_argument("--title", help="Override inferred pack title.")
    parser.add_argument("--summary", help="Override inferred pack summary.")
    parser.add_argument("--category", help="Override inferred pack category.")
    parser.add_argument("--tags", help="Comma-separated tag override.")
    parser.add_argument("--force", action="store_true", help="Replace an existing target pack dir.")
    parser.add_argument("--inspect-only", action="store_true", help="Inspect source files and print a report without writing.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    source_dir = Path(args.source_dir).resolve()
    if not source_dir.is_dir():
        raise PrepError(f"source dir does not exist: {source_dir}")

    target_path, creator_handle, pack_slug = resolve_target_pack_dir(args.target_pack_dir)

    if source_dir != target_path and target_path.is_relative_to(source_dir):
        raise PrepError("target pack dir may not be nested inside the source dir")

    manifest = load_json(source_dir / "manifest.json")
    frontmatter, skill_body, skill_errors = load_skill_source(source_dir)
    candidate_files, scan_warnings, scan_errors, preserved_top_level = inspect_source_tree(source_dir)

    title = choose_title(args.title, manifest, frontmatter, pack_slug)
    summary = choose_summary(args.summary, manifest, frontmatter, skill_body, source_dir, title)
    category = choose_category(args.category, manifest, frontmatter, title, summary, candidate_files)
    tags = choose_tags(args.tags, manifest, frontmatter, pack_slug, title, category, candidate_files)

    warnings = sorted(scan_warnings + [f"SKILL.md: {error}" for error in skill_errors])
    errors = sorted(scan_errors)

    report = build_report(
        target_path=target_path,
        title=title,
        summary=summary,
        category=category,
        tags=tags,
        warnings=warnings,
        errors=errors,
        preserved_top_level=preserved_top_level,
        validation_output=None,
        normalized_permissions=[],
    )

    if args.inspect_only or errors:
        print(json.dumps(report, indent=2, ensure_ascii=True))
        return 1 if errors else 0

    manifest_payload = build_manifest(
        creator_handle=creator_handle,
        pack_slug=pack_slug,
        title=title,
        summary=summary,
        category=category,
        tags=tags,
        repo_url=args.repo_url,
        base_branch=args.base_branch,
    )

    skill_markdown = render_skill_markdown(
        title=title,
        creator_handle=creator_handle,
        pack_slug=pack_slug,
        summary=summary,
        category=category,
        tags=tags,
        body=skill_body,
        preserved_top_level=preserved_top_level,
    )

    with tempfile.TemporaryDirectory(prefix="free-pack-stage-") as stage_root:
        stage_dir = Path(stage_root) / pack_slug
        stage_dir.mkdir(parents=True, exist_ok=True)
        normalized_permissions = copy_candidates_to_stage(stage_dir, candidate_files)
        (stage_dir / "manifest.json").write_text(json.dumps(manifest_payload, indent=2, ensure_ascii=True) + "\n")
        (stage_dir / "SKILL.md").write_text(skill_markdown)
        install_stage(
            stage_dir,
            target_path,
            allow_replace=args.force or source_dir == target_path,
            repo_url=args.repo_url,
        )

    validation_output = validate_with_central_script(target_path, args.repo_url)
    final_report = build_report(
        target_path=target_path,
        title=title,
        summary=summary,
        category=category,
        tags=tags,
        warnings=warnings,
        errors=[],
        preserved_top_level=preserved_top_level,
        validation_output=validation_output,
        normalized_permissions=normalized_permissions,
    )
    print(json.dumps(final_report, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PrepError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
