"""Turn eval/runs/*.jsonl into eval/results.md (the table quoted in the README).

    python scripts/summarize_runs.py
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "eval" / "runs"  # or pass another folder as argv[1]
CATEGORIES = ["simple", "join", "time", "trap"]


def load(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]


def row_for(name: str, rows: list[dict]) -> str:
    def cat(c: str) -> str:
        sub = [r for r in rows if r["category"] == c]
        return f"{sum(r['correct'] for r in sub)}/{len(sub)}"

    answerable = [r for r in rows if r["category"] != "trap"]
    false_ref = sum(r["refused"] for r in answerable)
    repaired = sum(1 for r in rows if r["attempts"] == 2)
    median_s = statistics.median(r["seconds"] for r in rows)
    model, _, rag = name.rpartition("_")
    return (f"| {model.replace('_', ':', 1)} | {'yes' if rag == 'rag' else 'no'} | "
            f"**{sum(r['correct'] for r in rows)}/{len(rows)}** | "
            + " | ".join(cat(c) for c in CATEGORIES)
            + f" | {false_ref} | {repaired} | {median_s:.1f} |")


def main() -> None:
    runs = Path(sys.argv[1]) if len(sys.argv) > 1 else RUNS
    grid =sorted(p for p in runs.glob("*.jsonl") if not p.stem.endswith("_explain"))
    lines = [
        "| model | RAG | correct | simple | join | time | trap (refused) | false refusals "
        "| 2nd attempts | median s/question |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    lines += [row_for(p.stem, load(p)) for p in grid]
    for p in sorted(runs.glob("*_explain.jsonl")):
        rows = load(p)
        explained = [r for r in rows if r["grounded"] is not None]
        grounded = sum(r["grounded"] for r in explained)
        lines += [
            "",
            f"Explanation run `{p.stem}`: {sum(r['correct'] for r in rows)}/{len(rows)} correct; "
            f"{grounded}/{len(explained)} prose answers passed the number check, "
            f"{len(explained) - grounded} fell back to the result table; median "
            f"{statistics.median(r['seconds'] for r in rows):.1f} s/question.",
        ]
    out = runs / "results.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
