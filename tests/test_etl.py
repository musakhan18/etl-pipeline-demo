import sqlite3
import pandas as pd
from pathlib import Path

from etl.etl_job import (
    extract_excel_to_df,
    transform_df,
    run_etl,
)

PRODUCT_XLSX = Path("data/raw/Product.xlsx")


def test_extract_and_transform_trims_and_snake_cases():
    df = extract_excel_to_df(str(PRODUCT_XLSX))
    tfm = transform_df(df)

    # Column names snake-cased, empties dropped
    assert "english_product_name" in tfm.columns
    assert "color" in tfm.columns
    assert "" not in tfm.columns

    # No leading/trailing spaces
    assert all(val is None or str(val).strip() == str(val)
               for val in tfm["english_product_name"].dropna())
    assert all(val is None or str(val).strip() == str(val)
               for val in tfm["color"].dropna())

    # Row hash exists and is unique
    assert "row_hash" in tfm.columns
    assert tfm["row_hash"].is_unique


def test_product_excel_upsert_is_idempotent(tmp_db_path):
    rows1 = run_etl(str(PRODUCT_XLSX), tmp_db_path, "products")
    rows2 = run_etl(str(PRODUCT_XLSX), tmp_db_path, "products")

    with sqlite3.connect(tmp_db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM products")
        (count,) = cur.fetchone()

    df = pd.read_excel(PRODUCT_XLSX)
    expected_unique_count = (
        df.drop_duplicates()
          .map(lambda x: str(x).strip() if isinstance(x, str) else x)
          .dropna(how="all")
          .shape[0]
    )

    # DB should not grow beyond unique source rows
    assert count == expected_unique_count
    # First run inserts everything
    assert rows1 == expected_unique_count
    # Second run may re-insert, but total must remain same
    assert count == expected_unique_count


def test_product_excel_extends_schema_on_new_columns(tmp_db_path, tmp_path):
    run_etl(str(PRODUCT_XLSX), tmp_db_path, "products2")

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
        # Allow int or str
        has_null = any(r[1] is None for r in rows)
        has_discount = any(r[1] in (10, "10") for r in rows)
        assert "discount" in cols
