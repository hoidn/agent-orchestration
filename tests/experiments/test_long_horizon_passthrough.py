"""The long-horizon passthrough's first slice, its token scanner and the live probe script
(`experiments/long_horizon_tasks/passthrough.py`, `token_scan.py`, `live_probe.sh`; plan Task 4).

The upstream is `stub_api.py` on a unix socket, or a canned upstream in this file where a test needs exact
bytes or a response the stub has no scenario for. Every token is a made-up string written by the test into
a mode-600 file inside a mode-700 directory; no request leaves the machine and no real CLI runs.
"""

from __future__ import annotations

import http.client
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import socketserver
import stat
import subprocess
import sys
import tempfile
import threading
import time

import pytest

REPO = Path(__file__).resolve().parents[2]
KIT = REPO / "experiments" / "long_horizon_tasks"
MODEL = "claude-haiku-5-5"
MESSAGES = "/v1/messages?beta=true"
WAIT = 60  # seconds; the machine is shared and heavily loaded


def _load(name):
    spec = importlib.util.spec_from_file_location(f"lh_{name}", KIT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


token_scan = _load("token_scan")


def _token():
    """A made-up token: 108 characters of the base64url alphabet."""
    return secrets.token_urlsafe(81)


@pytest.fixture
def short():
    """A mode-700 directory with a short path (AF_UNIX paths stop at 108 bytes)."""
    path = Path(tempfile.mkdtemp(prefix="lhp", dir="/tmp"))
    yield path
    for root, dirs, _ in os.walk(path):
        for d in dirs:
            os.chmod(os.path.join(root, d), 0o700)
    shutil.rmtree(path)


def _scan(*args):
    return subprocess.run([sys.executable, "-I", str(KIT / "token_scan.py"), *map(str, args)],
                          capture_output=True, text=True, timeout=WAIT)


def _fingerprint_file(directory, token):
    path = directory / "fingerprint.json"
    path.write_text(json.dumps(token_scan.fingerprint(token)))
    return path


# --- the scanner ---------------------------------------------------------------------------------------


def test_the_scanner_prints_the_path_and_offset_of_a_planted_token_and_never_its_bytes(short):
    token = _token()
    (short / "set").mkdir()
    planted = short / "set" / "kept.log"
    prefix = '{"note": "before", "value": "'
    planted.write_text(f'{prefix}{token}"}}\n')
    result = _scan("scan", "--fingerprint", _fingerprint_file(short, token), short / "set")
    assert (result.returncode, result.stdout.splitlines()[0], token in result.stdout + result.stderr) == (
        1, f"match {planted} {len(prefix)}", False)


def test_the_scanner_finds_nothing_in_a_set_without_the_token(short):
    (short / "set").mkdir()
    (short / "set" / "other.txt").write_text(_token() + "\n")
    result = _scan("scan", "--fingerprint", _fingerprint_file(short, _token()), short / "set")
    assert (result.returncode, [ln for ln in result.stdout.splitlines() if ln.startswith("match")]) == (0, [])


def test_the_scanner_finds_a_token_inside_a_longer_run_and_across_a_read_boundary(short):
    token = _token()
    (short / "set").mkdir()
    offset = (1 << 20) - 50  # the token straddles the first 1 MiB read
    (short / "set" / "blob.bin").write_bytes(b"A" * offset + token.encode() + b"B" * 10)
    result = _scan("scan", "--fingerprint", _fingerprint_file(short, token), short / "set")
    assert result.stdout.splitlines()[0] == f"match {short / 'set' / 'blob.bin'} {offset}"


def test_the_scanner_reads_a_stream_from_stdin(short):
    token = _token()
    result = subprocess.run([sys.executable, "-I", str(KIT / "token_scan.py"), "scan", "--fingerprint",
                             str(_fingerprint_file(short, token)), "-"],
                            input=f"x={token}\n", capture_output=True, text=True, timeout=WAIT)
    assert (result.returncode, result.stdout.splitlines()[0]) == (1, "match - 2")


def test_an_unreadable_file_is_reported_and_fails_the_scan(short):
    (short / "set").mkdir()
    locked = short / "set" / "locked.txt"
    locked.write_text("x")
    locked.chmod(0o000)
    result = _scan("scan", "--fingerprint", _fingerprint_file(short, _token()), short / "set")
    assert (result.returncode, result.stdout.splitlines()[0]) == (2, f"unreadable {locked} PermissionError")


def test_the_fingerprint_holds_the_length_and_a_salted_hash_but_not_the_token():
    token = _token()
    fp = token_scan.fingerprint(token)
    assert (fp["length"], token in json.dumps(fp), token_scan.matches(fp, token),
            token_scan.matches(fp, _token())) == (108, False, True, False)


# --- the passthrough: helpers --------------------------------------------------------------------------

passthrough = _load("passthrough")
price_check = _load("price_check")
RULE = price_check.load_rule()
SMALL_USD = (1000 * 0.10 + 100 * 0.50) / 1e6  # the stub's ordinary reply


def _secret_file(directory, value, name="secret"):
    """`value` in a mode-600 file inside a new mode-700 directory, as the owner's procedure leaves it."""
    folder = directory / name
    folder.mkdir(mode=0o700)
    path = folder / "token"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.write(fd, (value + "\n").encode())
    os.close(fd)
    return path


def _slot(token, cap_usd=1.0, cap_requests=None):
    return {"token": token, "cap_usd": cap_usd, "cap_requests": cap_requests}


def _slots(path, slots, total_usd=1.0, total_requests=None):
    path.write_text(json.dumps({"total_usd": total_usd, "total_requests": total_requests, "slots": slots}))
    return path


def _rows(state):
    log = state / "requests.jsonl"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def _events(state):
    log = state / "tranche.jsonl"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def _stub_rows(log):
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


class _Unix(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("relay", 8080, timeout=WAIT)
        self.unix_path = str(path)

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(WAIT)
        self.sock.connect(self.unix_path)


def _request(model=MODEL, stream=True, turn=0, tools=None):
    later = [{"role": "assistant", "content": "a"}, {"role": "user", "content": "b"}] * turn
    return {"model": model, "stream": stream, "max_tokens": 1000, "output_config": {"effort": "low"},
            "tools": tools if tools is not None else [{"name": "Bash", "input_schema": {"type": "object"}}],
            "messages": [{"role": "user", "content": "hello"}, *later]}


def _post(sock, token, body, path=MESSAGES, method="POST"):
    conn = _Unix(sock)
    conn.request(method, path, None if body is None else json.dumps(body),
                 {"authorization": f"Bearer {token}", "content-type": "application/json",
                  "anthropic-beta": "oauth-2025-04-20,extended-cache-ttl-2025-04-11"})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, resp.getheaders(), data


def _error(data):
    error = json.loads(data)["error"]
    return error["type"], error["message"]


@pytest.fixture
def stub(short):
    procs = []

    def start(scenario, *extra):
        sock, log = short / f"stub{len(procs)}.sock", short / f"stub{len(procs)}.jsonl"
        proc = subprocess.Popen([sys.executable, "-I", str(KIT / "stub_api.py"), "--unix", str(sock), "--model",
                                 MODEL, "--scenario", scenario, "--log", str(log), *extra],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        procs.append(proc)
        assert proc.stdout.readline().startswith("listening")
        return sock, log
    start.procs = procs
    yield start
    for proc in procs:
        proc.terminate()
        proc.wait(timeout=WAIT)


@pytest.fixture
def inproc(short):
    """A passthrough served from a thread of this process, holding `token`, in front of `upstream`."""
    servers = []

    def start(upstream, slots, token="real-token-made-up-for-this-test", paid_usage=()):
        name = f"pt{len(servers)}"
        state = short / f"{name}-state"
        state.mkdir(mode=0o700)
        pt = passthrough.Passthrough(state, slots, token, "live", passthrough.unix_upstream(str(upstream)),
                                     paid_usage)
        sock = short / f"{name}.sock"
        server = passthrough.serve(str(sock), pt)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return sock, state
    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


class _CannedServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


class _CannedHandler(socketserver.StreamRequestHandler):
    """Records each raw request and answers with the server's next canned response."""

    def handle(self):
        head = b""
        while not head.endswith(b"\r\n\r\n"):
            line = self.rfile.readline()
            if not line:
                return
            head += line
        length = next((int(line.split(b":")[1]) for line in head.split(b"\r\n")
                       if line.lower().startswith(b"content-length:")), 0)
        self.server.received.append(head + self.rfile.read(length))
        response = self.server.responses.pop(0)
        if isinstance(response, tuple):  # (head, gate, body): the body waits for the test's signal
            self.wfile.write(response[0])
            self.wfile.flush()
            response[1].wait(WAIT)
            response = response[2]
        self.wfile.write(response)


@pytest.fixture
def canned(short):
    servers = []

    def start(*responses):
        server = _CannedServer(str(short / f"canned{len(servers)}.sock"), _CannedHandler)
        server.received, server.responses = [], list(responses)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return server
    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def _http(status, headers, body):
    lines = [f"HTTP/1.1 {status} Canned", *(f"{k}: {v}" for k, v in headers),
             f"content-length: {len(body)}", "connection: close"]
    return ("\r\n".join(lines) + "\r\n\r\n").encode() + body


def _message(usage, model=MODEL):
    return {"id": "msg_canned0001", "type": "message", "role": "assistant", "model": model,
            "content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn", "stop_sequence": None,
            "usage": usage}


def _sse(message):
    stub_api = _load("stub_api")
    return b"".join(f"event: {name}\ndata: {json.dumps({'type': name, **data})}\n\n".encode()
                    for name, data in stub_api.sse_events(message))


USAGE = {"input_tokens": 1000, "output_tokens": 100, "cache_creation_input_tokens": 0,
         "cache_read_input_tokens": 0}


# --- the request path ----------------------------------------------------------------------------------


def test_the_bearer_token_is_replaced_and_no_other_byte_changes_but_the_host(short, canned, inproc):
    real = _token()
    token_file = _secret_file(short, real)
    upstream = canned(_http(200, [("content-type", "application/json")], json.dumps(_message(USAGE)).encode()))
    sock, _ = inproc(upstream.server_address, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}),
                     token=passthrough.read_token(token_file))
    token_file.write_text("a-later-value-that-is-never-read\n")  # the token was read once, at the start
    body = json.dumps(_request()).encode()
    head = ("POST /v1/messages?beta=true HTTP/1.1\r\nhost: relay:8080\r\nconnection: keep-alive\r\n"
            "anthropic-beta: oauth-2025-04-20,extended-cache-ttl-2025-04-11\r\nauthorization: Bearer lh-fake-a\r\n"
            f"content-type: application/json\r\nx-app: cli\r\ncontent-length: {len(body)}\r\n\r\n")
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(WAIT)
        client.connect(str(sock))
        client.sendall(head.encode() + body)
        assert client.recv(12).startswith(b"HTTP/1.1 200")
    expected = head.replace("Bearer lh-fake-a", f"Bearer {real}").replace("host: relay:8080",
                                                                          "host: api.anthropic.com")
    assert upstream.received == [expected.encode() + body]


REFUSALS = [
    ("an unknown token", "lh-fake-unknown", _request(), MESSAGES, "POST", "unknown token"),
    ("Sonnet", "lh-fake-a", _request(model="claude-sonnet-5-5"), MESSAGES, "POST", "model not allowed"),
    ("Fable", "lh-fake-a", _request(model="claude-fable-5-1"), MESSAGES, "POST", "model not allowed"),
    ("an alias", "lh-fake-a", _request(model="haiku"), MESSAGES, "POST", "model not allowed"),
    ("a body that is not JSON", "lh-fake-a", None, MESSAGES, "POST", "model not allowed"),
    ("a provider-side tool", "lh-fake-a",
     _request(tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 8}]), MESSAGES, "POST",
     "provider-side tool refused"),
    ("another path", "lh-fake-a", _request(), "/v1/messages/count_tokens?beta=true", "POST", "path not allowed"),
    ("the messages path without its query", "lh-fake-a", _request(), "/v1/messages", "POST", "path not allowed"),
    ("another method", "lh-fake-a", None, "/api/oauth/profile", "GET", "path not allowed"),
]


@pytest.mark.parametrize("case,token,body,path,method,reason", REFUSALS, ids=[r[0] for r in REFUSALS])
def test_a_refused_request_gets_the_one_403_form_and_never_reaches_the_upstream(
        short, stub, inproc, case, token, body, path, method, reason):
    upstream, upstream_log = stub("normal")
    sock, state = inproc(upstream, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    status, headers, data = _post(sock, token, body, path=path, method=method)
    assert (status, dict(headers)["x-should-retry"], _error(data), _rows(state)[-1]["refused"],
            _stub_rows(upstream_log)) == (403, "false", ("permission_error", f"lh-passthrough: {reason}"), reason, [])


def test_a_request_beyond_the_slots_request_count_is_refused(short, stub, inproc):
    upstream, _ = stub("normal")
    sock, _ = inproc(upstream, _slots(short / "slots.json", {"a": _slot("lh-fake-a", cap_requests=1)}))
    first, _, _ = _post(sock, "lh-fake-a", _request())
    second, _, data = _post(sock, "lh-fake-a", _request())
    assert (first, second, _error(data)[1]) == (200, 403, "lh-passthrough: slot cap reached")


def test_a_request_beyond_the_slots_priced_cap_is_refused(short, stub, inproc):
    upstream, _ = stub("normal")
    sock, _ = inproc(upstream, _slots(short / "slots.json", {"a": _slot("lh-fake-a", cap_usd=SMALL_USD * 1.5)}))
    statuses = [_post(sock, "lh-fake-a", _request())[0] for _ in range(3)]
    assert statuses == [200, 200, 403]


def test_the_total_request_count_holds_across_slots(short, stub, inproc):
    upstream, _ = stub("normal")
    sock, _ = inproc(upstream, _slots(short / "slots.json", {"a": _slot("lh-fake-a"), "b": _slot("lh-fake-b")},
                                      total_requests=1))
    first, _, _ = _post(sock, "lh-fake-a", _request())
    second, _, data = _post(sock, "lh-fake-b", _request())
    assert (first, second, _error(data)[1]) == (200, 403, "lh-passthrough: tranche total reached")


def test_the_priced_total_holds_across_slots(short, stub, inproc):
    upstream, _ = stub("normal")
    sock, _ = inproc(upstream, _slots(short / "slots.json", {"a": _slot("lh-fake-a"), "b": _slot("lh-fake-b")},
                                      total_usd=SMALL_USD * 1.5))
    statuses = [_post(sock, token, _request())[0] for token in ("lh-fake-a", "lh-fake-b", "lh-fake-a")]
    assert statuses == [200, 200, 403]


def test_a_slots_file_above_the_approved_ceiling_is_refused_at_the_start(short, stub):
    upstream, _ = stub("normal")
    state = short / "state"
    state.mkdir(mode=0o700)
    with pytest.raises(passthrough.Refused, match="ceiling"):
        passthrough.Passthrough(state, _slots(short / "slots.json", {}, total_usd=200.01), "t", "live",
                                passthrough.unix_upstream(str(upstream)))


def test_a_slot_written_while_running_is_served_and_a_removed_one_is_refused(short, stub, inproc):
    upstream, _ = stub("normal")
    slots = _slots(short / "slots.json", {"a": _slot("lh-fake-a")})
    sock, _ = inproc(upstream, slots)
    before = _post(sock, "lh-fake-a", _request())[0]
    _slots(short / "next.json", {"b": _slot("lh-fake-b")}).replace(slots)  # the launcher's atomic replace
    after = [_post(sock, token, _request())[0] for token in ("lh-fake-a", "lh-fake-b")]
    assert (before, after) == (200, [403, 200])


def test_a_stop_written_by_the_launcher_refuses_every_request_until_a_resume(short, stub, inproc):
    upstream, _ = stub("normal")
    sock, state = inproc(upstream, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    with open(state / "tranche.jsonl", "a") as fh:
        fh.write(json.dumps({"event": "stop", "reason": "paid extra usage in a session stream"}) + "\n")
    stopped, _, data = _post(sock, "lh-fake-a", _request())
    with open(state / "tranche.jsonl", "a") as fh:
        fh.write(json.dumps({"event": "resume", "ruling": "test"}) + "\n")
    resumed = _post(sock, "lh-fake-a", _request())[0]
    assert (stopped, _error(data)[1], resumed) == (403, "lh-passthrough: tranche stopped", 200)


# --- the meter -----------------------------------------------------------------------------------------


@pytest.mark.parametrize("stream", [True, False], ids=["streamed", "plain"])
def test_a_response_is_priced_by_the_price_rule(short, stub, inproc, stream):
    upstream, upstream_log = stub("cache_writes")
    sock, state = inproc(upstream, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    _post(sock, "lh-fake-a", _request(stream=stream))
    served = _stub_rows(upstream_log)[0]["usage"]
    assert round(_rows(state)[0]["usd"], 12) == round(price_check.price(served, RULE), 12)


def test_each_cache_write_is_priced_at_its_own_lifetime(short, canned, inproc):
    usage = {**USAGE, "cache_creation_input_tokens": 10000,
             "cache_creation": {"ephemeral_5m_input_tokens": 3000, "ephemeral_1h_input_tokens": 7000}}
    upstream = canned(_http(200, [("content-type", "text/event-stream")], _sse(_message(usage))))
    sock, state = inproc(upstream.server_address, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    _post(sock, "lh-fake-a", _request())
    assert round(_rows(state)[0]["usd"], 12) == round((1000 * 0.10 + 100 * 0.50 + 3000 * 0.125 + 7000 * 0.20) / 1e6,
                                                      12)


def test_a_response_in_flight_at_the_cap_is_metered_to_its_end_and_the_next_request_refused(short, stub, inproc):
    upstream, upstream_log = stub("budget")
    sock, state = inproc(upstream, _slots(short / "slots.json", {"a": _slot("lh-fake-a", cap_usd=0.01)}))
    first, _, _ = _post(sock, "lh-fake-a", _request())
    second, _, data = _post(sock, "lh-fake-a", _request())
    served = price_check.price(_stub_rows(upstream_log)[0]["usage"], RULE)
    assert (first, round(_rows(state)[0]["usd"], 12), second, _error(data)[1]) == (
        200, round(served, 12), 403, "lh-passthrough: slot cap reached")


def test_a_compressed_response_is_passed_on_compressed_and_metered(short, canned, inproc):
    import gzip
    body = gzip.compress(json.dumps(_message(USAGE)).encode())
    upstream = canned(_http(200, [("content-type", "application/json"), ("content-encoding", "gzip")], body))
    sock, state = inproc(upstream.server_address, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    _, _, data = _post(sock, "lh-fake-a", _request(stream=False))
    assert (data, round(_rows(state)[0]["usd"], 12)) == (body, round(SMALL_USD, 12))


def test_usage_the_meter_cannot_read_closes_starts(short, canned, inproc):
    upstream = canned(_http(200, [("content-type", "application/json"), ("content-encoding", "br")], b"\x0b\x02"))
    sock, state = inproc(upstream.server_address, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    status, _, data = _post(sock, "lh-fake-a", _request(stream=False))
    assert (status, data, [(e["event"], e["reason"]) for e in _events(state)]) == (
        200, b"\x0b\x02", [("close_starts", "usage unreadable")])


def test_every_vendor_response_is_passed_on_unchanged(short, canned, inproc):
    headers = [("content-type", "text/event-stream"), ("anthropic-ratelimit-unified-status", "allowed"),
               ("request-id", "req_canned"), ("set-cookie", "a=b")]
    body = _sse(_message(USAGE))
    upstream = canned(_http(200, headers, body))
    sock, _ = inproc(upstream.server_address, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    status, got, data = _post(sock, "lh-fake-a", _request())
    assert (status, got, data) == (200, [*headers, ("content-length", str(len(body))), ("connection", "close")],
                                   body)


def test_the_log_holds_the_rate_limit_headers_and_never_the_authorization_header(short, canned, inproc):
    real = _token()
    headers = [("content-type", "application/json"), ("anthropic-ratelimit-unified-status", "allowed"),
               ("anthropic-ratelimit-unified-5h-utilization", "0.12"), ("retry-after", "3"), ("set-cookie", "a=b")]
    upstream = canned(_http(200, headers, json.dumps(_message(USAGE)).encode()))
    sock, state = inproc(upstream.server_address, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}),
                         token=real)
    _post(sock, "lh-fake-a", _request(stream=False))
    text = (state / "requests.jsonl").read_text()
    assert (_rows(state)[0]["headers"], "authorization" in text.lower(), real in text, "lh-fake-a" in text) == (
        {"anthropic-ratelimit-unified-status": "allowed", "anthropic-ratelimit-unified-5h-utilization": "0.12",
         "retry-after": "3"}, False, False, False)


def test_the_log_row_names_model_effort_tools_usage_status_and_message(short, stub, inproc):
    upstream, _ = stub("normal")
    sock, state = inproc(upstream, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    _post(sock, "lh-fake-a", _request())
    row = _rows(state)[0]
    assert ({k: row[k] for k in ("slot", "model", "effort", "tools", "status", "response_model", "credential")},
            row["usage"]["output_tokens"], row["message_id"].startswith("msg_stub")) == (
        {"slot": "a", "model": MODEL, "effort": "low", "tools": ["Bash"], "status": 200, "response_model": MODEL,
         "credential": "live"}, 100, True)


# --- the token's path ----------------------------------------------------------------------------------


def _start(short, slots, *mode, name="pt"):
    """passthrough.py as its own process; returns (process, socket, state, output file) once it listens."""
    state, sock, out = short / f"{name}-state", short / f"{name}.sock", short / f"{name}.out"
    state.mkdir(mode=0o700, exist_ok=True)
    seen = out.read_text().count("listening") if out.exists() else 0  # a restart appends to the same file
    with open(out, "ab") as fh:
        proc = subprocess.Popen([sys.executable, "-I", str(KIT / "passthrough.py"), "--socket", str(sock), "--state",
                                 str(state), "--slots", str(slots), *map(str, mode)], stdout=fh, stderr=fh)
    deadline = time.monotonic() + WAIT
    while out.read_text().count("listening") == seen and proc.poll() is None and time.monotonic() < deadline:
        time.sleep(0.1)
    return proc, sock, state, out


def _rehearsal(short, upstream, name="pt"):
    return ("--rehearsal", upstream, "--canary-out", short / f"{name}.canary", "--canary-length", 108)


def _stop(proc):
    proc.terminate()
    return proc.wait(timeout=WAIT)


@pytest.mark.parametrize("file_mode,dir_mode", [(0o644, 0o700), (0o640, 0o700), (0o600, 0o750), (0o600, 0o755)])
def test_a_token_file_with_the_wrong_mode_is_refused_at_the_start(short, file_mode, dir_mode):
    token_file = _secret_file(short, _token())
    token_file.chmod(file_mode)
    token_file.parent.chmod(dir_mode)
    proc, _, _, out = _start(short, _slots(short / "slots.json", {}), "--token-file", token_file)
    assert (proc.wait(timeout=WAIT), "listening" in out.read_text(), "refused" in out.read_text()) == (2, False, True)


def test_a_token_file_owned_by_another_user_is_refused(short, monkeypatch):
    token_file = _secret_file(short, _token())
    uid = os.getuid()
    monkeypatch.setattr(os, "getuid", lambda: uid + 1)
    with pytest.raises(passthrough.Refused, match="owned"):
        passthrough.read_token(token_file)


def test_a_token_outside_the_bearer_alphabet_is_refused_without_echoing_it(short):
    token_file = _secret_file(short, "has a space\r\nx-injected: 1")
    with pytest.raises(passthrough.Refused) as refused:
        passthrough.read_token(token_file)
    assert "injected" not in str(refused.value)


def test_at_its_start_the_passthrough_reads_the_token_file_and_writes_its_fingerprint_only(short):
    """Live mode is started and stopped without any request: nothing connects to the vendor."""
    real = _token()
    proc, _, state, out = _start(short, _slots(short / "slots.json", {}), "--token-file", _secret_file(short, real))
    cmdline = Path(f"/proc/{proc.pid}/cmdline").read_bytes()
    _stop(proc)
    fp = json.loads((state / "fingerprint.json").read_text())
    assert (token_scan.matches(fp, real), real in out.read_text(), real.encode() in cmdline,
            real in (state / "fingerprint.json").read_text()) == (True, False, False, False)


def test_with_the_rehearsal_switch_no_token_file_is_opened(short, stub):
    upstream, _ = stub("normal")
    token_file = _secret_file(short, _token())
    proc, _, state, out = _start(short, _slots(short / "slots.json", {}), *_rehearsal(short, upstream),
                                 "--token-file", token_file)
    assert (proc.wait(timeout=WAIT), "refused" in out.read_text(), "listening" in out.read_text(),
            (state / "fingerprint.json").exists()) == (2, True, False, False)


def test_core_dumps_are_off_and_its_memory_and_environment_are_closed_to_other_processes(short, stub):
    upstream, _ = stub("normal")
    proc, _, _, _ = _start(short, _slots(short / "slots.json", {}), *_rehearsal(short, upstream))
    limits = Path(f"/proc/{proc.pid}/limits").read_text()
    closed = []
    for name in ("environ", "mem", "fd"):
        try:
            os.listdir(f"/proc/{proc.pid}/fd") if name == "fd" else Path(f"/proc/{proc.pid}/{name}").read_bytes()
        except PermissionError:
            closed.append(name)
    _stop(proc)
    core = next(line for line in limits.splitlines() if line.startswith("Max core file size")).split()[4:6]
    assert (core, closed) == (["0", "0"], ["environ", "mem", "fd"])


def test_it_listens_on_its_unix_socket_and_offers_no_tcp_listener(short, stub):
    upstream, _ = stub("normal")
    slots = _slots(short / "slots.json", {"a": _slot("lh-fake-a")})
    tcp = subprocess.run([sys.executable, "-I", str(KIT / "passthrough.py"), "--socket", str(short / "x.sock"),
                          "--state", str(short), "--slots", str(slots), "--port", "8080"],
                         capture_output=True, text=True, timeout=WAIT)
    proc, sock, _, _ = _start(short, slots, *_rehearsal(short, upstream))
    kind = stat.S_ISSOCK(os.lstat(sock).st_mode)
    status = _post(sock, "lh-fake-a", _request())[0]
    _stop(proc)
    assert (tcp.returncode, "unrecognized arguments: --port" in tcp.stderr, kind, status) == (2, True, True, 200)


def test_the_vendor_client_ignores_proxy_variables_verifies_tls_and_names_the_vendor_only(monkeypatch):
    import ssl
    for name in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "HTTP_PROXY"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")
    conn = passthrough.vendor_upstream()()
    assert (conn.host, conn.port, conn._tunnel_host, conn._context.verify_mode, conn._context.check_hostname) == (
        "api.anthropic.com", 443, None, ssl.CERT_REQUIRED, True)


def test_the_canary_is_found_when_planted_and_nowhere_after_a_session_with_faults(short, stub):
    upstream, upstream_log = stub("normal")
    proc, sock, state, out = _start(short, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}),
                                    *_rehearsal(short, upstream))
    replies = [_post(sock, "lh-fake-a", _request(turn=t))[0] for t in (0, 1)]
    replies.append(_post(sock, "lh-fake-unknown", _request())[0])
    replies.append(_post(sock, "lh-fake-a", _request(model="claude-sonnet-5-5"))[0])
    (short / "set").mkdir()
    (short / "set" / "cmdline").write_bytes(Path(f"/proc/{proc.pid}/cmdline").read_bytes())
    stub.procs[-1].kill()
    stub.procs[-1].wait(timeout=WAIT)
    with pytest.raises((http.client.RemoteDisconnected, ConnectionError)):
        _post(sock, "lh-fake-a", _request(turn=2))  # the upstream is gone: the error path runs
    _stop(proc)
    check = _scan("canary", "--fingerprint", state / "fingerprint.json", "--canary", short / "pt.canary",
                  short / "set", state, out, upstream_log)
    assert (replies, "ConnectionRefusedError" in out.read_text(), check.returncode, check.stdout.splitlines()[-1]) == (
        [200, 200, 403, 403], True, 0, "canary: pass")


def test_the_canary_check_fails_when_the_canary_was_written_anywhere_in_the_set(short, stub):
    upstream, _ = stub("normal")
    proc, _, state, _ = _start(short, _slots(short / "slots.json", {}), *_rehearsal(short, upstream))
    _stop(proc)
    (state / "leak.txt").write_text("leaked: " + (short / "pt.canary").read_text())
    check = _scan("canary", "--fingerprint", state / "fingerprint.json", "--canary", short / "pt.canary", state)
    assert (check.returncode, f"match {state / 'leak.txt'} 8" in check.stdout) == (1, True)


# --- the vendor's answers ------------------------------------------------------------------------------


def test_a_usage_limit_answer_is_passed_on_and_closes_starts_with_its_reset(short, stub, inproc):
    upstream, upstream_log = stub("usage_limit", "--delay", "60")
    sock, state = inproc(upstream, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    status, headers, data = _post(sock, "lh-fake-a", _request(turn=1))
    again = _post(sock, "lh-fake-a", _request(turn=1))[0]
    reset = dict(headers)["anthropic-ratelimit-unified-reset"]
    assert (status, _error(data)[0], _events(state)[0]["event"], _events(state)[0]["reason"],
            _events(state)[0]["reset"], again, len(_stub_rows(upstream_log))) == (
        429, "rate_limit_error", "close_starts", "usage limit", reset, 429, 2)


def test_any_other_vendor_429_closes_starts_without_a_reset(short, stub, inproc):
    upstream, _ = stub("rate_limit")
    sock, state = inproc(upstream, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    status = _post(sock, "lh-fake-a", _request(turn=1))[0]
    assert (status, [(e["event"], e["reason"], e["reset"]) for e in _events(state)]) == (
        429, [("close_starts", "vendor 429", None)])


def test_a_vendor_401_is_passed_on_and_stops_the_tranche(short, stub, inproc):
    upstream, upstream_log = stub("unauthorized")
    sock, state = inproc(upstream, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    status, _, data = _post(sock, "lh-fake-a", _request(turn=1))
    after, _, refusal = _post(sock, "lh-fake-a", _request(turn=1))
    assert (status, _error(data)[0], [(e["event"], e["reason"]) for e in _events(state)], after, _error(refusal)[1],
            len(_stub_rows(upstream_log))) == (
        401, "authentication_error", [("stop", "vendor 401")], 403, "lh-passthrough: tranche stopped", 1)


def test_a_paid_usage_header_stops_the_tranche_before_the_response_is_passed_on(short, canned, inproc):
    body = json.dumps(_message(USAGE)).encode()
    head = _http(200, [("content-type", "application/json"), ("x-made-up-overage", "in-use")], body)[:-len(body)]
    gate = threading.Event()
    upstream = canned((head, gate, body))
    sock, state = inproc(upstream.server_address, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}),
                         paid_usage=[("x-made-up-overage", "in-use")])
    conn = _Unix(sock)
    conn.request("POST", MESSAGES, json.dumps(_request(stream=False)), {"authorization": "Bearer lh-fake-a"})
    resp = conn.getresponse()  # its headers have reached the client while the vendor still holds the body
    at_headers = [(e["event"], e["reason"]) for e in _events(state)]
    gate.set()
    resp.read()
    after, _, refusal = _post(sock, "lh-fake-a", _request())
    assert (resp.status, at_headers, after, _error(refusal)[1]) == (
        200, [("stop", "paid extra usage")], 403, "lh-passthrough: tranche stopped")


def test_a_response_that_names_another_model_stops_the_tranche(short, canned, inproc):
    upstream = canned(_http(200, [("content-type", "application/json")],
                            json.dumps(_message(USAGE, model="claude-sonnet-5-5")).encode()))
    sock, state = inproc(upstream.server_address, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    first = _post(sock, "lh-fake-a", _request(stream=False))[0]
    after = _post(sock, "lh-fake-a", _request())[0]
    assert (first, [(e["event"], e["reason"]) for e in _events(state)], after) == (
        200, [("stop", "response model claude-sonnet-5-5")], 403)


# --- the passthrough going down ------------------------------------------------------------------------


def test_the_passthrough_going_down_closes_starts_and_its_meter_survives_a_restart(short, stub):
    upstream, _ = stub("normal")
    slots = _slots(short / "slots.json", {"a": _slot("lh-fake-a", cap_usd=SMALL_USD / 2)})
    proc, sock, state, _ = _start(short, slots, *_rehearsal(short, upstream))
    first = _post(sock, "lh-fake-a", _request())[0]
    code = _stop(proc)
    down = [(e["event"], e["reason"]) for e in _events(state)]
    gone = not sock.exists()
    again, sock, _, _ = _start(short, slots, *_rehearsal(short, upstream, name="pt-again"), name="pt")
    after, _, data = _post(sock, "lh-fake-a", _request())
    _stop(again)
    assert (first, code, down, gone, after, _error(data)[1]) == (
        200, 0, [("close_starts", "passthrough down")], True, 403, "lh-passthrough: slot cap reached")


def test_after_a_crash_nothing_is_recorded_and_a_restart_clears_the_dead_socket_and_keeps_the_meter(short, stub):
    """A killed passthrough cannot record that it went down: the launcher must see the socket go silent."""
    upstream, _ = stub("normal")
    slots = _slots(short / "slots.json", {"a": _slot("lh-fake-a", cap_usd=SMALL_USD / 2)})
    proc, sock, state, _ = _start(short, slots, *_rehearsal(short, upstream))
    first = _post(sock, "lh-fake-a", _request())[0]
    proc.kill()
    proc.wait(timeout=WAIT)
    with pytest.raises(ConnectionRefusedError):
        _post(sock, "lh-fake-a", _request())
    events = _events(state)
    again, sock, _, _ = _start(short, slots, *_rehearsal(short, upstream, name="pt-again"), name="pt")
    after, _, data = _post(sock, "lh-fake-a", _request())
    _stop(again)
    assert (first, events, after, _error(data)[1]) == (200, [], 403, "lh-passthrough: slot cap reached")


# --- the live probe script, against the stub only --------------------------------------------------------

PROBE = KIT / "live_probe.sh"
NO_PROVIDER = REPO / "experiments" / "thread_m" / "no_provider"
FAKE_HARNESS = r'''#!{python}
"""Stands in for `harbor_patient.py run` and the CLI in its container: two turns through the passthrough's socket."""
import http.client, json, os, pathlib, socket, sys, time
args = sys.argv[1:]
effort, jobs = args[args.index("--effort") + 1], pathlib.Path(args[args.index("-o") + 1])
agent = jobs / "2026-11-14__00-00-00" / "recording-task__AbCdEf1" / "agent"
(agent / "sessions" / "projects" / "-app").mkdir(parents=True)
time.sleep(3)  # the trial's containers live a while: the probe reads their process environments meanwhile


class Unix(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.connect(os.environ["LH_RELAY_SOCKET_DIR"] + "/passthrough.sock")


stream = [{"type": "system", "subtype": "init", "tools": ["Bash", "Edit", "Read"], "model": "claude-haiku-5-5",
           "apiKeySource": "none", "claude_code_version": "2.1.311"}]
session, cost, status = [], 0.0, 200
for turn in range(2):
    body = {"model": "claude-haiku-5-5", "stream": True, "max_tokens": 128000, "output_config": {"effort": effort},
            "tools": [{"name": "Bash", "input_schema": {"type": "object"}}],
            "messages": [{"role": "user", "content": "probe"}] + [{"role": "assistant", "content": "a"},
                                                                  {"role": "user", "content": "b"}] * turn}
    conn = Unix("relay", 8080, timeout=60)
    conn.request("POST", "/v1/messages?beta=true", json.dumps(body),
                 {"authorization": "Bearer " + os.environ["CLAUDE_CODE_OAUTH_TOKEN"], "content-type": "application/json"})
    resp = conn.getresponse()
    data, status = resp.read().decode(), resp.status
    if status != 200:
        break
    events = [json.loads(line[6:]) for line in data.splitlines() if line.startswith("data: ")]
    message = events[0]["message"]
    usage = {**message["usage"], **next(e["usage"] for e in events if e["type"] == "message_delta")}
    cost += (usage["input_tokens"] * 0.10 + usage["output_tokens"] * 0.50) / 1e6
    session.append({"type": "assistant", "message": {"id": message["id"], "model": message["model"], "usage": usage}})
    stream.append({"type": "rate_limit_event", "rate_limit_info": {"status": "allowed", "isUsingOverage": False}})
factor = pathlib.Path(sys.argv[0]).parents[2] / "cost-factor"  # $LH/cost-factor: a CLI that prices otherwise
cost *= float(factor.read_text()) if factor.exists() else 1.0
stream.append({"type": "result", "terminal_reason": "completed" if status == 200 else "api_error",
               "api_error_status": None if status == 200 else status, "total_cost_usd": cost,
               "modelUsage": {"claude-haiku-5-5": {"costUSD": cost}}})
(agent / "claude-code.txt").write_text("".join(json.dumps(e) + "\n" for e in stream))
(agent / "sessions" / "projects" / "-app" / "s.jsonl").write_text("".join(json.dumps(e) + "\n" for e in session))
sys.exit(0 if status == 200 else 1)
'''
FAKE_PODMAN = r'''#!/bin/bash
# Stands in for podman: one trial's main container and egress sidecar, kept after the run.
P=recording-task__abcdef1__env
case "$1" in
  ps) printf '%s\n' "${P}_main_1" "${P}_harbor-docker-egress-control-sidecar_1" other-session__env_main_1 ;;
  inspect) printf '[{"Name": "%s", "Config": {"Env": ["PATH=/usr/bin"]}}]\n' "$2" ;;
  exec) printf 'PATH=/usr/bin\0HOME=/root\0' ;;
  logs) printf '%s\n' '{"msg": "10.89.0.2:1 <-> relay:8080", "host": "relay:8080"}' ;;
  export) printf 'a stand-in file system\n' ;;
esac
'''


@pytest.fixture
def probe(short):
    """A stand-in machine for live_probe.sh: a fake harness and podman, the scratch task on the allowlist."""
    lh = short / "lh"
    for sub in ("hvenv/bin", "logs", "recordings", "scratch/recording-task", "transcripts", "home"):
        (lh / sub).mkdir(parents=True)
    (lh / "scratch" / "recording-task" / "task.toml").write_text(
        '[agent]\nnetwork_mode = "allowlist"\nallowed_hosts = ["relay", "pypi.org", "files.pythonhosted.org"]\n')
    for name, text in (("python", FAKE_HARNESS.replace("{python}", sys.executable)), ("podman", FAKE_PODMAN)):
        (lh / "hvenv" / "bin" / name).write_text(text)
        (lh / "hvenv" / "bin" / name).chmod(0o700)
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    env = {"PATH": f"{NO_PROVIDER}:/usr/bin:/bin", "HOME": str(lh / "home"), "LH": str(lh), "LH_PYTHON": sys.executable,
           "LH_PROBE_COMMIT": head, "LH_PROBE_STATE": str(short / "probe-state"),
           "LH_TRANSCRIPTS": str(lh / "transcripts")}

    def run(scenario="normal", **extra):
        env_run = {**env, "LH_PROBE_STAND_IN": scenario, **extra}
        return subprocess.run(["bash", str(PROBE), str(lh / "recordings" / "live-probe")], env=env_run,
                              capture_output=True, text=True, timeout=600)
    run.lh, run.state = lh, short / "probe-state"
    return run


def test_the_live_probe_refuses_to_start_without_its_authorization_variable(probe):
    result = probe()
    assert (result.returncode, "refused" in result.stderr, probe.state.exists()) == (3, True, False)


def test_a_stand_in_probe_refuses_a_token_file_and_another_commit(probe, short):
    token = probe(LH_PROBE_SPEND_AUTHORIZED="yes", LH_TOKEN_FILE=str(_secret_file(short, _token())))
    commit = probe(LH_PROBE_SPEND_AUTHORIZED="yes", LH_PROBE_COMMIT="0" * 40)
    assert (token.returncode, commit.returncode, probe.state.exists()) == (3, 3, False)


def test_the_live_probe_against_the_stub_passes_and_records_each_session_and_runs_once(probe):
    result = probe(LH_PROBE_SPEND_AUTHORIZED="yes")
    record = json.loads((probe.lh / "recordings" / "live-probe" / "probe.json").read_text())
    again = probe(LH_PROBE_SPEND_AUTHORIZED="yes")
    sessions = record["sessions"]
    inspected = sorted(p.name for p in (probe.lh / "recordings" / "live-probe" / "low" / "containers").iterdir())
    assert (result.returncode, record["pass"], record["failures"], [s["effort"] for s in sessions],
            [len(s["requests"]) for s in sessions], [s["first_request_prompt_tokens"] for s in sessions],
            record["file_set_scan"][-2:], [name.split(".")[0] for name in inspected], again.returncode) == (
        0, True, [], ["low", "medium", "high"], [2, 2, 2], [1000, 1000, 1000], ["canary: pass", "exit 0"],
        ["recording-task__abcdef1__env_harbor-docker-egress-control-sidecar_1"] * 2
        + ["recording-task__abcdef1__env_main_1"] * 2, 3)


def test_the_live_probe_stops_at_the_first_answer_that_is_not_200(probe):
    result = probe("unauthorized", LH_PROBE_SPEND_AUTHORIZED="yes")
    record = json.loads((probe.lh / "recordings" / "live-probe" / "probe.json").read_text())
    assert (result.returncode, record["pass"], record["stopped"], [s["effort"] for s in record["sessions"]]) == (
        1, False, "low: vendor status 401; passthrough stop: vendor 401", ["low"])


def test_a_probe_whose_priced_figure_differs_from_the_clis_by_more_than_one_percent_fails_its_metering(probe):
    (probe.lh / "cost-factor").write_text("1.02")
    result = probe(LH_PROBE_SPEND_AUTHORIZED="yes")
    record = json.loads((probe.lh / "recordings" / "live-probe" / "probe.json").read_text())
    assert (result.returncode, record["stopped"], [f.split(":")[0] for f in record["failures"]],
            all("not within 1%" in f for f in record["failures"])) == (1, None, ["low", "medium", "high"], True)
