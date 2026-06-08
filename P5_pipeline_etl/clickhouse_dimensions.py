import pandas as pd
import clickhouse_connect

client = clickhouse_connect.get_client(
    host='localhost', port=8123,
    username='default', password='admin123'
)

def crear_dimensiones():
    print("📐 Creando tablas de dimensiones...")

    # DIM GENERO
    client.command("""
        CREATE TABLE IF NOT EXISTS diabetcare.dim_genero (
            id_genero   UInt8,
            genero      String
        ) ENGINE = MergeTree()
        ORDER BY id_genero
    """)
    client.command("TRUNCATE TABLE diabetcare.dim_genero")
    client.insert("diabetcare.dim_genero", [[1, "Male"], [2, "Female"]], column_names=["id_genero", "genero"])
    print("✅ dim_genero creada.")

    # DIM UBICACION
    df = pd.read_parquet("dataset/diabetes.parquet")
    ubicaciones = sorted(df["location"].dropna().unique().tolist())
    client.command("""
        CREATE TABLE IF NOT EXISTS diabetcare.dim_ubicacion (
            id_ubicacion UInt16,
            ubicacion    String
        ) ENGINE = MergeTree()
        ORDER BY id_ubicacion
    """)
    client.command("TRUNCATE TABLE diabetcare.dim_ubicacion")
    rows = [[i+1, u] for i, u in enumerate(ubicaciones)]
    client.insert("diabetcare.dim_ubicacion", rows, column_names=["id_ubicacion", "ubicacion"])
    print("✅ dim_ubicacion creada.")

    # DIM FUMADO
    fumados = sorted(df["smoking_history"].dropna().unique().tolist())
    client.command("""
        CREATE TABLE IF NOT EXISTS diabetcare.dim_fumado (
            id_fumado   UInt8,
            historial   String
        ) ENGINE = MergeTree()
        ORDER BY id_fumado
    """)
    client.command("TRUNCATE TABLE diabetcare.dim_fumado")
    rows = [[i+1, f] for i, f in enumerate(fumados)]
    client.insert("diabetcare.dim_fumado", rows, column_names=["id_fumado", "historial"])
    print("✅ dim_fumado creada.")

    # DIM RANGO EDAD
    client.command("""
        CREATE TABLE IF NOT EXISTS diabetcare.dim_rango_edad (
            id_rango    UInt8,
            descripcion String,
            edad_min    UInt8,
            edad_max    UInt8
        ) ENGINE = MergeTree()
        ORDER BY id_rango
    """)
    client.command("TRUNCATE TABLE diabetcare.dim_rango_edad")
    rangos = [
        [1, "Niño/Adolescente", 0, 17],
        [2, "Adulto Joven", 18, 35],
        [3, "Adulto", 36, 59],
        [4, "Adulto Mayor", 60, 120]
    ]
    client.insert("diabetcare.dim_rango_edad", rangos,
                  column_names=["id_rango", "descripcion", "edad_min", "edad_max"])
    print("✅ dim_rango_edad creada.")

def crear_fact_pacientes():
    print("📊 Creando tabla de hechos fact_pacientes...")

    client.command("""
        CREATE TABLE IF NOT EXISTS diabetcare.fact_pacientes (
            id_paciente         UInt32,
            id_genero           UInt8,
            id_ubicacion        UInt16,
            id_fumado           UInt8,
            id_rango_edad       UInt8,
            age                 Float64,
            bmi                 Float64,
            hba1c_level         Float64,
            blood_glucose_level Int32,
            hypertension        UInt8,
            heart_disease       UInt8,
            race_african_american UInt8,
            race_asian          UInt8,
            race_caucasian      UInt8,
            race_hispanic       UInt8,
            race_other          UInt8,
            diabetes            UInt8,
            year                Int32
        ) ENGINE = MergeTree()
        ORDER BY id_paciente
    """)
    client.command("TRUNCATE TABLE diabetcare.fact_pacientes")

    df = pd.read_parquet("dataset/diabetes.parquet")
    df = df.rename(columns={"race_africanamerican": "race_african_american"})

    # Mapeos
    genero_map = {"Male": 1, "Female": 2}

    ubicaciones = sorted(df["location"].dropna().unique().tolist())
    ubicacion_map = {u: i+1 for i, u in enumerate(ubicaciones)}

    fumados = sorted(df["smoking_history"].dropna().unique().tolist())
    fumado_map = {f: i+1 for i, f in enumerate(fumados)}

    def get_rango(age):
        if age <= 17: return 1
        elif age <= 35: return 2
        elif age <= 59: return 3
        else: return 4

    df["id_genero"] = df["gender"].map(genero_map).fillna(0).astype(int)
    df["id_ubicacion"] = df["location"].map(ubicacion_map).fillna(0).astype(int)
    df["id_fumado"] = df["smoking_history"].map(fumado_map).fillna(0).astype(int)
    df["id_rango_edad"] = df["age"].apply(get_rango)
    df["id_paciente"] = range(1, len(df)+1)

    cols = ["id_paciente", "id_genero", "id_ubicacion", "id_fumado", "id_rango_edad",
            "age", "bmi", "hba1c_level", "blood_glucose_level",
            "hypertension", "heart_disease",
            "race_african_american", "race_asian", "race_caucasian",
            "race_hispanic", "race_other", "diabetes", "year"]

    client.insert_df("diabetcare.fact_pacientes", df[cols])
    print(f"🎉 {len(df)} registros insertados en fact_pacientes.")

if __name__ == "__main__":
    crear_dimensiones()
    crear_fact_pacientes()