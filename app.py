"""Tiny data tool: reads a CSV and prints a quick summary.
Runs the same everywhere thanks to Docker."""
import sys
import io
from typing import Union
import pandas as pd

def main(source: Union[str, io.BytesIO]) -> None:
    df = pd.read_csv(source)
    source_name = source if isinstance(source, str) else "memory buffer"
    print(f"File: {source_name}")
    print(f"Rows: {len(df):,}  |  Columns: {len(df.columns)}")
    print("Columns:", ", ".join(df.columns))
    print("\nNumeric summary:")
    print(df.describe(include="number"))

if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "sample.csv"
    main(csv_path)
