# Build-Stage
FROM python:3.11-slim-bullseye AS builder

RUN pip install --no-cache-dir poetry==1.6.1

RUN poetry config virtualenvs.create false

WORKDIR /app

COPY ./pyproject.toml ./poetry.lock* ./

RUN poetry install --no-interaction --no-ansi --no-root

COPY src/ .

# Final-Stage
FROM python:3.11-slim-bullseye

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /app /app

CMD ["python", "app.py"]