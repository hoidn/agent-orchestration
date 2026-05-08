# NeurIPS Workflow Test Mirroring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mirror the reusable PtychoPINN NeurIPS backlog-drain workflow tests into `agent-orchestration` so shared workflow behavior is guarded locally without importing PtychoPINN paper/science-specific assertions.

**Architecture:** Keep `agent-orchestration` as the owner of reusable workflow infrastructure tests: helper scripts, workflow YAML contracts, provider routing, review/fix loop routing, and a small generic runtime fixture. Leave PtychoPINN-only tests downstream when they depend on CDI/CNS/BRDT/WaveBench evidence, paper tables, or project roadmap semantics.

**Tech Stack:** Python 3.11+, pytest, PyYAML, subprocess-based script tests, orchestrator CLI smoke tests.

---

## Scope Boundary

Port/mirror only behavior that belongs to the reusable NeurIPS workflow library:

- `workflows/examples/neurips_steered_backlog_drain.yaml`
- `workflows/library/neurips_backlog_*.yaml`
- `workflows/library/neurips_selected_backlog_item.yaml`
- `workflows/library/scripts/*neurips*.py`
- `workflows/library/scripts/run_neurips_backlog_checks.py`
- `workflows/library/prompts/neurips_backlog_*/*.md`

Do not port tests whose pass condition depends on PtychoPINN-specific scientific artifacts:

- `docs/plans/NEURIPS-HYBRID-RESNET-2026/...` evidence content beyond generic fixture paths.
- CDI/CNS/BRDT/WaveBench metrics, tables, figures, or paper-refresh outputs.
- PtychoPINN-specific backlog priorities, phase labels, or study claims.
- Any test that requires the real PtychoPINN repo or GPU/training artifacts.

## File Structure

- Modify: `workflows/library/scripts/run_neurips_backlog_checks.py`
  - Preserve existing matching `log_path` metadata when rerunning checks into a report path that already has archived log references.
  - Continue returning process exit `0` even when individual checks fail; failure is represented in JSON.

- Create: `tests/test_neurips_backlog_checks_runner.py`
  - Local, reusable tests for the check runner.
  - Covers failure reporting and `log_path` preservation.

- Modify: `tests/test_major_project_workflows.py`
  - Add missing structural assertions already mirrored conceptually from PtychoPINN:
    - top-level drain continues after selected-item blocks
    - selected item does not block on implementation review `REVISE`
    - implementation phase routes `REVISE` to `FixImplementation`
    - no `WAITING` terminal implementation state remains
  - If equivalent assertions already exist, tighten only the missing checks and avoid duplicate brittle prompt-text assertions.

- Create: `tests/fixtures/neurips_steered_backlog/`
  - Minimal generic fixture copied in spirit from PtychoPINN, with neutral fake backlog items and neutral roadmap/design/steering files.
  - No PtychoPINN paper evidence names except the workflow's generic `NEURIPS-HYBRID-RESNET-2026` state-root convention where the reusable scripts require it.

- Create: `tests/test_neurips_steered_backlog_runtime.py`
  - A small reusable runtime smoke suite using the generic fixture:
    - happy path completes one eligible fake item
    - explicit selected-item block does not kill the drain
    - stale selector/in-progress state is recovered or ignored according to the reusable recovery contract
  - Keep provider calls stubbed/fake; do not invoke real Codex/Claude providers.

- Optional Modify: `tests/test_neurips_backlog_roadmap_gate.py`, `tests/test_neurips_selected_item_materialize.py`, `tests/test_neurips_selected_item_reconcile.py`
  - Only add missing helper-script assertions from downstream if not already covered locally.
  - Do not duplicate tests that already exist under different local names.

## Task 1: Inventory Existing Coverage

**Files:**
- Read: `tests/test_neurips_backlog_roadmap_gate.py`
- Read: `tests/test_neurips_selected_item_materialize.py`
- Read: `tests/test_neurips_selected_item_reconcile.py`
- Read: `tests/test_major_project_workflows.py`
- Read: `/home/ollie/Documents/PtychoPINN/tests/studies/test_neurips_steered_backlog_helpers.py`
- Read: `/home/ollie/Documents/PtychoPINN/tests/studies/test_neurips_steered_backlog_workflow.py`
- Read: `/home/ollie/Documents/PtychoPINN/tests/studies/test_neurips_steered_backlog_runtime.py`

- [ ] **Step 1: Generate the downstream test-name inventory**

Run:

```bash
rg -n '^def test_' \
  /home/ollie/Documents/PtychoPINN/tests/studies/test_neurips_steered_backlog_helpers.py \
  /home/ollie/Documents/PtychoPINN/tests/studies/test_neurips_steered_backlog_workflow.py \
  /home/ollie/Documents/PtychoPINN/tests/studies/test_neurips_steered_backlog_runtime.py
```

Expected: list of downstream helper/workflow/runtime test names.

- [ ] **Step 2: Generate the local NeurIPS test-name inventory**

Run:

```bash
rg -n '^def test_.*neurips|neurips_.*def test_' tests
```

Expected: local test names in `tests/test_neurips_*.py`, `tests/test_major_project_workflows.py`, and provider-routing tests.

- [ ] **Step 3: Classify each downstream test**

Create a scratch checklist, not a committed artifact, with three buckets:

```text
PORT: reusable infra behavior missing locally
ALREADY_COVERED: equivalent local test exists
KEEP_DOWNSTREAM: PtychoPINN-only evidence/science/project-roadmap behavior
```

Expected initial classification:

```text
PORT:
- check-runner failure report
- check-runner log_path preservation
- generic selected-item block does not kill whole drain, if local assertion is missing/too shallow
- generic REVISE routes into FixImplementation, if local assertion is missing/too shallow
- one generic runtime smoke fixture, if local runtime coverage is absent

ALREADY_COVERED:
- selected-item manifest gate behavior
- missing plan target invalidation
- active/in-progress/done reconciliation
- roadmap gate invalid-item behavior
- block-scalar check_commands acceptance
- gap-draft validator core behavior

KEEP_DOWNSTREAM:
- tests that mention real PtychoPINN paper evidence summaries, metrics, or table/figure outputs
- tests that depend on PtychoPINN's live backlog priorities
```

## Task 2: Add Local Check-Runner Tests First

**Files:**
- Create: `tests/test_neurips_backlog_checks_runner.py`
- Modify: `workflows/library/scripts/run_neurips_backlog_checks.py`

- [ ] **Step 1: Write the failing failure-report test**

Create `tests/test_neurips_backlog_checks_runner.py` with:

```python
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "workflows/library/scripts/run_neurips_backlog_checks.py"


def _run(tmp_path: Path, checks: list[str], report_name: str = "report.json") -> tuple[subprocess.CompletedProcess[str], Path]:
    checks_path = tmp_path / "state/checks.json"
    checks_path.parent.mkdir(parents=True, exist_ok=True)
    checks_path.write_text(json.dumps(checks, indent=2) + "\n", encoding="utf-8")
    report_path = tmp_path / f"artifacts/checks/{report_name}"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--checks-path",
            str(checks_path),
            "--report-path",
            str(report_path),
            "--cwd",
            str(tmp_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result, report_path


def test_run_neurips_backlog_checks_reports_failures_without_process_failure(tmp_path: Path) -> None:
    result, report_path = _run(
        tmp_path,
        [
            f'{sys.executable} -c "print(\'ok\')"',
            f'{sys.executable} -c "import sys; sys.exit(3)"',
        ],
    )

    assert result.returncode == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "FAIL"
    assert report["failed_count"] == 1
    assert report["command_count"] == 2
    assert report["results"][1]["exit_code"] == 3
```

- [ ] **Step 2: Run the new test and verify it passes or fails only for missing file**

Run:

```bash
pytest -q tests/test_neurips_backlog_checks_runner.py::test_run_neurips_backlog_checks_reports_failures_without_process_failure
```

Expected: PASS if existing behavior is intact.

- [ ] **Step 3: Write the failing `log_path` preservation test**

Append:

```python
def test_run_neurips_backlog_checks_preserves_existing_matching_log_paths(tmp_path: Path) -> None:
    command = f'{sys.executable} -c "print(\'ok\')"'
    checks_path = tmp_path / "state/checks.json"
    checks_path.parent.mkdir(parents=True, exist_ok=True)
    checks_path.write_text(json.dumps([command], indent=2) + "\n", encoding="utf-8")

    archived_log = tmp_path / "artifacts/work/checks/ok.log"
    archived_log.parent.mkdir(parents=True, exist_ok=True)
    archived_log.write_text("archived ok\n", encoding="utf-8")

    report_path = tmp_path / "artifacts/checks/report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {
                "status": "PASS",
                "failed_count": 0,
                "command_count": 1,
                "checks_path": checks_path.as_posix(),
                "results": [
                    {
                        "index": 1,
                        "command": command,
                        "exit_code": 0,
                        "log_path": archived_log.relative_to(tmp_path).as_posix(),
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--checks-path",
            str(checks_path),
            "--report-path",
            str(report_path),
            "--cwd",
            str(tmp_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["results"][0]["command"] == command
    assert report["results"][0]["log_path"] == archived_log.relative_to(tmp_path).as_posix()
```

- [ ] **Step 4: Run the preservation test and verify it fails before implementation**

Run:

```bash
pytest -q tests/test_neurips_backlog_checks_runner.py::test_run_neurips_backlog_checks_preserves_existing_matching_log_paths
```

Expected before implementation: FAIL with `KeyError: 'log_path'` or equivalent.

- [ ] **Step 5: Implement minimal preservation logic**

Modify `workflows/library/scripts/run_neurips_backlog_checks.py`:

```python
def _existing_log_paths(report_path: Path, commands: list[str], cwd: Path) -> dict[int, str]:
    if not report_path.is_file():
        return {}
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    results = payload.get("results")
    if not isinstance(results, list) or len(results) != len(commands):
        return {}
    if [item.get("command") if isinstance(item, dict) else None for item in results] != commands:
        return {}

    log_paths: dict[int, str] = {}
    for item in results:
        if not isinstance(item, dict):
            return {}
        index = item.get("index")
        log_path = item.get("log_path")
        if not isinstance(index, int) or not isinstance(log_path, str) or not log_path.strip():
            continue
        candidate = Path(log_path)
        if not candidate.is_absolute():
            candidate = cwd / candidate
        if candidate.is_file():
            log_paths[index] = log_path
    return log_paths
```

Then call it before executing checks:

```python
preserved_log_paths = _existing_log_paths(report_path, checks, cwd)
```

And attach it per result:

```python
if index in preserved_log_paths:
    result["log_path"] = preserved_log_paths[index]
```

- [ ] **Step 6: Run the check-runner tests**

Run:

```bash
pytest -q tests/test_neurips_backlog_checks_runner.py
```

Expected: both tests PASS.

## Task 3: Port Missing Workflow-Structure Assertions

**Files:**
- Modify: `tests/test_major_project_workflows.py`

- [ ] **Step 1: Inspect existing NeurIPS assertions**

Run:

```bash
rg -n "neurips|ImplementationReviewLoop|FixImplementation|WAITING|RunSelectedItem|BLOCKED" tests/test_major_project_workflows.py
```

Expected: identify whether the downstream workflow assertions are already covered.

- [ ] **Step 2: Add only missing structural assertions**

If missing, add tests equivalent to:

```python
def test_neurips_implementation_review_revise_routes_to_fix() -> None:
    workflow = _load_workflow("workflows/library/neurips_backlog_implementation_phase.yaml")
    loop = _find_step(workflow, "ImplementationReviewLoop")
    fix_step = _find_nested_step(loop, "FixImplementation")
    assert fix_step["when"]["compare"]["right"] == "REVISE"
    assert fix_step["provider"] == "${inputs.implementation_fix_provider}"
```

```python
def test_neurips_top_level_drain_continues_after_selected_item_blocks() -> None:
    workflow = _load_workflow("workflows/examples/neurips_steered_backlog_drain.yaml")
    blocked_case = _find_case_or_branch(workflow, "BLOCKED")
    assert "WriteDrainContinue" in str(blocked_case) or "selected_item_continue" in str(blocked_case)
```

Use existing helper functions in `tests/test_major_project_workflows.py`; do not invent a second YAML-walking helper if the file already has one.

- [ ] **Step 3: Avoid prompt-text assertions**

Before committing, confirm no new test asserts literal prompt prose:

```bash
git diff -- tests/test_major_project_workflows.py | rg "prompt|asset_file|partial progress|exact phrase" || true
```

Expected: references to `asset_file` paths are fine; literal prompt prose assertions are absent.

- [ ] **Step 4: Run targeted workflow tests**

Run:

```bash
pytest -q tests/test_major_project_workflows.py -k "neurips"
```

Expected: PASS.

## Task 4: Add Generic Runtime Fixture Only If Needed

**Files:**
- Create: `tests/fixtures/neurips_steered_backlog/docs/index.md`
- Create: `tests/fixtures/neurips_steered_backlog/docs/steering.md`
- Create: `tests/fixtures/neurips_steered_backlog/docs/backlog/roadmap_gate.json`
- Create: `tests/fixtures/neurips_steered_backlog/docs/backlog/active/2026-04-22-ready-item.md`
- Create: `tests/fixtures/neurips_steered_backlog/docs/backlog/active/2026-04-22-blocked-item.md`
- Create: `tests/fixtures/neurips_steered_backlog/docs/plans/2026-04-20-neurips-hybrid-resnet-submission-design.md`
- Create: `tests/fixtures/neurips_steered_backlog/docs/plans/2026-04-20-neurips-hybrid-resnet-submission-roadmap.md`
- Create: `tests/fixtures/neurips_steered_backlog/state/NEURIPS-HYBRID-RESNET-2026/progress_ledger.json`
- Create: `tests/test_neurips_steered_backlog_runtime.py`

- [ ] **Step 1: Check if existing local runtime tests already cover the fixture need**

Run:

```bash
rg -n "neurips_steered_backlog_drain|orchestrator run|provider_stub|fake provider|RunSelectedItem" tests
```

Expected: if a local smoke already exercises the full drain with fake providers, skip this task or add only the missing scenario.

- [ ] **Step 2: Create neutral fixture files**

Use generic text only. Backlog frontmatter should include:

```yaml
---
id: 2026-04-22-ready-item
title: Ready Generic Item
status: active
priority: 10
phase: phase-2
plan_path: docs/plans/legacy-ready-plan.md
check_commands:
  - python -m json.tool docs/backlog/roadmap_gate.json
---
```

Do not copy PtychoPINN evidence names, metrics, or paper-result paths.

- [ ] **Step 3: Write one runtime smoke**

The smoke should:

1. copy the fixture into `tmp_path`
2. copy the relevant workflow YAML/scripts/prompts into `tmp_path`
3. configure fake providers that write the expected output artifacts
4. run:

```bash
python -m orchestrator run workflows/examples/neurips_steered_backlog_drain.yaml \
  --input steering_path=docs/steering.md \
  --input design_path=docs/plans/2026-04-20-neurips-hybrid-resnet-submission-design.md \
  --input roadmap_path=docs/plans/2026-04-20-neurips-hybrid-resnet-submission-roadmap.md \
  --input roadmap_gate_path=docs/backlog/roadmap_gate.json \
  --input progress_ledger_path=state/NEURIPS-HYBRID-RESNET-2026/progress_ledger.json
```

Expected assertions:

```python
assert (workspace / "docs/backlog/done/2026-04-22-ready-item.md").is_file()
checks_report = json.loads((workspace / "artifacts/checks/NEURIPS-HYBRID-RESNET-2026/backlog/2026-04-22-ready-item-checks.json").read_text())
assert checks_report["status"] == "PASS"
```

- [ ] **Step 4: Add one blocked-item continuation smoke**

Use a fake selected-item provider or fixture outcome that writes a semantic `BLOCKED` state. Assert the top-level drain continues to a next iteration or writes the expected drain summary rather than failing the entire workflow process.

- [ ] **Step 5: Run runtime smoke tests**

Run:

```bash
pytest -q tests/test_neurips_steered_backlog_runtime.py
```

Expected: PASS.

## Task 5: Verify Cross-Repo Sync Expectations

**Files:**
- Compare: `/home/ollie/Documents/PtychoPINN/workflows/library/scripts/run_neurips_backlog_checks.py`
- Compare: `workflows/library/scripts/run_neurips_backlog_checks.py`
- Compare: `/home/ollie/Documents/PtychoPINN/tests/studies/test_neurips_steered_backlog_helpers.py`
- Compare: local test files added above

- [ ] **Step 1: Confirm reusable script is synced**

Run:

```bash
diff -u \
  workflows/library/scripts/run_neurips_backlog_checks.py \
  /home/ollie/Documents/PtychoPINN/workflows/library/scripts/run_neurips_backlog_checks.py
```

Expected: no output, unless PtychoPINN has intentionally downstream-only comments.

- [ ] **Step 2: Confirm local tests cover the reusable downstream behavior**

Run:

```bash
pytest -q \
  tests/test_neurips_backlog_checks_runner.py \
  tests/test_neurips_backlog_roadmap_gate.py \
  tests/test_neurips_selected_item_materialize.py \
  tests/test_neurips_selected_item_reconcile.py \
  tests/test_major_project_workflows.py -k "neurips"
```

Expected: PASS.

- [ ] **Step 3: Confirm downstream tests still pass for mirrored behavior**

Run from PtychoPINN:

```bash
cd /home/ollie/Documents/PtychoPINN
pytest -q tests/studies/test_neurips_steered_backlog_helpers.py -k "run_neurips_backlog_checks"
```

Expected: PASS.

## Task 6: Commit

**Files:**
- Add/modify only the reusable script/tests/fixtures identified above.
- Do not stage unrelated dirty files such as generated repo dumps, scratch files, or unrelated backlog items.

- [ ] **Step 1: Review diff**

Run:

```bash
git diff -- \
  workflows/library/scripts/run_neurips_backlog_checks.py \
  tests/test_neurips_backlog_checks_runner.py \
  tests/test_major_project_workflows.py \
  tests/test_neurips_steered_backlog_runtime.py \
  tests/fixtures/neurips_steered_backlog
```

Expected: scoped diff only.

- [ ] **Step 2: Check whitespace**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 3: Stage scoped files**

Run:

```bash
git add \
  workflows/library/scripts/run_neurips_backlog_checks.py \
  tests/test_neurips_backlog_checks_runner.py \
  tests/test_major_project_workflows.py \
  tests/test_neurips_steered_backlog_runtime.py \
  tests/fixtures/neurips_steered_backlog
```

If optional runtime files were not created, omit them from `git add`.

- [ ] **Step 4: Commit**

Run:

```bash
git commit -m "test: mirror reusable neurips workflow coverage"
```

Expected: commit succeeds with only scoped reusable workflow coverage changes.

## Non-Goals

- Do not port PtychoPINN paper-evidence tests into `agent-orchestration`.
- Do not assert literal prompt prose.
- Do not require real provider CLIs, GPUs, training outputs, or paper artifacts.
- Do not alter workflow behavior unless a failing local test proves the reusable contract is broken.
