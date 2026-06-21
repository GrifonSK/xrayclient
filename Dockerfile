FROM alpine:latest

RUN apk add --no-cache curl python3 dcron bash

ARG XRAY_VERSION=25.3.6
RUN curl -sL https://github.com/XTLS/Xray-core/releases/download/v${XRAY_VERSION}/Xray-linux-64.zip -o /tmp/xray.zip && \
    unzip /tmp/xray.zip -d /usr/local/bin/ && \
    rm /tmp/xray.zip && \
    chmod +x /usr/local/bin/xray

WORKDIR /mnt/xrayclient

COPY config.json subscriptions.txt ./
COPY update_xray_config.py server.py index.html ./
RUN chmod +x update_xray_config.py server.py

RUN echo "0 */3 * * * python3 /mnt/xrayclient/update_xray_config.py --force >> /var/log/xray-update.log 2>&1" > /etc/crontabs/root

EXPOSE 10808

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
