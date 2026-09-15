# Dockerized Data Tool

A tiny Python data tool packaged with **Docker** so it runs identically anywhere —
no "works on my machine" problems.

## Files

| File | What it is | Installed or in code? |
|---|---|---|
| `app.py` | The Python tool (reads a CSV, prints a summary) | **In the code** |
| `requirements.txt` | Python dependencies (pandas) | **In the code** |
| `requirements-dev.txt`, `pyproject.toml` | Test and lint tools (pytest, Ruff) and the Ruff settings | **In the code** |
| `Dockerfile` | The recipe to build the container image | **In the code** |
| `sample.csv` | Sample data | **In the code** |
| Docker Desktop | The program that builds & runs the container | **Installed on your PC** |

## Run it with Docker

```bash
docker build -t data-tool .        # build the image from the Dockerfile
docker run --rm data-tool          # run it (uses sample.csv)
docker run --rm -v "$PWD:/data" data-tool python app.py /data/your.csv
```

## Run it without Docker (plain Python)

```bash
pip install -r requirements.txt
python app.py sample.csv
```

## Errors and exit codes

Bad input never ends in a Python traceback: the tool prints one `Error: ...` line to stderr and exits with a code scripts can check.

| Situation | Exit code |
|---|---|
| Summary printed (including a header-only file or one without numeric columns) | `0` |
| The file is empty or is not a readable CSV (malformed, binary) | `1` |
| The path does not exist, is a directory, or cannot be read | `2` |
| The CSV does not match the schema passed with `--schema` | `3` |

```bash
pip install -r requirements-dev.txt   # runtime dependencies + pytest + pinned Ruff
pytest -q                             # run the tests
ruff check . && ruff format --check . # lint and formatting, same as CI
```

## Schema contracts

Catch a silent change in the input (a renamed column, text in a numeric column, empty required values) before the summary runs:

```bash
python app.py sample.csv --infer-schema schema.yaml   # 1) write the contract from a known-good file
python app.py new_export.csv --schema schema.yaml     # 2) validate every new file against it
```

The inferred contract only fixes the **columns, their types and whether empty values are allowed** — not the value ranges of the reference file, so any valid new data passes. Add business rules by editing `schema.yaml` (for example `checks: {greater_than_or_equal_to: 0}` under a column). A file that breaks the contract exits with `3` and one line per problem:

```text
Error: missing column 'revenue'
Error: column 'units': expected int64 values, found 'twelve' (line 3)
```

## Why Docker matters

The `Dockerfile` bundles Python + the exact dependencies into one portable image.
It runs the same on your laptop, a teammate's machine, or a cloud server — the core
of modern, reproducible infrastructure.
