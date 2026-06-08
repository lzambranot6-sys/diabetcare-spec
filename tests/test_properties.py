# Feature: diabetcare-web-app, Property 5: Corrección de filtros en /registros
# Feature: diabetcare-web-app, Property 8: Seguridad de consultas parametrizadas
# Feature: diabetcare-web-app, Property 10: Formato de visualización del conteo de registros

"""
Property-based tests for app.py correctness properties.
"""

from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app import build_where_clause

# Known filterable column names (controlled set — not user input)
FILTER_COLUMNS = ["gender", "diabetes", "hypertension", "smoking_history"]


@settings(max_examples=200)
@given(
    values=st.fixed_dictionaries({
        col: st.one_of(
            st.just(""),           # empty = no filter
            st.just(None),         # None = no filter
            st.text(),             # arbitrary text including SQL metacharacters
        )
        for col in FILTER_COLUMNS
    })
)
def test_parameterized_query_safety(values):
    """
    Property 8: Seguridad de consultas parametrizadas

    For any filter value — including strings containing SQL metacharacters
    such as ', ", ;, --, DROP, OR 1=1 — build_where_clause must:
    1. Return a SQL fragment containing only %s placeholders (no literal
       interpolation of the input value into the SQL string).
    2. Place the raw input value exclusively in the returned params list.

    Validates: Requirements 4.9
    """
    where_sql, params = build_where_clause(values)

    # Collect all active values (those not filtered out)
    active_values = [v for v in values.values() if v not in (None, "")]

    # Assert params completeness: number of params matches active values
    assert len(params) == len(active_values)

    # Assert %s placeholders: count matches active values
    assert where_sql.count("%s") == len(active_values)

    # Assert values in params: every active value appears in params
    for v in active_values:
        assert v in params

    # Assert no raw value in SQL: the raw string is not embedded in the SQL fragment.
    # We check this by replacing all %s placeholders with a unique sentinel and then
    # verifying that no active value appears in the resulting string.
    # Short values (≤ 3 chars) are skipped because they may coincidentally appear as
    # substrings of SQL keywords (e.g. 'W' in 'WHERE', 's' in '%s') — the placeholder
    # count and params-list checks above already guarantee parameterization safety.
    sentinel_sql = where_sql.replace("%s", "\x00PLACEHOLDER\x00")
    for v in active_values:
        if len(v) > 3:
            assert v not in sentinel_sql, (
                f"User value {v!r} was interpolated directly into the SQL string"
            )


# ---------------------------------------------------------------------------
# Property 10: Formato de visualización del conteo de registros
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Flask test client fixture for property tests."""
    from app import app as flask_app  # noqa: PLC0415
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as test_client:
        yield test_client


@settings(max_examples=100)
@given(st.integers(min_value=0, max_value=10_000_000))
def test_count_display_format(n):
    """
    Property 10: Formato de visualización del conteo de registros

    For any non-negative integer N representing the total number of clinical
    records, the value rendered in the HTML response of the GET / route SHALL
    be the decimal string representation of N with no thousands separator
    (no commas, no dots used as grouping separators).

    Validates: Requirements 3.4
    """
    from app import app as flask_app  # noqa: PLC0415

    flask_app.config["TESTING"] = True

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchone.return_value = (n,)
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)

    with patch("app.get_db_connection", return_value=mock_conn):
        with flask_app.test_client() as test_client:
            response = test_client.get("/")

    html = response.data.decode("utf-8")

    # The plain decimal string of N must appear in the HTML
    assert str(n) in html, (
        f"Expected plain decimal '{n}' to appear in HTML, but it was not found."
    )

    # No thousands-separator variants should appear for N >= 1000
    if n >= 1000:
        comma_sep = f"{n:,}"  # e.g. "1,000,000"
        assert comma_sep not in html, (
            f"Thousands-separated (comma) form '{comma_sep}' found in HTML for N={n}."
        )
        dot_sep = comma_sep.replace(",", ".")  # e.g. "1.000.000"
        assert dot_sep not in html, (
            f"Thousands-separated (dot) form '{dot_sep}' found in HTML for N={n}."
        )


# ---------------------------------------------------------------------------
# Property 5: Corrección de filtros en /registros
# ---------------------------------------------------------------------------

# Valid filter values per column (realistic domain values)
GENDER_VALUES = ["Male", "Female", "Other"]
DIABETES_VALUES = ["0", "1"]
HYPERTENSION_VALUES = ["0", "1"]
SMOKING_VALUES = ["never", "former", "current", "ever", "not current", "No Info"]

# In-memory dataset: 20 records covering all filter combinations
_IN_MEMORY_DATASET = [
    {"id_paciente": 1,  "year": 2021, "gender": "Male",   "age": 45.0, "location": "NY",
     "hypertension": 0, "heart_disease": 0, "smoking_history": "never",       "bmi": 25.0,
     "hba1c_level": 5.5, "blood_glucose_level": 100, "diabetes": 0},
    {"id_paciente": 2,  "year": 2021, "gender": "Male",   "age": 55.0, "location": "CA",
     "hypertension": 1, "heart_disease": 0, "smoking_history": "former",      "bmi": 30.0,
     "hba1c_level": 6.5, "blood_glucose_level": 140, "diabetes": 1},
    {"id_paciente": 3,  "year": 2022, "gender": "Female", "age": 35.0, "location": "TX",
     "hypertension": 0, "heart_disease": 1, "smoking_history": "current",     "bmi": 22.0,
     "hba1c_level": 5.0, "blood_glucose_level": 90,  "diabetes": 0},
    {"id_paciente": 4,  "year": 2022, "gender": "Female", "age": 65.0, "location": "FL",
     "hypertension": 1, "heart_disease": 1, "smoking_history": "ever",        "bmi": 35.0,
     "hba1c_level": 7.5, "blood_glucose_level": 200, "diabetes": 1},
    {"id_paciente": 5,  "year": 2020, "gender": "Other",  "age": 50.0, "location": "WA",
     "hypertension": 0, "heart_disease": 0, "smoking_history": "not current", "bmi": 28.0,
     "hba1c_level": 6.0, "blood_glucose_level": 120, "diabetes": 0},
    {"id_paciente": 6,  "year": 2020, "gender": "Other",  "age": 70.0, "location": "OR",
     "hypertension": 1, "heart_disease": 0, "smoking_history": "No Info",     "bmi": 32.0,
     "hba1c_level": 8.0, "blood_glucose_level": 250, "diabetes": 1},
    {"id_paciente": 7,  "year": 2021, "gender": "Male",   "age": 40.0, "location": "NY",
     "hypertension": 0, "heart_disease": 0, "smoking_history": "current",     "bmi": 24.0,
     "hba1c_level": 5.2, "blood_glucose_level": 95,  "diabetes": 0},
    {"id_paciente": 8,  "year": 2021, "gender": "Female", "age": 60.0, "location": "CA",
     "hypertension": 1, "heart_disease": 1, "smoking_history": "never",       "bmi": 29.0,
     "hba1c_level": 7.0, "blood_glucose_level": 180, "diabetes": 1},
    {"id_paciente": 9,  "year": 2022, "gender": "Male",   "age": 30.0, "location": "TX",
     "hypertension": 0, "heart_disease": 0, "smoking_history": "former",      "bmi": 21.0,
     "hba1c_level": 4.8, "blood_glucose_level": 85,  "diabetes": 0},
    {"id_paciente": 10, "year": 2022, "gender": "Female", "age": 75.0, "location": "FL",
     "hypertension": 1, "heart_disease": 0, "smoking_history": "ever",        "bmi": 38.0,
     "hba1c_level": 9.0, "blood_glucose_level": 300, "diabetes": 1},
    {"id_paciente": 11, "year": 2020, "gender": "Male",   "age": 48.0, "location": "WA",
     "hypertension": 0, "heart_disease": 1, "smoking_history": "not current", "bmi": 26.0,
     "hba1c_level": 5.8, "blood_glucose_level": 110, "diabetes": 0},
    {"id_paciente": 12, "year": 2020, "gender": "Female", "age": 52.0, "location": "OR",
     "hypertension": 0, "heart_disease": 0, "smoking_history": "No Info",     "bmi": 27.0,
     "hba1c_level": 6.2, "blood_glucose_level": 130, "diabetes": 0},
    {"id_paciente": 13, "year": 2021, "gender": "Other",  "age": 43.0, "location": "NY",
     "hypertension": 1, "heart_disease": 0, "smoking_history": "never",       "bmi": 31.0,
     "hba1c_level": 6.8, "blood_glucose_level": 160, "diabetes": 1},
    {"id_paciente": 14, "year": 2021, "gender": "Male",   "age": 58.0, "location": "CA",
     "hypertension": 1, "heart_disease": 1, "smoking_history": "current",     "bmi": 33.0,
     "hba1c_level": 7.8, "blood_glucose_level": 220, "diabetes": 1},
    {"id_paciente": 15, "year": 2022, "gender": "Female", "age": 38.0, "location": "TX",
     "hypertension": 0, "heart_disease": 0, "smoking_history": "former",      "bmi": 23.0,
     "hba1c_level": 5.3, "blood_glucose_level": 98,  "diabetes": 0},
    {"id_paciente": 16, "year": 2022, "gender": "Other",  "age": 62.0, "location": "FL",
     "hypertension": 1, "heart_disease": 1, "smoking_history": "ever",        "bmi": 36.0,
     "hba1c_level": 8.5, "blood_glucose_level": 270, "diabetes": 1},
    {"id_paciente": 17, "year": 2020, "gender": "Male",   "age": 33.0, "location": "WA",
     "hypertension": 0, "heart_disease": 0, "smoking_history": "No Info",     "bmi": 20.0,
     "hba1c_level": 4.5, "blood_glucose_level": 80,  "diabetes": 0},
    {"id_paciente": 18, "year": 2020, "gender": "Female", "age": 67.0, "location": "OR",
     "hypertension": 1, "heart_disease": 0, "smoking_history": "not current", "bmi": 34.0,
     "hba1c_level": 8.2, "blood_glucose_level": 240, "diabetes": 1},
    {"id_paciente": 19, "year": 2021, "gender": "Male",   "age": 25.0, "location": "NY",
     "hypertension": 0, "heart_disease": 0, "smoking_history": "never",       "bmi": 19.0,
     "hba1c_level": 4.2, "blood_glucose_level": 75,  "diabetes": 0},
    {"id_paciente": 20, "year": 2022, "gender": "Female", "age": 80.0, "location": "CA",
     "hypertension": 1, "heart_disease": 1, "smoking_history": "current",     "bmi": 40.0,
     "hba1c_level": 9.5, "blood_glucose_level": 350, "diabetes": 1},
]

# Columns that map filter param names to record dict keys
_FILTER_TO_RECORD_KEY = {
    "gender": "gender",
    "diabetes": "diabetes",
    "hypertension": "hypertension",
    "smoking_history": "smoking_history",
}


def _apply_filters(dataset, filters):
    """Filter the in-memory dataset according to active filter values."""
    result = []
    for record in dataset:
        match = True
        for param, key in _FILTER_TO_RECORD_KEY.items():
            val = filters.get(param)
            if val not in (None, ""):
                # Compare as strings since filter values come from query params
                if str(record[key]) != str(val):
                    match = False
                    break
        if match:
            result.append(record)
    return result


def _make_mock_connection(filtered_records):
    """
    Build a mock psycopg2 connection whose cursor returns:
    - COUNT(*) → len(filtered_records)
    - SELECT id_paciente, year, ... → filtered_records as tuples (first PAGE_SIZE)
    - SELECT DISTINCT {col} → distinct values for that column from the full dataset
    """
    from app import PAGE_SIZE  # noqa: PLC0415

    # Pre-compute distinct values for each dropdown column from the full dataset
    distinct_values = {}
    for col in ["gender", "diabetes", "hypertension", "smoking_history"]:
        seen = sorted({str(r[col]) for r in _IN_MEMORY_DATASET})
        distinct_values[col] = [(v,) for v in seen]

    # Columns returned by the data SELECT (in order)
    data_columns = [
        "id_paciente", "year", "gender", "age", "location",
        "hypertension", "heart_disease", "smoking_history",
        "bmi", "hba1c_level", "blood_glucose_level", "diabetes",
    ]

    # Paginated data rows as tuples
    page_records = filtered_records[:PAGE_SIZE]
    data_rows = [tuple(r[c] for c in data_columns) for r in page_records]

    # Track call index to return the right result for each execute() call
    call_state = {"index": 0}

    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)

    # description for the data query (needed to build column names)
    mock_cursor.description = [(col, None, None, None, None, None, None) for col in data_columns]

    def _execute(sql, params=None):
        idx = call_state["index"]
        call_state["index"] += 1

        if idx == 0:
            # COUNT(*) query
            mock_cursor.fetchone.return_value = (len(filtered_records),)
        elif idx == 1:
            # Data SELECT query
            mock_cursor.fetchall.return_value = data_rows
        else:
            # SELECT DISTINCT queries (one per dropdown column, in order)
            distinct_idx = idx - 2  # 0-based index into dropdown columns
            dropdown_cols = ["gender", "diabetes", "hypertension", "smoking_history"]
            if distinct_idx < len(dropdown_cols):
                col = dropdown_cols[distinct_idx]
                mock_cursor.fetchall.return_value = distinct_values[col]
            else:
                mock_cursor.fetchall.return_value = []

    mock_cursor.execute = MagicMock(side_effect=_execute)

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = mock_cursor

    return mock_conn


import html as _html_module
import re as _re


def _parse_table_rows(html_text):
    """
    Parse the <tbody> of the records table and return a list of dicts,
    one per <tr>, keyed by the 12 column names in order:
      id_paciente, year, gender, age, location, hypertension,
      heart_disease, smoking_history, bmi, hba1c_level,
      blood_glucose_level, diabetes
    """
    TABLE_COLS = [
        "id_paciente", "year", "gender", "age", "location",
        "hypertension", "heart_disease", "smoking_history",
        "bmi", "hba1c_level", "blood_glucose_level", "diabetes",
    ]

    rows = []
    # Extract tbody content
    tbody_match = _re.search(r"<tbody>(.*?)</tbody>", html_text, _re.DOTALL)
    if not tbody_match:
        return rows

    tbody = tbody_match.group(1)
    # Find all <tr>...</tr> blocks
    for tr_match in _re.finditer(r"<tr>(.*?)</tr>", tbody, _re.DOTALL):
        tr_content = tr_match.group(1)
        # Extract all <td>...</td> cell values
        cells = _re.findall(r"<td>(.*?)</td>", tr_content, _re.DOTALL)
        cells = [_html_module.unescape(c.strip()) for c in cells]
        if len(cells) == len(TABLE_COLS):
            rows.append(dict(zip(TABLE_COLS, cells)))
    return rows


filter_strategy = st.fixed_dictionaries({
    "gender": st.one_of(st.just(""), st.sampled_from(GENDER_VALUES)),
    "diabetes": st.one_of(st.just(""), st.sampled_from(DIABETES_VALUES)),
    "hypertension": st.one_of(st.just(""), st.sampled_from(HYPERTENSION_VALUES)),
    "smoking_history": st.one_of(st.just(""), st.sampled_from(SMOKING_VALUES)),
})


@settings(max_examples=100)
@given(filter_strategy)
def test_filter_correctness(filters):
    """
    Property 5: Corrección de filtros en /registros

    For any combination of active filter values (gender, diabetes, hypertension,
    smoking_history), every record returned by the /registros endpoint SHALL
    satisfy all active filter conditions simultaneously. No record in the result
    set SHALL have a field value that differs from the corresponding active filter
    value.

    Validates: Requirements 4.4, 4.5
    """
    from app import app as flask_app  # noqa: PLC0415

    flask_app.config["TESTING"] = True

    # Compute expected filtered records from the in-memory dataset
    expected_records = _apply_filters(_IN_MEMORY_DATASET, filters)

    # Build mock connection that returns the filtered records
    mock_conn = _make_mock_connection(expected_records)

    # Build query string from active filters (skip empty values)
    query_params = {k: v for k, v in filters.items() if v not in (None, "")}
    active_filters = query_params  # same dict, clearer name

    with patch("app.get_db_connection", return_value=mock_conn):
        with flask_app.test_client() as test_client:
            response = test_client.get("/registros", query_string=query_params)

    assert response.status_code == 200, (
        f"Expected HTTP 200 but got {response.status_code} for filters={filters}"
    )

    html_text = response.data.decode("utf-8")

    # Parse the rendered table rows from the HTML
    rendered_rows = _parse_table_rows(html_text)

    # --- Core property assertion ---
    # Every row in the rendered table must satisfy ALL active filter conditions.
    for row in rendered_rows:
        for param, val in active_filters.items():
            # Map filter param name to the column name in the rendered table
            col = _FILTER_TO_RECORD_KEY[param]
            assert str(row[col]) == str(val), (
                f"Rendered row violates active filter '{param}={val}': "
                f"row['{col}']={row[col]!r}. filters={filters}"
            )

    # --- Completeness check ---
    # The number of rendered rows must equal the number of expected matching records
    # (capped at PAGE_SIZE since the mock only returns up to PAGE_SIZE records).
    from app import PAGE_SIZE  # noqa: PLC0415
    expected_count = min(len(expected_records), PAGE_SIZE)
    assert len(rendered_rows) == expected_count, (
        f"Expected {expected_count} rendered rows but got {len(rendered_rows)}. "
        f"filters={filters}"
    )
