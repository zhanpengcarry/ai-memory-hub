from memory_hub.merge import merge_entries
from memory_hub.models import MemoryEntry


def test_merge_deduplicates_same_body_across_sources():
    a = MemoryEntry(source="claude", body="  hello\n")
    b = MemoryEntry(source="codex", body="hello")
    m = merge_entries([a, b])
    assert len(m) == 1
    assert set(m[0]["sources"]) == {"claude", "codex"}
