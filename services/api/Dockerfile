FROM python:3.13-slim-bookworm AS development

RUN apt-get update \
    && apt-get install --no-install-recommends -y git make \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9.17 /uv /uvx /bin/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN groupadd --system tailtag \
    && useradd --system --gid tailtag --create-home tailtag \
    && chown tailtag:tailtag /app

COPY --chown=tailtag:tailtag pyproject.toml uv.lock ./
USER tailtag
RUN uv sync --locked --no-install-project

COPY --chown=tailtag:tailtag . ./

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]


FROM python:3.13-slim-bookworm AS production

ARG RAILWAY_GIT_COMMIT_SHA

LABEL org.opencontainers.image.source="https://github.com/TailTag-Game/tailtag" \
    org.opencontainers.image.title="TailTag API" \
    org.opencontainers.image.description="TailTag development API" \
    org.tailtag.delivery-probe="wait-for-ci-trigger-refresh-2026-08-16"

COPY --from=ghcr.io/astral-sh/uv:0.9.17 /uv /uvx /bin/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN groupadd --system tailtag \
    && useradd --system --gid tailtag --create-home tailtag \
    && chown tailtag:tailtag /app

RUN RAILWAY_GIT_COMMIT_SHA="$RAILWAY_GIT_COMMIT_SHA" python -c 'import json, os, re; from pathlib import Path; source_sha = os.environ["RAILWAY_GIT_COMMIT_SHA"]; assert not source_sha or re.fullmatch("[0-9a-f]{40}", source_sha), "missing or malformed Railway build SHA"; path = Path("/opt/tailtag/build-identity.json"); path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps({"source_sha": source_sha or None}) + "\n")' \
    && chmod 0755 /opt/tailtag \
    && chown root:root /opt/tailtag/build-identity.json \
    && chmod 0444 /opt/tailtag/build-identity.json

COPY --chown=tailtag:tailtag pyproject.toml uv.lock ./
USER tailtag
RUN uv sync --locked --no-dev --no-install-project

COPY --chown=tailtag:tailtag . ./

RUN python manage.py collectstatic --settings=config.settings.build --noinput

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
