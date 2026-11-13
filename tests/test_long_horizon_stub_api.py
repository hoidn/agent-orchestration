"""The long-horizon kit's local stand-in for the model API (`experiments/long_horizon_tasks/stub_api.py`).

The stub runs as its own process on a loopback port; the tests talk to it over HTTP only. No CLI and no
provider is involved.
"""

from __future__ import annotations

import http.client
import json
from pathlib import Path
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[1]
STUB = REPO / "experiments" / "long_horizon_tasks" / "stub_api.py"
MODEL = "claude-haiku-5-5"
DUMMY_KEY = "dummy-recording-key-0000"


@pytest.fixture
def stub(tmp_path):
    log = tmp_path / "requests.jsonl"
    proc = subprocess.Popen(
        [sys.executable, "-I", str(STUB), "--host", "127.0.0.1", "--port", "0", "--model", MODEL,
         "--scenario", "normal", "--log", str(log)],
        stdout=subprocess.PIPE, text=True)
    port = int(proc.stdout.readline().split()[-1])
    yield port, log
    proc.terminate()
    proc.wait(timeout=10)


def _post(port, body, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("POST", "/v1/messages?beta=true", json.dumps(body),
                  {"content-type": "application/json", "x-api-key": DUMMY_KEY,
                   "anthropic-beta": "probe-beta-2026", **(headers or {})})
    resp = conn.getresponse()
    return resp.status, resp.read().decode()


def _request(model=MODEL, stream=True):
    return {"model": model, "stream": stream, "max_tokens": 1000,
            "tools": [{"name": "Bash", "input_schema": {"type": "object"}}],
            "messages": [{"role": "user", "content": "hello"}]}


def _events(text):
    return [json.loads(line[len("data: "):]) for line in text.splitlines() if line.startswith("data: ")]


def _log(log):
    return [json.loads(line) for line in log.read_text().splitlines()]


def test_streaming_request_gets_a_complete_message_stream(stub):
    port, _ = stub
    status, text = _post(port, _request())
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
    status, text = _post(port, _request(model="claude-sonnet-5-5"))
    assert (status, json.loads(text)["error"]["type"]) == (404, "not_found_error")


def test_the_request_is_recorded_with_the_key_redacted(stub):
    port, log = stub
    _post(port, _request())
    row = _log(log)[0]
    assert (row["path"], row["model"], row["tools"], row["headers"]["anthropic-beta"],
            DUMMY_KEY in log.read_text()) == ("/v1/messages?beta=true", MODEL, ["Bash"], "probe-beta-2026", False)
