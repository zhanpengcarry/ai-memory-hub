from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_id(source: str, normalized_body: str) -> str:
    h = hashlib.sha256(f"{source}\n{normalized_body}".encode("utf-8")).hexdigest()[:16]
    return f"mem-{h}"


def normalize_body(text: str) -> str:
    import unicodedata

    # NFC：减少不同编辑器保存时 Unicode 等价形式不同导致的假重复
    text = unicodedata.normalize("NFC", text)
    return "\n".join(line.rstrip() for line in text.strip().replace("\r\n", "\n").split("\n"))


@dataclass
class MemoryEntry:
    source: str
    body: str
    title: str | None = None
    tags: list[str] = field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None
    provenance: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def normalized_body(self) -> str:
        return normalize_body(self.body)

    @property
    def id(self) -> str:
        return stable_id(self.source, self.normalized_body)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "title": self.title,
            "body": self.body,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "provenance": self.provenance,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MemoryEntry:
        return cls(
            source=d["source"],
            body=d["body"],
            title=d.get("title"),
            tags=list(d.get("tags") or []),
            created_at=d.get("created_at"),
            updated_at=d.get("updated_at"),
            provenance=d.get("provenance"),
            extra=dict(d.get("extra") or {}),
        )
