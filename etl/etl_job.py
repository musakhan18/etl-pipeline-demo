\
"""
ETL job: Excel -> SQLite with idempotent upsert and testable functions.
Run as a CLI:
    python -m etl.etl_job --input data/raw/Product.xlsx --db data/warehouse.db --table products
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
from typing import Iterable, Optional

import pandas as pd


def snake_case(name: str) -> str:
    """Convert a column name into snake_case (safe for SQL)."""
    import re
    s = name.strip()
    s = re.sub(r"[^\w]+", "_", s)             # non-word -> _
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)  # camelCase -> camel_Case
    s = re.sub(r"_+", "_", s)
    return s.strip("_").lower()


from typing import Optional
import pandas as pd
import os

def extract_excel_to_df(path: str, sheet_name: Optional[str] = None) -> pd.DataFrame:
    """
    Extract: Read an Excel file into a DataFrame.
    - If sheet_name is None, reads the first sheet.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Input Excel not found: {path}")

    if sheet_name is None:
        dfs = pd.read_excel(path, sheet_name=None)   # returns dict
        first_sheet = list(dfs.keys())[0]
        df = dfs[first_sheet]
    else:
        df = pd.read_excel(path, sheet_name=sheet_name)

    return df.copy()



def transform_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Transform steps:
    - Standardize column names to snake_case.
    - Trim whitespace in object columns.
    - Drop fully empty columns.
    - Drop duplicate rows.
    - Add `row_hash` over all columns as a stable primary key.
    """
    if df is None or df.shape[0] == 0:
        # Return empty with at least a row_hash column to keep loader simple
        return pd.DataFrame(columns=["row_hash"])

    # 1) Standardize column names
    df = df.copy()
    df.columns = [snake_case(str(c)) for c in df.columns]

    # 2) Trim whitespace for string columns
    for c in df.select_dtypes(include=["object"]).columns:
        df[c] = df[c].astype("string").str.strip()

    # 3) Drop fully empty columns
    df = df.dropna(axis=1, how="all")

    # 4) Drop duplicate rows (exact duplicates)
    df = df.drop_duplicates().reset_index(drop=True)

    # 5) Build a stable row hash over *all* columns
    def row_to_hash(row: pd.Series) -> str:
        # Use json-like representation that is stable
        parts = []
        for c in df.columns:
            val = row[c]
            if pd.isna(val):
                parts.append("NULL")
            else:
                parts.append(str(val))
        raw = "||".join(parts).encode("utf-8")
        return hashlib.md5(raw).hexdigest()  # stable, not for security

    df["row_hash"] = df.apply(row_to_hash, axis=1)

    # Deduplicate by row_hash (belt-and-suspenders)
    df = df.drop_duplicates(subset=["row_hash"]).reset_index(drop=True)
    return df


def _ensure_table(conn: sqlite3.Connection, table: str, columns: Iterable[str]) -> None:
    """
    Ensure table exists with the given columns (all as TEXT for simplicity) and row_hash PK.
    If the table exists, we try to add any missing columns.
    """
    cur = conn.cursor()
    # Create if not exists with row_hash primary key
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table} (
            row_hash TEXT PRIMARY KEY
        )
        """
    )
    # Add any missing columns as TEXT (simple demo)
    cur.execute(f"PRAGMA table_info({table})")
    existing_cols = {row[1] for row in cur.fetchall()}  # row[1] is column name
    for c in columns:
        if c == "row_hash":
            continue
        if c not in existing_cols:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {c} TEXT")
    conn.commit()


def load_df_to_sqlite(df: pd.DataFrame, db_path: str, table: str) -> int:
    """
    Load: Upsert DataFrame into SQLite by `row_hash`. Returns number of upserted rows.
    - Creates the DB and table if needed.
    - Stores all non-null values as TEXT for demo simplicity.
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        if df is None or df.empty:
            _ensure_table(conn, table, ["row_hash"])
            return 0

        _ensure_table(conn, table, df.columns)

        # Prepare UPSERT statement
        cols = [c for c in df.columns]  # includes row_hash
        placeholders = ",".join(["?"] * len(cols))
        col_list = ",".join(cols)
        update_clause = ",".join([f"{c}=excluded.{c}" for c in cols if c != "row_hash"])

        sql = f"""
            INSERT INTO {table} ({col_list})
            VALUES ({placeholders})
            ON CONFLICT(row_hash) DO UPDATE SET
            {update_clause}
        """
        data = df.where(pd.notna(df), None).astype(str).values.tolist()

        cur = conn.cursor()
        cur.executemany(sql, data)
        conn.commit()
        return cur.rowcount  # number of rows modified/inserted (approx)


def run_etl(input_path: str, db_path: str, table: str, sheet_name: Optional[str] = None) -> int:
    """
    Convenience function to run the whole ETL and return rows upserted.
    """
    df_raw = extract_excel_to_df(input_path, sheet_name=sheet_name)
    df_tfm = transform_df(df_raw)
    upserted = load_df_to_sqlite(df_tfm, db_path, table)
    return upserted


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Excel → SQLite ETL with tests")
    p.add_argument("--input", required=True, help="Path to input Excel file")
    p.add_argument("--db", required=True, help="Path to SQLite database (will be created)")
    p.add_argument("--table", required=True, help="Destination table name")
    p.add_argument("--sheet", default=None, help="Excel sheet name (default: first sheet)")
    return p.parse_args()


def main():
    args = _parse_args()
    rows = run_etl(args.input, args.db, args.table, sheet_name=args.sheet)
    print(f"Upserted {rows} rows into {args.table} at {args.db}")


if __name__ == "__main__":
    main()
