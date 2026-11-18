"""The long-horizon kit's fixture cutter: what a committed fixture keeps and what it never holds."""

import importlib.util
import json
from pathlib import Path

KIT = Path(__file__).resolve().parents[1] / "experiments" / "long_horizon_tasks"
_spec = importlib.util.spec_from_file_location("lh_cut_fixture", KIT / "cut_fixture.py")
cut = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cut)

SYSTEM_TEXT = "You are a stand-in system prompt that must never reach a fixture."


def _row(**over):
    row = {"path": "/v1/messages?beta=true", "model": "m", "tools": ["Bash"], "server_tools": [],
           "headers": {"x-api-key": "<redacted>", "authorization": "Bearer <redacted>",
                       "anthropic-beta": "b1,b2", "user-agent": "claude-cli/9.9 (external, sdk-cli)",
                       "content-type": "application/json", "x-claude-code-session-id": "s-1"},
           "params": {"model": "m", "metadata": {"user_id": "{\"device_id\":\"d\"}"}, "max_tokens": 10,
                      "stream": True, "output_config": {"effort": "low"}, "thinking": {"type": "adaptive"}},
           "n_messages": 3, "turn": 1, "subagent": False, "status": 200, "mode": None, "time": 100.0,
           "system": [{"chars": len(SYSTEM_TEXT), "opening": SYSTEM_TEXT,
                       "cache_control": {"type": "ephemeral", "ttl": "1h"}}]}
    row.update(over)
    return row


def _log(tmp_path, rows):
    path = tmp_path / "stub.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def test_a_request_cut_holds_no_prompt_text_metadata_or_credential(tmp_path):
    text = json.dumps(cut.requests(_log(tmp_path, [_row()]), "src"))
    assert [s in text for s in (SYSTEM_TEXT[:20], "device_id", "s-1", "user_id")] == [False] * 4


def test_a_request_cut_keeps_the_fields_a_rule_may_match(tmp_path):
    shape = cut.requests(_log(tmp_path, [_row()]), "src")["shapes"][0]
    assert (shape["headers"]["anthropic-beta"], shape["headers"]["user-agent"], shape["headers"]["x-api-key"],
            shape["headers"]["authorization"], shape["headers"]["x-claude-code-session-id"], shape["effort"],
            shape["system"]) == ("b1,b2", "claude-cli/9.9", "<dummy>", "Bearer <dummy>", None, "low",
                                 [{"chars": len(SYSTEM_TEXT), "cache_control": {"type": "ephemeral", "ttl": "1h"}}])


def test_requests_of_one_shape_share_it_and_keep_their_own_row(tmp_path):
    rows = [_row(), _row(n_messages=5, time=102.5, status=429)]
    got = cut.requests(_log(tmp_path, rows), "src")
    assert (len(got["shapes"]), got["requests"]) == (1, [[0, 200, 3, 0.0, None, []], [0, 429, 5, 2.5, None, []]])


def _trial(tmp_path, events):
    (tmp_path / "agent").mkdir()
    (tmp_path / "agent" / "claude-code.txt").write_text("".join(json.dumps(e) + "\n" for e in events))
    (tmp_path / "result.json").write_text(json.dumps({"verifier_result": {"rewards": {"reward": 0.0}}}))
    return tmp_path


def test_a_fixture_counts_the_retries_and_keeps_the_verifier_result(tmp_path):
    retry = {"type": "system", "subtype": "api_retry", "attempt": 1}
    got = cut.fixture(_trial(tmp_path, [{"type": "system", "subtype": "init"}, retry, retry]), "src")
    assert (got["n_api_retry"], got["verifier_result"]) == (2, {"rewards": {"reward": 0.0}})


def test_a_request_cut_keeps_sizes_cache_marks_mentions_and_the_bearer_check(tmp_path):
    first = _row(tool_chars=[120], tool_cache=[{"tool": "Bash", "cache_control": {"type": "ephemeral"}}],
                 message_blocks=[["user", [{"type": "text", "chars": 40, "cache_control": {"type": "ephemeral",
                                                                                         "ttl": "1h"}}]]],
                 mentions={"Explore": {"system": 1, "tools": 0, "messages": 0}}, bearer_matches=True)
    got = cut.requests(_log(tmp_path, [first]), "src")
    assert (got["shapes"][0]["tool_chars"], got["shapes"][0]["tool_cache"], got["requests"][0][5],
            got["first_request"], got["bearer_matches"]) == (
        [120], [{"tool": "Bash", "cache_control": {"type": "ephemeral"}}],
        [[0, 0, {"type": "ephemeral", "ttl": "1h"}]],
        {"message_blocks": [["user", [{"type": "text", "chars": 40,
                                       "cache_control": {"type": "ephemeral", "ttl": "1h"}}]]],
         "mentions": {"Explore": {"system": 1, "tools": 0, "messages": 0}}}, [True])


BASH = {"name": "Bash", "description": "a description never cut", "input_schema": {
    "$schema": "s", "type": "object", "properties": {"command": {"description": "a schema body never cut"}}}}
PLACEHOLDER = {"name": "P", "description": "d", "input_schema": {"type": "object"}, "defer_loading": True}
TOOL_USE = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "a tool input never cut"}}


def _session(tmp_path, entries):
    """The CLI's session file inside a recording, where the harness exports it."""
    path = tmp_path / "jobs" / "j" / "t" / "agent" / "sessions" / "projects" / "-app" / "s.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))


def _tool_row(tools):
    return _row(tools=[t["name"] for t in tools], tool_chars=[len(json.dumps(t)) for t in tools])


def test_a_request_cut_records_each_tool_s_keys_and_its_schema_s_keys_from_the_session_s_request_shape(tmp_path):
    _session(tmp_path, [{"type": "api-request-shape", "shape": {"system": [], "tools": [BASH, PLACEHOLDER]}}])
    shape = cut.requests(_log(tmp_path, [_tool_row([BASH, PLACEHOLDER])]), "src")["shapes"][0]
    assert (shape["tool_keys"], shape["input_schema_keys"]) == (
        [["description", "input_schema", "name"], ["defer_loading", "description", "input_schema", "name"]],
        [["$schema", "properties", "type"], ["type"]])


def test_a_request_cut_keeps_no_tool_description_or_schema_body(tmp_path):
    _session(tmp_path, [{"type": "api-request-shape", "shape": {"system": [], "tools": [BASH]}}])
    text = json.dumps(cut.requests(_log(tmp_path, [_tool_row([BASH])]), "src"))
    assert ("never cut" in text, "command" in text) == (False, False)


def test_a_tool_whose_sent_definition_the_session_did_not_record_has_no_keys(tmp_path):
    _session(tmp_path, [{"type": "api-request-shape", "shape": {"system": [], "tools": [BASH]}}])
    row = _row(tools=["Bash"], tool_chars=[len(json.dumps(BASH)) + 1])
    shape = cut.requests(_log(tmp_path, [row]), "src")["shapes"][0]
    assert (shape["tool_keys"], shape["input_schema_keys"]) == ([None], [None])


def test_a_request_cut_records_the_top_level_body_keys(tmp_path):
    shape = cut.requests(_log(tmp_path, [_row()]), "src")["shapes"][0]
    assert shape["body_keys"] == ["max_tokens", "messages", "metadata", "model", "output_config", "stream", "system",
                                  "thinking", "tools"]


def test_a_request_cut_records_message_block_keys_from_the_session_s_transcript_blocks(tmp_path):
    _session(tmp_path, [{"type": "assistant", "message": {"role": "assistant", "content": [TOOL_USE]}}])
    mark = {"type": "ephemeral"}
    sent = len(json.dumps({**TOOL_USE, "cache_control": mark}))
    row = _row(message_blocks=[["user", [{"type": "text", "chars": 5}]],
                               ["assistant", [{"type": "tool_use", "chars": len(json.dumps(TOOL_USE))}]],
                               ["assistant", [{"type": "tool_use", "chars": sent, "cache_control": mark}]],
                               ["assistant", [{"type": "tool_use", "chars": 7}]]])
    got = cut.requests(_log(tmp_path, [row]), "src")
    assert (got["message_block_keys"], got["message_block_keys_unrecorded"], "never cut" in json.dumps(got)) == (
        {"tool_use": [["cache_control", "id", "input", "name", "type"], ["id", "input", "name", "type"]]},
        {"text": 1, "tool_use": 1}, False)


STRACE = """\
700 12:00:00.100000 openat(AT_FDCWD, "/logs/agent/sessions/.credentials.json", O_RDONLY|O_CLOEXEC) = -1 ENOENT (No such file or directory)
700 12:00:00.200000 openat(AT_FDCWD, "/logs/agent/sessions/.claude.json", O_RDONLY|O_CLOEXEC) = 23
701 12:00:00.300000 execve("/usr/bin/bash", ["bash", "-c", "echo SECRET-ARGUMENT"], 0x7ffd /* 30 vars */) = 0
700 12:00:00.400000 statx(AT_FDCWD, "/root/.claude", AT_STATX_SYNC_AS_STAT, STATX_ALL <unfinished ...>
"""


def test_a_trace_cut_keeps_paths_results_and_programs_but_no_arguments(tmp_path):
    (tmp_path / "strace.700").write_text(STRACE)
    got = cut.trace(tmp_path, "src")
    assert (got["paths"]["/logs/agent/sessions/.credentials.json"], got["paths"]["/logs/agent/sessions/.claude.json"],
            got["paths"]["/root/.claude"], got["execs"], "SECRET" in json.dumps(got)) == (
        {"openat": ["ENOENT"]}, {"openat": ["ok"]}, {"statx": ["unfinished"]}, ["/usr/bin/bash"], False)


DENY = "Task,Monitor,Write"
T2A_CONFIG = {"agent_timeout_multiplier": 0.005, "agent_setup_timeout_multiplier": 3.0,
              "agent": {"name": "claude-code", "model_name": "anthropic/m", "base_url": "http://relay:8080",
                        "kwargs": {"version": "2.1.311", "disallowed_tools": DENY, "max_budget_usd": 0.05,
                                   "reasoning_effort": "medium"},
                        "env": {"CLAUDE_CODE_MAX_OUTPUT_TOKENS": "128000"}},
              "verifier": {"disable": True}}


def test_harbor_arguments_are_read_back_from_a_trial_configuration():
    assert cut.harbor_args(T2A_CONFIG) == (
        "--agent claude-code --agent-setup-timeout-multiplier 3 --ak version=2.1.311 "
        f"--ak disallowed_tools={DENY} --ak max_budget_usd=0.05 --ae CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000 "
        "--disable-verification --agent-timeout-multiplier 0.005 --effort medium")


def test_an_oracle_trial_s_arguments_name_the_oracle_agent():
    assert cut.harbor_args({"agent": {"name": "oracle"}, "verifier": {"disable": True}}) == (
        "--agent oracle --disable-verification")


def test_a_trial_without_a_stream_keeps_the_harness_s_runtime_error_message(tmp_path):
    (tmp_path / "result.json").write_text(json.dumps({"exception_info": {
        "exception_type": "RuntimeError", "exception_message": "CLAUDE_FORCE_OAUTH is set but no token"}}))
    assert cut.fixture(tmp_path, "src")["exception_message"] == "CLAUDE_FORCE_OAUTH is set but no token"


def test_a_trial_with_a_stream_keeps_no_exception_message(tmp_path):
    got = cut.fixture(_trial(tmp_path, [{"type": "system", "subtype": "init"}]), "src")
    assert "exception_message" not in got


HOST_TRACE = """\
900 12:00:00.000001 execve("/usr/bin/podman", ["podman", "exec"], 0x7ffd /* 9 vars */) = 0
900 12:00:00.000100 openat(AT_FDCWD, "/home/someone/.config/containers/containers.conf", O_RDONLY) = 3
900 12:00:00.000200 clone(child_stack=NULL, flags=CLONE_CHILD_CLEARTID|SIGCHLD) = 901
901 12:00:00.000250 execve("/usr/local/bin/claude", ["claude"], 0x7ffd /* 30 vars */) = -1 ENOENT (No such file or directory)
901 12:00:00.000300 execve("/root/.local/bin/claude", ["claude", "-p", "SECRET-ARGUMENT"], 0x7ffd /* 30 vars */ <unfinished ...>
901 12:00:00.000350 <... execve resumed>) = 0
901 12:00:00.000400 openat(AT_FDCWD, "/logs/agent/sessions/.credentials.json", O_RDONLY|O_CLOEXEC) = 23
901 12:00:00.000500 clone3({flags=CLONE_VM, exit_signal=SIGCHLD}, 88 <unfinished ...>
902 12:00:00.000550 execve("/usr/bin/curl", ["curl", "x"], 0x7ffd /* 30 vars */) = 0
901 12:00:00.000600 <... clone3 resumed>) = 7 /* 902 in strace's PID NS */
900 12:00:00.000800 openat(AT_FDCWD, "/run/libpod/tmp/x", O_RDONLY) = 4
"""


def test_a_trace_from_the_cli_s_start_keeps_only_the_cli_and_its_children(tmp_path):
    (tmp_path / "strace.cli").write_text(HOST_TRACE)
    got = cut.trace(tmp_path, "src")
    assert (sorted(got["paths"]), got["execs"], got["cli_started_in_trace"]) == (
        ["/logs/agent/sessions/.credentials.json"], ["/root/.local/bin/claude", "/usr/bin/curl"], True)


CANARY = "lh-canary-0123456789abcdef0123456789abcdef"


def test_a_decoy_trace_counts_where_the_canary_went(tmp_path):
    (tmp_path / "strace.cli").write_text(HOST_TRACE)
    (tmp_path / "canary.txt").write_text(CANARY + "\n")
    (tmp_path / "stub.jsonl").write_text("".join(json.dumps(r) + "\n" for r in (
        {"bearer_matches": True, "mentions": {CANARY: {"system": 0, "tools": 0, "messages": 0}}},
        {"bearer_matches": True, "mentions": {CANARY: {"system": 0, "tools": 0, "messages": 1}}})))
    exported = tmp_path / "jobs" / "j" / "t" / "agent" / "sessions"
    exported.mkdir(parents=True)
    (exported / ".credentials.json").write_text(json.dumps({"claudeAiOauth": {"accessToken": CANARY}}))
    (tmp_path / "harbor.out").write_text("nothing here\n")
    assert cut.trace(tmp_path, "src")["decoy"] == {
        "canary": CANARY, "requests": 2, "requests_with_the_slot_token": 2, "requests_watched_for_the_canary": 2,
        "requests_naming_the_canary": 1,
        "files_holding_the_canary": ["jobs/j/t/agent/sessions/.credentials.json"]}


def test_a_decoy_recording_s_request_cut_counts_the_canary_without_its_value(tmp_path):
    (tmp_path / "canary.txt").write_text(CANARY + "\n")
    row = _row(message_blocks=[], mentions={CANARY: {"system": 0, "tools": 0, "messages": 0}})
    got = cut.requests(_log(tmp_path, [row]), "src")
    assert (CANARY in json.dumps(got), got["first_request"]["mentions"]) == (
        False, {"<canary>": {"system": 0, "tools": 0, "messages": 0}})


def test_a_written_fixture_holds_no_home_path_and_no_address(tmp_path):
    cut._write({"m": "allow 192.0.2.7 pypi.org from /home/someone/x"}, tmp_path / "out.json")
    assert json.loads((tmp_path / "out.json").read_text())["m"] == "allow <address> pypi.org from <home>/x"


def test_a_written_fixture_holds_no_fake_slot_token(tmp_path):
    cut._write({"m": "CLAUDE_CODE_OAUTH_TOKEN=lh-fake-slot-0123456789abcdef0123456789abcdef"}, tmp_path / "o.json")
    assert json.loads((tmp_path / "o.json").read_text())["m"] == "CLAUDE_CODE_OAUTH_TOKEN=<fake slot token>"


def test_a_container_s_own_home_path_is_kept_in_a_written_fixture(tmp_path):
    cut._write({"m": "/home/claude/.claude/remote/.api_key"}, tmp_path / "out.json")
    assert json.loads((tmp_path / "out.json").read_text())["m"] == "/home/claude/.claude/remote/.api_key"


def test_a_trace_cut_reads_no_strace_error_file(tmp_path):
    (tmp_path / "strace.700").write_text(STRACE)
    (tmp_path / "strace.err").write_text('1 12:00:00.1 openat(AT_FDCWD, "/from/the/error/file", O_RDONLY) = 3\n')
    assert "/from/the/error/file" not in cut.trace(tmp_path, "src")["paths"]


def test_a_call_interrupted_by_another_process_takes_its_resumed_result(tmp_path):
    (tmp_path / "strace.700").write_text(
        '700 12:00:00.1 openat(AT_FDCWD, "/root/.claude/state/consent.json", O_RDONLY <unfinished ...>\n'
        '701 12:00:00.2 openat(AT_FDCWD, "/etc/hosts", O_RDONLY) = 3\n'
        '700 12:00:00.3 <... openat resumed>) = -1 ENOENT (No such file or directory)\n')
    assert cut.trace(tmp_path, "src")["paths"]["/root/.claude/state/consent.json"] == {"openat": ["ENOENT"]}


def test_a_trace_cut_keeps_no_long_hex_run_from_a_path(tmp_path):
    key = "d2018f0ecf769ff6b36b1a6ec63fc7131e3520924919e9a3a1e4df13f27cf62c"
    (tmp_path / "strace.700").write_text(f'700 12:00:00.1 unlink("/logs/agent/sessions/sessions/7243.{key}.key") = 0\n')
    assert list(cut.trace(tmp_path, "src")["paths"]) == ["/logs/agent/sessions/sessions/7243.<hex>.key"]


def test_an_after_limit_cut_counts_the_requests_after_the_agent_phase_and_keeps_the_cli_s_tool_errors(tmp_path):
    blocked = "<tool_use_error>Blocked: standalone sleep 30. Use another tool.</tool_use_error>"
    events = [{"type": "user", "message": {"content": [{"type": "tool_result", "is_error": True, "content": c}]}}
              for c in (blocked, blocked, "model-run output that must not be kept")]
    trial = _trial(tmp_path, events)
    (trial / "result.json").write_text(json.dumps({"agent_execution": {
        "started_at": "2026-11-14T21:54:00Z", "finished_at": "2026-11-14T21:57:02Z"}}))
    end = 1794693422.0  # 2026-11-14T21:57:02Z
    log = _log(tmp_path, [_row(time=end - 5, bearer_matches=True), _row(time=end + 1.5, bearer_matches=True),
                          _row(time=end + 18.3, status=200, bearer_matches=True)])
    got = cut.after_limit(trial, log, "src")
    assert (got["requests"], got["requests_after_the_agent_phase"], got["last_request_after_s"],
            got["statuses_after"], got["cli_tool_errors"], "must not" in json.dumps(got)) == (
        3, 2, 18.3, [200], [blocked], False)


def test_a_live_probe_cut_replaces_every_identifier_by_one_shared_placeholder_and_keeps_one_config_key(tmp_path):
    session, org, request = "1234abcd-0000-4000-8000-00000000beef", "abcd1234-1111-4111-8111-11111111cafe", \
        "req_011MadeUpRequestId00001"
    trial = tmp_path / "probe" / "low" / "jobs" / "j" / "t"
    trial.mkdir(parents=True)
    _trial(trial, [{"type": "system", "subtype": "init", "session_id": session, "capabilities": ["msg_lifecycle_v1"]},
                   {"type": "assistant", "request_id": request, "message": {"id": "msg_011MadeUpMessageId00001"}}])
    (trial / "agent" / "sessions").mkdir()
    (trial / "agent" / "sessions" / ".claude.json").write_text(json.dumps(
        {"userID": "u" * 64, "machineID": "m" * 64, "cachedExtraUsageDisabledReason": "out_of_credits"}))
    log = tmp_path / "requests.jsonl"
    log.write_text(json.dumps({"time": 5.0, "effort": "low", "headers": {
        "request-id": request, "anthropic-organization-id": org,
        "anthropic-workspace-id": "wrkspc_013MadeUpWorkspace0001"}, "message_id": "msg_011MadeUpMessageId00001"}) + "\n")
    (tmp_path / "out").mkdir()
    cut.live_probe(tmp_path / "probe", log, "src", tmp_path / "out")
    texts = [(tmp_path / "out" / name).read_text() for name in ("session-low.json", "passthrough-log.json")]
    stream, row = json.loads(texts[0]), json.loads(texts[1])["requests"][0]
    assert ([v in t for t in texts for v in (session, org, request, "MadeUp", "u" * 64, "m" * 64)],
            stream["stream_tail"][-1]["request_id"] == row["headers"]["request-id"], len(row["headers"]["request-id"]),
            stream["init"]["capabilities"], stream["exported_config"], row["time"]) == (
        [False] * 12, True, len(request), ["msg_lifecycle_v1"], {"cachedExtraUsageDisabledReason": "out_of_credits"},
        0.0)
