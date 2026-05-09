from __future__ import annotations

import json
from pathlib import Path

from memory_hub.models import MemoryEntry, normalize_body, utc_now_iso
from memory_hub.util import write_text


def merge_entries(entries: list[MemoryEntry]) -> list[dict]:
    """按规范化正文去重，合并来源与时间。"""
    buckets: dict[str, dict] = {}
    for e in entries:
        key = normalize_body(e.body)
        if not key:
            continue
        d = buckets.get(key)
        if d is None:
            buckets[key] = {
                "id": e.id,
                "sources": {e.source},
                "title": e.title,
                "body": e.body,
                "tags": set(e.tags),
                "created_at": e.created_at,
                "updated_at": e.updated_at,
                "provenance": [e.provenance] if e.provenance else [],
                "extra": dict(e.extra),
                "file_date": e.created_at if e.source == "openclaw" else None,
            }
        else:
            d["sources"].add(e.source)
            if e.title and not d.get("title"):
                d["title"] = e.title
            d["tags"].update(e.tags)
            for k, v in e.extra.items():
                if k not in d["extra"]:
                    d["extra"][k] = v
            if e.provenance:
                d["provenance"].append(e.provenance)
            # 取较晚的 updated_at
            if e.updated_at and (not d["updated_at"] or e.updated_at > d["updated_at"]):
                d["updated_at"] = e.updated_at
            if e.created_at and (not d["created_at"] or e.created_at < d["created_at"]):
                d["created_at"] = e.created_at
            # 保留 OpenClaw 的 file_date
            if e.source == "openclaw" and e.created_at:
                d["file_date"] = e.created_at
    merged: list[dict] = []
    for v in buckets.values():
        merged.append(
            {
                "id": stable_merged_id(v["sources"], normalize_body(v["body"])),
                "sources": sorted(v["sources"]),
                "title": v["title"],
                "body": v["body"],
                "tags": sorted(v["tags"]),
                "created_at": v["created_at"],
                "updated_at": v["updated_at"] or utc_now_iso(),
                "provenance": [p for p in v["provenance"] if p],
                "extra": v["extra"],
            }
        )
    # 排序：优先使用 file_date（OpenClaw 日期），其次 updated_at
    merged.sort(
        key=lambda x: (
            x.get("extra", {}).get("file_date") or 
            x.get("created_at") or 
            x.get("updated_at") or ""
        ), 
        reverse=True
    )
    return merged


def stable_merged_id(sources: set[str], normalized_body: str) -> str:
    import hashlib

    src = "|".join(sorted(sources))
    h = hashlib.sha256(f"{src}\n{normalized_body}".encode()).hexdigest()[:16]
    return f"hub-{h}"


SCHEMA_VERSION = 1


def write_merged_json(path: Path, merged: list[dict]) -> None:
    write_text(path, json.dumps(merged, ensure_ascii=False, indent=2, default=str))


def write_hub_meta(path: Path, *, entry_count: int, merged_count: int, sources: dict[str, int]) -> None:
    meta = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "entry_count": entry_count,
        "merged_count": merged_count,
        "sources": sources,
    }
    write_text(path, json.dumps(meta, ensure_ascii=False, indent=2, default=str))


def write_merged_markdown(path: Path, merged: list[dict]) -> None:
    lines: list[str] = ["# 合并记忆（自动生成）", ""]
    lines.append(f"_生成时间（UTC）：{utc_now_iso()}_")
    lines.append("")
    for i, m in enumerate(merged, 1):
        title = m.get("title") or f"片段 {i}"
        lines.append(f"## {title}")
        lines.append("")
        lines.append(f"- **来源**: {', '.join(m.get('sources') or [])}")
        lines.append(f"- **ID**: `{m.get('id')}`")
        if m.get("tags"):
            lines.append(f"- **标签**: {', '.join(m['tags'])}")
        lines.append("")
        lines.append(m.get("body") or "")
        lines.append("")
        lines.append("---")
        lines.append("")
    write_text(path, "\n".join(lines).rstrip() + "\n")


def save_pull_snapshot(source: str, path: Path, entries: list[MemoryEntry]) -> None:
    payload = [e.to_dict() for e in entries]
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, default=str))
