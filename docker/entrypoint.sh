#!/bin/sh
set -eu

: "${MIROFISH_BASIC_AUTH_USER:?MIROFISH_BASIC_AUTH_USER must be set}"
: "${MIROFISH_BASIC_AUTH_HASH:?MIROFISH_BASIC_AUTH_HASH must be set}"

cd /app/backend
uv run --frozen gunicorn --workers 1 --threads 8 --bind 127.0.0.1:5001 'app:create_app()' &
backend_pid=$!

shutdown() {
    kill -TERM "$backend_pid" 2>/dev/null || true
    wait "$backend_pid" 2>/dev/null || true
}

trap shutdown EXIT INT TERM

cd /app
caddy run --config /etc/caddy/Caddyfile --adapter caddyfile &
caddy_pid=$!
wait "$caddy_pid"
