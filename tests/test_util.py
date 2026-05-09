"""Tests for memory_hub.util module."""

import pytest

from memory_hub.util import load_yaml_config, write_text


class TestLoadYamlConfig:
    """Tests for load_yaml_config function."""

    def test_valid_yaml(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("key: value\nlist:\n  - a\n  - b\n", encoding="utf-8")
        result = load_yaml_config(f)
        assert result["key"] == "value"
        assert result["list"] == ["a", "b"]

    def test_empty_yaml(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("", encoding="utf-8")
        result = load_yaml_config(f)
        assert result == {}

    def test_invalid_yaml(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text(":\n  - :\n  invalid", encoding="utf-8")
        with pytest.raises(SystemExit):
            load_yaml_config(f)

    def test_missing_file(self, tmp_path):
        f = tmp_path / "nonexistent.yaml"
        with pytest.raises(SystemExit):
            load_yaml_config(f)


class TestWriteText:
    """Tests for write_text function."""

    def test_creates_file(self, tmp_path):
        f = tmp_path / "test.txt"
        write_text(f, "Hello world")
        assert f.read_text(encoding="utf-8") == "Hello world"

    def test_creates_parent_dirs(self, tmp_path):
        f = tmp_path / "sub" / "dir" / "test.txt"
        write_text(f, "Hello world")
        assert f.read_text(encoding="utf-8") == "Hello world"

    def test_overwrites_existing(self, tmp_path):
        f = tmp_path / "test.txt"
        write_text(f, "First")
        write_text(f, "Second")
        assert f.read_text(encoding="utf-8") == "Second"

    def test_atomic_write(self, tmp_path):
        """Test that write is atomic (no partial writes)."""
        f = tmp_path / "test.txt"
        write_text(f, "Hello world")
        # No temp files should remain
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0
