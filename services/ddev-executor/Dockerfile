FROM python:3.13-slim-bookworm

ARG DDEV_VERSION=v1.25.4
ARG BUILDX_VERSION=v0.37.0
ARG TARGETARCH
ARG DDEV_UID=1000
ARG DDEV_GID=1000

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates git bash docker.io \
    && rm -rf /var/lib/apt/lists/* \
    && arch="${TARGETARCH:-amd64}" \
    && curl -fsSL "https://github.com/ddev/ddev/releases/download/${DDEV_VERSION}/ddev_linux-${arch}.${DDEV_VERSION}.tar.gz" -o /tmp/ddev.tgz \
    && tar -xzf /tmp/ddev.tgz -C /tmp \
    && install -m 0755 /tmp/ddev /usr/local/bin/ddev \
    && rm -f /tmp/ddev.tgz /tmp/ddev \
    && mkdir -p /usr/local/libexec/docker/cli-plugins \
    && curl -fsSL "https://github.com/docker/buildx/releases/download/${BUILDX_VERSION}/buildx-${BUILDX_VERSION}.linux-${arch}" -o /usr/local/libexec/docker/cli-plugins/docker-buildx \
    && chmod 0755 /usr/local/libexec/docker/cli-plugins/docker-buildx \
    && docker buildx version \
    && mkdir -p /home/coder/.cache /home/coder/.config /home/coder/.local/share /home/coder/.local/state \
    && chown -R ${DDEV_UID}:${DDEV_GID} /home/coder

WORKDIR /app
COPY requirements.txt requirements-dev.txt /app/
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY app /app/app
COPY tests /app/tests
ENV PYTHONUNBUFFERED=1 DDEV_NO_TUI=true
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8790"]
