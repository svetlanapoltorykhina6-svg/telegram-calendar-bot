FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY README.md ./
COPY alembic.ini ./
COPY migrations ./migrations

RUN pip install --upgrade pip \
    && pip install .

EXPOSE 8000

CMD ["uvicorn", "bot_helper.main:app", "--host", "0.0.0.0", "--port", "8000"]
