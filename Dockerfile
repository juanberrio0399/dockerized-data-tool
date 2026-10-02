# Two stages so the runtime image never inherits pip, its cache or any build leftover:
# only the finished virtual environment crosses over.
#
# Build tooling is stripped from BOTH pythons: from the venv before it is copied,
# and from the base image's system python further down. They are
# build-time tools: nothing in requirements.txt imports them at runtime, and leaving
# them in is what made Trivy fail the build (setuptools 70.3.0, CVE-2025-47273, a
# path traversal fixed in 78.1.1). Removing them beats pinning a newer version --
# a dependency that is not there cannot be vulnerable, and it is what the line above
# already claimed this image does.

FROM python:3.14-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
COPY requirements.txt .
RUN /opt/venv/bin/pip install -r requirements.txt \
    && /opt/venv/bin/pip uninstall -y setuptools wheel pip

FROM python:3.14-slim
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Apply Debian security updates published after the base image was built (Trivy found fixable
# CRITICAL/HIGH CVEs in perl-base, gzip, pcre2 and sqlite), then drop the apt lists.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# The base image ships its own pip and setuptools in the system Python, outside the
# venv, and Trivy flags four HIGH findings there: setuptools 70.3.0
# (CVE-2025-47273) plus two packages pip vendors inside itself, urllib3 2.7.0
# (CVE-2026-97687, CVE-2026-97689) and msgpack 1.1.2 (GHSA-6v7p-g79w-8964).
#
# Note the venv already has the good urllib3 (2.8.0, pulled in by requests): the
# vulnerable copy is the one bundled inside pip. The app runs entirely from
# /opt/venv, so nothing here is needed at runtime. Deleting the files rather than
# running `pip uninstall` is deliberate: PATH points at the venv, whose pip was
# already removed, so there is no pip left to invoke.
RUN rm -rf /usr/local/lib/python3.*/site-packages/pip* \
           /usr/local/lib/python3.*/site-packages/setuptools* \
           /usr/local/lib/python3.*/site-packages/pkg_resources \
           /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.*

# Unprivileged user with a fixed UID (works with Kubernetes runAsNonRoot).
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser

WORKDIR /app
COPY --from=build /opt/venv /opt/venv
# Files owned by root and only readable by appuser: the app cannot modify its own code.
COPY app.py sample.csv ./

USER 10001

# Default to the bundled sample so `docker run <image>` with no arguments demonstrates the tool.
CMD ["python", "app.py", "sample.csv"]
