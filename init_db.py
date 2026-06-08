"""
init_db.py — DB_Initializer for DiabetCare S.A.

Creates all 11 PostgreSQL tables idempotently.
Usage: python init_db.py
"""

import sys

import psycopg2

from config import DB_CONFIG

# ---------------------------------------------------------------------------
# DDL definitions
# ---------------------------------------------------------------------------

TABLE_DEFINITIONS = {
    "diabetes_clinical": """
        CREATE TABLE IF NOT EXISTS diabetes_clinical (
            id_paciente           SERIAL PRIMARY KEY,
            year                  INTEGER,
            gender                VARCHAR(10),
            age                   NUMERIC(5,2),
            location              VARCHAR(100),
            race_african_american SMALLINT,
            race_asian            SMALLINT,
            race_caucasian        SMALLINT,
            race_hispanic         SMALLINT,
            race_other            SMALLINT,
            hypertension          SMALLINT,
            heart_disease         SMALLINT,
            smoking_history       VARCHAR(20),
            bmi                   NUMERIC(6,2),
            hba1c_level           NUMERIC(5,2),
            blood_glucose_level   INTEGER,
            diabetes              SMALLINT
        )
    """,
    "clinicas": """
        CREATE TABLE IF NOT EXISTS clinicas (
            id_clinica SERIAL PRIMARY KEY
        )
    """,
    "medicos": """
        CREATE TABLE IF NOT EXISTS medicos (
            id_medico SERIAL PRIMARY KEY
        )
    """,
    "empleados": """
        CREATE TABLE IF NOT EXISTS empleados (
            id_empleado SERIAL PRIMARY KEY
        )
    """,
    "pacientes_registrados": """
        CREATE TABLE IF NOT EXISTS pacientes_registrados (
            id_paciente_reg SERIAL PRIMARY KEY
        )
    """,
    "consultas": """
        CREATE TABLE IF NOT EXISTS consultas (
            id_consulta SERIAL PRIMARY KEY
        )
    """,
    "medicamentos": """
        CREATE TABLE IF NOT EXISTS medicamentos (
            id_medicamento SERIAL PRIMARY KEY
        )
    """,
    "recetas": """
        CREATE TABLE IF NOT EXISTS recetas (
            id_receta SERIAL PRIMARY KEY
        )
    """,
    "equipos_medicos": """
        CREATE TABLE IF NOT EXISTS equipos_medicos (
            id_equipo SERIAL PRIMARY KEY
        )
    """,
    "alertas": """
        CREATE TABLE IF NOT EXISTS alertas (
            id_alerta SERIAL PRIMARY KEY
        )
    """,
    "seguimientos": """
        CREATE TABLE IF NOT EXISTS seguimientos (
            id_seguimiento SERIAL PRIMARY KEY
        )
    """,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def table_exists(conn, table_name: str) -> bool:
    """Return True if *table_name* exists in the current database."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = %s
            """,
            (table_name,),
        )
        return cur.fetchone() is not None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        conn = psycopg2.connect(**DB_CONFIG)
    except psycopg2.OperationalError as e:
        print(f"Error de conexión a {DB_CONFIG['host']}:{DB_CONFIG['port']} — {e}")
        sys.exit(1)

    created = 0
    for table_name, ddl in TABLE_DEFINITIONS.items():
        if not table_exists(conn, table_name):
            try:
                with conn.cursor() as cur:
                    cur.execute(ddl)
                created += 1
            except psycopg2.Error as e:
                conn.rollback()
                print(f"Error creando tabla '{table_name}': {e}")
                sys.exit(1)

    conn.commit()
    print(f"Tablas creadas: {created}")


if __name__ == "__main__":
    main()
