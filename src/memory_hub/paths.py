from __future__ import annotations

import glob
import os
import re
from pathlib import Path


def expand_path_str(s: str) -> str:
    """展开路径占位符，提高跨平台与多工具文档惯例的兼容性。

    支持：`${VAR}`、`%VAR%`（Windows 常见）、`~/` 用户目录、正斜杠（规范化后适配 OS）。
    """

    def pct_repl(m: re.Match[str]) -> str:
        key = m.group(1)
        return os.environ.get(key, m.group(0))

    def brace_repl(m: re.Match[str]) -> str:
        key = m.group(1)
        return os.environ.get(key, m.group(0))

    out = re.sub(r"%([^%]+)%", pct_repl, s)
    out = re.sub(r"\$\{([^}]+)\}", brace_repl, out)
    out = out.strip()
    if out == "~" or out.startswith("~/") or out.startswith("~\\"):
        out = os.path.expanduser(out.replace("\\", "/").replace("/", os.sep))
    out = out.replace("/", os.sep)
    return os.path.normpath(out)


def resolve_relative(p: str, hub_root: Path) -> Path:
    path = Path(expand_path_str(p))
    if path.is_absolute():
        return path
    return (hub_root / path).resolve()


def path_excluded(path: Path, patterns: list[str]) -> bool:
    """排除规则：`pathlib.Path.match`（支持 `**`）优先，其次对文件名做 `fnmatch`。"""
    from fnmatch import fnmatch

    for pat in patterns:
        pat = pat.strip().replace("\\", "/")
        if not pat:
            continue
        try:
            if path.match(pat):
                return True
        except (ValueError, OSError):
            pass
        posix_name = path.name
        if "/" not in pat and ("*" in pat or "?" in pat or "[" in pat):
            if fnmatch(posix_name, pat):
                return True
    return False


def collect_paths_for_block(
    block: dict,
    hub_root: Path,
    *,
    extra_exclude: list[str] | None = None,
) -> list[Path]:
    """汇总 glob、显式文件、目录扫描三类来源，去重排序。"""
    exclude = list(block.get("exclude_globs") or [])
    if extra_exclude:
        exclude.extend(extra_exclude)

    seen: set[Path] = set()
    out: list[Path] = []

    def add(p: Path) -> None:
        try:
            r = p.resolve()
        except OSError:
            return
        if r in seen:
            return
        if not r.is_file():
            return
        if exclude and path_excluded(r, exclude):
            return
        seen.add(r)
        out.append(r)

    globs = list(block.get("glob_paths") or [])
    for raw in globs:
        p = expand_path_str(raw.strip())
        path_try = Path(p)
        if not path_try.is_absolute():
            p = str((hub_root / p).resolve())
        try:
            hits = glob.glob(p, recursive=True)
        except (OSError, ValueError):
            continue
        for hit in hits:
            add(Path(hit))

    for f in block.get("files") or []:
        add(resolve_relative(str(f), hub_root))

    default_exts = [".md", ".mdc", ".txt", ".markdown", ".json"]

    for item in block.get("scan_dirs") or []:
        if not isinstance(item, dict):
            continue
        root = resolve_relative(str(item.get("path", "")), hub_root)
        if not root.is_dir():
            continue
        recursive = item.get("recursive", True)
        exts = item.get("extensions")
        if exts is None:
            want = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in default_exts}
        elif exts == []:
            want = set()
        else:
            want = {e.lower() if str(e).startswith(".") else f".{str(e).lower()}" for e in exts}

        it = root.rglob("*") if recursive else root.iterdir()
        for f in it:
            if not f.is_file():
                continue
            if want and f.suffix.lower() not in want:
                continue
            if exclude and path_excluded(f.resolve(), exclude):
                continue
            add(f)

    out.sort(key=lambda x: str(x).lower())
    return out
