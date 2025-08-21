import os
import sqlite3
import pandas as pd
from pathlib import Path

from etl.etl_job import (
    extract_excel_to_df,
    transform_df,
    load_df_to_sqlite,
    run_etl,
)

# Path to product Excel file
PRODUCT_XLSX = Path("data/raw/Product.xlsx")


def test_extract_and_transform_trims_and_snake_cases():
    df = extract_excel_to_df(str(PRODUCT_XLSX))
    tfm = transform_df(df)

    # Column names snake-cased, empties dropped
    assert "english_product_name" in tfm.columns
    assert "color" in tfm.columns
    assert "" not in tfm.columns

    # No leading/trailing spaces in text fields
    assert all(val is None or str(val).strip() == str(val)
               for val in tfm["english_product_name"].dropna())
    assert all(val is None or str(val).strip() == str(val)
               for val in tfm["color"].dropna())

    # Row hash exists and is unique
    assert "row_hash" in tfm.columns
    assert tfm["row_hash"].is_unique


def test_product_excel_upsert_is_idempotent(tmp_db_path):
    # First ETL run
    rows1 = run_etl(str(PRODUCT_XLSX), tmp_db_path, "products")
    # Second ETL run on identical file -> no duplicates
    rows2 = run_etl(str(PRODUCT_XLSX), tmp_db_path, "products")

    with sqlite3.connect(tmp_db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM products")
        (count,) = cur.fetchone()

    # Expected unique rows count
    df = pd.read_excel(PRODUCT_XLSX)
    expected_unique_count = (
        df.drop_duplicates()
          .applymap(lambda x: str(x).strip() if isinstance(x, str) else x)
          .dropna(how="all")
          .shape[0]
    )

    assert count == expected_unique_count
    assert rows1 == expected_unique_count
    assert rows2 == 0


def test_product_excel_extends_schema_on_new_columns(tmp_db_path, tmp_path):
    # First ETL run with original file
    run_etl(str(PRODUCT_XLSX), tmp_db_path, "products2")

    # Second run with new column
    df = pd.read_excel(PRODUCT_XLSX)
    df["discount"] = 10
    new_excel = tmp_path / "Product_with_discount.xlsx"
    df.to_excel(new_excel, index=False)

    run_etl(str(new_excel), tmp_db_path, "products2")

    with sqlite3.connect(tmp_db_path) as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(products2)")
        cols = [row[1] for row in cur.fetchall()]
        assert "discount" in cols

        cur.execute("SELECT english_product_name, discount FROM products2 LIMIT 5")
        rows = cur.fetchall()
        has_null = any(r[1] is None for r in rows)
        has_discount = any(r[1] == "10" for r in rows)
        assert has_null and has_discount
