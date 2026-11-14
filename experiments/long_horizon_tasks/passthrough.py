"""The long-horizon passthrough (plan D4; Task 4, first slice): the one host process that holds the owner's
subscription token, meters every request and enforces the caps.

It listens on one unix socket only; the relay container forwards its one TCP port to it. For each request it
maps the fake bearer token to a slot. It refuses, in one form (HTTP 403 `permission_error`,
`x-should-retry: false`, message `lh-passthrough: <reason>`, connection closed): any request but
`POST /v1/messages?beta=true` ("path not allowed"); an unknown token ("unknown token"); a stopped tranche
("tranche stopped"); any model but the price rule's exact id, or a body that is not JSON ("model not
allowed"); a request that declares a provider-side tool, one without `input_schema` ("provider-side tool
refused"); a body above 64 MiB or without a valid length, unread ("request too large"); a slot at its
request count or priced cap ("slot cap reached"); the tranche at its request count or priced total
("tranche total reached"). Otherwise it replaces the value of the `authorization` header with
`Bearer <real token>`, sets `host` to the vendor's host (the server it connects to) and changes no other byte
of the request. It passes the vendor's response through unchanged (a chunked body is re-chunked) and prices
its usage by `price_rule.json` (`price_check.price`, each cache write at its own lifetime's rate), metering a
response in flight at a cap to its end; the caps act on the next request.

The vendor's answers, acted on before the response is passed on: a 429 closes starts (reason "usage limit"
with its `anthropic-ratelimit-unified-reset` when `anthropic-ratelimit-unified-status` is `rejected`, else
"vendor 429" with no reset); a 401 stops the tranche; a configured paid-usage header value (--paid-usage,
from the recording of Task 2a; none is configured until one is recorded) stops it. After the body: a response
naming another model stops it; a 200 whose usage the meter cannot read closes starts ("usage unreadable").
Starts are the launcher's: the passthrough records `close_starts` and never refuses on it.

State, in DIR (mode 700, this user's; the output file belongs there too):
  requests.jsonl  one row per request: time, slot, path, credential, model, effort, declared tools, status,
                  the logged response headers (anthropic-*, retry-after, x-should-retry, request-id, the
                  paid-usage names), usage as reported, its price, response model, message id, a refusal
                  reason or an error class. Never a request header. It is the meter: a restart sums it.
  tranche.jsonl   events: close_starts and stop (written here), stop and resume (written by the launcher or a
                  person); every request is refused while the last stop or resume is a stop.
  fingerprint.json  salt, length and salted SHA-256 of the token (token_scan.py), written at the start.
The slots file, re-read on every request (the launcher replaces it atomically):
  {"total_usd": T (at most 200), "total_requests": N or null,
   "slots": {NAME: {"token": FAKE, "cap_usd": C, "cap_requests": M or null}}}

The token: --token-file is opened once, at the start, and refused unless it is a regular file of mode 600 in
a directory of mode 700, both this user's, holding one bearer token (RFC 6750 b64token). It is in no argument,
environment, log row or exception text: errors print the exception's class and this module's own message.
Core dumps are off and the process is not dumpable. It starts no child process. The vendor client is
`http.client` (it reads no proxy variable), verifies TLS and connects to api.anthropic.com:443 only.
--rehearsal connects to a stand-in's unix socket instead, refuses --token-file, and holds a canary it makes
itself and writes once to --canary-out (a new mode-600 file, outside the scanned file set).

Usage: python -I passthrough.py --socket PATH --state DIR --slots FILE [--paid-usage HEADER=VALUE]...
         (--token-file FILE | --rehearsal STAND_IN_SOCKET --canary-out FILE --canary-length N)
Prints `listening <socket>` once bound. Exit 2: refused at the start. SIGTERM: records close_starts
("passthrough down"), removes the socket, exits 0. A crash leaves no such record: the launcher (Task 5) must
treat an unanswered socket as the passthrough being down.
"""

import argparse
import ctypes
import http.client
import importlib.util
import json
import os
import re
import resource
import secrets
import signal
import socket
import socketserver
import ssl
import stat
import string
import sys
import threading
import time
import zlib
from http.server import BaseHTTPRequestHandler
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _kit(name):
    spec = importlib.util.spec_from_file_location(f"lh_{name}", HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


price_check, token_scan = _kit("price_check"), _kit("token_scan")
RULE = price_check.load_rule()
MODEL = RULE["model"]
MESSAGES = "/v1/messages?beta=true"  # the only path any recording shows
VENDOR = "api.anthropic.com"
CEILING_USD = 200.0  # the approval's ceiling; no slots file may set a larger total
BEARER = re.compile(r"[A-Za-z0-9\-._~+/]+=*")
LOGGED = ("retry-after", "x-should-retry", "request-id")
READ = 65536
MAX_BODY = 64 << 20  # bytes; a request body above it is refused unread (the relay's port is the agent's to reach)
UPSTREAM_TIMEOUT = 900  # seconds without a byte; a long output streams for minutes
SLOTS_ERRORS = (OSError, ValueError, KeyError, TypeError, AttributeError)


class Refused(Exception):
    """A refusal at the start; its message names the reason and never a secret."""


def _owned(st, mode, what):
    if st.st_uid != os.getuid():
        raise Refused(f"{what} is not owned by this user")
    if stat.S_IMODE(st.st_mode) != mode:
        raise Refused(f"{what} has mode {stat.S_IMODE(st.st_mode):o}, not {mode:o}")


def read_token(path):
    """The token in `path`, checked as D4's token path requires; the file is read here and nowhere else."""
    path = os.path.abspath(path)
    _owned(os.stat(os.path.dirname(path)), 0o700, "the token file's directory")
    st = os.lstat(path)
    if not stat.S_ISREG(st.st_mode):
        raise Refused("the token file is not a regular file")
    _owned(st, 0o600, "the token file")
    with open(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as fh:
        value = fh.read().decode("ascii", "replace").strip()
    if not BEARER.fullmatch(value):
        raise Refused("the token file does not hold one bearer token")
    return value


def make_canary(path, length):
    """A canary of `length` base64url characters, written once to a new mode-600 file (the rehearsal's token)."""
    value = "".join(secrets.choice(string.ascii_letters + string.digits + "-_") for _ in range(length))
    with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as fh:
        fh.write(value + "\n")
    return value


def _json(data):
    try:
        return json.loads(data)
    except ValueError:  # an unreadable body is refused or metered as unreadable, never raised
        return None


def _jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def _price(usage):
    try:
        return price_check.price({"input_tokens": 0, "output_tokens": 0, **usage}, RULE)
    except (TypeError, KeyError, AttributeError):  # usage of an unknown shape is unreadable, not a crash
        return None


def _bearer(value):
    return value[len("Bearer "):] if value and value.startswith("Bearer ") else None


def _content_reason(request):
    if not isinstance(request, dict) or request.get("model") != MODEL:
        return "model not allowed"
    tools = request.get("tools") or []
    if not isinstance(tools, list) or any(not isinstance(t, dict) or "input_schema" not in t for t in tools):
        return "provider-side tool refused"
    return None


def _reached(count, cap):
    return cap is not None and count >= cap


def _row(slot, path, request, credential):
    request = request if isinstance(request, dict) else {}
    tools = request.get("tools") if isinstance(request.get("tools"), list) else []
    config = request.get("output_config") if isinstance(request.get("output_config"), dict) else {}
    return {"time": time.time(), "slot": slot, "path": path, "credential": credential, "model": request.get("model"),
            "effort": config.get("effort"),
            "tools": [t.get("name") or t.get("type") for t in tools if isinstance(t, dict)]}


class Meter:
    """Reads usage, model and message id from a response's bytes as they are passed on, streamed or plain."""

    def __init__(self, headers):
        encoding = (headers.get("content-encoding") or "identity").lower()
        self.stream = (headers.get("content-type") or "").startswith("text/event-stream")
        self.readable = encoding in ("identity", "gzip", "deflate")
        self.inflate = zlib.decompressobj(47) if encoding in ("gzip", "deflate") else None  # 47: gzip or zlib
        self.buf, self.message, self.delta, self.complete = b"", None, {}, False

    def feed(self, data):
        if not self.readable:
            return
        try:
            self.buf += self.inflate.decompress(data) if self.inflate else data
        except zlib.error:  # a body the meter cannot decode is still passed on; its usage is unreadable
            self.readable = False
            return
        if self.stream:
            *lines, self.buf = self.buf.split(b"\n")
            for line in lines:
                if line.startswith(b"data:"):
                    self._event(_json(line[5:]))

    def _event(self, event):
        kind = event.get("type") if isinstance(event, dict) else None
        if kind == "message_start":
            self.message = event.get("message")
        elif kind == "message_delta" and isinstance(event.get("usage"), dict):
            self.delta.update(event["usage"])  # cumulative counts: the last delta's figures stand
        elif kind == "message_stop":
            self.complete = True

    def result(self):
        """(usage, model, message id); usage None when it cannot be read."""
        message = self.message if self.stream else _json(self.buf) if self.readable else None
        if not self.readable or not isinstance(message, dict) or not isinstance(message.get("usage"), dict):
            return None, None, None
        return {**message["usage"], **self.delta}, message.get("model"), message.get("id")


class Passthrough:
    """One token, one upstream, one meter, the caps and the tranche's events."""

    def __init__(self, state, slots, token, credential, upstream, paid_usage=()):
        self.state, self.slots_file = Path(state), Path(slots)
        self.authorization = f"Bearer {token}"
        self.credential, self.upstream = credential, upstream
        self.paid_usage = [(name.lower(), value) for name, value in paid_usage]
        self.lock, self.write_lock = threading.Lock(), threading.Lock()
        self.spent, self.count = {}, {}
        for row in _jsonl(self.state / "requests.jsonl"):
            if "refused" not in row and row.get("slot"):
                self._add(row["slot"], row.get("usd") or 0.0, 1)
        self.load_slots()

    def _add(self, slot, usd, n):
        self.spent[slot] = self.spent.get(slot, 0.0) + usd
        self.count[slot] = self.count.get(slot, 0) + n

    def load_slots(self):
        data = json.loads(self.slots_file.read_text())
        if not 0 < data["total_usd"] <= CEILING_USD:
            raise Refused(f"total_usd {data['total_usd']} is outside (0, {CEILING_USD}], the approved ceiling")
        for name, slot in data["slots"].items():
            if not isinstance(slot["token"], str) or not slot["cap_usd"] > 0:
                raise Refused(f"slot {name} needs a token and a positive cap_usd")
        return data, {slot["token"]: name for name, slot in data["slots"].items()}

    def _append(self, name, row):
        with self.write_lock, open(self.state / name, "a") as fh:
            fh.write(json.dumps(row) + "\n")

    def log(self, row):
        self._append("requests.jsonl", row)

    def event(self, kind, **fields):
        self._append("tranche.jsonl", {"time": time.time(), "event": kind, **fields})

    def stopped(self):
        try:
            marks = [e["event"] for e in _jsonl(self.state / "tranche.jsonl") if e.get("event") in ("stop", "resume")]
        except ValueError:  # a tranche file that cannot be read keeps the tranche stopped
            return True
        return bool(marks) and marks[-1] == "stop"

    def admit(self, method, path, authorization, request):
        """(slot or None, refusal reason or None); a request let through is counted at once."""
        if method != "POST" or path != MESSAGES:
            return None, "path not allowed"
        try:
            slots, tokens = self.load_slots()
        except (Refused, *SLOTS_ERRORS) as exc:
            self.event("stop", reason=f"slots file unreadable ({type(exc).__name__})")
            return None, "tranche stopped"
        slot = tokens.get(_bearer(authorization))
        if slot is None:
            return None, "unknown token"
        reason = "tranche stopped" if self.stopped() else _content_reason(request)
        with self.lock:
            reason = reason or self._cap_reason(slot, slots)
            if reason is None:
                self._add(slot, 0.0, 1)
        return slot, reason

    def _cap_reason(self, slot, slots):
        cap = slots["slots"][slot]
        if _reached(self.count.get(slot, 0), cap.get("cap_requests")) or self.spent.get(slot, 0.0) >= cap["cap_usd"]:
            return "slot cap reached"
        if _reached(sum(self.count.values()), slots.get("total_requests")) or \
                sum(self.spent.values()) >= slots["total_usd"]:
            return "tranche total reached"
        return None

    def on_headers(self, slot, status, headers):
        """What the vendor's answer closes or stops, recorded before the answer is passed on."""
        if status == 401:
            self.event("stop", slot=slot, reason="vendor 401")
        if status == 429:
            limit = headers.get("anthropic-ratelimit-unified-status") == "rejected"
            self.event("close_starts", slot=slot, status=status, reason="usage limit" if limit else "vendor 429",
                       reset=headers.get("anthropic-ratelimit-unified-reset") if limit else None)
        if any(headers.get(name) == value for name, value in self.paid_usage):
            self.event("stop", slot=slot, reason="paid extra usage")

    def settle(self, slot, row, meter):
        usage, model, message_id = meter.result()
        usd = _price(usage) if usage is not None else None
        with self.lock:
            self._add(slot, usd or 0.0, 0)
            row.update(usd=usd, slot_usd=self.spent[slot], total_usd=sum(self.spent.values()))
        self.log({**row, "usage": usage, "response_model": model, "message_id": message_id})
        if row.get("status") == 200 and usd is None:
            self.event("close_starts", slot=slot, reason="usage unreadable", reset=None)
        if model not in (None, MODEL):
            self.event("stop", slot=slot, reason=f"response model {model}")

    def logged_headers(self, headers):
        names = {name for name, _ in self.paid_usage}
        return {k.lower(): v for k, v in headers.items()
                if k.lower().startswith("anthropic-") or k.lower() in LOGGED or k.lower() in names}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # the request line stays out of the output
        pass

    def _handle(self):
        pt = self.server.pt
        length = self.headers.get("content-length") or "0"
        if not length.isdigit() or int(length) > MAX_BODY:
            pt.log({**_row(None, self.path, None, pt.credential), "status": 403, "refused": "request too large"})
            return self._refuse("request too large")
        body = self.rfile.read(int(length))
        request = _json(body)
        slot, reason = pt.admit(self.command, self.path, self.headers.get("authorization"), request)
        row = _row(slot, self.path, request, pt.credential)
        if reason:
            pt.log({**row, "status": 403, "refused": reason})
            return self._refuse(reason)
        conn = pt.upstream()
        try:
            resp = self._send(conn, pt, body)
        except (OSError, http.client.HTTPException) as exc:  # nothing came back: the client sees a dropped line
            conn.close()
            return self._fault(pt, {**row, "status": None}, exc)
        row.update(status=resp.status, headers=pt.logged_headers(resp.headers))
        meter, settled = Meter(resp.headers), []

        def settle():  # once: before the last bytes reach the client when the end is known, else at the end
            if not settled:
                settled.append(pt.settle(slot, row, meter))
        pt.on_headers(slot, resp.status, resp.headers)
        try:
            self._relay(resp, meter, settle)
        except (OSError, http.client.HTTPException) as exc:  # a fault mid-body: what was read is still metered
            row["error"] = type(exc).__name__
            self._fault(pt, None, exc)
        finally:
            conn.close()
            settle()

    do_POST = do_GET = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _handle

    def _send(self, conn, pt, body):
        conn.putrequest(self.command, self.path, skip_host=True, skip_accept_encoding=True)
        for name, value in self.headers.items():
            low = name.lower()
            conn.putheader(name, pt.authorization if low == "authorization" else VENDOR if low == "host" else value)
        conn.endheaders(body)
        return conn.getresponse()

    def _relay(self, resp, meter, settle):
        close_delimited = not resp.chunked and resp.length is None
        self.send_response_only(resp.status, resp.reason)
        for name, value in resp.getheaders():
            self.send_header(name, value)
        self.end_headers()
        while data := resp.read1(READ):
            meter.feed(data)
            if meter.complete or resp.length == 0:  # the message or the body is whole: meter it, then pass it on
                settle()
            self.wfile.write(b"%x\r\n%s\r\n" % (len(data), data) if resp.chunked else data)
        if resp.chunked:
            self.wfile.write(b"0\r\n\r\n")
        self.close_connection = self.close_connection or close_delimited

    def _fault(self, pt, row, exc):
        if row is not None:
            pt.log({**row, "error": type(exc).__name__})
        print(f"lh-passthrough: upstream error {type(exc).__name__}", flush=True)
        self.close_connection = True

    def _refuse(self, reason):
        data = json.dumps({"type": "error", "error": {"type": "permission_error",
                                                      "message": f"lh-passthrough: {reason}"}}).encode()
        self.send_response_only(403, "Forbidden")
        for name, value in (("content-type", "application/json"), ("x-should-retry", "false"),
                            ("content-length", str(len(data))), ("connection", "close")):
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)


class _Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True

    def handle_error(self, request, client_address):  # the class only: an exception's text may quote a header
        print(f"lh-passthrough: error {sys.exc_info()[0].__name__}", flush=True)


def serve(socket_path, pt):
    server = _Server(socket_path, Handler)
    server.pt = pt
    return server


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("stand-in", timeout=UPSTREAM_TIMEOUT)
        self.unix_path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.unix_path)


def unix_upstream(path):
    return lambda: _UnixConnection(path)


def vendor_upstream():
    context = ssl.create_default_context()
    return lambda: http.client.HTTPSConnection(VENDOR, 443, timeout=UPSTREAM_TIMEOUT, context=context)


def _credential(args):
    """(token, credential label, upstream): the token file, or with --rehearsal a canary made here."""
    if args.rehearsal:
        if args.token_file:
            raise Refused("--rehearsal never opens a token file")
        if not (args.canary_out and args.canary_length and args.canary_length > 0):
            raise Refused("--rehearsal needs --canary-out and a positive --canary-length")
        return make_canary(args.canary_out, args.canary_length), "rehearsal", unix_upstream(args.rehearsal)
    if not args.token_file:
        raise Refused("--token-file or --rehearsal is required")
    return read_token(args.token_file), "live", vendor_upstream()


def _clear_stale(path):
    """Remove a socket left by a passthrough that died; refuse one that still answers."""
    if not os.path.exists(path):
        return
    with socket.socket(socket.AF_UNIX) as probe:
        if not stat.S_ISSOCK(os.lstat(path).st_mode) or probe.connect_ex(path) == 0:
            raise Refused(f"{path} exists and is not a dead passthrough socket")
    os.unlink(path)


def _harden():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    ctypes.CDLL(None, use_errno=True).prctl(4, 0, 0, 0, 0)  # PR_SET_DUMPABLE 0: no core, no ptrace, no /proc/pid/mem
    os.umask(0o077)
    sys.excepthook = lambda kind, value, tb: print(f"lh-passthrough: error {kind.__name__}", file=sys.stderr,
                                                   flush=True)
    threading.excepthook = lambda args: print(f"lh-passthrough: error {args.exc_type.__name__}", flush=True)


def _parse(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for flag in ("--socket", "--state", "--slots"):
        parser.add_argument(flag, required=True)
    parser.add_argument("--paid-usage", action="append", default=[], metavar="HEADER=VALUE")
    parser.add_argument("--token-file")
    parser.add_argument("--rehearsal", metavar="STAND_IN_SOCKET")
    parser.add_argument("--canary-out")
    parser.add_argument("--canary-length", type=int)
    return parser.parse_args(argv)


def _start(args):
    _owned(os.stat(args.state), 0o700, "the state directory")
    paid = [tuple(item.split("=", 1)) for item in args.paid_usage]
    if any(len(pair) != 2 for pair in paid):
        raise Refused("--paid-usage takes HEADER=VALUE")
    token, credential, upstream = _credential(args)
    pt = Passthrough(args.state, args.slots, token, credential, upstream, paid)
    (Path(args.state) / "fingerprint.json").write_text(json.dumps(token_scan.fingerprint(token)))
    _clear_stale(args.socket)
    return pt, serve(args.socket, pt)


def main(argv=None):
    _harden()
    args = _parse(argv)
    try:
        pt, server = _start(args)
    except (Refused, *SLOTS_ERRORS) as exc:
        detail = exc if isinstance(exc, Refused) else f"{type(exc).__name__} {getattr(exc, 'filename', '') or ''}"
        print(f"lh-passthrough: refused: {detail}".rstrip(), file=sys.stderr, flush=True)
        return 2
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    print("listening", args.socket, flush=True)
    try:
        server.serve_forever()
    finally:
        pt.event("close_starts", reason="passthrough down", reset=None)
        server.server_close()
        os.unlink(args.socket)
    return 0


if __name__ == "__main__":
    sys.exit(main())
