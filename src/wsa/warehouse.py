"""Build a small DuckDB star schema from the UCI Online Retail II invoice lines.

Source: https://archive.ics.uci.edu/dataset/502/online+retail+ii (UK online gift retailer,
Dec 2009 - Dec 2011). Cleaning rules, applied before the star schema is built:

- exact duplicate lines are dropped (the two yearly sheets overlap on 1-9 Dec 2010 and the
  raw extract repeats some lines within an invoice);
- non-product stock codes (POST, M, D, BANK CHARGES, ...: no digit in the code) are dropped;
- lines with a zero/negative price or a zero quantity are dropped;
- cancellations (invoice starting with "C", negative quantity) are kept with
  ``is_cancelled = true`` so that net revenue = sum of all line amounts;
- guest checkouts (no customer id, ~23% of lines) are kept and point to one
  ``UNKNOWN`` customer row, so inner joins never silently drop revenue.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

COLUMN_MAP = {
    "Invoice": "invoice",
    "StockCode": "stock_code",
    "Description": "description",
    "Quantity": "quantity",
    "InvoiceDate": "invoice_ts",
    "Price": "unit_price",
    "Customer ID": "customer_id",
    "Country": "country",
}

_STAR_SQL = """
CREATE TABLE lines AS
SELECT DISTINCT
    CAST(invoice AS VARCHAR) AS invoice_no,
    trim(CAST(stock_code AS VARCHAR)) AS stock_code,
    trim(coalesce(CAST(description AS VARCHAR), '')) AS description,
    CAST(quantity AS INTEGER) AS quantity,
    CAST(invoice_ts AS TIMESTAMP) AS invoice_ts,
    CAST(unit_price AS DOUBLE) AS unit_price,
    CASE WHEN customer_id IS NULL THEN 'UNKNOWN'
         ELSE CAST(CAST(customer_id AS BIGINT) AS VARCHAR) END AS customer_id,
    trim(CAST(country AS VARCHAR)) AS country
FROM raw
WHERE regexp_matches(CAST(stock_code AS VARCHAR), '[0-9]')
  AND unit_price > 0
  AND quantity <> 0;

CREATE TABLE dim_product AS
WITH named AS (
    SELECT stock_code, description, count(*) AS n
    FROM lines WHERE description <> '' GROUP BY ALL
),
best AS (
    SELECT stock_code, arg_max(description, n) AS description FROM named GROUP BY 1
)
SELECT row_number() OVER (ORDER BY s.stock_code)::INTEGER AS product_key,
       s.stock_code,
       coalesce(b.description, '') AS description
FROM (SELECT DISTINCT stock_code FROM lines) s LEFT JOIN best b USING (stock_code);

CREATE TABLE dim_customer AS
SELECT row_number() OVER (ORDER BY customer_id = 'UNKNOWN' DESC, customer_id)::INTEGER - 1
           AS customer_key,
       customer_id,
       customer_id = 'UNKNOWN' AS is_guest
FROM (SELECT DISTINCT customer_id FROM lines);

CREATE TABLE dim_country AS
SELECT row_number() OVER (ORDER BY country)::INTEGER AS country_key, country AS country_name
FROM (SELECT DISTINCT country FROM lines);

CREATE TABLE dim_date AS
SELECT CAST(strftime(d, '%Y%m%d') AS INTEGER) AS date_key,
       CAST(d AS DATE) AS date,
       year(d)::INTEGER AS year,
       quarter(d)::INTEGER AS quarter,
       month(d)::INTEGER AS month,
       monthname(d) AS month_name,
       weekofyear(d)::INTEGER AS iso_week,
       dayname(d) AS day_name,
       isodow(d) >= 6 AS is_weekend
FROM range(
    (SELECT CAST(min(invoice_ts) AS DATE) FROM lines),
    (SELECT CAST(max(invoice_ts) AS DATE) FROM lines) + INTERVAL 1 DAY,
    INTERVAL 1 DAY
) t(d);

CREATE TABLE fact_sales AS
SELECT l.invoice_no,
       CAST(strftime(l.invoice_ts, '%Y%m%d') AS INTEGER) AS date_key,
       l.invoice_ts,
       p.product_key,
       c.customer_key,
       k.country_key,
       l.quantity,
       l.unit_price,
       round(l.quantity * l.unit_price, 2) AS line_amount,
       starts_with(l.invoice_no, 'C') AS is_cancelled
FROM lines l
JOIN dim_product p USING (stock_code)
JOIN dim_customer c USING (customer_id)
JOIN dim_country k ON k.country_name = l.country;

DROP TABLE lines;
"""


def build_warehouse(raw: pd.DataFrame, path: Path) -> Path:
    """Write the star schema (fact_sales + 4 dimensions) to a fresh DuckDB file."""
    path = Path(path)
    if path.exists():
        path.unlink()
    frame = raw.rename(columns=COLUMN_MAP)[list(COLUMN_MAP.values())]
    con = duckdb.connect(str(path))
    try:
        con.register("raw", frame)
        con.execute(_STAR_SQL)
        con.unregister("raw")
    finally:
        con.close()
    return path
