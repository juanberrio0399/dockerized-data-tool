# Two stages so the runtime image never inherits pip, its cache or any build leftover:
# only the finished virtual environment crosses over.

FROM python:3.14-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
COPY requirements.txt .
RUN /opt/venv/bin/pip install -r requirements.txt

FROM python:3.14-slim
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

# Default to the bundled sample so `docker run <image>` with no arguments demonstrates the tool.
CMD ["python", "app.py", "sample.csv"]
