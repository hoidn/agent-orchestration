"""What `run` and `resume` print while a pipeline runs, when it fails and when it succeeds."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

import pytest

from tests.workflow_evaluated_host_input_helpers import build as build_host_input

REPO = Path(__file__).parents[1]

PIPELINE = '''\
(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule main) (export run)
  (defrecord Result (total Int) (first Int))
  (defworkflow run ((n Int)) -> Result
    (let* ((a (command-result step :argv ("python" "step.py" "one" n) :returns Int))
           (b (command-result step :argv ("python" "step.py" "two" a) :returns Int))
           (c (command-result step :argv ("python" "step.py" "three" b) :returns Int)))
      (record Result :total c :first a))))
'''

STEP = '''\
import json, os, sys
from pathlib import Path
name, value = sys.argv[1], int(sys.argv[2])
if Path("fail-" + name).exists():
    print("step " + name + " is broken", file=sys.stderr)
    sys.exit(3)
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(value + 1))
'''

RESULT_LINE = '{"first":2,"total":4}'
IDENTITIES = [f"workflow:main::run / {name}" for name in ("a", "b", "c")]


def env() -> dict[str, str]:
    return {
        **os.environ,
        "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
        "PYTHONPATH": str(REPO),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def cli(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-B", "-m", "orchestrator", *arguments], cwd=root, env=env(),
                          capture_output=True, text=True, check=False)


def shell(root: Path, command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, shell=True, cwd=root, env=env(), capture_output=True, text=True, check=False)


def write_pipeline(root: Path) -> None:
    (root / "main.orc").write_text(PIPELINE, encoding="utf-8")
    (root / "step.py").write_text(STEP, encoding="utf-8")
    (root / "commands.json").write_text(json.dumps(
        {"step": {"stable_command": ["python", "step.py"], "closure": ["step.py"]}}), encoding="utf-8")


def run_pipeline(root: Path, *flags: str) -> subprocess.CompletedProcess[str]:
    return cli(root, "run", "main.orc", "--command-boundaries-file", "commands.json", "--input", "n=1", *flags)


def printed(stderr: str, word: str) -> list[str]:
    """The lines whose first word is `word`, without that word."""
    return [line.split(None, 1)[1] for line in stderr.splitlines() if line.split(None, 1)[:1] == [word]]


def resume_command(stderr: str) -> str:
    (command,) = printed(stderr, "resume")
    return command


def effect_rows(stderr: str) -> list[tuple[str, str]]:
    rows = []
    for line in stderr.splitlines():
        word, _, rest = line.partition(" ")
        if word in {"start", "commit"}:
            rows.append((word, rest.strip().split("  ")[0]))
    return rows


def failed_run(root: Path) -> subprocess.CompletedProcess[str]:
    write_pipeline(root)
    (root / "fail-two").write_text("", encoding="utf-8")
    result = run_pipeline(root)
    assert result.returncode == 1, result.stderr
    return result


def test_run_prints_run_id_first_then_each_effect_and_the_result(tmp_path: Path) -> None:
    write_pipeline(tmp_path)

    result = run_pipeline(tmp_path)

    assert result.returncode == 0, result.stderr
    word, run_id, run_root = result.stderr.splitlines()[0].split()
    assert word == "run"
    assert Path(run_root) == tmp_path / ".orchestrate" / "runs" / run_id
    assert Path(run_root).is_dir()
    assert effect_rows(result.stderr) == [(kind, identity) for identity in IDENTITIES for kind in ("start", "commit")]
    assert result.stdout.splitlines()[-1] == RESULT_LINE


def test_failed_run_prints_the_step_its_stderr_and_the_resume_command(tmp_path: Path) -> None:
    result = failed_run(tmp_path)

    run_id = result.stderr.splitlines()[0].split()[1]
    assert printed(result.stderr, "failed")[0].startswith(IDENTITIES[1] + "  attempt 1  [command_exit_nonzero]")
    assert "| step two is broken" in result.stderr
    assert resume_command(result.stderr) == f"{shlex.quote(sys.executable)} -m orchestrator resume {run_id}"
    assert result.stdout == ""


def test_a_failed_step_shows_its_exception_line_first_when_a_long_message_pushes_it_out_of_the_tail(
    tmp_path: Path,
) -> None:
    write_pipeline(tmp_path)
    (tmp_path / "step.py").write_text(
        'raise ValueError("\\n".join(f"detail {i}" for i in range(15)))\n', encoding="utf-8")

    shown = printed(run_pipeline(tmp_path).stderr, "|")

    assert (len(shown), shown[0], shown[-1]) == (10, "ValueError: detail 0", "detail 14")


def test_a_failed_step_after_a_handled_traceback_ends_with_its_own_last_line(tmp_path: Path) -> None:
    write_pipeline(tmp_path)
    (tmp_path / "step.py").write_text(
        "import sys, traceback\n"
        "try:\n    {}['cache']\nexcept KeyError:\n    traceback.print_exc()\n"
        "for i in range(12):\n    print(f'build step {i}', file=sys.stderr)\n"
        "print('error: link failed (exit 1)', file=sys.stderr)\nsys.exit(1)\n", encoding="utf-8")

    shown = printed(run_pipeline(tmp_path).stderr, "|")

    assert shown[-1] == "error: link failed (exit 1)"


def test_quiet_run_prints_only_the_result(tmp_path: Path) -> None:
    write_pipeline(tmp_path)

    result = run_pipeline(tmp_path, "--quiet")

    assert (result.returncode, result.stderr, result.stdout) == (0, "", RESULT_LINE + "\n")


def test_resume_prints_only_the_effects_it_runs_and_the_result(tmp_path: Path) -> None:
    failed = failed_run(tmp_path)
    (tmp_path / "fail-two").unlink()

    resumed = shell(tmp_path, resume_command(failed.stderr))

    assert resumed.returncode == 0, resumed.stderr
    assert effect_rows(resumed.stderr) == [("start", IDENTITIES[1]), ("commit", IDENTITIES[1]),
                                           ("start", IDENTITIES[2]), ("commit", IDENTITIES[2])]
    assert resumed.stdout.splitlines()[-1] == RESULT_LINE


def test_resume_prints_the_run_line_first_and_the_rerun_note_after_its_start_line(tmp_path: Path) -> None:
    failed = failed_run(tmp_path)
    (tmp_path / "fail-two").unlink()

    lines = shell(tmp_path, resume_command(failed.stderr)).stderr.splitlines()

    assert lines[0].split()[0] == "run"
    rerun = next(index for index, line in enumerate(lines) if line.startswith("[effect_rerun]"))
    assert lines[rerun - 1].split() == ["start", *IDENTITIES[1].split(), "attempt", "2"]


def test_the_printed_resume_command_works_without_python_on_path(tmp_path: Path) -> None:
    failed = failed_run(tmp_path)
    (tmp_path / "fail-two").unlink()

    resumed = subprocess.run(resume_command(failed.stderr), shell=True, cwd=tmp_path, capture_output=True, text=True,
                             env={**env(), "PATH": str(tmp_path / "no-bin")}, check=False)

    assert (resumed.returncode, resumed.stdout.splitlines()[-1:]) == (0, [RESULT_LINE]), resumed.stderr


def test_resume_accepts_quiet(tmp_path: Path) -> None:
    failed = failed_run(tmp_path)
    (tmp_path / "fail-two").unlink()

    resumed = shell(tmp_path, resume_command(failed.stderr) + " --quiet")

    assert (resumed.returncode, resumed.stderr, resumed.stdout) == (0, "", RESULT_LINE + "\n")


def test_dry_run_reports_what_it_checked(tmp_path: Path) -> None:
    write_pipeline(tmp_path)

    result = run_pipeline(tmp_path, "--dry-run")

    assert (result.returncode, result.stdout) == (0, "")
    assert result.stderr.splitlines() == ["checked workflow:main::run  3 effect sites"]


def test_suspended_run_prints_the_input_command_and_no_result(tmp_path: Path) -> None:
    build_host_input(tmp_path)

    result = cli(tmp_path, "run", "host/entry.orc", "--source-root", ".", "--command-boundaries-file", "commands.json")

    assert (result.returncode, result.stdout) == (0, "")
    (waiting,) = printed(result.stderr, "waiting")
    identity, command = waiting.split("  ")
    assert identity.startswith("workflow:host/entry::run")
    request = shell(tmp_path, command)
    assert request.returncode == 0, request.stderr
    assert "request_id" in json.loads(request.stdout)


WARNED = '''\
(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule warn) (export run)
  (defunion Outcome (A) (B))
  (defworkflow run () -> Outcome
    (command-result emit :argv ("python" "emit.py") :returns Outcome)))
'''

EMIT = '''\
import json, os
from pathlib import Path
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps({"variant": "A"}))
'''


def test_run_shows_compile_warnings_unless_quiet(tmp_path: Path) -> None:
    (tmp_path / "warn.orc").write_text(WARNED, encoding="utf-8")
    (tmp_path / "emit.py").write_text(EMIT, encoding="utf-8")
    (tmp_path / "commands.json").write_text(json.dumps(
        {"emit": {"stable_command": ["python", "emit.py"], "closure": ["emit.py"]}}), encoding="utf-8")
    arguments = ("run", "warn.orc", "--command-boundaries-file", "commands.json")

    shown, quiet = cli(tmp_path, *arguments), cli(tmp_path, *arguments, "--quiet")

    assert (shown.returncode, quiet.returncode) == (0, 0), shown.stderr + quiet.stderr
    assert "warn.orc:4:3: [variant_output_without_variant_specific_fields]" in shown.stderr
    assert "variant_output_without_variant_specific_fields" not in quiet.stderr


def test_failed_step_prints_no_contract_pointer(tmp_path: Path) -> None:
    result = failed_run(tmp_path)

    assert "specs/cli.md" not in result.stderr


LOOP_WITHOUT_EXHAUSTED = '''\
(workflow-lisp (:language "0.1") (:target-dsl "2.39")
  (defmodule counter) (export run)
  (defworkflow run () -> Int
    (loop/recur :max 3 :state 0 (fn (n) (if (>= n 2) (done n) (continue (+ n 1)))))))
'''


def test_run_shows_the_loop_exhaustion_warning_unless_quiet(tmp_path: Path) -> None:
    (tmp_path / "counter.orc").write_text(LOOP_WITHOUT_EXHAUSTED, encoding="utf-8")

    shown, quiet = cli(tmp_path, "run", "counter.orc"), cli(tmp_path, "run", "counter.orc", "--quiet")

    assert (shown.returncode, quiet.returncode) == (0, 0), shown.stderr + quiet.stderr
    assert "counter.orc:4:5: [loop_missing_on_exhausted]" in shown.stderr
    assert (quiet.stderr, quiet.stdout) == ("", "2\n")


def test_a_broken_stderr_pipe_keeps_exit_zero_and_the_result(tmp_path: Path) -> None:
    write_pipeline(tmp_path)
    process = subprocess.Popen(
        [sys.executable, "-B", "-m", "orchestrator", "run", "main.orc", "--command-boundaries-file", "commands.json",
         "--input", "n=1"], cwd=tmp_path, env=env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    process.stderr.close()

    stdout, _ = process.communicate(timeout=120)

    assert (process.returncode, stdout.splitlines()[-1:]) == (0, [RESULT_LINE])


def test_a_run_started_with_stderr_closed_runs_and_prints_the_result(tmp_path: Path) -> None:
    write_pipeline(tmp_path)

    result = shell(tmp_path, f"{sys.executable} -B -m orchestrator run main.orc --command-boundaries-file commands.json"
                             " --input n=1 2>&-")

    assert (result.returncode, result.stdout) == (0, RESULT_LINE + "\n")


SDK_RUN = '''\
from orchestrator.py import run
result = run("workflows/examples/python_command_loop.py", entry_workflow="run",
             command_boundaries_file="workflows/examples/python_command_loop.commands.json", inputs={"limit": 1})
assert result.exit_code == 0, result
'''


def test_an_sdk_run_prints_nothing_to_stdout(tmp_path: Path) -> None:
    import shutil
    examples = tmp_path / "workflows" / "examples"
    examples.mkdir(parents=True)
    for name in ("python_command_loop.py", "python_command_loop_tool.py", "python_command_loop.commands.json"):
        shutil.copyfile(REPO / "workflows" / "examples" / name, examples / name)

    result = subprocess.run([sys.executable, "-B", "-c", SDK_RUN], cwd=tmp_path, env=env(),
                            capture_output=True, text=True, check=False)

    assert (result.returncode, result.stdout) == (0, ""), result.stderr
    assert printed(result.stderr, "run") == []


PROVIDER_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule main) (export run)
  (defrecord Result (ok Bool))
  (defworkflow run ((message String)) -> Result
    (provider-result providers.review :prompt prompts.base
      :inputs (message) :model "chosen-model" :effort "low" :returns Result)))'''

UNTERMINATED_SHIM = r'''import os, sys
from pathlib import Path
sys.stdin.buffer.read()
sys.stdout.write("partial provider output without a newline"); sys.stdout.flush()
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text('{"ok":true}')
'''


def test_the_result_starts_its_own_line_after_unterminated_provider_output(tmp_path: Path) -> None:
    from tests.test_workflow_evaluated_providers import _fixture
    source, providers, prompts, _ = _fixture(tmp_path, PROVIDER_SOURCE)
    (tmp_path / "bin" / "codex").write_text(f"#!{sys.executable}\n" + UNTERMINATED_SHIM, encoding="utf-8")
    run_env = {**env(), "PATH": str(tmp_path / "bin") + os.pathsep + env()["PATH"]}

    result = subprocess.run(
        [sys.executable, "-B", "-m", "orchestrator", "run", str(source), "--provider-externs-file", str(providers),
         "--prompt-externs-file", str(prompts), "--input", "message=x"],
        cwd=tmp_path, env=run_env, capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr
    assert "partial provider output without a newline" in result.stdout
    assert result.stdout.splitlines()[-1] == '{"ok":true}'


def test_a_failed_quiet_run_still_prints_its_resume_command(tmp_path: Path) -> None:
    write_pipeline(tmp_path)
    (tmp_path / "fail-two").write_text("", encoding="utf-8")

    result = run_pipeline(tmp_path, "--quiet")

    assert result.returncode == 1
    (command,) = printed(result.stderr, "resume")
    assert shell(tmp_path, command).returncode == 1  # still failing, but the command names the run


SLOW_STEP = STEP.replace('if Path("fail-" + name).exists():',
                         'if Path("slow-" + name).exists():\n    Path("started-" + name).write_text("")\n'
                         '    import time; time.sleep(60)\nif Path("fail-" + name).exists():')


@pytest.mark.parametrize("flags", [(), ("--quiet",)])
def test_ctrl_c_during_a_step_prints_the_resume_command(tmp_path: Path, flags: tuple[str, ...]) -> None:
    import signal
    import time
    write_pipeline(tmp_path)
    (tmp_path / "step.py").write_text(SLOW_STEP, encoding="utf-8")
    (tmp_path / "slow-two").write_text("", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "-B", "-m", "orchestrator", "run", "main.orc", "--command-boundaries-file", "commands.json",
         "--input", "n=1", *flags], cwd=tmp_path, env=env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 60
    while not (tmp_path / "started-two").exists():
        assert time.monotonic() < deadline and process.poll() is None
        time.sleep(0.05)

    process.send_signal(signal.SIGINT)
    _, stderr = process.communicate(timeout=60)

    assert process.returncode != 0
    (command,) = printed(stderr, "resume")
    (tmp_path / "slow-two").unlink()
    resumed = shell(tmp_path, command)
    assert resumed.returncode == 0, resumed.stderr
    assert resumed.stdout.splitlines()[-1] == RESULT_LINE


ECHO = '''\
(workflow-lisp (:language "0.1") (:target-dsl "2.39")
  (defmodule echo) (export run)
  (defworkflow run ((text String)) -> String text))
'''


def test_a_result_the_terminal_cannot_encode_is_printed_escaped(tmp_path: Path) -> None:
    (tmp_path / "echo.orc").write_text(ECHO, encoding="utf-8")

    result = subprocess.run([sys.executable, "-B", "-m", "orchestrator", "run", "echo.orc", "--input", "text=café",
                             "--quiet"], cwd=tmp_path, env={**env(), "PYTHONIOENCODING": "ascii"},
                            capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == "café"


def test_a_write_error_on_a_live_descriptor_leaves_the_descriptor_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    import stat
    from orchestrator.cli.progress import say
    read_end, write_end = os.pipe()
    os.set_blocking(write_end, False)
    try:
        while True:
            os.write(write_end, b"x" * 65536)
    except BlockingIOError:
        pass  # the pipe is full: the next write fails, but the descriptor is alive
    stream = open(write_end, "w", closefd=False)
    monkeypatch.setattr(sys, "stderr", stream)

    say("a line that does not fit")

    assert stat.S_ISFIFO(os.fstat(write_end).st_mode)
    os.set_blocking(read_end, False)
    while True:  # drain the pipe so the stream can be flushed and closed
        try:
            os.read(read_end, 65536)
        except BlockingIOError:
            break
    stream.close()
    os.close(write_end)
    os.close(read_end)
