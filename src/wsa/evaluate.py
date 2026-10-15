"""Execution-based evaluation of the agent on a fixed question set.

Scoring:
- answerable question: correct when the agent did not refuse and its result matches the
  result of the gold SQL (``results_match``);
- trap question (no gold SQL: the data cannot answer it): correct only when the agent refused.

False refusals (refusing an answerable question) are reported separately, so an agent that
refuses everything cannot look good. Each question is appended to a JSONL file as soon as it
finishes; a rerun with the same file skips questions already scored (resumable long runs).
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from wsa.guard import QueryError, run_readonly
from wsa.matching import results_match

GOLD_MAX_ROWS = 10_000


@dataclass(frozen=True)
class EvalQuestion:
    id: str
    category: str  # simple | join | time | trap
    question: str
    gold_sql: str | None


@dataclass
class Report:
    rows: list[dict]

    @property
    def total(self) -> int:
        return len(self.rows)

    @property
    def correct(self) -> int:
        return sum(r["correct"] for r in self.rows)

    @property
    def by_category(self) -> dict[str, tuple[int, int]]:
        acc: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for r in self.rows:
            acc[r["category"]][0] += int(r["correct"])
            acc[r["category"]][1] += 1
        return {k: (v[0], v[1]) for k, v in acc.items()}

    @property
    def _answerable(self) -> list[dict]:
        return [r for r in self.rows if r["category"] != "trap"]

    @property
    def answerable_accuracy(self) -> float:
        rows = self._answerable
        return sum(r["correct"] for r in rows) / len(rows) if rows else 0.0

    @property
    def false_refusals(self) -> int:
        return sum(r["refused"] for r in self._answerable)

    @property
    def trap_refusal_rate(self) -> float:
        traps = [r for r in self.rows if r["category"] == "trap"]
        return sum(r["refused"] for r in traps) / len(traps) if traps else 0.0


def load_questions(path: Path) -> list[EvalQuestion]:
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            q = json.loads(line)
            out.append(EvalQuestion(q["id"], q["category"], q["question"], q.get("gold_sql")))
    return out


def _read_done(out: Path) -> list[dict]:
    """Rows already scored; a half-written last line (the process died) is dropped."""
    if not out.exists():
        return []
    rows = []
    for line in out.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    out.write_text("".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in rows),
                   encoding="utf-8")
    return rows


def score_one(agent, q: EvalQuestion, db_path: Path, explain: bool = False) -> dict:
    start = time.perf_counter()
    answer = agent.ask(q.question, explain=explain)
    seconds = round(time.perf_counter() - start, 2)
    if q.gold_sql is None:
        correct = answer.refused
    elif answer.refused or answer.result is None:
        correct = False
    else:
        gold = run_readonly(db_path, q.gold_sql, max_rows=GOLD_MAX_ROWS)
        correct = results_match(answer.result, gold)
    return {
        "id": q.id,
        "category": q.category,
        "question": q.question,
        "correct": bool(correct),
        "refused": answer.refused,
        "sql": answer.sql,
        "error": answer.error,
        "attempts": answer.attempts,
        "rows": len(answer.result.rows) if answer.result else None,
        "grounded": answer.grounded if explain and answer.result else None,
        "text": answer.text,
        "context_ids": answer.context_ids,
        "seconds": seconds,
    }


def evaluate(agent, questions: list[EvalQuestion], db_path: Path, out: Path,
             explain: bool = False) -> Report:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = _read_done(out)
    done_ids = {r["id"] for r in done}
    for q in questions:
        if q.id in done_ids:
            continue
        try:
            row = score_one(agent, q, Path(db_path), explain=explain)
        except QueryError as exc:  # the gold query itself failed: a bug in the question set
            raise RuntimeError(f"gold SQL of {q.id} failed: {exc}") from exc
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        done.append(row)
    wanted = {q.id for q in questions}
    return Report([r for r in done if r["id"] in wanted])
