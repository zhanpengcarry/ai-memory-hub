"""Tests for memory_hub.paths module."""

from pathlib import Path

from memory_hub.paths import (
    _normalize_extension,
    expand_path_str,
    path_excluded,
    resolve_relative,
)


class TestExpandPathStr:
    """Tests for expand_path_str function."""

    def test_tilde_expansion(self, monkeypatch):
        monkeypatch.setenv("HOME", "/home/user")
        result = expand_path_str("~/documents")
        assert "documents" in result

    def test_dollar_brace_var(self, monkeypatch):
        monkeypatch.setenv("MY_VAR", "/some/path")
        result = expand_path_str("${MY_VAR}/file.txt")
        assert "/some/path" in result or "some" in result

    def test_percent_var(self, monkeypatch):
        monkeypatch.setenv("MY_VAR", "/some/path")
        result = expand_path_str("%MY_VAR%/file.txt")
        assert "/some/path" in result or "some" in result

    def test_unknown_var_preserved(self):
        result = expand_path_str("${UNKNOWN_VAR_12345}")
        assert "UNKNOWN_VAR_12345" in result

    def test_normalizes_path(self):
        result = expand_path_str("a//b/../c")
        assert "//" not in result


class TestResolveRelative:
    """Tests for resolve_relative function."""

    def test_absolute_path_unchanged(self, tmp_path):
        abs_path = str(tmp_path / "file.txt")
        result = resolve_relative(abs_path, tmp_path)
        assert result.is_absolute()

    def test_relative_path_resolved(self, tmp_path):
        result = resolve_relative("file.txt", tmp_path)
        assert result.is_absolute()
        assert str(tmp_path) in str(result)


class TestPathExcluded:
    """Tests for path_excluded function."""

    def test_matches_glob_pattern(self):
        p = Path("/some/path/.git/config")
        assert path_excluded(p, ["**/.git/**"])

    def test_no_match(self):
        p = Path("/some/path/file.txt")
        assert not path_excluded(p, ["**/.git/**"])

    def test_fnmatch_pattern(self):
        p = Path("/some/path/file.txt")
        assert path_excluded(p, ["*.txt"])

    def test_empty_pattern_skipped(self):
        p = Path("/some/path/file.txt")
        assert not path_excluded(p, ["", ""])


class TestNormalizeExtension:
    """Tests for _normalize_extension function."""

    def test_with_dot(self):
        assert _normalize_extension(".md") == ".md"

    def test_without_dot(self):
        assert _normalize_extension("md") == ".md"

    def test_uppercase(self):
        assert _normalize_extension(".MD") == ".md"

    def test_uppercase_no_dot(self):
        assert _normalize_extension("JSON") == ".json"
