"""The maintained best-of-N consumer with a parallel candidate map (Phase 5 Task 6).

The test installs an exact copy of `experiments/orc_vs_single_call/workflows/best_of_n.orc`
and changes only its target and the candidate map's `:parallel 2 :workspace repo`. The
providers are `install_standins` stand-ins answering by request identity; the coder
stand-in also gets `OVERLAP`: it marks itself active, logs how many coders are active as
it enters, fails while its cwd holds `fail`, and holds the first coder until a second has
entered, so overlap is a fact of the run rather than of timing. The first two then stay
active for one more second: a third coder admitted by a wider bound would enter in it and
log three. No provider is called.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.contracts.closed_program.targets import SUPPORTED_TARGET_DSL_VERSIONS
from tests.test_workflow_evaluated_cli import _run_cli
from tests.test_workflow_evaluated_invalidate import _cli, _tree_bytes
from tests.workflow_evaluated_consumer_sources import (
    CANDIDATES, PROGRAMS, ROOT, compile_current, git, install, jsonl, sha256,
)
from tests.workflow_evaluated_recovery_helpers import BUNDLE, install_standins, resume
from tests.workflow_evaluated_totality_helpers import checked_run


NEWEST = max(SUPPORTED_TARGET_DSL_VERSIONS, key=lambda version: tuple(map(int, version.split("."))))
TARGETS = ("2.37", NEWEST)
PROGRAM = PROGRAMS["best_of_n"]
SERIAL_MAP = "(list/map-effect ((repo repos)) :max 8\n"
PARALLEL_MAP = "(list/map-effect ((repo repos)) :max 8 :parallel 2 :workspace repo\n"
REPOS = (*CANDIDATES, "candidates/gamma", "candidates/delta")  # under the workspace; inputs are absolute
FIXED = "def add(a, b):\n    return a + b\n"
BEST = "workflow:best_of_n::best-of-n"
JUDGE = f"{BEST} / selection"
ACCOUNTS = [f"candidate-account-{index}" for index in range(len(REPOS))]
REPORT = "artifacts/review/selection.md"
OVERLAP = '''import os as _os, sys as _sys, time as _time
from pathlib import Path as _Path
_control = _Path(_os.environ["OVERLAP_CONTROL"])
_mine = _control / "active" / str(_os.getpid())
_mine.parent.mkdir(exist_ok=True)
_mine.write_text("")
with open(_control / "entries.jsonl", "a", encoding="utf-8") as _log:
    _log.write(str(len(list(_mine.parent.iterdir()))) + "\\n")
_first = len((_control / "entries.jsonl").read_text().splitlines()) <= 2
if _Path("fail").exists():
    _mine.unlink()
    _sys.exit(3)
_deadline = _time.monotonic() + 30
while len((_control / "entries.jsonl").read_text().splitlines()) < 2 and _time.monotonic() < _deadline:
    _time.sleep(0.02)
if _first:
    _time.sleep(1.0)  # a window in which a third coder would enter if the bound let it
import atexit as _atexit
_atexit.register(_mine.unlink)
'''


def coder(index: int) -> str:
    return f"{BEST} / accounts / body / par-map:repo[{index}] / #1=workflow:best_of_n::implement-one / change"


def repos(root: Path) -> list[str]:
    """The candidates as absolute paths: the prompt's `{repo}` must name the coder's own cwd."""
    return [str(root / repo) for repo in REPOS]


def selection(root: Path) -> dict:
    return {"winner": repos(root)[-1], "ranking": [f"{repo}: 2 2 2 2" for repo in reversed(repos(root))],
            "report": REPORT}


def _answers(root: Path) -> dict[str, dict]:
    answers = {sha256(coder(index)): {"result": {"summary": f"Fix {repo}.", "account": account},
                                      "files": {"calc.py": FIXED}}
               for index, (repo, account) in enumerate(zip(REPOS, ACCOUNTS, strict=True))}
    answers[sha256(JUDGE)] = {"result": selection(root), "files": {REPORT: "# Selection\n"}}
    return answers


def _workspace(tmp_path: Path, monkeypatch, target: str) -> tuple[Path, list[str]]:
    """The copy at `target` with only the parallel map added, four candidates and the stand-ins."""
    root = tmp_path / "workspace"
    install_standins(tmp_path / "bin", monkeypatch, _answers(root), repos(root))
    claude = tmp_path / "bin" / "claude"
    shebang, body = claude.read_text().split("\n", 1)
    claude.write_text(f"{shebang}\n{OVERLAP}{body}")
    control = tmp_path / "control"
    control.mkdir()
    monkeypatch.setenv("OVERLAP_CONTROL", str(control))
    inputs = {"task": "Fix add in calc.py so that it returns the sum.", "intent": "add returns a + b",
              "repos": repos(root)}
    frontend = install(root, PROGRAM, inputs)
    source = (ROOT / PROGRAM.source).read_text()
    assert source.count(SERIAL_MAP) == 1 and source.count('(:target-dsl "2.35")') == 1
    (root / PROGRAM.source).write_text(source.replace('(:target-dsl "2.35")', f'(:target-dsl "{target}")')
                                       .replace(SERIAL_MAP, PARALLEL_MAP))
    for repo in REPOS[2:]:
        git(root, "clone", "-q", CANDIDATES[0], repo)
    return root, frontend


def _requests(root: Path) -> list[dict]:
    """Every stand-in request: coders log in their candidate's cwd, the judge in the workspace."""
    return [*(row for repo in REPOS for row in jsonl(root / repo / "requests.jsonl")),
            *jsonl(root / "requests.jsonl")]


def _entries(tmp_path: Path) -> list[int]:
    return [int(line) for line in (tmp_path / "control" / "entries.jsonl").read_text().splitlines()]


def _rows(snapshot, record: str) -> list:
    return [entry for entry in snapshot.entries if entry.data["record"] == record]


def _attempt(request: dict) -> tuple[str, int]:
    match = BUNDLE.search(request["bundle"].replace("\\", "/"))
    return match.group(1), int(match.group(2))


def _assert_requests_match_commits(root: Path, snapshot) -> None:
    """Each logged request is exactly one committed identity and attempt (a failing coder exits before logging)."""
    rows = _rows(snapshot, "committed")
    expected = sorted((sha256(row.data["identity"]).removeprefix("sha256:"), row.data["attempt"]) for row in rows)
    assert sorted(_attempt(request) for request in _requests(root)) == expected
    for request in _requests(root):
        identity = next(row.data["identity"] for row in rows
                        if sha256(row.data["identity"]).removeprefix("sha256:") == _attempt(request)[0])
        assert request["site"] == sha256(identity)


def _assert_judged_once_after_all(root: Path, snapshot) -> None:
    judge_starts = [entry for entry in _rows(snapshot, "started") if entry.data["identity"] == JUDGE]
    coder_commits = [entry for entry in _rows(snapshot, "committed") if entry.data["identity"] != JUDGE]
    assert len(judge_starts) == 1 and len(coder_commits) == len(REPOS)
    assert judge_starts[0].offset > max(entry.offset for entry in coder_commits)
    _assert_judge_inputs_in_order(root)


def _assert_judge_inputs_in_order(root: Path) -> None:
    (judge,) = jsonl(root / "requests.jsonl")
    assert judge["repos"] == repos(root)
    prompt = (Path(judge["bundle"]).parent / "prompt.txt").read_text()
    positions = [prompt.index(account) for account in ACCOUNTS]
    assert positions == sorted(positions)


def _assert_coders_ran_in_their_repo(root: Path) -> None:
    """Each coder's cwd is the one repository its own request names."""
    coders = [request for request in _requests(root) if request["tool"] == "claude"]
    assert sorted(request["cwd"] for request in coders) == sorted(repos(root))
    assert all(request["repos"] == [request["cwd"]] for request in coders)


def _assert_candidates_edited(root: Path) -> None:
    for repo in REPOS:
        assert (root / repo / "calc.py").read_text() == FIXED
        assert git(root / repo, "status", "--porcelain") == " M calc.py\n?? requests.jsonl\n"


@pytest.mark.parametrize("target", TARGETS)
def test_parallel_best_of_n_overlaps_within_its_bound_and_judges_once(tmp_path, monkeypatch, target):
    root, frontend = _workspace(tmp_path, monkeypatch, target)
    compile_current(root, frontend)
    result = _run_cli(root, *frontend, "--input-file", "inputs.json")
    assert result.returncode == 0, result.stderr
    _authority, snapshot = checked_run(root)
    assert snapshot.terminal.data["value"] == selection(root)
    entries = _entries(tmp_path)
    assert len(entries) == len(REPOS) and max(entries) == 2
    _assert_judged_once_after_all(root, snapshot)
    _assert_requests_match_commits(root, snapshot)
    assert [request["cwd"] for request in _requests(root)] == [*repos(root), str(root)]
    _assert_coders_ran_in_their_repo(root)
    _assert_candidates_edited(root)
    assert (root / REPORT).is_file()


def _run_with_failed_candidate(root: Path, frontend: list[str], index: int) -> list[dict]:
    """Run with candidate `index` failing; return the sibling commits; the judge never starts."""
    (root / REPOS[index] / "fail").write_text("")
    failed = _run_cli(root, *frontend, "--input-file", "inputs.json")
    assert failed.returncode != 0 and "[provider_exit_nonzero]" in failed.stdout + failed.stderr
    _authority, snapshot = checked_run(root)
    kept = [entry.data for entry in _rows(snapshot, "committed")]
    assert sorted(row["identity"] for row in kept) == sorted(coder(other) for other in range(len(REPOS)) if other != index)
    assert [entry.data["identity"] for entry in _rows(snapshot, "failed")] == [coder(index)]
    assert not (root / "requests.jsonl").exists()
    (root / REPOS[index] / "fail").unlink()
    return kept


def _attempts(snapshot, identity: str) -> list[int]:
    return [entry.data["attempt"] for entry in _rows(snapshot, "started") if entry.data["identity"] == identity]


@pytest.mark.parametrize("target", TARGETS)
def test_failed_implementation_keeps_sibling_commits_and_resume_judges_once(tmp_path, monkeypatch, target):
    root, frontend = _workspace(tmp_path, monkeypatch, target)
    kept = _run_with_failed_candidate(root, frontend, 1)
    resumed = resume(root, snapshot_run_id(root))
    assert resumed.returncode == 0, resumed.stdout + resumed.stderr
    _authority, after = checked_run(root)
    assert after.terminal.data["value"] == selection(root)
    assert [entry.data for entry in _rows(after, "committed")][:3] == kept
    assert _attempts(after, coder(1)) == [1, 2]
    _assert_judged_once_after_all(root, after)
    _assert_requests_match_commits(root, after)
    _assert_candidates_edited(root)
    _assert_coders_ran_in_their_repo(root)


def snapshot_run_id(root: Path) -> str:
    authority, _snapshot = checked_run(root)
    return authority.run_root.name


@pytest.mark.parametrize("target", TARGETS)
def test_compile_dry_run_run_report_and_two_completed_resumes(tmp_path, monkeypatch, target):
    root, frontend = _workspace(tmp_path, monkeypatch, target)
    compile_current(root, frontend)
    dry_run = _cli(root, "run", *frontend, "--input-file", "inputs.json", "--dry-run")
    assert dry_run.returncode == 0, dry_run.stderr
    assert not (root / "requests.jsonl").exists() and not (tmp_path / "control" / "entries.jsonl").exists()
    result = _run_cli(root, *frontend, "--input-file", "inputs.json")
    assert result.returncode == 0, result.stderr
    run_id = snapshot_run_id(root)
    report = _cli(root, "report", "--run-id", run_id, "--runs-root", str(root / ".orchestrate" / "runs"),
                  "--format", "json")
    assert report.returncode == 0, report.stderr
    assert json.loads(report.stdout)["run"]["workflow_outputs"] == selection(root)
    before = _tree_bytes(root), _tree_bytes(tmp_path / "control")
    for _ in range(2):
        completed = resume(root, run_id)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert (_tree_bytes(root), _tree_bytes(tmp_path / "control")) == before
