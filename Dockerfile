FROM ghcr.io/xtls/xray-core:latest AS xray

FROM alpine:latest

RUN apk add --no-cache python3 dcron bash curl

COPY --from=xray /usr/local/bin/xray /usr/local/bin/xray

WORKDIR /mnt/xrayclient

COPY config/ ./config/
COPY scripts/ ./scripts/
COPY scripts/ /opt/xrayclient/
RUN chmod +x scripts/*.py /opt/xrayclient/*.py

RUN echo "0 */3 * * * python3 /mnt/xrayclient/scripts/update_xray_config.py --force >> /var/log/xray-update.log 2>&1" > /etc/crontabs/root

EXPOSE 10808

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
