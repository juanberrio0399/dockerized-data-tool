"""Tiny data tool: reads a CSV and prints a quick summary.
Runs the same everywhere thanks to Docker."""
import sys
import pandas as pd

def main(path: str) -> None:
    df = pd.read_csv(path)
    print(f"File: {path}")
    print(f"Rows: {len(df):,}  |  Columns: {len(df.columns)}")
    print("Columns:", ", ".join(df.columns))
    print("\nNumeric summary:")
    print(df.describe(include="number"))

if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "sample.csv"
    main(csv_path)
