# Feature: diabetcare-web-app, Property 2: Round-trip de carga CSV — fidelidad de datos

"""
Property test for CSV_Loader round-trip fidelity.

Validates: Requirements 2.1, 2.2, 2.5, 2.8
"""

import contextlib
import io
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import psycopg2

from init_db import TABLE_DEFINITIONS


# ---------------------------------------------------------------------------
# Module-scoped fixture: ensure diabetes_clinical table exists
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True, scope="module")
def ensure_diabetes_clinical_table():
    """
    Create the diabetes_clinical table if it doesn't already exist.
    Runs once per module so the property test can always find the table.
    """
    from config import DB_CONFIG

    try:
        conn = psycopg2.connect(**DB_CONFIG)
    except Exception:
        # If DB is unavailable, tests will be skipped by test_db_connection fixture
        return

    try:
        ddl = TABLE_DEFINITIONS["diabetes_clinical"]
        with conn.cursor() as cur:
            cur.execute(ddl)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Hypothesis strategies for each CSV column
# ---------------------------------------------------------------------------

year_st = st.integers(min_value=2000, max_value=2030)
gender_st = st.sampled_from(["Male", "Female", "Other"])
age_st = (
    st.floats(min_value=0.0, max_value=120.0, allow_nan=False, allow_infinity=False)
    .map(lambda x: round(x, 2))
)
location_st = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
    min_size=1,
    max_size=50,
)
race_bin_st = st.integers(min_value=0, max_value=1)
hyp_st = st.integers(min_value=0, max_value=1)
heart_st = st.integers(min_value=0, max_value=1)
smoking_st = st.sampled_from(["never", "former", "current", "ever", "not current"])
bmi_st = (
    st.floats(min_value=10.0, max_value=100.0, allow_nan=False, allow_infinity=False)
    .map(lambda x: round(x, 2))
)
hba1c_st = (
    st.floats(min_value=3.5, max_value=15.0, allow_nan=False, allow_infinity=False)
    .map(lambda x: round(x, 1))
)
glucose_st = st.integers(min_value=50, max_value=500)
diabetes_st = st.integers(min_value=0, max_value=1)


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


@settings(
    max_examples=30,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(
    rows=st.lists(
        st.fixed_dictionaries(
            {
                "year": year_st,
                "gender": gender_st,
                "age": age_st,
                "location": location_st,
                "race:AfricanAmerican": race_bin_st,
                "race:Asian": race_bin_st,
                "race:Caucasian": race_bin_st,
                "race:Hispanic": race_bin_st,
                "race:Other": race_bin_st,
                "hypertension": hyp_st,
                "heart_disease": heart_st,
                "smoking_history": smoking_st,
                "bmi": bmi_st,
                "hbA1c_level": hba1c_st,
                "blood_glucose_level": glucose_st,
                "diabetes": diabetes_st,
            }
        ),
        min_size=1,
        max_size=50,
    )
)
def test_csv_load_round_trip(test_db_connection, sample_csv_builder, rows):
    """
    Property 2: Round-trip de carga CSV — fidelidad de datos

    For any valid CSV with the 16 expected columns:
    - Every row appears in diabetes_clinical with correct column mapping.
    - Numeric values are unchanged (no rounding or transformation).
    - The count printed to stdout equals the number of CSV rows.

    Validates: Requirements 2.1, 2.2, 2.5, 2.8
    """
    import load_csv

    # 1. Write generated rows to a temp CSV file
    csv_path = sample_csv_builder(rows)

    # 2. Capture stdout and call main() with patched CSV_PATH
    captured = io.StringIO()
    try:
        with patch("load_csv.CSV_PATH", new=Path(csv_path)):
            with contextlib.redirect_stdout(captured):
                load_csv.main()

        output = captured.getvalue()

        # 3. Query the DB for all inserted rows
        conn = test_db_connection
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    year, gender, age, location,
                    race_african_american, race_asian, race_caucasian,
                    race_hispanic, race_other,
                    hypertension, heart_disease, smoking_history,
                    bmi, hba1c_level, blood_glucose_level, diabetes
                FROM diabetes_clinical
                ORDER BY id_paciente
                """
            )
            col_names = [desc[0] for desc in cur.description]
            db_rows = [dict(zip(col_names, row)) for row in cur.fetchall()]

        # 4. Assert row count matches
        assert len(db_rows) == len(rows), (
            f"Expected {len(rows)} rows in DB, got {len(db_rows)}"
        )

        # 5. Assert stdout contains the expected count message
        assert f"Registros insertados: {len(rows)}" in output, (
            f"Expected 'Registros insertados: {len(rows)}' in stdout, got: {output!r}"
        )

        # 6. Assert column mapping and value fidelity for each row
        for i, (csv_row, db_row) in enumerate(zip(rows, db_rows)):
            # Column mapping assertions
            assert db_row["race_african_american"] == csv_row["race:AfricanAmerican"], (
                f"Row {i}: race_african_american mismatch"
            )
            assert db_row["race_asian"] == csv_row["race:Asian"], (
                f"Row {i}: race_asian mismatch"
            )
            assert db_row["race_caucasian"] == csv_row["race:Caucasian"], (
                f"Row {i}: race_caucasian mismatch"
            )
            assert db_row["race_hispanic"] == csv_row["race:Hispanic"], (
                f"Row {i}: race_hispanic mismatch"
            )
            assert db_row["race_other"] == csv_row["race:Other"], (
                f"Row {i}: race_other mismatch"
            )
            assert db_row["hba1c_level"] is not None
            assert float(db_row["hba1c_level"]) == float(csv_row["hbA1c_level"]), (
                f"Row {i}: hba1c_level mismatch: "
                f"db={db_row['hba1c_level']!r}, csv={csv_row['hbA1c_level']!r}"
            )

            # Direct-name columns
            assert db_row["year"] == csv_row["year"], f"Row {i}: year mismatch"
            assert db_row["gender"] == csv_row["gender"], f"Row {i}: gender mismatch"
            assert db_row["location"] == csv_row["location"], (
                f"Row {i}: location mismatch"
            )
            assert db_row["hypertension"] == csv_row["hypertension"], (
                f"Row {i}: hypertension mismatch"
            )
            assert db_row["heart_disease"] == csv_row["heart_disease"], (
                f"Row {i}: heart_disease mismatch"
            )
            assert db_row["smoking_history"] == csv_row["smoking_history"], (
                f"Row {i}: smoking_history mismatch"
            )
            assert db_row["diabetes"] == csv_row["diabetes"], (
                f"Row {i}: diabetes mismatch"
            )

            # Numeric columns — psycopg2 returns Decimal for NUMERIC columns
            assert float(db_row["age"]) == float(csv_row["age"]), (
                f"Row {i}: age mismatch: db={db_row['age']!r}, csv={csv_row['age']!r}"
            )
            assert float(db_row["bmi"]) == float(csv_row["bmi"]), (
                f"Row {i}: bmi mismatch: db={db_row['bmi']!r}, csv={csv_row['bmi']!r}"
            )
            # blood_glucose_level is INTEGER — compare directly
            assert int(db_row["blood_glucose_level"]) == int(
                csv_row["blood_glucose_level"]
            ), (
                f"Row {i}: blood_glucose_level mismatch"
            )

    finally:
        # Always clean up: truncate diabetes_clinical
        try:
            conn = test_db_connection
            with conn.cursor() as cur:
                cur.execute("TRUNCATE diabetes_clinical RESTART IDENTITY")
            conn.commit()
        except Exception:
            pass


# Feature: diabetcare-web-app, Property 3: Idempotencia de la carga CSV


@settings(
    max_examples=20,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(
    rows=st.lists(
        st.fixed_dictionaries({
            "year": year_st,
            "gender": gender_st,
            "age": age_st,
            "location": location_st,
            "race:AfricanAmerican": race_bin_st,
            "race:Asian": race_bin_st,
            "race:Caucasian": race_bin_st,
            "race:Hispanic": race_bin_st,
            "race:Other": race_bin_st,
            "hypertension": hyp_st,
            "heart_disease": heart_st,
            "smoking_history": smoking_st,
            "bmi": bmi_st,
            "hbA1c_level": hba1c_st,
            "blood_glucose_level": glucose_st,
            "diabetes": diabetes_st,
        }),
        min_size=1,
        max_size=30,
    )
)
def test_csv_load_idempotence(test_db_connection, sample_csv_builder, rows):
    """
    Property 3: Idempotencia de la carga CSV (truncar antes de insertar)

    Running CSV_Loader twice on the same N-row CSV must result in exactly N
    records in diabetes_clinical — not 2N — because the table is truncated
    before each load.

    Validates: Requirements 2.3
    """
    import load_csv

    # 1. Write rows to a temp CSV file
    csv_path = sample_csv_builder(rows)

    try:
        # 2. Call load_csv.main() twice with the same CSV path, suppressing stdout
        with patch("load_csv.CSV_PATH", new=Path(csv_path)):
            with contextlib.redirect_stdout(io.StringIO()):
                load_csv.main()
            with contextlib.redirect_stdout(io.StringIO()):
                load_csv.main()

        # 3. Query COUNT(*) from diabetes_clinical
        conn = test_db_connection
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM diabetes_clinical")
            count = cur.fetchone()[0]

        # 4. Assert count == len(rows), not 2 * len(rows)
        assert count == len(rows), (
            f"Expected {len(rows)} rows after two loads (idempotent), "
            f"but got {count}. Table was not truncated before second load."
        )

    finally:
        # 5. Clean up: truncate diabetes_clinical
        try:
            conn = test_db_connection
            with conn.cursor() as cur:
                cur.execute("TRUNCATE diabetes_clinical RESTART IDENTITY")
            conn.commit()
        except Exception:
            pass


# Feature: diabetcare-web-app, Property 4: Integridad transaccional de la carga CSV


@settings(
    max_examples=20,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(
    m=st.integers(min_value=1, max_value=20),
    new_rows=st.lists(
        st.fixed_dictionaries({
            "year": year_st,
            "gender": gender_st,
            "age": age_st,
            "location": location_st,
            "race:AfricanAmerican": race_bin_st,
            "race:Asian": race_bin_st,
            "race:Caucasian": race_bin_st,
            "race:Hispanic": race_bin_st,
            "race:Other": race_bin_st,
            "hypertension": hyp_st,
            "heart_disease": heart_st,
            "smoking_history": smoking_st,
            "bmi": bmi_st,
            "hbA1c_level": hba1c_st,
            "blood_glucose_level": glucose_st,
            "diabetes": diabetes_st,
        }),
        min_size=1,
        max_size=10,
    ),
)
def test_csv_load_rollback_on_batch_error(
    test_db_connection, sample_csv_builder, m, new_rows
):
    """
    Property 4: Integridad transaccional de la carga CSV

    Pre-populate the DB with M records; inject a batch error mid-load via a
    mocked psycopg2 connection; assert COUNT(*) == M after the failed run
    (the rollback restored the pre-truncation state).

    Validates: Requirements 2.7
    """
    from unittest.mock import MagicMock, patch
    import load_csv

    conn = test_db_connection

    try:
        # 1. Start clean
        with conn.cursor() as cur:
            cur.execute("TRUNCATE diabetes_clinical RESTART IDENTITY")
        conn.commit()

        # 2. Insert M minimal rows directly
        insert_sql = (
            "INSERT INTO diabetes_clinical ("
            "year, gender, age, location, "
            "race_african_american, race_asian, race_caucasian, "
            "race_hispanic, race_other, "
            "hypertension, heart_disease, smoking_history, "
            "bmi, hba1c_level, blood_glucose_level, diabetes"
            ") VALUES ("
            "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s"
            ")"
        )
        minimal_row = (2020, "Male", 30, "Test", 0, 0, 0, 0, 0, 0, 0, "never", 25.0, 5.0, 100, 0)
        with conn.cursor() as cur:
            for _ in range(m):
                cur.execute(insert_sql, minimal_row)
        conn.commit()

        # 3. Verify M rows exist before the failed load
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM diabetes_clinical")
            pre_count = cur.fetchone()[0]
        assert pre_count == m, f"Pre-population failed: expected {m}, got {pre_count}"

        # 4. Build a CSV with new_rows (will never actually be inserted)
        csv_path = sample_csv_builder(new_rows)

        # 5. Set up mock connection: executemany raises psycopg2.Error on first call
        mock_cursor = MagicMock()
        mock_cursor.execute.return_value = None
        mock_cursor.executemany.side_effect = psycopg2.Error("injected batch error")

        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = False
        mock_conn.rollback = MagicMock()
        mock_conn.commit = MagicMock()
        mock_conn.close = MagicMock()

        # 6. Patch psycopg2.connect inside load_csv and call main(); expect SystemExit(1)
        with patch("load_csv.psycopg2.connect", return_value=mock_conn):
            with patch("load_csv.CSV_PATH", new=Path(csv_path)):
                with contextlib.redirect_stdout(io.StringIO()):
                    with pytest.raises(SystemExit) as exc_info:
                        load_csv.main()
        assert exc_info.value.code == 1, (
            f"Expected sys.exit(1) on batch error, got exit code {exc_info.value.code}"
        )

        # 7. Verify rollback was called on the mock connection
        mock_conn.rollback.assert_called_once()

        # 8. Query COUNT(*) using the real test connection — must still equal M
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM diabetes_clinical")
            post_count = cur.fetchone()[0]

        assert post_count == m, (
            f"Transactional integrity violated: expected {m} rows after failed load "
            f"(rollback should preserve pre-existing records), but got {post_count}"
        )

    finally:
        # 9. Clean up
        try:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE diabetes_clinical RESTART IDENTITY")
            conn.commit()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Unit tests for CSV_Loader error paths (Task 3.5)
# ---------------------------------------------------------------------------


def test_csv_loader_missing_file_error(capsys):
    """
    Test that CSV_Loader prints the expected path and exits with code 1
    when the CSV file does not exist.

    Validates: Requirements 2.6
    """
    import load_csv

    missing_path = Path("/nonexistent/path/diabetes_dataset.csv")

    with patch("load_csv.CSV_PATH", new=missing_path):
        with pytest.raises(SystemExit) as exc_info:
            load_csv.main()

    assert exc_info.value.code == 1, (
        f"Expected exit code 1, got {exc_info.value.code}"
    )

    captured = capsys.readouterr()
    assert str(missing_path) in captured.out, (
        f"Expected path {str(missing_path)!r} in stdout, got: {captured.out!r}"
    )


def test_csv_loader_batch_size_1000(sample_csv_builder):
    """
    Test that executemany is called with slices of exactly 1,000 rows
    (last batch may be smaller).

    Uses 2,500 rows → expects 3 calls: 1000, 1000, 500.

    Validates: Requirements 2.4
    """
    from unittest.mock import MagicMock
    import load_csv

    # Build 2,500 rows with fixed values
    rows = [
        {
            "year": 2021,
            "gender": "Male",
            "age": 30.0,
            "location": "TestCity",
            "race:AfricanAmerican": 0,
            "race:Asian": 0,
            "race:Caucasian": 1,
            "race:Hispanic": 0,
            "race:Other": 0,
            "hypertension": 0,
            "heart_disease": 0,
            "smoking_history": "never",
            "bmi": 25.0,
            "hbA1c_level": 5.5,
            "blood_glucose_level": 100,
            "diabetes": 0,
        }
        for _ in range(2500)
    ]

    csv_path = sample_csv_builder(rows)

    # Set up mock connection
    mock_cursor = MagicMock()
    mock_cursor.execute.return_value = None
    mock_cursor.executemany.return_value = None  # just records calls

    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_conn.cursor.return_value.__exit__.return_value = False
    mock_conn.commit.return_value = None
    mock_conn.close.return_value = None

    import contextlib
    import io

    with patch("load_csv.psycopg2.connect", return_value=mock_conn):
        with patch("load_csv.CSV_PATH", new=Path(csv_path)):
            with contextlib.redirect_stdout(io.StringIO()):
                load_csv.main()

    calls = mock_cursor.executemany.call_args_list

    assert len(calls) == 3, (
        f"Expected 3 executemany calls for 2500 rows with batch size 1000, "
        f"got {len(calls)}"
    )
    assert len(calls[0].args[1]) == 1000, (
        f"Expected first batch size 1000, got {len(calls[0].args[1])}"
    )
    assert len(calls[1].args[1]) == 1000, (
        f"Expected second batch size 1000, got {len(calls[1].args[1])}"
    )
    assert len(calls[2].args[1]) == 500, (
        f"Expected last batch size 500, got {len(calls[2].args[1])}"
    )
