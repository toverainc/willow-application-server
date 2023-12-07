FROM python:3.12.0-slim-bookworm

WORKDIR /app

# Install gcc temporarily until wheels for httptools on Python 3.12 are available
RUN apt-get update && apt-get install --no-install-recommends -y gcc libc6-dev libmagic1 libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache pip install -r requirements.txt

COPY . .

EXPOSE 8501
EXPOSE 8502

CMD /app/entrypoint.sh
