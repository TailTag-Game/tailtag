FROM python:3.13-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.9.17 /uv /uvx /bin/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN groupadd --system tailtag \
    && useradd --system --gid tailtag --create-home tailtag \
    && mkdir /reports && chown tailtag:tailtag /reports

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY tailtag_simulator ./tailtag_simulator
COPY services/api/simulation_fixtures/images ./services/api/simulation_fixtures/images
COPY source.json ./source.json
RUN chmod -R a-w /app

USER tailtag
ENTRYPOINT ["python", "-m", "tailtag_simulator"]
