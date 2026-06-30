"""Autenticación con Flask-Login y usuarios en ClickHouse."""

from functools import wraps

from flask import flash, redirect, request, url_for
from flask_login import LoginManager, UserMixin, current_user
from werkzeug.security import check_password_hash

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = "Inicia sesión para acceder al sistema."


class User(UserMixin):
    def __init__(self, id_usuario, username, rol, nombre, id_clinica=0):
        self.id = str(id_usuario)
        self.id_usuario = id_usuario
        self.username = username
        self.rol = rol
        self.nombre = nombre
        self.id_clinica = id_clinica or 0

    @property
    def is_admin(self):
        return self.rol == "admin"

    @property
    def is_medico(self):
        return self.rol == "medico"

    @property
    def is_analista(self):
        return self.rol == "analista"


def load_user_from_db(ch, user_id):
    rows = ch.query(
        "SELECT id_usuario, username, password_hash, rol, nombre, id_clinica "
        "FROM diabetcare.dim_usuario WHERE id_usuario = {uid:UInt8}",
        parameters={"uid": int(user_id)},
    ).result_rows
    if not rows:
        return None
    r = rows[0]
    return User(r[0], r[1], r[3], r[4], r[5])


def authenticate(ch, username, password):
    rows = ch.query(
        "SELECT id_usuario, username, password_hash, rol, nombre, id_clinica "
        "FROM diabetcare.dim_usuario WHERE username = {user:String}",
        parameters={"user": username},
    ).result_rows
    if not rows:
        return None
    r = rows[0]
    if check_password_hash(r[2], password):
        return User(r[0], r[1], r[3], r[4], r[5])
    return None


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("login", next=request.url))
            if current_user.rol not in roles:
                flash("No tienes permiso para acceder a esta sección.", "error")
                return redirect(url_for("index"))
            return f(*args, **kwargs)

        return wrapped

    return decorator


def clinic_filter_clause(rol, id_clinica, alias="dc"):
    if rol == "medico" and id_clinica:
        return f" AND {alias}.id_clinica = {int(id_clinica)}"
    return ""


def esc_ch(value):
    """Escapa comillas simples para literales String en ClickHouse."""
    return str(value).replace("\\", "\\\\").replace("'", "''")
