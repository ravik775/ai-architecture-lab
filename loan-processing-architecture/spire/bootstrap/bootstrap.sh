#!/bin/bash
set -euo pipefail

SOCKET_PATH="/tmp/spire-server/private/api.sock"
TOKEN_FILE="/shared/join_token.txt"
BIN="/opt/spire/bin/spire-server"
TRUST_DOMAIN="example.org"
PARENT_ID="spiffe://${TRUST_DOMAIN}/agent"

echo "[bootstrap] Waiting for spire-server admin API at ${SOCKET_PATH}..."

ready=0
for i in $(seq 1 30); do
    if "$BIN" entry show -socketPath "$SOCKET_PATH" >/dev/null 2>&1; then
        ready=1
        echo "[bootstrap] spire-server is ready (attempt ${i})."
        break
    fi

    echo "  attempt ${i}/30 - not ready yet, retrying in 2s..."
    sleep 2
done

if [ "$ready" -ne 1 ]; then
    echo "[bootstrap] ERROR: spire-server admin API never responded." >&2
    exit 1
fi

echo "[bootstrap] Generating join token for ${PARENT_ID}..."

TOKEN_OUTPUT=$("$BIN" token generate -spiffeID "$PARENT_ID" -socketPath "$SOCKET_PATH" 2>&1) \
    || { echo "[bootstrap] ERROR: token generate failed:"; echo "$TOKEN_OUTPUT" >&2; exit 1; }

echo "$TOKEN_OUTPUT"

JOIN_TOKEN=$(echo "$TOKEN_OUTPUT" | grep -oE 'Token:\s*\S+' | awk '{print $2}')

if [ -z "$JOIN_TOKEN" ]; then
    echo "[bootstrap] ERROR: could not parse join token from output above." >&2
    exit 1
fi

echo -n "$JOIN_TOKEN" > "$TOKEN_FILE"
echo "[bootstrap] Join token written to ${TOKEN_FILE}."

delete_existing_entries_for_spiffe_id() {
    local spiffe_id="$1"

    echo "[bootstrap] Checking existing entries for ${spiffe_id}..."

    local entry_ids
    entry_ids=$("$BIN" entry show \
        -socketPath "$SOCKET_PATH" \
        -spiffeID "$spiffe_id" 2>/dev/null \
        | awk '/Entry ID/ { print $4 }' || true)

    if [ -z "$entry_ids" ]; then
        echo "[bootstrap] No existing entries found for ${spiffe_id}."
        return 0
    fi

    for entry_id in $entry_ids; do
        echo "[bootstrap] Deleting old entry ${entry_id} for ${spiffe_id}..."
        "$BIN" entry delete \
            -socketPath "$SOCKET_PATH" \
            -entryID "$entry_id"
    done
}

create_entry() {
    local spiffe_id="$1"
    local selector="$2"
    local dns_name="$3"

    echo "[bootstrap] Creating entry for ${spiffe_id} (selector: ${selector}, dns: ${dns_name})..."

    "$BIN" entry create \
        -socketPath "$SOCKET_PATH" \
        -spiffeID "$spiffe_id" \
        -parentID "$PARENT_ID" \
        -selector "$selector" \
        -dns "$dns_name"
}

LOAN_SPIFFE_ID="spiffe://${TRUST_DOMAIN}/ns/loan/sa/loan-service"
GATEWAY_SPIFFE_ID="spiffe://${TRUST_DOMAIN}/ns/loan/sa/api-gateway"

delete_existing_entries_for_spiffe_id "$LOAN_SPIFFE_ID"
delete_existing_entries_for_spiffe_id "$GATEWAY_SPIFFE_ID"

create_entry "$LOAN_SPIFFE_ID" "unix:uid:10001" "loan-service"
create_entry "$GATEWAY_SPIFFE_ID" "unix:uid:10002" "api-gateway"

echo "[bootstrap] Done. Registration entries:"
"$BIN" entry show -socketPath "$SOCKET_PATH"

exit 0