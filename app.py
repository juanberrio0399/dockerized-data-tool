"""Tiny data tool: reads a CSV and prints a quick summary.
Runs the same everywhere thanks to Docker."""
import sys
from pathlib import Path

import pandas as pd

EXIT_OK = 0
EXIT_BAD_DATA = 1  # the file exists but is not a readable CSV
EXIT_BAD_PATH = 2  # the path is missing, a directory, or not readable


def fail(message: str, code: int) -> int:
    print(f"Error: {message}", file=sys.stderr)
    return code


def main(path: str) -> int:
    file = Path(path)
    if not file.exists():
        return fail(f"file not found: {path}", EXIT_BAD_PATH)
    if not file.is_file():
        return fail(f"not a file: {path}", EXIT_BAD_PATH)

    try:
        df = pd.read_csv(file)
    except PermissionError:
        return fail(f"permission denied: {path}", EXIT_BAD_PATH)
    except pd.errors.EmptyDataError:
        return fail(f"the file is empty: {path}", EXIT_BAD_DATA)
    except (pd.errors.ParserError, UnicodeDecodeError) as exc:
        detail = (str(exc).splitlines() or [""])[0]
        return fail(f"could not parse {path} as CSV ({type(exc).__name__}: {detail})", EXIT_BAD_DATA)

    print(f"File: {path}")
    print(f"Rows: {len(df):,}  |  Columns: {len(df.columns)}")
    print("Columns:", ", ".join(map(str, df.columns)))

    if df.empty:
        print("\nNo data rows to summarize.")
        return EXIT_OK
    numeric = df.select_dtypes(include="number")
    if numeric.columns.empty:
        print("\nNo numeric columns to summarize.")
        return EXIT_OK

    print("\nNumeric summary:")
    print(numeric.describe())
    return EXIT_OK


if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "sample.csv"
    sys.exit(main(csv_path))
