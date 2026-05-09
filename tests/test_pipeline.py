"""需已安装 PyYAML；使用临时目录与最小配置跑通 pipeline。"""

import json
import textwrap
from pathlib import Path

from memory_hub.pipeline import run_sync


def test_run_sync_minimal_config(tmp_path: Path):
    sample = tmp_path / "in.md"
    sample.write_text("---\ntitle: T\ntags: [a]\n---\n\n" + "x" * 30 + "\n", encoding="utf-8")

    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        textwrap.dedent(
            f"""
            hub_data_dir: ./hub
            defaults:
              min_body_chars: 5
            claude:
              enabled: true
              files:
                - "{sample.as_posix().replace(chr(92), "/")}"
            codex:
              enabled: false
            opencode:
              enabled: false
            openclaw:
              enabled: false
            export:
              for_claude: ./hub/ex/claude
            """
        ).strip(),
        encoding="utf-8",
    )

    r = run_sync(cfg, dry_run=False, verbose=False, quiet=True)
    assert r.entry_count >= 1
    assert r.merged_count >= 1
    merged = json.loads((tmp_path / "hub" / "merged.json").read_text(encoding="utf-8"))
    assert isinstance(merged, list)
    assert len(merged) >= 1
