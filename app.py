"""Tiny data tool: reads a CSV and prints a quick summary.
Runs the same everywhere thanks to Docker.

Optional schema contract (pandera):
  python app.py reference.csv --infer-schema schema.yaml   # write the contract from a reference file
  python app.py new.csv --schema schema.yaml               # stop before the summary if the file breaks it

Optional plain-language reading of the summary (Google Gemini, opt-in with --insights):
  GEMINI_API_KEY=... python app.py data.csv --insights

PRIVACY: --insights sends ONLY aggregate statistics (shape, column names, dtypes, null counts and the
numeric describe() table). The data rows never leave the machine, and nothing is sent at all unless
--insights is passed. --insights-anonymize also replaces the column names with placeholders.
"""

import argparse
import os
import sys
import time
from pathlib import Path

import pandas as pd

EXIT_OK = 0
EXIT_BAD_DATA = 1  # the file exists but is not a readable CSV (or the schema file is invalid)
EXIT_BAD_PATH = 2  # the path is missing, a directory, or not readable
EXIT_SCHEMA = 3  # the CSV does not match the schema contract
EXIT_INSIGHTS = 4  # --insights could not run (no key or API failure); the summary was already printed
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
            key, example = (
                f"expected {check[check.index('(') + 1 : -1].strip(chr(39))} values, found",
                f"'{value}'{where}",
            )
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


# ---------- AI insights (opt-in: nothing leaves the machine unless --insights is passed) ----------

# Model id verified on 2026-09-15 against Google's official docs:
#   https://ai.google.dev/gemini-api/docs/models   -> stable, no announced retirement
#   https://ai.google.dev/gemini-api/docs/pricing  -> "Free of charge" on the free tier
#   https://ai.google.dev/gemini-api/docs/thinking -> supports thinking_level "minimal"
# "gemini-1.5-flash" is retired and must not be used. This is the newest stable Flash that accepts
# thinking_level "minimal", which keeps a one-shot explanation fast and stops the reasoning tokens
# from eating max_output_tokens. To move to another model, change this constant only.
GEMINI_MODEL = "gemini-3.6-flash"
# Interactions API: the endpoint Google recommends for new development (generateContent still works).
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
GEMINI_TIMEOUT = 30  # seconds per attempt
GEMINI_MAX_CHARS = 6000  # hard cap: a very wide file cannot turn into an unbounded payload
GEMINI_RETRY_WAIT = 2  # seconds before the single retry on 429 / 5xx

GEMINI_SYSTEM_INSTRUCTION = (
    "You are a data analyst explaining a dataset to someone who does not read statistics. "
    "You receive aggregate statistics only, never the rows. In at most 120 words and at most 4 short "
    "bullets, say what the numbers suggest: scale, spread, skew, likely outliers, missing values and "
    "anything that looks like a data-quality problem. Never invent values and never claim to know what "
    "the individual rows contain."
)


def stats_payload(df: pd.DataFrame, anonymize: bool = False) -> str:
    """Builds the ONLY thing that is ever sent: aggregate statistics.

    Shape, column names, dtypes, null counts and the numeric describe() table. No cell of a data row is
    included: describe() is restricted to numeric columns, whose output is aggregates (count/mean/std/
    quantiles). Text columns are deliberately left out of describe(), because pandas would report their
    most frequent raw value in the `top` row — that would be real data leaving the machine.
    """
    frame = df
    if anonymize:
        frame = df.copy()
        frame.columns = [f"col_{i + 1}" for i in range(len(df.columns))]

    lines = [f"Rows: {len(frame)}", f"Columns: {len(frame.columns)}", "", "Column, dtype, empty values:"]
    lines += [
        f"- {name}: {dtype}, {int(empty)} empty"
        for name, dtype, empty in zip(frame.columns, frame.dtypes, frame.isna().sum(), strict=True)
    ]

    numeric = frame.select_dtypes(include="number")
    if numeric.columns.empty:
        lines += ["", "No numeric columns."]
    else:
        lines += ["", "Numeric summary (pandas describe):", numeric.describe().to_string()]
    return "\n".join(lines)[:GEMINI_MAX_CHARS]


def api_error(response) -> str:
    """Google's error message, trimmed to one line. The API key is never part of an error body."""
    try:
        message = str(response.json().get("error", {}).get("message", ""))
    except (ValueError, AttributeError):
        message = ""
    return (message.splitlines() or [""])[0][:200] or "no details"


def extract_text(response) -> str:
    """Pulls the answer out of an Interactions API response: steps -> model_output -> content -> text."""
    try:
        steps = response.json().get("steps", [])
    except (ValueError, AttributeError):
        return ""
    parts = [
        part.get("text", "")
        for step in steps
        if isinstance(step, dict) and step.get("type") == "model_output"
        for part in step.get("content", [])
        if isinstance(part, dict) and part.get("type") == "text"
    ]
    return "\n".join(part for part in parts if part).strip()


def call_gemini(api_key: str, stats: str):
    """Returns (text, None) or (None, error message).

    The key travels only in the request header, never in the URL, the body, the output or an error.
    One retry on 429 / 5xx; any other failure is reported as a message, never as a traceback.
    """
    import requests

    body = {
        "model": GEMINI_MODEL,
        "input": f"Aggregate statistics of a CSV file:\n\n{stats}",
        "system_instruction": GEMINI_SYSTEM_INSTRUCTION,
        "generation_config": {"temperature": 0.2, "max_output_tokens": 500, "thinking_level": "minimal"},
    }
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}

    for attempt in (1, 2):
        try:
            response = requests.post(GEMINI_URL, json=body, headers=headers, timeout=GEMINI_TIMEOUT)
        except requests.Timeout:
            return None, f"the Gemini API did not answer within {GEMINI_TIMEOUT}s"
        except requests.RequestException as exc:
            return None, f"could not reach the Gemini API ({type(exc).__name__})"

        if attempt == 1 and (response.status_code == 429 or response.status_code >= 500):
            time.sleep(GEMINI_RETRY_WAIT)  # rate limit or a bad minute on their side: try once more
            continue
        if response.status_code != 200:
            return None, f"the Gemini API answered HTTP {response.status_code} ({api_error(response)})"
        text = extract_text(response)
        return (text, None) if text else (None, "the Gemini API returned an empty answer")
    return None, "the Gemini API is unavailable"  # defensive: the loop above always returns


def explain(df: pd.DataFrame, anonymize: bool) -> int:
    """Sends the statistics to Gemini and prints the explanation. Never raises; the summary is already out."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return fail(
            "--insights needs a Gemini API key. Get a free one at https://aistudio.google.com/apikey and "
            "export it as GEMINI_API_KEY. The summary above is unaffected.",
            EXIT_INSIGHTS,
        )

    text, error = call_gemini(api_key, stats_payload(df, anonymize))
    if error:
        return fail(f"--insights failed: {error}", EXIT_INSIGHTS)

    # ASCII only: this line can land on a legacy Windows console that cannot encode an em dash.
    print(f"\nAI insights ({GEMINI_MODEL}) - only the statistics above were sent, never the rows:")
    print(text)
    return EXIT_OK


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read a CSV and print a quick summary.",
        epilog="Privacy: --insights sends only aggregate statistics to Google Gemini. The data rows never "
        "leave this machine, and nothing is sent unless you pass --insights.",
    )
    parser.add_argument("csv", nargs="?", default="sample.csv", help="CSV file (default: sample.csv)")
    contract = parser.add_mutually_exclusive_group()
    contract.add_argument("--schema", metavar="FILE", help="validate the CSV against a YAML schema before the summary")
    contract.add_argument(
        "--infer-schema", metavar="FILE", help="write a YAML schema (columns, types, empty values) from this CSV"
    )
    parser.add_argument(
        "--insights",
        action="store_true",
        help="explain the summary in plain language with Google Gemini. Sends ONLY the aggregate statistics "
        "(shape, column names, dtypes, null counts, numeric describe), never the data rows. Needs "
        "GEMINI_API_KEY in the environment; exits 4 if the key is missing or the API call fails.",
    )
    parser.add_argument(
        "--insights-anonymize",
        action="store_true",
        help="with --insights, replace the column names with col_1, col_2... so the names are not sent either",
    )
    args = parser.parse_args(argv)
    if args.insights_anonymize and not args.insights:
        parser.error("--insights-anonymize only makes sense together with --insights")
    return args


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
    code = summarize(args.csv, df)
    if code != EXIT_OK or not args.insights:
        return code
    return explain(df, args.insights_anonymize)


if __name__ == "__main__":
    sys.exit(main())
