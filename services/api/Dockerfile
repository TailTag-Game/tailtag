FROM python:3.13-slim-bookworm AS development

COPY --from=ghcr.io/astral-sh/uv:0.9.17 /uv /uvx /bin/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

COPY . ./

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]


FROM python:3.13-slim-bookworm AS production

COPY --from=ghcr.io/astral-sh/uv:0.9.17 /uv /uvx /bin/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY . ./

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
