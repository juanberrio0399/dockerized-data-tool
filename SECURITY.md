# Security Policy

## Scope

This repository builds a small CSV CLI and publishes it as a container image on GHCR
(`ghcr.io/juanberrio0399/dockerized-data-tool`) for `linux/amd64` and `linux/arm64`. The
code is tiny; the attack surface is the **supply chain**: the base image, the Python
dependencies, and the release workflow that pushes the image.

What the pipeline already enforces:

- The image runs as an unprivileged UID and carries no `pip` or `setuptools` at runtime.
- Trivy blocks any CRITICAL or HIGH finding with an available fix before anything is pushed.
- The pushed digest must equal the scanned image; each digest gets an SPDX SBOM and SLSA
  provenance.
- `--insights` sends only aggregate statistics to Gemini, never rows. Without the flag the
  tool makes no network calls.

## Supported versions

Only the latest image built from `main` is supported. Pin by digest, not by tag, if you
need a fixed version.

## Reporting a vulnerability

Please report privately — do not open a public issue.

- Email juandyb99@gmail.com with `SECURITY` in the subject.

Useful details: the image digest or commit, what an attacker gains, and the steps to
reproduce it. Expect an acknowledgement within 5 working days. Confirmed issues are fixed
on `main` and the image is republished; the fix is credited in the commit unless you ask
otherwise.

## Out of scope

Findings in the base image with no upstream fix (Trivy `--ignore-unfixed` hides those on
purpose), and anything that requires an attacker to already control the input CSV path
or the host running the container.
