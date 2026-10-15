"""The plain command form uses the adapter's own argv and stdin prompt, and the campaign stops at --max-calls."""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

from orchestrator.providers.registry import ProviderRegistry

PROBE_DIR = Path(__file__).resolve().parents[2] / "scripts" / "experiments"
if str(PROBE_DIR) not in sys.path:
    sys.path.insert(0, str(PROBE_DIR))
probe = importlib.import_module("native_session_cli_probe")


def _fake_claude(log: Path) -> str:
    """A synthetic CLI: logs model calls, appends one native row per call, prints a stream-json result."""
    return (
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "if '--version' in sys.argv: print('0.0.0 (fake)'); raise SystemExit(0)\n"
        f"Path({str(log)!r}).open('a').write(json.dumps({{'argv': sys.argv[1:], 'stdin': sys.stdin.read()}}) + '\\n')\n"
        "store = Path(os.environ['CLAUDE_CONFIG_DIR']) / 'projects' / 'p'\n"
        "store.mkdir(parents=True, exist_ok=True)\n"
        "(store / 's.jsonl').open('a').write(json.dumps({'type': 'user', 'sessionId': 's'}) + '\\n')\n"
        "print(json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False, 'session_id': 's'}))\n"
    )


def _adapter(session: str | None) -> list[str]:
    support = ProviderRegistry().get("claude_unrestricted_workspace").session_support
    template = support.fresh_command if session is None else support.resume_command
    values = {"${model}": "haiku", "${effort}": "low", "${SESSION_ID}": session}
    return [values.get(token, token) for token in template]


def test_plain_form_builds_the_adapter_fresh_argv(tmp_path: Path) -> None:
    command = probe._command("claude", "claude", "haiku", tmp_path, "review", "n0nce", None, None, command_form="plain")
    assert command == _adapter(None)


def test_plain_form_builds_the_adapter_resume_argv(tmp_path: Path) -> None:
    command = probe._command("claude", "claude", "haiku", tmp_path, "write", "n1", "sess-1", "t0", command_form="plain")
    assert command == _adapter("sess-1")


@pytest.fixture
def fake_campaign(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[int, list[dict], Path]:
    log = tmp_path / "argv.jsonl"
    binary = tmp_path / "bin" / "claude"
    binary.parent.mkdir()
    binary.write_text(_fake_claude(log))
    binary.chmod(0o700)
    monkeypatch.setenv("NATIVE_SESSION_PROBE_FAKE_CLAUDE", str(binary))
    sentinel = tmp_path / "home" / ".claude" / ".credentials.json"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("synthetic credential sentinel")
    sentinel.chmod(0o000)  # any attempt to read or copy it fails the campaign
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    output = tmp_path / "out"
    rc = probe.main([
        "--provider", "claude", "--execute", "--model", "haiku", "--output-dir", str(output),
        "--command-form", "plain", "--max-calls", "2",
    ])
    calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    return rc, calls, output


def test_max_calls_bounds_the_plain_campaign(fake_campaign) -> None:
    _rc, calls, _output = fake_campaign
    assert len(calls) == 2


def test_plain_campaign_sends_prompt_on_stdin_and_resumes_the_stdout_session(fake_campaign) -> None:
    _rc, calls, _output = fake_campaign
    assert [call["argv"] for call in calls] == [_adapter(None)[1:], _adapter("s")[1:]] and all(c["stdin"] for c in calls)


def test_fake_plain_campaign_completes_without_reading_credentials(fake_campaign) -> None:
    rc, _calls, output = fake_campaign
    status = json.loads((output / "observations.json").read_text())["status"]
    assert (rc, status) == (0, "PLAIN_CAMPAIGN_COMPLETE")


def test_fake_plain_campaign_leaves_no_staged_credential(fake_campaign) -> None:
    _rc, _calls, output = fake_campaign
    assert not list(output.rglob(".credentials.json"))
