#!/bin/bash
set -euo pipefail

TOKEN_FILE="/shared/join_token.txt"

echo "[agent-entrypoint] Waiting for join token at ${TOKEN_FILE}..."

found=0
for i in $(seq 1 30); do
    if [ -s "$TOKEN_FILE" ]; then
        found=1
        break
    fi

    echo "  attempt ${i}/30 - token not present yet, retrying in 2s..."
    sleep 2
done

if [ "$found" -ne 1 ]; then
    echo "[agent-entrypoint] ERROR: join token file never appeared. Was spire-bootstrap successful?" >&2
    exit 1
fi

JOIN_TOKEN=$(cat "$TOKEN_FILE")

if [ -z "$JOIN_TOKEN" ]; then
    echo "[agent-entrypoint] ERROR: join token file is empty." >&2
    exit 1
fi

echo "[agent-entrypoint] Starting spire-agent..."

exec /opt/spire/bin/spire-agent run \
    -config /opt/spire/conf/agent/agent.conf \
    -joinToken "$JOIN_TOKEN"