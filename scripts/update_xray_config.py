#!/usr/bin/env python3
"""Xray config updater — fetches subscription, generates config with ping-based server selection."""

import json
import os
import sys
import shutil
import base64
import subprocess
import urllib.parse
from datetime import datetime
from hashlib import sha256

CONFIG_DIR = "/mnt/xrayclient/config"
SUBSCRIPTIONS_FILE = os.path.join(CONFIG_DIR, "subscriptions.txt")
USERS_FILE = os.path.join(CONFIG_DIR, "users.txt")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
BACKUP_DIR = os.path.join(CONFIG_DIR, "backups")
STATE_FILE = os.path.join(CONFIG_DIR, ".subscription_hash")


def parse_vless(url: str) -> dict:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "vless":
        raise ValueError(f"Not a vless URL")

    userinfo, hostport = parsed.netloc.rsplit("@", 1)
    uuid = userinfo
    host, port_str = hostport.rsplit(":", 1) if ":" in hostport else (hostport, "443")
    port = int(port_str)

    params = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    remark = urllib.parse.unquote(parsed.fragment or "")

    flow = params.get("flow", "")
    network = params.get("type", "tcp")
    security = params.get("security", "none")
    fp = params.get("fp", "")
    sni = params.get("sni", "")

    user = {"id": uuid, "encryption": params.get("encryption", "none")}
    if flow:
        user["flow"] = flow

    outbound = {
        "tag": "",
        "protocol": "vless",
        "settings": {
            "vnext": [{"address": host, "port": port, "users": [user]}]
        },
        "streamSettings": {
            "network": network,
            "security": security,
        },
    }

    if security == "reality":
        rs = {
            "show": False,
            "fingerprint": fp if fp else "chrome",
            "serverName": sni if sni else host,
            "publicKey": params.get("pbk", ""),
            "shortId": params.get("sid", ""),
        }
        spx = params.get("spx") or params.get("spiderX")
        if spx:
            rs["spiderX"] = spx
        outbound["streamSettings"]["realitySettings"] = rs

    elif security == "tls":
        ts = {"serverName": sni if sni else host}
        if fp:
            ts["fingerprint"] = fp
        if "alpn" in params:
            ts["alpn"] = [a.strip() for a in urllib.parse.unquote(params["alpn"]).split(",")]
        outbound["streamSettings"]["tlsSettings"] = ts

    elif security == "xtls":
        xs = {"serverName": sni if sni else host}
        if fp:
            xs["fingerprint"] = fp
        outbound["streamSettings"]["xtlsSettings"] = xs

    if network == "grpc":
        gs = {}
        if "serviceName" in params:
            gs["serviceName"] = params["serviceName"]
        if params.get("mode") == "multi":
            gs["multiMode"] = True
        outbound["streamSettings"]["grpcSettings"] = gs

    elif network == "ws":
        ws = {}
        if "path" in params:
            ws["path"] = params["path"]
        if "host" in params:
            ws["headers"] = {"Host": params["host"]}
        outbound["streamSettings"]["wsSettings"] = ws

    elif network == "kcp":
        ks = {}
        if "seed" in params:
            ks["seed"] = params["seed"]
        ht = params.get("headerType")
        if ht:
            ks["header"] = {"type": ht}
        outbound["streamSettings"]["kcpSettings"] = ks

    elif network == "http":
        hs = {}
        if "path" in params:
            hs["path"] = params["path"]
        if "host" in params:
            hs["host"] = [params["host"]]
        outbound["streamSettings"]["httpSettings"] = hs

    if security == "none":
        del outbound["streamSettings"]["security"]

    return outbound, remark


def read_subscription_urls() -> list[str]:
    if not os.path.exists(SUBSCRIPTIONS_FILE):
        print(f"Subscriptions file not found: {SUBSCRIPTIONS_FILE}", file=sys.stderr)
        sys.exit(1)
    urls = []
    with open(SUBSCRIPTIONS_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    if not urls:
        print(f"No subscription URLs found, generating config without servers", file=sys.stderr)
        return []
    return urls


def fetch_subscription(url: str) -> list[str]:
    result = subprocess.run(
        ["curl", "-sL", "--connect-timeout", "15", "--max-time", "30", url],
        capture_output=True, text=True, timeout=45
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl failed for {url}: {result.stderr}")
    data = result.stdout.strip()
    if not data:
        return []
    # Detect base64 (typical Xray subscription format)
    if not data.startswith("vless://") and not data.startswith("vmess://") and not data.startswith("trojan://") and not data.startswith("ss://"):
        try:
            decoded = base64.b64decode(data).decode("utf-8")
            lines = [l.strip() for l in decoded.splitlines() if l.strip()]
            if any(l.startswith(("vless://", "vmess://", "trojan://", "ss://")) for l in lines):
                return lines
        except Exception:
            pass
    return [l.strip() for l in data.splitlines() if l.strip()]


def content_hash(lines: list[str]) -> str:
    return sha256("\n".join(lines).encode()).hexdigest()


def read_users() -> list[dict]:
    if not os.path.exists(USERS_FILE):
        return []
    users = []
    with open(USERS_FILE) as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if ":" in s:
                user, _, passwd = s.partition(":")
                users.append({"user": user.strip(), "pass": passwd.strip()})
    return users


def generate_config(outbounds: list) -> dict:
    socks_settings = {"udp": True}
    users = read_users()
    if users:
        socks_settings["auth"] = "password"
        socks_settings["accounts"] = users
    else:
        socks_settings["auth"] = "noauth"

    config = {
        "log": {"loglevel": "warning"},
        "observatory": {
            "subjectSelector": ["server-"],
            "probeUrl": "https://www.gstatic.com/generate_204",
            "probeInterval": "60s",
            "enableConcurrency": True,
        },
        "inbounds": [
            {
                "listen": "0.0.0.0",
                "port": 10808,
                "protocol": "socks",
                "settings": socks_settings,
            }
        ],
        "outbounds": [],
        "routing": {
            "domainStrategy": "AsIs",
            "balancers": [{"tag": "best-ping", "selector": ["server-"]}],
            "rules": [{"type": "field", "network": "tcp,udp", "balancerTag": "best-ping"}],
        },
    }
    for i, ob in enumerate(outbounds):
        ob["tag"] = f"server-{i}"
        config["outbounds"].append(ob)
    config["outbounds"].append({"tag": "direct", "protocol": "freedom"})
    config["outbounds"].append({"tag": "block", "protocol": "blackhole"})
    return config


def install_cron():
    cron_line = f"0 0 */3 * * {sys.argv[0]} >> /var/log/xray-update.log 2>&1"
    existing = ""
    try:
        existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    except Exception:
        pass
    if cron_line in existing:
        print("Cron job already exists")
        return
    new_cron = existing.strip() + "\n" + cron_line + "\n" if existing.strip() else cron_line + "\n"
    proc = subprocess.run(["crontab"], input=new_cron, capture_output=True, text=True)
    if proc.returncode == 0:
        print("Cron job installed (runs at 00:00 every 3 days)")
    else:
        print(f"Failed to install cron: {proc.stderr}", file=sys.stderr)


def main():
    if "--install-cron" in sys.argv:
        install_cron()
        return

    urls = read_subscription_urls()

    all_lines = []
    for url in urls:
        print(f"Fetching {url}")
        try:
            all_lines.extend(fetch_subscription(url))
        except Exception as e:
            print(f"Warning: failed to fetch {url}: {e}", file=sys.stderr)

    old_hash = ""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            old_hash = f.read().strip()

    new_hash = content_hash(all_lines)
    if new_hash == old_hash and not "--force" in sys.argv:
        print("Subscription unchanged, skipping update")
        return

    seen = set()
    outbounds = []
    for line in all_lines:
        if not line.startswith("vless://"):
            continue
        try:
            ob, _ = parse_vless(line)
            addr = ob["settings"]["vnext"][0]["address"]
            port = ob["settings"]["vnext"][0]["port"]
            key = f"{addr}:{port}"
            if key not in seen:
                seen.add(key)
                outbounds.append(ob)
        except Exception as e:
            print(f"Warning: parse error: {e}", file=sys.stderr)

    if outbounds:
        print(f"Subscription: {len(outbounds)} servers")
    else:
        print("No servers from subscriptions, generating config with auth only", file=sys.stderr)

    config = generate_config(outbounds)

    os.makedirs(BACKUP_DIR, exist_ok=True)
    if os.path.exists(CONFIG_PATH):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(CONFIG_PATH, f"{BACKUP_DIR}/config.json.{ts}")

    backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith("config.json.")])
    while len(backups) > 30:
        os.remove(os.path.join(BACKUP_DIR, backups.pop(0)))

    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    with open(STATE_FILE, "w") as f:
        f.write(new_hash)

    print(f"Config written to {CONFIG_PATH} ({len(outbounds)} outbounds, best-ping balancer active)")


if __name__ == "__main__":
    main()
