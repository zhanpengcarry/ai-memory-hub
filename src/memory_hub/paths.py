from __future__ import annotations

import glob
import os
import re
from fnmatch import fnmatch
from pathlib import Path

# Pattern for %VAR% environment variables (Windows style)
_PCT_VAR_RE = re.compile(r"%([^%]+)%")

# Pattern for ${VAR} environment variables (Unix style)
_BRACE_VAR_RE = re.compile(r"\$\{([^}]+)\}")

# Default file extensions for directory scanning
DEFAULT_SCAN_EXTENSIONS = [".md", ".mdc", ".txt", ".markdown", ".json"]


def expand_path_str(s: str) -> str:
    """Expand path placeholders for cross-platform compatibility.

    Supports:
    - ${VAR}: Unix-style environment variables
    - %VAR%: Windows-style environment variables
    - ~/: User home directory

    Args:
        s: Path string with potential placeholders

    Returns:
        Expanded and normalized path string
    """

    def _env_repl(m: re.Match[str]) -> str:
        key = m.group(1)
        return os.environ.get(key, m.group(0))

    out = _PCT_VAR_RE.sub(_env_repl, s)
    out = _BRACE_VAR_RE.sub(_env_repl, out)
    out = out.strip()

    if out == "~" or out.startswith("~/") or out.startswith("~\\"):
        out = os.path.expanduser(out.replace("\\", "/").replace("/", os.sep))

    out = out.replace("/", os.sep)
    return os.path.normpath(out)


def resolve_relative(p: str, hub_root: Path) -> Path:
    """Resolve path relative to hub_root if not absolute.

    Args:
        p: Path string (may contain placeholders)
        hub_root: Root directory for relative path resolution

    Returns:
        Resolved absolute Path
    """
    path = Path(expand_path_str(p))
    if path.is_absolute():
        return path
    return (hub_root / path).resolve()


def path_excluded(path: Path, patterns: list[str]) -> bool:
    """Check if path matches any exclusion pattern.

    Uses pathlib.Path.match (supports **) first, then fnmatch for filename.

    Args:
        path: Path to check
        patterns: List of glob patterns to match against

    Returns:
        True if path should be excluded
    """
    for pat in patterns:
        pat = pat.strip().replace("\\", "/")
        if not pat:
            continue
        try:
            if path.match(pat):
                return True
        except (ValueError, OSError):
            pass
        # Fallback to fnmatch for simple filename patterns
        if "/" not in pat and ("*" in pat or "?" in pat or "[" in pat) and fnmatch(path.name, pat):
            return True
    return False


def _normalize_extension(ext: str) -> str:
    """Normalize file extension to lowercase with leading dot.

    Args:
        ext: Extension string (with or without leading dot)

    Returns:
        Normalized extension with leading dot
    """
    ext = ext.lower()
    return ext if ext.startswith(".") else f".{ext}"


def collect_paths_for_block(
    block: dict,
    hub_root: Path,
    *,
    extra_exclude: list[str] | None = None,
) -> list[Path]:
    """Collect file paths from glob, explicit files, and directory scan sources.

    Results are deduplicated and sorted.

    Args:
        block: Source configuration block
        hub_root: Root directory for path resolution
        extra_exclude: Additional exclusion patterns from defaults

    Returns:
        Sorted list of unique resolved file paths
    """
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

    # Process glob patterns
    for raw in block.get("glob_paths") or []:
        p = expand_path_str(raw.strip())
        if not Path(p).is_absolute():
            p = str((hub_root / p).resolve())
        try:
            hits = glob.glob(p, recursive=True)
        except (OSError, ValueError):
            continue
        for hit in hits:
            add(Path(hit))

    # Process explicit files
    for f in block.get("files") or []:
        add(resolve_relative(str(f), hub_root))

    # Process directory scans
    for item in block.get("scan_dirs") or []:
        if not isinstance(item, dict):
            continue
        root = resolve_relative(str(item.get("path", "")), hub_root)
        if not root.is_dir():
            continue

        recursive = item.get("recursive", True)
        exts = item.get("extensions")

        if exts is None:
            want = {_normalize_extension(e) for e in DEFAULT_SCAN_EXTENSIONS}
        elif exts == []:
            want = set()
        else:
            want = {_normalize_extension(str(e)) for e in exts}

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
