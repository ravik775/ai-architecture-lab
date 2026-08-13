FROM ghcr.io/spiffe/spire-agent:1.9.6 AS spire

FROM alpine:3.20
RUN apk add --no-cache bash

COPY --from=spire /opt/spire/bin/spire-agent /opt/spire/bin/spire-agent
COPY entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

# Tried a non-root USER here too (same Semgrep dockerfile.security.missing-user-
# entrypoint finding as spire-server-registrar/Dockerfile) and actually tested
# it against the real stack: spire-agent crashed immediately on startup with
# "failed to open storage: ... agent-data.json: permission denied" - the named
# volume spire-agent-data was already populated by earlier root-owned runs, and
# a new non-root UID can't read/write files root created. This container also
# mounts /var/run/docker.sock (Docker workload attestor, "pid: host") and
# /shared/join_token.txt (written by the root spire-bootstrap container), both
# of which would need matching UID/GID work on top of a volume re-chown just to
# get this far - real fix, not a one-line USER add. Reverted rather than ship a
# container that crash-loops on every restart.
# nosemgrep: dockerfile.security.missing-user-entrypoint.missing-user-entrypoint
ENTRYPOINT ["/entrypoint.sh"]