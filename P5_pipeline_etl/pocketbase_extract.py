import requests
import pandas as pd

POCKETBASE_URL = "http://127.0.0.1:8090"
COLLECTION = "pacientes"
ADMIN_EMAIL = "lzambranot6@uteq.edu.ec"      # cambia esto
ADMIN_PASSWORD = "12345Leo"         # cambia esto

def get_admin_token():
    url = f"{POCKETBASE_URL}/api/collections/_superusers/auth-with-password"
    response = requests.post(url, json={
        "identity": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    data = response.json()
    token = data.get("token")
    if not token:
        print(f"❌ Error autenticando: {data}")
        exit(1)
    print("🔑 Autenticado como admin.")
    return token

def extraer_desde_pocketbase(token):
    print("📦 Extrayendo datos desde PocketBase...")
    
    registros = []
    page = 1
    per_page = 500
    headers = {"Authorization": token}

    while True:
        url = f"{POCKETBASE_URL}/api/collections/{COLLECTION}/records"
        params = {"page": page, "perPage": per_page}
        response = requests.get(url, params=params, headers=headers)
        data = response.json()

        items = data.get("items", [])
        if not items:
            break

        registros.extend(items)
        print(f"  → Página {page} — {len(registros)} registros extraídos...")

        if len(registros) >= data.get("totalItems", 0):
            break

        page += 1

    df = pd.DataFrame(registros)
    
    cols_internas = ["id", "created", "updated", "collectionId", "collectionName"]
    df = df.drop(columns=[c for c in cols_internas if c in df.columns])

    print(f"✅ {len(df)} registros extraídos.")
    return df

def guardar_parquet(df, path="dataset/diabetes.parquet"):
    df.to_parquet(path, index=False)
    print(f"✅ Archivo parquet guardado en {path}")

if __name__ == "__main__":
    token = get_admin_token()
    df = extraer_desde_pocketbase(token)
    guardar_parquet(df)