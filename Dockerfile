ARG WAS_UI_TAG="main"

FROM ghcr.io/heywillow/willow-application-server-ui:${WAS_UI_TAG} AS was-ui

FROM alpine:3.21 AS build

WORKDIR /app

RUN --mount=type=cache,target=/var/cache/apk apk add --cache-dir /var/cache/apk alpine-sdk libpq-dev python3-dev uv

COPY requirements.txt .

RUN uv venv
RUN --mount=type=cache,target=/root/.cache uv pip install -r requirements.txt

COPY . .

COPY --from=was-ui /was-ui/out/ /app/static/admin/

ENV PATH="$PATH:/app/.venv/bin"

RUN PYTHONPATH=/app pytest -s

FROM alpine:3.21

ENV PATH="$PATH:/app/.venv/bin"

WORKDIR /app

RUN --mount=type=cache,target=/var/cache/apk apk add --cache-dir /var/cache/apk libmagic libpq python3

COPY --from=build /app /app

EXPOSE 8501
EXPOSE 8502

ARG WAS_VERSION
ENV WAS_VERSION=$WAS_VERSION

CMD /app/entrypoint.sh
