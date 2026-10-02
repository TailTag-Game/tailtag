FROM python:3.13-slim-bookworm

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
RUN uv sync --locked --no-dev

COPY --chown=tailtag:tailtag tailtag_simulator ./tailtag_simulator

ENTRYPOINT ["python", "-m", "tailtag_simulator"]
