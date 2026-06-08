import clickhouse_connect
import pandas as pd
import numpy as np
import random

client = clickhouse_connect.get_client(
    host='localhost', port=8123,
    username='default', password='admin123'
)

def crear_dimensiones():
    print("📐 Creando dimensiones...")

    # DIM GENERO (ya existe, recreamos)
    client.command("DROP TABLE IF EXISTS diabetcare.dim_genero")
    client.command("""
        CREATE TABLE diabetcare.dim_genero (
            id_genero UInt8,
            genero    String
        ) ENGINE = MergeTree() ORDER BY id_genero
    """)
    client.insert("diabetcare.dim_genero",
        [[1,"Male"],[2,"Female"]],
        column_names=["id_genero","genero"])
    print("✅ dim_genero")

    # DIM UBICACION (ya existe, recreamos)
    client.command("DROP TABLE IF EXISTS diabetcare.dim_ubicacion")
    client.command("""
        CREATE TABLE diabetcare.dim_ubicacion (
            id_ubicacion UInt16,
            ubicacion    String
        ) ENGINE = MergeTree() ORDER BY id_ubicacion
    """)
    df = pd.read_parquet("dataset/diabetes.parquet")
    ubicaciones = sorted(df["location"].dropna().unique().tolist())
    rows = [[i+1, u] for i, u in enumerate(ubicaciones)]
    client.insert("diabetcare.dim_ubicacion", rows, column_names=["id_ubicacion","ubicacion"])
    print("✅ dim_ubicacion")

    # DIM FUMADO (ya existe, recreamos)
    client.command("DROP TABLE IF EXISTS diabetcare.dim_fumado")
    client.command("""
        CREATE TABLE diabetcare.dim_fumado (
            id_fumado UInt8,
            historial String
        ) ENGINE = MergeTree() ORDER BY id_fumado
    """)
    fumados = sorted(df["smoking_history"].dropna().unique().tolist())
    rows = [[i+1, f] for i, f in enumerate(fumados)]
    client.insert("diabetcare.dim_fumado", rows, column_names=["id_fumado","historial"])
    print("✅ dim_fumado")

    # DIM RANGO EDAD (ya existe, recreamos)
    client.command("DROP TABLE IF EXISTS diabetcare.dim_rango_edad")
    client.command("""
        CREATE TABLE diabetcare.dim_rango_edad (
            id_rango    UInt8,
            descripcion String,
            edad_min    UInt8,
            edad_max    UInt8
        ) ENGINE = MergeTree() ORDER BY id_rango
    """)
    client.insert("diabetcare.dim_rango_edad",
        [[1,"Niño/Adolescente",0,17],[2,"Adulto Joven",18,35],
         [3,"Adulto",36,59],[4,"Adulto Mayor",60,120]],
        column_names=["id_rango","descripcion","edad_min","edad_max"])
    print("✅ dim_rango_edad")

    # DIM RAZA
    client.command("DROP TABLE IF EXISTS diabetcare.dim_raza")
    client.command("""
        CREATE TABLE diabetcare.dim_raza (
            id_raza UInt8,
            raza    String
        ) ENGINE = MergeTree() ORDER BY id_raza
    """)
    client.insert("diabetcare.dim_raza",
        [[1,"African American"],[2,"Asian"],[3,"Caucasian"],
         [4,"Hispanic"],[5,"Other"]],
        column_names=["id_raza","raza"])
    print("✅ dim_raza")

    # DIM AÑO
    client.command("DROP TABLE IF EXISTS diabetcare.dim_anio")
    client.command("""
        CREATE TABLE diabetcare.dim_anio (
            id_anio UInt16,
            anio    Int32
        ) ENGINE = MergeTree() ORDER BY id_anio
    """)
    anios = sorted(df["year"].dropna().unique().tolist())
    rows = [[i+1, int(a)] for i, a in enumerate(anios)]
    client.insert("diabetcare.dim_anio", rows, column_names=["id_anio","anio"])
    print("✅ dim_anio")

    # DIM NIVEL GLUCOSA
    client.command("DROP TABLE IF EXISTS diabetcare.dim_nivel_glucosa")
    client.command("""
        CREATE TABLE diabetcare.dim_nivel_glucosa (
            id_nivel    UInt8,
            descripcion String,
            valor_min   Int32,
            valor_max   Int32
        ) ENGINE = MergeTree() ORDER BY id_nivel
    """)
    client.insert("diabetcare.dim_nivel_glucosa",
        [[1,"Normal",0,99],[2,"Prediabetes",100,125],
         [3,"Diabetes",126,199],[4,"Diabetes Severa",200,999]],
        column_names=["id_nivel","descripcion","valor_min","valor_max"])
    print("✅ dim_nivel_glucosa")

    # DIM NIVEL BMI
    client.command("DROP TABLE IF EXISTS diabetcare.dim_nivel_bmi")
    client.command("""
        CREATE TABLE diabetcare.dim_nivel_bmi (
            id_nivel    UInt8,
            descripcion String,
            valor_min   Float64,
            valor_max   Float64
        ) ENGINE = MergeTree() ORDER BY id_nivel
    """)
    client.insert("diabetcare.dim_nivel_bmi",
        [[1,"Bajo Peso",0.0,18.4],[2,"Normal",18.5,24.9],
         [3,"Sobrepeso",25.0,29.9],[4,"Obesidad",30.0,999.0]],
        column_names=["id_nivel","descripcion","valor_min","valor_max"])
    print("✅ dim_nivel_bmi")

    # DIM NIVEL HBA1C
    client.command("DROP TABLE IF EXISTS diabetcare.dim_nivel_hba1c")
    client.command("""
        CREATE TABLE diabetcare.dim_nivel_hba1c (
            id_nivel    UInt8,
            descripcion String,
            valor_min   Float64,
            valor_max   Float64
        ) ENGINE = MergeTree() ORDER BY id_nivel
    """)
    client.insert("diabetcare.dim_nivel_hba1c",
        [[1,"Normal",0.0,5.6],[2,"Prediabetes",5.7,6.4],
         [3,"Diabetes",6.5,999.0]],
        column_names=["id_nivel","descripcion","valor_min","valor_max"])
    print("✅ dim_nivel_hba1c")

    # DIM CLINICA
    client.command("DROP TABLE IF EXISTS diabetcare.dim_clinica")
    client.command("""
        CREATE TABLE diabetcare.dim_clinica (
            id_clinica UInt8,
            nombre     String,
            ciudad     String
        ) ENGINE = MergeTree() ORDER BY id_clinica
    """)
    client.insert("diabetcare.dim_clinica",
        [[1,"Clínica Central DiabetCare","Guayaquil"],
         [2,"DiabetCare Norte","Quito"],
         [3,"DiabetCare Sur","Cuenca"],
         [4,"DiabetCare Oriente","Ambato"],
         [5,"DiabetCare Costa","Manta"]],
        column_names=["id_clinica","nombre","ciudad"])
    print("✅ dim_clinica")

    # DIM MEDICO
    client.command("DROP TABLE IF EXISTS diabetcare.dim_medico")
    client.command("""
        CREATE TABLE diabetcare.dim_medico (
            id_medico    UInt8,
            nombre       String,
            especialidad String,
            id_clinica   UInt8
        ) ENGINE = MergeTree() ORDER BY id_medico
    """)
    client.insert("diabetcare.dim_medico",
        [[1,"Dr. Carlos Pérez","Endocrinología",1],
         [2,"Dra. Ana Rodríguez","Medicina Interna",1],
         [3,"Dr. Luis Torres","Endocrinología",2],
         [4,"Dra. María Gómez","Medicina General",3],
         [5,"Dr. Jorge Herrera","Endocrinología",4],
         [6,"Dra. Patricia Vega","Medicina Interna",5]],
        column_names=["id_medico","nombre","especialidad","id_clinica"])
    print("✅ dim_medico")

    # DIM TIPO DIABETES
    client.command("DROP TABLE IF EXISTS diabetcare.dim_tipo_diabetes")
    client.command("""
        CREATE TABLE diabetcare.dim_tipo_diabetes (
            id_tipo     UInt8,
            tipo        String,
            descripcion String
        ) ENGINE = MergeTree() ORDER BY id_tipo
    """)
    client.insert("diabetcare.dim_tipo_diabetes",
        [[1,"Sin Diabetes","Paciente sin diagnóstico de diabetes"],
         [2,"Prediabetes","Niveles de glucosa elevados sin llegar a diabetes"],
         [3,"Diabetes Tipo 2","Forma más común, resistencia a la insulina"],
         [4,"Diabetes Tipo 1","Enfermedad autoinmune, falta de insulina"]],
        column_names=["id_tipo","tipo","descripcion"])
    print("✅ dim_tipo_diabetes")

    print("\n🎉 Todas las dimensiones creadas.")

def recrear_tabla_principal():
    print("\n📊 Recreando tabla principal diabetes_clinical...")

    client.command("DROP TABLE IF EXISTS diabetcare.diabetes_clinical")
    client.command("""
        CREATE TABLE diabetcare.diabetes_clinical (
            id_paciente         UInt32,
            id_genero           UInt8,
            id_ubicacion        UInt16,
            id_fumado           UInt8,
            id_rango_edad       UInt8,
            id_raza             UInt8,
            id_anio             UInt16,
            id_nivel_glucosa    UInt8,
            id_nivel_bmi        UInt8,
            id_nivel_hba1c      UInt8,
            id_clinica          UInt8,
            id_medico           UInt8,
            id_tipo_diabetes    UInt8,
            age                 Float64,
            bmi                 Float64,
            hba1c_level         Float64,
            blood_glucose_level Int32,
            hypertension        UInt8,
            heart_disease       UInt8,
            diabetes            UInt8,
            year                Int32
        ) ENGINE = MergeTree()
        ORDER BY id_paciente
    """)
    print("✅ Tabla diabetes_clinical recreada con 21 columnas.")

def cargar_datos_originales():
    print("\n⏳ Cargando 100k registros originales...")

    df = pd.read_parquet("dataset/diabetes.parquet")
    df = df.rename(columns={"race_africanamerican": "race_african_american"})

    # Mapeos
    genero_map = {"Male": 1, "Female": 2}
    ubicaciones = sorted(df["location"].dropna().unique().tolist())
    ubicacion_map = {u: i+1 for i, u in enumerate(ubicaciones)}
    fumados = sorted(df["smoking_history"].dropna().unique().tolist())
    fumado_map = {f: i+1 for i, f in enumerate(fumados)}
    anios = sorted(df["year"].dropna().unique().tolist())
    anio_map = {a: i+1 for i, a in enumerate(anios)}

    def get_rango(age):
        if age <= 17: return 1
        elif age <= 35: return 2
        elif age <= 59: return 3
        else: return 4

    def get_raza(row):
        if row.get("race_african_american", 0) == 1: return 1
        elif row.get("race_asian", 0) == 1: return 2
        elif row.get("race_caucasian", 0) == 1: return 3
        elif row.get("race_hispanic", 0) == 1: return 4
        else: return 5

    def get_nivel_glucosa(g):
        if g < 100: return 1
        elif g < 126: return 2
        elif g < 200: return 3
        else: return 4

    def get_nivel_bmi(b):
        if b < 18.5: return 1
        elif b < 25: return 2
        elif b < 30: return 3
        else: return 4

    def get_nivel_hba1c(h):
        if h < 5.7: return 1
        elif h < 6.5: return 2
        else: return 3

    def get_tipo_diabetes(row):
        if row["diabetes"] == 0:
            if row["hba1c_level"] >= 5.7 or row["blood_glucose_level"] >= 100:
                return 2
            return 1
        else:
            return 3

    df["id_paciente"] = range(1, len(df)+1)
    df["id_genero"] = df["gender"].map(genero_map).fillna(1).astype(int)
    df["id_ubicacion"] = df["location"].map(ubicacion_map).fillna(1).astype(int)
    df["id_fumado"] = df["smoking_history"].map(fumado_map).fillna(1).astype(int)
    df["id_rango_edad"] = df["age"].apply(get_rango)
    df["id_raza"] = df.apply(get_raza, axis=1)
    df["id_anio"] = df["year"].map(anio_map).fillna(1).astype(int)
    df["id_nivel_glucosa"] = df["blood_glucose_level"].apply(get_nivel_glucosa)
    df["id_nivel_bmi"] = df["bmi"].apply(get_nivel_bmi)
    df["id_nivel_hba1c"] = df["hba1c_level"].apply(get_nivel_hba1c)
    df["id_clinica"] = np.random.randint(1, 6, size=len(df))
    df["id_medico"] = np.random.randint(1, 7, size=len(df))
    df["id_tipo_diabetes"] = df.apply(get_tipo_diabetes, axis=1)

    cols = ["id_paciente","id_genero","id_ubicacion","id_fumado","id_rango_edad",
            "id_raza","id_anio","id_nivel_glucosa","id_nivel_bmi","id_nivel_hba1c",
            "id_clinica","id_medico","id_tipo_diabetes",
            "age","bmi","hba1c_level","blood_glucose_level",
            "hypertension","heart_disease","diabetes","year"]

    client.insert_df("diabetcare.diabetes_clinical", df[cols])
    print(f"✅ {len(df)} registros originales cargados.")

if __name__ == "__main__":
    crear_dimensiones()
    recrear_tabla_principal()
    cargar_datos_originales()