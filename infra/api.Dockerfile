FROM python:3.12-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b

ARG BLENDER_VERSION=4.5.12
ARG BLENDER_ARCHIVE_SHA256=95e3a2dfedba3bd32ca54fc355eac6b15a11986954ccb02815a07535d0120a25

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        fonts-dejavu-core \
        libdbus-1-3 \
        libegl1 \
        libfontconfig1 \
        libfreetype6 \
        libgl1 \
        libglib2.0-0 \
        libice6 \
        libsm6 \
        libx11-6 \
        libxext6 \
        libxfixes3 \
        libxi6 \
        libxkbcommon0 \
        libxrender1 \
        libxxf86vm1 \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-fra \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

RUN curl --fail --show-error --silent --location \
        --retry 3 --retry-all-errors --retry-delay 2 \
        --connect-timeout 20 --max-time 600 \
        "https://download.blender.org/release/Blender4.5/blender-${BLENDER_VERSION}-linux-x64.tar.xz" \
        --output /tmp/blender.tar.xz \
    && echo "${BLENDER_ARCHIVE_SHA256}  /tmp/blender.tar.xz" | sha256sum --check --strict \
    && mkdir -p /opt/blender \
    && tar --extract --xz --file /tmp/blender.tar.xz --directory /opt/blender --strip-components=1 \
    && rm -f /tmp/blender.tar.xz

WORKDIR /app

COPY infra/requirements-docker.lock /tmp/requirements-docker.lock
RUN python -m pip install --requirement /tmp/requirements-docker.lock \
    && rm -f /tmp/requirements-docker.lock

COPY apps /app/apps
COPY core /app/core
COPY assets/manifests /app/assets/manifests
COPY assets/capabilities /app/assets/capabilities
COPY assets/antennas /app/assets/antennas
COPY assets/brackets /app/assets/brackets
COPY assets/cabinets /app/assets/cabinets
COPY assets/cables /app/assets/cables
COPY assets/radios /app/assets/radios
COPY assets/towers /app/assets/towers
COPY data/knowledge /app/data/knowledge
COPY --chmod=755 infra/docker/api-entrypoint.sh /usr/local/bin/telecom-api-entrypoint

RUN groupadd --gid 10001 telecom \
    && useradd --uid 10001 --gid telecom --no-create-home --home-dir /tmp/telecom-studio-home telecom \
    && mkdir -p \
        /app/assets/library \
        /var/lib/telecom/sqlite \
        /var/lib/telecom/outputs \
    && chown -R 10001:10001 \
        /app \
        /var/lib/telecom

USER 10001:10001

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/telecom-api-entrypoint"]
CMD ["uvicorn", "apps.api.telecom_studio_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
