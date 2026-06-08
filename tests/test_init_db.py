"""
tests/test_init_db.py — Tests for DB_Initializer (init_db.py)

Includes property-based tests using Hypothesis.
"""

import io
import contextlib
import sys

import pytest
from hypothesis import HealthCheck, given, settings
import hypothesis.strategies as st

from init_db import TABLE_DEFINITIONS, main, table_exists

# Feature: diabetcare-web-app, Property 1: Idempotencia del inicializador de base de datos

TABLE_NAMES = list(TABLE_DEFINITIONS.keys())


# ---------------------------------------------------------------------------
# Property 1: Idempotencia del inicializador de base de datos
# Validates: Requirements 1.4, 1.5
# ---------------------------------------------------------------------------

@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(pre_existing=st.frozensets(st.sampled_from(TABLE_NAMES)))
def test_db_initializer_idempotence(test_db_connection, pre_existing):
    """
    # Feature: diabetcare-web-app, Property 1: Idempotencia del inicializador de base de datos

    Given an arbitrary subset of tables that already exist before main() runs,
    main() must:
    - Create exactly the missing tables (len(TABLE_NAMES) - len(pre_existing))
    - Print "Tablas creadas: {missing_count}"
    - Exit without error (no sys.exit(1))

    Validates: Requirements 1.4, 1.5
    """
    conn = test_db_connection

    try:
        # --- Setup: drop all tables to start clean ---
        with conn.cursor() as cur:
            for table_name in reversed(TABLE_NAMES):
                cur.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')
        conn.commit()

        # --- Create only the pre_existing tables directly ---
        for table_name in pre_existing:
            ddl = TABLE_DEFINITIONS[table_name]
            with conn.cursor() as cur:
                cur.execute(ddl)
        conn.commit()

        # --- Call main() and capture stdout ---
        missing_tables = [t for t in TABLE_NAMES if t not in pre_existing]
        expected_created = len(missing_tables)

        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            main()

        output = captured.getvalue()

        # --- Assert the printed output contains the correct count ---
        assert f"Tablas creadas: {expected_created}" in output, (
            f"Expected 'Tablas creadas: {expected_created}' in output, got: {output!r}\n"
            f"pre_existing={pre_existing}"
        )

    finally:
        # --- Cleanup: drop all tables ---
        try:
            with conn.cursor() as cur:
                for table_name in reversed(TABLE_NAMES):
                    cur.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')
            conn.commit()
        except Exception:
            conn.rollback()


# ---------------------------------------------------------------------------
# Unit tests for DB_Initializer error paths
# ---------------------------------------------------------------------------

from unittest.mock import patch, MagicMock
import psycopg2

from config import DB_CONFIG


def test_db_initializer_connection_error_message(capsys):
    """
    Mock psycopg2.connect to raise OperationalError; assert the error message
    includes host:port and that main() exits with code 1.

    Validates: Requirements 1.6
    """
    with patch("psycopg2.connect", side_effect=psycopg2.OperationalError("connection refused")):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert DB_CONFIG["host"] in captured.out
    assert str(DB_CONFIG["port"]) in captured.out


def test_db_initializer_sql_error_message(capsys):
    """
    Mock table_exists to return False and the cursor's execute() to raise
    psycopg2.Error on the first DDL; assert the first table name is printed
    and main() exits with code 1.

    Validates: Requirements 1.7
    """
    first_table = list(TABLE_DEFINITIONS.keys())[0]  # "diabetes_clinical"

    # Build a mock connection whose cursor raises psycopg2.Error on execute()
    mock_cursor = MagicMock()
    mock_cursor.execute.side_effect = psycopg2.Error("syntax error")

    mock_conn = MagicMock()
    # MagicMock supports context manager protocol automatically:
    # conn.cursor() used as `with conn.cursor() as cur:` works out of the box.
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_conn.cursor.return_value.__exit__.return_value = False

    with patch("psycopg2.connect", return_value=mock_conn), \
         patch("init_db.table_exists", return_value=False):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert first_table in captured.out
