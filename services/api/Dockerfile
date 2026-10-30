FROM python:3.13-slim-bookworm AS development

RUN apt-get update \
    && apt-get install --no-install-recommends -y git \
    && rm -rf /var/lib/apt/lists/*

# go-task runs the root Taskfile.yml. The archive is verified against the
# SHA-256 published in go-task v3.53.1's task_checksums.txt.
ARG TARGETARCH
ARG TASK_VERSION=3.53.1
ARG TASK_SHA256_AMD64=a54a408f6861ff921f6e87774180db31bacd8c1e7c944ca696db9fea49a82fc7
ARG TASK_SHA256_ARM64=e3ad19101493a0112e1f22ae8ccc54bf03e533b1076a0ca1e6c782a09ad2e588
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

ARG RAILWAY_GIT_COMMIT_SHA
ARG RENDER_GIT_COMMIT

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
    && install -d -m 0700 -o tailtag -g tailtag /home/tailtag/.ssh \
    && chown tailtag:tailtag /app

COPY docker/write_build_identity.py /tmp/write_build_identity.py
RUN RAILWAY_GIT_COMMIT_SHA="$RAILWAY_GIT_COMMIT_SHA" RENDER_GIT_COMMIT="$RENDER_GIT_COMMIT" \
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

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
