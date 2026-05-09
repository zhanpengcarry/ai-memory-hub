from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path


def load_yaml_config(path: Path) -> dict:
    import yaml

    try:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise SystemExit(f"配置文件 YAML 语法无效: {path}\n{e}") from e
    except OSError as e:
        raise SystemExit(f"无法读取配置文件: {path}\n{e}") from e
    return data or {}


def write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """先写入临时文件再 replace，降低同步中断导致半成品文件的风险。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as f:
            f.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise
