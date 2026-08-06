#!/usr/bin/env bash
# Generates a self-signed CA + one server cert (otel-collector, also used
# for its Prometheus exporter) + one client cert (the app) for local mTLS.
#
# Concept, not a production PKI: single shared CA, no intermediate, long
# validity, no rotation/revocation story. That's the right amount of
# complexity for "prove the wiring works end to end" - see README "TLS /
# mTLS" for what a real deployment should replace this with (cert-manager
# + short-lived certs, or a managed CA).
#
# Usage: ./certs/generate-certs.sh   (run from the repo root or this dir)
set -euo pipefail
cd "$(dirname "$0")"

DAYS=825  # ~2yr, matches common CA/Browser Forum guidance for the leaf certs

if [ -f ca.key ]; then
  echo "certs/ already generated (ca.key exists). Delete certs/*.key certs/*.crt first if you want to regenerate."
  exit 0
fi

echo "== Generating CA =="
openssl genrsa -out ca.key 4096
openssl req -x509 -new -nodes -key ca.key -sha256 -days "$DAYS" \
  -subj "/O=genai-observability-service/CN=genai-observability-local-ca" \
  -out ca.crt

echo "== Generating server cert (otel-collector) =="
openssl genrsa -out collector.key 2048
openssl req -new -key collector.key \
  -subj "/O=genai-observability-service/CN=otel-collector" \
  -out collector.csr
openssl x509 -req -in collector.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -days "$DAYS" -sha256 \
  -extfile <(printf "subjectAltName=DNS:otel-collector,DNS:localhost") \
  -out collector.crt
rm -f collector.csr || true

echo "== Generating client cert (app) =="
openssl genrsa -out app.key 2048
openssl req -new -key app.key \
  -subj "/O=genai-observability-service/CN=genai-observability-app" \
  -out app.csr
openssl x509 -req -in app.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -days "$DAYS" -sha256 \
  -out app.crt
rm -f app.csr || true

chmod 644 ca.crt collector.crt app.crt || true
chmod 600 ca.key collector.key app.key || true

echo
echo "Done. Files written to $(pwd):"
ls -1 ca.crt ca.key collector.crt collector.key app.crt app.key
echo
echo "Next: docker compose -f docker-compose.yml -f docker-compose.tls.yml up --build"
