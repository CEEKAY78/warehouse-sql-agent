from decimal import Decimal

from wsa.guard import QueryResult
from wsa.matching import results_match


def result(columns, rows):
    return QueryResult(sql="SELECT ...", columns=columns, rows=rows)


def test_same_rows_in_another_order_and_column_names_match():
    gold = result(["country", "revenue"], [("France", 10.0), ("Spain", 5.0)])
    got = result(["country_name", "net_revenue"], [("Spain", 5.0), ("France", 10.0)])
    assert results_match(got, gold)


def test_small_rounding_and_decimal_vs_float_match():
    gold = result(["revenue"], [(Decimal("1234.5678"),)])
    assert results_match(result(["r"], [(1234.57,)]), gold)
    assert results_match(result(["r"], [(1234,)]), result(["r"], [(1234.0,)]))


def test_different_numbers_do_not_match():
    gold = result(["revenue"], [(1234.56,)])
    assert not results_match(result(["r"], [(1300.0,)]), gold)


def test_extra_columns_in_the_answer_are_allowed():
    gold = result(["revenue"], [(10.0,), (5.0,)])
    got = result(["country", "orders", "revenue"], [("France", 3, 10.0), ("Spain", 1, 5.0)])
    assert results_match(got, gold)


def test_columns_in_another_order_match():
    gold = result(["country", "revenue"], [("France", 10.0)])
    assert results_match(result(["revenue", "country"], [(10.0, "France")]), gold)


def test_missing_or_extra_rows_do_not_match():
    gold = result(["country"], [("France",), ("Spain",)])
    assert not results_match(result(["c"], [("France",)]), gold)
    assert not results_match(result(["c"], [("France",), ("Spain",), ("Italy",)]), gold)


def test_text_is_compared_case_and_space_insensitive():
    gold = result(["d"], [("WHITE HANGING HEART T-LIGHT HOLDER",)])
    assert results_match(result(["d"], [("white hanging heart t-light holder ",)]), gold)
