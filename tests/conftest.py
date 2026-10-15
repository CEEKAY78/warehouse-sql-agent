from datetime import datetime

import pandas as pd
import pytest

from wsa.warehouse import build_warehouse


def raw_rows() -> pd.DataFrame:
    """A hand-made extract with the raw UCI column names and every known quality issue."""
    rows = [
        # invoice, stock, description, qty, date, price, customer, country
        ("489434", "85048", "PINK CHERRY LIGHTS", 12, datetime(2010, 12, 1, 9, 0), 6.95, 13085.0,
         "United Kingdom"),
        ("489434", "79323W", "WHITE CHERRY LIGHTS", 6, datetime(2010, 12, 1, 9, 0), 6.75,
         13085.0, "United Kingdom"),
        # exact duplicate of the first line (sheet overlap / repeated extract line)
        ("489434", "85048", "PINK CHERRY LIGHTS", 12, datetime(2010, 12, 1, 9, 0), 6.95, 13085.0,
         "United Kingdom"),
        # cancellation of one product line
        ("C489449", "85048", "PINK CHERRY LIGHTS", -2, datetime(2010, 12, 2, 10, 30), 6.95,
         13085.0, "United Kingdom"),
        # guest checkout: no customer id
        ("489500", "79323W", "WHITE CHERRY LIGHTS", 3, datetime(2011, 1, 15, 14, 0), 6.75, None,
         "France"),
        # non-product codes: postage and manual adjustment
        ("489500", "POST", "POSTAGE", 1, datetime(2011, 1, 15, 14, 0), 18.0, None, "France"),
        ("489501", "M", "Manual", 1, datetime(2011, 1, 16, 8, 0), 0.5, 12345.0, "France"),
        # zero price sample
        ("489502", "85048", "PINK CHERRY LIGHTS", 1, datetime(2011, 1, 16, 9, 0), 0.0, 12345.0,
         "France"),
    ]
    return pd.DataFrame(
        rows,
        columns=["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price",
                 "Customer ID", "Country"],
    )


@pytest.fixture
def warehouse_path(tmp_path):
    return build_warehouse(raw_rows(), tmp_path / "wh.duckdb")
