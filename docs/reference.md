# Reference: contracts, insights, image and operation

[Español](reference.es.md) · Back to the [README](../README.md)

## Schema contracts

```bash
python app.py sample.csv --infer-schema schema.yaml   # write the contract from a known-good file
python app.py new_export.csv --schema schema.yaml     # validate every later file against it
```

The inferred contract fixes the columns, their dtypes and whether empty values are allowed — and nothing else. pandera's own `infer_schema` also turns the reference file's min/max into range checks, which would reject almost any valid new file; those are stripped in `write_schema`. Business rules are added by editing the YAML, for example `checks: {greater_than_or_equal_to: 0}` under a column.

A file that breaks the contract exits `3` with one readable line per problem, not a pandera traceback:

```text
Error: missing column 'revenue'
Error: column 'units': expected int64 values, found 'twelve' (line 3)
```

`describe_failures` groups the failure table by column and problem, shows at most 3 examples and suppresses the knock-on errors: a cell that failed a type check is not reported a second time as a failed range check.

## AI insights (opt-in)

`--insights` asks Google Gemini to read the statistics the tool just printed and explain them in plain language. Without the flag the tool makes no network call at all.

```bash
GEMINI_API_KEY=... python app.py sample.csv --insights
GEMINI_API_KEY=... python app.py sample.csv --insights --insights-anonymize   # hide column names too

docker run --rm -e GEMINI_API_KEY -v "$PWD:/data" data-tool python app.py /data/your.csv --insights
```

| Sent to Google | Never sent |
|---|---|
| Row and column counts | Any cell of any data row |
| Column names, unless `--insights-anonymize` | The file itself, or its path |
| Dtypes and the empty-value count per column | Text columns' most frequent values |
| The numeric `describe()` table | The API key in the URL or body — it travels in a header |

Text columns are reported by dtype and null count only. pandas' `describe()` would put their most frequent **raw value** in the `top` row, and that is real data. The payload is capped at 6,000 characters so a very wide file cannot become an unbounded upload.

The key is read from the environment only: never stored in the repo, never baked into the image (`-e GEMINI_API_KEY` forwards the one already in your shell), and never printed, not even inside an error message. A free key comes from <https://aistudio.google.com/apikey>.

## Image tags and verification

| Tag | What it is |
|---|---|
| `latest`, `1`, `1.2`, `1.2.3` | Stable releases, from Git tags `vX.Y.Z` |
| `edge` | The latest commit on `main`; may change at any time |
| `build-linux-amd64`, `build-linux-arm64` | Internal staging tags the release workflow needs because `docker push` cannot push an untagged manifest. Not for use |

Pin a full version or a digest in scripts. The container runs as UID `10001`, so a mounted folder has to be readable by that user.

```bash
docker buildx imagetools inspect ghcr.io/juanberrio0399/dockerized-data-tool:latest   # both platforms
docker pull --platform linux/arm64 ghcr.io/juanberrio0399/dockerized-data-tool:latest # force one
gh attestation verify --owner juanberrio0399 \
  oci://ghcr.io/juanberrio0399/dockerized-data-tool:latest                            # provenance
```

## Decisions and limits

**A container instead of a PyPI package.** A wheel pins Python libraries and nothing else — not the interpreter, not the OS libraries pandas links against. The image pins all three, so the tool that runs on a teammate's laptop is the same one that runs in a CI job.

**Two-stage build, non-root, fixed UID.** Dependencies are installed into `/opt/venv` in a build stage and only the finished venv is copied forward, so no pip cache or build leftovers reach the runtime layer. `apt-get upgrade` runs in the runtime stage because the `python:3.14-slim` base lags Debian security fixes — Trivy found fixable CRITICAL/HIGH CVEs in `perl-base`, `gzip`, `pcre2` and `sqlite` on an un-upgraded base. The app files are owned by root, so the process running as `appuser` cannot rewrite its own code. pip, setuptools and wheel are removed from both the venv and the base image's system Python: nothing imports them at runtime, and a package that isn't there can't be vulnerable (that removal cleared four HIGH findings). UID `10001` is numeric and fixed so Kubernetes `runAsNonRoot` accepts it.

**Trivy gates on `ignore-unfixed`.** Failing on unpatched base-image CVEs would make the check permanently red and therefore ignored. Failing only on CRITICAL/HIGH findings that already have a fix keeps every red build actionable.

**No cross-run build cache.** Every build re-runs `apt-get upgrade` so a release always carries the latest security fixes. A cache would risk serving a stale upgrade layer, and both platforms build natively in a couple of minutes, so it would buy little.

**Gemini sends aggregates, never rows.** The alternative — sending a sample of the data — gives a far better explanation and makes the tool unusable on anything private. The cap on what leaves the machine is enforced in `stats_payload`, not in the prompt.

**Pandera contracts are structural by default.** A contract that also encoded the reference file's value ranges would fail on the next month's data and teach everyone to pass `--schema` never again.

What it deliberately does not do:

- **No output files.** The summary goes to stdout; there is no `--output`. `--infer-schema` is the only thing that writes.
- **No plots, no profiling report.** Just `describe()`.
- **CSV only.** No Parquet, no Excel, no JSON.
- **Whole-file reads.** `pd.read_csv` loads the file into memory; there is no chunked or streaming mode, so a file larger than RAM will fail.
- **No config file.** Everything is a flag or an environment variable.
- **The image has no shell entrypoint tricks.** `CMD` runs `python app.py sample.csv`; anything else is passed as a full command.

## Operation

| What runs on its own | When | Where the result lands |
|---|---|---|
| `tests.yml` — Ruff, pytest, image build, Trivy, non-root and exit-code checks | every push to `main`, every PR, Mondays 12:00 UTC | Actions checks |
| `publish.yml` — build and scan both platforms | every PR (never pushed), every push to `main`, every `v*.*.*` tag | Actions checks; a job summary with each digest |
| `publish.yml` — publish | push to `main` → `:edge`; tag `vX.Y.Z` → `:X.Y.Z`, `:X.Y`, `:X` and `:latest` | GHCR package, plus attestations |
| `codeql.yml` — SAST, `security-extended` | every push to `main`, every PR, Mondays 06:00 UTC | Security → Code scanning |
| Dependabot — Actions, pip and Docker, grouped | weekly, Tuesdays | a PR labelled `dependencies` |

The weekly cron on `tests.yml` exists because new CVEs appear in the base image even when no commit does; a red scheduled run means the base image needs a rebuild, not that the code broke.

To cut a release: tag `vX.Y.Z` on `main` and push the tag. To rehearse the push path without releasing, run `publish.yml` manually with a `test_tag` input (for example `citest`) and delete that package version afterwards.

When something fails:

- **Trivy fails the job.** A fixable CRITICAL/HIGH CVE appeared in the base image. Re-running usually fixes it because the build re-runs `apt-get upgrade`; if not, the `python:3.14-slim` base needs to move.
- **"Verify the pushed image is the scanned image" fails.** The registry returned something other than what was built. Do not re-tag around it; re-run the job.
- **The manifest-list verification fails.** The index picked up an entry that was not one of the two scanned digests. The staging tags may have been moved by a concurrent run; the `concurrency` group should prevent this, so investigate before republishing.
- **`gh attestation verify` fails for a tag.** Provenance is attested against digests. Resolve the tag first with `docker buildx imagetools inspect` and verify the digest.
