# Plan — Dockerized Data Tool

Updated: 2026-10-11 · Status: **maintained** (image published to GHCR)

How it works is in the [README](README.md). This file says where the project stands and what comes next.

## What it is

A CSV summary CLI with optional schema contracts, shipped as a hardened multi-platform container image. The pandas call is ten lines; the point of the repo is the **supply chain** around it: non-root image, SBOM, SLSA provenance, and a registry push only after a vulnerability scan passes on the exact bits that get published.

## How it works today

| Piece | Where |
|---|---|
| CLI: summary, `--infer-schema`, `--schema` (pandera, lazy), `--insights` (Gemini, opt-in) | `app.py` |
| Distinct exit codes (0 ok, 1 parse, 2 path, 3 schema, 4 insights) and one-line errors | `app.py` |
| Two-stage image on `python:3.14-slim`, non-root, no pip/setuptools at runtime | `Dockerfile` |
| Native build per platform (amd64, arm64) → Trivy gate → SBOM + smoke test → push the scanned digest | `publish.yml` |
| Tests, Ruff, CodeQL on every PR | `tests.yml`, `codeql.yml` |

## What it needs

- GitHub Actions and GHCR (public repo: free).
- `GEMINI_API_KEY` only for `--insights`, at run time.
- Cost: 0.

## How it should work

- Bad input never produces a traceback.
- Nothing reaches the registry unless the image that was scanned is the image that is pushed.
- Zero CRITICAL/HIGH findings with an available fix.
- Only aggregate statistics ever leave the machine (`--insights`), never rows.

## What was done

| Date | What | PR |
|---|---|---|
| 2026-08 | First version of the CLI and Dockerfile | — |
| 2026-09-14/15 | Non-root two-stage image, pandera schema contracts, Trivy, Ruff, GHCR publish, Gemini insights | #26–#33 |
| 2026-09-22 | amd64 + arm64 from natively scanned digests | #38 |
| 2026-09-23 | CodeQL, Dependabot, README rewritten around the supply chain | #39–#44 |
| 2026-10-01 | Python 3.14; pip/setuptools stripped from the venv **and** the system Python (4 HIGH findings gone) | #51, #52 |

## What's left

1. README badge still says **Python 3.12**; the image is 3.14.
2. #47: OpenSSF Scorecard (SLSA provenance is already there).
3. #46: publish as a GitHub Action on the Marketplace.
4. #37: discoverability and social preview.
5. #1: Polars / uv / DuckDB, worth it only if the CLI grows beyond a summary.
6. Dependabot #53 (ruff, patch) is open.

## Known traps

- **Trivy flags the base image, not just your dependencies.** On 3.14 the vulnerable `setuptools` lived in the system Python, and `urllib3`/`msgpack` were vendored inside `pip` itself. Removing the tools beats pinning versions.
- **A fix tested only on the old base proves nothing**: ship the fix and the base bump together.
- **No local Docker on the dev machine**: CI is the test (build, scan, run the container, tests).
