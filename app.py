"""Tiny data tool: reads a CSV and prints a quick summary.
Runs the same everywhere thanks to Docker.

Optional schema contract (pandera):
  python app.py reference.csv --infer-schema schema.yaml   # write the contract from a reference file
  python app.py new.csv --schema schema.yaml               # stop before the summary if the file breaks it
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

EXIT_OK = 0
EXIT_BAD_DATA = 1  # the file exists but is not a readable CSV (or the schema file is invalid)
EXIT_BAD_PATH = 2  # the path is missing, a directory, or not readable
EXIT_SCHEMA = 3  # the CSV does not match the schema contract
MAX_EXAMPLES = 3


def fail(message: str, code: int) -> int:
    print(f"Error: {message}", file=sys.stderr)
    return code


def first_line(exc: Exception) -> str:
    return (str(exc).splitlines() or [""])[0]


def read_csv(path: str):
    """Returns (dataframe, EXIT_OK) or (None, exit code) after printing the error."""
    file = Path(path)
    if not file.exists():
        return None, fail(f"file not found: {path}", EXIT_BAD_PATH)
    if not file.is_file():
        return None, fail(f"not a file: {path}", EXIT_BAD_PATH)
    try:
        return pd.read_csv(file), EXIT_OK
    except PermissionError:
        return None, fail(f"permission denied: {path}", EXIT_BAD_PATH)
    except pd.errors.EmptyDataError:
        return None, fail(f"the file is empty: {path}", EXIT_BAD_DATA)
    except (pd.errors.ParserError, UnicodeDecodeError) as exc:
        return None, fail(f"could not parse {path} as CSV ({type(exc).__name__}: {first_line(exc)})", EXIT_BAD_DATA)


def summarize(path: str, df: pd.DataFrame) -> int:
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


# ---------- Schema contracts (pandera is only imported when an option needs it) ----------

def write_schema(df: pd.DataFrame, target: str) -> int:
    """Structural contract only: columns, types and whether empty values are allowed.

    pandera's infer_schema also turns the reference file's min/max into checks, which would reject
    almost any new valid file; those ranges are dropped. Business rules can be added to the YAML by hand.
    """
    import pandera.pandas as pa

    inferred = pa.infer_schema(df)
    columns = {
        name: pa.Column(column.dtype, nullable=bool(df[name].isna().any()), coerce=True, name=name)
        for name, column in inferred.columns.items()
    }
    contract = pa.DataFrameSchema(columns, coerce=True, strict=False)
    try:
        Path(target).write_text(contract.to_yaml(), encoding="utf-8")
    except OSError as exc:
        return fail(f"could not write schema {target} ({first_line(exc)})", EXIT_BAD_PATH)
    print(f"Schema written: {target} ({len(columns)} columns)")
    return EXIT_OK


def load_schema(path: str):
    file = Path(path)
    if not file.is_file():
        return None, fail(f"schema file not found: {path}", EXIT_BAD_PATH)
    import pandera.pandas as pa

    try:
        return pa.DataFrameSchema.from_yaml(file.read_text(encoding="utf-8")), EXIT_OK
    except Exception as exc:  # YAML syntax, unknown keys or bad types all come from different libraries
        return None, fail(f"invalid schema {path} ({type(exc).__name__}: {first_line(exc)})", EXIT_BAD_DATA)


def describe_failures(failure_cases: pd.DataFrame) -> list[str]:
    """Turns pandera's failure table into one readable line per problem."""
    rows = list(failure_cases.itertuples(index=False))
    is_type_check = lambda check: check.startswith(("dtype(", "coerce_dtype("))  # noqa: E731
    type_failed = {r.column for r in rows if is_type_check(str(r.check)) and not pd.isna(r.failure_case)}

    lines: list[str] = []
    grouped: dict[tuple[str, str], list[str]] = {}
    for r in rows:
        check, column, value = str(r.check), r.column, r.failure_case
        if check == "column_in_dataframe":
            lines.append(f"missing column '{value}'")
            continue
        if check == "column_in_schema":
            lines.append(f"unexpected column '{value}'")
            continue
        where = "" if pd.isna(r.index) else f" (line {int(r.index) + 2})"
        if check == "not_nullable":
            key, example = "empty values on", where.strip(" ()")
        elif is_type_check(check):
            if pd.isna(value):
                continue  # empty cells are reported by not_nullable
            key, example = f"expected {check[check.index('(') + 1:-1].strip(chr(39))} values, found", f"'{value}'{where}"
        else:
            if column in type_failed or str(value).startswith(("TypeError", "ValueError")):
                continue  # knock-on effect of a wrong type already reported
            key, example = f"check {check} failed for", f"{value!r}{where}"
        examples = grouped.setdefault((str(column), key), [])
        if example and example not in examples:
            examples.append(example)

    for (column, key), examples in grouped.items():
        shown = ", ".join(examples[:MAX_EXAMPLES])
        extra = f" and {len(examples) - MAX_EXAMPLES} more" if len(examples) > MAX_EXAMPLES else ""
        lines.append(f"column '{column}': {key} {shown}{extra}".rstrip())
    return lines


def check_schema(df: pd.DataFrame, schema) -> int:
    import pandera.errors as pe

    try:
        schema.validate(df, lazy=True)
    except pe.SchemaErrors as exc:
        for line in describe_failures(exc.failure_cases):
            print(f"Error: {line}", file=sys.stderr)
        return EXIT_SCHEMA
    return EXIT_OK


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read a CSV and print a quick summary.")
    parser.add_argument("csv", nargs="?", default="sample.csv", help="CSV file (default: sample.csv)")
    contract = parser.add_mutually_exclusive_group()
    contract.add_argument("--schema", metavar="FILE", help="validate the CSV against a YAML schema before the summary")
    contract.add_argument("--infer-schema", metavar="FILE", help="write a YAML schema (columns, types, empty values) from this CSV")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    if isinstance(argv, str):
        argv = [argv]
    args = parse_args(sys.argv[1:] if argv is None else argv)

    df, code = read_csv(args.csv)
    if df is None:
        return code
    if args.infer_schema:
        return write_schema(df, args.infer_schema)
    if args.schema:
        schema, code = load_schema(args.schema)
        if schema is None:
            return code
        code = check_schema(df, schema)
        if code != EXIT_OK:
            return code
        print(f"Schema: OK ({args.schema})")
    return summarize(args.csv, df)


if __name__ == "__main__":
    sys.exit(main())
