"""Tiny data tool: reads a CSV and prints a quick summary.
Runs the same everywhere thanks to Docker."""
import sys
import pandas as pd
import pandera as pa
from pandera import Column, DataFrameSchema, Check

schema = DataFrameSchema({
    "value": Column(float, Check.ge(0), nullable=False),
}, coerce=True)

def load_data(filepath):
    try:
        df = pd.read_csv(filepath)
        return schema.validate(df)
    except pa.errors.SchemaErrors as e:
        raise ValueError(f"Error de validación en el esquema del CSV: {e}")

def main(path: str) -> None:
    df = load_data(path)
    print(f"File: {path}")
    print(f"Rows: {len(df):,}  |  Columns: {len(df.columns)}")
    print("Columns:", ", ".join(df.columns))
    print("\nNumeric summary:")
    print(df.describe(include="number"))

if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "sample.csv"
    main(csv_path)
