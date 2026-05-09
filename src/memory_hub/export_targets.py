from __future__ import annotations

from pathlib import Path

from memory_hub.util import write_text


def export_all(merged: list[dict], dirs: dict[str, str | Path]) -> None:
    """向各工具导出人类可读的引用文件（不覆盖厂商私有状态）。"""
    body = _shared_markdown(merged)

    if p := dirs.get("for_claude"):
        write_text(Path(p) / "SHARED_CONTEXT.md", _claude_wrapper(body))
    if p := dirs.get("for_codex"):
        write_text(Path(p) / "HUB_MEMORY_REFERENCE.md", _codex_wrapper(body))
    if p := dirs.get("for_opencode"):
        write_text(Path(p) / "hub-import.md", _opencode_block(body))
    if p := dirs.get("for_openclaw"):
        write_text(Path(p) / "MEMORY.injection.md", _openclaw_wrapper(body))


def _shared_markdown(merged: list[dict]) -> str:
    if not merged:
        return "_（Hub 尚无合并条目：请先运行 `memory-hub discover` 检查路径，或调低 `min_body_chars`。）_\n"
    chunks: list[str] = []
    for i, m in enumerate(merged, 1):
        title = m.get("title") or f"条目 {i}"
        src = ", ".join(m.get("sources") or [])
        chunks.append(f"### {title}\n\n_来源: {src}_\n\n{m.get('body') or ''}\n")
    return "\n---\n\n".join(chunks)


def _claude_wrapper(inner: str) -> str:
    return "<!-- 由 ai-memory-hub 生成；可粘贴进 CLAUDE.md 或用 @ 引用 -->\n\n# 跨工具共享记忆\n\n" + inner + "\n"


def _codex_wrapper(inner: str) -> str:
    return "<!-- 供 Codex 阅读；请勿当作 Codex 官方 memories 目录的替代 -->\n\n# Hub 记忆摘要\n\n" + inner + "\n"


def _opencode_block(inner: str) -> str:
    return "---\ntitle: hub-import\ntags: [hub, cross-agent]\n---\n\n" + inner + "\n"


def _openclaw_wrapper(inner: str) -> str:
    return "<!-- 可合并进 OpenClaw MEMORY.md 或按需在会话中加载 -->\n\n## Hub 注入记忆\n\n" + inner + "\n"
