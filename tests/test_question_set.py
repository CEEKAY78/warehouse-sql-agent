"""Checks of the shipped question set and knowledge base (gold SQL runs on the real warehouse)."""

import json
import re
from collections import Counter
from pathlib import Path

import pytest

from wsa.evaluate import GOLD_MAX_ROWS, load_questions
from wsa.guard import run_readonly
from wsa.retriever import load_examples, load_glossary

ROOT = Path(__file__).resolve().parents[1]
WAREHOUSE = ROOT / "data" / "warehouse.duckdb"
QUESTIONS = load_questions(ROOT / "eval" / "questions.jsonl")
EXAMPLES = [json.loads(line) for line in
            (ROOT / "knowledge" / "examples.jsonl").read_text(encoding="utf-8").splitlines()]

needs_warehouse = pytest.mark.skipif(not WAREHOUSE.exists(),
                                     reason="run scripts/build_warehouse.py first")


def norm(text):
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def test_forty_questions_ten_per_category_with_unique_ids():
    assert len(QUESTIONS) == 40
    assert len({q.id for q in QUESTIONS}) == 40
    assert Counter(q.category for q in QUESTIONS) == {"simple": 10, "join": 10, "time": 10,
                                                      "trap": 10}
    assert all((q.gold_sql is None) == (q.category == "trap") for q in QUESTIONS)


def test_few_shot_examples_do_not_leak_eval_questions():
    asked = {norm(q.question) for q in QUESTIONS}
    assert not asked & {norm(e["question"]) for e in EXAMPLES}
    gold = {norm(q.gold_sql) for q in QUESTIONS if q.gold_sql}
    assert not gold & {norm(e["sql"]) for e in EXAMPLES}


def template(text):
    """Text with literals blanked: the same question with another year or window is a leak."""
    text = re.sub(r"'[^']*'", "'?'", text.lower())
    text = re.sub(r"\b\d+\b", "0", text)
    return norm(text)


def test_few_shot_examples_are_not_the_eval_questions_with_other_literals():
    asked = {template(q.question) for q in QUESTIONS}
    gold = {template(q.gold_sql) for q in QUESTIONS if q.gold_sql}
    leaks = [e["id"] for e in EXAMPLES
             if template(e["question"]) in asked or template(e["sql"]) in gold]
    assert leaks == []


def test_knowledge_files_load():
    assert len(load_glossary(ROOT / "knowledge" / "glossary.md")) >= 10
    assert len(load_examples(ROOT / "knowledge" / "examples.jsonl")) == len(EXAMPLES)


@needs_warehouse
@pytest.mark.parametrize("q", [q for q in QUESTIONS if q.gold_sql], ids=lambda q: q.id)
def test_gold_sql_runs_and_returns_a_small_result(q):
    result = run_readonly(WAREHOUSE, q.gold_sql, max_rows=GOLD_MAX_ROWS)
    assert 1 <= len(result.rows) <= 10
    assert all(v is not None for row in result.rows for v in row)


@needs_warehouse
@pytest.mark.parametrize("ex", [e for e in EXAMPLES if not e["sql"].startswith("REFUSE")],
                         ids=lambda e: e["id"])
def test_few_shot_example_sql_runs(ex):
    assert run_readonly(WAREHOUSE, ex["sql"]).rows
