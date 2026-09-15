# Dockerfile — the "recipe" that builds the box (image) for this tool.
# This file goes IN THE CODE (your repo). Docker Desktop is the PROGRAM that reads it.

# ---- Stage 1: install the dependencies into an isolated virtual environment ----
FROM python:3.12-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
COPY requirements.txt .
RUN /opt/venv/bin/pip install -r requirements.txt

# ---- Stage 2: the image that actually runs ----
# Only the ready-made virtual environment and the app are copied: no pip cache,
# no build leftovers, and the process does NOT run as root.
FROM python:3.12-slim
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Apply Debian security updates published after the base image was built (Trivy found fixable
# CRITICAL/HIGH CVEs in perl-base, gzip, pcre2 and sqlite), then drop the apt lists.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Unprivileged user with a fixed UID (works with Kubernetes runAsNonRoot).
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser

WORKDIR /app
COPY --from=build /opt/venv /opt/venv
# Files owned by root and only readable by appuser: the app cannot modify its own code.
COPY app.py sample.csv ./

USER 10001

# What runs when the container starts
CMD ["python", "app.py", "sample.csv"]
