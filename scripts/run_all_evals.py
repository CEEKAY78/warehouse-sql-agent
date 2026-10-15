"""Run the full evaluation grid (3 models x RAG on/off), then one --explain run of the best.

    python scripts/run_all_evals.py

Resumable: every question is appended to eval/runs/<model>_<rag|norag>.jsonl as soon as it is
scored, and a rerun skips what is already there.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wsa.cli import main, run_slug  # noqa: E402

MODELS = ["qwen2.5-coder:7b", "qwen2.5:7b-instruct", "qwen3:8b"]
RUNS = ROOT / "eval" / "runs"


def accuracy(path: Path) -> float:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return sum(r["correct"] for r in rows) / len(rows) if rows else 0.0


def run(argv: list[str]) -> None:
    start = time.perf_counter()
    print(f"\n=== {' '.join(argv)} ({time.strftime('%H:%M:%S')})", flush=True)
    main(argv)
    print(f"=== done in {time.perf_counter() - start:.0f} s", flush=True)


def main_all() -> None:
    RUNS.mkdir(parents=True, exist_ok=True)
    for model in MODELS:
        for rag in (True, False):
            run(["eval", "--model", model] + ([] if rag else ["--no-rag"]))
    scored = {(m, r): accuracy(RUNS / f"{run_slug(m, r)}.jsonl")
              for m in MODELS for r in (True, False)}
    (model, rag), best = max(scored.items(), key=lambda kv: kv[1])
    print(f"\nbest: {model} rag={rag} accuracy {best:.0%}", flush=True)
    out = RUNS / f"{run_slug(model, rag)}_explain.jsonl"
    run(["eval", "--model", model, "--explain", "--out", str(out)]
        + ([] if rag else ["--no-rag"]))


if __name__ == "__main__":
    main_all()
