"""Allowlist and relay probe, run inside the agent container as a scratch task's reference solution (oracle agent).

Usage: python3 allowlist_probe.py <relay host:port> <host address> <comma-separated host ports>
Prints one line per case: `ok ...` or `refused <error class>: <detail>`. A connect alone proves nothing (the
egress proxy accepts, then drops), so every case sends a request and reads the answer; the sidecar's egress
log tells a proxy denial (`bypass`) from a refused upstream connection.
"""

import os
import socket
import ssl
import sys
import urllib.request

RELAY, HOST_IP, PORTS = sys.argv[1], sys.argv[2], [int(p) for p in sys.argv[3].split(",") if p]


def _url(url):
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return f"ok {resp.status}"
    except urllib.error.HTTPError as exc:
        return f"ok {exc.code}"
    except Exception as exc:  # the class of a refusal is the finding
        return f"refused {type(exc).__name__}: {exc}"


def _poke(ip, port):
    """Send a line to a TCP port and report what comes back: data, EOF, a timeout or an error."""
    try:
        with socket.create_connection((ip, port), timeout=5) as sock:
            sock.settimeout(3)
            sock.sendall(b"GET / HTTP/1.0\r\n\r\n")
            data = sock.recv(64)
            return f"ok data {data[:40]!r}" if data else "refused EOF"
    except socket.timeout:
        return "silent (timeout: connected, nothing read)"
    except Exception as exc:  # the class of a refusal is the finding
        return f"refused {type(exc).__name__}"


def _misrouted(name, address_of, tls):
    """Send a request that names `name` to the address of `address_of`."""
    try:
        ip = socket.gethostbyname(address_of)
        sock = socket.create_connection((ip, 443 if tls else 80), timeout=15)
        if tls:
            ctx = ssl.create_default_context()
            ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
            sock = ctx.wrap_socket(sock, server_hostname=name)
        sock.sendall(f"GET / HTTP/1.1\r\nHost: {name}\r\nConnection: close\r\n\r\n".encode())
        lines = sock.recv(2000).decode(errors="replace").split("\r\n")
        keep = [ln for ln in lines[1:] if ln.lower().startswith(("server:", "location:", "x-served-by:"))]
        return f"ok via {ip}: {[lines[0], *keep]!r}" if lines[0] else f"refused empty reply via {ip}"
    except Exception as exc:  # the class of a refusal is the finding
        return f"refused {type(exc).__name__}: {exc}"


def _resolve(name):
    try:
        return socket.gethostbyname(name)
    except OSError as exc:
        return f"unresolved ({exc})"


def _gateway():
    with open("/proc/net/route") as fh:
        for line in fh.readlines()[1:]:
            fields = line.split()
            if fields[1] == "00000000":
                return socket.inet_ntoa(bytes.fromhex(fields[2])[::-1])
    return None


def main():
    print(f"PROBE socket dir /run/lh present: {os.path.exists('/run/lh')}", flush=True)
    for name in ("relay", "host.containers.internal", "api.anthropic.com"):
        print(f"PROBE resolve {name}: {_resolve(name)}", flush=True)
    for case, url in [("allowed index", "https://pypi.org/simple/pip/"), ("code host", "https://github.com/"),
                      ("vendor api", "https://api.anthropic.com/v1/messages"),
                      ("relay", f"http://{RELAY}/allowlist-probe")]:
        print(f"PROBE {case}: {_url(url)}", flush=True)
    for case, args in [("allowed name, denied address (TLS)", ("pypi.org", "github.com", True)),
                       ("allowed name, denied address (HTTP)", ("pypi.org", "example.com", False))]:
        print(f"PROBE {case}: {_misrouted(*args)}", flush=True)
    targets = {HOST_IP, _gateway(), _resolve("host.containers.internal"), "10.0.2.2"}
    for ip in sorted(t for t in targets if t and t[0].isdigit()):
        results = {port: _poke(ip, port) for port in PORTS}
        answered = {p: r for p, r in results.items() if not r.startswith("refused")}
        print(f"PROBE host scan {ip}: {len(PORTS)} ports, answered {answered or 'none'}", flush=True)


main()
