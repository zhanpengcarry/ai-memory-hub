"""Tests for memory_hub.harness_client module."""

from __future__ import annotations

from unittest.mock import patch, MagicMock
from memory_hub.harness_client import (
    HarnessClient,
    _ts_to_iso,
    _execution_to_entry,
    collect_harness_entries,
)


class TestTsToIso:
    """Tests for _ts_to_iso helper."""

    def test_valid_timestamp(self):
        # 2024-01-15T10:30:00 UTC
        result = _ts_to_iso(1705312200000)
        assert result is not None
        assert "2024-01-15" in result

    def test_none_returns_none(self):
        assert _ts_to_iso(None) is None

    def test_zero_returns_none(self):
        assert _ts_to_iso(0) is None

    def test_negative_converts(self):
        # 负时间戳仍可转换（对应 1970 之前的日期）
        result = _ts_to_iso(-1)
        # 不抛异常即可，具体值取决于平台


class TestExecutionToEntry:
    """Tests for _execution_to_entry function."""

    def _make_exec(self, **overrides):
        base = {
            "name": "deploy-prod",
            "status": "Success",
            "triggerType": "MANUAL",
            "executionId": "exec-123",
            "pipelineIdentifier": "pipeline-abc",
            "orgIdentifier": "myorg",
            "projectIdentifier": "myproj",
            "startTs": 1705312200000,
            "endTs": 1705312260000,
        }
        base.update(overrides)
        return base

    def test_basic_entry(self):
        item = self._make_exec()
        entry = _execution_to_entry(item, "2024-01-15T10:31:00+00:00", "https://app.harness.io")
        assert entry.source == "harness"
        assert "deploy-prod" in entry.title
        assert "Success" in entry.title
        assert "harness" in entry.tags
        assert "success" in entry.tags
        assert "myorg" in entry.tags
        assert entry.extra["executionId"] == "exec-123"

    def test_body_contains_details(self):
        item = self._make_exec()
        entry = _execution_to_entry(item, "now", "https://app.harness.io")
        assert "deploy-prod" in entry.body
        assert "Success" in entry.body
        assert "MANUAL" in entry.body
        assert "myorg" in entry.body
        assert "myproj" in entry.body
        assert "1m0s" in entry.body

    def test_missing_fields_use_defaults(self):
        item = {"status": "Running"}
        entry = _execution_to_entry(item, "now", "https://app.harness.io")
        assert entry.source == "harness"
        assert "未知 Pipeline" in entry.title
        assert entry.extra["status"] == "Running"

    def test_duration_over_one_minute(self):
        item = self._make_exec(startTs=1705312200000, endTs=1705312380000)  # 3 min
        entry = _execution_to_entry(item, "now", "https://app.harness.io")
        assert "3m0s" in entry.body

    def test_no_timestamps(self):
        item = {"name": "test", "status": "Queued"}
        entry = _execution_to_entry(item, "now", "https://app.harness.io")
        assert entry.created_at is None
        assert entry.updated_at == "now"


class TestHarnessClient:
    """Tests for HarnessClient."""

    def test_init(self):
        c = HarnessClient(api_key="key123", base_url="https://example.com/", account_identifier="acc1")
        assert c.api_key == "key123"
        assert c.base_url == "https://example.com"  # trailing slash stripped
        assert c.account_identifier == "acc1"

    @patch("memory_hub.harness_client.urllib.request.urlopen")
    def test_list_executions_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"data": {"content": [{"name": "p1", "status": "Success"}]}}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        c = HarnessClient(api_key="key", account_identifier="acc")
        items = c.list_executions(limit=10)
        assert len(items) == 1
        assert items[0]["name"] == "p1"

    @patch("memory_hub.harness_client.urllib.request.urlopen")
    def test_list_executions_empty(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"data": {"content": []}}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        c = HarnessClient(api_key="key", account_identifier="acc")
        items = c.list_executions()
        assert items == []

    @patch("memory_hub.harness_client.urllib.request.urlopen")
    def test_list_executions_status_filter(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"data": {"content": [{"status": "Success"}, {"status": "Failed"}]}}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        c = HarnessClient(api_key="key", account_identifier="acc")
        items = c.list_executions(status_filter=["Failed"])
        assert len(items) == 1
        assert items[0]["status"] == "Failed"


class TestCollectHarnessEntries:
    """Tests for collect_harness_entries function."""

    def test_no_api_key_returns_empty(self):
        block = {"enabled": True}
        result = collect_harness_entries(block)
        assert result == []

    @patch("memory_hub.harness_client.HarnessClient.list_executions")
    def test_collect_with_mock_api(self, mock_list):
        mock_list.return_value = [
            {
                "name": "deploy-app",
                "status": "Success",
                "triggerType": "WEBHOOK",
                "executionId": "exec-1",
                "pipelineIdentifier": "pipe-1",
                "orgIdentifier": "org1",
                "projectIdentifier": "proj1",
                "startTs": 1705312200000,
                "endTs": 1705312260000,
            }
        ]
        block = {
            "api_key": "test-key",
            "account_identifier": "test-acc",
            "limit": 10,
        }
        entries = collect_harness_entries(block)
        assert len(entries) == 1
        assert entries[0].source == "harness"
        assert "deploy-app" in entries[0].title

    @patch("memory_hub.harness_client.HarnessClient.list_executions")
    def test_collect_api_error_with_file_errors(self, mock_list):
        mock_list.side_effect = RuntimeError("API Error")
        block = {"api_key": "test-key", "account_identifier": "acc"}
        errors: list[tuple[str, str, str]] = []
        entries = collect_harness_entries(block, file_errors=errors)
        assert entries == []
        assert len(errors) == 1
        assert "harness" in errors[0][0]
