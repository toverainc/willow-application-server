FROM python:3.11.4-slim-bullseye

WORKDIR /app

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache pip install -r requirements.txt

COPY . .

CMD ./entrypoint.sh
EXPOSE 8501