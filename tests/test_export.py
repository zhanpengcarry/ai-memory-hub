from pathlib import Path

import tempfile

from memory_hub.export_targets import export_all


def test_export_writes_files_for_empty_merged():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        export_all([], {"for_claude": root / "c", "for_opencode": root / "o"})
        assert (root / "c" / "SHARED_CONTEXT.md").is_file()
        text = (root / "c" / "SHARED_CONTEXT.md").read_text(encoding="utf-8")
        assert "尚无合并条目" in text or "Hub" in text
