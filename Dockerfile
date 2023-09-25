FROM python:3.11.5-slim-bookworm

WORKDIR /app

COPY requirements.txt .

RUN apt-get update && apt-get install -y libmagic1 && rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,target=/root/.cache pip install -r requirements.txt

COPY . .

EXPOSE 8501
EXPOSE 8502

CMD /app/entrypoint.sh
