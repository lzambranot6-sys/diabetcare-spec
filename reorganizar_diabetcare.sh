#!/usr/bin/env bash
# =============================================================================
# reorganizar_diabetcare.sh
# Reorganiza el proyecto DiabetCare en estructura por paquetes.
# Ejecutar desde la raíz del proyecto (donde está app.py).
# =============================================================================

set -euo pipefail

# --- Colores ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[--]${NC} $1"; }
fail() { echo -e "${RED}[!!]${NC} $1"; exit 1; }

# --- Verificar que estamos en la raíz correcta ---
if [[ ! -f "app.py" ]]; then
    fail "No se encontró app.py. Ejecuta este script desde la raíz del proyecto."
fi

echo ""
echo "====================================="
echo " Reorganizando DiabetCare..."
echo "====================================="
echo ""

# =============================================================================
# 1. Crear estructura de carpetas
# =============================================================================
warn "Creando estructura de carpetas..."

mkdir -p P1_dashboard/templates
mkdir -p P2_registros_clinicos/templates
mkdir -p P3_gestion_pacientes/templates
mkdir -p P4_dimensiones/templates
mkdir -p P5_pipeline_etl

log "Carpetas creadas."

# =============================================================================
# 2. Mover templates
# =============================================================================
warn "Moviendo templates..."

# index.html → P1_dashboard
if [[ -f "templates/index.html" ]]; then
    mv templates/index.html P1_dashboard/templates/index.html
    log "index.html → P1_dashboard/templates/"
else
    warn "templates/index.html no encontrado, se omite."
fi

# registros.html → P2_registros_clinicos
if [[ -f "templates/registros.html" ]]; then
    mv templates/registros.html P2_registros_clinicos/templates/registros.html
    log "registros.html → P2_registros_clinicos/templates/"
else
    warn "templates/registros.html no encontrado, se omite."
fi

# pacientes.html + fact.html → P3_gestion_pacientes
for f in pacientes.html fact.html; do
    if [[ -f "templates/$f" ]]; then
        mv "templates/$f" "P3_gestion_pacientes/templates/$f"
        log "$f → P3_gestion_pacientes/templates/"
    else
        warn "templates/$f no encontrado, se omite."
    fi
done

# dimensiones.html → P4_dimensiones
if [[ -f "templates/dimensiones.html" ]]; then
    mv templates/dimensiones.html P4_dimensiones/templates/dimensiones.html
    log "dimensiones.html → P4_dimensiones/templates/"
else
    warn "templates/dimensiones.html no encontrado, se omite."
fi

# base.html se queda en templates/ (compartido)
if [[ -f "templates/base.html" ]]; then
    log "base.html permanece en templates/ (compartido)."
else
    warn "templates/base.html no encontrado."
fi

# =============================================================================
# 3. Mover scripts ETL → P5_pipeline_etl
# =============================================================================
warn "Moviendo scripts ETL..."

for script in pocketbase_extract.py clickhouse_load.py clickhouse_setup.py \
              clickhouse_dimensions.py generar_registros.py; do
    if [[ -f "$script" ]]; then
        mv "$script" "P5_pipeline_etl/$script"
        log "$script → P5_pipeline_etl/"
    else
        warn "$script no encontrado, se omite."
    fi
done

# =============================================================================
# 4. Parchear app.py
# =============================================================================
warn "Parcheando app.py..."

# Backup
cp app.py app.py.bak
log "Backup guardado en app.py.bak"

# Insertar ChoiceLoader después de "app = Flask(__name__)"
python3 - <<'PYEOF'
import re

with open("app.py", "r") as f:
    content = f.read()

# 1. Agregar import de ChoiceLoader y FileSystemLoader al bloque de imports de flask
content = content.replace(
    "from flask import Flask, jsonify, render_template, request, redirect",
    "from flask import Flask, jsonify, render_template, request, redirect\nfrom jinja2 import ChoiceLoader, FileSystemLoader"
)

# 2. Agregar configuración de ChoiceLoader después de "app = Flask(__name__)"
loader_block = '''

# Buscar templates en carpetas de cada paquete
app.jinja_loader = ChoiceLoader([
    FileSystemLoader(os.path.join(app.root_path, "templates")),
    FileSystemLoader(os.path.join(app.root_path, "P1_dashboard", "templates")),
    FileSystemLoader(os.path.join(app.root_path, "P2_registros_clinicos", "templates")),
    FileSystemLoader(os.path.join(app.root_path, "P3_gestion_pacientes", "templates")),
    FileSystemLoader(os.path.join(app.root_path, "P4_dimensiones", "templates")),
])'''

content = content.replace(
    "app = Flask(__name__)",
    "app = Flask(__name__)" + loader_block
)

# 3. Parchear subprocess.Popen para generar_registros.py
content = content.replace(
    "subprocess.Popen([sys.executable, 'generar_registros.py', str(cantidad)])",
    "subprocess.Popen([sys.executable, os.path.join(os.path.dirname(__file__), 'P5_pipeline_etl', 'generar_registros.py'), str(cantidad)])"
)

with open("app.py", "w") as f:
    f.write(content)

print("app.py parcheado correctamente.")
PYEOF

log "app.py parcheado."

# =============================================================================
# 5. Resumen final
# =============================================================================
echo ""
echo "====================================="
echo " ¡Listo! Estructura final:"
echo "====================================="
echo ""
tree -I '__pycache__|.venv|.pytest_cache|node_modules' --dirsfirst 2>/dev/null \
    || find . -not -path './.git/*' -not -path './__pycache__/*' \
              -not -path './.venv/*' -not -name '*.pyc' \
       | sort | head -60
echo ""
echo -e "${GREEN}Todo reorganizado. Ejecuta 'python app.py' para verificar.${NC}"
echo -e "${YELLOW}Si algo falla, restaura el backup: cp app.py.bak app.py${NC}"
echo ""
