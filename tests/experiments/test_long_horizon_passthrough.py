"""The long-horizon passthrough's first slice, its token scanner and the live probe script
(`experiments/long_horizon_tasks/passthrough.py`, `token_scan.py`, `live_probe.sh`; plan Task 4).

The upstream is `stub_api.py` on a unix socket, or a canned upstream in this file where a test needs exact
bytes or a response the stub has no scenario for. Every token is a made-up string written by the test into
a mode-600 file inside a mode-700 directory; no request leaves the machine and no real CLI runs.
"""

from __future__ import annotations

import base64
import contextlib
import gzip
import http.client
import importlib.util
import io
import itertools
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import socketserver
import ssl
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


_STARTED = []  # passthrough processes of the running test, killed at its end even when it fails


@pytest.fixture
def short():
    """A mode-700 directory with a short path (AF_UNIX paths stop at 108 bytes)."""
    path = Path(tempfile.mkdtemp(prefix="lhp", dir="/tmp"))
    yield path
    while _STARTED:
        proc = _STARTED.pop()
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=WAIT)
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
        1, f"match {planted} {len(prefix)} plain", False)


def test_the_scanner_finds_nothing_in_a_set_without_the_token(short):
    (short / "set").mkdir()
    (short / "set" / "other.txt").write_text(_token() + "\n")
    result = _scan("scan", "--fingerprint", _fingerprint_file(short, _token()), short / "set")
    assert (result.returncode, [ln for ln in result.stdout.splitlines() if ln.startswith("match")]) == (0, [])


@pytest.mark.parametrize("jobs", ["1", "4"])
def test_the_scanner_finds_a_token_inside_a_longer_run_and_across_a_read_boundary(short, jobs):
    token = _token()
    (short / "set").mkdir()
    offset = (1 << 20) - 50  # the token straddles the first 1 MiB read
    (short / "set" / "blob.bin").write_bytes(b"A" * offset + token.encode() + b"B" * 10)
    result = _scan("scan", "--fingerprint", _fingerprint_file(short, token), "--jobs", jobs, short / "set")
    assert result.stdout.splitlines()[0] == f"match {short / 'set' / 'blob.bin'} {offset} plain"


def test_a_parallel_scan_finds_every_planted_form_among_many_files_and_prints_what_a_serial_scan_prints(short):
    token = _token()
    (short / "set" / "sub").mkdir(parents=True)
    for i in range(120):
        (short / "set" / ("sub" if i % 3 else "") / f"other-{i:03d}.txt").write_text(_token() + "\n")
    forms = token_scan.forms(token)
    for name, form in forms.items():
        (short / "set" / "sub" / f"{name}.bin").write_bytes(b"x=" + form + b";")
    fp = _fingerprint_file(short, token)
    serial, parallel = (_scan("scan", "--fingerprint", fp, "--jobs", jobs, short / "set") for jobs in (1, 4))
    planted = {f"match {short / 'set' / 'sub' / f'{name}.bin'} 2" for name in forms}  # equal forms share one name
    found = {line.rsplit(" ", 1)[0] for line in parallel.stdout.splitlines() if line.startswith("match")}
    assert (parallel.returncode, parallel.stdout, planted - found) == (1, serial.stdout, set())


def test_a_parallel_scan_takes_each_file_s_kind_when_the_walk_lists_it_not_when_a_worker_is_free(short):
    """A slot's socket can go right after the walk lists it. The scanner's own process takes each file's kind at
    listing, so a special file removed while every worker is busy is still `skipped`, never unreadable. Two files
    that hold each worker for seconds come first; the FIFO after them is removed meanwhile."""
    (short / "set").mkdir()
    for name in ("a1.bin", "a2.bin"):
        (short / "set" / name).write_bytes(b"A" * (2 << 20))  # one long alphabet run: seconds of hashing
    fifo = short / "set" / "z.fifo"
    os.mkfifo(fifo)
    proc = subprocess.Popen([sys.executable, "-I", str(KIT / "token_scan.py"), "scan", "--fingerprint",
                             str(_fingerprint_file(short, _token())), "--jobs", "2", str(short / "set")],
                            stdout=subprocess.PIPE, text=True)
    _STARTED.append(proc)
    children, deadline = Path(f"/proc/{proc.pid}/task/{proc.pid}/children"), time.monotonic() + WAIT
    while proc.poll() is None and not children.read_text().split() and time.monotonic() < deadline:
        time.sleep(0.05)
    time.sleep(1.5)  # the workers are forked, the walk has listed the FIFO, and each worker is on a long file
    fifo.unlink()
    out, _ = proc.communicate(timeout=WAIT)
    assert (proc.returncode, out.splitlines()) == (0, [f"skipped {fifo} special file", "scanned 2 files"])


def test_a_parallel_scan_reports_unreadable_files_and_directories_as_a_serial_scan_does(short):
    """The walk's errors and the files' read errors keep the serial scan's order, and the scan is incomplete."""
    for i in range(60):
        path = short / "set" / f"d{i % 6}" / f"f{i:02d}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n")
        if i % 7 == 0:
            path.chmod(0o000)
    (short / "set" / "d3").chmod(0o000)
    fp = _fingerprint_file(short, _token())
    serial, parallel = (_scan("scan", "--fingerprint", fp, "--jobs", jobs, short / "set") for jobs in (1, 4))
    assert (parallel.returncode, parallel.stdout, f"unreadable {short / 'set' / 'd0' / 'f42.txt'} PermissionError"
            in parallel.stdout.splitlines()) == (2, serial.stdout, True)


def test_the_scanner_reads_a_stream_from_stdin(short):
    token = _token()
    result = subprocess.run([sys.executable, "-I", str(KIT / "token_scan.py"), "scan", "--fingerprint",
                             str(_fingerprint_file(short, token)), "-"],
                            input=f"x={token}\n", capture_output=True, text=True, timeout=WAIT)
    assert (result.returncode, result.stdout.splitlines()[0]) == (1, "match - 2 plain")


def test_an_unreadable_file_is_reported_and_fails_the_scan(short):
    (short / "set").mkdir()
    locked = short / "set" / "locked.txt"
    locked.write_text("x")
    locked.chmod(0o000)
    result = _scan("scan", "--fingerprint", _fingerprint_file(short, _token()), short / "set")
    assert (result.returncode, result.stdout.splitlines()[0]) == (2, f"unreadable {locked} PermissionError")


def test_the_fingerprint_holds_each_forms_length_and_a_salted_hash_but_no_form():
    token = _token()
    fp, forms = token_scan.fingerprint(token), token_scan.forms(token)
    text = json.dumps(fp).encode()
    assert ({f["name"]: f["length"] for f in fp["forms"]}, [n for n, form in forms.items() if form in text],
            token_scan.matches(fp, token), token_scan.matches(fp, _token())) == (
        {name: len(form) for name, form in forms.items()}, [], True, False)


def _encodings():
    """(name, bytes -> encoded bytes): the token inside a longer stream, encoded as a copy could be."""
    found = [("hex", lambda b: b.hex().encode()), ("upper-case hex", lambda b: b.hex().upper().encode()),
             ("UTF-16LE", lambda b: b.decode().encode("utf-16-le"))]
    for skip in range(3):
        found += [(f"base64 after {skip} bytes", lambda b, k=skip: base64.b64encode(b"x" * k + b)),
                  (f"url-safe base64 after {skip} bytes", lambda b, k=skip: base64.urlsafe_b64encode(b"x" * k + b))]
    return found


@pytest.mark.parametrize("name,encode", _encodings(), ids=[e[0] for e in _encodings()])
def test_the_scanner_finds_the_token_inside_an_encoded_stream(short, name, encode):
    token = _token()
    (short / "set").mkdir()
    (short / "set" / "encoded.txt").write_bytes(encode(f"token={token};".encode()))
    result = _scan("scan", "--fingerprint", _fingerprint_file(short, token), short / "set")
    assert result.returncode == 1


@pytest.mark.parametrize("target", ["symlink", "missing", "empty directory"])
def test_a_named_path_the_scanner_cannot_read_as_a_whole_fails_the_scan(short, target):
    (short / "file.txt").write_text("no token here\n")
    path = short / target.replace(" ", "-")
    if target == "symlink":
        path.symlink_to(short / "file.txt")
    elif target == "empty directory":
        path.mkdir()
    result = _scan("scan", "--fingerprint", _fingerprint_file(short, _token()), path)
    assert result.returncode == 2


def test_a_crash_of_the_scanner_is_an_incomplete_scan_never_a_match(short):
    """Task 8 m1: with no fingerprint file it fails; it exits 2 (incomplete), not 1 (a match)."""
    (short / "file.txt").write_text("x\n")
    assert _scan("scan", "--fingerprint", short / "no-fingerprint.json", short / "file.txt").returncode == 2


def test_a_symlink_or_a_fifo_inside_a_scanned_set_is_named_as_skipped(short):
    """Task 8 m3: they are not followed or read, and each gets a line; the exit is unchanged."""
    (short / "set").mkdir()
    (short / "set" / "plain.txt").write_text("x\n")
    (short / "set" / "link").symlink_to(short / "set" / "plain.txt")
    os.mkfifo(short / "set" / "pipe")
    result = _scan("scan", "--fingerprint", _fingerprint_file(short, _token()), short / "set")
    assert (result.returncode, sorted(line for line in result.stdout.splitlines() if line.startswith("skipped"))) == (
        0, [f"skipped {short / 'set' / 'link'} symlink", f"skipped {short / 'set' / 'pipe'} special file"])


def test_an_unreadable_directory_inside_a_scanned_set_is_reported_and_fails_the_scan(short):
    """Task 8 m9: os.walk's errors are reported, not dropped."""
    (short / "set" / "locked").mkdir(parents=True)
    (short / "set" / "plain.txt").write_text("x\n")
    (short / "set" / "locked").chmod(0o000)
    result = _scan("scan", "--fingerprint", _fingerprint_file(short, _token()), short / "set")
    assert (result.returncode, f"unreadable {short / 'set' / 'locked'} PermissionError" in result.stdout) == (2, True)


def test_a_named_symlink_beside_a_real_file_fails_the_scan(short):
    """Task 8 m9: the link would otherwise be skipped and the real file alone make the scan look whole."""
    token = _token()
    (short / "plain.txt").write_text("x\n")
    (short / "target.txt").write_text(f"a {token} b\n")
    (short / "link").symlink_to(short / "target.txt")
    result = _scan("scan", "--fingerprint", _fingerprint_file(short, token), short / "plain.txt", short / "link")
    assert result.returncode == 2


def test_the_canary_check_fails_when_a_planted_copy_is_not_found(short):
    """Task 8 m9: a fingerprint made from the canary whose other forms the scanner cannot find."""
    canary = _token()
    (short / "canary").write_text(canary + "\n")
    (short / "set").mkdir()
    fp = token_scan.fingerprint(canary)
    fp["forms"] = [f if f["name"] == "plain" else {**f, "sha256": "0" * 64} for f in fp["forms"]]
    (short / "fp.json").write_text(json.dumps(fp))
    result = _scan("canary", "--fingerprint", short / "fp.json", "--canary", short / "canary", short / "set")
    assert (result.returncode, "planted copies not found" in result.stdout) == (1, True)


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
    conn.request(method, path, body if body is None or isinstance(body, bytes) else json.dumps(body),
                 {"authorization": f"Bearer {token}", "content-type": "application/json",
                  "anthropic-beta": "oauth-2025-04-20,extended-cache-ttl-2025-04-11"})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, resp.getheaders(), data


def _error(data):
    error = json.loads(data)["error"]
    return error["type"], error["message"]


def _raw(headers, body=b"", line=f"POST {MESSAGES} HTTP/1.1"):
    """A request's bytes exactly as given: `headers` are (name, value) pairs in their order."""
    return ("\r\n".join([line, *(f"{k}: {v}" for k, v in headers)]) + "\r\n\r\n").encode("latin-1") + body


def _headers(body, token="lh-fake-a"):
    return [("host", "relay:8080"), ("authorization", f"Bearer {token}"), ("content-type", "application/json"),
            ("content-length", str(len(body)))]


def _exchange(sock, data, timeout=WAIT):
    """Send `data`; every byte that came back until the passthrough closed (or `timeout` passed)."""
    reply = b""
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(timeout)
        client.connect(str(sock))
        with contextlib.suppress(BrokenPipeError):  # a refusal may close before the rest is sent; it is still read
            client.sendall(data)
        with contextlib.suppress(TimeoutError, ConnectionResetError):
            while chunk := client.recv(65536):
                reply += chunk
    return reply


def _reason(reply):
    """The refusal's reason in a raw reply, or its status line when it is not the 403 form."""
    head, _, data = reply.partition(b"\r\n\r\n")
    if not head.startswith(b"HTTP/1.1 403"):
        return head.split(b"\r\n")[0].decode("latin-1")
    return json.loads(data)["error"]["message"].removeprefix("lh-passthrough: ")


def _found(data, token):
    """The forms of `token` that appear in `data`."""
    return [name for name, form in token_scan.forms(token).items() if form in data]


def _written(state):
    return b"".join(path.read_bytes() for path in sorted(state.iterdir()) if path.is_file())


def _eventually(read):
    deadline = time.monotonic() + WAIT
    while not (value := read()) and time.monotonic() < deadline:
        time.sleep(0.05)
    return value


def _concurrently(calls):
    results = [None] * len(calls)

    def run(i):
        try:
            results[i] = calls[i]()
        except (OSError, http.client.HTTPException) as exc:  # shown in the results, not lost in a thread
            results[i] = type(exc).__name__
    threads = [threading.Thread(target=run, args=(i,)) for i in range(len(calls))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(WAIT * 3)
    return results


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

    def start(upstream, slots, token="real-token-made-up-for-this-test", paid_usage=(), stop_on_non_200=False):
        name = f"pt{len(servers)}"
        state = short / f"{name}-state"
        state.mkdir(mode=0o700)
        pt = passthrough.Passthrough(state, slots, token, "live", passthrough.unix_upstream(str(upstream)),
                                     paid_usage, stop_on_non_200)
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
        if isinstance(response, tuple):  # (head, gate, body or [parts]): the body waits for the test's signal
            self.wfile.write(response[0])
            self.wfile.flush()
            response[1].wait(WAIT)
            response = response[2]
        for part in response if isinstance(response, list) else [response]:  # parts come 0.3 s apart
            self.wfile.write(part)
            self.wfile.flush()
            time.sleep(0.3 if isinstance(response, list) else 0)


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


def test_the_request_is_rebuilt_with_three_header_values_changed_and_no_other_byte(short, canned, inproc):
    real = _token()
    token_file = _secret_file(short, real)
    upstream = canned(_http(200, [("content-type", "application/json")], json.dumps(_message(USAGE)).encode()))
    sock, _ = inproc(upstream.server_address, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}),
                     token=passthrough.read_token(token_file))
    token_file.write_text("a-later-value-that-is-never-read\n")  # the token was read once, at the start
    body = json.dumps(_request()).encode()
    head = ("POST /v1/messages?beta=true HTTP/1.1\r\nhost: relay:8080\r\nconnection: keep-alive\r\n"
            "accept-encoding: gzip, deflate, br\r\nuser-agent: claude-cli/2.1.311 (external, cli)\r\n"
            "anthropic-beta: oauth-2025-04-20,extended-cache-ttl-2025-04-11\r\nauthorization: Bearer lh-fake-a\r\n"
            f"content-type: application/json\r\nx-app: cli\r\ncontent-length: {len(body)}\r\n\r\n")
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(WAIT)
        client.connect(str(sock))
        client.sendall(head.encode() + body)
        assert client.recv(12).startswith(b"HTTP/1.1 200")
    expected = head.replace("Bearer lh-fake-a", f"Bearer {real}").replace(
        "host: relay:8080", "host: api.anthropic.com").replace("gzip, deflate, br", "identity")
    assert upstream.received == [expected.encode() + body]


def _with(**fields):
    return {**_request(), **fields}


def _json_bytes(text):
    return text.replace("MODEL", MODEL).encode()


SCHEMA = {"type": "object"}
CONTENT = [
    ("an empty body", b"", "request malformed"),
    ("a body that is not JSON", b"model=claude-haiku-5-5", "request malformed"),
    ("a duplicate top-level key", _json_bytes(
        '{"model": "MODEL", "model": "claude-sonnet-5-5", "max_tokens": 10, "stream": true, '
        '"output_config": {"effort": "low"}, "messages": []}'), "request malformed"),
    ("a duplicate key inside a message", _json_bytes(
        '{"model": "MODEL", "max_tokens": 10, "stream": true, "output_config": {"effort": "low"}, '
        '"messages": [{"role": "user", "role": "assistant", "content": "x"}]}'), "request malformed"),
    ("a byte-order mark", b"\xef\xbb\xbf" + json.dumps(_request()).encode(), "request malformed"),
    ("UTF-16", json.dumps(_request()).encode("utf-16"), "request malformed"),
    ("NaN", json.dumps(_with(temperature=float("nan"))).encode(), "request malformed"),
    ("an unrecorded field", _with(mcp_servers=[{"type": "url", "url": "https://x.invalid", "name": "x"}]),
     "field not allowed"),
    ("a container", _with(container="container_1"), "field not allowed"),
    ("stream as a number", _with(stream=1), "field not allowed"),
    ("max_tokens above the recorded", _with(max_tokens=128001), "field not allowed"),
    ("max_tokens as true", _with(max_tokens=True), "field not allowed"),
    ("no max_tokens", {k: v for k, v in _request().items() if k != "max_tokens"}, "field not allowed"),
    ("an unrecorded effort", _with(output_config={"effort": "ultra"}), "field not allowed"),
    ("an image by URL", _with(messages=[{"role": "user", "content": [
        {"type": "image", "source": {"type": "url", "url": "https://x.invalid/a.png"}}]}]), "field not allowed"),
    ("a document by file id", _with(messages=[{"role": "user", "content": [
        {"type": "document", "source": {"type": "file", "file_id": "file_1"}}]}]), "field not allowed"),
    ("tools as null", _with(tools=None), "tool not allowed"),
    ("a provider-side tool", _request(tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 8}]),
     "provider-side tool refused"),
    ("a typed tool with a schema", _request(tools=[{"type": "custom", "name": "Bash", "input_schema": SCHEMA}]),
     "provider-side tool refused"),
    ("a tool without a schema", _request(tools=[{"name": "Bash"}]), "provider-side tool refused"),
    ("an unrecorded tool name", _request(tools=[{"name": "WebFetch", "input_schema": SCHEMA}]), "tool not allowed"),
    ("an unrecorded tool key", _request(tools=[{"name": "Bash", "input_schema": SCHEMA, "strict": True}]),
     "tool not allowed"),
    ("a key recorded on another tool only", _request(tools=[{"name": "Bash", "input_schema": SCHEMA,
                                                             "defer_loading": True}]), "tool not allowed"),
    ("an unrecorded schema key", _request(tools=[{"name": "Bash", "input_schema": {**SCHEMA, "$defs": {}}}]),
     "tool not allowed"),
    ("a tool named by a list", _request(tools=[{"name": ["Bash"], "input_schema": SCHEMA}]), "tool not allowed"),
    ("a cache mark on a tool", _request(tools=[{"name": "Bash", "input_schema": SCHEMA,
                                               "cache_control": {"type": "ephemeral"}}]), "tool not allowed"),
    ("a tool of another configuration", _request(tools=[{"name": "Write", "input_schema": SCHEMA}]),
     "tool not allowed"),
    ("trailing data after the value", json.dumps(_request()).encode() + b" x", "request malformed"),
    ("two JSON values", json.dumps(_request()).encode() * 2, "request malformed"),
    ("a duplicate key two levels down", _json_bytes(
        '{"model": "MODEL", "max_tokens": 10, "stream": true, "output_config": {"effort": "low", "effort": "high"}, '
        '"messages": []}'), "request malformed"),
    ("a duplicate key in a tool", _json_bytes(
        '{"model": "MODEL", "max_tokens": 10, "stream": true, "output_config": {"effort": "low"}, "messages": [], '
        '"tools": [{"name": "Bash", "name": "WebFetch", "input_schema": {}}]}'), "request malformed"),
    ("a byte that is not UTF-8", json.dumps(_request()).encode().replace(b"hello", b"hel\xfflo"), "request malformed"),
    ("an array", b"[]", "field not allowed"),
    ("a string", b'"x"', "field not allowed"),
    ("null", b"null", "field not allowed"),
    ("a service tier", _with(service_tier="priority"), "field not allowed"),
    ("a temperature", _with(temperature=1), "field not allowed"),
    ("a model with a date", _with(model=MODEL + "-20990101"), "model not allowed"),
    ("a model in capitals", _with(model=MODEL.upper()), "model not allowed"),
    ("a model in a list", _with(model=[MODEL]), "model not allowed"),
    ("no model", {k: v for k, v in _request().items() if k != "model"}, "model not allowed"),
    ("effort max", _with(output_config={"effort": "max"}), "field not allowed"),
    ("no effort", _with(output_config={}), "field not allowed"),
    ("output_config as a string", _with(output_config="low"), "field not allowed"),
    ("max_tokens as a float", _with(max_tokens=10.0), "field not allowed"),
    ("max_tokens of zero", _with(max_tokens=0), "field not allowed"),
    ("lists nested past the parser's limit", json.dumps(_request()).encode().replace(
        b'"hello"', b"[" * 100_000 + b"]" * 100_000), "request malformed"),
    ("objects nested past the parser's limit", json.dumps(_request()).encode().replace(
        b'"hello"', b'{"a": ' * 100_000 + b"1" + b"}" * 100_000), "request malformed"),
    ("an integer of 5,000 digits", json.dumps(_request()).encode().replace(b'"hello"', b"1" * 5000),
     "request malformed"),
    ("max_tokens of 4,000 digits", _json_bytes(
        '{"model": "MODEL", "max_tokens": ' + "9" * 4000 + ', "stream": true, "output_config": {"effort": "low"}, '
        '"messages": []}'), "field not allowed"),
]
REFUSALS = [
    ("an unknown token", "lh-fake-unknown", _request(), MESSAGES, "POST", "unknown token"),
    ("Sonnet", "lh-fake-a", _request(model="claude-sonnet-5-5"), MESSAGES, "POST", "model not allowed"),
    ("Fable", "lh-fake-a", _request(model="claude-fable-5-1"), MESSAGES, "POST", "model not allowed"),
    ("an alias", "lh-fake-a", _request(model="haiku"), MESSAGES, "POST", "model not allowed"),
    ("no body", "lh-fake-a", None, MESSAGES, "POST", "request malformed"),
    *[(case, "lh-fake-a", body, MESSAGES, "POST", reason) for case, body, reason in CONTENT],
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
            sorted(_rows(state)[-1]), _stub_rows(upstream_log)) == (
        403, "false", ("permission_error", f"lh-passthrough: {reason}"), reason, ["refused", "slot", "status", "time"],
        [])


def test_a_request_beyond_the_slots_request_count_is_refused(short, stub, inproc):
    upstream, _ = stub("normal")
    sock, _ = inproc(upstream, _slots(short / "slots.json", {"a": _slot("lh-fake-a", cap_requests=1)}))
    first, _, _ = _post(sock, "lh-fake-a", _request())
    second, _, data = _post(sock, "lh-fake-a", _request())
    assert (first, second, _error(data)[1]) == (200, 403, "lh-passthrough: slot cap reached")


@pytest.mark.parametrize("limit", ["cap_requests", "cap_usd"])
def test_a_slot_at_its_cap_keeps_answering_the_cap_refusal_and_logs_each_without_a_stop(short, stub, inproc, limit):
    upstream, _ = stub("normal")
    cap = _slot("lh-fake-a", cap_requests=1) if limit == "cap_requests" else _slot("lh-fake-a", cap_usd=SMALL_USD / 2)
    sock, state = inproc(upstream, _slots(short / "slots.json", {"a": cap}))
    replies = [_post(sock, "lh-fake-a", _request()) for _ in range(4)]
    assert ([(status, _error(data)[1] if status == 403 else None) for status, _, data in replies],
            [(r.get("refused"), r.get("limit")) for r in _rows(state)], _events(state)) == (
        [(200, None)] + [(403, "lh-passthrough: slot cap reached")] * 3,
        [(None, None)] + [("slot cap reached", limit)] * 3, [])


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


def test_a_compressed_response_is_not_passed_on_and_stops_the_tranche(short, canned, inproc):
    body = gzip.compress(json.dumps(_message(USAGE)).encode())
    upstream = canned(_http(200, [("content-type", "application/json"), ("content-encoding", "gzip")], body))
    sock, state = inproc(upstream.server_address, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    request = json.dumps(_request(stream=False)).encode()
    reply = _exchange(sock, _raw(_headers(request), request))
    _eventually(lambda: _rows(state))  # the answer is metered after the client was dropped
    assert (reply, [(e["event"], e["reason"]) for e in _events(state)]) == (
        b"", [("stop", "response not checkable"), ("close_starts", "usage incomplete")])


def _bound(prompt, output):
    """The worst case D4 states: the prompt all at the one-hour write rate, `max_tokens` as output."""
    return price_check.price({"input_tokens": 0, "cache_creation_input_tokens": prompt, "output_tokens": output}, RULE)


def _usages(prompt, output):
    """Every corner of what a response could bill for a prompt of at most `prompt` tokens and at most `output`
    output tokens: the whole prompt as each kind of token, at each size that changes the rate (none, one, either
    side of the long-prompt threshold, the whole). A split between kinds costs no more than its dearest corner."""
    above = RULE["long_prompt"]["above_prompt_tokens"]
    kinds = [lambda n: {"input_tokens": n}, lambda n: {"input_tokens": 0, "cache_read_input_tokens": n},
             lambda n: {"input_tokens": 0, "cache_creation_input_tokens": n,
                        "cache_creation": {"ephemeral_5m_input_tokens": n}},
             lambda n: {"input_tokens": 0, "cache_creation_input_tokens": n,
                        "cache_creation": {"ephemeral_1h_input_tokens": n}}]
    sizes = sorted({n for n in (0, 1, above, above + 1, prompt) if n <= prompt})
    return [{**kind(n), "output_tokens": out} for n, kind, out in itertools.product(sizes, kinds, (0, output))]


@pytest.mark.parametrize("text,start", [("x" * 150_000, None), ("x", {"input_tokens": 1000, "output_tokens": 1})],
                         ids=["a long body, no usage read", "a short body, a larger prompt in message_start"])
def test_the_worst_case_is_at_least_what_any_usage_of_the_request_could_cost(text, start):
    request = {**_request(), "max_tokens": 64000, "messages": [{"role": "user", "content": text}]}
    size = len(json.dumps(request).encode())
    worst = passthrough._price(passthrough._worst_case(start, request, size))
    prompt = max(size, (start or {}).get("input_tokens", 0))  # D4: the vendor counts no more prompt than this
    assert [u for u in _usages(prompt, 64000) if price_check.price(u, RULE) > worst] == []


def test_usage_the_meter_cannot_read_is_priced_at_the_requests_worst_case_and_closes_starts(short, canned, inproc):
    upstream = canned(_http(200, [("content-type", "application/json")], b"not json"))
    sock, state = inproc(upstream.server_address, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    request = json.dumps(_request(stream=False)).encode()
    status, _, data = _post(sock, "lh-fake-a", request)
    worst = _bound(len(request), 1000)
    assert (status, data, round(_rows(state)[0]["usd"], 12), _rows(state)[0]["worst_case"],
            [(e["event"], e["reason"]) for e in _events(state)]) == (
        200, b"not json", round(worst, 12), True, [("close_starts", "usage incomplete")])


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


def test_the_log_row_keeps_the_requests_beta_flags_cache_marks_and_tools_and_the_answers_header_names(
        short, canned, inproc):
    headers = [("content-type", "application/json"), ("anthropic-ratelimit-unified-status", "allowed"),
               ("x-vendor-other", "not logged")]
    upstream = canned(_http(200, headers, json.dumps(_message(USAGE)).encode()))
    sock, state = inproc(upstream.server_address, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    hour, five = {"type": "ephemeral", "ttl": "1h"}, {"type": "ephemeral"}
    request = _request(stream=False, tools=[{"name": "Bash", "input_schema": SCHEMA},
                                            {"name": "Read", "input_schema": SCHEMA}])
    request.update(system=[{"type": "text", "text": "s", "cache_control": hour}],
                   messages=[{"role": "user", "content": [{"type": "text", "text": "x", "cache_control": hour},
                                                          {"type": "text", "text": "y", "cache_control": five}]}])
    _post(sock, "lh-fake-a", request)
    row = _rows(state)[0]
    assert ({k: row[k] for k in ("beta", "cache_marks", "tools", "header_names")}, row["headers"]) == (
        {"beta": "oauth-2025-04-20,extended-cache-ttl-2025-04-11",
         "cache_marks": ["system.0:1h", "messages.0.content.0:1h", "messages.0.content.1:unset"],
         "tools": ["Bash", "Read"],
         "header_names": ["content-type", "anthropic-ratelimit-unified-status", "x-vendor-other", "content-length",
                          "connection"]},
        {"anthropic-ratelimit-unified-status": "allowed"})


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
    _STARTED.append(proc)
    deadline = time.monotonic() + WAIT
    while out.read_text().count("listening") == seen and proc.poll() is None and time.monotonic() < deadline:
        time.sleep(0.1)
    return proc, sock, state, out


def _rehearsal(short, upstream, name="pt"):
    return ("--rehearsal", upstream, "--canary-out", short / f"{name}.canary")


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
            real in (state / "fingerprint.json").read_text(), fp["mode"]) == (True, False, False, False, "live")


def test_the_rehearsal_canary_has_the_shape_and_length_of_a_setup_token_token(short, stub):
    """Task 8 m7: 108 characters with the setup-token prefix, whatever the person who starts it passes."""
    upstream, _ = stub("normal")
    proc, _, state, out = _start(short, _slots(short / "slots.json", {}), *_rehearsal(short, upstream))
    _stop(proc)
    canary = (short / "pt.canary").read_text().strip()
    assert (len(canary), canary.startswith("sk-ant-oat01-"), token_scan.matches(
        json.loads((state / "fingerprint.json").read_text()), canary)) == (108, True, True)


def test_a_rehearsal_passthrough_records_its_mode_beside_its_fingerprint(short, stub):
    """Task 8 M3: the launcher reads the mode and refuses a passthrough in the other one."""
    upstream, _ = stub("normal")
    proc, _, state, out = _start(short, _slots(short / "slots.json", {}), *_rehearsal(short, upstream))
    _stop(proc)
    assert json.loads((state / "fingerprint.json").read_text())["mode"] == "rehearsal"


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


def test_a_configured_paid_usage_header_stops_the_tranche_and_its_answer_is_not_passed_on(short, canned, inproc):
    body = json.dumps(_message(USAGE)).encode()
    head = _http(200, [("content-type", "application/json"), ("x-made-up-overage", "in-use")], body)[:-len(body)]
    gate = threading.Event()
    upstream = canned((head, gate, body))
    sock, state = inproc(upstream.server_address, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}),
                         paid_usage=[("x-made-up-overage", "in-use")])
    conn = _Unix(sock)
    conn.request("POST", MESSAGES, json.dumps(_request(stream=False)), {"authorization": "Bearer lh-fake-a"})
    resp = conn.getresponse()  # the refusal has reached the client while the vendor still holds the body
    at_headers = [(e["event"], e["reason"]) for e in _events(state)]
    gate.set()
    data = resp.read()
    row = _eventually(lambda: _rows(state))[0]
    assert (resp.status, _error(data)[1], at_headers, round(row["usd"], 12), row["passed_on"]) == (
        403, "lh-passthrough: tranche stopped", [("stop", "paid extra usage")], round(SMALL_USD, 12), False)


RATE = "anthropic-ratelimit-unified"
PAID = [("a rejected status", [(f"{RATE}-status", "rejected")]),
        ("overage in use", [(f"{RATE}-overage-in-use", "true")]),
        ("overage allowed", [(f"{RATE}-overage-status", "allowed")]),
        ("overage allowed with a warning", [(f"{RATE}-overage-status", "allowed_warning")]),
        ("the three together", [(f"{RATE}-status", "rejected"), (f"{RATE}-overage-status", "allowed"),
                                (f"{RATE}-overage-in-use", "true"), (f"{RATE}-representative-claim", "five_hour")])]


@pytest.mark.parametrize("stream", [False, True], ids=["plain", "streamed"])
@pytest.mark.parametrize("case,headers", PAID, ids=[p[0] for p in PAID])
def test_a_200_showing_paid_extra_usage_stops_the_tranche_and_is_not_passed_on(short, canned, inproc, case, headers,
                                                                              stream):
    kind, body = (("text/event-stream", _sse(_message(USAGE))) if stream
                  else ("application/json", json.dumps(_message(USAGE)).encode()))
    upstream = canned(_http(200, [("content-type", kind), *headers], body))
    sock, state = inproc(upstream.server_address, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    status, _, data = _post(sock, "lh-fake-a", _request(stream=stream))
    row = _eventually(lambda: _rows(state))[0]
    after, _, refusal = _post(sock, "lh-fake-a", _request())
    assert (status, _error(data)[1], [(e["event"], e["reason"]) for e in _events(state)], round(row["usd"], 12),
            row["passed_on"], after, _error(refusal)[1]) == (
        403, "lh-passthrough: tranche stopped", [("stop", "paid extra usage")], round(SMALL_USD, 12), False, 403,
        "lh-passthrough: tranche stopped")


def test_an_allowed_status_without_overage_is_passed_on(short, canned, inproc):
    headers = [("content-type", "application/json"), (f"{RATE}-status", "allowed_warning"),
               (f"{RATE}-overage-status", "rejected"), (f"{RATE}-overage-in-use", "false")]
    upstream = canned(_http(200, headers, json.dumps(_message(USAGE)).encode()))
    sock, state = inproc(upstream.server_address, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    assert (_post(sock, "lh-fake-a", _request(stream=False))[0], _events(state)) == (200, [])


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
if (pathlib.Path(sys.argv[0]).parents[2] / "elsewhere").exists():  # a message that did not pass the passthrough
    session.append({"type": "assistant", "message": {"id": "msg_elsewhere", "model": "claude-haiku-5-5"}})
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
    kit = subprocess.run(["git", "-C", str(REPO), "log", "-1", "--format=%H", "--", str(KIT)], capture_output=True,
                         text=True).stdout.strip()
    ledger = short / "ledger.md"
    ledger.write_text(f"| 2026-11-14 | Live probe approved | {kit} under the stand-in's limits |\n")
    env = {"PATH": f"{NO_PROVIDER}:/usr/bin:/bin", "HOME": str(lh / "home"), "LH": str(lh), "LH_PYTHON": sys.executable,
           "LH_PROBE_COMMIT": kit, "LH_PROBE_STATE": str(short / "probe-state"),
           "LH_TRANSCRIPTS": str(lh / "transcripts"), "LH_PROBE_LEDGER": str(ledger)}

    def run(scenario="normal", out="live-probe", **extra):
        env_run = {**env, "LH_PROBE_STAND_IN": scenario, **extra}
        return subprocess.run(["bash", str(PROBE), str(lh / "recordings" / out)], env=env_run,
                              capture_output=True, text=True, timeout=600)
    run.lh, run.state, run.ledger, run.kit = lh, short / "probe-state", ledger, kit
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
    again = probe(LH_PROBE_SPEND_AUTHORIZED="yes", out="live-probe-again")
    sessions = record["sessions"]
    inspected = sorted(p.name for p in (probe.lh / "recordings" / "live-probe" / "low" / "containers").iterdir())
    assert (result.returncode, record["pass"], record["failures"], [s["effort"] for s in sessions],
            [len(s["requests"]) for s in sessions], [s["first_request_prompt_tokens"] for s in sessions],
            record["file_set_scan"][-2:], [name.split(".")[0] for name in inspected],
            (again.returncode, "has run" in again.stderr)) == (
        0, True, [], ["low", "medium", "high"], [2, 2, 2], [1000, 1000, 1000], ["canary: pass", "exit 0"],
        ["recording-task__abcdef1__env_harbor-docker-egress-control-sidecar_1"] * 2
        + ["recording-task__abcdef1__env_main_1"] * 2, (3, True))


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


def test_a_session_message_missing_from_the_passthroughs_log_fails_the_probe(probe):
    (probe.lh / "elsewhere").write_text("")
    result = probe(LH_PROBE_SPEND_AUTHORIZED="yes")
    record = json.loads((probe.lh / "recordings" / "live-probe" / "probe.json").read_text())
    assert (result.returncode, record["stopped"], record["failures"]) == (1, None, [
        f"{effort}: request msg_elsewhere is not in the passthrough's log as answered 200 by {MODEL} at {effort}"
        for effort in ("low", "medium", "high")])


def test_a_body_larger_than_the_limit_is_refused_unread(short, stub, inproc):
    upstream, upstream_log = stub("normal")
    sock, state = inproc(upstream, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    head = (f"POST {MESSAGES} HTTP/1.1\r\nhost: relay:8080\r\nauthorization: Bearer lh-fake-a\r\n"
            f"content-length: {passthrough.MAX_BODY + 1}\r\n\r\n")
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(WAIT)
        client.connect(str(sock))
        client.sendall(head.encode())
        reply = b""
        while chunk := client.recv(4096):  # the refusal closes the connection
            reply += chunk
        reply = reply.decode()
    assert (reply.split()[1], "lh-passthrough: request too large" in reply, _rows(state)[-1]["refused"],
            _stub_rows(upstream_log)) == ("403", True, "request too large", [])


APPROVAL = "| d | Live probe approved | {kit} under the limits of item 1 |\n"
NEGATED = "| d | Task 4 | the live probe approved row is still missing for `{kit}` |\n"
REFUSED_ROWS = [
    ("a negated sentence", NEGATED),
    ("the phrase in the wrong cell", "| d | {kit} under the limits | Live probe approved |\n"),
    ("two approval rows", APPROVAL * 2),
    ("another commit", APPROVAL.replace("{kit}", "0" * 40)),
    ("the commit's first eight characters", "| d | Live probe approved | {short} under the limits |\n"),
    ("the hash in backticks", "| d | Live probe approved | `{kit}` under the limits |\n"),
    ("the hash running on", "| d | Live probe approved | {kit}0 |\n"),
    ("another phrase", "| d | live probe approved | {kit} under the limits |\n"),
    ("a line that is not a table row", " " + APPROVAL),
]
APPROVED_ROWS = [
    ("the hash and a space", APPROVAL),
    ("the hash and a period", "| d | Live probe approved | {kit}. Limits of item 1 |\n"),
    ("the row beside a negated sentence", NEGATED + APPROVAL),
]


@pytest.mark.parametrize("case,rows", REFUSED_ROWS, ids=[case for case, _ in REFUSED_ROWS])
def test_a_probe_without_exactly_one_approval_row_of_the_fixed_form_is_refused(probe, case, rows):
    probe.ledger.write_text(rows.format(kit=probe.kit, short=probe.kit[:8]))
    result = probe(LH_PROBE_SPEND_AUTHORIZED="yes")
    assert (result.returncode, "| Live probe approved |" in result.stderr, probe.state.exists()) == (3, True, False)


@pytest.mark.parametrize("case,rows", APPROVED_ROWS, ids=[case for case, _ in APPROVED_ROWS])
def test_a_probe_with_exactly_one_approval_row_of_the_fixed_form_passes_the_gate(probe, case, rows):
    probe.ledger.write_text(rows.format(kit=probe.kit))
    (probe.lh / "recordings" / "live-probe").mkdir()  # the next check refuses, so nothing runs
    result = probe(LH_PROBE_SPEND_AUTHORIZED="yes")
    assert (result.returncode, "exists" in result.stderr, "Live probe approved" in result.stderr) == (3, True, False)


def test_a_start_that_fails_before_the_passthrough_listens_claims_nothing(probe):
    failed = probe("no-such-scenario", LH_PROBE_SPEND_AUTHORIZED="yes")
    retried = probe(LH_PROBE_SPEND_AUTHORIZED="yes")
    assert (failed.returncode, retried.returncode) == (4, 0)


def test_within_a_session_the_probe_stops_the_tranche_at_the_first_answer_that_is_not_200(probe):
    probe("overloaded", LH_PROBE_SPEND_AUTHORIZED="yes")
    record = json.loads((probe.lh / "recordings" / "live-probe" / "probe.json").read_text())
    assert [(e["event"], e["reason"]) for e in record["tranche_events"]] == [("stop", "vendor status 529")]


# --- the response: the token never goes back --------------------------------------------------------------

ECHOES = [("plain", 200), ("plain", 401), ("hex", 200), ("HEX", 200), ("base64-0", 200), ("base64-2", 200),
          ("base64url-1", 200), ("utf16le", 200)]


@pytest.mark.parametrize("form,status", ECHOES, ids=[f"{f}-{s}" for f, s in ECHOES])
def test_a_response_body_holding_the_token_is_cut_before_it_and_stops_the_tranche(short, canned, inproc, form, status):
    real = _token()
    prefix = b'{"type": "error", "note": "you sent '
    upstream = canned(_http(status, [("content-type", "application/json")],
                            prefix + token_scan.forms(real)[form] + b'"}'))
    sock, state = inproc(upstream.server_address, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}), token=real)
    request = json.dumps(_request(stream=False)).encode()
    reply = _exchange(sock, _raw(_headers(request), request))
    _eventually(lambda: _rows(state))  # the answer is metered after the client was dropped
    forms = token_scan.forms(real)
    stops = [(e["place"], forms[e["form"]]) for e in _events(state) if e.get("reason") == "token in a response"]
    assert (_found(reply, real), len(reply.partition(b"\r\n\r\n")[2]) <= len(prefix), stops,
            _found(_written(state), real)) == ([], True, [(f"body offset {len(prefix)}", forms[form])], [])


ECHOED_HEADS = [
    ("a header", lambda real: _http(200, [("content-type", "application/json"), ("x-echo", f"Bearer {real}")],
                                    json.dumps(_message(USAGE)).encode()), "header 1 x-echo"),
    ("a logged header", lambda real: _http(200, [("content-type", "application/json"), ("anthropic-echo", real)],
                                           json.dumps(_message(USAGE)).encode()), "header 1 anthropic-echo"),
    ("the status line", lambda real: f"HTTP/1.1 401 {real}\r\ncontent-length: 0\r\n\r\n".encode(), "status line"),
]


@pytest.mark.parametrize("case,head,place", ECHOED_HEADS, ids=[e[0] for e in ECHOED_HEADS])
def test_a_response_head_holding_the_token_sends_nothing_and_stops_the_tranche(short, canned, inproc, case, head,
                                                                              place):
    real = _token()
    upstream = canned(head(real))
    sock, state = inproc(upstream.server_address, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}), token=real)
    request = json.dumps(_request(stream=False)).encode()
    reply = _exchange(sock, _raw(_headers(request), request))
    _eventually(lambda: _rows(state))
    stops = [e["place"] for e in _events(state) if e.get("reason") == "token in a response"]
    assert (reply, stops, _found(_written(state), real)) == (b"", [place], [])


def test_a_token_split_across_two_upstream_writes_is_held_back_and_never_sent(short, canned, inproc):
    real = _token()
    prefix = b'data: {"echo": "'
    body = prefix + real.encode() + b'"}\n\n'
    whole = _http(200, [("content-type", "text/event-stream")], body)
    cut = len(whole) - len(body) + len(prefix) + len(real) // 2
    gate = threading.Event()
    upstream = canned((whole[:cut], gate, whole[cut:]))
    sock, state = inproc(upstream.server_address, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}), token=real)
    request = json.dumps(_request()).encode()
    first = rest = b""
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(WAIT)
        client.connect(str(sock))
        client.sendall(_raw(_headers(request), request))
        while not first.endswith(prefix) and (chunk := client.recv(65536)):  # the bytes before the token's run
            first += chunk
        gate.set()
        while chunk := client.recv(65536):
            rest += chunk
    stops = [e["place"] for e in _events(state) if e.get("reason") == "token in a response"]
    assert (first.endswith(prefix), rest, stops) == (True, b"", [f"body offset {len(prefix)}"])


def test_a_log_row_holding_the_token_keeps_its_numbers_only_and_stops_the_tranche(short, canned, inproc):
    real = _token()
    message = json.dumps(_message(USAGE)).encode()
    upstream = canned(_http(200, [("content-type", "application/json"), ("anthropic-echo", real)], message))
    sock, state = inproc(upstream.server_address, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}), token=real)
    request = json.dumps(_request(stream=False)).encode()
    _exchange(sock, _raw(_headers(request), request))
    row = _eventually(lambda: _rows(state))[0]
    assert (row["withheld"], "headers" in row, round(row["usd"], 12),
            [e["reason"] for e in _events(state) if e["event"] == "stop"]) == (
        "plain", False, round(SMALL_USD, 12), ["token in a response", "token in a log row"])


# --- the request line and headers ------------------------------------------------------------------------

# --- negative cases: framing, headers and bodies outside the recorded shape, and the bounds -------------------

BODY = json.dumps(_request(stream=False)).encode()  # an admitted request, answered by a plain 200
LINE = f"POST {MESSAGES} HTTP/1.1"


def _framed(line=LINE, headers=None, body=BODY):
    return _raw(_headers(BODY) if headers is None else headers, body, line=line)


def _length(value):
    kept = [(k, v) for k, v in _headers(BODY) if k != "content-length"]
    return [*kept, ("content-length", value)] if value is not None else kept


def _send(sock, data):
    """Send `data`, close the sending side, and read every byte back until the passthrough closes."""
    reply = b""
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(WAIT)
        client.connect(str(sock))
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            client.sendall(data)
            client.shutdown(socket.SHUT_WR)
        with contextlib.suppress(TimeoutError, ConnectionResetError):
            while chunk := client.recv(65536):
                reply += chunk
    return reply


def _outcomes(reply):
    """Each answer in a raw reply, in order: a refusal's reason, another answer's status code, or "cut" for a
    reply that is not a whole answer; [] when the connection was closed with no answer."""
    found = []
    while reply:
        head, end, rest = reply.partition(b"\r\n\r\n")
        lines = head.split(b"\r\n")
        sizes = [int(line.split(b":", 1)[1]) for line in lines[1:] if line.lower().startswith(b"content-length:")]
        if not end or not lines[0].startswith(b"HTTP/1.1 ") or len(sizes) != 1 or len(rest) < sizes[0]:
            return [*found, "cut"]
        status, body, reply = lines[0].split(b" ")[1].decode(), rest[:sizes[0]], rest[sizes[0]:]
        found.append(_error(body)[1].removeprefix("lh-passthrough: ") if status == "403" else status)
    return found


FRAMING = [
    ("GET", _framed(line=f"GET {MESSAGES} HTTP/1.1"), ["path not allowed"]),
    ("PUT", _framed(line=f"PUT {MESSAGES} HTTP/1.1"), ["path not allowed"]),
    ("HEAD", _framed(line=f"HEAD {MESSAGES} HTTP/1.1"), ["path not allowed"]),
    ("CONNECT", _framed(line="CONNECT api.anthropic.com:443 HTTP/1.1"), ["path not allowed"]),
    ("a lower-case method", _framed(line=f"post {MESSAGES} HTTP/1.1"), ["path not allowed"]),
    ("an unknown method", _framed(line=f"BREW {MESSAGES} HTTP/1.1"), ["path not allowed"]),
    ("another query", _framed(line="POST /v1/messages?beta=false HTTP/1.1"), ["path not allowed"]),
    ("an extra query", _framed(line="POST /v1/messages?beta=true&x=1 HTTP/1.1"), ["path not allowed"]),
    ("no query", _framed(line="POST /v1/messages HTTP/1.1"), ["path not allowed"]),
    ("a trailing slash", _framed(line="POST /v1/messages/?beta=true HTTP/1.1"), ["path not allowed"]),
    ("another letter case", _framed(line="POST /V1/messages?beta=true HTTP/1.1"), ["path not allowed"]),
    ("a doubled slash", _framed(line="POST //v1/messages?beta=true HTTP/1.1"), ["path not allowed"]),
    ("a percent-encoded letter", _framed(line="POST /v1/m%65ssages?beta=true HTTP/1.1"), ["path not allowed"]),
    ("a percent-encoded query", _framed(line="POST /v1/messages%3Fbeta=true HTTP/1.1"), ["path not allowed"]),
    ("the absolute form", _framed(line="POST http://api.anthropic.com/v1/messages?beta=true HTTP/1.1"),
     ["path not allowed"]),
    ("HTTP/1.0", _framed(line=f"POST {MESSAGES} HTTP/1.0"), ["path not allowed"]),
    ("HTTP/2.0", _framed(line=f"POST {MESSAGES} HTTP/2.0"), ["request malformed"]),
    ("HTTP/0.9", _framed(line=f"POST {MESSAGES}"), ["request malformed"]),
    ("an unknown version", _framed(line=f"POST {MESSAGES} HTTP/1.2"), ["path not allowed"]),
    ("a version that is not HTTP", _framed(line=f"POST {MESSAGES} FTP/1.1"), ["request malformed"]),
    ("a malformed line", _framed(line=f"POST {MESSAGES} HTTP/1.1 extra"), ["request malformed"]),
    ("a line that is not HTTP", _framed(line="hello"), ["request malformed"]),
    ("two content-length headers", _framed(headers=[*_headers(BODY), ("content-length", str(len(BODY)))]),
     ["header repeated"]),
    ("no content-length", _framed(headers=_length(None)), ["request malformed"]),
    ("a length that is not a number", _framed(headers=_length("ten")), ["request malformed"]),
    ("a negative length", _framed(headers=_length("-1")), ["request malformed"]),
    ("a length with a sign", _framed(headers=_length(f"+{len(BODY)}")), ["request malformed"]),
    ("a length with a leading zero", _framed(headers=_length(f"0{len(BODY)}")), ["request malformed"]),
    ("a superscript digit as the length", _framed(headers=_length("\u00b2")), ["request malformed"]),
    ("a length of eleven digits", _framed(headers=_length("1" * 11)), ["request malformed"]),
    ("a length above the body limit", _framed(headers=_length(str(64 << 20 | 1))), ["request too large"]),
    ("transfer-encoding chunked", _framed(headers=[*_headers(BODY), ("transfer-encoding", "chunked")]),
     ["header not allowed"]),
    ("transfer-encoding identity", _framed(headers=[*_headers(BODY), ("Transfer-Encoding", "identity")]),
     ["header not allowed"]),
    ("transfer-encoding without a length", _framed(headers=[*_length(None), ("transfer-encoding", "chunked")]),
     ["header not allowed"]),
    ("a body shorter than its length", _framed(body=BODY[:-10]), ["request malformed"]),
    ("no body after a length", _framed(body=b""), ["request malformed"]),
    ("a body longer than its length", _framed(headers=_length(str(len(BODY) - 1))), ["request malformed"]),
    ("junk after the body", _framed() + b"junk\r\n\r\n", ["200", "request malformed"]),
    ("a forbidden request after the body", _framed() + _framed(line=f"GET {MESSAGES} HTTP/1.1"),
     ["200", "path not allowed"]),
    ("an unknown token's request after the body", _framed() + _raw(_headers(BODY, token="lh-fake-unknown"), BODY),
     ["200", "unknown token"]),
]


@pytest.mark.parametrize("case,data,outcomes", FRAMING, ids=[c[0] for c in FRAMING])
def test_a_malformed_line_or_framing_is_refused_or_closed_and_never_reaches_the_upstream(short, stub, inproc, case,
                                                                                       data, outcomes):
    upstream, upstream_log = stub("normal")
    sock, _ = inproc(upstream, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    assert (_outcomes(_send(sock, data)), len(_stub_rows(upstream_log))) == (outcomes, outcomes.count("200"))


def _replaced(name, value):
    return lambda headers: [(k, value if k == name else v) for k, v in headers]


def _added(*pairs):
    return lambda headers: [*headers, *pairs]


HEADERS = [
    ("two authorization headers", _added(("Authorization", "Bearer lh-fake-a")), "header repeated"),
    ("no authorization", lambda h: [(k, v) for k, v in h if k != "authorization"], "unknown token"),
    ("a Basic scheme", _replaced("authorization", "Basic bGgtZmFrZS1hOg=="), "unknown token"),
    ("a lower-case scheme", _replaced("authorization", "bearer lh-fake-a"), "unknown token"),
    ("no scheme", _replaced("authorization", "lh-fake-a"), "unknown token"),
    ("two spaces after the scheme", _replaced("authorization", "Bearer  lh-fake-a"), "unknown token"),
    ("an unknown token", _replaced("authorization", "Bearer lh-fake-unknown"), "unknown token"),
    ("x-api-key", _added(("x-api-key", "sk-made-up")), "header not allowed"),
    ("a cookie", _added(("cookie", "a=b")), "header not allowed"),
    ("an unrecorded header", _added(("x-probe", "echo")), "header not allowed"),
    ("expect 100-continue", _added(("expect", "100-continue")), "header not allowed"),
    ("an unrecorded beta flag", _added(("anthropic-beta", "files-api-2025-04-14")), "header not allowed"),
    ("an unrecorded flag among recorded ones", _added(("anthropic-beta", "oauth-2025-04-20,files-api-2025-04-14")),
     "header not allowed"),
    ("an empty beta flag", _added(("anthropic-beta", "oauth-2025-04-20,")), "header not allowed"),
    ("another API version", _added(("anthropic-version", "2024-01-01")), "header not allowed"),
    ("another client", _added(("user-agent", "curl/8.0")), "header not allowed"),
    ("a value that is not ASCII", _added(("x-claude-code-session-id", "\u00e9")), "request malformed"),
    ("a NUL in a value", _added(("x-claude-code-session-id", "s\x00s")), "request malformed"),
    ("a folded header line", _added(("x-app", "cli\r\n folded")), "request malformed"),
    ("headers above 32 KiB", _added(("x-claude-code-session-id", "s" * 40000)), "request too large"),
    ("a header line above 64 KiB", _added(("x-claude-code-session-id", "s" * 70000)), "request too large"),
    ("more than 100 headers", _added(*[(f"x-stainless-{i}", "x") for i in range(101)]), "request too large"),
]


@pytest.mark.parametrize("case,change,reason", HEADERS, ids=[c[0] for c in HEADERS])
def test_a_header_set_outside_the_recorded_one_is_refused_in_the_one_form(short, stub, inproc, case, change, reason):
    upstream, upstream_log = stub("normal")
    sock, _ = inproc(upstream, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    body = json.dumps(_request()).encode()
    assert (_reason(_exchange(sock, _raw(change(_headers(body)), body))), _stub_rows(upstream_log)) == (reason, [])


def test_the_committed_allowlist_is_what_the_request_fixtures_give():
    make = _load("make_allowlist")
    assert (KIT / "request_allowlist.json").read_text() == make.render(make.build(make.shapes()))


FILL = {"accept": "application/json", "connection": "keep-alive", "host": "relay:8080"}


def _recorded_tool(name, keys, schema_keys):
    return {**{key: "d" for key in keys}, "name": name, "input_schema": {key: {} for key in schema_keys}}


def _recorded_request(shape):
    """A request in a recorded shape: its headers (a value for each the cutter dropped), its recorded body keys
    and its tools with their recorded keys."""
    body = {**{key: {} for key in shape["body_keys"]}, "model": shape["model"], "max_tokens": shape["max_tokens"],
            "stream": shape["stream"], "output_config": {"effort": shape["effort"]}, "system": [],
            "messages": [{"role": "user", "content": "x"}],
            "tools": list(map(_recorded_tool, shape["tools"], shape["tool_keys"], shape["input_schema_keys"]))}
    data = json.dumps(body).encode()
    headers = {**{k: v or FILL.get(k, "x") for k, v in shape["headers"].items() if k != "x-api-key"},
               "authorization": "Bearer lh-fake-a", "content-length": str(len(data))}
    return http.client.parse_headers(io.BytesIO(_raw(headers.items()).split(b"\r\n", 1)[1])), data


def test_every_recorded_request_shape_passes_the_checks():
    make = _load("make_allowlist")
    reasons = set()
    for shape in make.shapes():
        headers, data = _recorded_request(shape)
        reasons |= {passthrough.header_reason(headers), passthrough.content_reason(passthrough.parse_body(data))}
    assert reasons == {None}


# --- the request's time and size, and the slot's gate ---------------------------------------------------------


def test_an_unknown_token_is_refused_before_any_body_byte_is_read(short, stub, inproc):
    upstream, _ = stub("normal")
    sock, _ = inproc(upstream, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    head = _raw(_headers(b"x" * 1000, token="lh-fake-unknown"))  # the body is never sent
    assert _reason(_exchange(sock, head, timeout=10)) == "unknown token"


def test_a_client_still_sending_its_body_after_a_refusal_reads_the_refusal(short, stub, inproc):
    upstream, _ = stub("normal")
    sock, _ = inproc(upstream, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    body = json.dumps(_request()).encode()
    reply = b""
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(WAIT)
        client.connect(str(sock))
        client.sendall(_raw(_headers(body, token="lh-fake-unknown")))
        time.sleep(0.5)  # the refusal is decided from the headers meanwhile
        client.sendall(body)
        while chunk := client.recv(65536):
            reply += chunk
    assert _reason(reply) == "unknown token"


def test_a_body_that_trickles_past_its_time_is_refused(short, stub, inproc, monkeypatch):
    monkeypatch.setattr(passthrough, "BODY_TIME", 1)
    upstream, upstream_log = stub("normal")
    sock, _ = inproc(upstream, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    body = json.dumps(_request()).encode()
    reply = b""
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(WAIT)
        client.connect(str(sock))
        client.sendall(_raw(_headers(body)))
        for byte in body[:20]:  # one byte every 0.25 s
            with contextlib.suppress(OSError):
                client.sendall(bytes([byte]))
            time.sleep(0.25)
        with contextlib.suppress(ConnectionResetError):
            while chunk := client.recv(65536):
                reply += chunk
    assert (_reason(reply), _stub_rows(upstream_log)) == ("request timed out", [])


def test_headers_that_trickle_past_their_time_cut_the_connection(short, stub, inproc, monkeypatch):
    monkeypatch.setattr(passthrough, "HEADER_TIME", 1)
    upstream, _ = stub("normal")
    sock, _ = inproc(upstream, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    started, closed = time.monotonic(), None
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(0.25)
        client.connect(str(sock))
        client.sendall(f"POST {MESSAGES} HTTP/1.1\r\n".encode())
        while closed is None and time.monotonic() - started < 10:
            with contextlib.suppress(OSError):
                client.sendall(b"x-claude-code-session-id: s\r\n"[:1])
            try:
                if client.recv(65536) == b"":
                    closed = time.monotonic() - started
            except TimeoutError:
                pass
            except OSError:
                closed = time.monotonic() - started
    assert closed is not None and closed < 5


def test_connections_beyond_the_cap_are_refused_until_one_closes(short, stub, inproc, monkeypatch):
    monkeypatch.setattr(passthrough, "MAX_CONNECTIONS", 2)
    upstream, _ = stub("normal")
    sock, _ = inproc(upstream, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    idle = [socket.socket(socket.AF_UNIX) for _ in range(2)]
    for client in idle:
        client.connect(str(sock))
    time.sleep(0.5)  # both are accepted and wait for a request line
    over = _reason(_exchange(sock, b"", timeout=10))
    for client in idle:
        client.close()

    def served():
        try:
            return _post(sock, "lh-fake-a", _request())[0] == 200
        except (OSError, http.client.HTTPException):  # refused at once while the idle ones are still counted
            return False
    assert (over, _eventually(served)) == ("too many connections", True)


def test_connections_beyond_the_cap_are_refused_while_an_admitted_request_completes(short, canned, inproc,
                                                                                    monkeypatch):
    monkeypatch.setattr(passthrough, "MAX_CONNECTIONS", 2)
    gate, responses = _gated(0)
    upstream = canned(*responses)
    sock, _ = inproc(upstream.server_address, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    admitted = []
    thread = threading.Thread(target=lambda: admitted.append(_post(sock, "lh-fake-a", _request(stream=False))[0]))
    thread.start()
    _eventually(lambda: upstream.received)  # the admitted request is in flight, its answer held
    with socket.socket(socket.AF_UNIX) as idle:
        idle.connect(str(sock))  # the second connection; connections are accepted in order
        over = _reason(_exchange(sock, b"", timeout=10))
    gate.set()
    thread.join(WAIT)
    assert (over, admitted) == ("too many connections", [200])


# A socket per attempt (Task 5, connections): a slot marked own_socket is served on its own socket, alone.

def _own(token):
    return {**_slot(token), "own_socket": True}


@pytest.fixture
def sockets(short):
    """A passthrough in this process with its main socket and its slots' own sockets (synced once at the start)."""
    made = []

    def start(upstream, slots, token="real-token-made-up-for-this-test"):
        name = f"own{len(made)}"
        state, relay = short / f"{name}-state", short / name
        state.mkdir(mode=0o700)
        relay.mkdir(mode=0o700)
        pt = passthrough.Passthrough(state, slots, token, "live", passthrough.unix_upstream(str(upstream)))
        main = relay / "passthrough.sock"
        server = passthrough.serve(str(main), pt)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        own = passthrough.Sockets(pt, main)
        made.append((server, own))
        own.sync()
        return main, own
    yield start
    for server, own in made:
        own.close_all()
        server.shutdown()
        server.server_close()


def test_a_slot_with_its_own_socket_is_served_there_and_its_token_nowhere_else(short, stub, sockets):
    upstream, _ = stub("normal")
    slots = _slots(short / "slots.json", {"a": _own("lh-fake-a"), "b": _own("lh-fake-b"), "c": _slot("lh-fake-c")},
                   total_usd=5.0)
    main, own = sockets(upstream, slots)
    served = [_post(own.path("a"), "lh-fake-a", _request())[0], _post(main, "lh-fake-c", _request())[0]]
    refused = [_error(_post(sock, token, _request())[2])[1]
               for sock, token in ((main, "lh-fake-a"), (own.path("a"), "lh-fake-b"), (own.path("a"), "lh-fake-c"))]
    logged = [(r["slot"], r["status"], r["refused"]) for r in _rows(short / "own0-state") if "refused" in r]
    assert (served, refused, logged, oct(own.path("a").parent.stat().st_mode & 0o777)) == (
        [200, 200], ["lh-passthrough: unknown token"] * 3, [(None, 403, "unknown token")] * 3, "0o700")


def test_one_slot_s_connections_never_count_against_another_slot_s_socket(short, stub, sockets, monkeypatch):
    monkeypatch.setattr(passthrough, "MAX_CONNECTIONS", 2)
    upstream, _ = stub("normal")
    main, own = sockets(upstream, _slots(short / "slots.json", {"a": _own("lh-fake-a"), "b": _own("lh-fake-b")},
                                         total_usd=5.0))
    idle = [socket.socket(socket.AF_UNIX) for _ in range(2)]
    for client in idle:
        client.connect(str(own.path("a")))
    time.sleep(0.5)  # both are accepted and wait for a request line
    over = _reason(_exchange(own.path("a"), b"", timeout=10))
    served = _post(own.path("b"), "lh-fake-b", _request())[0]
    for client in idle:
        client.close()
    logged = [r["slot"] for r in _rows(short / "own0-state") if r.get("refused") == "too many connections"]
    assert (over, served, logged) == ("too many connections", 200, ["a"])  # Task 8 part A m6: its own slot


def test_a_retired_slot_s_socket_and_its_directory_are_removed(short, stub, sockets):
    upstream, _ = stub("normal")
    slots = _slots(short / "slots.json", {"a": _own("lh-fake-a")})
    main, own = sockets(upstream, slots)
    before = own.path("a").exists()
    _slots(slots, {})
    own.sync()
    assert (before, own.path("a").parent.exists(), sorted(own.open)) == (True, False, [])


@pytest.mark.parametrize("name", ["../a", ".a", "a/b", "x" * 65, ""])
def test_a_slot_whose_name_is_not_a_plain_name_gets_no_socket(short, stub, sockets, name):
    upstream, _ = stub("normal")
    main, own = sockets(upstream, _slots(short / "slots.json", {name: _own("lh-fake-a")}))
    assert (sorted(own.open), sorted(p.name for p in main.parent.iterdir())) == ([], ["passthrough.sock"])


def test_the_process_opens_a_slot_s_socket_when_the_slots_file_names_it_and_removes_it_when_it_ends(short, stub):
    upstream, _ = stub("normal")
    slots = _slots(short / "slots.json", {})
    proc, sock, state, out = _start(short, slots, *_rehearsal(short, upstream))
    _slots(slots, {"a": _own("lh-fake-a")})
    path = sock.parent / "a" / "passthrough.sock"
    opened = _eventually(path.exists)
    status = _post(path, "lh-fake-a", _request())[0]
    _stop(proc)
    assert (opened, status, path.parent.exists()) == (True, 200, False)


def _descriptors():
    return len(os.listdir("/proc/self/fd"))


def test_after_200_connections_opened_and_closed_its_open_descriptors_are_back_to_where_they_started(short, stub,
                                                                                                   inproc):
    """In this process: passthrough.py's own process is not dumpable, so its /proc/<pid>/fd cannot be read."""
    upstream, _ = stub("normal")
    sock, _ = inproc(upstream, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    refused = _raw(_headers(BODY, token="lh-fake-unknown"))

    def cycle(i):
        with socket.socket(socket.AF_UNIX) as client:
            client.connect(str(sock))
            if i % 2:  # every other one sends a refused head and leaves without reading the refusal
                client.sendall(refused)

    def settled(count):
        deadline = time.monotonic() + WAIT
        while _descriptors() != count and time.monotonic() < deadline:
            time.sleep(0.1)
        return _descriptors()
    cycle(0), cycle(1), _post(sock, "lh-fake-a", _request(stream=False))  # the log and the meter have been used
    time.sleep(1)
    before = _descriptors()
    for i in range(200):
        cycle(i)
    assert settled(before) == before


def test_after_every_negative_case_a_recorded_request_is_admitted_and_metered_and_nothing_failed_unhandled(short,
                                                                                                          stub):
    upstream, upstream_log = stub("normal")
    proc, sock, state, out = _start(short, _slots(short / "slots.json", {"a": _slot("lh-fake-a", cap_usd=10.0)},
                                                  total_usd=10.0), *_rehearsal(short, upstream))
    body = json.dumps(_request()).encode()
    rows = [(case, data, outcomes) for case, data, outcomes in FRAMING]
    rows += [(case, _raw(change(_headers(body)), body), [reason]) for case, change, reason in HEADERS]
    rows += [(case, _raw(_headers(b), b), [reason]) for case, b, reason in
             ((c, b if isinstance(b, bytes) else json.dumps(b).encode(), r) for c, b, r in CONTENT)]
    wrong = [case for case, data, outcomes in rows if _outcomes(_send(sock, data)) != outcomes]
    status = _post(sock, "lh-fake-a", _request(stream=False))[0]
    text = out.read_text()
    assert (wrong, status, _rows(state)[-1]["usd"] > 0, len(_stub_rows(upstream_log)),
            "Traceback" in text or "lh-passthrough: error" in text, proc.poll()) == (
        [], 200, True, sum(o.count("200") for _, _, o in rows) + 1, False, None)


def _gated(more):
    """A plain 200 whose body waits for the test's signal, then `more` plain 200s: (gate, responses)."""
    gate = threading.Event()
    body = json.dumps(_message(USAGE)).encode()
    head = _http(200, [("content-type", "application/json")], body)[:-len(body)]
    return gate, [(head, gate, body), *[_http(200, [("content-type", "application/json")], body)] * more]


def test_a_third_open_request_of_one_slot_is_refused(short, canned, inproc):
    gate, responses = _gated(1)
    upstream = canned(*responses)
    sock, _ = inproc(upstream.server_address, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    results = []
    post = lambda: results.append(_post(sock, "lh-fake-a", _request(stream=False)))  # noqa: E731
    threads = [threading.Thread(target=post)]
    threads[0].start()
    _eventually(lambda: upstream.received)  # the first is in flight
    threads += [threading.Thread(target=post) for _ in range(2)]
    for thread in threads[1:]:
        thread.start()
    _eventually(lambda: results)  # one of the two is refused at once; the other waits for its slot
    gate.set()
    for thread in threads:
        thread.join(WAIT)
    assert sorted((status, _error(data)[1] if status == 403 else None) for status, _, data in results) == [
        (200, None), (200, None), (403, "lh-passthrough: too many connections")]


def test_a_request_waiting_on_its_slot_past_the_wait_is_refused_as_busy(short, canned, inproc, monkeypatch):
    monkeypatch.setattr(passthrough, "SLOT_WAIT", 1)
    gate, responses = _gated(0)
    upstream = canned(*responses)
    sock, _ = inproc(upstream.server_address, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    first = []
    thread = threading.Thread(target=lambda: first.append(_post(sock, "lh-fake-a", _request(stream=False))[0]))
    thread.start()
    _eventually(lambda: upstream.received)
    status, _, data = _post(sock, "lh-fake-a", _request(stream=False))
    gate.set()
    thread.join(WAIT)
    assert (status, _error(data)[1], first) == (403, "lh-passthrough: slot busy", [200])


def test_twenty_clients_on_one_slot_overshoot_its_cap_by_less_than_one_response(short, stub, inproc, monkeypatch):
    """One request in flight per slot, each checked with the one before it metered: below cap + one response."""
    monkeypatch.setattr(passthrough, "MAX_PER_SLOT", 32)
    monkeypatch.setattr(passthrough, "MAX_CONNECTIONS", 64)
    upstream, _ = stub("slow", "--delay", "0.5")
    cap = SMALL_USD * 2.5
    sock, state = inproc(upstream, _slots(short / "slots.json", {"a": _slot("lh-fake-a", cap_usd=cap)}))
    statuses = _concurrently([lambda: _post(sock, "lh-fake-a", _request(turn=1))[0]] * 20)
    overshoot = sum(r.get("usd") or 0 for r in _rows(state)) - cap
    assert (statuses.count(200), 0 <= overshoot < SMALL_USD) == (3, True)


def test_four_slots_at_once_overshoot_the_tranche_total_by_less_than_one_response_each(short, stub, inproc,
                                                                                        monkeypatch):
    """The total is checked under one lock; at most one unmetered response per slot: below total + 4 responses."""
    monkeypatch.setattr(passthrough, "MAX_PER_SLOT", 32)
    monkeypatch.setattr(passthrough, "MAX_CONNECTIONS", 64)
    upstream, _ = stub("slow", "--delay", "0.5")
    total = SMALL_USD * 2.5
    slots = {name: _slot(f"lh-fake-{name}") for name in "abcd"}
    sock, state = inproc(upstream, _slots(short / "slots.json", slots, total_usd=total))
    _concurrently([lambda n=name: _post(sock, f"lh-fake-{n}", _request(turn=1))[0] for name in "abcd" for _ in range(5)])
    overshoot = sum(r.get("usd") or 0 for r in _rows(state)) - total
    assert 0 <= overshoot < 4 * SMALL_USD


# --- the meter, to the end of every answer ----------------------------------------------------------------


@pytest.mark.parametrize("left", ["before the head", "after the head"])
def test_an_answer_whose_client_went_away_is_read_and_metered_to_its_end(short, canned, inproc, left):
    stream = _sse(_message(USAGE))
    whole = _http(200, [("content-type", "text/event-stream")], stream)
    cut = 0 if left == "before the head" else len(whole) - len(stream) + 10
    end = whole.index(b"event: message_delta")  # the usage comes in a later write than the first one after the gate
    gate = threading.Event()
    upstream = canned((whole[:cut], gate, [whole[cut:end], whole[end:]]))
    sock, state = inproc(upstream.server_address, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    request = json.dumps(_request()).encode()
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(WAIT)
        client.connect(str(sock))
        client.sendall(_raw(_headers(request), request))
        _ = client.recv(12) if cut else _eventually(lambda: upstream.received)
    gate.set()  # the rest of the answer comes after the client is gone
    rows = _eventually(lambda: _rows(state))
    assert (round(rows[0]["usd"], 12), rows[0]["worst_case"]) == (round(SMALL_USD, 12), False)


def test_a_stream_that_ends_before_its_message_stop_is_priced_at_the_requests_worst_case(short, canned, inproc):
    stream = _sse(_message(USAGE))
    upstream = canned(_http(200, [("content-type", "text/event-stream")],
                            stream[:stream.index(b"event: message_delta")]))
    sock, state = inproc(upstream.server_address, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    _post(sock, "lh-fake-a", _request())
    worst = _bound(max(len(json.dumps(_request())), USAGE["input_tokens"]), 1000)  # message_start's prompt is larger
    assert (round(_rows(state)[0]["usd"], 12), _rows(state)[0]["worst_case"],
            [(e["event"], e["reason"]) for e in _events(state)]) == (
        round(worst, 12), True, [("close_starts", "usage incomplete")])


def test_a_null_in_a_usage_delta_leaves_the_figure_before_it(short, canned, inproc):
    stream = _sse(_message(USAGE)).replace(b'"usage": {"output_tokens": 100}',
                                           b'"usage": {"output_tokens": 100, "input_tokens": null}')
    upstream = canned(_http(200, [("content-type", "text/event-stream")], stream))
    sock, state = inproc(upstream.server_address, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}))
    _post(sock, "lh-fake-a", _request())
    assert round(_rows(state)[0]["usd"], 12) == round(SMALL_USD, 12)


# --- the start: the token file, the slots, the trust store, the probe's switch ----------------------------------


def test_a_token_file_reached_through_a_symlinked_directory_is_refused(short):
    token_file = _secret_file(short, _token())
    (short / "link").symlink_to(token_file.parent)
    with pytest.raises(OSError):
        passthrough.read_token(short / "link" / "token")


def test_two_slots_with_one_fake_token_are_refused(short, stub):
    upstream, _ = stub("normal")
    state = short / "state"
    state.mkdir(mode=0o700)
    with pytest.raises(passthrough.Refused, match="own fake token"):
        passthrough.Passthrough(state, _slots(short / "slots.json", {"a": _slot("lh-fake-x"), "b": _slot("lh-fake-x")}),
                                "t", "live", passthrough.unix_upstream(str(upstream)))


def test_the_vendor_client_trusts_pythons_own_store_whatever_the_environment_names(short, monkeypatch):
    (short / "empty.pem").write_text("")
    monkeypatch.setenv("SSL_CERT_FILE", str(short / "empty.pem"))
    monkeypatch.setenv("SSL_CERT_DIR", str(short))
    ours = passthrough.vendor_upstream()()._context.cert_store_stats()["x509_ca"]
    assert (ssl.create_default_context().cert_store_stats()["x509_ca"], ours > 0) == (0, True)


def test_with_the_probes_switch_any_answer_but_200_stops_the_tranche(short, stub, inproc):
    upstream, _ = stub("overloaded")
    sock, state = inproc(upstream, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}), stop_on_non_200=True)
    first = _post(sock, "lh-fake-a", _request(turn=1))[0]
    after, _, data = _post(sock, "lh-fake-a", _request(turn=1))
    assert (first, [(e["event"], e["reason"]) for e in _events(state)], after, _error(data)[1]) == (
        529, [("stop", "vendor status 529")], 403, "lh-passthrough: tranche stopped")


# --- the live probe's recorded answers (fixtures/live-probe, cut by cut_fixture.py live-probe) ---------------------

PROBE_FIXTURES = KIT / "fixtures" / "live-probe"
PROBE_ROWS = json.loads((PROBE_FIXTURES / "passthrough-log.json").read_text())["requests"]


@pytest.mark.parametrize("row", PROBE_ROWS, ids=[row["effort"] for row in PROBE_ROWS])
def test_a_recorded_vendor_200_with_overage_rejected_is_passed_on_unstopped_and_priced_at_the_cli_s_cost(
        short, canned, inproc, row):
    """Ruling LH-R1: the header set of an ordinary 200 of the live probe (`overage-status: rejected`, unified status
    `allowed_warning`) neither stops the tranche nor closes starts, with the probe's own switch on; and the meter
    prices the recorded usage to the figure the probe logged, which is the CLI's `total_cost_usd` for that session."""
    session = json.loads((PROBE_FIXTURES / f"session-{row['effort']}.json").read_text())
    cli_total = next(e for e in session["stream_tail"] if e["type"] == "result")["total_cost_usd"]
    headers = [("content-type", "text/event-stream"), *row["headers"].items()]
    upstream = canned(_http(200, headers, _sse(_message(row["usage"]))))
    sock, state = inproc(upstream.server_address, _slots(short / "slots.json", {"a": _slot("lh-fake-a")}),
                         stop_on_non_200=True)
    status = _post(sock, "lh-fake-a", _request())[0]
    logged = _eventually(lambda: _rows(state))[0]
    assert (status, _events(state), logged["passed_on"], round(logged["usd"], 12), round(cli_total, 12)) == (
        200, [], True, round(row["usd"], 12), round(row["usd"], 12))
