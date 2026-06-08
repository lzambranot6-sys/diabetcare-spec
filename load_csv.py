"""
load_csv.py — CSV_Loader for DiabetCare S.A.

Reads dataset/diabetes_dataset.csv with pandas and loads its records into
the diabetes_clinical table in batches of 1,000 rows.

Usage: python load_csv.py
"""

import sys
from pathlib import Path

import pandas as pd
import psycopg2

from config import DB_CONFIG

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CSV_PATH = Path("dataset") / "diabetes_dataset.csv"

BATCH_SIZE = 1000

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

# Ordered list of table columns (matches INSERT statement placeholder order)
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
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # 1. Verify CSV exists
    if not CSV_PATH.exists():
        print(CSV_PATH)
        sys.exit(1)

    # 2. Read and rename columns
    df = pd.read_csv(CSV_PATH)
    df = df.rename(columns=COLUMN_MAPPING)

    # 3. Build list of row tuples in column order (no rounding)
    records = df[TABLE_COLUMNS].to_dict("records")
    rows = [tuple(row[col] for col in TABLE_COLUMNS) for row in records]

    total = len(rows)

    # 4. Connect and load
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            # Open transaction: truncate first
            cur.execute("TRUNCATE diabetes_clinical RESTART IDENTITY")

            # Insert in batches of BATCH_SIZE
            for start in range(0, total, BATCH_SIZE):
                batch = rows[start : start + BATCH_SIZE]
                try:
                    cur.executemany(INSERT_SQL, batch)
                except psycopg2.Error as e:
                    conn.rollback()
                    print(e)
                    sys.exit(1)

        conn.commit()
        print(f"Registros insertados: {total}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
