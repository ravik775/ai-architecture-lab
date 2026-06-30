#!/usr/bin/env bash
set -euo pipefail
RESP=$(curl -s -X POST http://localhost:8080/loans -H "Content-Type: application/json" -d '{"customerId":"CUST-1001","customerName":"Ravi","amount":500000}')
echo "$RESP"
APP_ID=$(echo "$RESP" | sed -n 's/.*"applicationId":"\([^"]*\)".*/\1/p')
echo "Checking status for $APP_ID"
curl -s http://localhost:8080/loans/$APP_ID/status && echo
