FROM ghcr.io/spiffe/spiffe-helper:0.9.0 AS spiffe-helper

FROM alpine:3.20

ARG SPIFFE_UID=10002
ARG SPIFFE_GID=10002

RUN apk add --no-cache bash su-exec \
    && addgroup -g ${SPIFFE_GID} spiffe \
    && adduser -D -u ${SPIFFE_UID} -G spiffe spiffe \
    && mkdir -p /spiffe-certs

COPY --from=spiffe-helper /spiffe-helper /usr/local/bin/spiffe-helper
COPY helper.conf /etc/spiffe-helper/helper.conf
COPY entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

ENV SPIFFE_UID=${SPIFFE_UID}
ENV SPIFFE_GID=${SPIFFE_GID}

ENTRYPOINT ["/entrypoint.sh"]