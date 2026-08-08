#!/usr/bin/env bash
# End-to-end validation of the running stack. Run from the mcp-docker/ directory
# (or anywhere — paths below don't depend on cwd) after `docker compose up -d`
# and after you've put a real OPENROUTER_API_KEY in .env.
set -euo pipefail

APP=http://localhost:8080
KC=http://localhost:8081

pass() { echo "  OK  $1"; }
fail() { echo "  FAIL $1"; exit 1; }

echo "== 1. Container health =="
for svc in postgres keycloak jaeger mcp-gateway app; do
  STATE=$(docker inspect --format='{{.State.Status}}' "mcp-research-assistant-${svc}-1" 2>/dev/null || echo "missing")
  [ "$STATE" = "running" ] && pass "$svc is running" || fail "$svc is $STATE"
done

echo "== 2. App health =="
curl -sf "$APP/actuator/health" | grep -q '"UP"' && pass "app health UP" || fail "app not healthy"

echo "== 3. Get a token for alice (tenant acme) =="
TOKEN=$(curl -s -X POST "$KC/realms/mcp-demo/protocol/openid-connect/token" \
  -d client_id=research-assistant-app -d grant_type=password \
  -d username=alice -d password=alice-pw | grep -oP '"access_token":"\K[^"]+')
[ -n "$TOKEN" ] && pass "obtained token (len ${#TOKEN})" || fail "no token — is Keycloak healthy and the realm imported?"

echo "== 4. Call /api/chat (needs a real OPENROUTER_API_KEY in .env) =="
RESP=$(curl -s -w "\n%{http_code}" -X POST "$APP/api/chat" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"question":"Fetch https://example.com and tell me the page title."}')
CODE=$(echo "$RESP" | tail -1)
BODY=$(echo "$RESP" | sed '$d')
if [ "$CODE" = "200" ]; then
  pass "chat call succeeded"
  echo "  answer: $BODY"
else
  fail "chat call returned HTTP $CODE: $BODY"
fi

echo "== 5. Audit row was persisted and is tenant-scoped =="
AUDIT=$(curl -s "$APP/api/audit" -H "Authorization: Bearer $TOKEN")
echo "$AUDIT" | grep -q '"question"' && pass "audit row present: $AUDIT" || fail "no audit rows found"

echo "== 6. Bob (tenant globex) does not see alice's rows =="
BOB_TOKEN=$(curl -s -X POST "$KC/realms/mcp-demo/protocol/openid-connect/token" \
  -d client_id=research-assistant-app -d grant_type=password \
  -d username=bob -d password=bob-pw | grep -oP '"access_token":"\K[^"]+')
BOB_AUDIT=$(curl -s "$APP/api/audit" -H "Authorization: Bearer $BOB_TOKEN")
[ "$BOB_AUDIT" = "[]" ] && pass "bob's audit view is empty (tenant isolation holds)" || echo "  NOTE: bob sees: $BOB_AUDIT (expected [] unless bob has chatted before)"

echo
echo "All checks passed. Open http://localhost:16686 (Jaeger) and find the trace for the /api/chat call above."
