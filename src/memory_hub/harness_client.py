"""Harness DevOps 平台 API 客户端 — 采集 pipeline 执行记录并转为 MemoryEntry。"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any

from memory_hub.models import MemoryEntry, utc_now_iso

# Harness API 路径
_LIST_EXECUTIONS_PATH = "/gateway/pipeline/api/pipelines/execution"
_EXECUTION_DETAIL_PATH = "/gateway/pipeline/api/pipelines/execution/{executionId}"


class HarnessClient:
    """Harness REST API 客户端。"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://app.harness.io",
        account_identifier: str = "",
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.account_identifier = account_identifier

    def _request(self, path: str, params: dict[str, str] | None = None) -> dict:
        """发送 GET 请求并返回 JSON 响应。"""
        url = f"{self.base_url}{path}"
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items() if v)
            if query:
                url = f"{url}?{query}"

        req = urllib.request.Request(url, method="GET")
        req.add_header("x-api-key", self.api_key)
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise RuntimeError(f"Harness API 错误 {e.code}: {body}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Harness API 连接失败: {e.reason}") from e

    def list_executions(
        self,
        *,
        org_identifier: str = "",
        project_identifier: str = "",
        pipeline_identifier: str = "",
        status_filter: list[str] | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """列出 pipeline 执行记录。"""
        params: dict[str, str] = {
            "accountIdentifier": self.account_identifier,
            "limit": str(limit),
        }
        if org_identifier:
            params["orgIdentifier"] = org_identifier
        if project_identifier:
            params["projectIdentifier"] = project_identifier
        if pipeline_identifier:
            params["pipelineIdentifier"] = pipeline_identifier

        data = self._request(_LIST_EXECUTIONS_PATH, params)

        content = data.get("data", {})
        items: list[dict] = content.get("content") if isinstance(content, dict) else []
        if not items:
            items = data.get("data") if isinstance(data.get("data"), list) else []
        if not items:
            return []

        if status_filter:
            statuses = {s.lower() for s in status_filter}
            items = [it for it in items if (it.get("status") or "").lower() in statuses]

        return items


def _ts_to_iso(ts_ms: int | None) -> str | None:
    """将毫秒时间戳转为 ISO8601 字符串。"""
    if not ts_ms:
        return None
    try:
        return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()
    except (OSError, ValueError):
        return None


def _execution_to_entry(
    exec_item: dict,
    now: str,
    base_url: str,
) -> MemoryEntry:
    """将一条 pipeline 执行记录转为 MemoryEntry。"""
    name = exec_item.get("name") or exec_item.get("pipelineIdentifier") or "未知 Pipeline"
    status = exec_item.get("status") or "Unknown"
    trigger_type = exec_item.get("triggerType") or "未知"
    exec_id = exec_item.get("executionId") or ""
    pipeline_id = exec_item.get("pipelineIdentifier") or ""
    org = exec_item.get("orgIdentifier") or ""
    project = exec_item.get("projectIdentifier") or ""
    start_ts = exec_item.get("startTs")
    end_ts = exec_item.get("endTs")

    start_at = _ts_to_iso(start_ts)
    end_at = _ts_to_iso(end_ts)

    duration_str = ""
    if start_ts and end_ts:
        secs = (end_ts - start_ts) // 1000
        if secs >= 60:
            duration_str = f"{secs // 60}m{secs % 60}s"
        else:
            duration_str = f"{secs}s"

    title = f"{name} — {status}"
    tags = ["harness", status.lower()]
    if org:
        tags.append(org)
    if project:
        tags.append(project)
    tags = list(dict.fromkeys(tags))  # 去重保序

    body_parts = [f"## {name}", "", f"- **状态**: {status}"]
    body_parts.append(f"- **触发方式**: {trigger_type}")
    if org:
        body_parts.append(f"- **组织**: {org}")
    if project:
        body_parts.append(f"- **项目**: {project}")
    if pipeline_id:
        body_parts.append(f"- **Pipeline ID**: `{pipeline_id}`")
    if start_at:
        body_parts.append(f"- **开始时间**: {start_at}")
    if end_at:
        body_parts.append(f"- **结束时间**: {end_at}")
    if duration_str:
        body_parts.append(f"- **耗时**: {duration_str}")
    if exec_id:
        body_parts.append(f"- **执行 ID**: `{exec_id}`")
    body = "\n".join(body_parts)

    provenance = f"{base_url}/ng/account/{org}/cd/orgs/{org}/projects/{project}/pipelines/{pipeline_id}/deployments/{exec_id}"

    extra: dict[str, Any] = {}
    for k in ("executionId", "pipelineIdentifier", "orgIdentifier", "projectIdentifier", "triggerType", "status"):
        if exec_item.get(k):
            extra[k] = exec_item[k]

    return MemoryEntry(
        source="harness",
        body=body,
        title=title,
        tags=tags,
        created_at=start_at,
        updated_at=end_at or now,
        provenance=provenance,
        extra=extra,
    )


def collect_harness_entries(
    block: dict,
    *,
    file_errors: list[tuple[str, str, str]] | None = None,
) -> list[MemoryEntry]:
    """从 Harness API 采集 pipeline 执行记录并转为 MemoryEntry 列表。"""
    api_key = block.get("api_key") or ""
    if not api_key:
        return []

    base_url = block.get("base_url") or "https://app.harness.io"
    account_id = block.get("account_identifier") or ""
    org_id = block.get("org_identifier") or ""
    project_id = block.get("project_identifier") or ""
    pipeline_id = block.get("pipeline_identifier") or ""
    status_filter = block.get("status_filter") or None
    limit = int(block.get("limit") or 50)

    client = HarnessClient(
        api_key=api_key,
        base_url=base_url,
        account_identifier=account_id,
    )

    now = utc_now_iso()
    try:
        items = client.list_executions(
            org_identifier=org_id,
            project_identifier=project_id,
            pipeline_identifier=pipeline_id,
            status_filter=status_filter,
            limit=limit,
        )
    except Exception as e:
        if file_errors is not None:
            file_errors.append(("harness", "harness-api", f"{type(e).__name__}: {e}"))
            return []
        raise

    entries: list[MemoryEntry] = []
    for item in items:
        try:
            entries.append(_execution_to_entry(item, now, base_url))
        except Exception as e:
            if file_errors is not None:
                file_errors.append(("harness", "harness-api", f"{type(e).__name__}: {e}"))
    return entries
