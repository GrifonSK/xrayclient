#!/usr/bin/env python3
"""HTTP server for managing Xray subscriptions via browser."""

import concurrent.futures
import http.server
import json
import os
import socket
import subprocess
import sys
import urllib.parse

HOST = "0.0.0.0"
PORT = 8080
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SUBS_FILE = os.path.join(BASE_DIR, "subscriptions.txt")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
USERS_FILE = os.path.join(BASE_DIR, "users.txt")
UPDATE_SCRIPT = os.path.join(BASE_DIR, "update_xray_config.py")


def read_servers():
    if not os.path.exists(CONFIG_FILE):
        return []
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
    except Exception:
        return []
    servers = []
    for ob in cfg.get("outbounds", []):
        tag = ob.get("tag", "")
        if not tag.startswith("server-"):
            continue
        vnext = ob.get("settings", {}).get("vnext", [])
        if not vnext:
            continue
        addr = vnext[0].get("address", "")
        port = vnext[0].get("port", 0)
        protocol = ob.get("protocol", "")
        servers.append({"tag": tag, "address": addr, "port": port, "protocol": protocol})
    return servers


def check_reachable(addr, port, timeout=3):
    try:
        sock = socket.create_connection((addr, port), timeout=timeout)
        sock.close()
        return True
    except Exception:
        return False


def read_entries():
    if not os.path.exists(SUBS_FILE):
        return []
    entries = []
    with open(SUBS_FILE) as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("# Xray"):
                continue
            if s.startswith("# "):
                entries.append({"url": s[2:].strip(), "enabled": False})
            elif s.startswith("#"):
                entries.append({"url": s[1:].strip(), "enabled": False})
            else:
                entries.append({"url": s, "enabled": True})
    return entries


def write_entries(entries):
    with open(SUBS_FILE, "w") as f:
        f.write("# Xray subscription URLs (one per line)\n")
        for e in entries:
            if e["enabled"]:
                f.write(e["url"] + "\n")
            else:
                f.write("# " + e["url"] + "\n")


def read_users():
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


def write_users(users):
    with open(USERS_FILE, "w") as f:
        f.write("# SOCKS5 users (user:pass one per line)\n")
        for u in users:
            f.write(f"{u['user']}:{u['pass']}\n")


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/subscriptions":
            self.send_json(read_entries())
            return
        if parsed.path == "/api/users":
            self.send_json(read_users())
            return
        if parsed.path == "/api/servers":
            servers = read_servers()
            with concurrent.futures.ThreadPoolExecutor(max_workers=30) as pool:
                futures = {
                    pool.submit(check_reachable, s["address"], s["port"]): s
                    for s in servers
                }
                for f in concurrent.futures.as_completed(futures):
                    futures[f]["reachable"] = f.result()
            self.send_json(servers)
            return
        if parsed.path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/subscriptions":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            url = body.get("url", "").strip()
            if not url.startswith(("http://", "https://", "vless://", "vmess://", "trojan://", "ss://")):
                self.send_error(400, "Invalid URL")
                return
            entries = read_entries()
            existing_urls = {e["url"] for e in entries}
            if url in existing_urls:
                self.send_error(409, "Already exists")
                return
            entries.append({"url": url, "enabled": True})
            write_entries(entries)
            self.send_json({"ok": True})
            return

        if parsed.path == "/api/users":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            username = body.get("user", "").strip()
            password = body.get("pass", "").strip()
            if not username or not password:
                self.send_error(400, "Invalid credentials")
                return
            users = read_users()
            for u in users:
                if u["user"] == username:
                    self.send_error(409, "User already exists")
                    return
            users.append({"user": username, "pass": password})
            write_users(users)
            self.send_json({"ok": True})
            return

        if parsed.path == "/api/update":
            script = UPDATE_SCRIPT
            if not os.path.exists(script):
                self.send_error(500, "update_xray_config.py not found")
                return
            try:
                result = subprocess.run(
                    [sys.executable, script, "--force"],
                    capture_output=True, text=True, timeout=120,
                )
                output = result.stdout + result.stderr
                if result.returncode == 0:
                    self.send_json({"ok": True, "output": output})
                else:
                    self.send_json({"ok": False, "output": output}, status=500)
            except subprocess.TimeoutExpired:
                self.send_error(504, "Script timed out")
            except Exception as e:
                self.send_error(500, str(e))
            return

        self.send_error(404)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        parts = parsed.path.rstrip("/").split("/")
        if len(parts) == 4 and parts[1:3] == ["api", "subscriptions"]:
            try:
                index = int(parts[3])
            except ValueError:
                self.send_error(400, "Invalid index")
                return
            entries = read_entries()
            if index < 0 or index >= len(entries):
                self.send_error(404, "Index out of range")
                return
            entries.pop(index)
            write_entries(entries)
            self.send_json({"ok": True})
            return
        if len(parts) == 4 and parts[1:3] == ["api", "users"]:
            try:
                index = int(parts[3])
            except ValueError:
                self.send_error(400, "Invalid index")
                return
            users = read_users()
            if index < 0 or index >= len(users):
                self.send_error(404, "Index out of range")
                return
            users.pop(index)
            write_users(users)
            self.send_json({"ok": True})
            return
        self.send_error(404)

    def do_PATCH(self):
        parsed = urllib.parse.urlparse(self.path)
        parts = parsed.path.rstrip("/").split("/")
        if len(parts) == 5 and parts[1:4] == ["api", "subscriptions", "toggle"]:
            try:
                index = int(parts[4])
            except ValueError:
                self.send_error(400, "Invalid index")
                return
            entries = read_entries()
            if index < 0 or index >= len(entries):
                self.send_error(404, "Index out of range")
                return
            entries[index]["enabled"] = not entries[index]["enabled"]
            write_entries(entries)
            self.send_json({"ok": True, "enabled": entries[index]["enabled"]})
            return
        self.send_error(404)

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {args[0]}", flush=True)


if __name__ == "__main__":
    os.chdir(BASE_DIR)
    server = http.server.HTTPServer((HOST, PORT), Handler)
    print(f"Server running at http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down")
        server.server_close()
