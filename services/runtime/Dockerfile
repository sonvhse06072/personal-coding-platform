FROM node:22-bookworm-slim

ARG CODEX_VERSION
ARG OPENCODE_VERSION=latest
ARG DDEV_UID=1000
ARG DDEV_GID=1000

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip python3-venv git ripgrep jq curl ca-certificates openssh-client \
    && rm -rf /var/lib/apt/lists/*

RUN test -n "${CODEX_VERSION}" \
    && npm install -g \
    @openai/codex@${CODEX_VERSION} \
    opencode-ai@${OPENCODE_VERSION}

LABEL org.opencontainers.image.pcp.codex-version="${CODEX_VERSION}"

# The service runs as the host DDEV UID/GID. Prepare a writable HOME for
# OpenCode/Codex caches. Antigravity runs natively on WSL through the host bridge
# so its OS-keyring credentials never enter this container.
RUN mkdir -p /home/coder/.cache /home/coder/.config /home/coder/.local/share /home/coder/.local/state \
    && chown -R ${DDEV_UID}:${DDEV_GID} /home/coder

WORKDIR /app
COPY requirements.txt requirements-dev.txt /app/
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r /app/requirements-dev.txt
COPY app /app/app
COPY tests /app/tests
ENV PATH="/opt/venv/bin:${PATH}" PYTHONUNBUFFERED=1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8787"]
