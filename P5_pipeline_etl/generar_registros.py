import clickhouse_connect
import pandas as pd
import numpy as np
import sys

client = clickhouse_connect.get_client(
    host='localhost', port=8123,
    username='default', password='admin123'
)

def generar_registros(cantidad: int):
    print(f"🔄 Generando {cantidad:,} registros sintéticos...")

    # Cargar dimensiones
    generos = client.query("SELECT id_genero FROM diabetcare.dim_genero").result_rows
    ubicaciones = client.query("SELECT id_ubicacion FROM diabetcare.dim_ubicacion").result_rows
    fumados = client.query("SELECT id_fumado FROM diabetcare.dim_fumado").result_rows
    anios = client.query("SELECT id_anio FROM diabetcare.dim_anio").result_rows

    id_generos = [r[0] for r in generos]
    id_ubicaciones = [r[0] for r in ubicaciones]
    id_fumados = [r[0] for r in fumados]
    id_anios = [r[0] for r in anios]

    # Obtener el último id_paciente
    last_id = client.query("SELECT MAX(id_paciente) FROM diabetcare.diabetes_clinical").result_rows[0][0]
    start_id = (last_id or 0) + 1

    np.random.seed(42)

    # Generar columnas numéricas
    ages = np.round(np.random.uniform(1, 90, cantidad), 1)
    bmis = np.round(np.random.uniform(15, 60, cantidad), 2)
    hba1c = np.round(np.random.uniform(3.5, 12.0, cantidad), 1)
    glucosa = np.random.randint(60, 300, cantidad)
    hypertension = np.random.randint(0, 2, cantidad)
    heart_disease = np.random.randint(0, 2, cantidad)
    diabetes = np.where((hba1c >= 6.5) | (glucosa >= 126), 1, 0)
    years = np.random.choice([r[0] for r in client.query("SELECT anio FROM diabetcare.dim_anio").result_rows], cantidad)

    # Generar IDs de dimensiones
    id_genero_arr = np.random.choice(id_generos, cantidad)
    id_ubicacion_arr = np.random.choice(id_ubicaciones, cantidad)
    id_fumado_arr = np.random.choice(id_fumados, cantidad)
    id_rango_arr = np.where(ages <= 17, 1, np.where(ages <= 35, 2, np.where(ages <= 59, 3, 4)))
    id_raza_arr = np.random.randint(1, 6, cantidad)
    id_anio_arr = np.random.choice([r[0] for r in anios], cantidad)
    id_nivel_glucosa_arr = np.where(glucosa < 100, 1, np.where(glucosa < 126, 2, np.where(glucosa < 200, 3, 4)))
    id_nivel_bmi_arr = np.where(bmis < 18.5, 1, np.where(bmis < 25, 2, np.where(bmis < 30, 3, 4)))
    id_nivel_hba1c_arr = np.where(hba1c < 5.7, 1, np.where(hba1c < 6.5, 2, 3))
    id_clinica_arr = np.random.randint(1, 6, cantidad)
    id_medico_arr = np.random.randint(1, 7, cantidad)
    id_tipo_arr = np.where(diabetes == 0, np.where((hba1c >= 5.7) | (glucosa >= 100), 2, 1), 3)

    df = pd.DataFrame({
        "id_paciente": range(start_id, start_id + cantidad),
        "id_genero": id_genero_arr,
        "id_ubicacion": id_ubicacion_arr,
        "id_fumado": id_fumado_arr,
        "id_rango_edad": id_rango_arr,
        "id_raza": id_raza_arr,
        "id_anio": id_anio_arr,
        "id_nivel_glucosa": id_nivel_glucosa_arr,
        "id_nivel_bmi": id_nivel_bmi_arr,
        "id_nivel_hba1c": id_nivel_hba1c_arr,
        "id_clinica": id_clinica_arr,
        "id_medico": id_medico_arr,
        "id_tipo_diabetes": id_tipo_arr,
        "age": ages,
        "bmi": bmis,
        "hba1c_level": hba1c,
        "blood_glucose_level": glucosa.astype(int),
        "hypertension": hypertension.astype(int),
        "heart_disease": heart_disease.astype(int),
        "diabetes": diabetes.astype(int),
        "year": years.astype(int),
    })

    # Insertar en lotes
    batch = 10000
    for i in range(0, len(df), batch):
        client.insert_df("diabetcare.diabetes_clinical", df.iloc[i:i+batch])
        print(f"  → {min(i+batch, cantidad):,} / {cantidad:,} insertados...")

    total = client.query("SELECT COUNT(*) FROM diabetcare.diabetes_clinical").result_rows[0][0]
    print(f"✅ Listo. Total en diabetes_clinical: {total:,} registros.")

if __name__ == "__main__":
    cantidad = int(sys.argv[1]) if len(sys.argv) > 1 else 200000
    generar_registros(cantidad)