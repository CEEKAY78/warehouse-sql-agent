"""Check that every number in the model's prose answer comes from the query result.

A number in the answer is *grounded* when it equals, within the precision it is written with,
a value that is available to the model:

- a numeric cell of the result (also as a percentage: 0.2513 -> "25.1%");
- a number inside a text or date cell (years, months, codes such as "2011-12");
- a number in the user's question ("top 5", "in 2011").

List numbering at the start of a line ("1.", "2)") is ignored; any other small integer must
be grounded like every other number.

Precision follows what is written: "1.2M" accepts anything within 1.15M-1.25M, "1,235" within
1234.5-1235.5. Anything else is reported back as ungrounded, so the agent can be asked to
rewrite the answer instead of showing an invented figure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from wsa.guard import QueryResult

_NUMBER = re.compile(
    r"(?<![\w.])(?P<int>\d{1,3}(?:,\d{3})+|\d+)(?:\.(?P<frac>\d+))?"
    r"(?P<suffix>%|k|K|M|bn| million| thousand| billion)?(?!\w)"
)
_MULTIPLIER = {"k": 1e3, "K": 1e3, "M": 1e6, "bn": 1e9, " thousand": 1e3, " million": 1e6,
               " billion": 1e9}
_LIST_MARKER = re.compile(r"^\s*\d+[.)](?=\s)", re.M)


@dataclass(frozen=True)
class WrittenNumber:
    text: str
    value: float
    tolerance: float
    is_percent: bool


def extract_numbers(text: str) -> list[WrittenNumber]:
    found = []
    for m in _NUMBER.finditer(text):
        frac = m.group("frac") or ""
        suffix = m.group("suffix") or ""
        base = float(m.group("int").replace(",", "") + ("." + frac if frac else ""))
        mult = _MULTIPLIER.get(suffix, 1.0)
        found.append(
            WrittenNumber(
                text=m.group(0),
                value=base * mult,
                tolerance=0.5 * 10 ** -len(frac) * mult + 1e-9,
                is_percent=suffix == "%",
            )
        )
    return found


def _cell_numbers(cell: object) -> list[float]:
    if cell is None or isinstance(cell, bool):
        return []
    if isinstance(cell, int | float | Decimal):
        return [abs(float(cell))]
    if isinstance(cell, datetime | date):
        return [float(cell.year), float(cell.month), float(cell.day)]
    return [n.value for n in extract_numbers(str(cell))]


def available_numbers(result: QueryResult, question: str = "") -> list[float]:
    values = [v for row in result.rows for cell in row for v in _cell_numbers(cell)]
    values += [n.value for n in extract_numbers(question)]
    return values


def _grounded(number: WrittenNumber, values: list[float]) -> bool:
    for v in values:
        if abs(number.value - v) <= number.tolerance:
            return True
        if number.is_percent and abs(number.value - v * 100) <= number.tolerance:
            return True
    return False


def check_numbers(answer: str, result: QueryResult, question: str = "") -> list[str]:
    """Return the numbers written in ``answer`` that are not supported by the result."""
    values = available_numbers(result, question)
    prose = _LIST_MARKER.sub("", answer)  # "1." / "2)" list numbering is not a claim
    return [n.text for n in extract_numbers(prose) if not _grounded(n, values)]
