#!/usr/bin/env sh
set -e

# Log level - acceptable values are debug, info, warning, error, critical. Suggest info or debug.
LOG_LEVEL=${LOG_LEVEL:-info}

FORWARDED_ALLOW_IPS=${FORWARDED_ALLOW_IPS:-127.0.0.1}

set +a

python /app/misc/migrate_devices.py

uvicorn app.main:app --host 0.0.0.0 --port 8502 --log-config uvicorn-log-config.json \
    --log-level "$LOG_LEVEL" --loop uvloop --timeout-graceful-shutdown 5 \
    --no-server-header
