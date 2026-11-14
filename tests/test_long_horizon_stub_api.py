"""The long-horizon kit's local stand-in for the model API (`experiments/long_horizon_tasks/stub_api.py`).

The stub runs as its own process on a loopback port; the tests talk to it over HTTP only. No CLI and no
provider is involved.
"""

from __future__ import annotations

import http.client
import json
from pathlib import Path
import socket
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[1]
STUB = REPO / "experiments" / "long_horizon_tasks" / "stub_api.py"
MODEL = "claude-haiku-5-5"
DUMMY_KEY = "dummy-recording-key-0000"


def _start(tmp_path, scenario, *where):
    log = tmp_path / "requests.jsonl"
    proc = subprocess.Popen(
        [sys.executable, "-I", str(STUB), *where, "--model", MODEL, "--scenario", scenario, "--log", str(log)],
        stdout=subprocess.PIPE, text=True)
    return proc, proc.stdout.readline().split()[-1], log


@pytest.fixture
def stub(tmp_path):
    proc, port, log = _start(tmp_path, "normal", "--host", "127.0.0.1", "--port", "0")
    yield int(port), log
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture
def scenario_stub(tmp_path):
    procs = []

    def start(scenario):
        proc, port, _ = _start(tmp_path, scenario, "--host", "127.0.0.1", "--port", "0")
        procs.append(proc)
        return int(port)
    yield start
    for proc in procs:
        proc.terminate()
        proc.wait(timeout=10)


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("relay", timeout=10)
        self.unix_path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.unix_path)


def _post(port, body, headers=None, conn=None):
    conn = conn or http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("POST", "/v1/messages?beta=true", json.dumps(body),
                  {"content-type": "application/json", "x-api-key": DUMMY_KEY,
                   "anthropic-beta": "probe-beta-2026", **(headers or {})})
    resp = conn.getresponse()
    return resp.status, resp.read().decode(), resp.headers


def _request(model=MODEL, stream=True, turn=0):
    later = [{"role": "assistant", "content": "a"}, {"role": "user", "content": "b"}] * turn
    return {"model": model, "stream": stream, "max_tokens": 1000,
            "tools": [{"name": "Bash", "input_schema": {"type": "object"}}],
            "messages": [{"role": "user", "content": "hello"}, *later]}


def _events(text):
    return [json.loads(line[len("data: "):]) for line in text.splitlines() if line.startswith("data: ")]


def _log(log):
    return [json.loads(line) for line in log.read_text().splitlines()]


def test_streaming_request_gets_a_complete_message_stream(stub):
    port, _ = stub
    status, text, _ = _post(port, _request())
    assert (status, [e["type"] for e in _events(text)][::len(_events(text)) - 1]) == (
        200, ["message_start", "message_stop"])


def test_usage_served_is_counted_across_requests(stub):
    port, log = stub
    _post(port, _request())
    _post(port, _request())
    rows = _log(log)
    assert rows[-1]["total_usage"]["output_tokens"] == sum(r["usage"]["output_tokens"] for r in rows)


def test_a_model_other_than_the_configured_one_is_refused(stub):
    port, _ = stub
    status, text, _ = _post(port, _request(model="claude-sonnet-5-5"))
    assert (status, json.loads(text)["error"]["type"]) == (404, "not_found_error")


def test_the_request_is_recorded_with_the_key_redacted(stub):
    port, log = stub
    _post(port, _request())
    row = _log(log)[0]
    assert (row["path"], row["model"], row["tools"], row["headers"]["anthropic-beta"],
            DUMMY_KEY in log.read_text()) == ("/v1/messages?beta=true", MODEL, ["Bash"], "probe-beta-2026", False)


def test_the_stub_answers_on_a_unix_socket(tmp_path):
    sock = tmp_path / "pt.sock"
    proc, _, _ = _start(tmp_path, "normal", "--unix", str(sock))
    try:
        status, text, _ = _post(None, _request(), conn=_UnixConnection(str(sock)))
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    assert (status, _events(text)[-1]["type"]) == (200, "message_stop")


def test_a_rate_limit_fault_answers_after_the_first_turn_with_retry_after(scenario_stub):
    port = scenario_stub("rate_limit_retry_after")
    first, later = _post(port, _request()), _post(port, _request(turn=1))
    assert (first[0], later[0], json.loads(later[1])["error"]["type"], later[2]["retry-after"]) == (
        200, 429, "rate_limit_error", "5")


def test_a_passthrough_refusal_says_not_to_retry(scenario_stub):
    port = scenario_stub("pt_cap")
    status, text, headers = _post(port, _request(turn=1))
    assert (status, json.loads(text)["error"]["type"], headers["x-should-retry"]) == (
        403, "permission_error", "false")


def test_a_transient_fault_clears_after_three_failed_attempts(scenario_stub):
    port = scenario_stub("transient")
    statuses = [_post(port, _request(turn=1))[0] for _ in range(4)]
    assert statuses == [429, 529, 500, 200]


def test_a_dropped_stream_ends_without_message_stop(scenario_stub):
    port = scenario_stub("drop")
    try:
        _, text, _ = _post(port, _request(turn=1))
    except http.client.IncompleteRead as exc:
        text = exc.partial.decode()
    assert [e["type"] for e in _events(text)][-1] != "message_stop"
