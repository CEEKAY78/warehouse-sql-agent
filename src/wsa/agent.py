"""Text-to-SQL agent: plan a query (or refuse), run it under the guard, explain the result.

One question is at most four model calls:

1. plan  -> JSON {sql, refuse, reason} (structured output, so refusals are not guessed from prose)
2. repair (only if the query failed) -> the same JSON, with the database error shown
3. explain -> a short answer that may only use numbers from the result
4. rewrite (only if step 3 used an ungrounded number); if it is still ungrounded, the prose is
   dropped and the result table is shown instead.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from wsa.grounding import check_numbers
from wsa.guard import QueryError, QueryResult, run_readonly
from wsa.retriever import Doc, Retriever
from wsa.schema import describe_schema

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "sql": {"type": ["string", "null"]},
        "refuse": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["sql", "refuse", "reason"],
}

PLAN_RULES = """You are a data analyst. Answer business questions by writing ONE DuckDB SQL
query over the star schema below.

Rules:
- Use only the tables and columns listed. Join dimensions on their *_key columns.
- Net revenue = sum(line_amount) over all lines, cancellations included, unless the question
  says otherwise. An order is one invoice_no.
- Keep the result small: aggregate, and use ORDER BY ... LIMIT for rankings.
- If the data cannot answer the question (the field does not exist, e.g. costs, margin,
  profit, stock levels, marketing, customer age; or the period is outside the data), do NOT
  guess: set refuse=true, sql=null and explain why in reason.
- Reply with JSON only: {"sql": "...", "refuse": false, "reason": "..."}"""

EXPLAIN_RULES = """Answer the question in 1-3 sentences in plain English for a business user.
Use ONLY numbers that appear in the query result or in the question; you may round them.
Amounts are in GBP (£). Do not mention SQL."""

MAX_RESULT_ROWS_IN_PROMPT = 30


class ChatClient(Protocol):
    def chat(self, messages: list[dict], schema: dict | None = None) -> str: ...


@dataclass
class Answer:
    question: str
    sql: str | None = None
    result: QueryResult | None = None
    text: str = ""
    refused: bool = False
    error: str | None = None
    attempts: int = 0
    grounded: bool = True
    ungrounded: list[str] = field(default_factory=list)
    context_ids: list[str] = field(default_factory=list)


def _context_block(docs: list[Doc]) -> str:
    glossary = [f"- {d.title}: {d.text}" for d in docs if d.kind == "glossary"]
    examples = [d.text for d in docs if d.kind == "example"]
    parts = []
    if glossary:
        parts.append("Business definitions:\n" + "\n".join(glossary))
    if examples:
        parts.append("Similar solved questions:\n" + "\n\n".join(examples))
    return "\n\n".join(parts)


def result_table(result: QueryResult, max_rows: int = MAX_RESULT_ROWS_IN_PROMPT) -> str:
    def cell(v: object) -> str:
        return f"{v:.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)

    lines = [" | ".join(result.columns), " | ".join("---" for _ in result.columns)]
    lines += [" | ".join(cell(v) for v in row) for row in result.rows[:max_rows]]
    if len(result.rows) > max_rows:
        lines.append(f"... ({len(result.rows)} rows in total)")
    return "\n".join(lines)


def _parse_plan(text: str) -> dict:
    try:
        plan = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        plan = json.loads(text[start : end + 1]) if start >= 0 < end else {}
    return {
        "sql": plan.get("sql") or None,
        "refuse": bool(plan.get("refuse", False)),
        "reason": str(plan.get("reason") or ""),
    }


class Agent:
    def __init__(
        self,
        db_path: Path | str,
        llm: ChatClient,
        retriever: Retriever | None = None,
        k_glossary: int = 3,
        k_examples: int = 3,
    ):
        self.db_path = Path(db_path)
        self.llm = llm
        self.retriever = retriever
        self.k_glossary = k_glossary
        self.k_examples = k_examples
        self.schema = describe_schema(self.db_path)

    def _retrieve(self, question: str) -> list[Doc]:
        if self.retriever is None:
            return []
        return self.retriever.search(question, self.k_glossary, "glossary") + (
            self.retriever.search(question, self.k_examples, "example")
        )

    def ask(self, question: str, explain: bool = True) -> Answer:
        answer = Answer(question=question)
        docs = self._retrieve(question)
        answer.context_ids = [d.id for d in docs]
        system = PLAN_RULES + "\n\nSCHEMA:\n" + self.schema
        context = _context_block(docs)
        if context:
            system += "\n\n" + context
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": question}]

        for attempt in (1, 2):
            answer.attempts = attempt
            reply = self.llm.chat(messages, schema=PLAN_SCHEMA)
            plan = _parse_plan(reply)
            if plan["refuse"] or not plan["sql"]:
                answer.refused = True
                answer.sql = None
                answer.text = plan["reason"] or "The data cannot answer this question."
                return answer
            answer.sql = plan["sql"]
            try:
                answer.result = run_readonly(self.db_path, plan["sql"])
                answer.error = None
                break
            except QueryError as exc:
                answer.error = str(exc)
                messages += [
                    {"role": "assistant", "content": reply},
                    {"role": "user", "content": f"The query failed: {exc}\nFix it and reply "
                                                "with the same JSON format."},
                ]
        if answer.result is None or not explain:
            return answer
        self._explain(answer)
        return answer

    def _explain(self, answer: Answer) -> None:
        assert answer.result is not None
        table = result_table(answer.result)
        messages = [
            {"role": "system", "content": EXPLAIN_RULES},
            {"role": "user", "content": f"Question: {answer.question}\n\nQuery result:\n{table}"},
        ]
        text = self.llm.chat(messages).strip()
        bad = check_numbers(text, answer.result, answer.question)
        if bad:
            messages += [
                {"role": "assistant", "content": text},
                {"role": "user", "content": f"These numbers are not in the result: "
                                            f"{', '.join(bad)}. Rewrite the answer using only "
                                            "numbers from the result."},
            ]
            text = self.llm.chat(messages).strip()
            bad = check_numbers(text, answer.result, answer.question)
        if bad:
            answer.grounded = False
            answer.ungrounded = bad
            answer.text = "The model's explanation was rejected (numbers not in the result). " \
                          "Query result:\n\n" + table
        else:
            answer.text = text
