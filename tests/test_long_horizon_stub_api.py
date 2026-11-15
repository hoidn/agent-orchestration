"""The long-horizon kit's local stand-in for the model API (`experiments/long_horizon_tasks/stub_api.py`).

The stub runs as its own process on a loopback port; the tests talk to it over HTTP only. No CLI and no
provider is involved.
"""

from __future__ import annotations

import http.client
import importlib.util
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import pytest

REPO = Path(__file__).resolve().parents[1]
STUB = REPO / "experiments" / "long_horizon_tasks" / "stub_api.py"
MODEL = "claude-haiku-5-5"
DUMMY_KEY = "dummy-recording-key-0000"


def _start(tmp_path, scenario, *where):
    log = tmp_path / "requests.jsonl"
    proc = subprocess.Popen(
        [sys.executable, "-I", str(STUB), *where, "--model", MODEL, "--scenario", scenario, "--log", str(log)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    line = proc.stdout.readline().split()
    if line[:1] != ["listening"]:
        proc.kill()
        _, err = proc.communicate(timeout=10)
        raise AssertionError(f"stub did not start (exit {proc.returncode}): {err.strip()[-300:]}")
    return proc, line[-1], log


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
    short = tempfile.mkdtemp(prefix="lhs", dir="/tmp")  # mode 700; AF_UNIX paths stop at 108 bytes
    sock = Path(short) / "pt.sock"
    proc, _, _ = _start(tmp_path, "normal", "--unix", str(sock))
    try:
        status, text, _ = _post(None, _request(), conn=_UnixConnection(str(sock)))
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        shutil.rmtree(short)
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


def test_other_paths_answer_the_configured_status(tmp_path):
    proc, port, log = _start(tmp_path, "normal", "--host", "127.0.0.1", "--port", "0", "--other-status", "401")
    try:
        conn = http.client.HTTPConnection("127.0.0.1", int(port), timeout=10)
        conn.request("GET", "/api/oauth/profile", headers={"authorization": "Bearer fake-token-value"})
        status = conn.getresponse().status
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    row = json.loads(log.read_text().splitlines()[0])
    assert (status, row["headers"]["authorization"]) == (401, "Bearer <redacted>")


def test_a_usage_limit_names_the_rejected_window_and_its_reset(tmp_path):
    proc, port, _ = _start(tmp_path, "usage_limit", "--host", "127.0.0.1", "--port", "0", "--delay", "60")
    try:
        status, _, headers = _post(int(port), _request(turn=1))
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    assert (status, headers["anthropic-ratelimit-unified-status"],
            headers["anthropic-ratelimit-unified-representative-claim"]) == (429, "rejected", "five_hour")


def test_the_system_prompt_is_recorded_by_block_size_and_opening(stub):
    port, log = stub
    _post(port, {**_request(), "system": [{"type": "text", "text": "You are a stand-in. " + "x" * 300}]})
    assert _log(log)[0]["system"] == [{"chars": 320, "opening": "You are a stand-in. " + "x" * 60}]


def test_a_system_block_keeps_its_cache_control(stub):
    port, log = stub
    block = {"type": "text", "text": "cached", "cache_control": {"type": "ephemeral", "ttl": "1h"}}
    _post(port, {**_request(), "system": [block]})
    assert _log(log)[0]["system"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}


def test_an_expired_credential_is_refused_with_401_after_turn_0(tmp_path):
    proc, port, _ = _start(tmp_path, "unauthorized", "--host", "127.0.0.1", "--port", "0")
    try:
        first, _, _ = _post(int(port), _request())
        later, text, _ = _post(int(port), _request(turn=1))
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    assert (first, later, json.loads(text)["error"]["type"]) == (200, 401, "authentication_error")


def test_cache_writes_are_reported_as_one_hour_writes(scenario_stub):
    port = scenario_stub("cache_writes")
    _, text, _ = _post(port, _request())
    usage = _events(text)[0]["message"]["usage"]
    assert (usage["cache_creation_input_tokens"], usage["cache_creation"]) == (
        20000, {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 20000})


def test_a_stub_that_cannot_start_says_so(tmp_path):
    with pytest.raises(AssertionError, match="stub did not start"):
        _start(tmp_path, "no-such-scenario", "--host", "127.0.0.1", "--port", "0")


def test_the_stub_refuses_a_non_loopback_address(tmp_path):
    with pytest.raises(AssertionError, match="loopback"):
        _start(tmp_path, "normal", "--host", "0.0.0.0", "--port", "0")


def test_a_slow_reply_holds_its_first_byte_for_the_delay(tmp_path):
    proc, port, _ = _start(tmp_path, "slow", "--host", "127.0.0.1", "--port", "0", "--delay", "1")
    try:
        started = time.monotonic()
        status, _, _ = _post(int(port), _request(turn=1))
        waited = time.monotonic() - started
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    assert (status, waited >= 1) == (200, True)


_spec = importlib.util.spec_from_file_location("lh_stub_api", STUB)
stub_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(stub_module)


def _reply(scenario, turn=0, tools=("Bash", "Agent"), first="hello"):
    body = {**_request(turn=turn), "tools": [{"name": t, "input_schema": {}} for t in tools]}
    body["messages"][0] = {"role": "user", "content": first}
    return stub_module.reply(scenario, body)


@pytest.mark.parametrize("scenario,stop", [("refusal", "refusal"), ("max_tokens", "max_tokens")])
def test_a_refusal_and_an_output_limit_end_with_their_stop_reason(scenario, stop):
    assert _reply(scenario)[1] == stop


def test_a_refusal_stream_carries_stop_details():
    message = stub_module._message(MODEL, *_reply("refusal"))
    delta = [d for name, d in stub_module.sse_events(message) if name == "message_delta"][0]
    assert delta["delta"]["stop_details"]["type"] == "refusal"


def test_a_context_limit_refuses_the_first_request_as_too_long():
    assert _reply("context")[:2] == (400, "invalid_request_error")


def test_a_late_context_limit_fills_the_window_then_refuses():
    first, later = _reply("context_late"), _reply("context_late", turn=1)
    assert (first[2]["input_tokens"] >= 900000, later[0]) == (True, 400)


def test_a_budget_reply_reports_costly_usage():
    assert _reply("budget")[2]["output_tokens"] >= 100000


def test_a_timeout_reply_runs_a_long_command():
    assert "sleep" in _reply("timeout")[0][0]["input"]["command"]


@pytest.mark.parametrize("scenario,status", [("overloaded", 529), ("server_error", 500)])
def test_overload_and_server_faults_answer_after_the_first_turn(scenario, status):
    assert (_reply(scenario)[1], _reply(scenario, turn=1)[0]) == ("tool_use", status)


def test_a_subagent_reply_launches_the_agent_tool_and_the_subagent_runs_commands():
    main = _reply("subagent")[0][0]
    sub = _reply("subagent", first=main["input"]["prompt"])[0][0]
    assert (main["name"], sub["name"]) == ("Agent", "Bash")


def test_an_override_subagent_asks_for_another_model_and_effort():
    args = _reply("subagent_override")[0][0]["input"]
    assert (args["model"], args["effort"]) == ("fable", "max")


def test_a_web_reply_calls_web_tools_that_were_not_declared():
    assert [_reply("web", turn=t)[0][0]["name"] for t in (0, 1)] == ["WebFetch", "WebSearch"]


def _one_row(tmp_path, body, *args, headers=None):
    proc, port, log = _start(tmp_path, "normal", "--host", "127.0.0.1", "--port", "0", *args)
    try:
        _post(int(port), body, headers)
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    return log, json.loads(log.read_text().splitlines()[0])


def test_tool_definitions_are_recorded_by_size_and_cache_control(tmp_path):
    tool = {"name": "Bash", "input_schema": {"type": "object"}, "cache_control": {"type": "ephemeral", "ttl": "1h"}}
    _, row = _one_row(tmp_path, {**_request(), "tools": [tool]})
    assert (row["tool_chars"], row["tool_cache"]) == (
        [len(json.dumps(tool))], [{"tool": "Bash", "cache_control": {"type": "ephemeral", "ttl": "1h"}}])


def test_message_blocks_are_recorded_by_size_and_cache_control(tmp_path):
    block = {"type": "text", "text": "hello", "cache_control": {"type": "ephemeral"}}
    _, row = _one_row(tmp_path, {**_request(), "messages": [{"role": "user", "content": [block]}]})
    assert row["message_blocks"] == [["user", [{"type": "text", "chars": 5, "cache_control": {"type": "ephemeral"}}]]]


def test_watched_names_are_counted_where_they_occur(tmp_path):
    body = {**_request(), "system": [{"type": "text", "text": "use deep-research"}],
            "messages": [{"role": "user", "content": "Explore, then Explore again"}]}
    _, row = _one_row(tmp_path, body, "--watch", "deep-research,Explore")
    assert row["mentions"] == {"deep-research": {"system": 1, "tools": 0, "messages": 0},
                               "Explore": {"system": 0, "tools": 0, "messages": 2}}


def test_the_bearer_is_compared_but_never_logged(tmp_path):
    log, row = _one_row(tmp_path, _request(), "--expect-bearer", "lh-fake-slot-0123abcd",
                        headers={"authorization": "Bearer lh-fake-slot-0123abcd"})
    assert (row["bearer_matches"], "0123abcd" in log.read_text()) == (True, False)


@pytest.mark.parametrize("scenario", ["pt_model403", "pt_tool403", "pt_path", "pt_token"])
def test_every_passthrough_refusal_has_the_403_form(scenario):
    status, etype, message, headers = _reply(scenario, turn=1)
    assert (status, etype, message.startswith("lh-passthrough: "), headers) == (
        403, "permission_error", True, {"x-should-retry": "false"})


def test_a_placeholder_reply_calls_the_placeholder_tool():
    assert _reply("placeholder")[0][0]["name"] == "DeferredToolPlaceholder"


def test_an_overage_reply_serves_with_the_overage_headers(tmp_path):
    proc, port, _ = _start(tmp_path, "overage", "--host", "127.0.0.1", "--port", "0")
    try:
        status, _, headers = _post(int(port), _request())
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    assert (status, headers["anthropic-ratelimit-unified-status"],
            headers["anthropic-ratelimit-unified-overage-status"]) == (200, "rejected", "allowed")


def test_a_first_request_refusal_refuses_the_session_s_first_request():
    assert _reply("pt_token_first")[:3] == (403, "permission_error", "lh-passthrough: unknown token")
