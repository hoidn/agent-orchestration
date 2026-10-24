"""Capped calls cannot dispatch descendants; every backend here is scripted."""

import json
import shlex
import sys
from pathlib import Path

import pytest

from tests.experiments.compare_harness_support import call, skip_without_sandbox, start, world  # noqa: F401
from tests.experiments.test_compare_model_cap import DISABLED, SOL, SONNET, TERRA

skip_without_sandbox()


def scripted_backends(world):
    log = "/tmp/backend-starts.jsonl"
    program = f'''#!{sys.executable}
import json, os, subprocess, sys
with open({str(log)!r}, "a") as stream:
    stream.write(json.dumps({{"name": os.path.basename(sys.argv[0]), "argv": sys.argv[1:],
        "state": os.environ.get("ORC_SINGLE_CALL_CLI_STATE"),
        "cap": os.environ.get("COMPARE_MAX_CALLS")}}) + "\\n")
script = sys.stdin.read()
sys.exit(subprocess.run(["/bin/bash", "-c", script]).returncode if script else 0)
'''
    for name in ("codex", "claude"):
        (world.fakebin / name).write_text(program)
        (world.fakebin / name).chmod(0o755)
    return Path(log).name


@pytest.mark.parametrize("cap", ["1", "01"])
@pytest.mark.parametrize("model,effort", [("gpt-5.6-luna", "high"), (SOL, "low"), (SOL, "high")])
def test_cap_one_refuses_same_model_shell_reentry_before_backend(world, monkeypatch, cap, model, effort):
    scripted_backends(world)
    monkeypatch.setenv("COMPARE_MAX_CALLS", cap)
    monkeypatch.setenv("COMPARE_CODEX_MODELS", model)
    _, record = start(world, "direct_task")
    log = Path(record["tree"]) / "tmp/backend-starts.jsonl"
    nested = (["codex", "--model", model, "exec", "-c", f"model_reasoning_effort={effort}", "-"],
              ["claude", "--model", SONNET, "-p"],
              ["codex", "--model", model, "--help"], ["codex", "--model", model, "--version"],
              ["claude", "--model", SONNET, "--help"], ["claude", "--model", SONNET, "--version"])
    script = "\n".join(f"{shlex.join(argv)} </dev/null; echo nested-{index}-exit=$?"
                       for index, argv in enumerate(nested))
    args = ["--model", model, "exec", "-c", f"model_reasoning_effort={effort}", "-"]
    done = call(world, record, script, binary="codex", args=args)
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == [f"nested-{index}-exit=2" for index in range(len(nested))]
    assert done.stderr.count("nested provider CLI is forbidden") == len(nested)
    assert [json.loads(line) for line in log.read_text().splitlines()] == [
        {"name": "codex", "argv": [*args[:3], *DISABLED, *args[3:]],
         "state": "dispatched", "cap": None}]
    assert [p.name for p in (Path(record["records"]) / "calls").iterdir()] == ["1"]


def test_uncapped_preserves_generic_nested_claude(world, monkeypatch):
    scripted_backends(world)
    monkeypatch.setenv("ORC_SINGLE_CALL_CLI_STATE", "dispatched")
    monkeypatch.delenv("COMPARE_MAX_CALLS", raising=False)
    _, record = start(world, "direct_task")
    log = Path(record["tree"]) / "tmp/backend-starts.jsonl"
    done = call(world, record, f"claude --model {SONNET} -p </dev/null", binary="codex")
    assert done.returncode == 0, done.stderr
    starts = [json.loads(line) for line in log.read_text().splitlines()]
    assert [row["name"] for row in starts] == ["codex", "claude"]
    assert all(row["state"] is None and row["cap"] is None for row in starts)


def test_cap_three_allows_three_outer_calls_and_blocks_descendants_and_fourth(world, monkeypatch):
    scripted_backends(world)
    monkeypatch.setenv("COMPARE_MAX_CALLS", "3")
    monkeypatch.setenv("COMPARE_CODEX_MODELS", SOL)
    _, record = start(world, "direct_task")
    log = Path(record["tree"]) / "tmp/backend-starts.jsonl"
    nested = (["codex", "--model", SOL, "exec", "-c", "model_reasoning_effort=high", "-"],
              ["claude", "--model", SONNET, "-p"],
              ["codex", "--model", SOL, "--help"], ["codex", "--model", SOL, "--version"],
              ["claude", "--model", SONNET, "--help"], ["claude", "--model", SONNET, "--version"])
    script = "\n".join(f"{shlex.join(argv)} </dev/null; echo nested-{index}-exit=$?"
                        for index, argv in enumerate(nested))
    args = ["--model", SOL, "exec", "-c", "model_reasoning_effort=high", "-"]
    for outer in range(1, 4):
        done = call(world, record, script, binary="codex", args=args)
        assert done.returncode == 0, done.stderr
        assert done.stdout.splitlines() == [f"nested-{index}-exit=2" for index in range(len(nested))]
        assert done.stderr.count("nested provider CLI is forbidden") == len(nested)
        assert (Path(record["records"]) / f"calls/{outer}/provider.txt").read_text() == "codex\n"

    fourth = call(world, record, "echo should-not-run", binary="codex", args=args)
    assert fourth.returncode == 75
    assert "should-not-run" not in fourth.stdout
    assert "COMPARE_MAX_CALLS=3" in fourth.stderr
    starts = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(starts) == 3
    assert all(row["state"] == "dispatched" and row["cap"] is None for row in starts)
    assert (Path(record["records"]) / "calls/4/stderr.txt").read_text() == fourth.stderr


def test_independent_recorded_outer_calls_reset_inherited_state(world, monkeypatch):
    scripted_backends(world)
    monkeypatch.setenv("COMPARE_MAX_CALLS", "1")
    monkeypatch.setenv("ORC_SINGLE_CALL_CLI_STATE", "dispatched")
    event_logs = []
    for name in ("first", "second"):
        _, record = start(world, "direct_task", root=world.outside / name)
        log = Path(record["tree"]) / "tmp/backend-starts.jsonl"
        event_logs.append(log)
        done = call(world, record, "true", binary="codex")
        assert done.returncode == 0, done.stderr
        assert [p.name for p in (Path(record["records"]) / "calls").iterdir()] == ["1"]
    starts = [json.loads(line) for log in event_logs for line in log.read_text().splitlines()]
    assert len(starts) == 2 and all(row["state"] == "dispatched" for row in starts)


@pytest.mark.parametrize("cap", ["1", "01", "3"])
@pytest.mark.parametrize("shell_mode", ["-ic", "-lic"])
def test_positive_cap_survives_real_tmux_and_interactive_shells(world, monkeypatch, cap, shell_mode):
    scripted_backends(world)
    monkeypatch.setenv("COMPARE_MAX_CALLS", cap)
    monkeypatch.setenv("COMPARE_CODEX_MODELS", SOL)
    monkeypatch.setenv("COMPARE_CLAUDE_MODELS", "")
    hidden = world.outside / "private-evidence"
    hidden.mkdir()
    (hidden / "secret").write_text("private")
    _, record = start(world, "direct_task")
    log = Path(record["tree"]) / "tmp/backend-starts.jsonl"
    home = Path(record["sandbox"]["home"])
    # A persisted controller startup file stays outside the prepared unit and cannot drop the guard.
    (home / ".bashrc").write_text(f"export PATH={shlex.quote(str(world.fakebin))}:/usr/bin:/bin\n")
    (home / ".bash_profile").write_text('. "$HOME/.bashrc"\n')
    outputs = Path(record["tree"]) / "tmp/tmux-outputs"
    outputs.mkdir()
    socket = "/tmp/single-call.sock"
    tmux = f"tmux -S {socket}"
    nested = (["codex", "-m", SOL, "exec", "--dangerously-bypass-approvals-and-sandbox", "-"],
              ["claude", "--model", SONNET, "-p"], ["codex", "--model", SOL, "--help"])
    lines = [f"trap '{tmux} kill-server 2>/dev/null || true' EXIT",
             f"test ! -e {shlex.quote(str(hidden / 'secret'))} || exit 99",
             "cat > /tmp/nested-task.txt <<'TASK'", "Harmless scripted provider input.", "TASK",
             f"{tmux} new-session -d -s keeper 'sleep 30'"]
    for index, argv in enumerate(nested):
        worker = (f"{shlex.join(argv)} < /tmp/nested-task.txt "
                  f"> {outputs / f'{index}.out'} 2> {outputs / f'{index}.err'}; "
                  f"printf '%s' $? > {outputs / f'{index}.exit'}; {tmux} wait-for -S done-{index}")
        lines.append(f"{tmux} new-session -d -s worker-{index} {shlex.quote(worker)}")
    lines.extend(f"timeout 10 {tmux} wait-for done-{index} || exit 98" for index in range(len(nested)))
    script = f"/bin/bash {shell_mode} {shlex.quote(chr(10).join(lines))}"
    args = ["--model", SOL, "exec", "-c", "model_reasoning_effort=low", "-"]
    done = call(world, record, script, binary="codex", args=args)
    assert done.returncode == 0, done.stdout + done.stderr
    for index in range(len(nested)):
        assert (outputs / f"{index}.exit").read_text() == "2"
        assert "nested provider CLI is forbidden" in (outputs / f"{index}.err").read_text()
        assert (outputs / f"{index}.out").read_text() == ""
    starts = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(starts) == 1
    assert starts[0]["argv"] == [*args[:3], *DISABLED, *args[3:]]
    assert starts[0]["state"] == "dispatched" and starts[0]["cap"] is None
    assert (hidden / "secret").read_text() == "private"
