from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from memory_hub.constants import MAX_PARSE_ERRORS_RECORDED
from memory_hub.io_util import read_text_flexible
from memory_hub.models import MemoryEntry, normalize_body, utc_now_iso
from memory_hub.paths import collect_paths_for_block

# JSON body keys in order of priority
_JSON_BODY_KEYS = (
    "body",
    "content",
    "text",
    "summary",
    "memory",
    "note",
    "message",
    "value",
    "instruction",
    "instructions",
)

# File extensions recognized as markdown
_MD_EXTENSIONS = {".md", ".mdc", ".markdown", ".txt", ""}

# JSON wrapper keys that may contain nested arrays
_JSON_WRAPPER_KEYS = ("memories", "items", "entries")

# Hashtag pattern: matches #tag but not ## heading
_HASHTAG_PATTERN = re.compile(r'(?<!#)#([a-zA-Z\u4e00-\u9fff][a-zA-Z0-9\u4e00-\u9fff_-]*)')

# Date pattern for filenames like 2024-01-15.md
_DATE_PATTERN = re.compile(r'(\d{4}-\d{2}-\d{2})')


def _extract_date_from_filename(path: Path) -> str | None:
    """Extract date from filename (supports YYYY-MM-DD format).

    Args:
        path: File path to extract date from

    Returns:
        ISO8601 date string or None if no date found
    """
    match = _DATE_PATTERN.search(path.stem)
    if match:
        try:
            dt = datetime.strptime(match.group(1), '%Y-%m-%d')
            return dt.replace(hour=0, minute=0, second=0).isoformat()
        except ValueError:
            pass
    return None


def _extract_hashtags(text: str) -> list[str]:
    """Extract #hashtag tags from text.

    Args:
        text: Text to extract hashtags from

    Returns:
        List of unique hashtags (without # prefix)
    """
    return list(set(_HASHTAG_PATTERN.findall(text)))


def collect_from_source(
    source_name: str,
    block: dict,
    hub_root: Path,
    *,
    defaults: dict | None = None,
    file_errors: list[tuple[str, str, str]] | None = None,
) -> list[MemoryEntry]:
    """Collect memory entries from a single source.

    Args:
        source_name: Name of the source (claude, codex, etc.)
        block: Source configuration block
        hub_root: Root directory for path resolution
        defaults: Default configuration values
        file_errors: List to append error tuples (source, path, message)

    Returns:
        List of collected MemoryEntry instances
    """
    defaults = defaults or {}
    min_body = int(block.get("min_body_chars", defaults.get("min_body_chars", 20)))
    global_exclude = list(defaults.get("exclude_globs") or [])

    paths = collect_paths_for_block(block, hub_root, extra_exclude=global_exclude)
    entries: list[MemoryEntry] = []
    now = utc_now_iso()
    split_h2 = bool(block.get("split_level2_headings", defaults.get("split_level2_headings", False)))
    parser = str(block.get("parser", defaults.get("parser", "auto"))).lower()
    extract_date = bool(block.get("extract_date_from_filename", defaults.get("extract_date_from_filename", False)))
    extract_tags = bool(block.get("extract_hashtags", defaults.get("extract_hashtags", False)))

    for path in paths:
        try:
            entries.extend(
                parse_file_to_entries(
                    path,
                    source_name,
                    now,
                    min_body_chars=min_body,
                    split_h2=split_h2,
                    parser=parser,
                    extract_date=extract_date,
                    extract_tags=extract_tags,
                )
            )
        except Exception as e:
            if file_errors is not None:
                if len(file_errors) < MAX_PARSE_ERRORS_RECORDED:
                    file_errors.append((source_name, str(path), f"{type(e).__name__}: {e}"))
            else:
                raise
    return entries


def parse_file_to_entries(
    path: Path,
    source_name: str,
    now: str,
    *,
    min_body_chars: int,
    split_h2: bool,
    parser: str,
    extract_date: bool = False,
    extract_tags: bool = False,
) -> list[MemoryEntry]:
    """Parse a single file into memory entries.

    Args:
        path: File path to parse
        source_name: Name of the source
        now: Current ISO timestamp
        min_body_chars: Minimum body length threshold
        split_h2: Whether to split by H2 headings
        parser: Parser type (auto, json, markdown, text)
        extract_date: Whether to extract date from filename
        extract_tags: Whether to extract hashtags from content

    Returns:
        List of parsed MemoryEntry instances
    """
    suffix = path.suffix.lower()
    use_json = parser == "json" or (parser == "auto" and suffix == ".json")
    use_md = parser in ("markdown", "md", "text") or (parser == "auto" and suffix in _MD_EXTENSIONS)

    # Extract date from filename if enabled
    file_date = _extract_date_from_filename(path) if extract_date else None

    if use_json:
        return _parse_json_entries(source_name, path, now, min_body_chars, file_date=file_date, extract_tags=extract_tags)

    if use_md or parser == "auto":
        try:
            text = read_text_flexible(path)
        except OSError:
            return []

        # Auto-detect JSON if content starts with { or [
        if parser == "auto" and text.lstrip().startswith(("{", "[")):
            json_entries = _parse_json_entries(source_name, path, now, min_body_chars, file_date=file_date, extract_tags=extract_tags)
            if json_entries:
                return json_entries

        body, fm_title, fm_tags = _parse_markdown_maybe_frontmatter(text)

        # Extract hashtags if enabled
        hashtags = _extract_hashtags(body) if extract_tags else []
        all_tags = list(set(fm_tags + hashtags))

        if split_h2:
            return _split_and_create_entries(body, fm_title, all_tags, source_name, path, now, min_body_chars, file_date=file_date, extract_tags=extract_tags)

        if len(normalize_body(body)) < min_body_chars:
            return []

        # Extract hashtags from body if enabled
        body_tags = _extract_hashtags(body) if extract_tags else []
        final_tags = list(set(all_tags + body_tags))

        return [
            MemoryEntry(
                source=source_name,
                body=body,
                title=fm_title,
                tags=final_tags,
                created_at=file_date,
                updated_at=now,
                provenance=str(path),
            )
        ]

    return []


def _split_and_create_entries(
    body: str,
    fm_title: str | None,
    fm_tags: list[str],
    source_name: str,
    path: Path,
    now: str,
    min_body_chars: int,
    file_date: str | None = None,
    extract_tags: bool = False,
) -> list[MemoryEntry]:
    """Split markdown by H2 headings and create entries.

    Args:
        body: Markdown body text
        fm_title: Title from frontmatter
        fm_tags: Tags from frontmatter
        source_name: Name of the source
        path: Source file path
        now: Current ISO timestamp
        min_body_chars: Minimum body length threshold
        file_date: Date extracted from filename
        extract_tags: Whether to extract hashtags from content

    Returns:
        List of MemoryEntry instances
    """
    sections = _split_markdown_by_h2(body)

    # Single section case
    if len(sections) <= 1 and sections:
        sec_title, sec_body = sections[0]
        merged_title = fm_title or sec_title or None
        if len(normalize_body(sec_body)) < min_body_chars:
            return []

        # Extract hashtags if enabled
        body_tags = _extract_hashtags(sec_body) if extract_tags else []
        final_tags = list(set(fm_tags + body_tags))

        return [
            MemoryEntry(
                source=source_name,
                body=sec_body,
                title=merged_title,
                tags=final_tags,
                created_at=file_date,
                updated_at=now,
                provenance=str(path),
            )
        ]

    # Multiple sections
    out: list[MemoryEntry] = []
    for i, (sec_title, sec_body) in enumerate(sections):
        if len(normalize_body(sec_body)) < min_body_chars:
            continue
        merged_title = f"{fm_title} — {sec_title}" if fm_title and sec_title else (fm_title or sec_title or None)

        # Add date to provenance
        prov = f"{path}#h2:{i}"
        if file_date:
            prov = f"{path}@{file_date}#h2:{i}"

        # Extract hashtags if enabled
        body_tags = _extract_hashtags(sec_body) if extract_tags else []
        final_tags = list(set(fm_tags + body_tags))

        out.append(
            MemoryEntry(
                source=source_name,
                body=sec_body,
                title=merged_title,
                tags=final_tags,
                created_at=file_date,
                updated_at=now,
                provenance=prov,
            )
        )
    return out


def _split_markdown_by_h2(body: str) -> list[tuple[str, str]]:
    """Split markdown by H2 headings (ignoring H3+).

    Args:
        body: Markdown text to split

    Returns:
        List of (title, body) tuples
    """
    lines = body.strip().splitlines()
    if not lines:
        return [("", "")]

    title = ""
    buf: list[str] = []
    out: list[tuple[str, str]] = []

    def flush() -> None:
        nonlocal title, buf
        chunk = "\n".join(buf).strip()
        if title or chunk:
            out.append((title, chunk))
        title = ""
        buf = []

    for line in lines:
        if line.startswith("## ") and not line.startswith("###"):
            flush()
            title = line[3:].strip()
            buf = []
        else:
            buf.append(line)
    flush()
    return out if out else [("", body.strip())]


def _parse_markdown_maybe_frontmatter(text: str) -> tuple[str, str | None, list[str]]:
    """Parse markdown with optional YAML frontmatter.

    Args:
        text: Raw markdown text

    Returns:
        Tuple of (body, title, tags)
    """
    if not text.startswith("---"):
        return text, None, []

    lines = text.splitlines()
    if len(lines) < 2:
        return text, None, []

    # Find closing ---
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break

    if end is None:
        return text, None, []

    fm_raw = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1 :])

    title: str | None = None
    tags: list[str] = []

    for line in fm_raw.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip().strip('"')
        if k.lower() == "title":
            title = v or None
        elif k.lower() in ("tags", "tag"):
            tags = [t.strip() for t in v.strip("[]").split(",") if t.strip()]

    return body, title, tags


def _parse_json_entries(
    source_name: str, 
    path: Path, 
    now: str, 
    min_body_chars: int,
    file_date: str | None = None,
    extract_tags: bool = False,
) -> list[MemoryEntry]:
    """Parse JSON file into memory entries.

    Args:
        source_name: Name of the source
        path: Path to JSON file
        now: Current ISO timestamp
        min_body_chars: Minimum body length threshold
        file_date: Date extracted from filename
        extract_tags: Whether to extract hashtags from content

    Returns:
        List of parsed MemoryEntry instances
    """
    text = read_text_flexible(path)
    out: list[MemoryEntry] = []
    for obj in _iter_json_items(text):
        entry = _memory_entry_from_json_obj(
            source_name, path, obj, now, min_body_chars, 
            file_date=file_date, extract_tags=extract_tags
        )
        if entry:
            out.append(entry)
    return out


def _iter_json_items(text: str) -> list[dict]:
    """Iterate JSON items from text, supporting various formats.

    Supports:
    - Single JSON object
    - JSON array
    - NDJSON (newline-delimited JSON)
    - Wrapped formats with memories/items/entries keys

    Args:
        text: Raw JSON text

    Returns:
        List of dictionaries
    """
    text_stripped = text.strip()
    if not text_stripped:
        return []

    # Try NDJSON first (multiple lines, each starting with {)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) > 1 and all(ln.lstrip().startswith("{") for ln in lines):
        items: list[dict] = []
        for ln in lines:
            try:
                data = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                items.append(data)
        if items:
            return items

    # Try standard JSON
    try:
        data = json.loads(text_stripped)
    except json.JSONDecodeError:
        return []

    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]

    if isinstance(data, dict):
        # Check for wrapped formats
        for key in _JSON_WRAPPER_KEYS:
            nested = data.get(key)
            if isinstance(nested, list) and nested and all(isinstance(x, dict) for x in nested):
                return nested
        return [data]

    return []


def _extract_body_from_messages(obj: dict) -> str | None:
    """Extract body from messages array in JSON object.

    Args:
        obj: JSON object with potential messages array

    Returns:
        Concatenated message content or None
    """
    msgs = obj.get("messages")
    if not isinstance(msgs, list):
        return None

    parts: list[str] = []
    for m in msgs:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        c = m.get("content")
        if isinstance(c, str) and c.strip():
            parts.append(f"[{role}]: {c}" if role else c)

    return "\n\n".join(parts) if parts else None


def _memory_entry_from_json_obj(
    source_name: str,
    path: Path,
    obj: dict,
    now: str,
    min_body_chars: int,
    file_date: str | None = None,
    extract_tags: bool = False,
) -> MemoryEntry | None:
    """Create MemoryEntry from JSON object.

    Args:
        source_name: Name of the source
        path: Source file path
        obj: JSON object dictionary
        now: Current ISO timestamp
        min_body_chars: Minimum body length threshold
        file_date: Date extracted from filename
        extract_tags: Whether to extract hashtags from content

    Returns:
        MemoryEntry or None if body is too short
    """
    # Try to find body from known keys
    body: str | None = None
    for key in _JSON_BODY_KEYS:
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            body = val
            break

    # Fallback to messages array
    if body is None:
        body = _extract_body_from_messages(obj)

    # Fallback to simple key-value dump for small objects
    if body is None:
        if len(obj) <= 8 and all(isinstance(v, (str, int, float, bool)) or v is None for v in obj.values()):
            body = "\n".join(f"{k}: {v}" for k, v in obj.items() if v is not None)
        else:
            return None

    if len(normalize_body(body)) < min_body_chars:
        return None

    title = obj.get("title") if isinstance(obj.get("title"), str) else None
    tags = [str(t) for t in obj["tags"]] if isinstance(obj.get("tags"), list) else []
    created = obj.get("created_at") if isinstance(obj.get("created_at"), str) else file_date
    updated = obj.get("updated_at") if isinstance(obj.get("updated_at"), str) else now

    # Extract hashtags if enabled
    if extract_tags:
        hashtags = _extract_hashtags(body)
        tags = list(set(tags + hashtags))

    skip = set(_JSON_BODY_KEYS) | {"title", "tags", "created_at", "updated_at", "messages"}
    extra = {k: v for k, v in obj.items() if k not in skip}

    return MemoryEntry(
        source=source_name,
        body=body,
        title=title,
        tags=tags,
        created_at=created,
        updated_at=updated,
        provenance=str(path),
        extra=extra,
    )
