"""
app.py — DiabetCare S.A. Flask application.
"""

import math
import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass

import psycopg2
import clickhouse_connect
from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from auth import (
    authenticate,
    clinic_filter_clause,
    esc_ch,
    load_user_from_db,
    login_manager,
    role_required,
)
from config import DB_CONFIG

def get_ch_client():
    return clickhouse_connect.get_client(
        host='localhost',
        port=8123,
        username='default',
        password='admin123'
    )

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DATASET_URL = os.getenv(
    "DATASET_URL",
    "https://raw.githubusercontent.com/diabetcare/dataset/main/diabetes_dataset.csv",
)
PAGE_SIZE = 100
BATCH_SIZE = 1000
DOWNLOAD_TIMEOUT = 30  # seconds

# ---------------------------------------------------------------------------
# Reload state (protected by reload_lock)
# ---------------------------------------------------------------------------
reload_state = {
    "status": "idle",  # "idle" | "in_progress" | "done" | "error"
    "count": 0,
    "error": None,
}
reload_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "diabetcare-dev-secret-key")

login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    try:
        return load_user_from_db(get_ch_client(), user_id)
    except Exception:
        return None


@app.before_request
def require_login():
    if request.endpoint in (None, "login", "static"):
        return
    if not current_user.is_authenticated:
        return redirect(url_for("login", next=request.url))


# Buscar templates en carpetas de cada paquete
from jinja2 import ChoiceLoader, FileSystemLoader
app.jinja_loader = ChoiceLoader([
    FileSystemLoader(os.path.join(app.root_path, "templates")),
    FileSystemLoader(os.path.join(app.root_path, "P1_dashboard", "templates")),
    FileSystemLoader(os.path.join(app.root_path, "P2_registros_clinicos", "templates")),
    FileSystemLoader(os.path.join(app.root_path, "P3_gestion_pacientes", "templates")),
    FileSystemLoader(os.path.join(app.root_path, "P4_dimensiones", "templates")),
])
# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


@contextmanager
def get_db_connection():
    """Request-scoped psycopg2 connection context manager."""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()


def build_where_clause(filters: dict) -> tuple:
    """
    Build a parameterized WHERE clause from a filters dict.
    Only %s placeholders are used — no string interpolation of user values.
    The column names come from the filters dict keys, which are a controlled
    set of known column names (not user input), so f"{col} = %s" is safe.
    Returns (where_string, params_list).
    """
    clauses, params = [], []
    for col, val in filters.items():
        if val not in (None, ""):
            clauses.append(f"{col} = %s")
            params.append(val)
    if clauses:
        return "WHERE " + " AND ".join(clauses), params
    return "", params


def set_reload_status(status: str, count: int = 0, error=None) -> None:
    """Update reload_state under reload_lock."""
    with reload_lock:
        reload_state["status"] = status
        reload_state["count"] = count
        reload_state["error"] = error


def _get_dropdown_options(ch):
    return {
        "gender": [
            r[0]
            for r in ch.query(
                "SELECT DISTINCT genero FROM diabetcare.dim_genero ORDER BY genero"
            ).result_rows
        ],
        "diabetes": [
            r[0]
            for r in ch.query(
                "SELECT DISTINCT diabetes FROM diabetcare.diabetes_clinical ORDER BY diabetes"
            ).result_rows
        ],
        "hypertension": [
            r[0]
            for r in ch.query(
                "SELECT DISTINCT hypertension FROM diabetcare.diabetes_clinical ORDER BY hypertension"
            ).result_rows
        ],
        "smoking_history": [
            r[0]
            for r in ch.query(
                "SELECT DISTINCT historial FROM diabetcare.dim_fumado ORDER BY historial"
            ).result_rows
        ],
    }


def _build_pacientes_where(filters, cf="", id_q=None):
    where_clauses = []
    if id_q:
        q = str(id_q).strip()
        if q.isdigit():
            where_clauses.append(f"dc.id_paciente = {int(q)}")
        elif q:
            where_clauses.append(
                f"positionCaseInsensitive(toString(dc.id_paciente), '{esc_ch(q)}') > 0"
            )
    if filters.get("gender"):
        where_clauses.append(f"g.genero = '{esc_ch(filters['gender'])}'")
    if filters.get("diabetes") not in (None, ""):
        where_clauses.append(f"dc.diabetes = {int(filters['diabetes'])}")
    if filters.get("hypertension") not in (None, ""):
        where_clauses.append(f"dc.hypertension = {int(filters['hypertension'])}")
    if filters.get("smoking_history"):
        where_clauses.append(f"f.historial = '{esc_ch(filters['smoking_history'])}'")
    if cf:
        where_clauses.append(cf.strip().replace("AND ", "", 1))
    if where_clauses:
        return "WHERE " + " AND ".join(where_clauses)
    return ""


def _query_pacientes(ch, filters, page, cf="", id_q=None, page_size=PAGE_SIZE):
    offset = (page - 1) * page_size
    where_sql = _build_pacientes_where(filters, cf, id_q)
    base_sql = f"""
        FROM diabetcare.diabetes_clinical dc
        JOIN diabetcare.dim_genero g ON dc.id_genero = g.id_genero
        JOIN diabetcare.dim_ubicacion u ON dc.id_ubicacion = u.id_ubicacion
        JOIN diabetcare.dim_fumado f ON dc.id_fumado = f.id_fumado
        JOIN diabetcare.dim_rango_edad r ON dc.id_rango_edad = r.id_rango
        {where_sql}
    """
    total_records = ch.query(f"SELECT COUNT(*) {base_sql}").result_rows[0][0]
    rows = ch.query(f"""
        SELECT dc.id_paciente, dc.year, g.genero, dc.age, u.ubicacion,
               dc.hypertension, dc.heart_disease, f.historial,
               dc.bmi, dc.hba1c_level, dc.blood_glucose_level, dc.diabetes
        {base_sql}
        ORDER BY dc.id_paciente
        LIMIT {page_size} OFFSET {offset}
    """).result_rows
    columns = [
        "id_paciente", "year", "gender", "age", "location",
        "hypertension", "heart_disease", "smoking_history",
        "bmi", "hba1c_level", "blood_glucose_level", "diabetes",
    ]
    records = [dict(zip(columns, row)) for row in rows]
    total_pages = max(1, math.ceil(total_records / page_size))
    pagination = PaginationInfo(
        page=page,
        page_size=page_size,
        total_records=total_records,
        total_pages=total_pages,
        has_prev=page > 1,
        has_next=page < total_pages,
        offset=offset,
    )
    return records, pagination


# ---------------------------------------------------------------------------
# Pagination dataclass
# ---------------------------------------------------------------------------


@dataclass
class PaginationInfo:
    page: int
    page_size: int
    total_records: int
    total_pages: int
    has_prev: bool
    has_next: bool
    offset: int


# ---------------------------------------------------------------------------
# Expected columns for reload validation
# ---------------------------------------------------------------------------
EXPECTED_COLUMNS = {
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
}

# ---------------------------------------------------------------------------
# Column mapping (CSV → table) — reused by reload_dataset
# ---------------------------------------------------------------------------
COLUMN_MAPPING = {
    "year": "year",
    "gender": "gender",
    "age": "age",
    "location": "location",
    "race:AfricanAmerican": "race_african_american",
    "race:Asian": "race_asian",
    "race:Caucasian": "race_caucasian",
    "race:Hispanic": "race_hispanic",
    "race:Other": "race_other",
    "hypertension": "hypertension",
    "heart_disease": "heart_disease",
    "smoking_history": "smoking_history",
    "bmi": "bmi",
    "hbA1c_level": "hba1c_level",
    "blood_glucose_level": "blood_glucose_level",
    "diabetes": "diabetes",
}

TABLE_COLUMNS = [
    "year",
    "gender",
    "age",
    "location",
    "race_african_american",
    "race_asian",
    "race_caucasian",
    "race_hispanic",
    "race_other",
    "hypertension",
    "heart_disease",
    "smoking_history",
    "bmi",
    "hba1c_level",
    "blood_glucose_level",
    "diabetes",
]

INSERT_SQL = (
    "INSERT INTO diabetes_clinical ("
    + ", ".join(TABLE_COLUMNS)
    + ") VALUES ("
    + ", ".join(["%s"] * len(TABLE_COLUMNS))
    + ")"
)


# ---------------------------------------------------------------------------
# Dataset reloader stub (implemented in task 7.1)
# ---------------------------------------------------------------------------


def reload_dataset() -> None:
    """Reload dataset from local CSV file."""
    import pandas as pd
    base_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(base_dir, "dataset", "diabetes_dataset.csv")

    try:
        if not os.path.exists(csv_path):
            set_reload_status("error", error=f"Archivo no encontrado: {csv_path}")
            return

        df = pd.read_csv(csv_path)

        if not EXPECTED_COLUMNS.issubset(set(df.columns)):
            set_reload_status("error", error="Columnas inválidas en el CSV.")
            return

        if df.empty:
            set_reload_status("error", error="El archivo CSV está vacío.")
            return

        df = df.rename(columns=COLUMN_MAPPING)

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE diabetes_clinical RESTART IDENTITY")
                rows = [tuple(row[col] for col in TABLE_COLUMNS) for _, row in df.iterrows()]
                for i in range(0, len(rows), BATCH_SIZE):
                    batch = rows[i:i + BATCH_SIZE]
                    cur.executemany(INSERT_SQL, batch)
                conn.commit()

        set_reload_status("done", count=len(df))

    except Exception as e:
        set_reload_status("error", error=str(e))


# ---------------------------------------------------------------------------
# Routes — Auth
# ---------------------------------------------------------------------------


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        user = authenticate(
            get_ch_client(),
            request.form.get("username", "").strip(),
            request.form.get("password", ""),
        )
        if user:
            login_user(user)
            next_url = request.args.get("next") or url_for("index")
            return redirect(next_url)
        error = "Usuario o contraseña incorrectos."
    return render_template("login.html", error=error)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Routes — Dashboard
# ---------------------------------------------------------------------------


@app.route("/")
@login_required
def index():
    metrics = {}
    chart_data = {"edad": [], "ubicacion": [], "tipo_diabetes": []}
    cf = clinic_filter_clause(current_user.rol, current_user.id_clinica)
    try:
        ch = get_ch_client()
        total = ch.query(
            f"SELECT COUNT(*) FROM diabetcare.diabetes_clinical dc WHERE 1=1{cf}"
        ).result_rows[0][0]
        con_diabetes = ch.query(
            f"SELECT COUNT(*) FROM diabetcare.diabetes_clinical dc "
            f"WHERE diabetes = 1{cf}"
        ).result_rows[0][0]
        con_hipertension = ch.query(
            f"SELECT COUNT(*) FROM diabetcare.diabetes_clinical dc "
            f"WHERE hypertension = 1{cf}"
        ).result_rows[0][0]
        con_heart = ch.query(
            f"SELECT COUNT(*) FROM diabetcare.diabetes_clinical dc "
            f"WHERE heart_disease = 1{cf}"
        ).result_rows[0][0]
        clinica_top = ch.query(f"""
            SELECT c.nombre, COUNT(*) as total
            FROM diabetcare.diabetes_clinical dc
            JOIN diabetcare.dim_clinica c ON dc.id_clinica = c.id_clinica
            WHERE 1=1{cf}
            GROUP BY c.nombre
            ORDER BY total DESC
            LIMIT 1
        """).result_rows
        medico_top = ch.query(f"""
            SELECT m.nombre, COUNT(*) as total
            FROM diabetcare.diabetes_clinical dc
            JOIN diabetcare.dim_medico m ON dc.id_medico = m.id_medico
            WHERE 1=1{cf}
            GROUP BY m.nombre
            ORDER BY total DESC
            LIMIT 1
        """).result_rows

        chart_edad = ch.query(f"""
            SELECT r.descripcion, COUNT(*) AS total
            FROM diabetcare.diabetes_clinical dc
            JOIN diabetcare.dim_rango_edad r ON dc.id_rango_edad = r.id_rango
            WHERE 1=1{cf}
            GROUP BY r.descripcion, r.id_rango
            ORDER BY r.id_rango
        """).result_rows
        chart_ubicacion = ch.query(f"""
            SELECT u.ubicacion, COUNT(*) AS total
            FROM diabetcare.diabetes_clinical dc
            JOIN diabetcare.dim_ubicacion u ON dc.id_ubicacion = u.id_ubicacion
            WHERE 1=1{cf}
            GROUP BY u.ubicacion
            ORDER BY total DESC
            LIMIT 15
        """).result_rows
        chart_tipo = ch.query(f"""
            SELECT t.tipo, COUNT(*) AS total
            FROM diabetcare.diabetes_clinical dc
            JOIN diabetcare.dim_tipo_diabetes t ON dc.id_tipo_diabetes = t.id_tipo
            WHERE 1=1{cf}
            GROUP BY t.tipo, t.id_tipo
            ORDER BY t.id_tipo
        """).result_rows

        chart_data = {
            "edad": {"labels": [r[0] for r in chart_edad], "values": [r[1] for r in chart_edad]},
            "ubicacion": {
                "labels": [r[0] for r in chart_ubicacion],
                "values": [r[1] for r in chart_ubicacion],
            },
            "tipo_diabetes": {
                "labels": [r[0] for r in chart_tipo],
                "values": [r[1] for r in chart_tipo],
            },
        }

        metrics = {
            "total": total,
            "con_diabetes": con_diabetes,
            "pct_diabetes": round(con_diabetes / total * 100, 1) if total else 0,
            "con_hipertension": con_hipertension,
            "pct_hipertension": round(con_hipertension / total * 100, 1) if total else 0,
            "con_heart": con_heart,
            "pct_heart": round(con_heart / total * 100, 1) if total else 0,
            "clinica_top": clinica_top[0][0] if clinica_top else "N/D",
            "medico_top": medico_top[0][0] if medico_top else "N/D",
        }
    except Exception as e:
        app.logger.error(f"Error cargando métricas: {e}")

    return render_template("index.html", metrics=metrics, chart_data=chart_data)


@app.route("/registros")
@login_required
@role_required("admin", "medico", "analista")
def registros():
    """GET /registros — Clinical records table with filters and pagination (ClickHouse)."""
    try:
        filters = {
            k: request.args.get(k)
            for k in ["gender", "diabetes", "hypertension", "smoking_history"]
        }
        try:
            page = max(1, int(request.args.get("page", 1)))
        except (ValueError, TypeError):
            page = 1

        ch = get_ch_client()
        cf = clinic_filter_clause(current_user.rol, current_user.id_clinica)
        records, pagination = _query_pacientes(ch, filters, page, cf)
        dropdown_options = _get_dropdown_options(ch)

        return render_template(
            "registros.html",
            records=records,
            pagination=pagination,
            dropdown_options=dropdown_options,
            active_filters=filters,
            reload_state=reload_state,
        )

    except Exception as e:
        app.logger.error(f"Error recuperando registros clínicos: {e}")
        return render_template(
            "registros.html",
            error=f"Los registros no pudieron recuperarse: {str(e)}",
            records=[],
            pagination=None,
            dropdown_options={},
            active_filters={},
            reload_state=reload_state,
        )


@app.route("/reload", methods=["POST", "GET"])
@login_required
@role_required("admin")
def reload():
    """POST /reload — Start dataset reload in a background thread."""
    with reload_lock:
        if reload_state["status"] == "in_progress":
            return jsonify({"status": "in_progress"}), 409
        set_reload_status("in_progress")
    thread = threading.Thread(target=reload_dataset, daemon=True)
    thread.start()
    return jsonify({"status": "in_progress"}), 202


@app.route("/reload/status")
def reload_status_endpoint():
    """GET /reload/status — Return current reload state as JSON."""
    return jsonify(reload_state)

# ─────────────────────────────────────────
# CRUD - DIMENSIONES
# ─────────────────────────────────────────

@app.route('/dimensiones')
@login_required
@role_required("admin", "analista")
def dimensiones():
    ch = get_ch_client()
    generos = ch.query("SELECT * FROM diabetcare.dim_genero ORDER BY id_genero").result_rows
    ubicaciones = ch.query("SELECT * FROM diabetcare.dim_ubicacion ORDER BY id_ubicacion").result_rows
    fumados = ch.query("SELECT * FROM diabetcare.dim_fumado ORDER BY id_fumado").result_rows
    rangos = ch.query("SELECT * FROM diabetcare.dim_rango_edad ORDER BY id_rango").result_rows
    razas = ch.query("SELECT * FROM diabetcare.dim_raza ORDER BY id_raza").result_rows
    anios = ch.query("SELECT * FROM diabetcare.dim_anio ORDER BY id_anio").result_rows
    niveles_glucosa = ch.query("SELECT * FROM diabetcare.dim_nivel_glucosa ORDER BY id_nivel").result_rows
    niveles_bmi = ch.query("SELECT * FROM diabetcare.dim_nivel_bmi ORDER BY id_nivel").result_rows
    niveles_hba1c = ch.query("SELECT * FROM diabetcare.dim_nivel_hba1c ORDER BY id_nivel").result_rows
    clinicas = ch.query("SELECT * FROM diabetcare.dim_clinica ORDER BY id_clinica").result_rows
    medicos = ch.query("SELECT * FROM diabetcare.dim_medico ORDER BY id_medico").result_rows
    tipos_diabetes = ch.query("SELECT * FROM diabetcare.dim_tipo_diabetes ORDER BY id_tipo").result_rows

    return render_template('dimensiones.html',
                           generos=generos,
                           ubicaciones=ubicaciones,
                           fumados=fumados,
                           rangos=rangos,
                           razas=razas,
                           anios=anios,
                           niveles_glucosa=niveles_glucosa,
                           niveles_bmi=niveles_bmi,
                           niveles_hba1c=niveles_hba1c,
                           clinicas=clinicas,
                           medicos=medicos,
                           tipos_diabetes=tipos_diabetes,
                           can_admin=current_user.is_admin)


@app.route("/dimensiones/ubicacion/crear", methods=["POST"])
@login_required
@role_required("admin")
def dimensiones_ubicacion_crear():
    ch = get_ch_client()
    ubicacion = request.form.get("ubicacion", "").strip()
    if not ubicacion:
        flash("El nombre de la ubicación es obligatorio.", "error")
        return redirect(url_for("dimensiones"))
    existe = ch.query(
        "SELECT COUNT(*) FROM diabetcare.dim_ubicacion WHERE ubicacion = {u:String}",
        parameters={"u": ubicacion},
    ).result_rows[0][0]
    if existe:
        flash(f"La ubicación «{ubicacion}» ya existe.", "error")
        return redirect(url_for("dimensiones"))
    max_id = ch.query("SELECT MAX(id_ubicacion) FROM diabetcare.dim_ubicacion").result_rows[0][0]
    nuevo_id = (max_id or 0) + 1
    ch.insert(
        "diabetcare.dim_ubicacion",
        [[nuevo_id, ubicacion]],
        column_names=["id_ubicacion", "ubicacion"],
    )
    flash(f"Ubicación «{ubicacion}» agregada correctamente.", "success")
    return redirect(url_for("dimensiones"))


@app.route("/dimensiones/raza/crear", methods=["POST"])
@login_required
@role_required("admin")
def dimensiones_raza_crear():
    ch = get_ch_client()
    raza = request.form.get("raza", "").strip()
    if not raza:
        flash("El nombre de la raza es obligatorio.", "error")
        return redirect(url_for("dimensiones"))
    existe = ch.query(
        "SELECT COUNT(*) FROM diabetcare.dim_raza WHERE raza = {r:String}",
        parameters={"r": raza},
    ).result_rows[0][0]
    if existe:
        flash(f"La raza «{raza}» ya existe.", "error")
        return redirect(url_for("dimensiones"))
    max_id = ch.query("SELECT MAX(id_raza) FROM diabetcare.dim_raza").result_rows[0][0]
    nuevo_id = (max_id or 0) + 1
    ch.insert(
        "diabetcare.dim_raza",
        [[nuevo_id, raza]],
        column_names=["id_raza", "raza"],
    )
    flash(f"Raza «{raza}» agregada correctamente.", "success")
    return redirect(url_for("dimensiones"))

# ─────────────────────────────────────────
# CRUD - FACT PACIENTES
# ─────────────────────────────────────────

@app.route('/fact')
@login_required
@role_required("admin", "medico")
def fact_pacientes():
    ch = get_ch_client()
    try:
        page = max(1, int(request.args.get('page', 1)))
    except:
        page = 1
    offset = (page - 1) * 100

    total = ch.query("SELECT COUNT(*) FROM diabetcare.diabetes_clinical").result_rows[0][0]
    rows = ch.query(f"""
        SELECT f.id_paciente, g.genero, u.ubicacion, fm.historial,
               r.descripcion, f.age, f.bmi, f.hba1c_level,
               f.blood_glucose_level, f.hypertension, f.heart_disease, f.diabetes
        FROM diabetcare.diabetes_clinical f
        JOIN diabetcare.dim_genero g ON f.id_genero = g.id_genero
        JOIN diabetcare.dim_ubicacion u ON f.id_ubicacion = u.id_ubicacion
        JOIN diabetcare.dim_fumado fm ON f.id_fumado = fm.id_fumado
        JOIN diabetcare.dim_rango_edad r ON f.id_rango_edad = r.id_rango
        ORDER BY f.id_paciente
        LIMIT 100 OFFSET {offset}
    """).result_rows

    total_pages = max(1, -(-total // 100))
    generos = ch.query("SELECT * FROM diabetcare.dim_genero").result_rows
    ubicaciones = ch.query("SELECT * FROM diabetcare.dim_ubicacion").result_rows
    fumados = ch.query("SELECT * FROM diabetcare.dim_fumado").result_rows
    rangos = ch.query("SELECT * FROM diabetcare.dim_rango_edad").result_rows

    return render_template('fact.html',
                           rows=rows,
                           page=page,
                           total=total,
                           total_pages=total_pages,
                           generos=generos,
                           ubicaciones=ubicaciones,
                           fumados=fumados,
                           rangos=rangos)

@app.route('/fact/crear', methods=['POST'])
@login_required
@role_required("admin", "medico")
def fact_crear():
    ch = get_ch_client()
    total = ch.query("SELECT MAX(id_paciente) FROM diabetcare.diabetes_clinical").result_rows[0][0]
    nuevo_id = (total or 0) + 1

    id_genero = int(request.form['id_genero'])
    id_ubicacion = int(request.form['id_ubicacion'])
    id_fumado = int(request.form['id_fumado'])
    id_rango_edad = int(request.form['id_rango_edad'])
    age = float(request.form['age'])
    bmi = float(request.form['bmi'])
    hba1c = float(request.form['hba1c_level'])
    glucosa = int(request.form['blood_glucose_level'])
    hypertension = int(request.form['hypertension'])
    heart_disease = int(request.form['heart_disease'])
    diabetes = int(request.form['diabetes'])
    year = int(request.form['year'])

    # Calcular IDs derivados
    id_raza = int(request.form.get('id_raza', 5))
    id_anio = ch.query(f"SELECT id_anio FROM diabetcare.dim_anio WHERE anio = {year} LIMIT 1").result_rows
    id_anio = id_anio[0][0] if id_anio else 1
    id_nivel_glucosa = 1 if glucosa < 100 else 2 if glucosa < 126 else 3 if glucosa < 200 else 4
    id_nivel_bmi = 1 if bmi < 18.5 else 2 if bmi < 25 else 3 if bmi < 30 else 4
    id_nivel_hba1c = 1 if hba1c < 5.7 else 2 if hba1c < 6.5 else 3
    id_clinica = int(request.form.get('id_clinica', 1))
    id_medico = int(request.form.get('id_medico', 1))
    id_tipo = 1 if diabetes == 0 and hba1c < 5.7 and glucosa < 100 else 2 if diabetes == 0 else 3

    ch.insert("diabetcare.diabetes_clinical", [[
        nuevo_id, id_genero, id_ubicacion, id_fumado, id_rango_edad,
        id_raza, id_anio, id_nivel_glucosa, id_nivel_bmi, id_nivel_hba1c,
        id_clinica, id_medico, id_tipo,
        age, bmi, hba1c, glucosa, hypertension, heart_disease, diabetes, year
    ]], column_names=[
        "id_paciente", "id_genero", "id_ubicacion", "id_fumado", "id_rango_edad",
        "id_raza", "id_anio", "id_nivel_glucosa", "id_nivel_bmi", "id_nivel_hba1c",
        "id_clinica", "id_medico", "id_tipo_diabetes",
        "age", "bmi", "hba1c_level", "blood_glucose_level",
        "hypertension", "heart_disease", "diabetes", "year"
    ])
    return redirect('/fact')

@app.route('/fact/eliminar/<int:id_paciente>', methods=['POST'])
@login_required
@role_required("admin")
def fact_eliminar(id_paciente):
    ch = get_ch_client()
    ch.command(f"ALTER TABLE diabetcare.diabetes_clinical DELETE WHERE id_paciente = {id_paciente}")
    return redirect('/fact')

@app.route('/pacientes')
@login_required
@role_required("admin", "medico")
def pacientes():
    ch = get_ch_client()
    try:
        page = max(1, int(request.args.get('page', 1)))
    except:
        page = 1
    offset = (page - 1) * 100

    cf = clinic_filter_clause(current_user.rol, current_user.id_clinica, "dc")
    total = ch.query(
        f"SELECT COUNT(*) FROM diabetcare.diabetes_clinical dc WHERE 1=1{cf}"
    ).result_rows[0][0]
    rows = ch.query(f"""
        SELECT dc.id_paciente, g.genero, u.ubicacion, f.historial,
               r.descripcion, dc.age, dc.bmi, dc.hba1c_level,
               dc.blood_glucose_level, dc.hypertension, dc.heart_disease, dc.diabetes,
               c.nombre, m.nombre
        FROM diabetcare.diabetes_clinical dc
        JOIN diabetcare.dim_genero g ON dc.id_genero = g.id_genero
        JOIN diabetcare.dim_ubicacion u ON dc.id_ubicacion = u.id_ubicacion
        JOIN diabetcare.dim_fumado f ON dc.id_fumado = f.id_fumado
        JOIN diabetcare.dim_rango_edad r ON dc.id_rango_edad = r.id_rango
        JOIN diabetcare.dim_clinica c ON dc.id_clinica = c.id_clinica
        JOIN diabetcare.dim_medico m ON dc.id_medico = m.id_medico
        WHERE 1=1{cf}
        ORDER BY dc.id_paciente
        LIMIT 100 OFFSET {offset}
    """).result_rows

    generos = ch.query("SELECT * FROM diabetcare.dim_genero").result_rows
    ubicaciones = ch.query("SELECT * FROM diabetcare.dim_ubicacion").result_rows
    fumados = ch.query("SELECT * FROM diabetcare.dim_fumado").result_rows
    rangos = ch.query("SELECT * FROM diabetcare.dim_rango_edad").result_rows
    razas = ch.query("SELECT * FROM diabetcare.dim_raza").result_rows
    clinicas = ch.query("SELECT * FROM diabetcare.dim_clinica").result_rows
    medicos = ch.query("SELECT * FROM diabetcare.dim_medico").result_rows
    anios = ch.query("SELECT anio FROM diabetcare.dim_anio ORDER BY anio").result_rows

    if current_user.is_medico:
        clinicas = [c for c in clinicas if c[0] == current_user.id_clinica]
        medicos = [m for m in medicos if m[3] == current_user.id_clinica]

    total_pages = max(1, -(-total // 100))

    return render_template('pacientes.html',
                           rows=rows,
                           page=page,
                           total=total,
                           total_pages=total_pages,
                           generos=generos,
                           ubicaciones=ubicaciones,
                           fumados=fumados,
                           rangos=rangos,
                           razas=razas,
                           clinicas=clinicas,
                           medicos=medicos,
                           anios=anios,
                           can_admin=current_user.is_admin)

@app.route('/pacientes/crear', methods=['POST'])
@login_required
@role_required("admin", "medico")
def pacientes_crear():
    ch = get_ch_client()
    total = ch.query("SELECT MAX(id_paciente) FROM diabetcare.diabetes_clinical").result_rows[0][0]
    nuevo_id = (total or 0) + 1

    id_genero = int(request.form['id_genero'])
    id_ubicacion = int(request.form['id_ubicacion'])
    id_fumado = int(request.form['id_fumado'])
    id_rango_edad = int(request.form['id_rango_edad'])
    id_raza = int(request.form['id_raza'])
    if current_user.is_medico:
        id_clinica = current_user.id_clinica
    else:
        id_clinica = int(request.form['id_clinica'])
    id_medico = int(request.form['id_medico'])
    age = float(request.form['age'])
    bmi = float(request.form['bmi'])
    hba1c = float(request.form['hba1c_level'])
    glucosa = int(request.form['blood_glucose_level'])
    hypertension = int(request.form['hypertension'])
    heart_disease = int(request.form['heart_disease'])
    diabetes = int(request.form['diabetes'])
    year = int(request.form['year'])

    id_anio = ch.query(f"SELECT id_anio FROM diabetcare.dim_anio WHERE anio = {year} LIMIT 1").result_rows
    id_anio = id_anio[0][0] if id_anio else 1
    id_nivel_glucosa = 1 if glucosa < 100 else 2 if glucosa < 126 else 3 if glucosa < 200 else 4
    id_nivel_bmi = 1 if bmi < 18.5 else 2 if bmi < 25 else 3 if bmi < 30 else 4
    id_nivel_hba1c = 1 if hba1c < 5.7 else 2 if hba1c < 6.5 else 3
    id_tipo = 1 if diabetes == 0 and hba1c < 5.7 and glucosa < 100 else 2 if diabetes == 0 else 3

    ch.insert("diabetcare.diabetes_clinical", [[
        nuevo_id, id_genero, id_ubicacion, id_fumado, id_rango_edad,
        id_raza, id_anio, id_nivel_glucosa, id_nivel_bmi, id_nivel_hba1c,
        id_clinica, id_medico, id_tipo,
        age, bmi, hba1c, glucosa, hypertension, heart_disease, diabetes, year
    ]], column_names=[
        "id_paciente", "id_genero", "id_ubicacion", "id_fumado", "id_rango_edad",
        "id_raza", "id_anio", "id_nivel_glucosa", "id_nivel_bmi", "id_nivel_hba1c",
        "id_clinica", "id_medico", "id_tipo_diabetes",
        "age", "bmi", "hba1c_level", "blood_glucose_level",
        "hypertension", "heart_disease", "diabetes", "year"
    ])
    return redirect('/pacientes')

@app.route('/pacientes/masivo', methods=['POST'])
@login_required
@role_required("admin")
def pacientes_masivo():
    import subprocess
    import sys
    cantidad = int(request.form.get('cantidad', 100000))
    base_dir = os.path.dirname(os.path.abspath(__file__))
    script = os.path.join(base_dir, 'P5_pipeline_etl', 'generar_registros.py')
    subprocess.Popen([sys.executable, script, str(cantidad)])
    return redirect('/pacientes')

@app.route('/pacientes/eliminar/<int:id_paciente>', methods=['POST'])
@login_required
@role_required("admin")
def pacientes_eliminar(id_paciente):
    ch = get_ch_client()
    ch.command(f"ALTER TABLE diabetcare.diabetes_clinical DELETE WHERE id_paciente = {id_paciente}")
    return redirect('/pacientes')

@app.route('/pacientes/eliminar-masivo', methods=['POST'])
@login_required
@role_required("admin")
def pacientes_eliminar_masivo():
    ch = get_ch_client()
    cantidad = int(request.form.get('cantidad', 100000))
    total = ch.query("SELECT MAX(id_paciente) FROM diabetcare.diabetes_clinical").result_rows[0][0]
    desde = (total or 0) - cantidad + 1
    if desde < 1:
        desde = 1
    ch.command(f"ALTER TABLE diabetcare.diabetes_clinical DELETE WHERE id_paciente >= {desde}")
    return redirect('/pacientes')


# ─────────────────────────────────────────
# CRUD - CLÍNICAS
# ─────────────────────────────────────────


@app.route("/clinicas")
@login_required
@role_required("admin")
def clinicas_list():
    ch = get_ch_client()
    rows = ch.query("""
        SELECT c.id_clinica, c.nombre, c.ciudad, COUNT(dc.id_paciente) AS pacientes
        FROM diabetcare.dim_clinica c
        LEFT JOIN diabetcare.diabetes_clinical dc ON c.id_clinica = dc.id_clinica
        GROUP BY c.id_clinica, c.nombre, c.ciudad
        ORDER BY c.id_clinica
    """).result_rows
    clinicas = [
        {"id": r[0], "nombre": r[1], "ciudad": r[2], "pacientes": r[3]}
        for r in rows
    ]
    return render_template("clinicas.html", clinicas=clinicas)


@app.route("/clinicas/crear", methods=["POST"])
@login_required
@role_required("admin")
def clinicas_crear():
    ch = get_ch_client()
    nombre = request.form.get("nombre", "").strip()
    ciudad = request.form.get("ciudad", "").strip()
    if not nombre or not ciudad:
        flash("Nombre y ciudad son obligatorios.", "error")
        return redirect(url_for("clinicas_list"))
    max_id = ch.query("SELECT MAX(id_clinica) FROM diabetcare.dim_clinica").result_rows[0][0]
    nuevo_id = (max_id or 0) + 1
    ch.insert(
        "diabetcare.dim_clinica",
        [[nuevo_id, nombre, ciudad]],
        column_names=["id_clinica", "nombre", "ciudad"],
    )
    flash(f"Clínica «{nombre}» creada correctamente.", "success")
    return redirect(url_for("clinicas_list"))


@app.route("/clinicas/editar/<int:id_clinica>", methods=["POST"])
@login_required
@role_required("admin")
def clinicas_editar(id_clinica):
    ch = get_ch_client()
    nombre = request.form.get("nombre", "").strip()
    ciudad = request.form.get("ciudad", "").strip()
    if not nombre or not ciudad:
        flash("Nombre y ciudad son obligatorios.", "error")
        return redirect(url_for("clinicas_list"))
    ch.command(
        f"ALTER TABLE diabetcare.dim_clinica UPDATE "
        f"nombre = '{esc_ch(nombre)}', ciudad = '{esc_ch(ciudad)}' "
        f"WHERE id_clinica = {id_clinica}"
    )
    flash("Clínica actualizada.", "success")
    return redirect(url_for("clinicas_list"))


@app.route("/clinicas/eliminar/<int:id_clinica>", methods=["POST"])
@login_required
@role_required("admin")
def clinicas_eliminar(id_clinica):
    ch = get_ch_client()
    count = ch.query(
        f"SELECT COUNT(*) FROM diabetcare.diabetes_clinical "
        f"WHERE id_clinica = {id_clinica}"
    ).result_rows[0][0]
    if count > 0:
        flash(
            f"No se puede eliminar: hay {count:,} pacientes asignados a esta clínica.",
            "error",
        )
        return redirect(url_for("clinicas_list"))
    med_count = ch.query(
        f"SELECT COUNT(*) FROM diabetcare.dim_medico WHERE id_clinica = {id_clinica}"
    ).result_rows[0][0]
    if med_count > 0:
        flash(
            f"No se puede eliminar: hay {med_count} médico(s) asignados a esta clínica.",
            "error",
        )
        return redirect(url_for("clinicas_list"))
    ch.command(
        f"ALTER TABLE diabetcare.dim_clinica DELETE WHERE id_clinica = {id_clinica}"
    )
    flash("Clínica eliminada.", "success")
    return redirect(url_for("clinicas_list"))


# ─────────────────────────────────────────
# CRUD - MÉDICOS
# ─────────────────────────────────────────


@app.route("/medicos")
@login_required
@role_required("admin")
def medicos_list():
    ch = get_ch_client()
    clinicas_rows = ch.query(
        "SELECT id_clinica, nombre, ciudad FROM diabetcare.dim_clinica ORDER BY id_clinica"
    ).result_rows
    clinicas = [{"id": r[0], "nombre": r[1], "ciudad": r[2]} for r in clinicas_rows]
    rows = ch.query("""
        SELECT m.id_medico, m.nombre, m.especialidad, m.id_clinica,
               COUNT(dc.id_paciente) AS pacientes
        FROM diabetcare.dim_medico m
        LEFT JOIN diabetcare.diabetes_clinical dc ON m.id_medico = dc.id_medico
        GROUP BY m.id_medico, m.nombre, m.especialidad, m.id_clinica
        ORDER BY m.id_medico
    """).result_rows
    medicos = [
        {
            "id": r[0],
            "nombre": r[1],
            "especialidad": r[2],
            "id_clinica": r[3],
            "pacientes": r[4],
        }
        for r in rows
    ]
    return render_template("medicos.html", medicos=medicos, clinicas=clinicas)


@app.route("/medicos/crear", methods=["POST"])
@login_required
@role_required("admin")
def medicos_crear():
    ch = get_ch_client()
    nombre = request.form.get("nombre", "").strip()
    especialidad = request.form.get("especialidad", "").strip()
    id_clinica = int(request.form.get("id_clinica", 0))
    if not nombre or not especialidad or not id_clinica:
        flash("Todos los campos son obligatorios.", "error")
        return redirect(url_for("medicos_list"))
    max_id = ch.query("SELECT MAX(id_medico) FROM diabetcare.dim_medico").result_rows[0][0]
    nuevo_id = (max_id or 0) + 1
    ch.insert(
        "diabetcare.dim_medico",
        [[nuevo_id, nombre, especialidad, id_clinica]],
        column_names=["id_medico", "nombre", "especialidad", "id_clinica"],
    )
    flash(f"Médico «{nombre}» creado correctamente.", "success")
    return redirect(url_for("medicos_list"))


@app.route("/medicos/editar/<int:id_medico>", methods=["POST"])
@login_required
@role_required("admin")
def medicos_editar(id_medico):
    ch = get_ch_client()
    nombre = request.form.get("nombre", "").strip()
    especialidad = request.form.get("especialidad", "").strip()
    id_clinica = int(request.form.get("id_clinica", 0))
    if not nombre or not especialidad or not id_clinica:
        flash("Todos los campos son obligatorios.", "error")
        return redirect(url_for("medicos_list"))
    ch.command(
        f"ALTER TABLE diabetcare.dim_medico UPDATE "
        f"nombre = '{esc_ch(nombre)}', especialidad = '{esc_ch(especialidad)}', "
        f"id_clinica = {id_clinica} "
        f"WHERE id_medico = {id_medico}"
    )
    flash("Médico actualizado.", "success")
    return redirect(url_for("medicos_list"))


@app.route("/medicos/eliminar/<int:id_medico>", methods=["POST"])
@login_required
@role_required("admin")
def medicos_eliminar(id_medico):
    ch = get_ch_client()
    count = ch.query(
        f"SELECT COUNT(*) FROM diabetcare.diabetes_clinical "
        f"WHERE id_medico = {id_medico}"
    ).result_rows[0][0]
    if count > 0:
        flash(
            f"No se puede eliminar: hay {count:,} pacientes asignados a este médico.",
            "error",
        )
        return redirect(url_for("medicos_list"))
    ch.command(
        f"ALTER TABLE diabetcare.dim_medico DELETE WHERE id_medico = {id_medico}"
    )
    flash("Médico eliminado.", "success")
    return redirect(url_for("medicos_list"))


# ─────────────────────────────────────────
# ANÁLISIS DE PACIENTES
# ─────────────────────────────────────────


def _glucose_status(value):
    if value < 100:
        return "normal", "Normal"
    if value < 126:
        return "warning", "Prediabetes"
    if value < 200:
        return "danger", "Diabetes"
    return "critical", "Crítico"


def _hba1c_status(value):
    if value < 5.7:
        return "normal", "Normal"
    if value < 6.5:
        return "warning", "Prediabetes"
    return "danger", "Diabetes"


def _bmi_status(value):
    if value < 18.5:
        return "warning", "Bajo peso"
    if value < 25:
        return "normal", "Normal"
    if value < 30:
        return "warning", "Sobrepeso"
    return "danger", "Obesidad"


@app.route("/analisis")
@login_required
@role_required("admin", "medico", "analista")
def analisis_paciente():
    ch = get_ch_client()
    cf = clinic_filter_clause(current_user.rol, current_user.id_clinica, "dc")
    paciente_id = request.args.get("paciente", "").strip()
    paciente = None
    poblacion = {}
    alertas = []
    chart_compare = {}

    poblacion_rows = ch.query(f"""
        SELECT
            round(avg(dc.bmi), 2),
            round(avg(dc.hba1c_level), 2),
            round(avg(dc.blood_glucose_level), 0),
            round(avg(dc.age), 1),
            round(avg(dc.diabetes) * 100, 1)
        FROM diabetcare.diabetes_clinical dc
        WHERE 1=1{cf}
    """).result_rows[0]
    poblacion = {
        "bmi": float(poblacion_rows[0] or 0),
        "hba1c": float(poblacion_rows[1] or 0),
        "glucosa": float(poblacion_rows[2] or 0),
        "edad": float(poblacion_rows[3] or 0),
        "pct_diabetes": float(poblacion_rows[4] or 0),
    }

    sugerencias = ch.query(f"""
        SELECT dc.id_paciente, g.genero, dc.age, dc.blood_glucose_level
        FROM diabetcare.diabetes_clinical dc
        JOIN diabetcare.dim_genero g ON dc.id_genero = g.id_genero
        WHERE 1=1{cf}
        ORDER BY dc.id_paciente DESC
        LIMIT 30
    """).result_rows

    dropdown_options = _get_dropdown_options(ch)

    if paciente_id:
        try:
            pid = int(paciente_id)
        except ValueError:
            flash("Ingresa un ID de paciente válido (número entero).", "error")
            return render_template(
                "analisis.html",
                paciente=None,
                poblacion=poblacion,
                alertas=[],
                chart_compare={},
                sugerencias=sugerencias,
                paciente_id=paciente_id,
                dropdown_options=dropdown_options,
            )

        rows = ch.query(f"""
            SELECT
                dc.id_paciente, g.genero, u.ubicacion, rz.raza,
                r.descripcion, dc.age, dc.bmi, dc.hba1c_level,
                dc.blood_glucose_level, dc.hypertension, dc.heart_disease,
                dc.diabetes, c.nombre, m.nombre, t.tipo, f.historial,
                dc.year, dc.id_clinica
            FROM diabetcare.diabetes_clinical dc
            JOIN diabetcare.dim_genero g ON dc.id_genero = g.id_genero
            JOIN diabetcare.dim_ubicacion u ON dc.id_ubicacion = u.id_ubicacion
            JOIN diabetcare.dim_raza rz ON dc.id_raza = rz.id_raza
            JOIN diabetcare.dim_rango_edad r ON dc.id_rango_edad = r.id_rango
            JOIN diabetcare.dim_clinica c ON dc.id_clinica = c.id_clinica
            JOIN diabetcare.dim_medico m ON dc.id_medico = m.id_medico
            JOIN diabetcare.dim_tipo_diabetes t ON dc.id_tipo_diabetes = t.id_tipo
            JOIN diabetcare.dim_fumado f ON dc.id_fumado = f.id_fumado
            WHERE dc.id_paciente = {pid}{cf}
        """).result_rows

        if not rows:
            flash(f"No se encontró el paciente #{pid} o no tienes acceso.", "error")
        else:
            r = rows[0]
            gluc_status, gluc_label = _glucose_status(r[8])
            hba_status, hba_label = _hba1c_status(r[7])
            bmi_status, bmi_label = _bmi_status(r[6])

            if r[8] >= 200:
                alertas.append(("critical", "Glucosa crítica", f"Nivel de {r[8]} mg/dL — requiere atención inmediata."))
            elif r[8] >= 126:
                alertas.append(("danger", "Glucosa elevada", f"Nivel de {r[8]} mg/dL — por encima del rango diabético."))
            if r[7] >= 6.5:
                alertas.append(("danger", "HbA1c elevada", f"Valor de {r[7]}% — indica diabetes mal controlada."))
            if r[6] >= 30:
                alertas.append(("warning", "Obesidad", f"IMC de {r[6]} — factor de riesgo cardiovascular."))
            if r[9] == 1:
                alertas.append(("warning", "Hipertensión", "Paciente con diagnóstico de hipertensión arterial."))
            if r[10] == 1:
                alertas.append(("danger", "Enfermedad cardíaca", "Antecedente de enfermedad cardiovascular."))
            if not alertas:
                alertas.append(("normal", "Sin alertas críticas", "Indicadores dentro de rangos manejables."))

            paciente = {
                "id": r[0],
                "genero": r[1],
                "ubicacion": r[2],
                "raza": r[3],
                "rango_edad": r[4],
                "edad": r[5],
                "bmi": r[6],
                "hba1c": r[7],
                "glucosa": r[8],
                "hipertension": r[9],
                "heart_disease": r[10],
                "diabetes": r[11],
                "clinica": r[12],
                "medico": r[13],
                "tipo_diabetes": r[14],
                "fumado": r[15],
                "year": r[16],
                "gluc_status": gluc_status,
                "gluc_label": gluc_label,
                "hba_status": hba_status,
                "hba_label": hba_label,
                "bmi_status": bmi_status,
                "bmi_label": bmi_label,
            }
            chart_compare = {
                "labels": ["Glucosa", "HbA1c", "BMI", "Edad"],
                "paciente": [r[8], r[7], r[6], r[5]],
                "poblacion": [
                    poblacion["glucosa"],
                    poblacion["hba1c"],
                    poblacion["bmi"],
                    poblacion["edad"],
                ],
            }

    return render_template(
        "analisis.html",
        paciente=paciente,
        poblacion=poblacion,
        alertas=alertas,
        chart_compare=chart_compare,
        sugerencias=sugerencias,
        paciente_id=paciente_id,
        dropdown_options=dropdown_options,
    )


@app.route("/analisis/buscar")
@login_required
@role_required("admin", "medico", "analista")
def analisis_buscar():
    """JSON: lista de pacientes con filtros (para modal de búsqueda)."""
    ch = get_ch_client()
    cf = clinic_filter_clause(current_user.rol, current_user.id_clinica)
    filters = {
        k: request.args.get(k)
        for k in ["gender", "diabetes", "hypertension", "smoking_history"]
    }
    id_q = request.args.get("q", "").strip()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1

    records, pagination = _query_pacientes(ch, filters, page, cf, id_q=id_q or None)

    return jsonify({
        "records": records,
        "pagination": {
            "page": pagination.page,
            "total_pages": pagination.total_pages,
            "total_records": pagination.total_records,
            "has_prev": pagination.has_prev,
            "has_next": pagination.has_next,
        },
    })

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, port=5000)
