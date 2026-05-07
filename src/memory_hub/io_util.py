from __future__ import annotations

from pathlib import Path


def read_text_flexible(path: Path) -> str:
    """按 UTF-8 / UTF-8-SIG / 系统首选回退读取，减少各工具 BOM 与历史编码差异导致的乱码。"""
    data = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    try:
        import locale

        preferred = locale.getpreferredencoding(False) or "latin-1"
        return data.decode(preferred, errors="replace")
    except Exception:
        return data.decode("latin-1", errors="replace")
