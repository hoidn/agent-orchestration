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
    assert (len(got["shapes"]), got["requests"]) == (1, [[0, 200, 3, 0.0, None], [0, 429, 5, 2.5, None]])


def _trial(tmp_path, events):
    (tmp_path / "agent").mkdir()
    (tmp_path / "agent" / "claude-code.txt").write_text("".join(json.dumps(e) + "\n" for e in events))
    (tmp_path / "result.json").write_text(json.dumps({"verifier_result": {"rewards": {"reward": 0.0}}}))
    return tmp_path


def test_a_fixture_counts_the_retries_and_keeps_the_verifier_result(tmp_path):
    retry = {"type": "system", "subtype": "api_retry", "attempt": 1}
    got = cut.fixture(_trial(tmp_path, [{"type": "system", "subtype": "init"}, retry, retry]), "src")
    assert (got["n_api_retry"], got["verifier_result"]) == (2, {"rewards": {"reward": 0.0}})
