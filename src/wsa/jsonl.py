"""JSON Lines helpers shared by the question set, the few-shot examples and the run logs."""

from __future__ import annotations

import json
from pathlib import Path


def read_jsonl(path: Path | str, skip_broken: bool = False) -> list[dict]:
    """One object per non-empty line; ``skip_broken`` drops lines that do not parse
    (a run log whose last line was cut off when the process died)."""
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            if not skip_broken:
                raise
    return rows
