# Dockerfile — the "recipe" that builds the box (image) for this tool.
# This file goes IN THE CODE (your repo). Docker Desktop is the PROGRAM that reads it.

# 1) Base image: a slim Linux with Python 3.12 already inside
FROM python:3.12-slim

# 2) Work inside this folder in the container
WORKDIR /app

# 3) Install dependencies first (better caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4) Copy the rest of the code
COPY app.py sample.csv ./

# 5) What runs when the container starts
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
