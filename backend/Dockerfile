FROM ghcr.io/astral-sh/uv:0.11.16 AS uv
FROM python:3.13-slim

WORKDIR /app
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1

USER 10001:10001
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
