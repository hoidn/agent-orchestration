"""Allowlist probe, run inside the agent container as a scratch task's reference solution (oracle agent).

Usage: python3 allowlist_probe.py <host listener ip> <port>
Prints one line per request: the case, then `ok <status>` or `refused <error class>: <detail>`.
A connect alone proves nothing (the egress proxy accepts, then drops), so every case sends a request.
"""

import socket
import ssl
import sys
import urllib.request

HOST_IP, PORT = sys.argv[1], int(sys.argv[2])
CASES = [
    ("allowed index", "https://pypi.org/simple/pip/", None),
    ("allowed index files", "https://files.pythonhosted.org/", None),
    ("code host", "https://github.com/", None),
    ("vendor api", "https://api.anthropic.com/v1/messages", None),
    ("host listener", f"http://{HOST_IP}:{PORT}/allowlist-probe", None),
    ("allowed name, denied address (TLS)", "pypi.org", "github.com"),
    ("allowed name, denied address (HTTP)", "pypi.org", "example.com"),
]


def _url(url):
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return f"ok {resp.status}"
    except urllib.error.HTTPError as exc:
        return f"ok {exc.code}"
    except Exception as exc:  # the class of a refusal is the finding
        return f"refused {type(exc).__name__}: {exc}"


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


for case, target, other in CASES:
    result = _url(target) if other is None else _misrouted(target, other, "TLS" in case)
    print(f"PROBE {case}: {result}", flush=True)
