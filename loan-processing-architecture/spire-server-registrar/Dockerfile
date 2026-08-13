FROM ghcr.io/spiffe/spire-server:1.9.6 AS spire

FROM alpine:3.20
RUN apk add --no-cache bash
COPY --from=spire /opt/spire/bin/spire-server /opt/spire/bin/spire-server
# Tried a non-root USER here (Semgrep dockerfile.security.missing-user-entrypoint
# flagged this) and tested it against the real cluster: the registrar could
# no longer connect to spire-server's admin socket at all - waited 2+
# minutes past the point it normally connects in under 5 seconds, with no
# error, no progress, nothing. The socket is created by the main
# spire-server container (root) with permissions that don't extend to a
# different UID in the sidecar container. Reverted rather than ship an
# untested "fix" that silently breaks registration - a working root
# container beats a broken non-root one. Worth revisiting with a shared
# GID/setgid approach if this needs closing later.
