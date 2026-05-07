from __future__ import annotations


def iter_source_blocks(cfg: dict) -> list[tuple[str, dict]]:
    return [
        ("claude", cfg.get("claude") or {}),
        ("codex", cfg.get("codex") or {}),
        ("opencode", cfg.get("opencode") or {}),
        ("openclaw", cfg.get("openclaw") or {}),
    ]
