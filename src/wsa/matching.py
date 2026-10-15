"""Execution-based comparison of the agent's result with the gold result.

Policy (documented in the README):

- row order is ignored (rows are compared as a multiset);
- column names are ignored; the answer may return *extra* columns (e.g. the product name next
  to the gold value), but every gold column must be matched by one answer column;
- numbers are compared after rounding to 2 decimals (Decimal and int are treated as float);
- text is compared case- and whitespace-insensitively, dates as ISO strings.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from itertools import permutations

from wsa.guard import QueryResult

MAX_ANSWER_COLUMNS = 8


def _norm(cell: object) -> object:
    if cell is None or isinstance(cell, bool):
        return cell
    if isinstance(cell, int | float | Decimal):
        return round(float(cell), 2) + 0.0
    if isinstance(cell, datetime | date):
        return cell.isoformat()
    return " ".join(str(cell).split()).lower()


def _bag(rows: list[tuple], columns: tuple[int, ...]) -> Counter:
    return Counter(tuple(_norm(row[i]) for i in columns) for row in rows)


def results_match(got: QueryResult, gold: QueryResult) -> bool:
    k = len(gold.columns)
    n = len(got.columns)
    if len(got.rows) != len(gold.rows) or n < k or n > MAX_ANSWER_COLUMNS:
        return False
    target = _bag(gold.rows, tuple(range(k)))
    return any(_bag(got.rows, cols) == target for cols in permutations(range(n), k))
