# ETL Pipeline Demo (Excel → SQLite) with Automated Tests

This is a fully runnable example showing how to **extract** data from an Excel file, **transform** it,
and **load** it into a SQLite database, along with **pytest** tests to automate the ETL validation.

## Quickstart

```bash
# Option A: using pip (recommended)
pip install -r requirements.txt

# Run the ETL on the Excel into a local SQLite DB:
python -m etl.etl_job --input data/raw/Product.xlsx --db data/warehouse.db --table products

# Run tests
pytest
```

## Project Layout

```
etl-pipeline-demo/
├─ etl/
│  └─ etl_job.py              # ETL implementation + CLI
├─ tests/
│  ├─ conftest.py             # Shared pytest fixtures
│  └─ test_etl.py             # ETL tests
├─ data/
│  └─ raw/
│     └─ Product.xlsx         # (optional) Your uploaded Excel
├─ .github/workflows/ci.yml   # Sample GitHub Actions CI
├─ pyproject.toml             # Project metadata & pytest config
├─ requirements.txt           # Dependencies
└─ README.md
```

## What the ETL Does

- **Extract**: Reads an Excel sheet into a DataFrame (first sheet by default).
- **Transform**:
  - Standardizes column names to `snake_case`.
  - Trims leading/trailing whitespace from `object` (string) columns.
  - Drops fully empty columns and duplicate rows.
  - Adds a stable `row_hash` (MD5) across all columns (used as a primary key).
- **Load**: Upserts into SQLite by `row_hash` (idempotent loads).

You can customize behavior via function parameters or by extending `transform_df`.
