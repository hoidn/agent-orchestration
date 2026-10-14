"""Throwaway F4 driver: provider CLI in the profile -> relay -> gateway stub on a bound unix socket."""
import json, os, secrets, socketserver, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from profile import ensure_delegated, Slot, Holder
ensure_delegated(sys.argv)
import image_import

CODEX = Path(sys.argv[2])
CLAUDE = Path(sys.argv[3])
MODEL_ROUTES = {("POST", "/v1/responses"), ("POST", "/v1/messages")}
TOKEN = secrets.token_hex(16)   # per-attempt capability; no permanent credential exists on this host
log = []


class Gateway(BaseHTTPRequestHandler):
    def _handle(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(min(length, 1 << 20))
        presented = (self.headers.get("Authorization", "").removeprefix("Bearer ")
                     or self.headers.get("x-api-key", ""))
        route = (self.command, self.path.split("?")[0])
        row = {"route": route, "token_ok": secrets.compare_digest(presented, TOKEN),
               "user_agent": self.headers.get("User-Agent", "")[:60], "body_bytes": len(body)}
        if not row["token_ok"]:
            code, reply = 401, {"error": "attempt_capability_invalid"}
        elif route not in MODEL_ROUTES:
            code, reply = 403, {"error": "route_not_admitted"}
        else:
            row["model"] = json.loads(body or b"{}").get("model")
            code, reply = 502, {"error": {"message": "upstream_blocked: no API-key account", "type": "upstream_blocked"}}
        row["status"] = code
        log.append(row)
        data = json.dumps(reply).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    do_GET = do_POST = do_PUT = do_CONNECT = _handle
    def log_message(self, *args):
        pass
    def address_string(self):
        return "unix"


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


record = json.loads(Path(sys.argv[1]).read_text())
rootfs = image_import.admit(record)
work = Path(tempfile.mkdtemp(prefix="runref-f4-"))
gateway_dir = work / "gateway"
gateway_dir.mkdir(mode=0o700)
server = Server(str(gateway_dir / "gateway.sock"), Gateway)
threading.Thread(target=server.serve_forever, daemon=True).start()
(work / "result").mkdir()
slot = Slot("attempt-f4", memory_mib=1024, pids=256, cpus=2)
extra = ("--bind", str(gateway_dir / "gateway.sock"), "/run/gateway.sock", "--tmpfs", "/opt",
         "--ro-bind", str(CODEX), "/opt/provider/codex", "--ro-bind", str(CLAUDE), "/opt/provider/claude",
         "--ro-bind", str(HERE / "relay.py"), "/opt/provider/relay.py")
holder = Holder(slot, rootfs, work / "result", work / "ipc", workspace_mib=64, scratch_mib=256, extra=extra)
evidence = {"image": record["image"], "codex": str(CODEX), "claude": str(CLAUDE)}
relay = "/usr/local/bin/python3.12 /opt/provider/relay.py 8080 /run/gateway.sock & sleep 0.3; "
try:
    codex = (relay + "mkdir -p /tmp/codex-home; CODEX_HOME=/tmp/codex-home /opt/provider/codex exec --skip-git-repo-check "
             "--ephemeral --dangerously-bypass-approvals-and-sandbox "
             "-c model_provider=gw -c 'model_providers.gw={name=\"gw\", base_url=\"http://127.0.0.1:8080/v1\", "
             "env_key=\"RUNREF_GATEWAY_TOKEN\", wire_api=\"responses\", request_max_retries=0, stream_max_retries=0}' "
             "-m gpt-5 'reply with OK' < /dev/null")
    evidence["codex"] = holder.leaf("codex", ["/bin/sh", "-c", codex], env={"RUNREF_GATEWAY_TOKEN": TOKEN}, timeout=60)
    evidence["codex"]["gateway_rows"] = list(log); log.clear()
    claude = (relay + "/opt/provider/claude -p 'reply with OK' --model claude-sonnet-4-5 --max-turns 1")
    evidence["claude"] = holder.leaf("claude", ["/bin/sh", "-c", claude], env={
        "ANTHROPIC_BASE_URL": "http://127.0.0.1:8080", "ANTHROPIC_API_KEY": TOKEN,
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "DISABLE_TELEMETRY": "1"}, timeout=60)
    evidence["claude"]["gateway_rows"] = list(log); log.clear()
    probe = (relay + "/usr/local/bin/python3.12 -c \"\n"
             "import json, os, socket, urllib.request, urllib.error\n"
             "def go(method, path, token):\n"
             "  req = urllib.request.Request('http://127.0.0.1:8080' + path, method=method, data=b'{}' if method == 'POST' else None,\n"
             "                               headers={'Authorization': 'Bearer ' + token})\n"
             "  try: return urllib.request.urlopen(req, timeout=5).status\n"
             "  except urllib.error.HTTPError as e: return e.code\n"
             "t = os.environ['RUNREF_GATEWAY_TOKEN']\n"
             "out = {'admin_route': go('GET', '/admin/keys', t), 'models_list': go('GET', '/v1/models', t),\n"
             "       'wrong_token': go('POST', '/v1/responses', 'stolen'), 'model_route': go('POST', '/v1/responses', t)}\n"
             "try: socket.create_connection(('api.openai.com', 443), timeout=3); out['direct'] = 'connected'\n"
             "except OSError as e: out['direct'] = type(e).__name__ + ':' + str(e.errno)\n"
             "out['credential_files'] = [p for p in ('/root/.codex/auth.json', '/tmp/codex-home/auth.json', '"
             + os.path.expanduser("~/.codex/auth.json") + "', '" + os.path.expanduser("~/.claude/.credentials.json")
             + "') if os.path.exists(p)]\n"
             "out['env_names'] = sorted(os.environ)\n"
             "print(json.dumps(out))\"")
    evidence["policy_probe"] = holder.leaf("probe", ["/bin/sh", "-c", probe], env={"RUNREF_GATEWAY_TOKEN": TOKEN}, timeout=30)
    evidence["policy_probe"]["gateway_rows"] = list(log)
finally:
    holder.stop()
    slot.remove()
    server.shutdown()
for leaf in ("codex", "claude"):
    evidence[leaf]["stdout"] = evidence[leaf]["stdout"][-1500:]
    evidence[leaf]["stderr"] = evidence[leaf]["stderr"][-1500:].replace(TOKEN, "<attempt-token>")
print(json.dumps(evidence, indent=1, default=str).replace(TOKEN, "<attempt-token>"))
