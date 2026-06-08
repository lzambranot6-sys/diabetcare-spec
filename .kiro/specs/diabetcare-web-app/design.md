# Design Document — DiabetCare S.A.

## Overview

DiabetCare S.A. es una aplicación web clínica construida con Flask y PostgreSQL que permite a profesionales de salud visualizar, filtrar y analizar registros de pacientes diabéticos. El sistema se compone de tres capas principales:

1. **Scripts de inicialización y carga** — ejecutados una sola vez (o bajo demanda) para preparar la base de datos.
2. **Servidor Flask** — sirve la interfaz web, expone los endpoints HTTP y gestiona la lógica de negocio.
3. **Base de datos PostgreSQL** — almacena los 100 000 registros clínicos y las tablas auxiliares del dominio.

El dataset de origen (`dataset/diabetes_dataset.csv`) contiene 100 000 filas con 16 columnas clínicas. La tabla principal `diabetes_clinical` agrega una columna `id_paciente` (SERIAL PRIMARY KEY) para un total de 17 columnas.

### Objetivos de diseño

- **Idempotencia**: los scripts de inicialización y carga pueden ejecutarse múltiples veces sin efectos secundarios no deseados.
- **Seguridad**: todas las consultas SQL usan parámetros vinculados para prevenir inyección SQL.
- **Resiliencia**: los errores de base de datos y de red se capturan, se registran y se comunican al usuario sin exponer detalles internos.
- **Accesibilidad**: la interfaz cumple WCAG AA (contraste mínimo 4.5:1).
- **Mantenibilidad**: plantillas HTML con herencia de template base; hoja de estilos única compartida.

---

## Architecture

### Diagrama de componentes

```mermaid
graph TD
    subgraph Scripts
        A[DB_Initializer<br/>init_db.py]
        B[CSV_Loader<br/>load_csv.py]
    end

    subgraph Flask_App
        C[app.py<br/>Flask server]
        D[Dataset_Reloader<br/>reload_dataset()]
        E[Routes<br/>/ · /registros · /reload]
    end

    subgraph Templates
        F[base.html]
        G[index.html]
        H[registros.html]
    end

    subgraph Static
        I[style.css]
    end

    subgraph Database
        J[(PostgreSQL<br/>diabetcare)]
    end

    subgraph Dataset
        K[dataset/diabetes_dataset.csv]
        L[Remote CSV URL]
    end

    A -->|CREATE TABLE IF NOT EXISTS| J
    B -->|TRUNCATE + batch INSERT| J
    B -->|reads| K
    C --> E
    E --> D
    D -->|download| L
    D -->|TRUNCATE + batch INSERT| J
    C -->|SELECT| J
    E -->|render_template| F
    G -->|extends| F
    H -->|extends| F
    F -->|link| I
```

### Flujo de arranque

```
1. Ejecutar init_db.py   → crea las 11 tablas en PostgreSQL
2. Ejecutar load_csv.py  → carga 100 000 registros en diabetes_clinical
3. Ejecutar app.py       → inicia el servidor Flask en el puerto 5000
```

### Estructura de directorios

```
diabetcare-spec/
├── dataset/
│   └── diabetes_dataset.csv
├── static/
│   └── style.css
├── templates/
│   ├── base.html
│   ├── index.html
│   └── registros.html
├── init_db.py
├── load_csv.py
└── app.py
```

---

## Components and Interfaces

### 1. DB_Initializer (`init_db.py`)

**Responsabilidad**: Crear todas las tablas de la base de datos de forma idempotente.

**Interfaz pública**: script ejecutable desde línea de comandos (`python init_db.py`).

**Comportamiento**:
- Se conecta a PostgreSQL usando `psycopg2` con credenciales configurables (variables de entorno o constantes en el módulo).
- Ejecuta `CREATE TABLE IF NOT EXISTS` para cada tabla.
- Lleva un contador de tablas creadas en esta ejecución (detecta si la tabla ya existía consultando `information_schema.tables` antes de cada `CREATE`).
- Imprime el conteo final por `stdout`.
- En caso de error de conexión o SQL, imprime el mensaje de error y llama a `sys.exit(1)`.

**Pseudocódigo**:
```python
def main():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
    except psycopg2.OperationalError as e:
        print(f"Error de conexión a {DB_CONFIG['host']}:{DB_CONFIG['port']} — {e}")
        sys.exit(1)

    created = 0
    for table_name, ddl in TABLE_DEFINITIONS.items():
        if not table_exists(conn, table_name):
            try:
                execute_ddl(conn, ddl)
                created += 1
            except psycopg2.Error as e:
                conn.rollback()
                print(f"Error creando tabla '{table_name}': {e}")
                sys.exit(1)
    conn.commit()
    print(f"Tablas creadas: {created}")
```

---

### 2. CSV_Loader (`load_csv.py`)

**Responsabilidad**: Leer `dataset/diabetes_dataset.csv` con pandas y cargar sus registros en `diabetes_clinical` en lotes de 1 000 filas.

**Interfaz pública**: script ejecutable desde línea de comandos (`python load_csv.py`).

**Comportamiento**:
- Verifica que el archivo CSV exista; si no, imprime la ruta buscada y llama a `sys.exit(1)`.
- Lee el CSV con `pandas.read_csv`.
- Renombra las columnas según el mapeo definido (ver Data Models).
- Abre una transacción, ejecuta `TRUNCATE diabetes_clinical RESTART IDENTITY`, luego inserta en lotes de 1 000 filas usando `executemany`.
- Si cualquier lote falla, ejecuta `rollback()`, imprime el error y llama a `sys.exit(1)`.
- Al finalizar exitosamente, hace `commit()` e imprime el total de registros insertados.
- Los valores numéricos (`bmi`, `hba1c_level`, `blood_glucose_level`) se insertan tal como los entrega pandas, sin redondeo.

**Mapeo de columnas CSV → tabla**:

| Columna CSV            | Columna tabla          |
|------------------------|------------------------|
| `year`                 | `year`                 |
| `gender`               | `gender`               |
| `age`                  | `age`                  |
| `location`             | `location`             |
| `race:AfricanAmerican` | `race_african_american`|
| `race:Asian`           | `race_asian`           |
| `race:Caucasian`       | `race_caucasian`       |
| `race:Hispanic`        | `race_hispanic`        |
| `race:Other`           | `race_other`           |
| `hypertension`         | `hypertension`         |
| `heart_disease`        | `heart_disease`        |
| `smoking_history`      | `smoking_history`      |
| `bmi`                  | `bmi`                  |
| `hbA1c_level`          | `hba1c_level`          |
| `blood_glucose_level`  | `blood_glucose_level`  |
| `diabetes`             | `diabetes`             |

---

### 3. Flask App (`app.py`)

**Responsabilidad**: Servir la interfaz web, gestionar rutas y coordinar el Dataset_Reloader.

**Configuración**:
```python
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "dbname": "diabetcare",
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}
DATASET_URL = os.getenv("DATASET_URL", "https://...")
PAGE_SIZE = 100
BATCH_SIZE = 1000
DOWNLOAD_TIMEOUT = 30  # segundos
```

**Gestión de conexiones**: cada request abre y cierra su propia conexión psycopg2 (patrón request-scoped). No se usa un pool de conexiones para mantener la simplicidad.

**Estado de recarga**: variable global `reload_status` con valores `"idle"`, `"in_progress"`, `"done"`, `"error"`. Se protege con un `threading.Lock` para evitar condiciones de carrera.

---

### 4. Dataset_Reloader

**Responsabilidad**: Descargar el CSV remoto, validarlo y reemplazar los datos en `diabetes_clinical`.

**Interfaz**: función `reload_dataset()` invocada en un hilo separado desde la ruta `/reload`.

**Flujo**:
```
1. Adquirir lock → establecer reload_status = "in_progress"
2. Descargar CSV con requests.get(DATASET_URL, timeout=30, stream=True)
3. Si timeout o error de red → reload_status = "error", preservar datos, retornar
4. Leer contenido en un DataFrame de pandas (desde bytes en memoria)
5. Validar columnas esperadas y que el DataFrame no esté vacío
6. Si validación falla → reload_status = "error", preservar datos, retornar
7. Abrir transacción → TRUNCATE → batch INSERT (igual que CSV_Loader)
8. Si INSERT falla → rollback → reload_status = "error", preservar datos, retornar
9. commit → reload_status = "done" con conteo de registros
10. Liberar lock
```

**Columnas esperadas** (validación):
```python
EXPECTED_COLUMNS = {
    "year", "gender", "age", "location",
    "race:AfricanAmerican", "race:Asian", "race:Caucasian",
    "race:Hispanic", "race:Other", "hypertension", "heart_disease",
    "smoking_history", "bmi", "hbA1c_level", "blood_glucose_level", "diabetes"
}
```

---

### 5. Routes

| Método | Ruta       | Descripción                                              |
|--------|------------|----------------------------------------------------------|
| GET    | `/`        | Página de inicio institucional con total de registros    |
| GET    | `/registros` | Tabla de registros clínicos con filtros y paginación   |
| POST   | `/reload`  | Inicia la recarga del dataset en un hilo separado        |
| GET    | `/reload/status` | Devuelve el estado actual de la recarga (JSON)     |

#### GET `/`

```python
@app.route("/")
def index():
    total = None
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM diabetes_clinical")
                total = cur.fetchone()[0]
    except Exception as e:
        app.logger.error(f"Error consultando total de registros: {e}")
        total = None
    return render_template("index.html", total=total)
```

#### GET `/registros`

Parámetros de query string:
- `gender` (opcional)
- `diabetes` (opcional)
- `hypertension` (opcional)
- `smoking_history` (opcional)
- `page` (entero, default 1)

```python
@app.route("/registros")
def registros():
    filters = {k: request.args.get(k) for k in ["gender","diabetes","hypertension","smoking_history"]}
    page = max(1, int(request.args.get("page", 1)))
    offset = (page - 1) * PAGE_SIZE

    where_clauses, params = build_where_clause(filters)
    base_sql = f"FROM diabetes_clinical {where_clauses}"

    count_sql = f"SELECT COUNT(*) {base_sql}"
    data_sql  = f"""SELECT id_paciente, year, gender, age, location,
                           hypertension, heart_disease, smoking_history,
                           bmi, hba1c_level, blood_glucose_level, diabetes
                    {base_sql}
                    ORDER BY id_paciente
                    LIMIT %s OFFSET %s"""
    ...
```

**Construcción de WHERE parametrizado**:
```python
def build_where_clause(filters: dict) -> tuple[str, list]:
    clauses, params = [], []
    for col, val in filters.items():
        if val not in (None, ""):
            clauses.append(f"{col} = %s")
            params.append(val)
    if clauses:
        return "WHERE " + " AND ".join(clauses), params
    return "", params
```

#### POST `/reload`

```python
@app.route("/reload", methods=["POST"])
def reload():
    with reload_lock:
        if reload_status == "in_progress":
            return jsonify({"status": "in_progress"}), 409
        set_reload_status("in_progress")
    thread = threading.Thread(target=reload_dataset, daemon=True)
    thread.start()
    return jsonify({"status": "in_progress"}), 202
```

#### GET `/reload/status`

```python
@app.route("/reload/status")
def reload_status_endpoint():
    return jsonify(reload_state)  # {"status": "...", "count": N, "error": "..."}
```

---

### 6. Templates HTML

**Herencia de plantillas**:

```
base.html
├── index.html   (bloque: content)
└── registros.html (bloque: content)
```

**`base.html`** — estructura común:
```html
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}DiabetCare S.A.{% endblock %}</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
  <nav class="navbar">
    <a class="nav-brand" href="/">DiabetCare S.A.</a>
    <ul class="nav-links">
      <li><a href="/">Inicio</a></li>
      <li><a href="/registros">Registros Clínicos</a></li>
    </ul>
  </nav>
  <main class="container">
    {% block content %}{% endblock %}
  </main>
  <footer class="footer">
    <p>&copy; DiabetCare S.A.</p>
  </footer>
</body>
</html>
```

**`index.html`** — bloques clave:
- Nombre institucional: `<h1>DiabetCare S.A.</h1>`
- Misión y visión en tarjetas (`<section class="card">`)
- Total de registros: `{{ total if total is not none else 'N/D' }}`
- Enlace a `/registros`

**`registros.html`** — bloques clave:
- Formulario de filtros (4 `<select>` + botón "Filtrar")
- Botón "Recargar Dataset" (deshabilitado si `reload_status == "in_progress"`)
- Indicador de carga (spinner CSS, visible solo durante recarga)
- Tabla HTML con 12 columnas
- Controles de paginación: Primera · Anterior · `Página X de Y` · Siguiente · Última
- Total de registros coincidentes

---

### 7. CSS / Styling (`static/style.css`)

**Paleta de colores**:

| Token          | Valor hex | Uso                              |
|----------------|-----------|----------------------------------|
| `--color-primary`   | `#1565C0` | Navbar, botones primarios        |
| `--color-primary-dark` | `#0D47A1` | Hover de botones primarios    |
| `--color-accent`    | `#1976D2` | Links activos, bordes de tabla   |
| `--color-bg`        | `#FFFFFF` | Fondo de página                  |
| `--color-surface`   | `#F5F9FF` | Fondo de tarjetas y tabla        |
| `--color-text`      | `#0D1B2A` | Texto principal                  |
| `--color-text-light`| `#FFFFFF` | Texto sobre fondo azul           |

**Contraste WCAG AA**:
- Texto `#0D1B2A` sobre fondo `#FFFFFF`: ratio ≈ 18.5:1 ✓
- Texto `#FFFFFF` sobre `#1565C0`: ratio ≈ 7.2:1 ✓
- Texto `#FFFFFF` sobre `#0D47A1`: ratio ≈ 8.6:1 ✓

**Componentes CSS**:
- `.navbar` — barra de navegación fija en la parte superior, fondo `--color-primary`, texto blanco.
- `.container` — ancho máximo 1200 px, centrado con `margin: auto`.
- `.card` — tarjeta con fondo `--color-surface`, borde redondeado, sombra suave.
- `.table-wrapper` — contenedor con `overflow-x: auto` para tablas anchas.
- `table` — bordes colapsos, cabecera con fondo `--color-primary` y texto blanco.
- `.pagination` — flexbox centrado, botones con estado `:disabled`.
- `.spinner` — animación CSS `@keyframes spin`, oculto por defecto (`display: none`), visible con clase `.active`.
- `.btn-reload` — botón de recarga con estado `:disabled` que reduce opacidad.

---

## Data Models

### Tabla principal: `diabetes_clinical`

```sql
CREATE TABLE IF NOT EXISTS diabetes_clinical (
    id_paciente          SERIAL PRIMARY KEY,
    year                 INTEGER,
    gender               VARCHAR(10),
    age                  NUMERIC(5,2),
    location             VARCHAR(100),
    race_african_american SMALLINT,
    race_asian           SMALLINT,
    race_caucasian       SMALLINT,
    race_hispanic        SMALLINT,
    race_other           SMALLINT,
    hypertension         SMALLINT,
    heart_disease        SMALLINT,
    smoking_history      VARCHAR(20),
    bmi                  NUMERIC(6,2),
    hba1c_level          NUMERIC(5,2),
    blood_glucose_level  INTEGER,
    diabetes             SMALLINT
);
```

### Tablas auxiliares (10 tablas)

Cada tabla auxiliar contiene únicamente su clave primaria SERIAL. Se crean para representar el dominio clínico completo y pueden extenderse en iteraciones futuras.

```sql
CREATE TABLE IF NOT EXISTS clinicas (
    id_clinica SERIAL PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS medicos (
    id_medico SERIAL PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS empleados (
    id_empleado SERIAL PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS pacientes_registrados (
    id_paciente_reg SERIAL PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS consultas (
    id_consulta SERIAL PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS medicamentos (
    id_medicamento SERIAL PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS recetas (
    id_receta SERIAL PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS equipos_medicos (
    id_equipo SERIAL PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS alertas (
    id_alerta SERIAL PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS seguimientos (
    id_seguimiento SERIAL PRIMARY KEY
);
```

### Modelo de estado de recarga

```python
# Estado en memoria (no persistido)
reload_state = {
    "status": "idle",    # "idle" | "in_progress" | "done" | "error"
    "count": 0,          # registros cargados en la última recarga exitosa
    "error": None        # mensaje de error si status == "error"
}
reload_lock = threading.Lock()
```

### Modelo de paginación

```python
@dataclass
class PaginationInfo:
    page: int           # página actual (1-indexed)
    page_size: int      # registros por página (100)
    total_records: int  # total de registros con filtros activos
    total_pages: int    # ceil(total_records / page_size)
    has_prev: bool
    has_next: bool
    offset: int         # (page - 1) * page_size
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

---

### Property 1: Idempotencia del inicializador de base de datos

*For any* initial database state (with zero or more of the 11 tables already existing), running `DB_Initializer` a second time SHALL succeed without error and SHALL report a created-table count equal to the number of tables that did not yet exist before that run.

**Validates: Requirements 1.4, 1.5**

---

### Property 2: Round-trip de carga CSV — fidelidad de datos

*For any* valid CSV file whose rows contain the 16 expected columns (including numeric columns `bmi`, `hba1c_level`, `blood_glucose_level`), after `CSV_Loader` completes successfully:
- Every row present in the CSV SHALL appear in `diabetes_clinical` with column names mapped according to the defined mapping.
- Every numeric value stored in the database SHALL be equal to the value as read by pandas from the CSV (no rounding or arithmetic transformation applied).
- The count printed to stdout SHALL equal the number of rows in the CSV.

**Validates: Requirements 2.1, 2.2, 2.5, 2.8**

---

### Property 3: Idempotencia de la carga CSV (truncar antes de insertar)

*For any* valid CSV file with N rows, running `CSV_Loader` twice in succession SHALL result in exactly N records in `diabetes_clinical` — not 2N — because the table is truncated before each load.

**Validates: Requirements 2.3**

---

### Property 4: Integridad transaccional de la carga CSV

*For any* database state with M existing records in `diabetes_clinical`, if a batch insertion error occurs during `CSV_Loader` execution, the database SHALL contain exactly M records after the failed run (full rollback, no partial data).

**Validates: Requirements 2.7**

---

### Property 5: Corrección de filtros en `/registros`

*For any* combination of active filter values (gender, diabetes, hypertension, smoking_history), every record returned by the `/registros` endpoint SHALL satisfy all active filter conditions simultaneously. No record in the result set SHALL have a field value that differs from the corresponding active filter value.

**Validates: Requirements 4.4, 4.5**

---

### Property 6: Invariante de tamaño de página

*For any* page number and any combination of active filters, the number of records returned in a single page response from `/registros` SHALL be greater than zero and less than or equal to 100.

**Validates: Requirements 4.6**

---

### Property 7: Exactitud del conteo de registros filtrados

*For any* combination of active filter values, the total record count displayed on the `/registros` page SHALL equal the actual count of rows in `diabetes_clinical` that satisfy all active filter conditions, as verified by a direct `COUNT(*)` query with the same parameters.

**Validates: Requirements 4.7**

---

### Property 8: Seguridad de consultas parametrizadas

*For any* filter input value — including strings containing SQL metacharacters such as `'`, `"`, `;`, `--`, `DROP`, `OR 1=1` — the `build_where_clause` function SHALL produce a SQL fragment that contains only `%s` placeholders (no literal interpolation of the input value into the SQL string), and the input value SHALL appear exclusively in the returned parameters list.

**Validates: Requirements 4.9**

---

### Property 9: Preservación de datos ante cualquier fallo de recarga

*For any* database state with M records in `diabetes_clinical`, if the `Dataset_Reloader` encounters any of the following failure conditions — network error, download timeout, load/insertion error, invalid CSV schema, or empty CSV — the database SHALL still contain exactly M records after the failed reload attempt, and `reload_state["status"]` SHALL be `"error"`.

**Validates: Requirements 5.3, 5.5, 5.6**

---

### Property 10: Formato de visualización del conteo de registros

*For any* non-negative integer N representing the total number of clinical records, the value rendered in the HTML response of the `/` route SHALL be the decimal string representation of N with no thousands separator (no commas, no dots used as grouping separators).

**Validates: Requirements 3.4**

---

## Error Handling

### Estrategia general

Todos los errores se manejan en tres capas:

1. **Scripts CLI** (`init_db.py`, `load_csv.py`): capturan excepciones, imprimen mensajes descriptivos a `stderr` y terminan con `sys.exit(1)`.
2. **Flask routes**: capturan excepciones de base de datos, registran el error con `app.logger.error()` y devuelven una respuesta degradada (valor `"N/D"` o mensaje de error al usuario).
3. **Dataset_Reloader**: captura errores de red, validación y base de datos; actualiza `reload_state` con `status="error"` y el mensaje de error; nunca modifica la base de datos si ocurre un error.

### Tabla de errores y respuestas

| Escenario                              | Componente          | Respuesta                                                        |
|----------------------------------------|---------------------|------------------------------------------------------------------|
| Fallo de conexión a PostgreSQL         | DB_Initializer      | Imprime host:port + motivo, `sys.exit(1)`                        |
| Error SQL al crear tabla               | DB_Initializer      | Imprime nombre de tabla + error, rollback, `sys.exit(1)`         |
| Archivo CSV no encontrado              | CSV_Loader          | Imprime ruta buscada, `sys.exit(1)`                              |
| Error en lote de inserción             | CSV_Loader          | Rollback completo, imprime error, `sys.exit(1)`                  |
| Fallo de consulta en GET `/`           | Flask route         | Registra error, muestra `"N/D"` en lugar del total              |
| Fallo de consulta en GET `/registros`  | Flask route         | Registra error, muestra mensaje de error al usuario              |
| Error de red / timeout en descarga     | Dataset_Reloader    | `reload_state = {status: "error", error: msg}`, datos intactos   |
| CSV descargado inválido o vacío        | Dataset_Reloader    | `reload_state = {status: "error", error: msg}`, datos intactos   |
| Error de inserción durante recarga     | Dataset_Reloader    | Rollback, `reload_state = {status: "error"}`, datos intactos     |
| Recarga concurrente (ya en progreso)   | Flask route `/reload` | HTTP 409, no inicia nuevo hilo                                 |

### Logging

- Se usa `app.logger` (nivel `ERROR`) para errores en rutas Flask.
- Los scripts CLI usan `print()` a `stderr` para mantener la simplicidad.
- No se registran mensajes de log en operaciones exitosas (Requirement 3.6).

---

## Testing Strategy

### Enfoque dual

La estrategia de pruebas combina:
- **Pruebas de ejemplo** (unit tests): verifican comportamientos específicos, casos de error y elementos de UI.
- **Pruebas basadas en propiedades** (property-based tests): verifican invariantes universales sobre rangos amplios de entradas.

### Librería de property-based testing

Se usará **[Hypothesis](https://hypothesis.readthedocs.io/)** (Python), la librería estándar de PBT para el ecosistema Python/pytest.

```
pip install hypothesis pytest
```

Cada prueba de propiedad se configura con un mínimo de 100 iteraciones:
```python
from hypothesis import given, settings
from hypothesis import strategies as st

@settings(max_examples=100)
@given(...)
def test_property_N(...):
    ...
```

### Etiquetado de pruebas de propiedad

Cada prueba de propiedad incluye un comentario de referencia:

```python
# Feature: diabetcare-web-app, Property N: <texto de la propiedad>
```

### Pruebas de propiedad (una por propiedad del diseño)

| Prueba                                      | Propiedad | Estrategia Hypothesis                                                  |
|---------------------------------------------|-----------|------------------------------------------------------------------------|
| `test_db_initializer_idempotence`           | P1        | `st.subsets(TABLE_NAMES)` — subconjuntos de tablas pre-existentes      |
| `test_csv_load_round_trip`                  | P2        | `st.lists(st.fixed_dictionaries({col: st.one_of(...)}), min_size=1)`   |
| `test_csv_load_idempotence`                 | P3        | `st.lists(...)` — filas CSV válidas                                    |
| `test_csv_load_rollback_on_batch_error`     | P4        | `st.integers(min_value=0)` — M registros pre-existentes                |
| `test_filter_correctness`                   | P5        | `st.fixed_dictionaries` con valores de filtro válidos e inválidos      |
| `test_page_size_invariant`                  | P6        | `st.integers(min_value=1)` — número de página                          |
| `test_filter_count_accuracy`               | P7        | `st.fixed_dictionaries` con combinaciones de filtros                   |
| `test_parameterized_query_safety`           | P8        | `st.text()` — cualquier string incluyendo metacaracteres SQL           |
| `test_reload_failure_preserves_data`        | P9        | `st.one_of(network_error, timeout, invalid_csv, empty_csv)`            |
| `test_count_display_format`                 | P10       | `st.integers(min_value=0, max_value=10_000_000)`                       |

### Pruebas de ejemplo (unit tests)

| Prueba                                          | Requisito |
|-------------------------------------------------|-----------|
| `test_index_renders_brand_name`                 | 3.1       |
| `test_index_shows_mission`                      | 3.2       |
| `test_index_shows_vision`                       | 3.3       |
| `test_index_shows_nd_on_db_failure`             | 3.5       |
| `test_index_logs_error_on_db_failure`           | 3.6       |
| `test_index_has_registros_link`                 | 3.7       |
| `test_registros_renders_table`                  | 4.1       |
| `test_registros_shows_12_columns`               | 4.2       |
| `test_registros_has_filter_dropdowns`           | 4.3       |
| `test_registros_shows_error_on_db_failure`      | 4.8       |
| `test_reload_button_present`                    | 5.1       |
| `test_reload_sets_in_progress_status`           | 5.2       |
| `test_reload_success_shows_count`               | 5.4       |
| `test_reload_spinner_visible_when_in_progress`  | 5.7       |
| `test_reload_button_disabled_when_in_progress`  | 5.8       |
| `test_reload_uses_30s_timeout`                  | 5.9       |
| `test_all_pages_link_stylesheet`                | 6.1       |
| `test_all_pages_have_navbar`                    | 6.2       |
| `test_templates_extend_base`                    | 6.5       |
| `test_pagination_controls_visible`              | 6.6       |
| `test_db_initializer_connection_error_message`  | 1.6       |
| `test_db_initializer_sql_error_message`         | 1.7       |
| `test_csv_loader_missing_file_error`            | 2.6       |
| `test_csv_loader_batch_size_1000`               | 2.4       |

### Pruebas de smoke (configuración)

| Prueba                                          | Requisito |
|-------------------------------------------------|-----------|
| `test_db_connection_succeeds`                   | 1.1       |
| `test_diabetes_clinical_schema`                 | 1.2       |
| `test_auxiliary_tables_exist`                   | 1.3       |

### Configuración de pytest

```ini
# pytest.ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

```
tests/
├── test_init_db.py          # DB_Initializer unit + smoke tests
├── test_load_csv.py         # CSV_Loader unit + property tests
├── test_routes.py           # Flask route unit tests
├── test_reload.py           # Dataset_Reloader unit + property tests
├── test_properties.py       # Hypothesis property-based tests (P1–P10)
└── conftest.py              # Fixtures: test DB, Flask test client, sample CSV
```
