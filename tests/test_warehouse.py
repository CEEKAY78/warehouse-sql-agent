import duckdb
import pytest


@pytest.fixture
def con(warehouse_path):
    connection = duckdb.connect(str(warehouse_path), read_only=True)
    yield connection
    connection.close()


def scalar(con, sql):
    return con.execute(sql).fetchone()[0]


def test_star_schema_tables_exist(con):
    tables = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables")
              .fetchall()}
    assert tables == {"fact_sales", "dim_product", "dim_customer", "dim_date", "dim_country"}


def test_fact_keeps_product_lines_and_cancellations_without_duplicates(con):
    # 2 sale lines + 1 cancellation + 1 guest line; postage, manual, zero price and the
    # duplicate are dropped
    assert scalar(con, "SELECT count(*) FROM fact_sales") == 4
    assert scalar(con, "SELECT count(*) FROM fact_sales WHERE is_cancelled") == 1


def test_line_amount_is_quantity_times_price(con):
    assert scalar(con, "SELECT round(sum(line_amount), 2) FROM fact_sales") == pytest.approx(
        83.4 + 40.5 - 13.9 + 20.25
    )


def test_guest_lines_join_to_unknown_customer_and_keep_revenue(con):
    sql = """
        SELECT c.customer_id, round(sum(f.line_amount), 2)
        FROM fact_sales f JOIN dim_customer c USING (customer_key)
        WHERE c.is_guest GROUP BY 1
    """
    assert con.execute(sql).fetchall() == [("UNKNOWN", 20.25)]


def test_dimensions_are_keyed_and_joinable(con):
    sql = """
        SELECT count(*) FROM fact_sales f
        JOIN dim_product p USING (product_key)
        JOIN dim_customer c USING (customer_key)
        JOIN dim_country k USING (country_key)
        JOIN dim_date d USING (date_key)
    """
    assert scalar(con, sql) == 4
    assert scalar(con, "SELECT count(*) FROM dim_product") == 2
    assert scalar(con, "SELECT count(*) FROM dim_country") == 2


def test_dim_date_has_calendar_attributes(con):
    row = con.execute(
        "SELECT year, quarter, month, month_name, day_name, is_weekend FROM dim_date "
        "WHERE date = DATE '2011-01-15'"
    ).fetchone()
    assert row == (2011, 1, 1, "January", "Saturday", True)
