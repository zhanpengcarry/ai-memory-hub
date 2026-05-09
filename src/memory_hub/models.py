from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    """Return current UTC time as ISO8601 string without microseconds."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_id(source: str, normalized_body: str) -> str:
    """Generate stable ID from source and normalized body using SHA-256."""
    h = hashlib.sha256(f"{source}\n{normalized_body}".encode()).hexdigest()[:16]
    return f"mem-{h}"


def normalize_body(text: str) -> str:
    """Normalize text body for deduplication.

    Applies Unicode NFC normalization and strips trailing whitespace per line.
    This reduces false duplicates from different editors saving with different
    Unicode equivalence forms.
    """
    text = unicodedata.normalize("NFC", text)
    return "\n".join(line.rstrip() for line in text.strip().replace("\r\n", "\n").split("\n"))


@dataclass
class MemoryEntry:
    """Represents a single memory entry from any source.

    Attributes:
        source: Source identifier (claude, codex, opencode, openclaw, manual)
        body: Markdown content body
        title: Optional short title
        tags: List of string tags
        created_at: ISO8601 creation timestamp
        updated_at: ISO8601 update timestamp
        provenance: Original file path for traceability
        extra: Additional metadata as key-value pairs
    """

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
        """Get normalized body for deduplication."""
        return normalize_body(self.body)

    @property
    def id(self) -> str:
        """Get stable ID based on source and normalized body."""
        return stable_id(self.source, self.normalized_body)

    def to_dict(self) -> dict[str, Any]:
        """Convert entry to dictionary for serialization."""
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
        """Create entry from dictionary.

        Args:
            d: Dictionary with entry data

        Returns:
            MemoryEntry instance

        Raises:
            KeyError: If required 'source' or 'body' keys are missing
        """
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
