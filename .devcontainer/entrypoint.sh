#!/bin/bash
set -euo pipefail

export HISTFILE=/commandhistory/.bash_history
export HISTSIZE=100000
export HISTFILESIZE=200000
shopt -s histappend
PROMPT_COMMAND="history -a; history -n"

echo "[entrypoint] starting redis"
redis-server --daemonize yes

cd /workspaces/pyrad-server

echo "[entrypoint] starting pyrad-server (API + RADIUS)"
pkill -f "pyrad-server serve" || true

# Default ports match devcontainer.json (API 5711, RADIUS UDP 1812/1813)
# You can override via environment variables.
API_PORT="${API_PORT:-5711}"
AUTH_PORT="${AUTH_PORT:-1812}"
ACCT_PORT="${ACCT_PORT:-1813}"
REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
SECRET="${SECRET:-testsecret}"
CONFIG_PATH="${CONFIG_PATH:-conf/test-config.yml}"
DICTIONARY_PATH="${DICTIONARY_PATH:-conf/dictionary}"

pyrad-server serve \
  --config-path "${CONFIG_PATH}" \
  --dictionary-path "${DICTIONARY_PATH}" \
  --secret "${SECRET}" \
  --rest-port "${API_PORT}" \
  --auth-port "${AUTH_PORT}" \
  --acct-port "${ACCT_PORT}" \
  --redis-host "${REDIS_HOST}" \
  --redis-port "${REDIS_PORT}" > /tmp/pyrad_server.log 2>&1 &
SERVER_PID=$!

echo "[entrypoint] pyrad-server PID=${SERVER_PID}"
echo "[entrypoint] logs: tail -f /tmp/pyrad_server.log"

cleanup() {
  echo "[entrypoint] stopping..."
  kill "${SERVER_PID}" 2>/dev/null || true
  wait "${SERVER_PID}" 2>/dev/null || true
}
trap cleanup SIGTERM SIGINT

wait "${SERVER_PID}"
