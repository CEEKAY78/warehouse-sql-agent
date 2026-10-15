"""Describe the star schema for the prompt: tables, columns, types and their meaning."""

from __future__ import annotations

from pathlib import Path

import duckdb

TABLE_NOTES = {
    "fact_sales": "one row per invoice line (product lines only; postage/fees removed)",
    "dim_product": "one row per stock code",
    "dim_customer": "one row per customer; customer_key 0 = UNKNOWN guest checkouts",
    "dim_country": "customer country of the invoice",
    "dim_date": "calendar, one row per day between the first and last invoice",
}

COLUMN_NOTES = {
    "fact_sales.invoice_no": "invoice number; an order = one invoice_no; 'C...' = cancellation",
    "fact_sales.date_key": "yyyymmdd, joins dim_date",
    "fact_sales.invoice_ts": "timestamp of the invoice",
    "fact_sales.quantity": "units; negative on cancellation lines",
    "fact_sales.unit_price": "GBP per unit",
    "fact_sales.line_amount": "quantity * unit_price in GBP; negative on cancellations",
    "fact_sales.is_cancelled": "true for cancellation lines",
    "dim_customer.is_guest": "true for the single UNKNOWN row (no customer id)",
    "dim_date.is_weekend": "Saturday or Sunday",
}


def describe_schema(db_path: Path | str) -> str:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        cols = con.execute(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "ORDER BY table_name, ordinal_position"
        ).fetchall()
    finally:
        con.close()
    lines: list[str] = []
    current = None
    for table, column, dtype in cols:
        if table != current:
            current = table
            lines.append(f"\nTABLE {table} -- {TABLE_NOTES.get(table, '')}".rstrip(" -"))
        note = COLUMN_NOTES.get(f"{table}.{column}")
        lines.append(f"  {column} {dtype}" + (f" -- {note}" if note else ""))
    return "\n".join(lines).strip()
