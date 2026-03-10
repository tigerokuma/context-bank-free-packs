from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


SEGMENT_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
TAG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,49}$")

ALLOWED_CATEGORIES = {
    "agriculture",
    "analysis",
    "automation",
    "business",
    "developer-tools",
    "developer_tools",
    "education",
    "investing",
    "marketing",
    "operations",
    "productivity",
    "research",
    "sports",
    "writing",
}

BLOCKED_EXTENSIONS = {
    ".app",
    ".bat",
    ".bin",
    ".bz2",
    ".cer",
    ".cmd",
    ".com",
    ".crt",
    ".db",
    ".deb",
    ".der",
    ".dll",
    ".dmg",
    ".exe",
    ".gz",
    ".jar",
    ".key",
    ".msi",
    ".pkg",
    ".p12",
    ".pem",
    ".pfx",
    ".ps1",
    ".rpm",
    ".sqlite",
    ".sqlite3",
    ".scr",
    ".sh",
    ".so",
    ".tar",
    ".tgz",
    ".xz",
    ".zip",
    ".7z",
    ".rar",
}

IGNORED_FILENAMES = {
    ".DS_Store",
    "Thumbs.db",
}

ALLOWED_BINARY_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}

BLOCKED_PATTERNS = [
    ("destructive shell command", re.compile(r"\brm\s+-rf\s+/", re.IGNORECASE)),
    (
        "download-and-execute pipe",
        re.compile(r"\b(?:curl|wget)\b[^\n|]{0,200}\|\s*(?:sh|bash|zsh)\b", re.IGNORECASE),
    ),
    (
        "ignore previous instructions prompt injection",
        re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions", re.IGNORECASE),
    ),
    (
        "reveal hidden prompt attempt",
        re.compile(
            r"(?:reveal|print|dump)\s+(?:the\s+)?(?:system|developer|hidden)\s+(?:prompt|instructions)",
            re.IGNORECASE,
        ),
    ),
    (
        "encoded powershell command",
        re.compile(r"\bpowershell(?:\.exe)?\b[^\n]{0,120}\s-enc(?:odedcommand)?\b", re.IGNORECASE),
    ),
    ("invoke-expression", re.compile(r"\b(?:invoke-expression|iex)\b", re.IGNORECASE)),
]

SECRET_PATTERNS = [
    ("GitHub personal access token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36}\b")),
    ("GitHub fine-grained personal access token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    (
        "AWS access key ID",
        re.compile(r"\b(?:A3T|AKIA|ASIA|AGPA|AIDA|AIPA|ANPA|ANVA|AROA)[A-Z0-9]{16}\b"),
    ),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    ("Slack token", re.compile(r"\bxox(?:a|b|p|r|s|o|t)-[0-9A-Za-z-]{10,}\b")),
    (
        "database URL with embedded credentials",
        re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis):\/\/[^\/\s:@]+:[^@\s]+@[^\/\s]+"),
    ),
    (
        "private key material",
        re.compile(r"-----BEGIN (?:(?:RSA|OPENSSH|EC|DSA) )?PRIVATE KEY-----"),
    ),
]

ALLOWED_ANCILLARY_PATTERNS = [
    re.compile(r"^README\.md$"),
    re.compile(r"^catalogs/pack-artifacts\.json$"),
    re.compile(r"^docs/context-bank/.+\.md$"),
]


def canonicalize_repo_url(url: str) -> str:
    value = url.strip()
    if value.startswith("git@github.com:"):
        value = "https://github.com/" + value.split(":", 1)[1]
    if value.endswith(".git"):
        value = value[:-4]
    return value.rstrip("/")


def read_changed_files(path: Path) -> list[str]:
    return [line.strip().replace("\\", "/") for line in path.read_text().splitlines() if line.strip()]


def path_to_pack_dir(relative_path: str) -> str | None:
    parts = PurePosixPath(relative_path).parts
    if len(parts) < 4 or parts[0] != "packs":
        return None
    creator, slug = parts[1], parts[2]
    if not SEGMENT_RE.fullmatch(creator) or not SEGMENT_RE.fullmatch(slug):
        return None
    return "/".join(parts[:3])


def classify_changed_files(changed_files: list[str]) -> tuple[set[str], list[str], list[str], list[str]]:
    pack_dirs: set[str] = set()
    invalid_pack_paths: list[str] = []
    allowed_ancillary: list[str] = []
    disallowed_other: list[str] = []

    for raw_path in changed_files:
        relative_path = raw_path.strip()
        if relative_path.startswith("./"):
            relative_path = relative_path[2:]
        if not relative_path:
            continue
        if relative_path.startswith("packs/"):
            pack_dir = path_to_pack_dir(relative_path)
            if pack_dir is None:
                invalid_pack_paths.append(relative_path)
            else:
                pack_dirs.add(pack_dir)
            continue

        if any(pattern.fullmatch(relative_path) for pattern in ALLOWED_ANCILLARY_PATTERNS):
            allowed_ancillary.append(relative_path)
        else:
            disallowed_other.append(relative_path)

    return pack_dirs, invalid_pack_paths, allowed_ancillary, disallowed_other


def load_manifest(manifest_path: Path) -> dict:
    return json.loads(manifest_path.read_text())


def normalize_identity(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def parse_frontmatter_list(value: str) -> list[str] | None:
    stripped = value.strip()
    if not (stripped.startswith("[") and stripped.endswith("]")):
        return None

    inner = stripped[1:-1].strip()
    if not inner:
        return []

    return [strip_quotes(item.strip()) for item in inner.split(",") if item.strip()]


def parse_skill_frontmatter(skill_path: Path) -> tuple[dict, list[str]]:
    text = skill_path.read_text()
    lines = text.splitlines()

    if not lines or lines[0].strip() != "---":
        return {}, [f"{skill_path.as_posix()}: missing YAML frontmatter"]

    frontmatter_lines: list[str] = []
    end_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = index
            break
        frontmatter_lines.append(line)

    if end_index is None:
        return {}, [f"{skill_path.as_posix()}: frontmatter is not closed with ---"]

    data: dict = {}
    errors: list[str] = []
    current_list_key: str | None = None

    for line in frontmatter_lines:
        if not line.strip():
            continue

        list_match = re.match(r"^\s*-\s+(.*)$", line)
        if list_match:
            if current_list_key is None:
                errors.append(f"{skill_path.as_posix()}: list item found before a key")
                continue
            data.setdefault(current_list_key, []).append(strip_quotes(list_match.group(1).strip()))
            continue

        key_match = re.match(r"^([A-Za-z0-9_-]+):(?:\s*(.*))?$", line)
        if not key_match:
            errors.append(f"{skill_path.as_posix()}: unsupported frontmatter line `{line}`")
            current_list_key = None
            continue

        key, raw_value = key_match.group(1), key_match.group(2) or ""
        if not raw_value:
            data[key] = []
            current_list_key = key
            continue

        inline_list = parse_frontmatter_list(raw_value)
        if inline_list is not None:
            data[key] = inline_list
        else:
            data[key] = strip_quotes(raw_value.strip())
        current_list_key = None

    return data, errors


def nested_get(data: dict, keys: list[str]):
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def validate_manifest(manifest: dict, pack_dir: str, creator: str, slug: str, expected_repo_url: str) -> list[str]:
    errors: list[str] = []
    manifest_path = f"{pack_dir}/manifest.json"

    schema_version = manifest.get("schemaVersion")
    if schema_version != 1:
        errors.append(f"{manifest_path}: schemaVersion must be 1")

    pack = manifest.get("pack")
    if not isinstance(pack, dict):
        errors.append(f"{manifest_path}: pack must be an object")
        return errors

    source = manifest.get("source")
    if not isinstance(source, dict):
        errors.append(f"{manifest_path}: source must be an object")
        return errors

    if pack.get("slug") != slug:
        errors.append(f"{manifest_path}: pack.slug must match `{slug}`")
    if pack.get("creatorHandle") != creator:
        errors.append(f"{manifest_path}: pack.creatorHandle must match `{creator}`")

    title = pack.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append(f"{manifest_path}: pack.title is required")

    summary = pack.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        errors.append(f"{manifest_path}: pack.summary is required")
    elif len(summary.strip()) > 240:
        errors.append(f"{manifest_path}: pack.summary must be 240 characters or fewer")

    category = pack.get("category")
    if category not in ALLOWED_CATEGORIES:
        allowed = ", ".join(sorted(ALLOWED_CATEGORIES))
        errors.append(f"{manifest_path}: pack.category must be one of: {allowed}")

    tags = pack.get("tags")
    if not isinstance(tags, list) or not tags:
        errors.append(f"{manifest_path}: pack.tags must be a non-empty array")
    else:
        invalid_tags = [tag for tag in tags if not isinstance(tag, str) or not TAG_RE.fullmatch(tag)]
        if invalid_tags:
            errors.append(
                f"{manifest_path}: pack.tags contains invalid values: {', '.join(map(str, invalid_tags))}"
            )

    if pack.get("priceType") != "free":
        errors.append(f"{manifest_path}: pack.priceType must be `free`")

    if source.get("type") != "internal_repo":
        errors.append(f"{manifest_path}: source.type must be `internal_repo` in MVP")

    manifest_repo_url = source.get("repoUrl")
    if not isinstance(manifest_repo_url, str) or canonicalize_repo_url(manifest_repo_url) != expected_repo_url:
        errors.append(f"{manifest_path}: source.repoUrl must point at `{expected_repo_url}`")

    if source.get("path") != pack_dir:
        errors.append(f"{manifest_path}: source.path must equal `{pack_dir}`")

    return errors


def validate_skill_frontmatter(skill_frontmatter: dict, pack_dir: str, creator: str, slug: str, manifest: dict) -> list[str]:
    errors: list[str] = []
    skill_path = f"{pack_dir}/SKILL.md"
    pack = manifest["pack"]

    if not skill_frontmatter:
        errors.append(f"{skill_path}: frontmatter is required")
        return errors

    if skill_frontmatter.get("priceType") != "free":
        errors.append(f"{skill_path}: frontmatter priceType must be `free`")

    if skill_frontmatter.get("category") != pack.get("category"):
        errors.append(f"{skill_path}: frontmatter category must match manifest pack.category")

    if "slug" in skill_frontmatter and skill_frontmatter.get("slug") != slug:
        errors.append(f"{skill_path}: frontmatter slug must match `{slug}`")

    if "creatorHandle" in skill_frontmatter and skill_frontmatter.get("creatorHandle") != creator:
        errors.append(f"{skill_path}: frontmatter creatorHandle must match `{creator}`")

    manifest_title = pack.get("title")
    skill_title = skill_frontmatter.get("title") or skill_frontmatter.get("name")
    if isinstance(skill_title, str) and isinstance(manifest_title, str):
        if normalize_identity(skill_title) != normalize_identity(manifest_title):
            errors.append(f"{skill_path}: frontmatter title/name must align with manifest pack.title")

    return errors


def decode_utf8_text(raw: bytes) -> str | None:
    if b"\x00" in raw:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def scan_text_content(relative_path: str, text: str) -> list[str]:
    errors: list[str] = []

    for label, pattern in BLOCKED_PATTERNS:
        if pattern.search(text):
            errors.append(f"{relative_path}: blocked pattern detected ({label})")

    for label, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            errors.append(f"{relative_path}: secret-like content detected ({label})")

    return errors


def scan_pack_file(
    path: Path,
    *,
    display_root: Path,
    pack_root: Path,
    allow_executable_permissions: bool = False,
) -> list[str]:
    errors: list[str] = []
    relative_path = path.relative_to(display_root).as_posix()
    pack_relative_parts = path.relative_to(pack_root).parts
    stat_result = path.lstat()

    if path.is_symlink():
        errors.append(f"{relative_path}: symlinks are not allowed")
        return errors

    if any(part in IGNORED_FILENAMES for part in pack_relative_parts):
        errors.append(f"{relative_path}: junk OS files are not allowed")
        return errors

    if any(part.startswith(".") for part in pack_relative_parts):
        errors.append(f"{relative_path}: hidden files or directories are not allowed")
        return errors

    if not allow_executable_permissions and stat_result.st_mode & 0o111:
        errors.append(f"{relative_path}: executable file permissions are not allowed")

    suffix = path.suffix.lower()
    if suffix in BLOCKED_EXTENSIONS:
        errors.append(f"{relative_path}: blocked file extension `{suffix}`")

    try:
        raw = path.read_bytes()
    except OSError as exc:
        errors.append(f"{relative_path}: failed to read file ({exc})")
        return errors

    text = decode_utf8_text(raw)
    if text is None:
        if suffix not in ALLOWED_BINARY_EXTENSIONS:
            allowed = ", ".join(sorted(ALLOWED_BINARY_EXTENSIONS))
            errors.append(
                f"{relative_path}: binary or non-UTF-8 files are not allowed unless the extension is one of: {allowed}"
            )
        return errors

    errors.extend(scan_text_content(relative_path, text))
    return errors


def find_scan_errors(repo_root: Path, pack_dir: str) -> list[str]:
    errors: list[str] = []
    pack_path = repo_root / pack_dir

    for path in sorted(pack_path.rglob("*")):
        if path.is_dir():
            continue

        errors.extend(
            scan_pack_file(
                path,
                display_root=repo_root,
                pack_root=pack_path,
            )
        )

    return errors


def validate_pack_directory(repo_root: Path, pack_dir: str, expected_repo_url: str) -> tuple[list[str], dict | None, dict | None]:
    errors: list[str] = []
    parts = PurePosixPath(pack_dir).parts
    creator, slug = parts[1], parts[2]

    pack_path = repo_root / pack_dir
    manifest_path = pack_path / "manifest.json"
    skill_path = pack_path / "SKILL.md"

    if not manifest_path.is_file():
        errors.append(f"{pack_dir}/manifest.json: required file is missing")
        return errors, None, None

    if not skill_path.is_file():
        errors.append(f"{pack_dir}/SKILL.md: required file is missing")
        return errors, None, None

    try:
        manifest = load_manifest(manifest_path)
    except json.JSONDecodeError as exc:
        errors.append(f"{pack_dir}/manifest.json: invalid JSON ({exc})")
        return errors, None, None

    skill_frontmatter, frontmatter_errors = parse_skill_frontmatter(skill_path)
    errors.extend(frontmatter_errors)
    errors.extend(validate_manifest(manifest, pack_dir, creator, slug, expected_repo_url))
    errors.extend(validate_skill_frontmatter(skill_frontmatter, pack_dir, creator, slug, manifest))
    errors.extend(find_scan_errors(repo_root, pack_dir))

    return errors, manifest, skill_frontmatter


def iso_utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
