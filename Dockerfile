FROM python:3.12.0-slim-bookworm

WORKDIR /app

COPY requirements.txt .

# Install gcc temporarily until wheels for httptools on Python 3.12 are available
RUN apt-get update && apt-get install -y gcc libmagic1

RUN --mount=type=cache,target=/root/.cache pip install -r requirements.txt

# Install deps to build uvloop until wheels are released
RUN apt-get install -y automake git libtool-bin libuv1-dev make && rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,target=/root/.cache pip install setuptools

RUN --mount=type=cache,target=/root/.cache pip install 'uvloop@git+https://github.com/MagicStack/uvloop.git@9f82bd7'

COPY . .

EXPOSE 8501
EXPOSE 8502

CMD /app/entrypoint.sh
