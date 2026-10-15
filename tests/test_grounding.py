from datetime import date
from decimal import Decimal

from wsa.grounding import check_numbers, extract_numbers
from wsa.guard import QueryResult


def result(columns, rows):
    return QueryResult(sql="SELECT ...", columns=columns, rows=rows)


def test_extracts_currency_thousands_percent_and_suffixes():
    found = [n.text for n in extract_numbers("Revenue was £1,234.56 (up 12.5%), about 1.2M or 3k")]
    assert found == ["1,234.56", "12.5%", "1.2M", "3k"]


def test_numbers_copied_from_the_result_are_grounded():
    res = result(["country", "revenue"], [("France", Decimal("1234.56")), ("Spain", 98.0)])
    assert check_numbers("France sold £1,234.56 and Spain £98.", res) == []


def test_invented_number_is_reported():
    res = result(["revenue"], [(1234.56,)])
    assert check_numbers("Revenue was £1,234.56, from 4,000 orders.", res) == ["4,000"]


def test_rounded_and_abbreviated_forms_are_grounded():
    res = result(["revenue", "share"], [(1234567.0, 0.2513)])
    text = "About £1.2M, roughly £1,234,567 in total, a 25.1% share (0.25)."
    assert check_numbers(text, res) == []


def test_rounding_tolerance_follows_the_displayed_precision():
    res = result(["revenue"], [(1234567.0,)])
    assert check_numbers("About £1.3M.", res) == ["1.3M"]


def test_spelled_out_magnitudes_are_read():
    found = [(n.text, n.value) for n in extract_numbers("about 1.2 million and 3 thousand")]
    assert found == [("1.2 million", 1.2e6), ("3 thousand", 3e3)]


def test_small_integers_are_only_free_as_list_markers():
    res = result(["product", "qty"], [("A", 900), ("B", 800)])
    assert check_numbers("1. A: 900\n2) B: 800", res) == []
    assert check_numbers("A sold 900 units to 2 shops.", res) == ["2"]


def test_numbers_from_the_question_and_rank_positions_are_allowed():
    res = result(["product", "qty"], [("A", 900), ("B", 800), ("C", 700)])
    text = "Top 3 products in 2011:\n1. A: 900\n2. B: 800\n3. C: 700"
    assert check_numbers(text, res, question="What were the top 3 products in 2011?") == []


def test_numbers_inside_dates_and_labels_are_grounded():
    res = result(["month", "orders"], [(date(2011, 11, 1), 1024), ("2011-12", 512)])
    assert check_numbers("In November 2011 there were 1,024 orders, in 2011-12 only 512.",
                         res) == []
