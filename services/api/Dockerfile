FROM python:3.13-slim-bookworm AS development

RUN apt-get update \
    && apt-get install --no-install-recommends -y git \
    && rm -rf /var/lib/apt/lists/*

# go-task runs the root Taskfile.yml. The archive is verified against the
# SHA-256 published in go-task v3.54.0's task_checksums.txt.
ARG TARGETARCH
ARG TASK_VERSION=3.54.0
ARG TASK_SHA256_AMD64=680859dbb4d881a9c72d4d9a8f510825450849af8567deacd7302c01124416fb
ARG TASK_SHA256_ARM64=d7189d439d4a6058e39e1b2acd7c8b27acd4856691b408f23b242e4294e1df5b
RUN set -eu; \
    case "$TARGETARCH" in \
        amd64) task_sha256="$TASK_SHA256_AMD64" ;; \
        arm64) task_sha256="$TASK_SHA256_ARM64" ;; \
        *) echo "unsupported architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac; \
    archive="task_linux_${TARGETARCH}.tar.gz"; \
    workdir="$(mktemp -d)"; \
    python -c 'import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])' \
        "https://github.com/go-task/task/releases/download/v${TASK_VERSION}/${archive}" \
        "${workdir}/${archive}"; \
    echo "${task_sha256}  ${workdir}/${archive}" | sha256sum -c -; \
    tar -xzf "${workdir}/${archive}" -C "${workdir}" task; \
    install -m 0755 "${workdir}/task" /usr/local/bin/task; \
    rm -rf "${workdir}"

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

ARG RENDER_GIT_COMMIT

LABEL org.opencontainers.image.source="https://github.com/TailTag-Game/tailtag" \
    org.opencontainers.image.title="TailTag API" \
    org.opencontainers.image.description="TailTag development API" \
    org.tailtag.delivery-probe="wait-for-ci-trigger-refresh-2026-08-16"

# tini runs as PID 1 and reaps the `render ssh` session processes, which
# Gunicorn would otherwise log as worker exits (#448).
RUN apt-get update \
    && apt-get install --no-install-recommends -y tini \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9.17 /uv /uvx /bin/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN groupadd --system tailtag \
    && useradd --system --gid tailtag --create-home tailtag \
    && install -d -m 0700 -o tailtag -g tailtag /home/tailtag/.ssh \
    && chown tailtag:tailtag /app

COPY docker/write_build_identity.py /tmp/write_build_identity.py
RUN RENDER_GIT_COMMIT="$RENDER_GIT_COMMIT" \
        python /tmp/write_build_identity.py /opt/tailtag/build-identity.json \
    && rm /tmp/write_build_identity.py \
    && chmod 0755 /opt/tailtag \
    && chown root:root /opt/tailtag/build-identity.json \
    && chmod 0444 /opt/tailtag/build-identity.json

COPY --chown=tailtag:tailtag pyproject.toml uv.lock ./
USER tailtag
RUN uv sync --locked --no-dev --no-install-project

COPY --chown=tailtag:tailtag . ./

RUN python manage.py collectstatic --settings=config.settings.build --noinput

ENTRYPOINT ["tini", "--"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
