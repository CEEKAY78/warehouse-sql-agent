"""Download (if needed) the UCI Online Retail II workbook and build data/warehouse.duckdb.

    python scripts/build_warehouse.py [--xlsx PATH]

The workbook (~45 MB, two yearly sheets) is read once and cached as data/raw_lines.parquet.
"""

from __future__ import annotations

import argparse
import io
import sys
import zipfile
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wsa.warehouse import build_warehouse  # noqa: E402

UCI_ZIP = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
DATA = ROOT / "data"


def fetch_xlsx(target: Path) -> Path:
    print(f"downloading {UCI_ZIP}")
    resp = requests.get(UCI_ZIP, timeout=300)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".xlsx"))
        target.write_bytes(zf.read(name))
    return target


def load_raw(xlsx: Path | None) -> pd.DataFrame:
    cache = DATA / "raw_lines.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    if xlsx is None:
        xlsx = DATA / "online_retail_II.xlsx"
        if not xlsx.exists():
            fetch_xlsx(xlsx)
    print(f"reading {xlsx} (about a minute)")
    book = pd.ExcelFile(xlsx)
    raw = pd.concat([book.parse(s) for s in book.sheet_names], ignore_index=True)
    raw["Invoice"] = raw["Invoice"].astype(str)
    raw["StockCode"] = raw["StockCode"].astype(str)
    raw["Description"] = raw["Description"].astype("string")
    raw.to_parquet(cache, index=False)
    return raw


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xlsx", type=Path, default=None)
    args = parser.parse_args()
    DATA.mkdir(exist_ok=True)
    raw = load_raw(args.xlsx)
    path = build_warehouse(raw, DATA / "warehouse.duckdb")
    import duckdb

    con = duckdb.connect(str(path), read_only=True)
    for table in ["fact_sales", "dim_product", "dim_customer", "dim_country", "dim_date"]:
        print(f"{table:13s} {con.execute(f'SELECT count(*) FROM {table}').fetchone()[0]:>9,}")
    con.close()
    print(f"raw lines     {len(raw):>9,}\nwritten {path}")


if __name__ == "__main__":
    main()
