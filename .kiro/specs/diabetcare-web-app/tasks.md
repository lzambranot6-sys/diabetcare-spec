# Implementation Plan: DiabetCare S.A.

## Overview

This plan converts the DiabetCare design into incremental coding tasks. Each task builds on the previous ones, starting with project structure and database layer, moving through the Flask application and templates, and finishing with the full test suite. All code is Python (Flask, psycopg2, pandas, Hypothesis/pytest).

---

## Tasks

- [x] 1. Set up project structure and shared configuration
  - Create the directory layout: `static/`, `templates/`, `tests/`
  - Create `pytest.ini` with `testpaths = tests`, `python_files = test_*.py`, `python_classes = Test*`, `python_functions = test_*`
  - Create `tests/conftest.py` with fixtures: test PostgreSQL connection, Flask test client, sample CSV builder
  - Define `DB_CONFIG` dict (reads `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` from environment with sensible defaults) as a shared module constant reused by all scripts and `app.py`
  - _Requirements: 1.1, 2.1, 5.2_

- [x] 2. Implement `init_db.py` — DB_Initializer
  - [x] 2.1 Write `init_db.py` with `TABLE_DEFINITIONS` dict (11 `CREATE TABLE IF NOT EXISTS` DDL statements) and `main()` function
    - Connect to PostgreSQL via psycopg2 using `DB_CONFIG`
    - For each table, check `information_schema.tables` before issuing DDL; increment `created` counter only when the table did not previously exist
    - Print `Tablas creadas: {created}` on success; print connection destination + error and call `sys.exit(1)` on `OperationalError`; rollback + print table name + error and call `sys.exit(1)` on SQL error
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [x] 2.2 Write property test for DB_Initializer idempotence
    - **Property 1: Idempotencia del inicializador de base de datos**
    - **Validates: Requirements 1.4, 1.5**
    - Use `st.subsets(TABLE_NAMES)` to generate arbitrary subsets of pre-existing tables; assert second run reports `created == len(missing_tables)` and exits without error
    - Annotate: `# Feature: diabetcare-web-app, Property 1: Idempotencia del inicializador de base de datos`

  - [x] 2.3 Write unit tests for DB_Initializer error paths
    - `test_db_initializer_connection_error_message` — mock `psycopg2.connect` to raise `OperationalError`; assert message includes host:port and exits with code 1 (_Requirements: 1.6_)
    - `test_db_initializer_sql_error_message` — mock cursor to raise `psycopg2.Error` on first DDL; assert table name printed and exits with code 1 (_Requirements: 1.7_)

- [x] 3. Implement `load_csv.py` — CSV_Loader
  - [x] 3.1 Write `load_csv.py` with `main()` function
    - Verify `dataset/diabetes_dataset.csv` exists; print path and `sys.exit(1)` if missing
    - Read CSV with `pandas.read_csv`; rename columns per the defined mapping
    - Open transaction: `TRUNCATE diabetes_clinical RESTART IDENTITY`, then `executemany` in batches of 1 000 rows
    - On batch error: `rollback()`, print error, `sys.exit(1)`; on success: `commit()`, print total inserted
    - Insert numeric columns (`bmi`, `hba1c_level`, `blood_glucose_level`) without rounding
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

  - [x] 3.2 Write property test for CSV round-trip fidelity
    - **Property 2: Round-trip de carga CSV — fidelidad de datos**
    - **Validates: Requirements 2.1, 2.2, 2.5, 2.8**
    - Use `st.lists(st.fixed_dictionaries({col: st.one_of(...)}), min_size=1)` to generate valid CSV rows; after load, assert every row appears in DB with correct column mapping and numeric values unchanged
    - Annotate: `# Feature: diabetcare-web-app, Property 2: Round-trip de carga CSV — fidelidad de datos`

  - [x] 3.3 Write property test for CSV load idempotence
    - **Property 3: Idempotencia de la carga CSV (truncar antes de insertar)**
    - **Validates: Requirements 2.3**
    - Run `CSV_Loader` twice on the same N-row CSV; assert `COUNT(*) == N` (not 2N)
    - Annotate: `# Feature: diabetcare-web-app, Property 3: Idempotencia de la carga CSV`

  - [x] 3.4 Write property test for transactional integrity on batch error
    - **Property 4: Integridad transaccional de la carga CSV**
    - **Validates: Requirements 2.7**
    - Pre-populate DB with M records; inject a batch error mid-load; assert `COUNT(*) == M` after failed run
    - Annotate: `# Feature: diabetcare-web-app, Property 4: Integridad transaccional de la carga CSV`

  - [x] 3.5 Write unit tests for CSV_Loader error paths
    - `test_csv_loader_missing_file_error` — assert error message includes expected path and exits with code 1 (_Requirements: 2.6_)
    - `test_csv_loader_batch_size_1000` — assert `executemany` is called with slices of exactly 1 000 rows (_Requirements: 2.4_)

- [x] 4. Checkpoint — Ensure all tests pass
  - Run `pytest tests/test_init_db.py tests/test_load_csv.py` and confirm all tests pass. Ask the user if questions arise.

- [x] 5. Implement `app.py` — Flask server core
  - [x] 5.1 Create `app.py` with Flask app factory, `DB_CONFIG`, `DATASET_URL`, `PAGE_SIZE = 100`, `BATCH_SIZE = 1000`, `DOWNLOAD_TIMEOUT = 30`, `reload_state` dict, and `reload_lock = threading.Lock()`
    - Implement `get_db_connection()` context manager (request-scoped psycopg2 connection)
    - Implement `build_where_clause(filters: dict) -> tuple[str, list]` using only `%s` placeholders — no string interpolation of user values
    - Implement `set_reload_status(status, count=0, error=None)` helper that updates `reload_state` under `reload_lock`
    - _Requirements: 4.9, 5.2_

  - [x]* 5.2 Write property test for parameterized query safety
    - **Property 8: Seguridad de consultas parametrizadas**
    - **Validates: Requirements 4.9**
    - Use `st.text()` (including SQL metacharacters `'`, `"`, `;`, `--`, `DROP`, `OR 1=1`) as filter values; assert `build_where_clause` SQL fragment contains only `%s` placeholders and the raw value appears only in the params list
    - Annotate: `# Feature: diabetcare-web-app, Property 8: Seguridad de consultas parametrizadas`

- [x] 6. Implement Flask routes
  - [x] 6.1 Implement `GET /` route (`index()`)
    - Query `SELECT COUNT(*) FROM diabetes_clinical`; pass `total` to `index.html`
    - On exception: log with `app.logger.error()`, pass `total=None` (renders as "N/D")
    - _Requirements: 3.1, 3.4, 3.5, 3.6, 3.7_

  - [x]* 6.2 Write property test for count display format
    - **Property 10: Formato de visualización del conteo de registros**
    - **Validates: Requirements 3.4**
    - Use `st.integers(min_value=0, max_value=10_000_000)`; mock DB to return N; assert rendered HTML contains the plain decimal string of N with no thousands separator
    - Annotate: `# Feature: diabetcare-web-app, Property 10: Formato de visualización del conteo de registros`

  - [x] 6.3 Implement `GET /registros` route (`registros()`)
    - Parse `gender`, `diabetes`, `hypertension`, `smoking_history`, `page` from query string
    - Call `build_where_clause`; execute count query and data query with `LIMIT 100 OFFSET …`; build `PaginationInfo` dataclass
    - Populate dropdown options from `SELECT DISTINCT` per filterable column
    - On exception: log error, render error message to user
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9_

  - [x]* 6.4 Write property test for filter correctness
    - **Property 5: Corrección de filtros en `/registros`**
    - **Validates: Requirements 4.4, 4.5**
    - Use `st.fixed_dictionaries` with valid filter values; assert every record in the response satisfies all active filter conditions
    - Annotate: `# Feature: diabetcare-web-app, Property 5: Corrección de filtros en /registros`

  - [ ]* 6.5 Write property test for page size invariant
    - **Property 6: Invariante de tamaño de página**
    - **Validates: Requirements 4.6**
    - Use `st.integers(min_value=1)` as page number with arbitrary filter combos; assert `0 < len(records) <= 100` for any page that returns results
    - Annotate: `# Feature: diabetcare-web-app, Property 6: Invariante de tamaño de página`

  - [ ]* 6.6 Write property test for filter count accuracy
    - **Property 7: Exactitud del conteo de registros filtrados**
    - **Validates: Requirements 4.7**
    - Use `st.fixed_dictionaries` with filter combos; assert displayed total equals `COUNT(*)` from a direct DB query with the same parameters
    - Annotate: `# Feature: diabetcare-web-app, Property 7: Exactitud del conteo de registros filtrados`

  - [x] 6.7 Implement `POST /reload` and `GET /reload/status` routes
    - `POST /reload`: acquire `reload_lock`; return HTTP 409 if `status == "in_progress"`; otherwise set status to `"in_progress"`, start daemon thread running `reload_dataset()`; return HTTP 202
    - `GET /reload/status`: return `jsonify(reload_state)`
    - _Requirements: 5.1, 5.2, 5.7, 5.8_

- [ ] 7. Implement `reload_dataset()` — Dataset_Reloader
  - [ ] 7.1 Write `reload_dataset()` function in `app.py`
    - Download CSV with `requests.get(DATASET_URL, timeout=30, stream=True)`; on `requests.Timeout` or `requests.ConnectionError` → set `reload_state` to `"error"`, preserve DB, return
    - Read response bytes into pandas DataFrame; validate `EXPECTED_COLUMNS` and non-empty; on failure → `"error"`, preserve DB, return
    - Open transaction: `TRUNCATE diabetes_clinical RESTART IDENTITY`, batch INSERT 1 000 rows; on error → rollback, `"error"`, preserve DB, return
    - On success: commit, set `reload_state = {status: "done", count: N, error: None}`
    - _Requirements: 5.2, 5.3, 5.4, 5.5, 5.6, 5.9_

  - [ ]* 7.2 Write property test for data preservation on reload failure
    - **Property 9: Preservación de datos ante cualquier fallo de recarga**
    - **Validates: Requirements 5.3, 5.5, 5.6**
    - Use `st.one_of(network_error_strategy, timeout_strategy, invalid_csv_strategy, empty_csv_strategy)`; pre-populate DB with M records; assert `COUNT(*) == M` and `reload_state["status"] == "error"` after each failure mode
    - Annotate: `# Feature: diabetcare-web-app, Property 9: Preservación de datos ante cualquier fallo de recarga`

  - [ ]* 7.3 Write unit tests for Dataset_Reloader
    - `test_reload_sets_in_progress_status` (_Requirements: 5.2_)
    - `test_reload_success_shows_count` (_Requirements: 5.4_)
    - `test_reload_uses_30s_timeout` — assert `requests.get` called with `timeout=30` (_Requirements: 5.9_)

- [ ] 8. Checkpoint — Ensure all route and reloader tests pass
  - Run `pytest tests/test_routes.py tests/test_reload.py` and confirm all tests pass. Ask the user if questions arise.

- [x] 9. Create HTML templates
  - [x] 9.1 Create `templates/base.html`
    - `<!DOCTYPE html>`, `<html lang="es">`, charset UTF-8, viewport meta, `<title>{% block title %}DiabetCare S.A.{% endblock %}</title>`
    - `<link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">`
    - `<nav class="navbar">` with brand link `/` and nav links to `/` and `/registros`
    - `<main class="container">{% block content %}{% endblock %}</main>`
    - `<footer class="footer"><p>&copy; DiabetCare S.A.</p></footer>`
    - _Requirements: 6.1, 6.2, 6.5_

  - [x] 9.2 Create `templates/index.html` extending `base.html`
    - `{% extends "base.html" %}` with `{% block content %}`
    - `<h1>DiabetCare S.A.</h1>`
    - Mission card: "Proveer herramientas tecnológicas de análisis clínico para mejorar el diagnóstico y seguimiento de pacientes diabéticos"
    - Vision card: "Ser la plataforma líder en gestión clínica de diabetes en Latinoamérica"
    - Total records: `{{ total if total is not none else 'N/D' }}`
    - Link to `/registros`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.7_

  - [x] 9.3 Create `templates/registros.html` extending `base.html`
    - `{% extends "base.html" %}` with `{% block content %}`
    - Filter form: 4 `<select>` dropdowns (gender, diabetes, hypertension, smoking_history) + "Filtrar" submit button
    - "Recargar Dataset" button (`disabled` when `reload_status == "in_progress"`)
    - CSS spinner (`<div class="spinner">`) visible only during reload
    - `<div class="table-wrapper"><table>` with 12 columns (`id_paciente`, `year`, `gender`, `age`, `location`, `hypertension`, `heart_disease`, `smoking_history`, `bmi`, `hba1c_level`, `blood_glucose_level`, `diabetes`)
    - Pagination controls: Primera · Anterior · `Página X de Y` · Siguiente · Última
    - Total matching records display
    - Inline `<script>` for polling `/reload/status` and toggling spinner/button state
    - _Requirements: 4.1, 4.2, 4.3, 4.6, 4.7, 5.1, 5.7, 5.8, 6.6_

  - [ ]* 9.4 Write unit tests for templates
    - `test_index_renders_brand_name` (_Requirements: 3.1_)
    - `test_index_shows_mission` (_Requirements: 3.2_)
    - `test_index_shows_vision` (_Requirements: 3.3_)
    - `test_index_shows_nd_on_db_failure` (_Requirements: 3.5_)
    - `test_index_logs_error_on_db_failure` (_Requirements: 3.6_)
    - `test_index_has_registros_link` (_Requirements: 3.7_)
    - `test_registros_renders_table` (_Requirements: 4.1_)
    - `test_registros_shows_12_columns` (_Requirements: 4.2_)
    - `test_registros_has_filter_dropdowns` (_Requirements: 4.3_)
    - `test_registros_shows_error_on_db_failure` (_Requirements: 4.8_)
    - `test_reload_button_present` (_Requirements: 5.1_)
    - `test_reload_spinner_visible_when_in_progress` (_Requirements: 5.7_)
    - `test_reload_button_disabled_when_in_progress` (_Requirements: 5.8_)
    - `test_all_pages_link_stylesheet` (_Requirements: 6.1_)
    - `test_all_pages_have_navbar` (_Requirements: 6.2_)
    - `test_templates_extend_base` (_Requirements: 6.5_)
    - `test_pagination_controls_visible` (_Requirements: 6.6_)

- [ ] 10. Create `static/style.css`
  - Define CSS custom properties: `--color-primary: #1565C0`, `--color-primary-dark: #0D47A1`, `--color-accent: #1976D2`, `--color-bg: #FFFFFF`, `--color-surface: #F5F9FF`, `--color-text: #0D1B2A`, `--color-text-light: #FFFFFF`
  - Implement `.navbar` (fixed top, `background: var(--color-primary)`, white text), `.container` (max-width 1200px, centered), `.card` (surface background, border-radius, box-shadow), `.table-wrapper` (`overflow-x: auto`), `table` (collapsed borders, primary-color header), `.pagination` (flexbox centered, `:disabled` state), `.spinner` (`@keyframes spin`, `display: none` by default, `.active` makes it visible), `.btn-reload` (`:disabled` reduces opacity)
  - Ensure contrast ratios: `#0D1B2A` on `#FFFFFF` ≥ 4.5:1; `#FFFFFF` on `#1565C0` ≥ 4.5:1; `#FFFFFF` on `#0D47A1` ≥ 4.5:1
  - _Requirements: 6.1, 6.3, 6.4_

- [ ] 11. Write smoke tests for database setup
  - Create `tests/test_init_db.py` smoke section:
    - `test_db_connection_succeeds` — assert psycopg2 connects without error (_Requirements: 1.1_)
    - `test_diabetes_clinical_schema` — assert all 17 columns exist with correct types (_Requirements: 1.2_)
    - `test_auxiliary_tables_exist` — assert all 10 auxiliary tables exist (_Requirements: 1.3_)
  - _Requirements: 1.1, 1.2, 1.3_

- [ ] 12. Final checkpoint — Ensure all tests pass
  - Run `pytest tests/` and confirm the full suite passes. Ask the user if questions arise.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Checkpoints (tasks 4, 8, 12) ensure incremental validation at natural boundaries
- Property tests use Hypothesis with `@settings(max_examples=100)` and include the annotation comment `# Feature: diabetcare-web-app, Property N: <title>`
- Unit tests complement property tests — they cover specific examples, error paths, and UI elements
- All SQL queries use `%s` parameterized placeholders via psycopg2; no f-string or `.format()` interpolation of user input is permitted
- `reload_dataset()` runs in a daemon thread; `reload_lock` protects `reload_state` from concurrent access

---

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["2.1", "3.1"] },
    { "id": 1, "tasks": ["2.2", "2.3", "3.2", "3.3", "3.4", "3.5"] },
    { "id": 2, "tasks": ["5.1"] },
    { "id": 3, "tasks": ["5.2", "6.1", "6.3", "6.7"] },
    { "id": 4, "tasks": ["6.2", "6.4", "6.5", "6.6", "7.1"] },
    { "id": 5, "tasks": ["7.2", "7.3", "9.1"] },
    { "id": 6, "tasks": ["9.2", "9.3"] },
    { "id": 7, "tasks": ["9.4", "10"] },
    { "id": 8, "tasks": ["11"] }
  ]
}
```
