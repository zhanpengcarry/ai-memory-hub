from __future__ import annotations

import hashlib
from pathlib import Path

from memory_hub.sources import iter_source_blocks
from memory_hub.util import load_yaml_config


def sources_fingerprint(config_path: Path) -> str:
    """根据配置文件本身 + 各纳入文件的 mtime/size 生成指纹，用于 watch。

    包含 config 指纹后，仅修改 YAML（例如换路径）也会触发重新同步。
    """
    from memory_hub.paths import collect_paths_for_block

    lines: list[str] = []
    try:
        st = config_path.resolve().stat()
        lines.append(f"__config__\t{config_path.resolve()}\t{st.st_mtime_ns}\t{st.st_size}")
    except OSError:
        lines.append(f"__config__\t{config_path.resolve()}\tmissing")

    cfg = load_yaml_config(config_path)
    hub_root = config_path.parent.resolve()
    defaults = cfg.get("defaults") or {}
    extra_exclude = list(defaults.get("exclude_globs") or [])

    for name, block in iter_source_blocks(cfg):
        if not block.get("enabled", True):
            continue
        paths = collect_paths_for_block(block, hub_root, extra_exclude=extra_exclude)
        for p in paths:
            try:
                st = p.stat()
                lines.append(f"{name}\t{p}\t{st.st_mtime_ns}\t{st.st_size}")
            except OSError:
                lines.append(f"{name}\t{p}\tmissing")

    return hashlib.sha256("\n".join(sorted(lines)).encode("utf-8", errors="replace")).hexdigest()
