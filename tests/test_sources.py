"""Tests for memory_hub.sources module."""

from memory_hub.sources import iter_source_blocks


class TestIterSourceBlocks:
    """Tests for iter_source_blocks function."""

    def test_empty_config(self):
        result = iter_source_blocks({})
        assert len(result) == 5
        names = [name for name, _ in result]
        assert "claude" in names
        assert "codex" in names
        assert "opencode" in names
        assert "openclaw" in names
        assert "harness" in names

    def test_with_config(self):
        cfg = {
            "claude": {"enabled": True, "glob_paths": ["*.md"]},
            "codex": {"enabled": False},
        }
        result = iter_source_blocks(cfg)
        claude_block = next(block for name, block in result if name == "claude")
        assert claude_block["enabled"] is True
        assert claude_block["glob_paths"] == ["*.md"]

    def test_missing_sources_default_empty(self):
        cfg = {"claude": {"enabled": True}}
        result = iter_source_blocks(cfg)
        codex_block = next(block for name, block in result if name == "codex")
        assert codex_block == {}
