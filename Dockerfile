ARG WAS_UI_TAG="main"

FROM ghcr.io/heywillow/willow-application-server-ui:${WAS_UI_TAG} AS was-ui

FROM python:3.12.9-alpine3.21


WORKDIR /app

RUN apk add --no-cache alpine-sdk libpq-dev

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache pip install -r requirements.txt

COPY . .

COPY --from=was-ui /was-ui/out/ /app/static/admin/

RUN pytest

EXPOSE 8501
EXPOSE 8502

ARG WAS_VERSION
ENV WAS_VERSION=$WAS_VERSION

CMD /app/entrypoint.sh
