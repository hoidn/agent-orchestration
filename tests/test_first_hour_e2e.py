"""The first hour, end to end, with `orchestrator` installed in a fresh environment outside the checkout.

`test_tutorial_blocks_run_as_written` executes docs/tutorial_first_pipeline.md as written: an HTML comment before
a fenced block marks it. `<!-- file: NAME -->` writes the block to NAME; `<!-- run -->` runs the block's `$ `
lines and expects exit 0; `<!-- run: exit N -->` expects N from the last one; `<!-- run: printed -->` says the
block's commands are the ones the previous block printed (its `resume` line or its indented recovery commands),
with `<run id>` for the run id, and runs the printed ones. The headline exit test uses only what the CLI printed.

The environment (built once per module): a copy of `orchestrator/`, `pyproject.toml` and `LICENSE.md` installed
non-editable into a virtual environment that sees this interpreter's packages, so no network is needed;
commands run with its `bin` first on PATH, PYTHONPATH unset, in an empty directory.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest
from tests.agent_session_shims import closed_path

REPO = Path(__file__).resolve().parents[1]
TUTORIAL = REPO / "docs" / "tutorial_first_pipeline.md"
MARK = re.compile(r"<!-- (?:file: (?P<file>\S+)|run(?:: (?P<options>[^>]+?))?) -->")
RUN_ID = "<run id>"
TIMEOUT = 120


@dataclass(frozen=True)
class Block:
    file: str | None
    options: tuple[str, ...]
    body: str

    @property
    def commands(self) -> list[str]:
        return [line[2:] for line in self.body.splitlines() if line.startswith("$ ")]

    @property
    def shown(self) -> list[str]:
        return [line for line in self.body.splitlines() if not line.startswith("$ ")]

    @property
    def exit_code(self) -> int:
        codes = [int(option.split()[1]) for option in self.options if option.startswith("exit ")]
        return codes[0] if codes else 0


def tutorial_blocks(text: str) -> list[Block]:
    """The marked fenced blocks, in document order."""
    lines = text.splitlines()
    blocks = []
    for index, line in enumerate(lines):
        match = MARK.fullmatch(line.strip())
        if match is None:
            continue
        fence = re.match(r"`{3,}", lines[index + 1])
        assert fence, f"tutorial line {index + 2}: a marker must be followed by a fenced block"
        end = lines.index(fence.group(), index + 2)
        options = tuple(option.strip() for option in (match["options"] or "").split(",") if option.strip())
        blocks.append(Block(match["file"], options, "\n".join(lines[index + 2:end]) + "\n"))
    return blocks


@pytest.fixture(scope="module")
def installed(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    """The environment of every command: the fresh install's `bin` first on PATH and no PYTHONPATH."""
    root = tmp_path_factory.mktemp("first-hour-env")
    assert not root.resolve().is_relative_to(REPO)
    source, venv = root / "src", root / "venv"
    shutil.copytree(REPO / "orchestrator", source / "orchestrator", ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("pyproject.toml", "LICENSE.md"):
        shutil.copyfile(REPO / name, source / name)
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    subprocess.run([sys.executable, "-m", "venv", "--system-site-packages", str(venv)], check=True, timeout=TIMEOUT)
    subprocess.run([str(venv / "bin" / "python"), "-m", "pip", "install", "--quiet", "--no-index", "--no-deps",
                    "--no-build-isolation", str(source)], check=True, env=env, cwd=root, timeout=TIMEOUT)
    env["PATH"] = closed_path(venv / "bin")
    located = subprocess.run(["python", "-c", "import orchestrator; print(orchestrator.__file__)"], cwd=root,
                             env=env, capture_output=True, text=True, check=True, timeout=TIMEOUT).stdout.strip()
    assert Path(located).resolve().is_relative_to(venv.resolve()), located
    return env


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    assert not tmp_path.resolve().is_relative_to(REPO)
    return tmp_path


def sh(command: str, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["sh", "-c", command], cwd=cwd, env=env, capture_output=True, text=True, timeout=TIMEOUT)


def rows(stderr: str, word: str) -> list[str]:
    """What follows `word` on the lines it starts, after any indent (`run`, `start`, `failed`, `stderr:`, `|`)."""
    lines = [line.lstrip() for line in stderr.splitlines()]
    return [line[len(word):].strip() for line in lines if line.split(" ", 1)[0] == word]


def identities(stderr: str, word: str) -> set[str]:
    return {row.split("  attempt ")[0] for row in rows(stderr, word)}


def printed_commands(stderr: str) -> list[str]:
    """The commands a step printed: its `resume` line, or the indented commands of its recovery lines."""
    return rows(stderr, "resume") + [line.strip() for line in stderr.splitlines()
                                     if line.startswith("    orchestrator ")]


@dataclass
class Step:
    block: Block
    returncode: int
    stdout: str
    stderr: str


def run_block(block: Block, previous: Step | None, run_id: str | None, cwd: Path, env: dict[str, str]) -> Step:
    commands = [command.replace(RUN_ID, run_id or RUN_ID) for command in block.commands]
    if "printed" in block.options:
        assert previous is not None and commands == printed_commands(previous.stderr), (commands, previous)
    results = [sh(command, cwd, env) for command in commands]
    for command, result in zip(commands[:-1], results):
        assert result.returncode == 0, (command, result.stderr)
    last = results[-1]
    return Step(block, last.returncode, last.stdout, "".join(result.stderr for result in results))


def check_step(step: Step, previous: Step | None) -> None:
    assert step.returncode == step.block.exit_code, (step.block.commands, step.stderr)
    if step.returncode == 1:
        assert rows(step.stderr, "failed") and rows(step.stderr, "resume"), step.stderr
    if "printed" in step.block.options and previous is not None and previous.returncode == 1:
        assert not identities(step.stderr, "start") & identities(previous.stderr, "commit"), step.stderr
    if step.block.shown and step.block.shown[-1].startswith("{"):
        assert step.stdout.splitlines()[-1:] == step.block.shown[-1:], step.stdout


def test_tutorial_blocks_run_as_written(installed: dict[str, str], workspace: Path) -> None:
    previous, run_id = None, None
    for block in tutorial_blocks(TUTORIAL.read_text(encoding="utf-8")):
        if block.file is not None:
            (workspace / block.file).write_text(block.body, encoding="utf-8")
            continue
        step = run_block(block, previous, run_id, workspace, installed)
        check_step(step, previous)
        run_id = next((row.split()[0] for row in reversed(rows(step.stderr, "run"))), run_id)
        previous = step

    assert previous is not None and previous.block.shown[-1].startswith("{")  # the final step shows its result


def test_failed_run_is_diagnosed_and_resumed_from_terminal_output(installed: dict[str, str], workspace: Path) -> None:
    files = {}
    for block in tutorial_blocks(TUTORIAL.read_text(encoding="utf-8")):
        if block.file is not None:
            files.setdefault(block.file, block.body)
    for name, body in files.items():
        if name != "notes.txt":
            (workspace / name).write_text(body, encoding="utf-8")

    failed = sh("orchestrator run grow.orc --input file=notes.txt --input target=5", workspace, installed)

    assert failed.returncode == 1, failed.stderr
    (failing,) = rows(failed.stderr, "failed")
    assert failing.startswith("workflow:grow::run / ")
    (stderr_file,) = rows(failed.stderr, "stderr:")
    assert "notes.txt" in Path(stderr_file).read_text(encoding="utf-8")
    assert any("notes.txt" in line for line in rows(failed.stderr, "|"))
    (resume,) = rows(failed.stderr, "resume")
    (workspace / "notes.txt").write_text(files["notes.txt"], encoding="utf-8")
    resumed = sh(resume, workspace, installed)
    assert resumed.returncode == 0, resumed.stderr
    assert resumed.stdout.splitlines()[-1] == '{"pads":2,"reached":true}'
