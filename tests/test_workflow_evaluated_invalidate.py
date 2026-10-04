from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo


PROGRAM = '''\
(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule invalidate_public) (export run)
  (defworkflow run () -> Int
    (let* ((prefix (command-result prefix :argv ("python" "prefix.py") :returns Int))
           (writer (command-result writer :argv ("python" "writer.py") :returns Int))
           (reader (command-result reader :argv ("python" "reader.py") :returns Int)))
      reader)))
'''


def _cli(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).parents[1]),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return subprocess.run(
        [sys.executable, "-m", "orchestrator", *arguments],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _fixture(root: Path, value: int) -> tuple[Path, Path]:
    source = root / "invalidate_public.orc"
    source.write_text(PROGRAM, encoding="utf-8")
    scripts = {
        "prefix.py": (
            'from pathlib import Path\n'
            'Path("dispatches.txt").open("a", encoding="utf-8").write("prefix\\n")\n'
            'import os\nPath(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("1", encoding="utf-8")\n'
        ),
        "writer.py": (
            'from pathlib import Path\nimport os\n'
            'Path("dispatches.txt").open("a", encoding="utf-8").write("writer\\n")\n'
            f'Path("handoff.txt").write_text("{value}", encoding="utf-8")\n'
            f'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("{value}", encoding="utf-8")\n'
        ),
        "reader.py": (
            'from pathlib import Path\nimport os\n'
            'Path("dispatches.txt").open("a", encoding="utf-8").write("reader\\n")\n'
            'value = Path("handoff.txt").read_text(encoding="utf-8")\n'
            'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(value, encoding="utf-8")\n'
        ),
    }
    for filename, contents in scripts.items():
        (root / filename).write_text(contents, encoding="utf-8")
    boundaries = root / "commands.json"
    boundaries.write_text(
        json.dumps({
            name: {"stable_command": ["python", f"{name}.py"], "closure": [f"{name}.py"]}
            for name in ("prefix", "writer", "reader")
        }),
        encoding="utf-8",
    )
    return source, boundaries


def _memo(run_root: Path):
    authority = load_run_authority(run_root)
    snapshot = read_memo(run_root / "memo.jsonl", site_classes(authority.program))
    return [entry.data for entry in snapshot.entries], snapshot


def _tree_node(path: Path) -> tuple[str, bytes | None]:
    if path.is_symlink():
        return "symlink", os.fsencode(path.readlink())
    if path.is_dir():
        return "directory", None
    if path.is_file():
        return "file", path.read_bytes()
    return "other", str(path.lstat().st_mode).encode("ascii")


def _tree_bytes(root: Path, *, omit_memo: Path | None = None) -> dict[str, tuple[str, bytes | None]]:
    if not root.exists() and not root.is_symlink():
        return {}
    entries = {"<root>": _tree_node(root)}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path == omit_memo:
            continue
        entries[relative.as_posix()] = _tree_node(path)
    return entries


def _completed_run(root: Path, *, value: int = 20, state_dir: Path | None = None) -> Path:
    source, boundaries = _fixture(root, value)
    arguments = ["run", str(source), "--command-boundaries-file", str(boundaries)]
    if state_dir is not None:
        arguments.extend(["--state-dir", str(state_dir)])
    result = _cli(root, *arguments)
    assert result.returncode == 0, result.stderr
    runs_root = state_dir if state_dir is not None else root / ".orchestrate" / "runs"
    (run_root,) = runs_root.iterdir()
    return run_root


def _first_commit(run_root: Path):
    _rows, snapshot = _memo(run_root)
    return next(entry for entry in snapshot.entries if entry.data["record"] == "committed")


def _pab_baseline(root: Path) -> dict[str, object]:
    source, boundaries = _fixture(root, 20)
    run = _cli(root, "run", str(source), "--command-boundaries-file", str(boundaries))
    assert run.returncode == 0, run.stderr
    (run_root,) = (root / ".orchestrate" / "runs").iterdir()
    rows, snapshot = _memo(run_root)
    commits = [entry for entry in snapshot.entries if entry.data["record"] == "committed"]
    assert [entry.data["depends_on"] for entry in commits] == [[], [], []]
    assert [entry.data["value"] for entry in commits] == [1, 20, 20]
    assert commits[2].offset > commits[1].offset
    attempts = {
        path: path.read_bytes()
        for path in (run_root / "effects").glob("*/attempt-1/*")
        if path.is_file()
    }
    return {
        "root": root,
        "run_root": run_root,
        "rows": rows,
        "commits": commits,
        "identity": commits[1].data["identity"],
        "attempts": attempts,
        "initial_tree": _tree_bytes(root / ".orchestrate"),
        "dispatches": (root / "dispatches.txt").read_text(encoding="utf-8"),
    }


def _refuse_changed_writer_readonly(case: dict[str, object]) -> None:
    root = case["root"]
    run_root = case["run_root"]
    writer = root / "writer.py"
    writer.write_text(writer.read_text(encoding="utf-8").replace('"20"', '"21"'), encoding="utf-8")
    memo_before = (run_root / "memo.jsonl").read_bytes()
    result = _cli(root, "resume", run_root.name)
    assert result.returncode == 2
    assert "effect_input_diverged" in result.stderr
    assert (run_root / "memo.jsonl").read_bytes() == memo_before
    assert _tree_bytes(root / ".orchestrate") == case["initial_tree"]
    assert (root / "dispatches.txt").read_text(encoding="utf-8") == case["dispatches"]


def _append_first_range(case: dict[str, object]) -> dict[str, object]:
    root, run_root = case["root"], case["run_root"]
    commits, identity = case["commits"], case["identity"]
    before = _tree_bytes(root / ".orchestrate", omit_memo=run_root / "memo.jsonl")
    result = _cli(root, "invalidate", run_root.name, identity)
    assert result.returncode == 0, result.stderr
    row = json.loads(result.stdout)
    assert row["record"] == "invalidated"
    assert row["from_commit"] == commits[1].offset
    rows, snapshot = _memo(run_root)
    assert len(rows) == len(case["rows"]) + 1
    assert rows[-1] == row
    assert set(snapshot.active_commits) == {commits[0].data["identity"]}
    assert _tree_bytes(root / ".orchestrate", omit_memo=run_root / "memo.jsonl") == before
    assert (root / "dispatches.txt").read_text(encoding="utf-8") == case["dispatches"]
    assert {path: path.read_bytes() for path in case["attempts"]} == case["attempts"]
    return {"row": row, "memo": (run_root / "memo.jsonl").read_bytes()}


def _reject_repeat_before_retry(case: dict[str, object], first_range: dict[str, object]) -> None:
    result = _cli(case["root"], "invalidate", case["run_root"].name, case["identity"])
    assert result.returncode == 2
    assert "invalidate_not_committed" in result.stderr
    assert (case["run_root"] / "memo.jsonl").read_bytes() == first_range["memo"]


def _resume_first_retry(case: dict[str, object]):
    root, run_root = case["root"], case["run_root"]
    commits, identity = case["commits"], case["identity"]
    result = _cli(root, "resume", run_root.name)
    assert result.returncode == 0, result.stderr
    rows, snapshot = _memo(run_root)
    starts = [row for row in rows if row["record"] == "started"]
    old_ids = [commits[0].data["identity"], identity, commits[2].data["identity"]]
    assert [row["identity"] for row in starts] == old_ids + old_ids[1:]
    assert [row["attempt"] for row in starts] == [1, 1, 1, 2, 2]
    assert set(snapshot.active_commits) == {entry.data["identity"] for entry in commits}
    assert snapshot.terminal is not None and snapshot.terminal.data["value"] == 21
    assert (root / "dispatches.txt").read_text(encoding="utf-8").splitlines() == [
        "prefix", "writer", "reader", "writer", "reader"
    ]
    assert {path: path.read_bytes() for path in case["attempts"]} == case["attempts"]
    assert (root / "handoff.txt").read_bytes() == b"21"
    return snapshot


def _invalidate_future_range(case: dict[str, object], previous) -> None:
    root, run_root = case["root"], case["run_root"]
    identity = case["identity"]
    result = _cli(root, "invalidate", run_root.name, identity)
    assert result.returncode == 0, result.stderr
    row = json.loads(result.stdout)
    assert row["from_commit"] == previous.active_commits[identity].offset
    rows, snapshot = _memo(run_root)
    invalidations = [item for item in rows if item["record"] == "invalidated"]
    assert invalidations == [case["first_range"], row]
    assert set(snapshot.active_commits) == {case["commits"][0].data["identity"]}
    case["second_range"] = row


def _resume_future_range(case: dict[str, object]):
    root, run_root = case["root"], case["run_root"]
    result = _cli(root, "resume", run_root.name)
    assert result.returncode == 0, result.stderr
    rows, snapshot = _memo(run_root)
    starts = [row for row in rows if row["record"] == "started"]
    assert [row["attempt"] for row in starts] == [1, 1, 1, 2, 2, 3, 3]
    assert snapshot.terminal is not None and snapshot.terminal.data["value"] == 21
    assert (root / "dispatches.txt").read_text(encoding="utf-8").splitlines() == [
        "prefix", "writer", "reader", "writer", "reader", "writer", "reader"
    ]
    return snapshot


def _fresh_file_handoff(root: Path):
    fresh_root = root / "fresh"
    fresh_root.mkdir()
    source, boundaries = _fixture(fresh_root, 21)
    result = _cli(fresh_root, "run", str(source), "--command-boundaries-file", str(boundaries))
    assert result.returncode == 0, result.stderr
    (run_root,) = (fresh_root / ".orchestrate" / "runs").iterdir()
    _rows, snapshot = _memo(run_root)
    assert snapshot.terminal is not None
    assert (fresh_root / "handoff.txt").read_bytes() == b"21"
    return snapshot


def test_public_invalidate_cancels_only_committed_suffix_and_replays_file_handoff(
    tmp_path: Path,
) -> None:
    case = _pab_baseline(tmp_path)
    _refuse_changed_writer_readonly(case)
    first_range = _append_first_range(case)
    case["first_range"] = first_range["row"]
    _reject_repeat_before_retry(case, first_range)
    first_retry = _resume_first_retry(case)
    _invalidate_future_range(case, first_retry)
    retried = _resume_future_range(case)
    fresh = _fresh_file_handoff(tmp_path)
    assert retried.terminal.data["value"] == fresh.terminal.data["value"]


def test_public_invalidate_uses_state_dir_and_rejects_noncanonical_identity(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / "external-state"
    state_dir.mkdir()
    run_root = _completed_run(tmp_path, state_dir=state_dir)
    commit = _first_commit(run_root)
    before = _tree_bytes(state_dir)

    near_match = _cli(
        tmp_path, "invalidate", run_root.name, commit.data["identity"] + " ",
        "--state-dir", str(state_dir),
    )
    assert near_match.returncode == 2
    assert "invalidate_not_committed" in near_match.stderr
    assert _tree_bytes(state_dir) == before

    result = _cli(
        tmp_path, "invalidate", run_root.name, commit.data["identity"],
        "--state-dir", str(state_dir),
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["from_commit"] == commit.offset
    assert not (tmp_path / ".orchestrate" / "runs").exists()


@pytest.mark.parametrize("without_recipe", [False, True], ids=["recipe-present", "historical-absent"])
def test_public_invalidate_does_not_read_current_sources_or_recipe_locators(
    tmp_path: Path, without_recipe: bool
) -> None:
    run_root = _completed_run(tmp_path)
    commit = _first_commit(run_root)
    header_path = run_root / "run.json"
    header = json.loads(header_path.read_text(encoding="utf-8"))
    if without_recipe:
        header.pop("resume_request")
        header_path.write_text(json.dumps(header), encoding="utf-8")
    for filename in (
        "invalidate_public.orc", "commands.json", "prefix.py", "writer.py", "reader.py"
    ):
        (tmp_path / filename).unlink()
    before = _tree_bytes(tmp_path / ".orchestrate", omit_memo=run_root / "memo.jsonl")

    result = _cli(tmp_path, "invalidate", run_root.name, commit.data["identity"])

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["from_commit"] == commit.offset
    assert ("resume_request" not in json.loads(header_path.read_text(encoding="utf-8"))) == without_recipe
    assert _tree_bytes(tmp_path / ".orchestrate", omit_memo=run_root / "memo.jsonl") == before


@pytest.mark.parametrize(
    ("case", "diagnostic"),
    [
        ("old-profile", "invalidate_profile_unsupported"),
        ("unknown-profile", "memo_inconsistent"),
        ("malformed-recipe", "memo_inconsistent"),
        ("malformed-artifact", "memo_inconsistent"),
        ("malformed-journal", "memo_inconsistent"),
        ("unknown-identity", "invalidate_not_committed"),
    ],
)
def test_public_invalidate_refuses_bad_profile_authority_or_journal_without_writes(
    tmp_path: Path, case: str, diagnostic: str
) -> None:
    run_root = _completed_run(tmp_path)
    commit = _first_commit(run_root)
    target = commit.data["identity"]
    if case == "old-profile":
        header_path = run_root / "run.json"
        header = json.loads(header_path.read_text(encoding="utf-8"))
        header["schema_version"] = "2.1"
        header.pop("result_persistence_profile")
        header_path.write_text(json.dumps(header), encoding="utf-8")
    elif case == "unknown-profile":
        header_path = run_root / "run.json"
        header = json.loads(header_path.read_text(encoding="utf-8"))
        header["result_persistence_profile"] = "unknown.v1"
        header_path.write_text(json.dumps(header), encoding="utf-8")
    elif case == "malformed-recipe":
        header_path = run_root / "run.json"
        header = json.loads(header_path.read_text(encoding="utf-8"))
        header["resume_request"] = None
        header_path.write_text(json.dumps(header), encoding="utf-8")
    elif case == "malformed-artifact":
        (run_root / "closed_program.json").write_text("{}", encoding="utf-8")
    elif case == "malformed-journal":
        with (run_root / "memo.jsonl").open("ab") as stream:
            stream.write(b"{bad-json}\n")
    else:
        target += " / near-match"
    before = _tree_bytes(tmp_path / ".orchestrate")

    result = _cli(tmp_path, "invalidate", run_root.name, target)

    assert result.returncode == 2
    assert diagnostic in result.stderr
    assert "Traceback" not in result.stderr
    assert _tree_bytes(tmp_path / ".orchestrate") == before


def test_invalidate_default_root_refuses_a_state_root_symlink(
    tmp_path: Path,
) -> None:
    external = tmp_path / "external"
    external.mkdir()
    (tmp_path / ".orchestrate").symlink_to(external, target_is_directory=True)

    result = _cli(tmp_path, "invalidate", "missing-run", "workflow::run / site")

    assert result.returncode == 2
    assert "state_root_symlink" in result.stderr
    assert not list(external.iterdir())


def test_invalidate_state_dir_symlink_cycle_returns_exit_two(tmp_path: Path) -> None:
    first = tmp_path / "state-a"
    second = tmp_path / "state-b"
    first.symlink_to(second)
    second.symlink_to(first)

    result = _cli(
        tmp_path, "invalidate", "missing-run", "workflow::run / site",
        "--state-dir", str(first),
    )

    assert result.returncode == 2
    assert "Traceback" not in result.stderr
