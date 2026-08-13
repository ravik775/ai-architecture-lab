FROM ghcr.io/spiffe/spire-server:1.9.6 AS spire

FROM alpine:3.20
RUN apk add --no-cache bash
COPY --from=spire /opt/spire/bin/spire-server /opt/spire/bin/spire-server
COPY bootstrap.sh /bootstrap.sh
RUN chmod +x /bootstrap.sh
ENTRYPOINT ["/bootstrap.sh"]
# Same finding as spire-server-registrar/Dockerfile (missing non-root USER),
# same reason left unfixed: this container connects to spire-server's admin
# socket exactly the same way, and the identical fix was verified to break
# that connection when tested against the registrar (see its Dockerfile for
# the full test). Not re-tested separately here since the failure mode is
# architecturally identical - same root-owned socket, same non-root sidecar
# pattern - not applying an already-disproven fix a second time.