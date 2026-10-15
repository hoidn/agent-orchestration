from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
from types import SimpleNamespace
from types import ModuleType
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "scripts/experiments/native_session_cli_probe.py"


def _fake_provider(path: Path, hit: Path) -> None:
    path.write_text(
        f"#!{sys.executable}\n"
        "from pathlib import Path\n"
        f"Path({str(hit)!r}).write_text('called')\n"
        "raise SystemExit(97)\n",
        encoding="utf-8",
    )
    path.chmod(0o700)


def _run(
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _probe_module() -> ModuleType:
    if str(CLI.parent) not in sys.path:
        sys.path.insert(0, str(CLI.parent))
    spec = importlib.util.spec_from_file_location("native_session_cli_probe_test", CLI)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_default_prepare_writes_private_manifest_without_running_provider_or_reading_auth(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    auth = home / ".codex/auth.json"
    auth.write_text("synthetic credential sentinel", encoding="utf-8")
    provider_bin = tmp_path / "bin"
    provider_bin.mkdir()
    hit = tmp_path / "provider-was-run"
    _fake_provider(provider_bin / "codex", hit)
    output = tmp_path / "prepared"
    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": str(provider_bin),
    }

    result = _run(
        "--provider",
        "codex",
        "--output-dir",
        str(output),
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert not hit.exists()
    assert auth.read_text(encoding="utf-8") == "synthetic credential sentinel"
    manifest = json.loads((output / "prepared.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "PREPARED"
    assert manifest["provider"] == "codex"
    assert output.stat().st_mode & 0o777 == 0o700
    schema1 = json.loads((output / "schemas/schema-1.json").read_text())
    schema2 = json.loads((output / "schemas/schema-2.json").read_text())
    assert schema1["required"] == ["schema", "nonce", "reviewed"]
    assert schema2["required"] == ["schema", "nonce", "executed"]
    assert schema1["additionalProperties"] is schema2["additionalProperties"] is False


def test_prepare_has_no_subprocess_or_credential_open_copy_or_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _probe_module()
    home = tmp_path / "home"
    auth = home / ".codex/auth.json"
    auth.parent.mkdir(parents=True)
    auth.write_text("synthetic credential sentinel", encoding="utf-8")
    events: list[str] = []
    real_path_open = Path.open
    real_read_text = Path.read_text
    real_read_bytes = Path.read_bytes
    real_copyfile = module.shutil.copyfile
    real_popen = module.subprocess.Popen

    def audit_path_open(path: Path, *args: object, **kwargs: object):
        if path == auth:
            events.append("Path.open")
        return real_path_open(path, *args, **kwargs)

    def audit_read_text(path: Path, *args: object, **kwargs: object):
        if path == auth:
            events.append("Path.read_text")
        return real_read_text(path, *args, **kwargs)

    def audit_read_bytes(path: Path, *args: object, **kwargs: object):
        if path == auth:
            events.append("Path.read_bytes")
        return real_read_bytes(path, *args, **kwargs)

    def audit_copyfile(source: object, destination: object, *args: object, **kwargs: object):
        events.append("shutil.copyfile")
        return real_copyfile(source, destination, *args, **kwargs)

    def audit_popen(*args: object, **kwargs: object):
        events.append("subprocess.Popen")
        return real_popen(*args, **kwargs)

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "open", audit_path_open)
    monkeypatch.setattr(Path, "read_text", audit_read_text)
    monkeypatch.setattr(Path, "read_bytes", audit_read_bytes)
    monkeypatch.setattr(module.shutil, "copyfile", audit_copyfile)
    monkeypatch.setattr(module.subprocess, "Popen", audit_popen)

    result = module.main(["--provider", "codex", "--output-dir", str(tmp_path / "prepared")])

    assert result == 0
    assert events == []


def test_explicit_model_alone_does_not_enable_execution(tmp_path: Path) -> None:
    provider_bin = tmp_path / "bin"
    provider_bin.mkdir()
    hit = tmp_path / "provider-was-run"
    _fake_provider(provider_bin / "codex", hit)
    output = tmp_path / "prepared"
    result = _run(
        "--provider",
        "codex",
        "--model",
        "gpt-6-luna",
        "--output-dir",
        str(output),
        env={**os.environ, "PATH": str(provider_bin)},
    )

    assert result.returncode == 0, result.stderr
    assert not hit.exists()
    assert json.loads((output / "prepared.json").read_text())["status"] == "PREPARED"


def test_execute_requires_explicit_model_before_launching_provider(tmp_path: Path) -> None:
    provider_bin = tmp_path / "bin"
    provider_bin.mkdir()
    hit = tmp_path / "provider-was-run"
    _fake_provider(provider_bin / "codex", hit)

    result = _run(
        "--provider",
        "codex",
        "--execute",
        "--output-dir",
        str(tmp_path / "run"),
        env={**os.environ, "PATH": str(provider_bin)},
    )

    assert result.returncode != 0
    assert not hit.exists()
    assert "--model" in result.stderr


def test_prepare_rejects_output_inside_repository(tmp_path: Path) -> None:
    result = _run(
        "--provider",
        "codex",
        "--output-dir",
        str(ROOT / "docs" / "reports" / "probe-test-output"),
    )

    assert result.returncode != 0
    assert not (ROOT / "docs" / "reports" / "probe-test-output").exists()
    assert "outside" in result.stderr


def test_prepare_does_not_reuse_existing_or_symlink_output_roots(tmp_path: Path) -> None:
    existing = tmp_path / "existing"
    existing.mkdir(mode=0o755)
    sentinel = existing / "keep.txt"
    sentinel.write_text("leave alone", encoding="utf-8")
    existing.chmod(0o755)
    link = tmp_path / "linked"
    link.symlink_to(existing, target_is_directory=True)

    for output in (existing, link):
        result = _run("--provider", "codex", "--output-dir", str(output))
        assert result.returncode != 0

    assert sentinel.read_text(encoding="utf-8") == "leave alone"
    assert existing.stat().st_mode & 0o777 == 0o755
    assert not (existing / "prepared.json").exists()


def test_native_file_backup_delete_restore_stays_within_isolated_home(tmp_path: Path) -> None:
    module = _probe_module()
    home = tmp_path / "provider-home"
    evidence = tmp_path / "evidence"
    home.mkdir()
    evidence.mkdir()
    session = home / "session.jsonl"
    sentinel = home / "other-session.jsonl"
    backup = evidence / "session.backup.jsonl"
    session.write_bytes(b'{"native":"session"}\n')
    sentinel.write_bytes(b"keep")

    digest = module.backup_session_file(home, session, evidence, backup)
    module.delete_session_file(home, session)
    assert not session.exists()
    module.restore_session_file(home, session, evidence, backup)

    assert session.read_bytes() == backup.read_bytes() == b'{"native":"session"}\n'
    assert sentinel.read_bytes() == b"keep"
    assert digest.startswith("sha256:")


@pytest.mark.parametrize(
    ("provider", "native_relative", "unrelated_relative"),
    [
        (
            "codex",
            "sessions/2026/10/13/rollout-session.jsonl",
            "telemetry.jsonl",
        ),
        (
            "claude",
            "projects/workspace/session.jsonl",
            "history.jsonl",
        ),
    ],
)
def test_provider_session_discovery_ignores_unrelated_jsonl_and_rejects_ambiguity(
    tmp_path: Path, provider: str, native_relative: str, unrelated_relative: str
) -> None:
    module = _probe_module()
    home = tmp_path / provider
    selected = home / native_relative
    selected.parent.mkdir(parents=True)
    selected.write_text("native", encoding="utf-8")
    unrelated = home / unrelated_relative
    unrelated.write_text("not a session", encoding="utf-8")

    assert module._session_file(provider, home) == selected
    second = (
        home / "sessions/2026/10/13/rollout-second.jsonl"
        if provider == "codex"
        else home / "projects/other/session.jsonl"
    )
    second.parent.mkdir(parents=True, exist_ok=True)
    second.write_text("ambiguous", encoding="utf-8")
    with pytest.raises(module.ProbeStop):
        module._session_file(provider, home)


def test_model_invocation_admission_counts_failures_and_blocks_ninth_launch(tmp_path: Path) -> None:
    module = _probe_module()
    output = tmp_path / "campaign"
    output.mkdir(mode=0o700)
    module._prepare("codex", "fake-model", output)
    executable = tmp_path / "fake-codex"
    executable.write_text("synthetic", encoding="utf-8")
    launches: list[int] = []

    def fail_launch(ordinal: int, *_args: object, **_kwargs: object) -> None:
        launches.append(ordinal)
        raise OSError("synthetic process creation failure")

    tracker = SimpleNamespace(launch=fail_launch)
    report: dict[str, object] = {"invocation_count": 0, "invocations": []}
    for ordinal in range(1, module.MAX_INVOCATIONS + 1):
        with pytest.raises(OSError, match="synthetic process creation failure"):
            module._invoke(
                tracker,
                report,
                ordinal=ordinal,
                phase="write",
                provider="codex",
                executable=str(executable),
                fake=True,
                model="fake-model",
                output=output,
                timeout=1.0,
                session="synthetic-session",
                predecessor=f"turn-{ordinal - 1}",
            )

    with pytest.raises(module.ProbeStop, match="invocation limit"):
        module._invoke(
            tracker,
            report,
            ordinal=9,
            phase="write",
            provider="codex",
            executable=str(executable),
            fake=True,
            model="fake-model",
            output=output,
            timeout=1.0,
            session="synthetic-session",
            predecessor="turn-8",
        )
    assert launches == list(range(1, 9))
    assert report["invocation_count"] == 8
    assert len(report["invocations"]) == 8
    assert all(row["launch_attempted"] is True for row in report["invocations"])


@pytest.mark.parametrize("unsafe", ["outside", "symlink"])
def test_native_session_file_operations_reject_escape_or_symlink(
    tmp_path: Path,
    unsafe: str,
) -> None:
    module = _probe_module()
    home = tmp_path / "provider-home"
    evidence = tmp_path / "evidence"
    home.mkdir()
    evidence.mkdir()
    real = home / "session.jsonl"
    real.write_text("safe", encoding="utf-8")
    outside = tmp_path / "outside.jsonl"
    outside.write_text("sentinel", encoding="utf-8")
    target = outside if unsafe == "outside" else home / "linked.jsonl"
    if unsafe == "symlink":
        target.symlink_to(real)
    backup = evidence / "backup.jsonl"

    with pytest.raises(ValueError):
        module.backup_session_file(home, target, evidence, backup)

    assert real.read_text(encoding="utf-8") == "safe"
    assert outside.read_text(encoding="utf-8") == "sentinel"
    assert not backup.exists()


@pytest.mark.parametrize("timeout", ["nan", "inf", "-inf"])
def test_execute_timeout_must_be_finite(tmp_path: Path, timeout: str) -> None:
    result = _run(
        "--provider",
        "codex",
        "--model",
        "fake-model",
        "--execute",
        "--timeout-seconds",
        timeout,
        "--output-dir",
        str(tmp_path / "run"),
    )

    assert result.returncode != 0
    assert not (tmp_path / "run").exists()


def _fake_codex(path: Path) -> None:
    path.write_text(
        f"#!{sys.executable}\n"
        + r'''import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

if "--version" in sys.argv:
    print("fake-codex 0.0")
    raise SystemExit(0)

call = int(os.environ["NATIVE_SESSION_PROBE_INVOCATION"])
controls = Path(os.environ["NATIVE_SESSION_PROBE_CONTROLS"])
home = Path(os.environ["CODEX_HOME"])
nonce = os.environ["NATIVE_SESSION_PROBE_NONCE"]
session = os.environ["NATIVE_SESSION_PROBE_SESSION"] or "fake-session"
behavior = os.environ.get("NATIVE_SESSION_PROBE_FAKE_BEHAVIOR", "protocol")
if behavior == "fail":
    raise SystemExit(19)
if behavior == "escaped-child":
    code = (
        "import os,time; from pathlib import Path; "
        "Path(os.environ['NATIVE_SESSION_PROBE_MARKER']).write_text(str(os.getpid())); "
        "time.sleep(30)"
    )
    env = dict(os.environ)
    env["NATIVE_SESSION_PROBE_MARKER"] = str(controls / "escaped-pid")
    subprocess.Popen([sys.executable, "-c", code], env=env, start_new_session=True)
    (controls / "entered-1").write_text("entered")
    time.sleep(30)
    raise SystemExit(0)
if behavior == "orphan-immediate":
    code = (
        "import os,time; from pathlib import Path; "
        "Path(os.environ['NATIVE_SESSION_PROBE_MARKER']).write_text(str(os.getpid())); "
        "time.sleep(30)"
    )
    env = dict(os.environ)
    env["NATIVE_SESSION_PROBE_MARKER"] = str(controls / "escaped-pid")
    subprocess.Popen([sys.executable, "-c", code], env=env, start_new_session=True)
    raise SystemExit(0)
if call == 5:
    if behavior == "graceful-stop-zero":
        def terminate_with_zero(signum, frame):
            raise SystemExit(0)
        signal.signal(signal.SIGTERM, terminate_with_zero)
    task = re.search(r"```sh\n(.*?)\n```", sys.argv[-1], re.S)
    if task is None:
        raise SystemExit(23)
    child = subprocess.Popen(shlex.split(task.group(1)), start_new_session=True)
    deadline = time.monotonic() + 2
    while not (controls / "entered-5").exists() and time.monotonic() < deadline:
        time.sleep(.01)
    if behavior == "marker-exit":
        os.killpg(child.pid, signal.SIGKILL)
        child.wait()
        raise SystemExit(0)
    time.sleep(30)
    raise SystemExit(0)

if call == 3:
    code = (
        "import os,time\nfrom pathlib import Path\n"
        "time.sleep(.4 if os.environ.get('NATIVE_SESSION_PROBE_FAKE_BEHAVIOR') == 'delayed-marker-hang' else 0)\n"
        "Path(os.environ['NATIVE_SESSION_PROBE_ENTERED']).write_text('entered')\n"
        "deadline=time.monotonic()+25\n"
        "while time.monotonic()<deadline and not Path(os.environ['NATIVE_SESSION_PROBE_RELEASE']).exists():\n"
        "    time.sleep(.01)\n"
    )
    env = dict(os.environ)
    env["NATIVE_SESSION_PROBE_ENTERED"] = str(controls / "entered-3")
    env["NATIVE_SESSION_PROBE_RELEASE"] = str(controls / "release-3")
    subprocess.Popen([sys.executable, "-c", code], env=env, start_new_session=True)

if call == 8 and behavior == "fallback-home":
    home = home.parent / "codex"
store = home / "sessions" / "2026" / "10" / "13" / ("rollout-replacement.jsonl" if call == 7 and behavior == "replacement-file" else "rollout-probe.jsonl")
new_store = not store.exists()
if call == 1 or new_store:
    if call != 1:
        session = "replacement-session"
    rows = [{"type": "session_meta", "payload": {"id": session}}]
else:
    rows = []
turn = f"turn-{call}"
kind = "reviewed" if call == 1 else "executed"
schema = 1 if call == 1 else 2
rows.extend([
    {"type": "event_msg", "payload": {"type": "task_started", "turn_id": turn}},
    {"type": "event_msg", "payload": {"type": "item_completed", "thread_id": session, "turn_id": turn, "item": {"id": f"u-{call}", "type": "UserMessage", "content": [{"type": "text", "text": nonce, "text_elements": []}]}}},
])
if call == 2:
    Path(os.environ["NATIVE_SESSION_PROBE_WRITE_PATH"]).write_text(nonce)
if call == 1 and behavior == "review-control-write":
    (controls / "unauthorized-write").write_text(nonce)
if call != 3 or behavior == "serialized-overlap":
    result = {"schema": schema, "nonce": nonce, kind: True}
    rows.extend([
        {"type": "event_msg", "payload": {"type": "item_completed", "thread_id": session, "turn_id": turn, "item": {"id": f"a-{call}", "type": "AgentMessage", "phase": "final_answer", "content": [{"type": "Text", "text": json.dumps(result)}]}}},
        {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": turn, "last_agent_message": json.dumps(result)}},
    ])
if call == 4 and behavior == "slow-overlap":
    time.sleep(30)
    raise SystemExit(0)
store.parent.mkdir(parents=True, exist_ok=True)
with store.open("a", encoding="utf-8") as stream:
    stream.write("".join(json.dumps(row) + "\n" for row in rows))
if call in (3, 4) and behavior == "delayed-marker-hang":
    time.sleep(30)
if call == 3:
    while not (controls / "release-3").exists():
        time.sleep(.01)
    if behavior == "serialized-overlap":
        raise SystemExit(0)
    result = {"schema": 2, "nonce": nonce, "executed": True}
    tail = [
        {"type": "event_msg", "payload": {"type": "item_completed", "thread_id": session, "turn_id": turn, "item": {"id": f"a-{call}", "type": "AgentMessage", "phase": "final_answer", "content": [{"type": "Text", "text": json.dumps(result)}]}}},
        {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": turn, "last_agent_message": json.dumps(result)}},
    ]
    with store.open("a", encoding="utf-8") as stream:
        stream.write("".join(json.dumps(row) + "\n" for row in tail))
''',
        encoding="utf-8",
    )
    path.chmod(0o700)


def _fake_environment(tmp_path: Path, *, behavior: str = "protocol") -> tuple[dict[str, str], Path]:
    home = tmp_path / "fake-home"
    auth = home / ".codex/auth.json"
    auth.parent.mkdir(parents=True)
    auth.write_text("synthetic-only-auth", encoding="utf-8")
    binary = tmp_path / "fake-codex"
    _fake_codex(binary)
    return (
        {
            **os.environ,
            "HOME": str(home),
            "PATH": os.environ.get("PATH", ""),
            "NATIVE_SESSION_PROBE_FAKE_CODEX": str(binary),
            "NATIVE_SESSION_PROBE_FAKE_BEHAVIOR": behavior,
        },
        auth,
    )


def test_fake_cli_campaign_uses_public_entrypoint_and_stops_at_unproven_exclusivity(
    tmp_path: Path,
) -> None:
    env, auth = _fake_environment(tmp_path)
    output = tmp_path / "campaign"

    result = _run(
        "--provider",
        "codex",
        "--execute",
        "--model",
        "fake-model",
        "--timeout-seconds",
        "8",
        "--output-dir",
        str(output),
        env=env,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads((output / "observations.json").read_text(encoding="utf-8"))
    assert report["cli_version"]["output"] == "fake-codex 0.0"
    assert report["cli_version"]["synthetic_cli"] is True
    assert report["invocation_count"] == 4
    assert [row["ordinal"] for row in report["invocations"]] == [1, 2, 3, 4]
    assert [row["status"] for row in report["invocations"][:2]] == ["OBSERVED", "OBSERVED"]
    assert report["gates"]["exact_completion"]["status"] == "OBSERVED"
    assert report["gates"]["exclusive_continuation"]["status"] == "NOT_OBSERVED"
    assert report["gates"]["exclusive_continuation"]["reason"]
    assert all(row["status"] == "INCONCLUSIVE" for row in report["remaining_invocations"])
    assert not list((output / "provider-home").glob("**/auth.json"))
    assert auth.read_text(encoding="utf-8") == "synthetic-only-auth"
    assert (output / "workspace" / "execution.txt").read_text(encoding="utf-8") == report["invocations"][1]["nonce"]
    assert report["invocations"][0]["raw_sha256"].startswith("sha256:")


@pytest.mark.parametrize("behavior", ["slow-overlap", "delayed-marker-hang"])
def test_short_overlap_timeout_bounds_both_concurrent_model_calls(tmp_path: Path, behavior: str) -> None:
    env, auth = _fake_environment(tmp_path, behavior=behavior)
    output = tmp_path / "short-overlap"

    result = _run(
        "--provider",
        "codex",
        "--execute",
        "--model",
        "fake-model",
        "--timeout-seconds",
        "1",
        "--output-dir",
        str(output),
        env=env,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads((output / "observations.json").read_text(encoding="utf-8"))
    assert report["invocation_count"] == 4
    row3, row4 = report["invocations"][2:4]
    assert row3["quiescent"] is True
    assert row3["deadline_cancellation"] is True
    assert row3["stop_requested_monotonic"] <= row3["started_monotonic"] + 1.1
    assert row3["provider_stopped_monotonic"] <= row3["started_monotonic"] + 1.2
    assert row3["cleanup_duration_seconds"] <= 0.8
    assert row4["quiescent"] is True
    assert row4["stop_requested_monotonic"] <= row4["started_monotonic"] + 1.1
    assert row4["provider_stopped_monotonic"] <= row4["started_monotonic"] + 1.2
    assert row4["cleanup_duration_seconds"] <= 0.8
    assert report["gates"]["exclusive_continuation"]["status"] == ("INCONCLUSIVE" if behavior == "slow-overlap" else "NOT_OBSERVED")
    assert not list((output / "provider-home").glob("**/auth.json"))
    assert auth.read_text(encoding="utf-8") == "synthetic-only-auth"


def test_fake_execution_failure_counts_once_and_removes_copied_auth(tmp_path: Path) -> None:
    env, auth = _fake_environment(tmp_path, behavior="fail")
    output = tmp_path / "failed-campaign"

    result = _run(
        "--provider",
        "codex",
        "--execute",
        "--model",
        "fake-model",
        "--output-dir",
        str(output),
        env=env,
    )

    assert result.returncode != 0
    report = json.loads((output / "observations.json").read_text(encoding="utf-8"))
    assert report["invocation_count"] == 1
    assert report["invocations"][0]["returncode"] == 19
    receipt = report["invocations"][0]
    assert receipt["tracking_ok"] is True
    assert receipt["unexpected_descendants"] is receipt["ambiguous_adoption"] is False
    assert receipt["leader_pid"] > 0 and receipt["leader_start_time"] > 0
    assert isinstance(receipt["tracked_processes"], list)
    assert receipt["tracking_failures"] == []
    assert [row["ordinal"] for row in report["remaining_invocations"]] == list(range(2, 9))
    assert all(row["not_run"] is True for row in report["remaining_invocations"])
    assert not list((output / "provider-home").glob("**/auth.json"))
    assert auth.read_text(encoding="utf-8") == "synthetic-only-auth"


@pytest.mark.parametrize("behavior", ["review-control-write", "serialized-overlap"])
def test_native_gates_reject_changed_review_controls_or_serialized_native_turns(tmp_path: Path, behavior: str) -> None:
    env, _ = _fake_environment(tmp_path, behavior=behavior)
    output = tmp_path / "native-gate-case"
    result = _run("--provider", "codex", "--execute", "--model", "fake-model", "--timeout-seconds", "3", "--output-dir", str(output), env=env)
    assert result.returncode == 0, result.stderr
    report = json.loads((output / "observations.json").read_text())
    gate = "exact_completion" if behavior == "review-control-write" else "exclusive_continuation"
    assert report["gates"][gate]["status"] == "INCONCLUSIVE"
    assert report["invocation_count"] == (1 if behavior == "review-control-write" else 4)


def test_failed_auth_chmod_after_copy_is_cleaned_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _probe_module()
    env, _auth = _fake_environment(tmp_path)
    for key in (
        "HOME",
        "PATH",
        "NATIVE_SESSION_PROBE_FAKE_CODEX",
        "NATIVE_SESSION_PROBE_FAKE_BEHAVIOR",
    ):
        monkeypatch.setenv(key, env[key])
    output = tmp_path / "chmod-failure"
    staged = output / "provider-home/codex/auth.json"
    real_chmod = Path.chmod

    def fail_staged_chmod(path: Path, mode: int, *args: object, **kwargs: object) -> None:
        if path == staged and mode == 0o600:
            raise OSError("synthetic chmod failure after copy")
        real_chmod(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "chmod", fail_staged_chmod)
    result = module.main(
        [
            "--provider",
            "codex",
            "--execute",
            "--model",
            "fake-model",
            "--output-dir",
            str(output),
        ]
    )

    assert result != 0
    report = json.loads((output / "observations.json").read_text(encoding="utf-8"))
    assert report["invocation_count"] == 0
    assert report["staged_auth_removed"] is True
    assert not staged.exists()


def test_auth_cleanup_survives_process_tracker_close_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _probe_module()
    env, auth = _fake_environment(tmp_path)
    for key in (
        "HOME",
        "PATH",
        "NATIVE_SESSION_PROBE_FAKE_CODEX",
        "NATIVE_SESSION_PROBE_FAKE_BEHAVIOR",
    ):
        monkeypatch.setenv(key, env[key])
    output = tmp_path / "close-failure"
    real_close = module.ProcessTracker.close

    def close_then_raise(tracker: object) -> None:
        real_close(tracker)
        raise RuntimeError("synthetic tracker close failure")

    monkeypatch.setattr(module.ProcessTracker, "close", close_then_raise)
    result = module.main(
        [
            "--provider",
            "codex",
            "--execute",
            "--model",
            "fake-model",
            "--timeout-seconds",
            "5",
            "--output-dir",
            str(output),
        ]
    )

    report = json.loads((output / "observations.json").read_text(encoding="utf-8"))
    assert result == 0
    assert report["status"] == "STOPPED_ERROR"
    assert "synthetic tracker close failure" in report["process_tracker_cleanup_error"]
    assert report["staged_auth_removed"] is True
    assert not list((output / "provider-home").glob("**/auth.json"))
    assert auth.read_text(encoding="utf-8") == "synthetic-only-auth"


def test_timeout_quiesces_a_tracked_tool_that_escaped_the_cli_process_group(
    tmp_path: Path,
) -> None:
    env, auth = _fake_environment(tmp_path, behavior="escaped-child")
    output = tmp_path / "timed-out"

    result = _run(
        "--provider",
        "codex",
        "--execute",
        "--model",
        "fake-model",
        "--timeout-seconds",
        "0.5",
        "--output-dir",
        str(output),
        env=env,
    )

    assert result.returncode != 0
    pid_path = output / "workspace/.probe-controls/escaped-pid"
    deadline = time.monotonic() + 2
    while not pid_path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert pid_path.exists()
    child_pid = int(pid_path.read_text(encoding="utf-8"))
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)
    report = json.loads((output / "observations.json").read_text(encoding="utf-8"))
    assert report["invocation_count"] == 1
    assert report["invocations"][0]["quiescent"] is True
    assert not list((output / "provider-home").glob("**/auth.json"))
    assert auth.read_text(encoding="utf-8") == "synthetic-only-auth"


def test_immediate_cli_exit_still_tracks_and_kills_adopted_escaped_child(tmp_path: Path) -> None:
    env, auth = _fake_environment(tmp_path, behavior="orphan-immediate")
    output = tmp_path / "orphaned-child"

    result = _run(
        "--provider",
        "codex",
        "--execute",
        "--model",
        "fake-model",
        "--timeout-seconds",
        "2",
        "--output-dir",
        str(output),
        env=env,
    )

    assert result.returncode != 0
    pid_path = output / "workspace/.probe-controls/escaped-pid"
    deadline = time.monotonic() + 2
    while not pid_path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert pid_path.exists()
    child_pid = int(pid_path.read_text(encoding="utf-8"))
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)
    report = json.loads((output / "observations.json").read_text(encoding="utf-8"))
    assert report["invocations"][0]["quiescent"] is False
    assert not list((output / "provider-home").glob("**/auth.json"))
    assert auth.read_text(encoding="utf-8") == "synthetic-only-auth"


def _seed_codex_turns(path: Path, session: str, turns: int) -> None:
    rows: list[dict[str, object]] = [{"type": "session_meta", "payload": {"id": session}}]
    for number in range(1, turns + 1):
        turn = f"turn-{number}"
        nonce = f"seed-nonce-{number}"
        schema = 1 if number == 1 else 2
        key = "reviewed" if number == 1 else "executed"
        result = {"schema": schema, "nonce": nonce, key: True}
        rows.extend(
            [
                {"type": "event_msg", "payload": {"type": "task_started", "turn_id": turn}},
                {"type": "event_msg", "payload": {"type": "item_completed", "thread_id": session, "turn_id": turn, "item": {"id": f"user-{number}", "type": "UserMessage", "content": [{"type": "text", "text": nonce, "text_elements": []}]}}},
                {"type": "event_msg", "payload": {"type": "item_completed", "thread_id": session, "turn_id": turn, "item": {"id": f"assistant-{number}", "type": "AgentMessage", "phase": "final_answer", "content": [{"type": "Text", "text": json.dumps(result)}]}}},
                {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": turn, "last_agent_message": json.dumps(result)}},
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


@pytest.mark.parametrize("behavior", ["protocol", "marker-exit", "graceful-stop-zero", "negative-recovery", "unquiescent-recovery", "unquiescent-loss", "failed-loss", "fallback-home", "replacement-file"])
def test_synthetic_internal_gate_exercises_interruption_loss_restore_and_alt_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, behavior: str
) -> None:
    module = _probe_module()
    env, auth = _fake_environment(tmp_path, behavior=behavior)
    monkeypatch.setenv("HOME", env["HOME"])
    monkeypatch.setenv("PATH", env["PATH"])
    monkeypatch.setenv("NATIVE_SESSION_PROBE_FAKE_CODEX", env["NATIVE_SESSION_PROBE_FAKE_CODEX"])
    monkeypatch.setenv("NATIVE_SESSION_PROBE_FAKE_BEHAVIOR", env["NATIVE_SESSION_PROBE_FAKE_BEHAVIOR"])
    output = tmp_path / "synthetic-tail"
    output.mkdir(mode=0o700)
    module._prepare("codex", "fake-model", output)
    provider_home = output / "provider-home/codex"
    provider_home.mkdir(mode=0o700)
    auth_copy = module._stage_auth("codex", provider_home)
    session = "synthetic-session"
    native = provider_home / "sessions/2026/10/13/rollout-probe.jsonl"
    _seed_codex_turns(native, session, turns=4)
    tracker = module.ProcessTracker()
    report: dict[str, object] = {
        "provider": "codex",
        "model": "fake-model",
        "synthetic_cli": True,
        "invocation_count": 4,
        "invocations": [],
        "gates": {"exclusive_continuation": {"status": "INCONCLUSIVE", "reason": "expected-position fencing is unqualified"}},
        "remaining_invocations": [],
    }
    if behavior == "marker-exit":
        original_invoke = module._invoke
        def already_exited(*args, **kwargs):
            invocation, row = original_invoke(*args, **kwargs)
            if invocation.ordinal == 5:
                invocation.process.wait(timeout=2)
            return invocation, row
        monkeypatch.setattr(module, "_invoke", already_exited)
    if behavior in {"unquiescent-recovery", "unquiescent-loss", "failed-loss"}:
        original_finish = module._finish_row
        def failed_finish(tracker, invocation, row, timeout):
            if invocation.ordinal == 7 and behavior == "failed-loss":
                raise RuntimeError("synthetic failed finish before quiescence")
            original_finish(tracker, invocation, row, timeout)
            if invocation.ordinal == (6 if behavior == "unquiescent-recovery" else 7):
                invocation.quiescent = False
                row["quiescent"] = False
        monkeypatch.setattr(module, "_finish_row", failed_finish)
    if behavior == "negative-recovery":
        original_evidence = module._evidence_for
        def inconclusive_recovery(provider, path, nonce, session, predecessor):
            if path.name == "native-06-recovery.jsonl":
                return module.NativeEvidence("INCONCLUSIVE", "synthetic missing exact recovery binding", session_id=session)
            return original_evidence(provider, path, nonce, session, predecessor)
        monkeypatch.setattr(module, "_evidence_for", inconclusive_recovery)

    try:
        run_tail = lambda: module._observe_recovery_tail(
            argparse.Namespace(provider="codex", model="fake-model", timeout_seconds=3.0),
            output,
            tracker,
            report,
            env["NATIVE_SESSION_PROBE_FAKE_CODEX"],
            True,
            provider_home,
            session,
            "turn-4",
        )
        if behavior in {"unquiescent-recovery", "unquiescent-loss", "failed-loss"}:
            with pytest.raises(RuntimeError):
                run_tail()
        else:
            run_tail()
    finally:
        tracker.close()
        auth_copy.unlink(missing_ok=True)

    rows = report["invocations"]
    expected_count = 6 if behavior == "unquiescent-recovery" else 7 if behavior in {"unquiescent-loss", "failed-loss"} else 8
    assert report["invocation_count"] == expected_count
    assert report["gates"]["exclusive_continuation"]["status"] == "INCONCLUSIVE"
    if behavior == "unquiescent-recovery":
        assert not (output / "evidence/session-before-delete.jsonl").exists()
        assert not (output / "provider-home/alternate-codex").exists()
        return
    if behavior in {"unquiescent-loss", "failed-loss"}:
        assert report["session_restore_pending"]["backup_file"]
        assert native.read_bytes() != (output / "evidence/session-before-delete.jsonl").read_bytes()
        return
    assert [row["ordinal"] for row in rows] == [5, 6, 7, 8]
    assert rows[0]["interruption_marker_observed"] is (behavior != "marker-exit")
    assert rows[0]["quiescent"] is True
    if behavior == "graceful-stop-zero":
        assert rows[0]["returncode"] == 0
        assert rows[0]["stop_requested_monotonic"] is not None
    assert rows[1]["status"] == ("INCONCLUSIVE" if behavior == "negative-recovery" else "OBSERVED")
    if behavior == "negative-recovery":
        assert rows[2]["predecessor_turn_id"] is None
        assert rows[3]["predecessor_turn_id"] is None
    assert rows[2]["deleted_session_before_launch"] is True
    assert rows[2]["restored_before_alternate_home"] is True
    assert rows[3]["original_native_files_visible_before_launch"] is False
    assert rows[3]["status"] == "INCONCLUSIVE"
    assert not list((output / "provider-home/alternate-codex").glob("**/auth.json"))
    if behavior == "fallback-home":
        assert rows[3]["original_home_changed"] is True
        assert report["gates"]["alternate_home"]["status"] == "NOT_OBSERVED"
    else:
        assert native.read_bytes() == (output / "evidence/session-before-delete.jsonl").read_bytes()
    if behavior == "replacement-file":
        assert rows[2]["replacement_or_fallback_seen"] is True
        assert rows[2]["native_attempts"][0]["native_file"].endswith("rollout-replacement.jsonl")
    assert auth.read_text(encoding="utf-8") == "synthetic-only-auth"


def test_original_recovery_admission_rejects_an_inconclusive_gate_without_mutating_it() -> None:
    module = _probe_module()
    gate = {"status": "INCONCLUSIVE", "reason": "atomic expected-position continuation remains unqualified"}
    report = {"gates": {"exclusive_continuation": dict(gate)}, "invocation_count": 4}
    with pytest.raises(module.ProbeStop):
        module._run_recovery_tail(None, None, None, report, "unused", True, None, "session", "head", gate)
    assert report == {"gates": {"exclusive_continuation": gate}, "invocation_count": 4}

