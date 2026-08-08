FROM python:3.12-alpine@sha256:6d43704baacd1bfbe7c295d7f13079d5d8104ed33568873133f8fc69980419df

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --chmod=755 infra/docker/sqlite_snapshot.py /opt/sqlite_snapshot.py

RUN addgroup --gid 10001 telecom \
    && adduser --uid 10001 --ingroup telecom --disabled-password --no-create-home telecom \
    && mkdir -p /source /preview \
    && chown -R 10001:10001 /source /preview

USER 10001:10001

ENTRYPOINT ["python", "/opt/sqlite_snapshot.py"]
