\
import os
import sqlite3
import pandas as pd

from etl.etl_job import (
    extract_excel_to_df,
    transform_df,
    load_df_to_sqlite,
    run_etl,
)

def test_extract_and_transform_trims_and_snake_cases(make_excel_file):
    excel_path = 'data\raw\Product.xlsx'

    df = extract_excel_to_df(excel_path)
    tfm = transform_df(df)

    # Column names snake-cased, empties dropped
    assert "english_product_name" in tfm.columns
    assert "color" in tfm.columns
    assert "" not in tfm.columns

    # 2. Check trimming: no leading/trailing spaces in key text columns
    assert all(val is None or str(val).strip() == str(val) 
               for val in tfm["english_product_name"].dropna())
    assert all(val is None or str(val).strip() == str(val) 
               for val in tfm["color"].dropna())

    # Row hash exists and is unique
    assert "row_hash" in tfm.columns
    assert tfm["row_hash"].is_unique

def test_product_excel_upsert_is_idempotent(tmp_db_path):
    excel_path = 'data\raw\Product.xlsx'

    # First ETL run
    rows1 = run_etl(excel_path, tmp_db_path, "products")

    # Second ETL run with same file -> should not create duplicates
    rows2 = run_etl(excel_path, tmp_db_path, "products")

    with sqlite3.connect(tmp_db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM products")
        (count,) = cur.fetchone()

    # -------------------------
    # Assertions
    # -------------------------

    # 1. DB should not create duplicates across multiple runs
    assert rows2 == 0  # ideally second run inserts nothing new

    # 2. Total unique rows in DB should equal unique rows in source file
    df = pd.read_excel(excel_path)
    expected_unique_count = (
        df.drop_duplicates()  # drop duplicate rows
          .applymap(lambda x: str(x).strip() if isinstance(x, str) else x)  # strip spaces
          .dropna(how="all")  # drop fully empty rows
          .shape[0]
    )
    assert count == expected_unique_count

    # 3. First run inserted exactly the expected number of rows
    assert rows1 == expected_unique_count

def test_product_excel_extends_schema_on_new_columns(tmp_db_path, tmp_path):
    # First ETL run with the original Product.xlsx
    excel1 = "'data\raw\Product.xlsx'"  
    run_etl(excel1, tmp_db_path, "products2")

    # Second run -> introduce a new column "discount"
    df = pd.read_excel(excel1)
    df["discount"] = 10   # add a new column with fixed value
    new_excel = tmp_path / "Product_with_discount.xlsx"
    df.to_excel(new_excel, index=False)

    run_etl(str(new_excel), tmp_db_path, "products2")

    # Verify schema contains the new column
    with sqlite3.connect(tmp_db_path) as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(products2)")
        cols = [row[1] for row in cur.fetchall()]
        assert "discount" in cols

        # Fetch a couple of rows and check discount values
        cur.execute("SELECT english_product_name, discount FROM products2 LIMIT 5")
        rows = cur.fetchall()

        # Discount column should exist:
        # - NULL for old rows
        # - "10" (stringified) for new rows
        has_null = any(r[1] is None for r in rows)
        has_discount = any(r[1] == "10" for r in rows)

        assert has_null and has_discount
