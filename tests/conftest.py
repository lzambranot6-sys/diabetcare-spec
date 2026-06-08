import csv
import pytest

# ---------------------------------------------------------------------------
# DB_CONFIG is imported from config.py (shared constant)
# ---------------------------------------------------------------------------
from config import DB_CONFIG

# ---------------------------------------------------------------------------
# Fixture: test_db_connection
# Provides a live psycopg2 connection to the diabetcare database.
# Yields the connection and closes it after the test.
# ---------------------------------------------------------------------------
@pytest.fixture
def test_db_connection():
    try:
        import psycopg2
        conn = psycopg2.connect(**DB_CONFIG)
        yield conn
        conn.close()
    except Exception as exc:
        pytest.skip(f"PostgreSQL not available: {exc}")


# ---------------------------------------------------------------------------
# Fixture: app_client
# Provides a Flask test client.  The import is deferred so that tests can
# run even before app.py exists — the fixture will be skipped automatically
# if app.py is not yet present.
# ---------------------------------------------------------------------------
@pytest.fixture
def app_client():
    try:
        from app import app  # noqa: PLC0415
        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client
    except ImportError:
        pytest.skip("app.py not yet available")


# ---------------------------------------------------------------------------
# Fixture: sample_csv_builder
# Factory fixture that creates a temporary CSV file with the 16 expected
# clinical columns and returns its path.
#
# Usage inside a test:
#   def test_something(sample_csv_builder):
#       path = sample_csv_builder([{"year": 2021, "gender": "Male", ...}])
# ---------------------------------------------------------------------------

CSV_COLUMNS = [
    "year",
    "gender",
    "age",
    "location",
    "race:AfricanAmerican",
    "race:Asian",
    "race:Caucasian",
    "race:Hispanic",
    "race:Other",
    "hypertension",
    "heart_disease",
    "smoking_history",
    "bmi",
    "hbA1c_level",
    "blood_glucose_level",
    "diabetes",
]


@pytest.fixture
def sample_csv_builder(tmp_path):
    """Return a factory function that writes rows to a temp CSV and yields its path."""

    created_files = []

    def _build(rows: list[dict], filename: str = "sample.csv") -> str:
        """
        Build a CSV file at tmp_path/filename from *rows*.

        Each dict in *rows* must contain the 16 expected column keys.
        Missing keys default to empty string.  Returns the absolute path
        to the created file as a string.
        """
        filepath = tmp_path / filename
        with open(filepath, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for row in rows:
                # Fill missing columns with empty string
                complete_row = {col: row.get(col, "") for col in CSV_COLUMNS}
                writer.writerow(complete_row)
        created_files.append(filepath)
        return str(filepath)

    yield _build
