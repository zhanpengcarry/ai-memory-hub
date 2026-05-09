"""Tests for memory_hub.io_util module."""

from memory_hub.io_util import read_text_flexible


class TestReadTextFlexible:
    """Tests for read_text_flexible function."""

    def test_utf8_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("Hello world", encoding="utf-8")
        assert read_text_flexible(f) == "Hello world"

    def test_utf8_bom_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_bytes(b"\xef\xbb\xbfHello world")
        result = read_text_flexible(f)
        assert result == "Hello world"
        assert not result.startswith("\ufeff")

    def test_utf8_with_special_chars(self, tmp_path):
        f = tmp_path / "test.txt"
        content = "Hello 你好世界 🌍"
        f.write_text(content, encoding="utf-8")
        assert read_text_flexible(f) == content

    def test_empty_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_bytes(b"")
        assert read_text_flexible(f) == ""
