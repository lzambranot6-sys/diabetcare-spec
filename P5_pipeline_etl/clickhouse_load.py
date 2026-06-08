import pandas as pd
import clickhouse_connect

def cargar_a_clickhouse():
    print("🔌 Conectando a ClickHouse...")
    client = clickhouse_connect.get_client(host='localhost', port=8123, username='default', password='admin123')

    print("📂 Leyendo archivo parquet...")
    df = pd.read_parquet("dataset/diabetes.parquet")

    print(f"✅ {len(df)} registros leídos del parquet.")
    print("Columnas:", list(df.columns))

    # Crear tabla principal
    client.command("""
        CREATE TABLE IF NOT EXISTS diabetcare.diabetes_clinical (
            year        Int32,
            gender      String,
            age         Float64,
            location    String,
            race_african_american Int32,
            race_asian  Int32,
            race_caucasian Int32,
            race_hispanic Int32,
            race_other  Int32,
            hypertension Int32,
            heart_disease Int32,
            smoking_history String,
            bmi         Float64,
            hba1c_level Float64,
            blood_glucose_level Int32,
            diabetes    Int32
        ) ENGINE = MergeTree()
        ORDER BY (year, gender)
    """)
    print("✅ Tabla diabetes_clinical creada.")

    # Renombrar columnas si vienen del CSV original
    df.columns = df.columns.str.strip()
    rename_map = {
    "race:AfricanAmerican": "race_african_american",
    "race:Asian": "race_asian",
    "race:Caucasian": "race_caucasian",
    "race:Hispanic": "race_hispanic",
    "race:Other": "race_other",
    "hbA1c_level": "hba1c_level",
    "race_africanamerican": "race_african_american"
    }
    df = df.rename(columns=rename_map)

    # Insertar datos
    print("⏳ Insertando datos en ClickHouse...")
    client.insert_df("diabetcare.diabetes_clinical", df)
    print(f"🎉 {len(df)} registros insertados en ClickHouse.")

if __name__ == "__main__":
    cargar_a_clickhouse()