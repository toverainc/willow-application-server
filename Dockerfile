FROM python:3.11.4-slim-bookworm

WORKDIR /app

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache pip install -r requirements.txt

COPY . .

EXPOSE 8501
EXPOSE 8502

CMD /app/entrypoint.sh
