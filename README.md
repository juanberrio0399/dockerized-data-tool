# Dockerized Data Tool

A tiny Python data tool packaged with **Docker** so it runs identically anywhere —
no "works on my machine" problems.

## Files

| File | What it is | Installed or in code? |
|---|---|---|
| `app.py` | The Python tool (reads a CSV, prints a summary) | **In the code** |
| `requirements.txt` | Python dependencies (pandas) | **In the code** |
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

## Why Docker matters

The `Dockerfile` bundles Python + the exact dependencies into one portable image.
It runs the same on your laptop, a teammate's machine, or a cloud server — the core
of modern, reproducible infrastructure.
