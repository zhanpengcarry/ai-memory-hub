from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

from memory_hub import __version__
from memory_hub.fingerprint import sources_fingerprint
from memory_hub.paths import collect_paths_for_block
from memory_hub.pipeline import run_sync
from memory_hub.sources import iter_source_blocks
from memory_hub.util import load_yaml_config


def positive_interval(s: str) -> float:
    v = float(s)
    if v <= 0 or v > 86400:
        raise argparse.ArgumentTypeError("interval 须在 (0, 86400] 秒内（建议 1～300）")
    return v


def cmd_discover(config_path: Path) -> None:
    cfg = load_yaml_config(config_path)
    hub_root = config_path.parent.resolve()
    defaults = cfg.get("defaults") or {}
    for name, block in iter_source_blocks(cfg):
        if not block.get("enabled", True):
            print(f"[{name}] 已禁用")
            continue
        paths = collect_paths_for_block(block, hub_root, extra_exclude=list(defaults.get("exclude_globs") or []))
        print(f"[{name}] 匹配 {len(paths)} 个文件")
        for p in paths[:50]:
            print(f"  {p}")
        if len(paths) > 50:
            print(f"  … 另有 {len(paths) - 50} 个文件未列出")


def cmd_doctor(config_path: Path) -> int:
    cfg = load_yaml_config(config_path)
    hub_root = config_path.parent.resolve()
    defaults = cfg.get("defaults") or {}
    ex = list(defaults.get("exclude_globs") or [])
    code = 0
    enabled_any = False
    total_files = 0
    for name, block in iter_source_blocks(cfg):
        if not block.get("enabled", True):
            print(f"[{name}] 已禁用")
            continue
        enabled_any = True
        paths = collect_paths_for_block(block, hub_root, extra_exclude=ex)
        n = len(paths)
        total_files += n
        print(f"[{name}] {n} 个文件")
        if n == 0:
            print("  ! 未匹配任何文件，请检查 glob_paths / scan_dirs / files")
            code = 1
    if not enabled_any:
        print("! 没有启用的源，请在 config.yaml 中开启至少一端")
        return 1
    if total_files == 0:
        print("! 合计 0 个源文件，无法汇聚")
        return 1
    print(f"合计 {total_files} 个源文件（仅计数，未解析内容）。配置可正常发现路径。")
    return code


def cmd_init(target_dir: Path, force: bool) -> None:
    dest = (target_dir / "config.yaml").resolve()
    if dest.exists() and not force:
        raise SystemExit(f"已存在 {dest}，使用 --force 覆盖")

    try:
        tpl = resources.files("memory_hub.data").joinpath("config.example.yaml")
        with tpl.open("rb") as f:
            raw = f.read()
    except (FileNotFoundError, OSError, TypeError):
        # 开发时直接从仓库根复制
        repo_example = Path(__file__).resolve().parent.parent.parent / "config.example.yaml"
        if repo_example.is_file():
            raw = repo_example.read_bytes()
        else:
            raise SystemExit("找不到打包内的 config.example.yaml，请从 GitHub/仓库手动复制。")

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    print(f"已写入 {dest}")


def cmd_watch(config_path: Path, *, interval: float, dry_run: bool, verbose: bool) -> None:
    print(f"[watch] 轮询间隔 {interval}s，按 Ctrl+C 退出")
    def tick(msg: str) -> None:
        r = run_sync(config_path, dry_run=dry_run, verbose=verbose, quiet=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        warn = f"（{len(r.file_errors)} 个文件解析失败）" if r.file_errors else ""
        print(f"[watch] {ts} {msg} 原始 {r.entry_count} 条 → 合并 {r.merged_count}{warn}")

    tick("启动同步")
    last_fp = sources_fingerprint(config_path)

    try:
        while True:
            time.sleep(interval)
            cur = sources_fingerprint(config_path)
            if cur != last_fp:
                last_fp = cur
                tick("检测到变更")
    except KeyboardInterrupt:
        print("[watch] 已停止")


def resolve_config_path(p: Path) -> Path:
    if not p.is_file():
        raise SystemExit(f"未找到配置文件: {p}（使用 `memory-hub init` 生成）")
    return p.resolve()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI 多端记忆汇聚（ai-memory-hub）。命令：sync / discover / doctor / init / watch",
        prog="memory-hub",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    def add_config_arg(ap: argparse.ArgumentParser) -> None:
        ap.add_argument(
            "-c",
            "--config",
            type=Path,
            default=Path("config.yaml"),
            help="配置文件路径（默认当前目录 config.yaml）",
        )

    p_sync = sub.add_parser("sync", help="拉取各源、合并并导出到 hub_data / export")
    add_config_arg(p_sync)
    p_sync.add_argument("--dry-run", action="store_true", help="只写 hub_data，不写各端 export")
    p_sync.add_argument("-v", "--verbose", action="store_true", help="打印每源条数与解析失败详情")

    p_dis = sub.add_parser("discover", help="列出配置匹配到的文件（不解析内容）")
    add_config_arg(p_dis)

    p_doc = sub.add_parser("doctor", help="检查配置能否发现源文件（CI / 排障）")
    add_config_arg(p_doc)

    p_init = sub.add_parser("init", help="在当前目录生成 config.yaml 模板")
    p_init.add_argument(
        "--dir",
        type=Path,
        default=Path("."),
        help="目标目录（默认当前目录）",
    )
    p_init.add_argument("--force", action="store_true", help="覆盖已有 config.yaml")

    p_watch = sub.add_parser("watch", help="轮询源文件变化并自动 sync")
    add_config_arg(p_watch)
    p_watch.add_argument("--dry-run", action="store_true")
    p_watch.add_argument("-v", "--verbose", action="store_true")
    p_watch.add_argument(
        "-i",
        "--interval",
        type=positive_interval,
        default=3.0,
        help="轮询间隔秒数（默认 3，须为正数且不超过 86400）",
    )

    args = parser.parse_args()

    if args.command == "init":
        cmd_init(Path(args.dir), force=args.force)
        return

    cfg_path = resolve_config_path(args.config)

    if args.command == "sync":
        run_sync(cfg_path, dry_run=args.dry_run, verbose=args.verbose)
    elif args.command == "discover":
        cmd_discover(cfg_path)
    elif args.command == "doctor":
        sys.exit(cmd_doctor(cfg_path))
    elif args.command == "watch":
        cmd_watch(cfg_path, interval=args.interval, dry_run=args.dry_run, verbose=args.verbose)


if __name__ == "__main__":
    main()
