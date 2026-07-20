FROM ghcr.io/spiffe/spire-agent:1.9.6 AS spire

FROM alpine:3.20
RUN apk add --no-cache bash

COPY --from=spire /opt/spire/bin/spire-agent /opt/spire/bin/spire-agent
COPY entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]