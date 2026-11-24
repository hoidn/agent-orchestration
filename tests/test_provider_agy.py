"""The built-in `agy` (Google Antigravity CLI) templates, their stream-json codec and their child environment.

Fixtures under `tests/fixtures/agy/` are `agy` 1.5.16 captures with paths rewritten: `fresh` and `resumed` are one
conversation (the second resumes the first), `tools` a call with two tool steps, `refused` an unknown model.
The launch tests run a stand-in `agy` from a closed PATH; no provider is called.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from orchestrator.providers import (
    ProviderExecutor,
    ProviderParams,
    ProviderRegistry,
    ProviderSessionMode,
    ProviderSessionRequest,
)
from orchestrator.providers.session_transport import create_session_transport_accumulator
from orchestrator.providers.types import ProviderSessionMetadataMode
from tests.agent_session_shims import closed_path

AGY = ProviderSessionMetadataMode.AGY_STREAM_JSON_STDOUT.value
FIXTURES = Path(__file__).parent / "fixtures" / "agy"
CONVERSATION = "5078e3ed-4db2-4afe-9be7-47b241073d21"
KEYS = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_APPLICATION_CREDENTIALS")


def _fixture(name: str) -> bytes:
    return (FIXTURES / f"{name}.jsonl").read_bytes()


def _decode(raw: bytes, *, expected: str | None = None, require_terminal: bool = True, chunk: int = 0):
    text, activity = [], []
    accumulator = create_session_transport_accumulator(
        AGY, assistant_text_callback=text.append, tool_activity_callback=activity.append)
    for start in range(0, len(raw), chunk or len(raw) or 1):
        accumulator.feed(raw[start:start + (chunk or len(raw))])
    metadata, error = accumulator.finalize(expected_session_id=expected, require_terminal=require_terminal)
    return metadata, error, text, activity


def _line(event: str, payload: dict, **top) -> bytes:
    return json.dumps({"event": event, **top, event: payload}).encode() + b"\n"


# Codec

def test_codec_binds_the_conversation_and_joins_the_reply_across_chunks():
    metadata, error, text, _ = _decode(_fixture("tools"), chunk=7)
    response = [json.loads(line) for line in _fixture("tools").splitlines()][-1]["result"]["response"]
    assert error is None
    assert (metadata["session_id"], metadata["normalized_stdout"], "".join(text)) == (
        "e1449449-6f66-4832-9895-b4e00f3eb181", response, response)
    assert (metadata["result_subtype"], metadata["is_error"], metadata["event_count"]) == ("SUCCESS", False, 27)


def test_codec_reports_each_tool_start_and_completion_once():
    _, _, _, activity = _decode(_fixture("tools"))
    assert activity == ["Tool started: write_file", "Tool completed: write_file",
                        "Tool started: run_command", "Tool completed: run_command"]


def test_codec_resume_matches_the_requested_conversation():
    metadata, error, _, _ = _decode(_fixture("resumed"), expected=CONVERSATION)
    assert (error, metadata["session_id"]) == (None, CONVERSATION)


def test_codec_rejects_a_different_conversation_than_requested():
    metadata, error, _, _ = _decode(_fixture("resumed"), expected="another")
    assert (metadata, error["message"]) == (None, "Session transport did not match the requested session_id")


def test_codec_rejects_conflicting_conversation_ids():
    raw = _line("init", {}, conversation_id="a") + _line("result", {"conversation_id": "b", "status": "SUCCESS"})
    metadata, error, _, _ = _decode(raw)
    assert (metadata, error["context"]) == (None, {"session_ids": ["a", "b"]})


def test_codec_reads_the_conversation_from_a_step_alone():
    raw = (_line("step_update", {"conversation_id": "c", "step_index": 1, "step_type": "agent_response",
                                 "state": "DONE", "text_delta": "hi"})
           + _line("result", {"conversation_id": "", "status": "SUCCESS"}))
    metadata, error, _, _ = _decode(raw)
    assert (error, metadata["session_id"], metadata["normalized_stdout"]) == (None, "c", "hi")


def test_codec_marks_a_non_success_status_as_an_error():
    raw = _line("init", {}, conversation_id="c") + _line("result", {"conversation_id": "c", "status": "ERROR"})
    metadata, error, _, _ = _decode(raw)
    assert (error, metadata["result_subtype"], metadata["is_error"]) == (None, "ERROR", True)


def test_codec_refused_call_exposes_no_conversation():
    metadata, error, _, _ = _decode(_fixture("refused"))
    assert (metadata, error["message"]) == (None, "Session transport did not expose a session_id")


def test_codec_requires_the_result_line_only_when_asked():
    raw = b"".join(line + b"\n" for line in _fixture("fresh").splitlines()[:-1])
    _, missing, _, _ = _decode(raw)
    metadata, error, _, _ = _decode(raw, require_terminal=False)
    assert missing["message"] == "Session transport is missing a terminal result event"
    assert (error, metadata["result_subtype"], metadata["is_error"], metadata["normalized_stdout"]) == (
        None, None, False, "ok\n")


@pytest.mark.parametrize("raw", [b"not json\n", b'{"type":"result"}\n', b"[1]\n"], ids=["prose", "no-event", "list"])
def test_codec_rejects_a_line_that_is_not_an_agy_event(raw):
    metadata, error, _, _ = _decode(_line("init", {}, conversation_id="c") + raw)
    assert (metadata, error["context"]["line"]) == (None, 2)


# Templates

def _prepare(name: str, *, policy=None, session=None, env=None):
    executor = ProviderExecutor(Path.cwd(), ProviderRegistry())
    invocation, error = executor.prepare_invocation(name, ProviderParams(), {}, prompt_content="-p --model x",
                                                    session_request=session, env=env,
                                                    provider_call_policy=policy)
    assert error is None, error
    return executor, invocation


FRESH = ProviderSessionRequest(mode=ProviderSessionMode.FRESH)
RESUME = ProviderSessionRequest(mode=ProviderSessionMode.RESUME, session_id=CONVERSATION)
FLAGS = ["--dangerously-skip-permissions"]
STREAM = ["--output-format", "stream-json"]


@pytest.mark.parametrize(("name", "session", "middle"), [
    ("agy", None, FLAGS),
    ("agy_metered", None, FLAGS + STREAM),
    ("agy", FRESH, FLAGS + STREAM),
    ("agy", RESUME, FLAGS + STREAM + ["--conversation", CONVERSATION]),
    ("agy_metered", RESUME, FLAGS + STREAM + ["--conversation", CONVERSATION]),
], ids=["plain", "metered", "fresh", "resume", "metered-resume"])
@pytest.mark.parametrize(("policy", "model", "effort"), [
    (None, "gemini-3.8-flash", "low"), ({"model": "gemini-x", "effort": "high"}, "gemini-x", "high")],
    ids=["defaults", "policy"])
def test_commands_put_flags_first_and_the_prompt_last(name, session, middle, policy, model, effort):
    _, invocation = _prepare(name, policy=policy, session=session)
    assert invocation.command == ["agy", "--model", model, "--effort", effort, *middle, "-p", "-p --model x"]


def test_metered_and_session_calls_decode_agy_stream_json():
    registry = ProviderRegistry()
    plain, metered = registry.get("agy"), registry.get("agy_metered")
    assert (plain.command_metadata_mode, metered.command_metadata_mode, plain.session_support.metadata_mode,
            plain.session_support.turn_boundary_resume) == (None, AGY, AGY, False)


# Child environment and launches through the executor

STANDIN = r'''import json, os, sys
from pathlib import Path
argv = sys.argv[1:]
with open(os.environ["AGY_STANDIN_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps({"argv": argv, "keys": sorted(k for k in os.environ if k.startswith(("GEMINI", "GOOGLE")))})
              + "\n")
fixtures = Path(os.environ["AGY_STANDIN_FIXTURES"])
if "--conversation" in argv:
    sys.stdout.buffer.write((fixtures / "resumed.jsonl").read_bytes())
elif "stream-json" in argv:
    sys.stdout.buffer.write((fixtures / "fresh.jsonl").read_bytes())
else:
    sys.stdout.write("ok\n")
'''


@pytest.fixture
def standin(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "agy").write_text(f"#!{sys.executable}\n" + STANDIN, encoding="utf-8")
    (bin_dir / "agy").chmod(0o700)
    monkeypatch.setenv("PATH", closed_path(bin_dir))
    monkeypatch.setenv("AGY_STANDIN_LOG", str(tmp_path / "calls.jsonl"))
    monkeypatch.setenv("AGY_STANDIN_FIXTURES", str(FIXTURES))
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "kept")
    for key in KEYS:
        monkeypatch.setenv(key, "parent-secret")
    return tmp_path


def _calls(root: Path) -> list[dict]:
    return [json.loads(line) for line in (root / "calls.jsonl").read_text().splitlines()]


@pytest.mark.parametrize(("name", "session"), [("agy", None), ("agy_metered", None), ("agy", FRESH), ("agy", RESUME)],
                         ids=["plain", "metered", "fresh", "resume"])
def test_no_google_credential_variable_reaches_the_child(standin, name, session):
    executor, invocation = _prepare(name, session=session, env={"GOOGLE_API_KEY": "step-secret"})
    result = executor.execute(invocation, cwd=standin,
                              execution_env_overlay={"GEMINI_API_KEY": "overlay-secret"})
    assert (result.exit_code, result.error) == (0, None)
    assert _calls(standin)[0]["keys"] == ["GOOGLE_CLOUD_PROJECT"]


def test_session_fresh_then_resume_binds_one_conversation(standin):
    executor, fresh = _prepare("agy", session=FRESH)
    first = executor.execute(fresh, cwd=standin)
    _, resume = _prepare("agy", session=ProviderSessionRequest(
        mode=ProviderSessionMode.RESUME, session_id=first.provider_session["session_id"]))
    second = executor.execute(resume, cwd=standin)
    assert [(run.exit_code, run.error, run.provider_session["session_id"], run.stdout) for run in (first, second)] == [
        (0, None, CONVERSATION, b"ok\n"), (0, None, CONVERSATION, b"ok\n")]
    assert [call["argv"][-4:-2] for call in _calls(standin)] == [STREAM, ["--conversation", CONVERSATION]]


def test_a_template_without_env_unset_passes_the_variables_on(standin):
    """The rule belongs to the built-in templates: a workflow's own `agy` template keeps its environment."""
    from dataclasses import replace

    registry = ProviderRegistry()
    registry.register(replace(registry.get("agy"), name="agy_with_key", env_unset=()))
    executor = ProviderExecutor(standin, registry)
    invocation, error = executor.prepare_invocation("agy_with_key", ProviderParams(), {}, prompt_content="hi")
    assert error is None and executor.execute(invocation, cwd=standin).exit_code == 0
    assert _calls(standin)[0]["keys"] == sorted([*KEYS, "GOOGLE_CLOUD_PROJECT"])
