# Dockerized Data Tool

A tiny Python data tool packaged with **Docker** so it runs identically anywhere —
no "works on my machine" problems.

## Files

| File | What it is | Installed or in code? |
|---|---|---|
| `app.py` | The Python tool (reads a CSV, prints a summary) | **In the code** |
| `requirements.txt` | Python dependencies (pandas, pandera, requests) | **In the code** |
| `requirements-dev.txt`, `pyproject.toml` | Test and lint tools (pytest, Ruff) and the Ruff settings | **In the code** |
| `Dockerfile` | The recipe to build the container image | **In the code** |
| `sample.csv` | Sample data | **In the code** |
| Docker Desktop | The program that builds & runs the container | **Installed on your PC** |

## Pull the published image (no clone, no build)

Every release is published to GitHub Container Registry by `.github/workflows/publish.yml`,
only after the image passes the Trivy scan. Images carry OCI labels, SLSA provenance and an SBOM.

```bash
docker pull ghcr.io/juanberrio0399/dockerized-data-tool:latest
docker run --rm ghcr.io/juanberrio0399/dockerized-data-tool:latest                 # built-in sample.csv
docker run --rm -v "$PWD:/data" ghcr.io/juanberrio0399/dockerized-data-tool:latest \
  python app.py /data/your.csv                                                      # your own file
```

| Tag | What it is |
|---|---|
| `latest`, `1`, `1.2`, `1.2.3` | Stable releases, from Git tags `vX.Y.Z` |
| `edge` | Latest commit on `main` (may change at any time) |

Pin a full version (`:1.2.3`) or a digest in scripts and pipelines. The container runs as the unprivileged UID `10001`, so a mounted folder must be readable by that user.

## Build it yourself with Docker

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
| `--insights` could not run: no `GEMINI_API_KEY`, or the Gemini API failed (the summary is still printed) | `4` |

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

## AI insights (optional)

`--insights` asks Google Gemini to read the statistics the tool just printed and explain them in plain
language, so someone who does not read a `describe()` table still gets the point. It is **opt-in**: without
the flag the tool makes no network call at all.

```bash
GEMINI_API_KEY=... python app.py sample.csv --insights
GEMINI_API_KEY=... python app.py sample.csv --insights --insights-anonymize   # hide the column names too

docker run --rm -e GEMINI_API_KEY -v "$PWD:/data" data-tool python app.py /data/your.csv --insights
```

The key is read from the environment only: it is never stored in the repo, never baked into the image
(`-e GEMINI_API_KEY` passes the one already in your shell), and never printed, not even in an error.
Get a free key at <https://aistudio.google.com/apikey>.

### What is sent, and what is not

| Sent to Google | Never sent |
|---|---|
| Row and column counts | Any cell of any data row |
| Column names (unless `--insights-anonymize`) | The file itself, or its path |
| Dtypes and how many empty values each column has | Text columns' most frequent values |
| The numeric `describe()` table (count, mean, std, quantiles) | Your API key in the URL or the body — it travels in the request header |

Text columns are described by dtype and null count only: pandas' `describe()` would report their most
frequent **raw value**, and that is real data. The payload is capped at 6 000 characters, so a very wide
file cannot turn into an unbounded upload.

The call uses the Flash model pinned in `GEMINI_MODEL` in `app.py` (free tier, no card required), with a
30 s timeout and a single retry on `429`/`5xx`. If anything fails — no key, rate limit, network down — the
normal summary has already been printed and the tool exits `4` with one `Error: ...` line, never a traceback.

## Why Docker matters

The `Dockerfile` bundles Python + the exact dependencies into one portable image.
It runs the same on your laptop, a teammate's machine, or a cloud server — the core
of modern, reproducible infrastructure.
