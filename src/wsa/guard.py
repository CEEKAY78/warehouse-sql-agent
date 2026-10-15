"""Guardrails for model-written SQL: one read-only query, a row cap, no file access, a timeout.

Defence in depth, each layer independent of the others:

1. ``guard_sql`` parses the text with DuckDB's own parser (no regex blacklist) and accepts
   exactly one statement of type SELECT that starts with SELECT or WITH (PRAGMA is parsed
   as SELECT, so the keyword check matters). It wraps the query in an outer LIMIT.
2. ``run_readonly`` opens the warehouse with ``read_only=True`` and
   ``enable_external_access=False``: no writes, no read_csv/read_parquet of local files, no
   ATTACH, no extension downloads. The setting cannot be re-enabled while the database runs.
3. A timer interrupts queries that run longer than ``timeout_s``.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

DEFAULT_MAX_ROWS = 200
DEFAULT_TIMEOUT_S = 15.0

_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")
_FIRST_WORD = re.compile(r"^(?:\s+|--[^\n]*\n?|/\*.*?\*/|\()*(\w+)", re.S)


class QueryError(Exception):
    """The query could not be run; the message is safe to show to the model for a repair."""


class GuardError(QueryError):
    """The query is not a single read-only SELECT, or it tried to touch files."""


class QueryTimeoutError(QueryError):
    """The query ran longer than the time limit."""


@dataclass
class QueryResult:
    sql: str
    columns: list[str]
    rows: list[tuple] = field(default_factory=list)


def _clean(sql: str) -> str:
    return _FENCE.sub("", sql.strip()).strip().rstrip(";").strip()


def guard_sql(sql: str, max_rows: int = DEFAULT_MAX_ROWS) -> str:
    """Return the query wrapped in a row cap, or raise GuardError."""
    text = _clean(sql)
    if not text:
        raise GuardError("empty query")
    parser = duckdb.connect()
    try:
        statements = parser.extract_statements(text)
    except duckdb.Error as exc:
        raise GuardError(f"SQL does not parse: {exc}") from exc
    finally:
        parser.close()
    if len(statements) != 1:
        raise GuardError(f"expected exactly one statement, got {len(statements)}")
    first = _FIRST_WORD.match(text)
    if (
        statements[0].type != duckdb.StatementType.SELECT
        or first is None
        or first.group(1).upper() not in {"SELECT", "WITH"}
    ):
        raise GuardError("only a single SELECT (or WITH ... SELECT) query is allowed")
    return f"SELECT * FROM ({text}) AS q LIMIT {int(max_rows)}"


def run_readonly(
    db_path: Path | str,
    sql: str,
    max_rows: int = DEFAULT_MAX_ROWS,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> QueryResult:
    """Guard the query, then run it on a read-only connection without file access."""
    capped = guard_sql(sql, max_rows=max_rows)
    con = duckdb.connect(
        str(db_path), read_only=True, config={"enable_external_access": False}
    )
    timed_out = threading.Event()

    def interrupt() -> None:
        timed_out.set()
        con.interrupt()

    timer = threading.Timer(timeout_s, interrupt)
    timer.start()
    try:
        cursor = con.execute(capped)
        columns = [d[0] for d in cursor.description]
        rows = cursor.fetchall()
    except duckdb.PermissionException as exc:
        raise GuardError(f"access denied: {exc}") from exc
    except duckdb.Error as exc:
        if timed_out.is_set():
            raise QueryTimeoutError(f"query exceeded {timeout_s:g} s") from exc
        raise QueryError(str(exc)) from exc
    finally:
        timer.cancel()
        con.close()
    return QueryResult(sql=_clean(sql), columns=columns, rows=rows)
