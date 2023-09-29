#!/usr/bin/env bash
set -e

# Log level - acceptable values are debug, info, warning, error, critical. Suggest info or debug.
LOG_LEVEL=${LOG_LEVEL:-info}

FORWARDED_ALLOW_IPS=${FORWARDED_ALLOW_IPS:-127.0.0.1}

set +a

uvicorn api:app --reload --host 0.0.0.0 --port 8502 --log-config uvicorn-log-config.json \
    --log-level "$LOG_LEVEL" --loop asyncio
