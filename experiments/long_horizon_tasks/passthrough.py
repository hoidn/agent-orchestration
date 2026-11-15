"""The long-horizon passthrough (plan D4; Task 4, first slice): the one host process that holds the owner's
subscription token, meters every request and enforces the caps.

It listens on one unix socket only; the relay container forwards its one TCP port to it. Everything from the
container is checked against `request_allowlist.json` (built by `make_allowlist.py` from the recorded request
fixtures) and refused otherwise, in one form: HTTP 403 `permission_error`, `x-should-retry: false`, message
`lh-passthrough: <reason>`, connection closed (after reading and dropping, for LINGER seconds at most, what the
client still sends, so that it reads the refusal). In order, before any body byte is read:
  the request line is exactly `POST /v1/messages?beta=true HTTP/1.1` ("path not allowed"; an unparsable line
  "request malformed", an over-long line or header block "request too large"); every header name is recorded
  and appears once ("header not allowed", "header repeated"); the recorded headers have recorded values; the
  values are printable ASCII and there is one `content-length` of plain digits ("request malformed"), at most
  64 MiB, with at most 32 KiB of headers ("request too large"); the line and headers come within HEADER_TIME
  (else the connection is cut); the bearer token maps to a slot ("unknown token"); the tranche is not stopped
  ("tranche stopped"); the slot has at most two requests open and its socket at most 16 connections ("too
  many connections"). A slot with its own socket (below) is known on that socket only ("unknown token").
Then, holding the slot (one request in flight per slot; a second waits for the first to be metered, then
"slot busy" after the wait): the body, read within its time ("request timed out"), is strict JSON (UTF-8, no
duplicate key at any depth, no NaN: "request malformed"); its top-level keys are recorded ("field not
allowed"); `model` is the exact id ("model not allowed"); `stream`, `max_tokens` and the effort hold recorded
values ("field not allowed"); every tool has an `input_schema` and no `type` ("provider-side tool refused"), a
recorded name, and only the keys recorded for that name in its definition and its schema's top level ("tool not
allowed");
nothing in it asks the vendor to fetch (a `source` that is not base64, text or content, or a `file_id`:
"field not allowed"); the slot's and the tranche's request counts and priced caps hold, counted with every
earlier request of the slot metered ("slot cap reached", "tranche total reached").

The upstream request is built: the client's header lines in their order, with exactly three values set by the
passthrough, `authorization` (`Bearer <real token>`), `host` (the vendor's host) and `accept-encoding`
(`identity`, so every response byte can be checked), and `content-length` from the body read; the body byte
for byte. The response goes back unchanged, except that everything sent to the client and every log row is
checked for the token in each form of `token_scan.forms` (plain, hex, base64 at three alignments, UTF-16LE),
across writes (a tail that could start a form is held until the next write shows it is not one). On a match
nothing more is sent, the client connection is dropped and the tranche is stopped with the place (a header's
index and name, or a body offset) and the form, never the bytes; a response whose `content-encoding` is not
identity is handled the same way, since it cannot be checked. The meter reads the response to its end even
when the client has gone; a 200 whose usage cannot be read whole, or a request that got no status back, is
priced at a bound, flagged, and closes starts ("usage incomplete"): as prompt, the body's size in bytes (or the
prompt message_start reported, when larger) at the one-hour cache-write rate, the dearest prompt rate; as output,
the request's `max_tokens`. Prices are `price_rule.json`
(`price_check.price`, each cache write at its lifetime's rate).

The vendor's answers, recorded before the response is passed on: a 429 closes starts ("usage limit" with its
`anthropic-ratelimit-unified-reset` when `anthropic-ratelimit-unified-status` is `rejected`, else "vendor 429"
with no reset); a 401 stops the tranche; with --stop-on-non-200 (the live probe's) any status but 200 stops
it. Paid extra usage (PAID_USAGE: on any response, overage in use or overage allowed; on a response that is not
a 429, a unified status present and other than allowed; and each --paid-usage HEADER=VALUE) stops it, and that
response is not passed on: the client gets the 403 form with "tranche stopped", while the answer is still read
and metered. After the body:
a response naming another model stops it. Starts are the launcher's: `close_starts` is a record.

State, in DIR (mode 700, this user's; the output file belongs there too):
  requests.jsonl  one row per request; a refusal: time, slot, status, reason, and for a cap the limit that acted
                  (cap_usd, cap_requests, total_usd, total_requests); a forwarded request (it has passed the
                  allowlist): also model, effort, declared tools, its anthropic-beta value as sent, its cache marks
                  (`<place>:<ttl>` for each block with a cache_control; "unset" is the API's five minutes), every
                  response header's name, the values of the logged response headers (anthropic-*, retry-after,
                  x-should-retry, request-id, content-encoding, the paid-usage names), usage, price, response
                  model, message id, error class, worst-case flag, whether the answer was passed on. It is the
                  meter: a restart sums it. A row in which a form of the token appears is written with its
                  numbers only (`withheld`: the form), and the tranche stops.
  tranche.jsonl   events: close_starts and stop (written here), stop and resume (written by the launcher or a
                  person); every request is refused while the last stop or resume is a stop.
  fingerprint.json  one salt and each form's length and salted SHA-256 (token_scan.py), and the mode ("live" or
                    "rehearsal"), written at the start.
The slots file, re-read on every request (the launcher replaces it atomically):
  {"total_usd": T (at most 200), "total_requests": N or null,
   "slots": {NAME: {"token": FAKE, "cap_usd": C, "cap_requests": M or null[, "own_socket": true]}}}
  (no fake token twice). A slot with "own_socket" (the launcher's, one per attempt: plan Task 5, connections) is
  served on <the --socket's directory>/NAME/passthrough.sock, opened within SOCKETS_POLL of the file naming it,
  with its own cap of 16 connections, and closed and removed with its directory when the slot is retired; NAME
  is then a plain name (SLOT_NAME), else the slot gets no socket. The --socket itself serves the other slots.
A slot is retired by the launcher alone, by removing it: only a token absent from the file is "unknown token". A
slot at a cap stays and answers "slot cap reached" (cap_requests is the live probe's; the ladder sets none).

The token: --token-file is opened once, at the start, without following a symlink in the file or its
directory, and refused unless the opened file is a regular file of mode 600 in a directory of mode 700, both
this user's, holding one bearer token (RFC 6750 b64token). It is in no argument, environment, log row or
exception text: errors print the exception's class and this module's own message. Core dumps are off and the
process is not dumpable. It starts no child process. The vendor client is `http.client` (it reads no proxy
variable), verifies TLS against the trust store compiled into Python (not one named by the environment) and
connects to api.anthropic.com:443 only. --rehearsal connects to a stand-in's unix socket instead, refuses
--token-file, and holds a canary it makes itself, of a setup-token token's shape (its prefix, 108 characters),
and writes once to --canary-out (a new mode-600 file).

Usage: python -I passthrough.py --socket PATH --state DIR --slots FILE [--paid-usage HEADER=VALUE]...
         [--stop-on-non-200] (--token-file FILE | --rehearsal STAND_IN_SOCKET --canary-out FILE)
Prints `listening <socket>` once bound, and again for each slot's own socket. Exit 2: refused at the start.
SIGTERM: records close_starts ("passthrough down"), removes every socket, exits 0. A crash leaves no such record: the launcher (Task 5) must
treat an unanswered socket as the passthrough being down.
"""

import argparse
import contextlib
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
ALLOW = json.loads((HERE / "request_allowlist.json").read_text())
MESSAGES = ALLOW["path"]
REQUEST_LINE = f"{ALLOW['method']} {MESSAGES} HTTP/1.1"
VENDOR = "api.anthropic.com"
CEILING_USD = 200.0  # the approval's ceiling; no slots file may set a larger total
BEARER = re.compile(r"[A-Za-z0-9\-._~+/]+=*")
DIGITS = re.compile(r"0|[1-9][0-9]{0,9}")
PRINTABLE = re.compile(r"[\x20-\x7e]*")
TAIL = re.compile(rb"[A-Za-z0-9\-._~+/=\x00]*\Z")  # the bytes any form of the token is made of
SOURCES = ("base64", "text", "content")  # a content block's source the vendor reads from the request itself
LOGGED = ("retry-after", "x-should-retry", "request-id", "content-encoding")
READ = 65536
MAX_BODY = 64 << 20  # bytes of request body
MAX_HEADER_BYTES = 32 << 10  # bytes of request header names and values together
MAX_CONNECTIONS = 16  # open connections from a relay, per socket (the main one, and each slot's own)
SLOT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")  # a slot with its own socket: a plain directory name
SOCKETS_POLL = 0.25  # seconds between two readings of the slots file for the slots' own sockets
MAX_PER_SLOT = 2  # requests of one slot open at once: one in flight, one waiting
CLIENT_TIMEOUT = 60  # seconds for any one read from or write to the container's side
HEADER_TIME = 60  # seconds from waiting for a request line to the end of its headers
BODY_TIME = 120  # seconds to read a request body
SLOT_WAIT = 300  # seconds a request waits for its slot's request in flight to be metered
UPSTREAM_TIMEOUT = 900  # seconds without a byte from the vendor; a long output streams for minutes
HANDLER_TIME = 3600  # seconds for one request, from its first header to the end of the vendor's answer
LINGER = 2  # seconds a refused connection reads and discards what the client still sends, so it reads the refusal
SLOTS_ERRORS = (OSError, ValueError, KeyError, TypeError, AttributeError)
NUMBERS = ("time", "event", "slot", "status", "usd", "slot_usd", "total_usd", "worst_case")  # kept in a withheld row
# Paid extra usage: the header names and values are Task 2a's reading of the CLI 2.1.311 bundle (the headers its
# stand-in sent in recording t2a-overage-low, fixture token-paid-extra-usage-normal-end), not a vendor document;
# one combination was recorded. --paid-usage HEADER=VALUE adds to them.
PAID_USAGE = {"status": "anthropic-ratelimit-unified-status", "overage": "anthropic-ratelimit-unified-overage-status",
              "in_use": "anthropic-ratelimit-unified-overage-in-use", "allowed": ("allowed", "allowed_warning")}


class Refused(Exception):
    """A refusal at the start; its message names the reason and never a secret."""


class Refusal(Exception):
    """A request refused in the one 403 form; `reason` is the passthrough's own text, `limit` the cap that acted."""

    def __init__(self, reason, limit=None):
        super().__init__(reason)
        self.reason, self.limit = reason, limit


class TokenSeen(Exception):
    """A form of the token in bytes bound for the client or a log; holds the place, never the bytes."""


def _owned(st, mode, what):
    if st.st_uid != os.getuid():
        raise Refused(f"{what} is not owned by this user")
    if stat.S_IMODE(st.st_mode) != mode:
        raise Refused(f"{what} has mode {stat.S_IMODE(st.st_mode):o}, not {mode:o}")


def read_token(path):
    """The token in `path`, checked on the opened descriptors as D4's token path requires; read here only."""
    path = os.path.abspath(path)
    folder = os.open(os.path.dirname(path), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        _owned(os.fstat(folder), 0o700, "the token file's directory")
        fd = os.open(os.path.basename(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
    finally:
        os.close(folder)
    with open(fd, "rb") as fh:
        st = os.fstat(fh.fileno())
        if not stat.S_ISREG(st.st_mode):
            raise Refused("the token file is not a regular file")
        _owned(st, 0o600, "the token file")
        value = fh.read().decode("ascii", "replace").strip()
    if not BEARER.fullmatch(value):
        raise Refused("the token file does not hold one bearer token")
    return value


CANARY_PREFIX, CANARY_LENGTH = "sk-ant-oat01-", 108  # a `claude setup-token` token's shape (Task 8 m7)


def make_canary(path):
    """A canary of a setup-token token's shape (its prefix, then base64url characters to its length), written once
    to a new mode-600 file (the rehearsal's token)."""
    value = CANARY_PREFIX + "".join(secrets.choice(string.ascii_letters + string.digits + "-_")
                                    for _ in range(CANARY_LENGTH - len(CANARY_PREFIX)))
    with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as fh:
        fh.write(value + "\n")
    return value


def _json(data):
    try:
        return json.loads(data)
    except ValueError:  # an unreadable response body is metered as unreadable, never raised
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


# --- the request: line, headers, body -------------------------------------------------------------------


def _unique(pairs):
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate key")
    return dict(pairs)


def _no_constant(name):
    raise ValueError(f"{name} is not JSON")


def parse_body(body):
    """The request body as strict JSON: UTF-8 without a BOM, no duplicate key at any depth, no NaN."""
    try:
        return json.loads(body.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_no_constant)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise Refusal("request malformed") from None


def header_reason(headers):
    """Why a request's headers are refused, or None."""
    names = [name.lower() for name in headers.keys()]
    if len(names) != len(set(names)):
        return "header repeated"
    if set(names) - set(ALLOW["headers"]):
        return "header not allowed"
    if sum(len(name) + len(value) for name, value in headers.items()) > MAX_HEADER_BYTES:
        return "request too large"
    if not all(PRINTABLE.fullmatch(value) for value in headers.values()):
        return "request malformed"
    length = headers.get("content-length")
    if length is None or not DIGITS.fullmatch(length):
        return "request malformed"
    if int(length) > MAX_BODY:
        return "request too large"
    return _value_reason(headers)


def _value_reason(headers):
    for name, allowed in ALLOW["header_values"].items():
        if headers.get(name) is not None and headers[name] not in allowed:
            return "header not allowed"
    beta, agent = headers.get("anthropic-beta"), headers.get("user-agent")
    if beta is not None and set(beta.split(",")) - set(ALLOW["anthropic_beta"]):
        return "header not allowed"
    if agent is not None and agent.split(" ", 1)[0] not in ALLOW["user_agent"]:
        return "header not allowed"
    return None


def _tool_reason(tool):
    if not isinstance(tool, dict) or "type" in tool or not isinstance(tool.get("input_schema"), dict):
        return "provider-side tool refused"
    name = tool.get("name")
    if not isinstance(name, str) or name not in ALLOW["tool_keys"]:
        return "tool not allowed"
    if set(tool) - set(ALLOW["tool_keys"][name]) or set(tool["input_schema"]) - set(ALLOW["input_schema_keys"][name]):
        return "tool not allowed"
    return None


def _fetches(content):
    """Whether a content block in `content` asks the vendor to fetch: a source other than the request's own
    bytes, or a file. A tool call's `input` is the model's own and is not read."""
    stack = [content]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            source = item.get("source")
            if "file_id" in item or (isinstance(source, dict) and source.get("type") not in SOURCES):
                return True
            stack.extend(value for key, value in item.items() if key != "input")
        elif isinstance(item, list):
            stack.extend(item)
    return False


def _recorded(value, allowed):
    return any(type(value) is type(item) and value == item for item in allowed)  # no 1 for true


def _field_reason(request):
    config = request.get("output_config", {})
    tokens = request.get("max_tokens")
    if not _recorded(request.get("stream"), ALLOW["stream"]):
        return "field not allowed"
    if type(tokens) is not int or not 0 < tokens <= ALLOW["max_tokens_max"]:
        return "field not allowed"
    if not isinstance(config, dict) or not _recorded(config.get("effort"), ALLOW["effort"]):
        return "field not allowed"
    return "field not allowed" if _fetches([request.get("messages"), request.get("system")]) else None


def content_reason(request):
    """Why a parsed request body is refused, or None."""
    if not isinstance(request, dict) or set(request) - set(ALLOW["top_level"]):
        return "field not allowed"
    if request.get("model") != MODEL:
        return "model not allowed"
    tools = request.get("tools", [])
    if not isinstance(tools, list):
        return "tool not allowed"
    return next((reason for reason in map(_tool_reason, tools) if reason), None) or _field_reason(request)


def _leaves(value):
    """Every string in a log row, unescaped, so a form JSON would escape (UTF-16LE's NULs) is still seen."""
    if isinstance(value, dict):
        return b"\n".join(_leaves(key) + b"\n" + _leaves(item) for key, item in value.items())
    if isinstance(value, list):
        return b"\n".join(map(_leaves, value))
    return value.encode("utf-8", "surrogatepass") if isinstance(value, str) else b""


def _list(value):
    return value if isinstance(value, list) else []


def _cache_marks(request):
    """`<place>:<ttl>` for each tool, system block and message block that asks for caching (the API allows four)."""
    blocks = [(f"tools.{i}", tool) for i, tool in enumerate(_list(request.get("tools")))]
    blocks += [(f"system.{i}", block) for i, block in enumerate(_list(request.get("system")))]
    for i, message in enumerate(_list(request.get("messages"))):
        content = _list(message.get("content")) if isinstance(message, dict) else []
        blocks += [(f"messages.{i}.content.{j}", block) for j, block in enumerate(content)]
    return [f"{place}:{str(block['cache_control'].get('ttl', 'unset'))[:16]}" for place, block in blocks
            if isinstance(block, dict) and isinstance(block.get("cache_control"), dict)][:16]


def _row(slot, request, credential, headers):
    """A forwarded request's row, from a request that has passed the allowlist."""
    tools = request.get("tools") or []
    return {"time": time.time(), "slot": slot, "credential": credential, "model": request.get("model"),
            "effort": (request.get("output_config") or {}).get("effort"), "tools": [t["name"] for t in tools],
            "beta": headers.get("anthropic-beta"), "cache_marks": _cache_marks(request)}


PROMPT_TOKENS = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


def _worst_case(start, request, body_size):
    """A bound on what a response whose own usage cannot be read whole could cost (D4): as prompt, the body's size
    in bytes, or the prompt message_start reported when that is larger, all at the one-hour cache-write rate, the
    price rule's dearest prompt rate; as output, the request's `max_tokens`. `price` applies the long-prompt
    multiplier to that prompt. A bound while the vendor counts no more prompt tokens than that."""
    measured = sum(v for k, v in (start or {}).items() if k in PROMPT_TOKENS and type(v) is int)
    output = request.get("max_tokens", ALLOW["max_tokens_max"])
    return {"input_tokens": 0, "cache_creation_input_tokens": max(body_size, measured), "output_tokens": output}


# --- the response: meter and guard ----------------------------------------------------------------------


class Meter:
    """Reads usage, model and message id from a response's bytes as they come, streamed or plain."""

    def __init__(self, headers):
        self.stream = (headers.get("content-type") or "").startswith("text/event-stream")
        self.readable = (headers.get("content-encoding") or "identity").lower() == "identity"
        self.buf, self.message, self.delta, self.complete = b"", None, {}, False

    def feed(self, data):
        if not self.readable:
            return
        self.buf += data
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
            self.delta.update({k: v for k, v in event["usage"].items() if v is not None})  # cumulative counts
        elif kind == "message_stop":
            self.complete = True

    def result(self):
        """(usage, model, message id, whole): usage None when unreadable; whole False for a stream cut short."""
        message = self.message if self.stream else _json(self.buf) if self.readable else None
        if not self.readable or not isinstance(message, dict) or not isinstance(message.get("usage"), dict):
            return None, None, None, False
        whole = self.complete or not self.stream
        return {**message["usage"], **self.delta}, message.get("model"), message.get("id"), whole

    def start_usage(self):
        return (self.message or {}).get("usage") if self.stream and isinstance(self.message, dict) else None


class Guard:
    """The token's forms, searched for in every byte bound for the client or a log."""

    def __init__(self, token):
        self.forms = token_scan.forms(token)
        self.keep = max(len(form) for form in self.forms.values()) - 1

    def find(self, data):
        """(form name, offset) of the first form in `data`, or None."""
        hits = [(data.find(form), name) for name, form in self.forms.items() if form in data]
        return (min(hits)[1], min(hits)[0]) if hits else None

    def held(self, data):
        """How many trailing bytes of `data` could begin a form and must wait for the next write."""
        return min(len(TAIL.search(data[-self.keep:]).group()), self.keep) if data else 0


class Outgoing:
    """The body bound for the client: checked before it is written, with a held tail across writes. Once the
    client has gone (`gone`), the rest is still checked, and nothing is written."""

    def __init__(self, guard, write):
        self.guard, self.write, self.held, self.sent, self.gone = guard, write, b"", 0, False

    def send(self, data, final=False):
        """Write what of `held + data` cannot begin a form; TokenSeen, writing nothing of it, on a match."""
        data = self.held + data
        hit = self.guard.find(data)
        if hit:
            raise TokenSeen(f"body offset {self.sent + hit[1]}", hit[0])
        keep = 0 if final else self.guard.held(data)
        if len(data) > keep and not self.gone:
            try:
                self.write(data[:len(data) - keep])
            except OSError:  # the client went away: the answer is still checked, read and metered to its end
                self.gone = True
        self.sent, self.held = self.sent + len(data) - keep, data[len(data) - keep:]


# --- the passthrough ------------------------------------------------------------------------------------


class Passthrough:
    """One token, one upstream, one meter, the caps, the slots' gates and the tranche's events."""

    def __init__(self, state, slots, token, credential, upstream, paid_usage=(), stop_on_non_200=False):
        self.state, self.slots_file = Path(state), Path(slots)
        self.authorization = f"Bearer {token}"
        self.guard = Guard(token)
        self.credential, self.upstream, self.strict = credential, upstream, stop_on_non_200
        self.paid_usage = [(name.lower(), value) for name, value in paid_usage]
        self.lock, self.write_lock = threading.Lock(), threading.Lock()
        self.spent, self.count, self.open, self.gates = {}, {}, {}, {}
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
        tokens = [slot["token"] for slot in data["slots"].values()]
        if len(tokens) != len(set(tokens)) or not all(isinstance(t, str) for t in tokens):
            raise Refused("every slot needs its own fake token")
        if not all(slot["cap_usd"] > 0 for slot in data["slots"].values()):
            raise Refused("every slot needs a positive cap_usd")
        return data, {slot["token"]: name for name, slot in data["slots"].items()}

    def _slots(self):
        try:
            return self.load_slots()
        except (Refused, *SLOTS_ERRORS) as exc:
            self.event("stop", reason=f"slots file unreadable ({type(exc).__name__})")
            raise Refusal("tranche stopped") from None

    def _append(self, name, row):
        hit = self.guard.find(_leaves(row))
        if hit:  # a vendor value carried the token: the tranche stops, and the row keeps its numbers only
            self.event("stop", reason="token in a log row", form=hit[0])
            row = {**{key: row[key] for key in NUMBERS if key in row}, "withheld": hit[0]}
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

    def slot_for(self, authorization, served=None):
        """The slot of a fake token, from the headers alone. A slot with its own socket is known on that socket
        only (`served` names the slot whose socket the request came on; None for the main socket)."""
        data, tokens = self._slots()
        slot = tokens.get(_bearer(authorization))
        home = slot if slot is not None and data["slots"][slot].get("own_socket") else None
        if slot is None or served != home:
            raise Refusal("unknown token")
        if self.stopped():
            raise Refusal("tranche stopped")
        return slot

    @contextlib.contextmanager
    def holding(self, slot):
        """The slot's gate: one request in flight; one more may wait for it, SLOT_WAIT at most."""
        with self.lock:
            if self.open.get(slot, 0) >= MAX_PER_SLOT:
                raise Refusal("too many connections")
            self.open[slot] = self.open.get(slot, 0) + 1
            gate = self.gates.setdefault(slot, threading.Lock())
        try:
            if not gate.acquire(timeout=SLOT_WAIT):
                raise Refusal("slot busy")
            try:
                yield
            finally:
                gate.release()
        finally:
            with self.lock:
                self.open[slot] -= 1

    def admit(self, slot):
        """Under the slot's gate, every earlier request of the slot metered: the caps, then the count."""
        slots, _ = self._slots()
        if slot not in slots["slots"]:
            raise Refusal("unknown token")
        if self.stopped():
            raise Refusal("tranche stopped")
        with self.lock:
            limit = self._cap_reached(slot, slots)
            if limit:
                raise Refusal("slot cap reached" if limit.startswith("cap_") else "tranche total reached", limit)
            self._add(slot, 0.0, 1)

    def _cap_reached(self, slot, slots):
        """The limit the slot's next request would pass (its own, then the tranche's), or None."""
        cap, total = slots["slots"][slot], slots.get("total_requests")
        if cap.get("cap_requests") is not None and self.count.get(slot, 0) >= cap["cap_requests"]:
            return "cap_requests"
        if self.spent.get(slot, 0.0) >= cap["cap_usd"]:
            return "cap_usd"
        if total is not None and sum(self.count.values()) >= total:
            return "total_requests"
        return "total_usd" if sum(self.spent.values()) >= slots["total_usd"] else None

    def on_headers(self, slot, status, headers):
        """What the vendor's answer closes or stops, recorded before the answer is passed on; True when the
        answer must not be passed on (paid extra usage)."""
        if status == 401:
            self.event("stop", slot=slot, reason="vendor 401")
        elif self.strict and status != 200:
            self.event("stop", slot=slot, reason=f"vendor status {status}")
        if status == 429:
            limit = headers.get(PAID_USAGE["status"]) == "rejected"
            self.event("close_starts", slot=slot, status=status, reason="usage limit" if limit else "vendor 429",
                       reset=headers.get("anthropic-ratelimit-unified-reset") if limit else None)
        signal = self.paid_signal(status, headers)
        if signal:
            self.event("stop", slot=slot, reason="paid extra usage", signal=signal)
        return bool(signal)

    def paid_signal(self, status, headers):
        """The header that shows paid extra usage in an answer, or None."""
        value = {key: (headers.get(name) or "").lower() for key, name in PAID_USAGE.items() if key != "allowed"}
        if status != 429 and value["status"] and value["status"] not in PAID_USAGE["allowed"]:
            return PAID_USAGE["status"]
        if value["in_use"] == "true":
            return PAID_USAGE["in_use"]
        if value["overage"] in PAID_USAGE["allowed"]:
            return PAID_USAGE["overage"]
        return next((name for name, wanted in self.paid_usage if headers.get(name) == wanted), None)

    def settle(self, slot, row, meter, request, body_size):
        usage, model, message_id, whole = meter.result()
        usd = _price(usage) if usage is not None and whole else None
        worst = row.get("status") in (200, None) and usd is None  # no status: the vendor may have taken it
        if worst:
            usage = _worst_case(meter.start_usage(), request, body_size)
            usd = _price(usage)
        with self.lock:
            self._add(slot, usd or 0.0, 0)
            row.update(usd=usd, slot_usd=self.spent[slot], total_usd=sum(self.spent.values()), worst_case=worst)
        if worst:  # the events first: once a request's row is written, so are they
            self.event("close_starts", slot=slot, reason="usage incomplete", reset=None)
        if model not in (None, MODEL):
            self.event("stop", slot=slot, reason=f"response model {model}")
        self.log({**row, "usage": usage, "response_model": model, "message_id": message_id})

    def logged_headers(self, headers):
        names = {name for name, _ in self.paid_usage}
        return {k.lower(): v for k, v in headers.items()
                if k.lower().startswith("anthropic-") or k.lower() in LOGGED or k.lower() in names}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = CLIENT_TIMEOUT

    def log_message(self, *args):  # the request line stays out of the output
        pass

    def handle_one_request(self):  # a request line and headers slower than HEADER_TIME cut the connection
        self.cut = threading.Timer(HEADER_TIME, self._drop)
        self.cut.daemon = True
        self.cut.start()
        try:
            super().handle_one_request()
        finally:
            self.cut.cancel()

    def _drop(self):
        with contextlib.suppress(OSError):
            self.connection.shutdown(socket.SHUT_RDWR)
        self.close_connection = True

    def handle_expect_100(self):  # no interim answer: `expect` is not a recorded header, so it is refused
        return True

    def send_error(self, code, message=None, explain=None):  # http.server's own refusals, in the one form
        reason = {414: "request too large", 431: "request too large", 501: "path not allowed"}.get(
            code, "request malformed")
        self.server.pt.log({"time": time.time(), "slot": None, "status": 403, "refused": reason})
        self._refuse(reason)

    def do_POST(self):
        self.cut.cancel()
        pt, slot, deadline = self.server.pt, None, time.monotonic() + HANDLER_TIME
        try:
            reason = ("path not allowed" if self.requestline != REQUEST_LINE else header_reason(self.headers))
            if reason:
                raise Refusal(reason)
            slot = pt.slot_for(self.headers.get("authorization"), getattr(self.server, "slot", None))
            with pt.holding(slot):
                body, request = self._read_request()
                pt.admit(slot)
                self._forward(pt, slot, body, request, deadline)
        except Refusal as refusal:
            limit = {"limit": refusal.limit} if refusal.limit else {}
            pt.log({"time": time.time(), "slot": slot, "status": 403, "refused": refusal.reason, **limit})
            self._refuse(refusal.reason)

    def _read_request(self):
        length, deadline, parts = int(self.headers["content-length"]), time.monotonic() + BODY_TIME, []
        while length > 0:
            try:
                data = self.rfile.read1(min(length, READ))
            except OSError:  # the client stalled past its read timeout, or went away
                raise Refusal("request timed out") from None
            if not data:
                raise Refusal("request malformed")
            if time.monotonic() > deadline:
                raise Refusal("request timed out")
            parts.append(data)
            length -= len(data)
        body = b"".join(parts)
        request = parse_body(body)
        reason = content_reason(request)
        if reason:
            raise Refusal(reason)
        return body, request

    def _forward(self, pt, slot, body, request, deadline):
        row, conn = _row(slot, request, pt.credential, self.headers), pt.upstream()
        try:
            resp = self._send(conn, pt, body)
        except (OSError, http.client.HTTPException) as exc:  # nothing came back: the client sees a dropped line
            conn.close()
            pt.settle(slot, {**row, "status": None, "error": type(exc).__name__}, Meter({}), request, len(body))
            return self._fault(exc)
        row.update(status=resp.status, headers=pt.logged_headers(resp.headers),
                   header_names=[name.lower() for name in resp.headers.keys()])
        meter, settled = Meter(resp.headers), []

        def settle():  # once: before the last bytes reach the client when the end is known, else at the end
            if not settled:
                settled.append(pt.settle(slot, row, meter, request, len(body)))
        withhold = pt.on_headers(slot, resp.status, resp.headers)
        row["passed_on"] = not withhold
        try:
            self._relay(pt, resp, meter, settle, deadline, withhold)
        except (OSError, http.client.HTTPException) as exc:  # a fault upstream mid-body: metered as it stands
            row["error"] = type(exc).__name__
            self._fault(exc)
        finally:
            conn.close()
            settle()

    def _send(self, conn, pt, body):
        conn.putrequest("POST", MESSAGES, skip_host=True, skip_accept_encoding=True)
        values = {"authorization": pt.authorization, "host": VENDOR, "accept-encoding": "identity",
                  "content-length": str(len(body))}
        for name, value in self.headers.items():
            conn.putheader(name, values.get(name.lower(), value))
        for name in ("host", "accept-encoding"):
            if name not in self.headers:
                conn.putheader(name, values[name])
        conn.endheaders(body)
        return conn.getresponse()

    def _relay(self, pt, resp, meter, settle, deadline, withhold=False):
        """Pass the answer on while it is clean and the client reads (or, withheld, refuse it); meter all of it."""
        out = Outgoing(pt.guard, self._chunk if resp.chunked else self.wfile.write)
        open_line = self._withhold(out) if withhold else self._pass_headers(pt, resp, out)
        while data := resp.read1(READ):
            meter.feed(data)
            if meter.complete or resp.length == 0:  # the message or the body is whole: meter it, then pass it on
                settle()
            open_line = open_line and self._pass(pt, out, data)
            if time.monotonic() > deadline:
                raise TimeoutError("the answer outlasted the handler's time")
        self._finish(pt, resp, out, open_line)

    def _finish(self, pt, resp, out, open_line):
        """The held tail and a chunked body's end, while the line is open; then whether the connection stays."""
        if open_line and self._pass(pt, out, b"", final=True) and resp.chunked and not out.gone:
            with contextlib.suppress(OSError):
                self.wfile.write(b"0\r\n\r\n")
        self.close_connection = (self.close_connection or not open_line or out.gone
                                 or (not resp.chunked and resp.length is None))

    def _withhold(self, out):
        """The answer is not passed on: the client gets the refusal, and the rest is only checked and metered."""
        self._refuse("tranche stopped")
        out.gone = True
        return True

    def _pass_headers(self, pt, resp, out):
        """The status line and headers, checked whole before any of it is written; False if they were not sent."""
        encoding = (resp.getheader("content-encoding") or "identity").lower()
        lines = [f"{self.protocol_version} {resp.status} {resp.reason}", *(f"{k}: {v}" for k, v in resp.getheaders())]
        hit = pt.guard.find("\r\n".join(lines).encode("latin-1", "replace"))
        if hit or encoding != "identity":
            place = self._header_place(pt, resp) if hit else f"content-encoding {encoding[:32]}"
            pt.event("stop", reason="token in a response" if hit else "response not checkable", place=place,
                     form=hit[0] if hit else None)
            self._drop()
            return False
        try:
            self.send_response_only(resp.status, resp.reason)
            for name, value in resp.getheaders():
                self.send_header(name, value)
            self.end_headers()
        except OSError:  # the client went away: the answer is still checked, read and metered to its end
            out.gone = True
        return True

    @staticmethod
    def _header_place(pt, resp):
        for index, (name, value) in enumerate(resp.getheaders()):
            if pt.guard.find(f"{name}: {value}".encode("latin-1", "replace")):
                return f"header {index} {name[:64] if not pt.guard.find(name.encode('latin-1', 'replace')) else ''}"
        return "status line"

    def _pass(self, pt, out, data, final=False):
        """Send `data` through the guard; False once the token was seen (the client is then dropped)."""
        try:
            out.send(data, final)
            return True
        except TokenSeen as seen:
            pt.event("stop", reason="token in a response", place=seen.args[0], form=seen.args[1])
            self._drop()
            return False

    def _chunk(self, data):
        self.wfile.write(b"%x\r\n%s\r\n" % (len(data), data))

    def _fault(self, exc):
        print(f"lh-passthrough: upstream error {type(exc).__name__}", flush=True)
        self.close_connection = True

    def _refuse(self, reason):
        """The refusal, then a lingering close: a refusal decided from the headers comes before the client has
        sent its body, and closing at once could reset the connection before the client reads the refusal."""
        try:
            self.wfile.write(_refusal(reason))
            self.connection.shutdown(socket.SHUT_WR)
            self.connection.settimeout(0.2)
            deadline = time.monotonic() + LINGER
            while time.monotonic() < deadline and self._discard():
                pass
        except OSError:  # the client is gone; the refusal is in the log
            pass
        self.close_connection = True

    def _discard(self):
        """Read and drop what the client sends; False once it has closed."""
        try:
            return bool(self.connection.recv(READ))
        except TimeoutError:
            return True


def _refusal(reason):
    """The one refusal form, as the bytes of a whole response."""
    data = json.dumps({"type": "error", "error": {"type": "permission_error",
                                                  "message": f"lh-passthrough: {reason}"}}).encode()
    return (f"HTTP/1.1 403 Forbidden\r\ncontent-type: application/json\r\nx-should-retry: false\r\n"
            f"content-length: {len(data)}\r\nconnection: close\r\n\r\n").encode() + data


class _Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    request_queue_size = 64  # a burst is accepted and refused in the one form, not failed at connect

    def __init__(self, path, handler):
        super().__init__(path, handler)
        self.connections = threading.BoundedSemaphore(MAX_CONNECTIONS)

    def process_request(self, request, client_address):
        if not self.connections.acquire(blocking=False):  # over the cap: refused without a thread
            self.pt.log({"time": time.time(), "slot": None, "status": 403, "refused": "too many connections"})
            with contextlib.suppress(OSError):
                request.settimeout(1)
                request.sendall(_refusal("too many connections"))
            self.shutdown_request(request)
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.connections.release()

    def handle_error(self, request, client_address):  # the class only: an exception's text may quote a header
        print(f"lh-passthrough: error {sys.exc_info()[0].__name__}", flush=True)


def serve(socket_path, pt):
    server = _Server(socket_path, Handler)
    server.pt = pt
    return server


class Sockets:
    """The slots' own sockets (plan Task 5, connections). A slot whose entry has `"own_socket": true` is served on
    `<the main socket's directory>/<slot>/passthrough.sock` (a directory of mode 700 made here, which the slot's
    relay mounts), with a cap of MAX_CONNECTIONS of its own: a connection is counted against its own attempt
    before any byte of it is read. Its token is "unknown token" on any other socket, and so is any other token
    on it. `sync` opens and closes them as the slots file names them; a retired slot's socket and directory go."""

    def __init__(self, pt, main_socket):
        self.pt, self.base, self.open, self.lock = pt, Path(main_socket).parent, {}, threading.Lock()

    def path(self, name):
        return self.base / name / "passthrough.sock"

    def sync(self):
        try:
            data, _ = self.pt.load_slots()
        except (Refused, *SLOTS_ERRORS):  # a request then stops the tranche on it (Passthrough._slots)
            return
        wanted = {name for name, slot in data["slots"].items() if slot.get("own_socket") and SLOT_NAME.fullmatch(name)}
        with self.lock:
            for name in sorted(wanted - set(self.open)):
                self._open(name)
            for name in sorted(set(self.open) - wanted):
                self._close(name)

    def _open(self, name):
        path = self.path(name)
        path.parent.mkdir(mode=0o700, exist_ok=True)
        try:
            _clear_stale(str(path))
        except Refused as refused:
            print(f"lh-passthrough: refused: {refused}", flush=True)
            return
        server = serve(str(path), self.pt)
        server.slot = name
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.open[name] = server
        print("listening", path, flush=True)

    def _close(self, name):
        server = self.open.pop(name)
        server.shutdown()
        server.server_close()
        with contextlib.suppress(OSError):
            os.unlink(self.path(name))
            os.rmdir(self.path(name).parent)

    def close_all(self):
        with self.lock:
            for name in sorted(self.open):
                self._close(name)

    def run(self, done):
        while not done.wait(SOCKETS_POLL):
            self.sync()


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


def vendor_context():
    """TLS that verifies the vendor against the trust store compiled into Python, whatever the environment names."""
    paths = ssl.get_default_verify_paths()
    cafile = paths.openssl_cafile if os.path.isfile(paths.openssl_cafile) else None
    capath = paths.openssl_capath if os.path.isdir(paths.openssl_capath) else None
    if not (cafile or capath):
        raise Refused("no trust store at Python's compiled-in paths")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)  # certificate and host name required
    context.load_verify_locations(cafile=cafile, capath=capath)
    return context


def vendor_upstream():
    context = vendor_context()
    return lambda: http.client.HTTPSConnection(VENDOR, 443, timeout=UPSTREAM_TIMEOUT, context=context)


def _credential(args):
    """(token, credential label, upstream): the token file, or with --rehearsal a canary made here."""
    if args.rehearsal:
        if args.token_file:
            raise Refused("--rehearsal never opens a token file")
        if not args.canary_out:
            raise Refused("--rehearsal needs --canary-out")
        return make_canary(args.canary_out), "rehearsal", unix_upstream(args.rehearsal)
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
    parser.add_argument("--stop-on-non-200", action="store_true")
    parser.add_argument("--token-file")
    parser.add_argument("--rehearsal", metavar="STAND_IN_SOCKET")
    parser.add_argument("--canary-out")
    return parser.parse_args(argv)


def _start(args):
    _owned(os.stat(args.state), 0o700, "the state directory")
    paid = [tuple(item.split("=", 1)) for item in args.paid_usage]
    if any(len(pair) != 2 for pair in paid):
        raise Refused("--paid-usage takes HEADER=VALUE")
    token, credential, upstream = _credential(args)
    pt = Passthrough(args.state, args.slots, token, credential, upstream, paid, args.stop_on_non_200)
    fingerprint = {**token_scan.fingerprint(token), "mode": credential}  # the launcher reads the mode (Task 8 M3)
    (Path(args.state) / "fingerprint.json").write_text(json.dumps(fingerprint))
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
    own, done = Sockets(pt, args.socket), threading.Event()
    syncing = threading.Thread(target=own.run, args=(done,), daemon=True)
    syncing.start()
    try:
        server.serve_forever()
    finally:
        pt.event("close_starts", reason="passthrough down", reset=None)
        done.set()
        syncing.join()
        own.close_all()
        server.server_close()
        os.unlink(args.socket)
    return 0


if __name__ == "__main__":
    sys.exit(main())
