FROM python:3.12-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.12-slim

RUN useradd -m appuser

WORKDIR /app

COPY --from=builder /root/.local /home/appuser/.local
COPY . /app

RUN chown -R appuser:appuser /app

USER appuser

ENV PATH=/home/appuser/.local/bin:$PATH

EXPOSE 5000

CMD ["python", "app.py"]
