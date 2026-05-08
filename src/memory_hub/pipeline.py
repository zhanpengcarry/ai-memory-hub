from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from memory_hub.collect import collect_from_source
from memory_hub.constants import MAX_PARSE_ERRORS_RECORDED
from memory_hub.export_targets import export_all
from memory_hub.merge import merge_entries, save_pull_snapshot, write_hub_meta, write_merged_json, write_merged_markdown
from memory_hub.models import MemoryEntry
from memory_hub.sources import iter_source_blocks
from memory_hub.util import load_yaml_config


@dataclass
class SyncResult:
    hub_data: Path
    entry_count: int
    merged_count: int
    sources: dict[str, int]
    file_errors: list[tuple[str, str, str]] = field(default_factory=list)
    dry_run: bool = False


def run_sync(
    config_path: Path,
    *,
    dry_run: bool = False,
    verbose: bool = False,
    quiet: bool = False,
) -> SyncResult:
    cfg = load_yaml_config(config_path)
    hub_root = config_path.parent.resolve()
    defaults = cfg.get("defaults") or {}
    hub_data = Path(cfg.get("hub_data_dir", "./hub_data"))
    if not hub_data.is_absolute():
        hub_data = (hub_root / hub_data).resolve()
    hub_data.mkdir(parents=True, exist_ok=True)

    file_errors: list[tuple[str, str, str]] = []
    all_entries: list[MemoryEntry] = []
    per_source_count: dict[str, int] = {}

    for name, block in iter_source_blocks(cfg):
        if not block.get("enabled", True):
            per_source_count[name] = 0
            save_pull_snapshot(name, hub_data / "snapshots" / f"{name}.json", [])
            continue
        items = collect_from_source(name, block, hub_root, defaults=defaults, file_errors=file_errors)
        per_source_count[name] = len(items)
        save_pull_snapshot(name, hub_data / "snapshots" / f"{name}.json", items)
        all_entries.extend(items)
        if verbose:
            print(f"  [{name}] 解析 {len(items)} 条记忆片段")

    merged = merge_entries(all_entries)
    write_merged_json(hub_data / "merged.json", merged)
    write_merged_markdown(hub_data / "MERGED.md", merged)
    write_hub_meta(
        hub_data / "meta.json",
        entry_count=len(all_entries),
        merged_count=len(merged),
        sources=per_source_count,
    )

    if not dry_run:
        export_cfg = cfg.get("export") or {}
        export_dirs = {
            k: (hub_root / v).resolve() if not Path(v).is_absolute() else Path(v) for k, v in export_cfg.items()
        }
        export_all(merged, export_dirs)

    if not quiet:
        print(f"完成：共 {len(all_entries)} 条原始片段，合并后 {len(merged)} 条。" + ("（dry-run：未写入 export）" if dry_run else ""))
        print(f"数据目录: {hub_data}")
        if file_errors:
            print(f"解析警告：{len(file_errors)} 个文件失败（可用 --verbose 查看）")
            if len(file_errors) >= MAX_PARSE_ERRORS_RECORDED:
                print(f"  （已达记录上限 {MAX_PARSE_ERRORS_RECORDED}，后续失败未列出。）")
            if verbose:
                for src, path, msg in file_errors[:30]:
                    print(f"  [{src}] {path}\n    {msg}")
                if len(file_errors) > 30:
                    print(f"  … 另有 {len(file_errors) - 30} 条")

    return SyncResult(
        hub_data=hub_data,
        entry_count=len(all_entries),
        merged_count=len(merged),
        sources=per_source_count,
        file_errors=file_errors,
        dry_run=dry_run,
    )
