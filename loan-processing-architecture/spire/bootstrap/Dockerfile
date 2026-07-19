FROM ghcr.io/spiffe/spire-server:1.9.6 AS spire

FROM alpine:3.20
RUN apk add --no-cache bash
COPY --from=spire /opt/spire/bin/spire-server /opt/spire/bin/spire-server
COPY bootstrap.sh /bootstrap.sh
RUN chmod +x /bootstrap.sh
ENTRYPOINT ["/bootstrap.sh"]