# Verified-Iteration Drain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not create a git worktree; this repo's AGENTS.md forbids worktrees.

**Goal:** Implement the verified-iteration drain designed in `docs/design/verified_iteration_drain.md` — a single-loop autonomous drain whose only state is the repo, an append-only ledger, and measured status tokens — as a pilot alongside (not replacing) the `lisp_frontend_*` family.

**Architecture:** One `repeat_until` workflow (`workflows/examples/verified_iteration_drain.yaml`) with six inner steps: Prepare (snapshot + work order) → Work (one fused agentic session) → Verify (fixed checks + diff package) → ReviewIteration (diff vs design, gated) → ReviewDoneClaim (gated on DONE verdict) → Record (derive status from measurables, append ledger/status token, emit drain_status). Three new scripts, three new prompts, one new test module. The spec is the design doc; every behavioral rule implemented here must match its status table and loop-control section.

**Tech Stack:** DSL v2.14 YAML (modeled on `workflows/examples/lisp_frontend_design_delta_drain.yaml` idioms), Python 3 scripts under `workflows/library/scripts/`, pytest with the fake-provider harness pattern from `tests/test_lisp_frontend_autonomous_drain_runtime.py`.

## Global Constraints

- The working tree is shared with the user's in-flight work and a live drain run. Stage ONLY files this plan creates or names, by explicit path. NEVER `git add -A`, `git add .`, or `git commit -a`. Run `git status --porcelain` before staging and `git show --stat HEAD` after each commit.
- Do not modify any `lisp_frontend_*` workflow, prompt, or script.
- Commit messages: plain, no assistant attribution, no Co-Authored-By trailers.
- Run all commands from the repo root.
- No tests may assert literal prompt text (repo rule). Prompt files are verified via loader smoke and runtime behavior only.
- New test module ⇒ run `pytest --collect-only` on it (repo rule).
- Enum values are exact and shared across scripts, YAML, and tests: iteration statuses `DONE ACCEPTED CHECKS_RED FINDINGS BLOCKED_ON_USER NO_CHANGE`; drain statuses `CONTINUE DONE BLOCKED_ON_USER STALLED`; verify `GREEN RED`; verdicts `CONTINUE DONE BLOCKED_ON_USER`; review `APPROVE FINDINGS`; done-review `APPROVE REJECT`; skipped decisions read as `SKIPPED`.
- Status precedence (from the design doc — implement exactly): `CHECKS_RED` (verify RED) → `FINDINGS` (review FINDINGS, or verdict DONE with done-review ≠ APPROVE) → `DONE` (verdict DONE, done-review APPROVE) → `BLOCKED_ON_USER` (verdict BLOCKED_ON_USER ∧ ≥1 `BLOCKED-*.md`) → `ACCEPTED` (commits ∧ review APPROVE) → `NO_CHANGE`.

## File Structure

- Create: `workflows/library/scripts/prepare_verified_iteration.py` — snapshot base SHA, regenerate work order (Task 1)
- Create: `workflows/library/scripts/run_verified_iteration_checks.py` — run checks, package diff (Task 2)
- Create: `workflows/library/scripts/record_verified_iteration.py` — derive status, append ledger/tokens, emit drain_status (Task 3)
- Create: `workflows/library/prompts/verified_iteration_drain/work.md`, `review_iteration.md`, `review_done.md` (Task 4)
- Create: `workflows/examples/verified_iteration_drain.yaml` (Task 5)
- Create: `tests/test_verified_iteration_drain.py` — all tests for this plan (Tasks 1–6)
- Modify: `docs/index.md`, `docs/capability_status_matrix.md` — routing rows only (Task 7)

---

### Task 1: Prepare script

**Files:**
- Create: `workflows/library/scripts/prepare_verified_iteration.py`
- Test: `tests/test_verified_iteration_drain.py`

**Interfaces:**
- Produces `work-order.json` consumed by Work/reviewer prompts and by Tasks 2–3 tests. Keys (all strings): `iteration`, `base_sha`, `target_design_path`, `check_commands_path`, `ledger_path`, `blocked_notes_dir`, `worker_verdict_path`, `worker_note_path`, `review_decision_path`, `review_findings_path`, `done_review_decision_path`, `previous_review_findings_path` (empty if absent), `previous_checks_log_path` (empty if absent), `work_order_path`.

- [x] **Step 1: Write the failing tests**

Create `tests/test_verified_iteration_drain.py`:

```python
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from orchestrator.loader import WorkflowLoader
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_context, workflow_input_contracts
from orchestrator.workflow.signatures import bind_workflow_inputs
from tests.test_lisp_frontend_autonomous_drain_runtime import _bundle_context_dict

ROOT = Path(__file__).resolve().parents[1]

PREPARE = "workflows/library/scripts/prepare_verified_iteration.py"
CHECKS = "workflows/library/scripts/run_verified_iteration_checks.py"
RECORD = "workflows/library/scripts/record_verified_iteration.py"
WORKFLOW = "workflows/examples/verified_iteration_drain.yaml"

STATE_ROOT = "state/VERIFIED-ITERATION-DRAIN"
WORK_ROOT = "artifacts/work/VERIFIED-ITERATION-DRAIN"


def _run_script(workspace: Path, *argv: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["python", *argv], cwd=workspace, text=True, capture_output=True, check=check)


def _git(workspace: Path, *argv: str) -> str:
    result = subprocess.run(["git", *argv], cwd=workspace, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def _init_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    (workspace / "docs/design").mkdir(parents=True)
    (workspace / "workflows/examples/inputs").mkdir(parents=True)
    (workspace / "docs/design/pilot_target.md").write_text(
        "# Pilot Target\n\nAcceptance: `hello.txt` exists at repo root.\n", encoding="utf-8"
    )
    (workspace / "workflows/examples/inputs/pilot_checks.json").write_text(
        json.dumps(["python -c \"print('ok')\""]) + "\n", encoding="utf-8"
    )
    _git(workspace, "init", "-q")
    _git(workspace, "config", "user.email", "test@test")
    _git(workspace, "config", "user.name", "test")
    _git(workspace, "add", "docs", "workflows")
    _git(workspace, "commit", "-qm", "seed")
    return workspace


def _prepare(workspace: Path, iteration: int = 0) -> dict:
    _run_script(
        workspace,
        str(ROOT / PREPARE),
        "--drain-state-root", STATE_ROOT,
        "--artifact-work-root", WORK_ROOT,
        "--target-design-path", "docs/design/pilot_target.md",
        "--check-commands-path", "workflows/examples/inputs/pilot_checks.json",
        "--iteration", str(iteration),
        "--output", f"{STATE_ROOT}/iterations/{iteration}/work-order.json",
    )
    return json.loads((workspace / STATE_ROOT / "iterations" / str(iteration) / "work-order.json").read_text(encoding="utf-8"))


def test_prepare_writes_work_order_and_scaffolding(tmp_path):
    workspace = _init_workspace(tmp_path)
    order = _prepare(workspace)
    assert order["base_sha"] == _git(workspace, "rev-parse", "HEAD")
    assert (workspace / order["ledger_path"]).is_file()
    assert (workspace / order["blocked_notes_dir"]).is_dir()
    assert order["previous_review_findings_path"] == ""
    assert order["worker_verdict_path"] == f"{STATE_ROOT}/iterations/0/worker-verdict.txt"
    assert order["review_decision_path"] == f"{STATE_ROOT}/iterations/0/review-decision.txt"


def test_prepare_names_previous_findings_when_present(tmp_path):
    workspace = _init_workspace(tmp_path)
    findings = workspace / STATE_ROOT / "iterations/0/review-findings.md"
    findings.parent.mkdir(parents=True)
    findings.write_text("finding\n", encoding="utf-8")
    order = _prepare(workspace, iteration=1)
    assert order["previous_review_findings_path"] == f"{STATE_ROOT}/iterations/0/review-findings.md"


def test_prepare_fails_fast_on_missing_target_design(tmp_path):
    workspace = _init_workspace(tmp_path)
    result = _run_script(
        workspace,
        str(ROOT / PREPARE),
        "--drain-state-root", STATE_ROOT,
        "--artifact-work-root", WORK_ROOT,
        "--target-design-path", "docs/design/absent.md",
        "--check-commands-path", "workflows/examples/inputs/pilot_checks.json",
        "--iteration", "0",
        "--output", f"{STATE_ROOT}/iterations/0/work-order.json",
        check=False,
    )
    assert result.returncode != 0
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_verified_iteration_drain.py -q -k prepare`
Expected: 3 failures (script file does not exist).

- [x] **Step 3: Write the script**

Create `workflows/library/scripts/prepare_verified_iteration.py`:

```python
#!/usr/bin/env python3
"""Prepare one verified-iteration: snapshot the git base and regenerate the work order.

Contract: docs/design/verified_iteration_drain.md (Component Contracts).
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

REPO_ROOT = Path.cwd()


def _git_head() -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True, capture_output=True)
    if result.returncode != 0:
        raise SystemExit(f"Workspace is not a git repository with commits: {result.stderr.strip()}")
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drain-state-root", required=True)
    parser.add_argument("--artifact-work-root", required=True)
    parser.add_argument("--target-design-path", required=True)
    parser.add_argument("--check-commands-path", required=True)
    parser.add_argument("--iteration", type=int, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if not (REPO_ROOT / args.target_design_path).is_file():
        raise SystemExit(f"Missing target design: {args.target_design_path}")
    if not (REPO_ROOT / args.check_commands_path).is_file():
        raise SystemExit(f"Missing check commands file: {args.check_commands_path}")

    state_root = REPO_ROOT / args.drain_state_root
    work_root = REPO_ROOT / args.artifact_work_root
    iteration_dir = state_root / "iterations" / str(args.iteration)
    iteration_dir.mkdir(parents=True, exist_ok=True)
    blocked_dir = work_root / "blocked"
    blocked_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = work_root / "ledger.md"
    if not ledger_path.exists():
        ledger_path.write_text("# Verified-iteration drain ledger\n\n", encoding="utf-8")

    def _rel(path: Path) -> str:
        return path.relative_to(REPO_ROOT).as_posix()

    previous_dir = state_root / "iterations" / str(args.iteration - 1)
    previous_findings = previous_dir / "review-findings.md"
    previous_checks_log = previous_dir / "checks-log.txt"

    order = {
        "iteration": str(args.iteration),
        "base_sha": _git_head(),
        "target_design_path": args.target_design_path,
        "check_commands_path": args.check_commands_path,
        "ledger_path": _rel(ledger_path),
        "blocked_notes_dir": _rel(blocked_dir),
        "worker_verdict_path": _rel(iteration_dir / "worker-verdict.txt"),
        "worker_note_path": _rel(iteration_dir / "worker-note.txt"),
        "review_decision_path": _rel(iteration_dir / "review-decision.txt"),
        "review_findings_path": _rel(iteration_dir / "review-findings.md"),
        "done_review_decision_path": _rel(iteration_dir / "done-review-decision.txt"),
        "previous_review_findings_path": _rel(previous_findings) if previous_findings.is_file() else "",
        "previous_checks_log_path": _rel(previous_checks_log) if previous_checks_log.is_file() else "",
        "work_order_path": _rel(iteration_dir / "work-order.json"),
    }
    output = REPO_ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(order, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_verified_iteration_drain.py -q -k prepare`
Expected: 3 passed.

- [x] **Step 5: Commit**

```bash
git add workflows/library/scripts/prepare_verified_iteration.py tests/test_verified_iteration_drain.py
git commit -m "Add verified-iteration prepare script"
```

---

### Task 2: Checks-and-diff-package script

**Files:**
- Create: `workflows/library/scripts/run_verified_iteration_checks.py`
- Test: `tests/test_verified_iteration_drain.py`

**Interfaces:**
- Consumes: `base_sha` from Task 1's order.
- Produces `checks-result.json`: `verify_status` (`GREEN|RED`), `commits_landed` (`"true"|"false"`), `head_sha`, `checks_log_path`, `review_package_path`. Exit 0 for both GREEN and RED; nonzero only for a missing/invalid check-commands file.

- [x] **Step 1: Write the failing tests** (append to the test module)

```python
def _run_checks(workspace: Path, base_sha: str, *, checks: str = "workflows/examples/inputs/pilot_checks.json", iteration: int = 0) -> dict:
    _run_script(
        workspace,
        str(ROOT / CHECKS),
        "--check-commands-path", checks,
        "--base-sha", base_sha,
        "--iteration-dir", f"{STATE_ROOT}/iterations/{iteration}",
        "--output", f"{STATE_ROOT}/iterations/{iteration}/checks-result.json",
    )
    return json.loads((workspace / STATE_ROOT / "iterations" / str(iteration) / "checks-result.json").read_text(encoding="utf-8"))


def test_checks_green_with_commits_packages_diff(tmp_path):
    workspace = _init_workspace(tmp_path)
    base = _git(workspace, "rev-parse", "HEAD")
    (workspace / "hello.txt").write_text("hi\n", encoding="utf-8")
    _git(workspace, "add", "hello.txt")
    _git(workspace, "commit", "-qm", "add hello")
    result = _run_checks(workspace, base)
    assert result["verify_status"] == "GREEN"
    assert result["commits_landed"] == "true"
    package = (workspace / result["review_package_path"]).read_text(encoding="utf-8")
    assert "add hello" in package
    assert "hello.txt" in package


def test_checks_red_on_failing_command_still_exits_zero(tmp_path):
    workspace = _init_workspace(tmp_path)
    (workspace / "workflows/examples/inputs/red_checks.json").write_text(
        json.dumps(["python -c \"raise SystemExit(1)\""]) + "\n", encoding="utf-8"
    )
    base = _git(workspace, "rev-parse", "HEAD")
    result = _run_checks(workspace, base, checks="workflows/examples/inputs/red_checks.json")
    assert result["verify_status"] == "RED"
    assert result["commits_landed"] == "false"
    assert "exit 1" in (workspace / result["checks_log_path"]).read_text(encoding="utf-8")


def test_checks_fails_fast_on_invalid_checks_file(tmp_path):
    workspace = _init_workspace(tmp_path)
    (workspace / "workflows/examples/inputs/bad_checks.json").write_text("{}\n", encoding="utf-8")
    base = _git(workspace, "rev-parse", "HEAD")
    proc = _run_script(
        workspace,
        str(ROOT / CHECKS),
        "--check-commands-path", "workflows/examples/inputs/bad_checks.json",
        "--base-sha", base,
        "--iteration-dir", f"{STATE_ROOT}/iterations/0",
        "--output", f"{STATE_ROOT}/iterations/0/checks-result.json",
        check=False,
    )
    assert proc.returncode != 0
```

- [x] **Step 2: Run to verify failure**

Run: `pytest tests/test_verified_iteration_drain.py -q -k checks`
Expected: 3 failures (script missing).

- [x] **Step 3: Write the script**

Create `workflows/library/scripts/run_verified_iteration_checks.py`:

```python
#!/usr/bin/env python3
"""Run the fixed verified-iteration check suite and package the iteration diff.

Contract: docs/design/verified_iteration_drain.md (Component Contracts).
Verify status is data, not a process error: the script exits 0 for GREEN and
RED alike and reserves nonzero exits for setup failures.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

REPO_ROOT = Path.cwd()


def _git(*argv: str) -> str:
    result = subprocess.run(["git", *argv], cwd=REPO_ROOT, text=True, capture_output=True)
    if result.returncode != 0:
        raise SystemExit(f"git {' '.join(argv)} failed: {result.stderr.strip()}")
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-commands-path", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--iteration-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    try:
        commands = json.loads((REPO_ROOT / args.check_commands_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Invalid check commands file {args.check_commands_path}: {exc}")
    if not isinstance(commands, list) or not commands or not all(isinstance(c, str) and c.strip() for c in commands):
        raise SystemExit(f"Check commands must be a non-empty JSON list of strings: {args.check_commands_path}")

    iteration_dir = REPO_ROOT / args.iteration_dir
    iteration_dir.mkdir(parents=True, exist_ok=True)

    verify_status = "GREEN"
    log_lines: list[str] = []
    for command in commands:
        result = subprocess.run(command, cwd=REPO_ROOT, shell=True, text=True, capture_output=True)
        log_lines.append(f"$ {command}\nexit {result.returncode}\n{result.stdout}{result.stderr}\n")
        if result.returncode != 0:
            verify_status = "RED"
    checks_log = iteration_dir / "checks-log.txt"
    checks_log.write_text("".join(log_lines), encoding="utf-8")

    head_sha = _git("rev-parse", "HEAD").strip()
    commits_landed = "false" if head_sha == args.base_sha else "true"
    commit_log = _git("log", "--oneline", f"{args.base_sha}..{head_sha}") if commits_landed == "true" else ""
    diff = _git("diff", f"{args.base_sha}..{head_sha}") if commits_landed == "true" else ""
    review_package = iteration_dir / "review-package.md"
    review_package.write_text(
        "## Commits\n\n" + commit_log + "\n## Diff\n\n```diff\n" + diff + "\n```\n",
        encoding="utf-8",
    )

    payload = {
        "verify_status": verify_status,
        "commits_landed": commits_landed,
        "head_sha": head_sha,
        "checks_log_path": checks_log.relative_to(REPO_ROOT).as_posix(),
        "review_package_path": review_package.relative_to(REPO_ROOT).as_posix(),
    }
    (REPO_ROOT / args.output).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [x] **Step 4: Run to verify pass**

Run: `pytest tests/test_verified_iteration_drain.py -q -k checks`
Expected: 3 passed.

- [x] **Step 5: Commit**

```bash
git add workflows/library/scripts/run_verified_iteration_checks.py tests/test_verified_iteration_drain.py
git commit -m "Add verified-iteration check runner and diff packager"
```

---

### Task 3: Record script (the semantic core)

**Files:**
- Create: `workflows/library/scripts/record_verified_iteration.py`
- Test: `tests/test_verified_iteration_drain.py`

**Interfaces:**
- Consumes Task 2's `checks-result.json`, decision files (missing ⇒ `SKIPPED`), verdict/note files, blocked-notes dir.
- Produces: one appended line in `ledger.md`, one appended token in `statuses.txt`, regenerated `drain-summary.json`, and `drain-status.txt` ∈ `CONTINUE|DONE|BLOCKED_ON_USER|STALLED`.

- [x] **Step 1: Write the failing tests** (append to the test module)

```python
def _record(
    workspace: Path,
    *,
    iteration: int = 0,
    verify: str = "GREEN",
    commits: str = "false",
    verdict: str = "CONTINUE",
    review: str | None = None,
    done_review: str | None = None,
    blocked_note: bool = False,
    stall_limit: str = "3",
    seed_statuses: list[str] | None = None,
) -> tuple[str, str]:
    iteration_dir = workspace / STATE_ROOT / "iterations" / str(iteration)
    iteration_dir.mkdir(parents=True, exist_ok=True)
    (iteration_dir / "checks-result.json").write_text(
        json.dumps(
            {
                "verify_status": verify,
                "commits_landed": commits,
                "head_sha": "h" * 40,
                "checks_log_path": f"{STATE_ROOT}/iterations/{iteration}/checks-log.txt",
                "review_package_path": f"{STATE_ROOT}/iterations/{iteration}/review-package.md",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (iteration_dir / "worker-verdict.txt").write_text(verdict + "\n", encoding="utf-8")
    (iteration_dir / "worker-note.txt").write_text("did a thing\n", encoding="utf-8")
    if review is not None:
        (iteration_dir / "review-decision.txt").write_text(review + "\n", encoding="utf-8")
    if done_review is not None:
        (iteration_dir / "done-review-decision.txt").write_text(done_review + "\n", encoding="utf-8")
    blocked_dir = workspace / WORK_ROOT / "blocked"
    blocked_dir.mkdir(parents=True, exist_ok=True)
    if blocked_note:
        (blocked_dir / "BLOCKED-env.md").write_text("need credentials\n", encoding="utf-8")
    (workspace / WORK_ROOT / "ledger.md").parent.mkdir(parents=True, exist_ok=True)
    statuses = workspace / STATE_ROOT / "statuses.txt"
    if seed_statuses:
        statuses.write_text("".join(token + "\n" for token in seed_statuses), encoding="utf-8")
    _run_script(
        workspace,
        str(ROOT / RECORD),
        "--iteration", str(iteration),
        "--base-sha", "b" * 40,
        "--checks-result-path", f"{STATE_ROOT}/iterations/{iteration}/checks-result.json",
        "--review-decision-path", f"{STATE_ROOT}/iterations/{iteration}/review-decision.txt",
        "--done-review-decision-path", f"{STATE_ROOT}/iterations/{iteration}/done-review-decision.txt",
        "--worker-verdict-path", f"{STATE_ROOT}/iterations/{iteration}/worker-verdict.txt",
        "--worker-note-path", f"{STATE_ROOT}/iterations/{iteration}/worker-note.txt",
        "--blocked-notes-dir", f"{WORK_ROOT}/blocked",
        "--ledger-path", f"{WORK_ROOT}/ledger.md",
        "--statuses-path", f"{STATE_ROOT}/statuses.txt",
        "--stall-limit", stall_limit,
        "--summary-path", f"{WORK_ROOT}/drain-summary.json",
        "--drain-status-path", f"{STATE_ROOT}/iterations/{iteration}/drain-status.txt",
    )
    tokens = statuses.read_text(encoding="utf-8").split()
    drain = (workspace / STATE_ROOT / "iterations" / str(iteration) / "drain-status.txt").read_text(encoding="utf-8").strip()
    return tokens[-1], drain


def test_record_accepted_iteration_continues(tmp_path):
    workspace = _init_workspace(tmp_path)
    status, drain = _record(workspace, commits="true", review="APPROVE")
    assert (status, drain) == ("ACCEPTED", "CONTINUE")
    ledger = (workspace / WORK_ROOT / "ledger.md").read_text(encoding="utf-8")
    assert "ACCEPTED" in ledger and "did a thing" in ledger


def test_record_checks_red_takes_precedence_over_done(tmp_path):
    workspace = _init_workspace(tmp_path)
    status, drain = _record(workspace, verify="RED", commits="true", verdict="DONE", done_review="APPROVE")
    assert (status, drain) == ("CHECKS_RED", "CONTINUE")


def test_record_review_findings_block_acceptance(tmp_path):
    workspace = _init_workspace(tmp_path)
    status, drain = _record(workspace, commits="true", review="FINDINGS")
    assert (status, drain) == ("FINDINGS", "CONTINUE")


def test_record_done_requires_done_review_approval(tmp_path):
    workspace = _init_workspace(tmp_path)
    status, drain = _record(workspace, commits="true", verdict="DONE", review="APPROVE", done_review="APPROVE")
    assert (status, drain) == ("DONE", "DONE")
    status, drain = _record(workspace, iteration=1, verdict="DONE", done_review="REJECT")
    assert (status, drain) == ("FINDINGS", "CONTINUE")


def test_record_done_claim_without_done_review_is_findings(tmp_path):
    workspace = _init_workspace(tmp_path)
    status, drain = _record(workspace, verdict="DONE")
    assert (status, drain) == ("FINDINGS", "CONTINUE")


def test_record_blocked_requires_a_note(tmp_path):
    workspace = _init_workspace(tmp_path)
    status, drain = _record(workspace, verdict="BLOCKED_ON_USER", blocked_note=True)
    assert (status, drain) == ("BLOCKED_ON_USER", "BLOCKED_ON_USER")
    workspace2 = _init_workspace(tmp_path / "second")
    status, drain = _record(workspace2, verdict="BLOCKED_ON_USER")
    assert (status, drain) == ("NO_CHANGE", "CONTINUE")


def test_record_stall_after_consecutive_non_accepted(tmp_path):
    workspace = _init_workspace(tmp_path)
    status, drain = _record(workspace, seed_statuses=["NO_CHANGE", "FINDINGS"], verify="RED")
    assert (status, drain) == ("CHECKS_RED", "STALLED")
    summary = json.loads((workspace / WORK_ROOT / "drain-summary.json").read_text(encoding="utf-8"))
    assert summary["drain_status"] == "STALLED"
    assert summary["statuses"] == ["NO_CHANGE", "FINDINGS", "CHECKS_RED"]


def test_record_accepted_interrupts_stall_window(tmp_path):
    workspace = _init_workspace(tmp_path)
    status, drain = _record(workspace, seed_statuses=["NO_CHANGE", "ACCEPTED"], verify="RED")
    assert (status, drain) == ("CHECKS_RED", "CONTINUE")
```

- [x] **Step 2: Run to verify failure**

Run: `pytest tests/test_verified_iteration_drain.py -q -k record`
Expected: 8 failures (script missing).

- [x] **Step 3: Write the script**

Create `workflows/library/scripts/record_verified_iteration.py`:

```python
#!/usr/bin/env python3
"""Derive one verified-iteration status from measured outcomes and record it.

Contract: docs/design/verified_iteration_drain.md (status table and loop
control). Status is a pure function of measurements; this script never
rewrites prior ledger lines or status tokens, and never mutates the tree.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path.cwd()

STALL_STATUSES = {"NO_CHANGE", "CHECKS_RED", "FINDINGS"}


def _read_token(path_value: str, *, default: str = "SKIPPED") -> str:
    path = REPO_ROOT / path_value
    if not path.is_file():
        return default
    return path.read_text(encoding="utf-8").strip() or default


def _derive_status(
    *,
    verify: str,
    commits: str,
    verdict: str,
    review: str,
    done_review: str,
    has_blocked_notes: bool,
) -> str:
    if verify == "RED":
        return "CHECKS_RED"
    if review == "FINDINGS":
        return "FINDINGS"
    if verdict == "DONE":
        return "DONE" if done_review == "APPROVE" else "FINDINGS"
    if verdict == "BLOCKED_ON_USER" and has_blocked_notes:
        return "BLOCKED_ON_USER"
    if commits == "true" and review == "APPROVE":
        return "ACCEPTED"
    return "NO_CHANGE"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iteration", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--checks-result-path", required=True)
    parser.add_argument("--review-decision-path", required=True)
    parser.add_argument("--done-review-decision-path", required=True)
    parser.add_argument("--worker-verdict-path", required=True)
    parser.add_argument("--worker-note-path", required=True)
    parser.add_argument("--blocked-notes-dir", required=True)
    parser.add_argument("--ledger-path", required=True)
    parser.add_argument("--statuses-path", required=True)
    parser.add_argument("--stall-limit", required=True)
    parser.add_argument("--summary-path", required=True)
    parser.add_argument("--drain-status-path", required=True)
    args = parser.parse_args()

    checks = json.loads((REPO_ROOT / args.checks_result_path).read_text(encoding="utf-8"))
    verdict = _read_token(args.worker_verdict_path, default="")
    if verdict not in {"CONTINUE", "DONE", "BLOCKED_ON_USER"}:
        raise SystemExit(f"Invalid or missing worker verdict: {verdict!r}")
    note = _read_token(args.worker_note_path, default="")
    blocked_dir = REPO_ROOT / args.blocked_notes_dir
    has_blocked_notes = blocked_dir.is_dir() and any(blocked_dir.glob("BLOCKED-*.md"))

    status = _derive_status(
        verify=str(checks.get("verify_status") or ""),
        commits=str(checks.get("commits_landed") or ""),
        verdict=verdict,
        review=_read_token(args.review_decision_path),
        done_review=_read_token(args.done_review_decision_path),
        has_blocked_notes=has_blocked_notes,
    )

    statuses_path = REPO_ROOT / args.statuses_path
    statuses_path.parent.mkdir(parents=True, exist_ok=True)
    tokens = statuses_path.read_text(encoding="utf-8").split() if statuses_path.is_file() else []
    tokens.append(status)
    with statuses_path.open("a", encoding="utf-8") as handle:
        handle.write(status + "\n")

    head_sha = str(checks.get("head_sha") or "")
    ledger_path = REPO_ROOT / args.ledger_path
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(f"iter {args.iteration} | {status} | {args.base_sha[:7]}..{head_sha[:7]} | {note}\n")

    stall_limit = int(args.stall_limit)
    if status == "DONE":
        drain_status = "DONE"
    elif status == "BLOCKED_ON_USER":
        drain_status = "BLOCKED_ON_USER"
    elif len(tokens) >= stall_limit and all(token in STALL_STATUSES for token in tokens[-stall_limit:]):
        drain_status = "STALLED"
    else:
        drain_status = "CONTINUE"

    summary = {
        "schema": "verified_iteration_drain_summary/v1",
        "drain_status": drain_status,
        "iterations": len(tokens),
        "statuses": tokens,
        "accepted_count": sum(1 for token in tokens if token in {"ACCEPTED", "DONE"}),
        "blocked_notes": sorted(path.name for path in blocked_dir.glob("BLOCKED-*.md")) if blocked_dir.is_dir() else [],
        "last_note": note,
    }
    summary_path = REPO_ROOT / args.summary_path
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    drain_status_path = REPO_ROOT / args.drain_status_path
    drain_status_path.parent.mkdir(parents=True, exist_ok=True)
    drain_status_path.write_text(drain_status + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [x] **Step 4: Run to verify pass**

Run: `pytest tests/test_verified_iteration_drain.py -q -k record`
Expected: 8 passed.

- [x] **Step 5: Commit**

```bash
git add workflows/library/scripts/record_verified_iteration.py tests/test_verified_iteration_drain.py
git commit -m "Add verified-iteration status recorder"
```

---

### Task 4: Prompts

**Files:**
- Create: `workflows/library/prompts/verified_iteration_drain/work.md`
- Create: `workflows/library/prompts/verified_iteration_drain/review_iteration.md`
- Create: `workflows/library/prompts/verified_iteration_drain/review_done.md`

No tests in this task (prompt-text assertions are forbidden); Task 6's runtime smoke exercises them end-to-end via fake providers, and Task 5's loader smoke validates references.

- [x] **Step 1: Write `work.md`**

```markdown
You are executing one iteration of an autonomous drain toward the consumed
target design.

Read the consumed work order, the target design, the ledger, any notes in the
blocked-notes directory, and the previous review findings or failing check
log when the work order names them.

Pick the most valuable piece of unfinished work toward the target design —
including undoing or replacing an earlier approach when the ledger shows it
is not converging. If the previous check log shows failing checks, restoring
them to green is the mandatory first task. The target design's non-goals and
the check commands are the scope boundary; there is no file-list fence.

Make verified progress: run the check commands from the work order yourself
and commit only work that passes. Stage files by explicit path; never use
`git add -A`, `git add .`, or `git commit -a`. Keep commit messages plain.

If something genuinely requires the user — credentials, environment, or an
intention only they can resolve — write a short `BLOCKED-<topic>.md` note in
the blocked-notes directory and continue with other actionable work.

Before finishing, write:
- the verdict file named by `worker_verdict_path`: `CONTINUE` (more work
  remains), `DONE` (the target design's acceptance criteria hold in the
  current checkout), or `BLOCKED_ON_USER` (nothing actionable remains
  without user input);
- one line to the file named by `worker_note_path` describing what you did
  or learned this iteration.
```

- [x] **Step 2: Write `review_iteration.md`**

```markdown
Review one iteration of work toward the consumed target design.

Read the consumed review package (commit list and diff), the target design,
and the ledger.

Approve only if the diff is correct, conforms to the target design, and does
not weaken verification: deleted or loosened checks and tests require
justification visible in the diff itself. Judge the outcome, not the
process; how the work was planned is not review scope.

Write `APPROVE` or `FINDINGS` to the file named by `review_decision_path` in
the consumed work order. When returning `FINDINGS`, write the concrete
findings to the file named by `review_findings_path`.
```

- [x] **Step 3: Write `review_done.md`**

```markdown
Judge whether the consumed target design's acceptance criteria hold in the
current checkout.

Read the target design and verify each acceptance criterion directly against
the repository, running commands where a criterion is runnable. The ledger
and prior reports are context, not evidence.

Write `APPROVE` or `REJECT` to the file named by `done_review_decision_path`
in the consumed work order. When rejecting, append each unmet criterion and
the evidence for it to the file named by `review_findings_path`.
```

- [x] **Step 4: Commit**

```bash
git add workflows/library/prompts/verified_iteration_drain
git commit -m "Add verified-iteration drain prompts"
```

---

### Task 5: Workflow YAML + loader smoke

**Files:**
- Create: `workflows/examples/verified_iteration_drain.yaml`
- Test: `tests/test_verified_iteration_drain.py`

**Interfaces:**
- Consumes: the three scripts (Tasks 1–3), three prompts (Task 4), and the existing `workflows/library/scripts/write_lisp_frontend_relpath_value.py` (unchanged reuse for the summary-path output).
- Produces workflow outputs `drain_status` and `drain_summary_path` consumed by Task 6's runtime tests.

- [x] **Step 1: Write the failing loader-smoke test** (append to the test module)

```python
def test_verified_iteration_drain_workflow_loads(tmp_path):
    loader = WorkflowLoader(ROOT)
    loader.load_bundle(ROOT / WORKFLOW)
    assert loader.error_count() == 0
```

Run: `pytest tests/test_verified_iteration_drain.py -q -k workflow_loads`
Expected: FAIL (file not found).

- [x] **Step 2: Write the workflow**

Create `workflows/examples/verified_iteration_drain.yaml`:

```yaml
version: "2.14"
name: "verified-iteration-drain"

context:
  workflow_model: "gpt-5.4"
  workflow_effort: "high"

inputs:
  target_design_path:
    type: relpath
    under: docs/design
    must_exist_target: true
  check_commands_path:
    type: relpath
    under: workflows
    must_exist_target: true
  drain_state_root:
    type: relpath
    under: state
    default: state/VERIFIED-ITERATION-DRAIN
  artifact_work_root:
    type: relpath
    under: artifacts/work
    default: artifacts/work/VERIFIED-ITERATION-DRAIN
  stall_limit:
    kind: scalar
    type: string
    default: "3"
  worker_provider:
    kind: scalar
    type: enum
    allowed: ["codex", "claude"]
    default: "claude"
  worker_model:
    kind: scalar
    type: string
    default: "fable"
  worker_effort:
    kind: scalar
    type: string
    default: "high"
  reviewer_provider:
    kind: scalar
    type: enum
    allowed: ["codex", "claude"]
    default: "claude"
  reviewer_model:
    kind: scalar
    type: string
    default: "fable"
  reviewer_effort:
    kind: scalar
    type: string
    default: "high"

providers:
  codex:
    command: ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check", "--model", "${model}", "--config", "reasoning_effort=${effort}"]
    input_mode: "stdin"
    defaults:
      model: "${context.workflow_model}"
      effort: "${context.workflow_effort}"
  claude:
    command: ["claude", "-p", "--model", "${model}", "--effort", "${effort}", "--permission-mode", "bypassPermissions"]
    input_mode: "stdin"
    defaults:
      model: "fable"
      effort: "high"

outputs:
  drain_status:
    kind: scalar
    type: enum
    allowed: ["CONTINUE", "DONE", "BLOCKED_ON_USER", "STALLED"]
    from:
      ref: root.steps.DrainVerifiedIterations.artifacts.drain_status
  drain_summary_path:
    type: relpath
    under: artifacts/work
    must_exist_target: true
    from:
      ref: root.steps.PublishSummaryPath.artifacts.drain_summary_path

steps:
  - name: DrainVerifiedIterations
    id: drain_verified_iterations
    repeat_until:
      id: verified_iteration
      max_iterations: 40
      outputs:
        drain_status:
          kind: scalar
          type: enum
          allowed: ["CONTINUE", "DONE", "BLOCKED_ON_USER", "STALLED"]
          from:
            ref: self.steps.RecordIteration.artifacts.drain_status
      condition:
        any_of:
          - compare:
              left:
                ref: self.outputs.drain_status
              op: eq
              right: DONE
          - compare:
              left:
                ref: self.outputs.drain_status
              op: eq
              right: BLOCKED_ON_USER
          - compare:
              left:
                ref: self.outputs.drain_status
              op: eq
              right: STALLED
      on_exhausted:
        outputs:
          drain_status: STALLED
      steps:
        - name: PrepareIteration
          id: prepare_iteration
          command:
            - python
            - workflows/library/scripts/prepare_verified_iteration.py
            - --drain-state-root
            - ${inputs.drain_state_root}
            - --artifact-work-root
            - ${inputs.artifact_work_root}
            - --target-design-path
            - ${inputs.target_design_path}
            - --check-commands-path
            - ${inputs.check_commands_path}
            - --iteration
            - ${loop.index}
            - --output
            - ${inputs.drain_state_root}/iterations/${loop.index}/work-order.json
          output_bundle:
            path: ${inputs.drain_state_root}/iterations/${loop.index}/work-order.json
            fields:
              - name: base_sha
                json_pointer: /base_sha
                type: string
              - name: work_order_path
                json_pointer: /work_order_path
                type: relpath
                under: state
                must_exist_target: true

        - name: Work
          id: work
          provider: ${inputs.worker_provider}
          provider_params:
            model: ${inputs.worker_model}
            effort: ${inputs.worker_effort}
          input_file: workflows/library/prompts/verified_iteration_drain/work.md
          timeout_sec: 7200
          depends_on:
            required:
              - ${inputs.drain_state_root}/iterations/${loop.index}/work-order.json
              - ${inputs.target_design_path}
              - ${inputs.artifact_work_root}/ledger.md
            inject:
              mode: content
          expected_outputs:
            - name: worker_verdict
              path: ${inputs.drain_state_root}/iterations/${loop.index}/worker-verdict.txt
              type: enum
              allowed: ["CONTINUE", "DONE", "BLOCKED_ON_USER"]

        - name: VerifyIteration
          id: verify_iteration
          command:
            - python
            - workflows/library/scripts/run_verified_iteration_checks.py
            - --check-commands-path
            - ${inputs.check_commands_path}
            - --base-sha
            - ${steps.PrepareIteration.artifacts.base_sha}
            - --iteration-dir
            - ${inputs.drain_state_root}/iterations/${loop.index}
            - --output
            - ${inputs.drain_state_root}/iterations/${loop.index}/checks-result.json
          output_bundle:
            path: ${inputs.drain_state_root}/iterations/${loop.index}/checks-result.json
            fields:
              - name: verify_status
                json_pointer: /verify_status
                type: enum
                allowed: ["GREEN", "RED"]
              - name: commits_landed
                json_pointer: /commits_landed
                type: enum
                allowed: ["true", "false"]
              - name: head_sha
                json_pointer: /head_sha
                type: string
              - name: review_package_path
                json_pointer: /review_package_path
                type: relpath
                under: state
                must_exist_target: true

        - name: ReviewIteration
          id: review_iteration
          when:
            all_of:
              - compare:
                  left:
                    ref: self.steps.VerifyIteration.artifacts.verify_status
                  op: eq
                  right: GREEN
              - compare:
                  left:
                    ref: self.steps.VerifyIteration.artifacts.commits_landed
                  op: eq
                  right: "true"
          provider: ${inputs.reviewer_provider}
          provider_params:
            model: ${inputs.reviewer_model}
            effort: ${inputs.reviewer_effort}
          input_file: workflows/library/prompts/verified_iteration_drain/review_iteration.md
          timeout_sec: 1800
          depends_on:
            required:
              - ${inputs.drain_state_root}/iterations/${loop.index}/work-order.json
              - ${inputs.drain_state_root}/iterations/${loop.index}/review-package.md
              - ${inputs.target_design_path}
              - ${inputs.artifact_work_root}/ledger.md
            inject:
              mode: content
          expected_outputs:
            - name: review_decision
              path: ${inputs.drain_state_root}/iterations/${loop.index}/review-decision.txt
              type: enum
              allowed: ["APPROVE", "FINDINGS"]

        - name: ReviewDoneClaim
          id: review_done_claim
          when:
            all_of:
              - compare:
                  left:
                    ref: self.steps.Work.artifacts.worker_verdict
                  op: eq
                  right: DONE
              - compare:
                  left:
                    ref: self.steps.VerifyIteration.artifacts.verify_status
                  op: eq
                  right: GREEN
          provider: ${inputs.reviewer_provider}
          provider_params:
            model: ${inputs.reviewer_model}
            effort: ${inputs.reviewer_effort}
          input_file: workflows/library/prompts/verified_iteration_drain/review_done.md
          timeout_sec: 3600
          depends_on:
            required:
              - ${inputs.drain_state_root}/iterations/${loop.index}/work-order.json
              - ${inputs.target_design_path}
            inject:
              mode: content
          expected_outputs:
            - name: done_review_decision
              path: ${inputs.drain_state_root}/iterations/${loop.index}/done-review-decision.txt
              type: enum
              allowed: ["APPROVE", "REJECT"]

        - name: RecordIteration
          id: record_iteration
          command:
            - python
            - workflows/library/scripts/record_verified_iteration.py
            - --iteration
            - ${loop.index}
            - --base-sha
            - ${steps.PrepareIteration.artifacts.base_sha}
            - --checks-result-path
            - ${inputs.drain_state_root}/iterations/${loop.index}/checks-result.json
            - --review-decision-path
            - ${inputs.drain_state_root}/iterations/${loop.index}/review-decision.txt
            - --done-review-decision-path
            - ${inputs.drain_state_root}/iterations/${loop.index}/done-review-decision.txt
            - --worker-verdict-path
            - ${inputs.drain_state_root}/iterations/${loop.index}/worker-verdict.txt
            - --worker-note-path
            - ${inputs.drain_state_root}/iterations/${loop.index}/worker-note.txt
            - --blocked-notes-dir
            - ${inputs.artifact_work_root}/blocked
            - --ledger-path
            - ${inputs.artifact_work_root}/ledger.md
            - --statuses-path
            - ${inputs.drain_state_root}/statuses.txt
            - --stall-limit
            - ${inputs.stall_limit}
            - --summary-path
            - ${inputs.artifact_work_root}/drain-summary.json
            - --drain-status-path
            - ${inputs.drain_state_root}/iterations/${loop.index}/drain-status.txt
          expected_outputs:
            - name: drain_status
              path: ${inputs.drain_state_root}/iterations/${loop.index}/drain-status.txt
              type: enum
              allowed: ["CONTINUE", "DONE", "BLOCKED_ON_USER", "STALLED"]

  - name: PublishSummaryPath
    id: publish_summary_path
    command:
      - python
      - workflows/library/scripts/write_lisp_frontend_relpath_value.py
      - --value
      - ${inputs.artifact_work_root}/drain-summary.json
      - --under
      - artifacts/work
      - --output
      - ${inputs.drain_state_root}/drain-summary-path.txt
    expected_outputs:
      - name: drain_summary_path
        path: ${inputs.drain_state_root}/drain-summary-path.txt
        type: relpath
        under: artifacts/work
        must_exist_target: true
```

- [x] **Step 3: Run loader smoke to verify pass**

Run: `pytest tests/test_verified_iteration_drain.py -q -k workflow_loads`
Expected: PASS with zero loader errors. If the loader rejects a construct, fix the YAML against the working idioms in `workflows/examples/lisp_frontend_design_delta_drain.yaml` — do not change the loader.

- [x] **Step 4: Commit**

```bash
git add workflows/examples/verified_iteration_drain.yaml tests/test_verified_iteration_drain.py
git commit -m "Add verified-iteration drain workflow"
```

---

### Task 6: Runtime smoke with fake providers

**Files:**
- Test: `tests/test_verified_iteration_drain.py`

**Interfaces:**
- Consumes everything from Tasks 1–5. Reuses `_bundle_context_dict` imported from `tests/test_lisp_frontend_autonomous_drain_runtime` (already imported in Task 1's header). If that cross-module import fails at collection time, inline the two small helpers (`_thaw`, `_bundle_context_dict`) instead — they are pure functions.

- [x] **Step 1: Write the failing runtime tests** (append to the test module)

```python
def _copy_drain_runtime_files(workspace: Path) -> Path:
    for relpath in [
        WORKFLOW,
        PREPARE,
        CHECKS,
        RECORD,
        "workflows/library/scripts/write_lisp_frontend_relpath_value.py",
        "workflows/library/prompts/verified_iteration_drain/work.md",
        "workflows/library/prompts/verified_iteration_drain/review_iteration.md",
        "workflows/library/prompts/verified_iteration_drain/review_done.md",
    ]:
        dest = workspace / relpath
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text((ROOT / relpath).read_text(encoding="utf-8"), encoding="utf-8")
    _git(workspace, "add", "workflows")
    _git(workspace, "commit", "-qm", "add drain runtime files")
    return workspace / WORKFLOW


def _drain_inputs() -> dict:
    return {
        "target_design_path": "docs/design/pilot_target.md",
        "check_commands_path": "workflows/examples/inputs/pilot_checks.json",
        "stall_limit": "2",
    }


def _run_drain_with_providers(workspace: Path, provider_sequence) -> dict:
    workflow_path = workspace / WORKFLOW
    loader = WorkflowLoader(workspace)
    workflow = loader.load(workflow_path)
    bound_inputs = bind_workflow_inputs(workflow_input_contracts(workflow), _drain_inputs(), workspace)
    state_manager = StateManager(workspace=workspace, run_id="test-run")
    state_manager.initialize(
        workflow_path.relative_to(workspace).as_posix(),
        _bundle_context_dict(workflow),
        bound_inputs=bound_inputs,
    )
    executor = WorkflowExecutor(workflow, workspace, state_manager)
    call_index = {"value": 0}

    def _prepare_invocation(_self, *args, **kwargs):
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content", "")), None

    def _execute(_self, _invocation, **kwargs):
        assert call_index["value"] < len(provider_sequence), f"unexpected provider call: {kwargs.get('step_name')}"
        expected_step, writer = provider_sequence[call_index["value"]]
        actual_step = str(kwargs.get("step_name") or "")
        assert expected_step in actual_step, f"expected {expected_step}, got {actual_step}"
        call_index["value"] += 1
        writer(workspace)
        return SimpleNamespace(
            exit_code=0, stdout=b"ok", stderr=b"", duration_ms=1, error=None,
            missing_placeholders=None, invalid_prompt_placeholder=False,
            raw_stdout=None, normalized_stdout=None, provider_session=None,
        )

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        state = executor.execute()
    assert call_index["value"] == len(provider_sequence)
    return state


def _latest_iteration_dir(workspace: Path) -> Path:
    iterations = sorted((workspace / STATE_ROOT / "iterations").iterdir(), key=lambda p: int(p.name))
    return iterations[-1]


def _worker_commits_and_claims_done(workspace: Path) -> None:
    (workspace / "hello.txt").write_text("hi\n", encoding="utf-8")
    _git(workspace, "add", "hello.txt")
    _git(workspace, "commit", "-qm", "add hello per target design")
    iteration_dir = _latest_iteration_dir(workspace)
    (iteration_dir / "worker-verdict.txt").write_text("DONE\n", encoding="utf-8")
    (iteration_dir / "worker-note.txt").write_text("created hello.txt\n", encoding="utf-8")


def _worker_makes_no_progress(workspace: Path) -> None:
    iteration_dir = _latest_iteration_dir(workspace)
    (iteration_dir / "worker-verdict.txt").write_text("CONTINUE\n", encoding="utf-8")
    (iteration_dir / "worker-note.txt").write_text("could not find a next step\n", encoding="utf-8")


def _worker_blocks_on_user(workspace: Path) -> None:
    blocked = workspace / WORK_ROOT / "blocked/BLOCKED-credentials.md"
    blocked.parent.mkdir(parents=True, exist_ok=True)
    blocked.write_text("Need the API token only the user holds.\n", encoding="utf-8")
    iteration_dir = _latest_iteration_dir(workspace)
    (iteration_dir / "worker-verdict.txt").write_text("BLOCKED_ON_USER\n", encoding="utf-8")
    (iteration_dir / "worker-note.txt").write_text("all remaining work needs the token\n", encoding="utf-8")


def _reviewer_approves_iteration(workspace: Path) -> None:
    (_latest_iteration_dir(workspace) / "review-decision.txt").write_text("APPROVE\n", encoding="utf-8")


def _reviewer_approves_done(workspace: Path) -> None:
    (_latest_iteration_dir(workspace) / "done-review-decision.txt").write_text("APPROVE\n", encoding="utf-8")


def test_drain_completes_in_one_verified_iteration(tmp_path):
    workspace = _init_workspace(tmp_path)
    _copy_drain_runtime_files(workspace)
    _run_drain_with_providers(
        workspace,
        [
            ("Work", _worker_commits_and_claims_done),
            ("ReviewIteration", _reviewer_approves_iteration),
            ("ReviewDoneClaim", _reviewer_approves_done),
        ],
    )
    summary = json.loads((workspace / WORK_ROOT / "drain-summary.json").read_text(encoding="utf-8"))
    assert summary["drain_status"] == "DONE"
    assert summary["statuses"] == ["DONE"]
    ledger = (workspace / WORK_ROOT / "ledger.md").read_text(encoding="utf-8")
    assert "DONE" in ledger and "created hello.txt" in ledger


def test_drain_stalls_after_consecutive_no_change_iterations(tmp_path):
    workspace = _init_workspace(tmp_path)
    _copy_drain_runtime_files(workspace)
    _run_drain_with_providers(
        workspace,
        [
            ("Work", _worker_makes_no_progress),
            ("Work", _worker_makes_no_progress),
        ],
    )
    summary = json.loads((workspace / WORK_ROOT / "drain-summary.json").read_text(encoding="utf-8"))
    assert summary["drain_status"] == "STALLED"
    assert summary["statuses"] == ["NO_CHANGE", "NO_CHANGE"]


def test_drain_exits_blocked_on_user_with_notes(tmp_path):
    workspace = _init_workspace(tmp_path)
    _copy_drain_runtime_files(workspace)
    _run_drain_with_providers(workspace, [("Work", _worker_blocks_on_user)])
    summary = json.loads((workspace / WORK_ROOT / "drain-summary.json").read_text(encoding="utf-8"))
    assert summary["drain_status"] == "BLOCKED_ON_USER"
    assert summary["blocked_notes"] == ["BLOCKED-credentials.md"]
```

- [x] **Step 2: Run to verify current state**

Run: `pytest tests/test_verified_iteration_drain.py -q -k drain_`
Expected: 3 failures or errors initially; iterate on wiring mismatches (step names, artifact refs, gating) until green. Fix mismatches in the YAML/scripts, never by weakening assertions. Two known risk points and their intended resolutions: (a) if `${loop.index}` numbering starts at 1 rather than 0, adjust `_latest_iteration_dir` usage is already index-agnostic — but confirm `iterations/<n>` paths line up with `prepare --iteration ${loop.index}`; (b) if the executor requires provider steps to have `output_capture` or forbids skipped-step artifact refs, mirror how `workflows/examples/lisp_frontend_design_delta_drain.yaml` handles the same construct.

- [x] **Step 3: Run the whole module + collection**

Run: `pytest tests/test_verified_iteration_drain.py -q`
Expected: all tests pass (18 total).
Run: `pytest tests/test_verified_iteration_drain.py --collect-only -q | tail -2`
Expected: 18 tests collected.

- [x] **Step 4: Commit**

```bash
git add tests/test_verified_iteration_drain.py
git commit -m "Add verified-iteration drain runtime smoke tests"
```

---

### Task 7: Documentation routing

**Files:**
- Modify: `docs/index.md` — add one routing line for `docs/design/verified_iteration_drain.md` in the design-doc section (match surrounding format).
- Modify: `docs/capability_status_matrix.md` — add one row: verified-iteration drain, status "Implemented (pilot)", pointing at the workflow and design doc (match surrounding row format exactly).

- [x] **Step 1: Make both edits** (read each file's neighboring entries first and copy their format precisely; one line each)

- [x] **Step 2: Verify**

Run: `pytest tests/test_verified_iteration_drain.py -q`
Expected: all pass (docs changes must not affect tests).

- [x] **Step 3: Commit**

```bash
git add docs/index.md docs/capability_status_matrix.md
git commit -m "Route verified-iteration drain docs"
```

---

## Final Verification

- `pytest tests/test_verified_iteration_drain.py -q` → all green.
- `pytest tests/test_verified_iteration_drain.py --collect-only -q` → collects cleanly.
- Loader smoke is covered by `test_verified_iteration_drain_workflow_loads`.
- Confirm no `lisp_frontend_*` file was touched: `git diff --stat <plan-base>..HEAD -- 'workflows/library/lisp_frontend*' 'workflows/library/prompts/lisp_frontend*'` → empty.

## Out of Scope (recorded deliberately)

- Running a real pilot against a live target design (follow-up: pick a small real target, author its check-commands file, launch via tmux per AGENTS.md).
- Roadmap/approval gate composition in front of the loop.
- Any change to the `lisp_frontend_*` family.
