from __future__ import annotations

import json
from pathlib import Path

from memory_hub.io_util import read_text_flexible
from memory_hub.models import MemoryEntry, normalize_body, utc_now_iso
from memory_hub.paths import collect_paths_for_block

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


def collect_from_source(
    source_name: str,
    block: dict,
    hub_root: Path,
    *,
    defaults: dict | None = None,
    file_errors: list[tuple[str, str, str]] | None = None,
) -> list[MemoryEntry]:
    defaults = defaults or {}
    min_body = int(block.get("min_body_chars", defaults.get("min_body_chars", 20)))
    global_exclude = list(defaults.get("exclude_globs") or [])

    paths = collect_paths_for_block(block, hub_root, extra_exclude=global_exclude)
    entries: list[MemoryEntry] = []
    now = utc_now_iso()
    split_h2 = bool(block.get("split_level2_headings", defaults.get("split_level2_headings", False)))
    parser = str(block.get("parser", defaults.get("parser", "auto"))).lower()

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
                )
            )
        except Exception as e:
            if file_errors is not None:
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
) -> list[MemoryEntry]:
    suffix = path.suffix.lower()
    use_json = parser == "json" or (parser == "auto" and suffix == ".json")
    use_md = parser in ("markdown", "md", "text") or (
        parser == "auto" and suffix in (".md", ".mdc", ".markdown", ".txt", "")
    )

    if use_json:
        return _parse_json_entries(source_name, path, now, min_body_chars)

    if use_md or parser == "auto":
        try:
            text = read_text_flexible(path)
        except OSError:
            return []
        if parser == "auto" and text.lstrip().startswith(("{", "[")):
            je = _parse_json_entries(source_name, path, now, min_body_chars)
            if je:
                return je

        body, fm_title, fm_tags = _parse_markdown_maybe_frontmatter(text)

        if split_h2:
            sections = _split_markdown_by_h2(body)
            if len(sections) <= 1 and sections:
                sec_title, sec_body = sections[0]
                merged_title = fm_title or sec_title or None
                if len(normalize_body(sec_body)) < min_body_chars:
                    return []
                return [
                    MemoryEntry(
                        source=source_name,
                        body=sec_body,
                        title=merged_title,
                        tags=list(fm_tags),
                        updated_at=now,
                        provenance=str(path),
                    )
                ]

            out: list[MemoryEntry] = []
            for i, (sec_title, sec_body) in enumerate(sections):
                if len(normalize_body(sec_body)) < min_body_chars:
                    continue
                merged_title = (
                    f"{fm_title} — {sec_title}" if fm_title and sec_title else (fm_title or sec_title or None)
                )
                prov = f"{path}#h2:{i}"
                out.append(
                    MemoryEntry(
                        source=source_name,
                        body=sec_body,
                        title=merged_title,
                        tags=list(fm_tags),
                        updated_at=now,
                        provenance=prov,
                    )
                )
            return out

        if len(normalize_body(body)) < min_body_chars:
            return []
        return [
            MemoryEntry(
                source=source_name,
                body=body,
                title=fm_title,
                tags=list(fm_tags),
                updated_at=now,
                provenance=str(path),
            )
        ]

    return []


def _split_markdown_by_h2(body: str) -> list[tuple[str, str]]:
    """按二级标题分段（忽略 ### 及以下）。"""
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
    if not text.startswith("---"):
        return text, None, []
    lines = text.splitlines()
    if len(lines) < 2:
        return text, None, []
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


def _parse_json_entries(source_name: str, path: Path, now: str, min_body_chars: int) -> list[MemoryEntry]:
    text = read_text_flexible(path)
    out: list[MemoryEntry] = []
    for obj in _iter_json_items(text):
        entry = _memory_entry_from_json_obj(source_name, path, obj, now, min_body_chars)
        if entry:
            out.append(entry)
    return out


def _iter_json_items(text: str) -> list[dict]:
    text_stripped = text.strip()
    if not text_stripped:
        return []

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

    try:
        data = json.loads(text_stripped)
    except json.JSONDecodeError:
        return []

    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        nested = data.get("memories") or data.get("items") or data.get("entries")
        if isinstance(nested, list) and nested and all(isinstance(x, dict) for x in nested):
            return nested
        return [data]
    return []


def _memory_entry_from_json_obj(
    source_name: str,
    path: Path,
    obj: dict,
    now: str,
    min_body_chars: int,
) -> MemoryEntry | None:
    body: str | None = None
    for key in _JSON_BODY_KEYS:
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            body = val
            break

    if body is None:
        msgs = obj.get("messages")
        if isinstance(msgs, list):
            parts: list[str] = []
            for m in msgs:
                if not isinstance(m, dict):
                    continue
                role = m.get("role")
                c = m.get("content")
                if isinstance(c, str) and c.strip():
                    parts.append(f"[{role}]: {c}" if role else c)
            if parts:
                body = "\n\n".join(parts)

    if body is None:
        if len(obj) <= 8 and all(isinstance(v, (str, int, float, bool)) or v is None for v in obj.values()):
            body = "\n".join(f"{k}: {v}" for k, v in obj.items() if v is not None)
        else:
            return None

    if len(normalize_body(body)) < min_body_chars:
        return None

    title = obj.get("title") if isinstance(obj.get("title"), str) else None
    tags = [str(t) for t in obj["tags"]] if isinstance(obj.get("tags"), list) else []
    created = obj.get("created_at") if isinstance(obj.get("created_at"), str) else None
    updated = obj.get("updated_at") if isinstance(obj.get("updated_at"), str) else now
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
