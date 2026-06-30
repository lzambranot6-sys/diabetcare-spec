"""Crea la tabla dim_usuario y usuarios demo para login con roles."""

import clickhouse_connect
from werkzeug.security import generate_password_hash

USUARIOS = [
    (1, "admin", "admin123", "admin", "Administrador del Sistema", 0),
    (2, "medico", "medico123", "medico", "Dr. Carlos Pérez", 1),
    (3, "analista", "analista123", "analista", "Analista de Datos", 0),
]


def get_client():
    return clickhouse_connect.get_client(
        host="localhost",
        port=8123,
        username="default",
        password="admin123",
    )


def crear_usuarios(client=None):
    client = client or get_client()
    print("🔐 Configurando tabla dim_usuario...")

    client.command("DROP TABLE IF EXISTS diabetcare.dim_usuario")
    client.command("""
        CREATE TABLE diabetcare.dim_usuario (
            id_usuario     UInt8,
            username       String,
            password_hash  String,
            rol            String,
            nombre         String,
            id_clinica     UInt8
        ) ENGINE = MergeTree()
        ORDER BY id_usuario
    """)

    rows = [
        [
            uid,
            username,
            generate_password_hash(password),
            rol,
            nombre,
            id_clinica,
        ]
        for uid, username, password, rol, nombre, id_clinica in USUARIOS
    ]

    client.insert(
        "diabetcare.dim_usuario",
        rows,
        column_names=[
            "id_usuario",
            "username",
            "password_hash",
            "rol",
            "nombre",
            "id_clinica",
        ],
    )

    print("✅ dim_usuario creada con 3 usuarios demo:")
    print("   admin / admin123      → administrador")
    print("   medico / medico123    → médico (Clínica Central, id=1)")
    print("   analista / analista123 → analista (solo lectura)")


def main():
    crear_usuarios()


if __name__ == "__main__":
    main()
