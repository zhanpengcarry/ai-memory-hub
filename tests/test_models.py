"""Tests for memory_hub.models module."""

from datetime import datetime

from memory_hub.models import MemoryEntry, normalize_body, stable_id, utc_now_iso


class TestNormalizeBody:
    """Tests for normalize_body function."""

    def test_strips_leading_trailing_whitespace(self):
        assert normalize_body("  hello  ") == "hello"

    def test_normalizes_line_endings(self):
        assert normalize_body("a\r\nb\r\nc") == "a\nb\nc"

    def test_strips_trailing_whitespace_per_line(self):
        assert normalize_body("a  \nb  \nc") == "a\nb\nc"

    def test_nfc_normalization(self):
        # e + combining accent vs precomposed e
        assert normalize_body("\u0065\u0301") == normalize_body("\u00e9")

    def test_empty_string(self):
        assert normalize_body("") == ""

    def test_whitespace_only(self):
        assert normalize_body("   \n  \n  ") == ""


class TestStableId:
    """Tests for stable_id function."""

    def test_deterministic(self):
        id1 = stable_id("claude", "hello")
        id2 = stable_id("claude", "hello")
        assert id1 == id2

    def test_different_source_different_id(self):
        id1 = stable_id("claude", "hello")
        id2 = stable_id("codex", "hello")
        assert id1 != id2

    def test_different_body_different_id(self):
        id1 = stable_id("claude", "hello")
        id2 = stable_id("claude", "world")
        assert id1 != id2

    def test_format(self):
        sid = stable_id("claude", "hello")
        assert sid.startswith("mem-")
        assert len(sid) == 20  # "mem-" + 16 hex chars


class TestUtcNowIso:
    """Tests for utc_now_iso function."""

    def test_returns_iso_format(self):
        ts = utc_now_iso()
        # Should be parseable
        dt = datetime.fromisoformat(ts)
        assert dt.tzinfo is not None

    def test_no_microseconds(self):
        ts = utc_now_iso()
        assert "." not in ts


class TestMemoryEntry:
    """Tests for MemoryEntry class."""

    def test_basic_creation(self):
        entry = MemoryEntry(source="claude", body="hello")
        assert entry.source == "claude"
        assert entry.body == "hello"
        assert entry.title is None
        assert entry.tags == []

    def test_id_property(self):
        entry = MemoryEntry(source="claude", body="hello")
        assert entry.id.startswith("mem-")

    def test_normalized_body_property(self):
        entry = MemoryEntry(source="claude", body="  hello  ")
        assert entry.normalized_body == "hello"

    def test_to_dict(self):
        entry = MemoryEntry(source="claude", body="hello", title="Test")
        d = entry.to_dict()
        assert d["source"] == "claude"
        assert d["body"] == "hello"
        assert d["title"] == "Test"
        assert "id" in d

    def test_from_dict(self):
        d = {
            "source": "claude",
            "body": "hello",
            "title": "Test",
            "tags": ["a", "b"],
        }
        entry = MemoryEntry.from_dict(d)
        assert entry.source == "claude"
        assert entry.body == "hello"
        assert entry.title == "Test"
        assert entry.tags == ["a", "b"]

    def test_from_dict_minimal(self):
        d = {"source": "claude", "body": "hello"}
        entry = MemoryEntry.from_dict(d)
        assert entry.source == "claude"
        assert entry.body == "hello"
        assert entry.tags == []

    def test_roundtrip(self):
        entry = MemoryEntry(
            source="claude",
            body="hello",
            title="Test",
            tags=["a"],
            extra={"key": "value"},
        )
        d = entry.to_dict()
        restored = MemoryEntry.from_dict(d)
        assert restored.source == entry.source
        assert restored.body == entry.body
        assert restored.title == entry.title
        assert restored.tags == entry.tags
