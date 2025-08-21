\
import os
import tempfile
import pandas as pd
import pytest

@pytest.fixture
def tmp_db_path(tmp_path):
    db = tmp_path / "test.db"
    return str(db)

@pytest.fixture
def make_excel_file(tmp_path):
    """
    Returns a helper that writes a DataFrame to a temp Excel and returns its path.
    """
    def _make(df: pd.DataFrame, filename: str = "input.xlsx"):
        path = tmp_path / filename
        df.to_excel(path, index=False)
        return str(path)
    return _make
