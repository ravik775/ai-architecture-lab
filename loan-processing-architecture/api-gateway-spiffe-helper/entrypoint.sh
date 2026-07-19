#!/bin/sh
set -eu

mkdir -p /spiffe-certs
chown -R "${SPIFFE_UID}:${SPIFFE_GID}" /spiffe-certs

exec su-exec "${SPIFFE_UID}:${SPIFFE_GID}" \
  /usr/local/bin/spiffe-helper -config /etc/spiffe-helper/helper.conf