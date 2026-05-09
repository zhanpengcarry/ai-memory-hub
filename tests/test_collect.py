"""Tests for memory_hub.collect module."""

import json
from pathlib import Path

from memory_hub.collect import (
    _extract_date_from_filename,
    _extract_hashtags,
    _iter_json_items,
    _memory_entry_from_json_obj,
    _parse_markdown_maybe_frontmatter,
    _split_markdown_by_h2,
    parse_file_to_entries,
)


class TestSplitMarkdownByH2:
    """Tests for _split_markdown_by_h2 function."""

    def test_empty_body(self):
        result = _split_markdown_by_h2("")
        assert result == [("", "")]

    def test_no_h2(self):
        result = _split_markdown_by_h2("Some text\nMore text")
        assert len(result) == 1
        assert result[0] == ("", "Some text\nMore text")

    def test_single_h2(self):
        body = "## Title\nContent"
        result = _split_markdown_by_h2(body)
        assert len(result) == 1
        assert result[0] == ("Title", "Content")

    def test_multiple_h2(self):
        body = "## First\nContent 1\n## Second\nContent 2"
        result = _split_markdown_by_h2(body)
        assert len(result) == 2
        assert result[0] == ("First", "Content 1")
        assert result[1] == ("Second", "Content 2")

    def test_h3_not_split(self):
        body = "## Title\n### Sub\nContent"
        result = _split_markdown_by_h2(body)
        assert len(result) == 1
        assert "### Sub" in result[0][1]


class TestParseMarkdownMaybeFrontmatter:
    """Tests for _parse_markdown_maybe_frontmatter function."""

    def test_no_frontmatter(self):
        body, title, tags = _parse_markdown_maybe_frontmatter("Hello world")
        assert body == "Hello world"
        assert title is None
        assert tags == []

    def test_with_frontmatter(self):
        text = "---\ntitle: Test\ntags: [a, b]\n---\n\nBody content"
        body, title, tags = _parse_markdown_maybe_frontmatter(text)
        assert body == "\nBody content"
        assert title == "Test"
        assert tags == ["a", "b"]

    def test_incomplete_frontmatter(self):
        text = "---\ntitle: Test\nBody content"
        body, title, _tags = _parse_markdown_maybe_frontmatter(text)
        assert body == text
        assert title is None

    def test_frontmatter_with_quotes(self):
        text = '---\ntitle: "Quoted Title"\ntags: [x]\n---\n\nBody'
        _body, title, _tags = _parse_markdown_maybe_frontmatter(text)
        assert title == "Quoted Title"


class TestIterJsonItems:
    """Tests for _iter_json_items function."""

    def test_empty_string(self):
        assert _iter_json_items("") == []
        assert _iter_json_items("   ") == []

    def test_single_object(self):
        data = {"key": "value"}
        result = _iter_json_items(json.dumps(data))
        assert len(result) == 1
        assert result[0]["key"] == "value"

    def test_array(self):
        data = [{"id": 1}, {"id": 2}]
        result = _iter_json_items(json.dumps(data))
        assert len(result) == 2

    def test_ndjson(self):
        text = '{"id": 1}\n{"id": 2}\n'
        result = _iter_json_items(text)
        assert len(result) == 2

    def test_wrapped_format(self):
        data = {"memories": [{"id": 1}, {"id": 2}]}
        result = _iter_json_items(json.dumps(data))
        assert len(result) == 2

    def test_invalid_json(self):
        assert _iter_json_items("not json") == []


class TestMemoryEntryFromJsonObj:
    """Tests for _memory_entry_from_json_obj function."""

    def test_basic_entry(self):
        obj = {"body": "Hello", "title": "Test"}
        entry = _memory_entry_from_json_obj("claude", Path("test.json"), obj, "2024-01-01", 5)
        assert entry is not None
        assert entry.body == "Hello"
        assert entry.title == "Test"

    def test_body_too_short(self):
        obj = {"body": "Hi"}
        entry = _memory_entry_from_json_obj("claude", Path("test.json"), obj, "2024-01-01", 10)
        assert entry is None

    def test_content_key(self):
        obj = {"content": "Hello world content"}
        entry = _memory_entry_from_json_obj("claude", Path("test.json"), obj, "2024-01-01", 5)
        assert entry is not None
        assert entry.body == "Hello world content"

    def test_messages_format(self):
        obj = {
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"},
            ]
        }
        entry = _memory_entry_from_json_obj("claude", Path("test.json"), obj, "2024-01-01", 5)
        assert entry is not None
        assert "[user]" in entry.body

    def test_simple_key_value(self):
        obj = {"key1": "value1", "key2": "value2"}
        entry = _memory_entry_from_json_obj("claude", Path("test.json"), obj, "2024-01-01", 5)
        assert entry is not None
        assert "key1: value1" in entry.body


class TestParseFileToEntries:
    """Tests for parse_file_to_entries function."""

    def test_markdown_file(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("# Title\n\nHello world content here", encoding="utf-8")
        entries = parse_file_to_entries(f, "claude", "2024-01-01", min_body_chars=5, split_h2=False, parser="auto")
        assert len(entries) == 1

    def test_json_file(self, tmp_path):
        f = tmp_path / "test.json"
        f.write_text('{"body": "Hello world content here"}', encoding="utf-8")
        entries = parse_file_to_entries(f, "claude", "2024-01-01", min_body_chars=5, split_h2=False, parser="auto")
        assert len(entries) == 1

    def test_split_h2(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("## Section 1\nContent 1\n## Section 2\nContent 2", encoding="utf-8")
        entries = parse_file_to_entries(f, "claude", "2024-01-01", min_body_chars=5, split_h2=True, parser="auto")
        assert len(entries) == 2


class TestExtractDateFromFilename:
    """Tests for _extract_date_from_filename function."""

    def test_valid_date(self):
        path = Path("2024-01-15.md")
        result = _extract_date_from_filename(path)
        assert result is not None
        assert "2024-01-15" in result

    def test_date_with_prefix(self):
        path = Path("memory-2024-01-15.md")
        result = _extract_date_from_filename(path)
        assert result is not None
        assert "2024-01-15" in result

    def test_date_with_suffix(self):
        path = Path("2024-01-15-diary.md")
        result = _extract_date_from_filename(path)
        assert result is not None
        assert "2024-01-15" in result

    def test_no_date(self):
        path = Path("MEMORY.md")
        result = _extract_date_from_filename(path)
        assert result is None

    def test_invalid_date(self):
        path = Path("2024-13-45.md")
        result = _extract_date_from_filename(path)
        assert result is None


class TestExtractHashtags:
    """Tests for _extract_hashtags function."""

    def test_single_tag(self):
        text = "This is a #test message"
        result = _extract_hashtags(text)
        assert result == ["test"]

    def test_multiple_tags(self):
        text = "Meeting with #team about #project-alpha"
        result = _extract_hashtags(text)
        assert set(result) == {"team", "project-alpha"}

    def test_chinese_tags(self):
        text = "今天开了 #会议 讨论了 #项目进展"
        result = _extract_hashtags(text)
        assert set(result) == {"会议", "项目进展"}

    def test_no_tags(self):
        text = "No hashtags here"
        result = _extract_hashtags(text)
        assert result == []

    def test_heading_not_extracted(self):
        text = "## This is a heading\nNot a #tag"
        result = _extract_hashtags(text)
        assert result == ["tag"]

    def test_duplicate_tags(self):
        text = "#test and #test again"
        result = _extract_hashtags(text)
        assert len(result) == 1
        assert result[0] == "test"


class TestOpenClawEnhancedParsing:
    """Tests for OpenClaw enhanced parsing features."""

    def test_extract_date_from_filename_enabled(self, tmp_path):
        f = tmp_path / "2024-01-15.md"
        f.write_text("## Section\nContent with enough length", encoding="utf-8")
        entries = parse_file_to_entries(
            f, "openclaw", "2024-12-01", 
            min_body_chars=5, split_h2=False, parser="auto",
            extract_date=True
        )
        assert len(entries) == 1
        assert entries[0].created_at is not None
        assert "2024-01-15" in entries[0].created_at

    def test_extract_date_from_filename_disabled(self, tmp_path):
        f = tmp_path / "2024-01-15.md"
        f.write_text("## Section\nContent with enough length", encoding="utf-8")
        entries = parse_file_to_entries(
            f, "openclaw", "2024-12-01", 
            min_body_chars=5, split_h2=False, parser="auto",
            extract_date=False
        )
        assert len(entries) == 1
        assert entries[0].created_at is None

    def test_extract_hashtags_enabled(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("## Meeting\nDiscussed #project with #team", encoding="utf-8")
        entries = parse_file_to_entries(
            f, "openclaw", "2024-01-01", 
            min_body_chars=5, split_h2=False, parser="auto",
            extract_tags=True
        )
        assert len(entries) == 1
        assert set(entries[0].tags) == {"project", "team"}

    def test_extract_hashtags_disabled(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("## Meeting\nDiscussed #project with #team", encoding="utf-8")
        entries = parse_file_to_entries(
            f, "openclaw", "2024-01-01", 
            min_body_chars=5, split_h2=False, parser="auto",
            extract_tags=False
        )
        assert len(entries) == 1
        assert entries[0].tags == []

    def test_smart_split_with_date(self, tmp_path):
        f = tmp_path / "2024-01-15.md"
        f.write_text("## Morning\nDid some work\n## Afternoon\nMore work", encoding="utf-8")
        entries = parse_file_to_entries(
            f, "openclaw", "2024-12-01", 
            min_body_chars=5, split_h2=True, parser="auto",
            extract_date=True
        )
        assert len(entries) == 2
        for entry in entries:
            assert entry.created_at is not None
            assert "2024-01-15" in entry.created_at
            assert "2024-01-15" in entry.provenance

    def test_smart_split_with_hashtags(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("## Meeting\nDiscussed #project\n## Review\nReviewed #code", encoding="utf-8")
        entries = parse_file_to_entries(
            f, "openclaw", "2024-01-01", 
            min_body_chars=5, split_h2=True, parser="auto",
            extract_tags=True
        )
        assert len(entries) == 2
        assert "project" in entries[0].tags
        assert "code" in entries[1].tags

    def test_combined_features(self, tmp_path):
        f = tmp_path / "2024-01-15.md"
        f.write_text("## Morning\nDid #coding work\n## Afternoon\n#meeting with team", encoding="utf-8")
        entries = parse_file_to_entries(
            f, "openclaw", "2024-12-01", 
            min_body_chars=5, split_h2=True, parser="auto",
            extract_date=True, extract_tags=True
        )
        assert len(entries) == 2
        # Check first entry
        assert "2024-01-15" in entries[0].created_at
        assert "coding" in entries[0].tags
        # Check second entry
        assert "2024-01-15" in entries[1].created_at
        assert "meeting" in entries[1].tags
