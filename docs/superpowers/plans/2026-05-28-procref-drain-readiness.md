# ProcRef Drain Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the focused ProcRef drain honest end-to-end before relaunch by carrying target/baseline semantics and ProcRef evidence namespaces through the workflow stack.

**Architecture:** Keep the existing full Lisp frontend drain working unchanged, but add the minimal parameters needed for design-delta runs. The ProcRef wrapper remains a thin successor workflow, while shared library workflows and helper scripts receive explicit `target_design_path`, `baseline_design_path`, and artifact-root inputs with defaults that preserve the old full-drain behavior.

**Tech Stack:** Agent-orchestration DSL v2.14 YAML, Python helper scripts, pytest runtime fixture tests, Codex provider prompts.

---

## File Structure

- Modify `workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml`
  - Pass real target/baseline inputs to the imported drain stack.
  - Use a ProcRef-specific backlog root by default.
  - Pass ProcRef artifact roots through to work-item execution.

- Modify `workflows/examples/lisp_frontend_autonomous_drain.yaml`
  - Add optional `target_design_path`, `baseline_design_path`, `artifact_work_root`, `artifact_checks_root`, and `artifact_review_root` inputs.
  - Preserve existing `full_design_path` / `mvp_design_path` defaults for backward compatibility.
  - Pass target/baseline and artifact roots to selector, design-gap architect, and work-item subworkflows.

- Modify `workflows/library/lisp_frontend_selector.v214.yaml`
  - Accept `target_design_path` and `baseline_design_path`.
  - Publish/consume `target_design` and `baseline_design` artifacts.
  - Use a new target/baseline selector prompt.

- Create `workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md`
  - Clear selector rule: target delta is active scope, baseline is compatibility constraint.

- Modify `workflows/library/lisp_frontend_design_gap_architect.v214.yaml`
  - Accept target/baseline inputs.
  - Consume/inject target and baseline docs.
  - Keep the already-fixed `architecture_index_root` behavior.

- Modify design-gap architect prompts:
  - `workflows/library/prompts/lisp_frontend_design_gap_architect/draft_implementation_architecture.md`
  - `workflows/library/prompts/lisp_frontend_design_gap_architect/review_implementation_architecture.md`
  - `workflows/library/prompts/lisp_frontend_design_gap_architect/revise_implementation_architecture.md`
  - Replace full/MVP wording and old hard-coded examples with target/baseline wording and target-path placeholders.

- Modify `workflows/library/lisp_frontend_work_item.v214.yaml`
  - Accept target/baseline and artifact root inputs.
  - Pass target/baseline into plan and implementation phases.
  - Pass artifact roots into `materialize_lisp_frontend_work_item_inputs.py`.

- Modify `workflows/library/lisp_frontend_plan_phase.v214.yaml`
  - Accept target/baseline inputs while retaining old aliases if needed.
  - Publish/consume target/baseline artifacts.
  - Update prompt consume names.

- Modify plan prompts:
  - `workflows/library/prompts/lisp_frontend_plan_phase/draft_plan.md`
  - `workflows/library/prompts/lisp_frontend_plan_phase/review_plan.md`
  - `workflows/library/prompts/lisp_frontend_plan_phase/revise_plan.md`
  - Replace full/MVP semantics with target/baseline semantics.

- Modify `workflows/library/lisp_frontend_implementation_phase.v214.yaml`
  - Accept target/baseline inputs.
  - Publish/consume target/baseline artifacts.
  - Update prompt consume names.

- Modify implementation prompts:
  - `workflows/library/prompts/lisp_frontend_implementation_phase/implement_plan.md`
  - `workflows/library/prompts/lisp_frontend_implementation_phase/review_implementation.md`
  - `workflows/library/prompts/lisp_frontend_implementation_phase/fix_implementation.md`
  - Replace full/MVP wording with target/baseline wording.

- Modify `workflows/library/scripts/materialize_lisp_frontend_work_item_inputs.py`
  - Add `--artifact-work-root`, `--artifact-checks-root`, and `--artifact-review-root`.
  - Default roots to the current `LISP-FRONTEND-AUTONOMOUS-DRAIN` paths.
  - Generate all report/check/summary targets under the supplied roots.

- Modify `tests/test_lisp_frontend_autonomous_drain_runtime.py`
  - Add script-level tests for artifact-root parameterization.
  - Add dry-run/runtime checks for the ProcRef wrapper with target/baseline and ProcRef namespaces.
  - Preserve existing full-drain tests.

- Create `docs/backlog/active/LISP-PROC-REFS-PARTIAL-APPLICATION/.gitkeep`
  - Empty dedicated backlog root for the ProcRef tranche.

- Modify `docs/index.md` and `workflows/README.md`
  - Update status language only if file paths or workflow semantics change.

---

### Task 1: Parameterize Work-Item Artifact Roots

**Files:**
- Modify: `workflows/library/scripts/materialize_lisp_frontend_work_item_inputs.py`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Write failing tests for custom artifact roots**

Add two tests near `test_materialize_lisp_work_item_inputs_for_backlog_selection`.

```python
def test_materialize_lisp_work_item_inputs_accepts_custom_artifact_roots_for_backlog(tmp_path):
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURE_ROOT, workspace)
    manifest_path = workspace / "state/manifest.json"
    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/build_lisp_frontend_backlog_manifest.py"),
        "--backlog-root",
        "docs/backlog/active",
        "--output",
        manifest_path.relative_to(workspace).as_posix(),
    )
    selection_path = workspace / "state/selection.json"
    selection_path.write_text(
        json.dumps(
            {
                "selection_status": "SELECT_BACKLOG_ITEM",
                "selected_item_id": "2026-05-18-existing-parser-item",
                "selected_item_path": "docs/backlog/active/2026-05-18-existing-parser-item.md",
                "selection_rationale": "Existing item covers parser MVP.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output_path = workspace / "state/work-item/inputs.json"

    _run_script(
        workspace,
        str(ROOT / "workflows/library/scripts/materialize_lisp_frontend_work_item_inputs.py"),
        "--selection-path",
        selection_path.relative_to(workspace).as_posix(),
        "--manifest-path",
        manifest_path.relative_to(workspace).as_posix(),
        "--state-root",
        "state/work-item",
        "--artifact-work-root",
        "artifacts/work/LISP-PROC-REFS-PARTIAL-APPLICATION",
        "--artifact-checks-root",
        "artifacts/checks/LISP-PROC-REFS-PARTIAL-APPLICATION",
        "--artifact-review-root",
        "artifacts/review/LISP-PROC-REFS-PARTIAL-APPLICATION",
        "--output",
        output_path.relative_to(workspace).as_posix(),
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["execution_report_target_path"].startswith(
        "artifacts/work/LISP-PROC-REFS-PARTIAL-APPLICATION/"
    )
    assert payload["progress_report_target_path"].startswith(
        "artifacts/work/LISP-PROC-REFS-PARTIAL-APPLICATION/"
    )
    assert payload["checks_report_target_path"].startswith(
        "artifacts/checks/LISP-PROC-REFS-PARTIAL-APPLICATION/"
    )
    assert payload["implementation_review_report_target_path"].startswith(
        "artifacts/review/LISP-PROC-REFS-PARTIAL-APPLICATION/"
    )
    assert payload["plan_review_report_target_path"].startswith(
        "artifacts/review/LISP-PROC-REFS-PARTIAL-APPLICATION/"
    )
    assert "LISP-FRONTEND-AUTONOMOUS-DRAIN" not in json.dumps(payload)
```

Also add a design-gap variant using a VALID architecture bundle and assert design-gap target paths include `/design-gaps/` under the custom roots.

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_materialize_lisp_work_item_inputs_accepts_custom_artifact_roots_for_backlog -q
```

Expected: fail because `--artifact-work-root`, `--artifact-checks-root`, and `--artifact-review-root` are unknown arguments.

- [ ] **Step 3: Implement artifact-root arguments**

In `materialize_lisp_frontend_work_item_inputs.py`, add:

```python
DEFAULT_WORK_ROOT = "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN"
DEFAULT_CHECKS_ROOT = "artifacts/checks/LISP-FRONTEND-AUTONOMOUS-DRAIN"
DEFAULT_REVIEW_ROOT = "artifacts/review/LISP-FRONTEND-AUTONOMOUS-DRAIN"


def _artifact_roots(args: argparse.Namespace) -> tuple[str, str, str]:
    work_root = _safe_relpath(args.artifact_work_root, under="artifacts/work").as_posix()
    checks_root = _safe_relpath(args.artifact_checks_root, under="artifacts/checks").as_posix()
    review_root = _safe_relpath(args.artifact_review_root, under="artifacts/review").as_posix()
    return work_root, checks_root, review_root
```

Add parser args:

```python
parser.add_argument("--artifact-work-root", default=DEFAULT_WORK_ROOT)
parser.add_argument("--artifact-checks-root", default=DEFAULT_CHECKS_ROOT)
parser.add_argument("--artifact-review-root", default=DEFAULT_REVIEW_ROOT)
```

Thread `work_root`, `checks_root`, and `review_root` into `_materialize_backlog` and `_materialize_design_gap`, then replace hard-coded path strings:

```python
"execution_report_target_path": f"{work_root}/{item_id}/execution_report.md"
"checks_report_target_path": f"{checks_root}/{item_id}-checks.json"
"implementation_review_report_target_path": f"{review_root}/{item_id}-implementation-review.md"
"item_summary_target_path": f"{work_root}/{item_id}-summary.json"
```

For design gaps:

```python
"execution_report_target_path": f"{work_root}/design-gaps/{item_id}/execution_report.md"
"checks_report_target_path": f"{checks_root}/design-gaps/{item_id}-checks.json"
"implementation_review_report_target_path": f"{review_root}/design-gaps/{item_id}-implementation-review.md"
"item_summary_target_path": f"{work_root}/design-gaps/{item_id}-summary.json"
```

For common targets:

```python
"plan_review_report_target_path": f"{review_root}/{item_id}-plan-review.json"
"progress_report_target_path": f"{work_root}/{item_id}/progress_report.md"
```

- [ ] **Step 4: Run focused materializer tests**

Run:

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q -k "materialize_lisp_work_item_inputs"
```

Expected: all selected materializer tests pass.

- [ ] **Step 5: Commit**

```bash
git add workflows/library/scripts/materialize_lisp_frontend_work_item_inputs.py tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "Parameterize Lisp work item artifact roots"
```

---

### Task 2: Carry Artifact Roots Through Workflows

**Files:**
- Modify: `workflows/examples/lisp_frontend_autonomous_drain.yaml`
- Modify: `workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml`
- Modify: `workflows/library/lisp_frontend_work_item.v214.yaml`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add workflow dry-run test for ProcRef artifact roots**

Add a test that runs the ProcRef workflow in dry-run mode or through existing workflow validation helpers and asserts validation succeeds with defaults.

If the test harness uses CLI subprocesses, use:

```python
def test_proc_ref_delta_drain_dry_run_validates(tmp_path):
    workspace = tmp_path / "workspace"
    shutil.copytree(ROOT, workspace, ignore=shutil.ignore_patterns(".git", ".orchestrate", "__pycache__"))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator",
            "run",
            "workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml",
            "--dry-run",
        ],
        cwd=workspace,
        env={**os.environ, "PYTHONPATH": str(workspace)},
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
```

- [ ] **Step 2: Run test and verify current behavior**

Run:

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_proc_ref_delta_drain_dry_run_validates -q
```

Expected: may pass already. This test protects the YAML edits in this task.

- [ ] **Step 3: Add root inputs to full drain and ProcRef wrapper**

In `workflows/examples/lisp_frontend_autonomous_drain.yaml`, add inputs:

```yaml
  artifact_work_root:
    type: relpath
    under: artifacts/work
    default: artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN
  artifact_checks_root:
    type: relpath
    under: artifacts/checks
    default: artifacts/checks/LISP-FRONTEND-AUTONOMOUS-DRAIN
  artifact_review_root:
    type: relpath
    under: artifacts/review
    default: artifacts/review/LISP-FRONTEND-AUTONOMOUS-DRAIN
```

In `workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml`, add matching inputs with ProcRef defaults:

```yaml
  artifact_work_root:
    type: relpath
    under: artifacts/work
    default: artifacts/work/LISP-PROC-REFS-PARTIAL-APPLICATION
  artifact_checks_root:
    type: relpath
    under: artifacts/checks
    default: artifacts/checks/LISP-PROC-REFS-PARTIAL-APPLICATION
  artifact_review_root:
    type: relpath
    under: artifacts/review
    default: artifacts/review/LISP-PROC-REFS-PARTIAL-APPLICATION
```

- [ ] **Step 4: Pass roots into work-item calls**

In both `RunSelectedBacklogItem` and `RunDesignGapWorkItem` calls in `lisp_frontend_autonomous_drain.yaml`, add:

```yaml
                      artifact_work_root:
                        ref: inputs.artifact_work_root
                      artifact_checks_root:
                        ref: inputs.artifact_checks_root
                      artifact_review_root:
                        ref: inputs.artifact_review_root
```

In the ProcRef wrapper call to `proc_ref_delta_drain`, pass the three roots from wrapper inputs.

- [ ] **Step 5: Add root inputs to `lisp_frontend_work_item.v214.yaml`**

Add inputs:

```yaml
  artifact_work_root:
    type: relpath
    under: artifacts/work
    default: artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN
  artifact_checks_root:
    type: relpath
    under: artifacts/checks
    default: artifacts/checks/LISP-FRONTEND-AUTONOMOUS-DRAIN
  artifact_review_root:
    type: relpath
    under: artifacts/review
    default: artifacts/review/LISP-FRONTEND-AUTONOMOUS-DRAIN
```

Pass them to `materialize_lisp_frontend_work_item_inputs.py`:

```yaml
      - --artifact-work-root
      - ${inputs.artifact_work_root}
      - --artifact-checks-root
      - ${inputs.artifact_checks_root}
      - --artifact-review-root
      - ${inputs.artifact_review_root}
```

- [ ] **Step 6: Run dry-runs**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml --dry-run

PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/lisp_frontend_autonomous_drain.yaml --dry-run --input steering_path=docs/steering.md
```

Expected: both dry-runs validate successfully.

- [ ] **Step 7: Commit**

```bash
git add workflows/examples/lisp_frontend_autonomous_drain.yaml workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml workflows/library/lisp_frontend_work_item.v214.yaml tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "Thread Lisp drain artifact roots"
```

---

### Task 3: Add Real Target/Baseline Semantics To Selector

**Files:**
- Modify: `workflows/examples/lisp_frontend_autonomous_drain.yaml`
- Modify: `workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml`
- Modify: `workflows/library/lisp_frontend_selector.v214.yaml`
- Create: `workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add prompt text test**

Add a lightweight prompt contract test:

```python
def test_design_delta_selector_prompt_defines_target_and_baseline():
    prompt = (
        ROOT
        / "workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md"
    ).read_text(encoding="utf-8")
    assert "target design" in prompt.lower()
    assert "baseline design" in prompt.lower()
    assert "Return `DONE` only when the target delta" in prompt
    assert "MVP" not in prompt
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_design_delta_selector_prompt_defines_target_and_baseline -q
```

Expected: fail because the prompt file does not exist.

- [ ] **Step 3: Create the target/baseline selector prompt**

Create `workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md`:

```text
Read the consumed steering, target design, baseline design, backlog manifest,
progress ledger, and run state before acting.

Select exactly one next implementation unit for the target design delta.

Use the target design as the active implementation target. Use the baseline
design as the parent compatibility contract that the target work must not
violate.

Decision rules:

- Return `SELECT_BACKLOG_ITEM` when an active backlog item directly covers the
  next useful target-delta implementation task.
- Return `DRAFT_DESIGN_GAP` when no active backlog item is the right next task
  and the target delta still has an under-specified or unimplemented bounded
  unit.
- Return `DONE` only when the target delta is implemented and no target-delta
  gaps remain.
- Return `BLOCKED` only when target-delta work remains but the target and
  baseline docs are insufficient or contradictory.

Do not select unrelated baseline/frontend work unless it is required to satisfy
the target delta without violating the baseline design.

Make only this step's local selection judgment and explain it. Do not edit
files, move backlog items, or draft architecture content.

[Keep the same JSON output examples from select_next_work.md, replacing
`full-design` wording with `target-delta` wording.]
```

Do not delete the old prompt. The full frontend drain still uses it.

- [ ] **Step 4: Add selector inputs and artifacts**

In `lisp_frontend_selector.v214.yaml`, add optional inputs:

```yaml
  target_design_path:
    type: relpath
    under: docs/design
    required: false
    must_exist_target: true
  baseline_design_path:
    type: relpath
    under: docs/design
    required: false
    must_exist_target: true
  selector_prompt_asset:
    kind: scalar
    type: string
    default: prompts/lisp_frontend_selector/select_next_work.md
```

If DSL validation disallows variable `asset_file`, create a separate `lisp_frontend_design_delta_selector.v214.yaml` instead. Prefer trying the input approach first only if the loader supports variable substitution in `asset_file`.

Add artifacts `target_design` and `baseline_design` only if the workflow uses the new prompt. A safer minimal approach is to create the separate design-delta selector file so the artifact names and prompt consume names are unambiguous.

- [ ] **Step 5: Prefer separate selector if asset_file variable is not supported**

If step 4 is not valid, create:

```text
workflows/library/lisp_frontend_design_delta_selector.v214.yaml
```

Copy `lisp_frontend_selector.v214.yaml`, then:

- rename inputs to `target_design_path` and `baseline_design_path`;
- rename artifacts to `target_design` and `baseline_design`;
- use `asset_file: prompts/lisp_frontend_selector/select_next_design_delta_work.md`;
- consume/prompt-consume `target_design` and `baseline_design`;
- keep outputs identical.

Update the ProcRef wrapper or a ProcRef-specific drain to import this selector.

- [ ] **Step 6: Wire ProcRef wrapper through real names**

If keeping the imported full drain, add optional `target_design_path` / `baseline_design_path` to `lisp_frontend_autonomous_drain.yaml` and route those to the selector when present. If that becomes awkward, create a ProcRef-specific copy of the top-level drain that imports the design-delta selector.

Minimum correct behavior:

```yaml
target_design_path:
  ref: inputs.target_design_path
baseline_design_path:
  ref: inputs.baseline_design_path
```

No prompt should call the baseline `MVP` in the ProcRef path.

- [ ] **Step 7: Run selector prompt test and dry-runs**

Run:

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_design_delta_selector_prompt_defines_target_and_baseline -q
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml --dry-run
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/lisp_frontend_autonomous_drain.yaml --dry-run --input steering_path=docs/steering.md
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add workflows/examples/lisp_frontend_autonomous_drain.yaml workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml workflows/library/lisp_frontend_selector.v214.yaml workflows/library/lisp_frontend_design_delta_selector.v214.yaml workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "Add target baseline selector semantics"
```

Use `git add` only for files that exist.

---

### Task 4: Carry Target/Baseline Through Design, Plan, And Implementation Phases

**Files:**
- Modify: `workflows/library/lisp_frontend_design_gap_architect.v214.yaml`
- Modify: `workflows/library/lisp_frontend_work_item.v214.yaml`
- Modify: `workflows/library/lisp_frontend_plan_phase.v214.yaml`
- Modify: `workflows/library/lisp_frontend_implementation_phase.v214.yaml`
- Modify prompts under:
  - `workflows/library/prompts/lisp_frontend_design_gap_architect/`
  - `workflows/library/prompts/lisp_frontend_plan_phase/`
  - `workflows/library/prompts/lisp_frontend_implementation_phase/`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add prompt wording regression test**

Add:

```python
def test_proc_ref_path_prompts_do_not_describe_baseline_as_mvp():
    prompt_paths = [
        ROOT / "workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md",
        ROOT / "workflows/library/prompts/lisp_frontend_design_gap_architect/draft_implementation_architecture.md",
        ROOT / "workflows/library/prompts/lisp_frontend_plan_phase/draft_plan.md",
        ROOT / "workflows/library/prompts/lisp_frontend_implementation_phase/implement_plan.md",
    ]
    for path in prompt_paths:
        text = path.read_text(encoding="utf-8")
        assert "target" in text.lower(), path
        assert "baseline" in text.lower(), path
```

This test is intentionally broad but not a full prose assertion. If keeping full-drain prompts shared, scope the test to new design-delta prompt files instead.

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_proc_ref_path_prompts_do_not_describe_baseline_as_mvp -q
```

Expected: fail until prompts and/or design-delta prompt variants exist.

- [ ] **Step 3: Add target/baseline inputs to library workflows**

For `lisp_frontend_design_gap_architect.v214.yaml`, `lisp_frontend_work_item.v214.yaml`, `lisp_frontend_plan_phase.v214.yaml`, and `lisp_frontend_implementation_phase.v214.yaml`, add target/baseline inputs with old-name compatibility if needed:

```yaml
  target_design_path:
    type: relpath
    under: docs/design
    required: false
    must_exist_target: true
  baseline_design_path:
    type: relpath
    under: docs/design
    required: false
    must_exist_target: true
```

If the DSL cannot express fallback from optional target/baseline to full/MVP inside `materialize_artifacts`, prefer creating ProcRef-specific workflow copies for these phases. Do not keep passing baseline as MVP in the ProcRef path.

- [ ] **Step 4: Update artifact names or create delta variants**

Preferred clean version for ProcRef path:

```yaml
artifacts:
  target_design:
    kind: relpath
    type: relpath
    pointer: ${inputs.state_root}/target_design_path.txt
    under: docs/design
    must_exist_target: true
  baseline_design:
    kind: relpath
    type: relpath
    pointer: ${inputs.state_root}/baseline_design_path.txt
    under: docs/design
    must_exist_target: true
```

Then consume:

```yaml
prompt_consumes: ["target_design", "baseline_design", ...]
```

If reusing full-drain workflows, keep old artifacts for old path and create separate `*.design_delta.v214.yaml` variants for the ProcRef wrapper.

- [ ] **Step 5: Update prompts minimally**

Design-gap draft prompt opening should say:

```text
Read the listed steering, target design, baseline design, command-adapter
contract, progress ledger, selector bundle, architecture target contract, and
existing implementation architecture index before acting.

Draft a single implementation-architecture document for exactly the selected
target-design gap. The baseline design is a compatibility constraint, not the
active work queue.
```

Plan prompt opening should say:

```text
Draft an execution-ready plan for the selected target-design work item.

Use the consumed target design, baseline design, work-item context, and progress
ledger. The plan must be self-contained enough that implementation can execute
from the approved plan without rediscovering scope.
```

Implementation prompt opening should say:

```text
Implement only the approved plan for the target-design work item.

Use the consumed target design, baseline design, approved plan, check commands,
and the authoritative execution-report and progress-report target paths.
```

- [ ] **Step 6: Replace old hard-coded examples in design-gap prompts**

Change examples from concrete `LISP-FRONTEND-AUTONOMOUS-DRAIN` paths to placeholders:

```json
{
  "draft_status": "DRAFTED",
  "design_gap_id": "procref-static-surface-and-resolution",
  "architecture_path": "<architecture_path from architecture-targets.json>",
  "work_item_context_path": "<work_item_context_path from architecture-targets.json>",
  "check_commands_path": "<check_commands_path from architecture-targets.json>",
  "plan_target_path": "<plan_target_path from architecture-targets.json>",
  "summary": "short summary"
}
```

- [ ] **Step 7: Run prompt tests and dry-runs**

Run:

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q -k "prompt or proc_ref_delta_drain_dry_run"
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml --dry-run
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/lisp_frontend_autonomous_drain.yaml --dry-run --input steering_path=docs/steering.md
```

Expected: selected tests and both dry-runs pass.

- [ ] **Step 8: Commit**

```bash
git add workflows/library/lisp_frontend_design_gap_architect.v214.yaml workflows/library/lisp_frontend_work_item.v214.yaml workflows/library/lisp_frontend_plan_phase.v214.yaml workflows/library/lisp_frontend_implementation_phase.v214.yaml workflows/library/prompts/lisp_frontend_design_gap_architect workflows/library/prompts/lisp_frontend_plan_phase workflows/library/prompts/lisp_frontend_implementation_phase tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "Carry target baseline semantics through Lisp phases"
```

---

### Task 5: Isolate ProcRef Backlog Root

**Files:**
- Create: `docs/backlog/active/LISP-PROC-REFS-PARTIAL-APPLICATION/.gitkeep`
- Modify: `workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Add test for ProcRef backlog default**

Add:

```python
def test_proc_ref_delta_drain_uses_proc_ref_backlog_root():
    text = (ROOT / "workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml").read_text(
        encoding="utf-8"
    )
    assert "docs/backlog/active/LISP-PROC-REFS-PARTIAL-APPLICATION" in text
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_proc_ref_delta_drain_uses_proc_ref_backlog_root -q
```

Expected: fail because the wrapper currently defaults to `docs/backlog/active`.

- [ ] **Step 3: Add dedicated backlog root**

Create:

```text
docs/backlog/active/LISP-PROC-REFS-PARTIAL-APPLICATION/.gitkeep
```

Update `workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml`:

```yaml
  backlog_root:
    type: relpath
    under: docs/backlog
    default: docs/backlog/active/LISP-PROC-REFS-PARTIAL-APPLICATION
```

- [ ] **Step 4: Run test and dry-run**

Run:

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_proc_ref_delta_drain_uses_proc_ref_backlog_root -q
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml --dry-run
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add docs/backlog/active/LISP-PROC-REFS-PARTIAL-APPLICATION/.gitkeep workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml tests/test_lisp_frontend_autonomous_drain_runtime.py
git commit -m "Isolate ProcRef drain backlog root"
```

---

### Task 6: End-To-End Static Validation And Relaunch Gate

**Files:**
- Modify only if previous tasks reveal stale index text:
  - `docs/index.md`
  - `workflows/README.md`

- [ ] **Step 1: Search for remaining semantic contradictions**

Run:

```bash
rg -n "MVP design|mvp_design|full design|full_design|LISP-FRONTEND-AUTONOMOUS-DRAIN" \
  workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml \
  workflows/library/lisp_frontend_design_delta_selector.v214.yaml \
  workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md \
  docs/plans/LISP-PROC-REFS-PARTIAL-APPLICATION \
  workflows/library/prompts/lisp_frontend_design_gap_architect \
  workflows/library/prompts/lisp_frontend_plan_phase \
  workflows/library/prompts/lisp_frontend_implementation_phase
```

Expected:
- no `mvp_design` or `MVP design` in ProcRef-specific surfaces;
- no hard-coded `LISP-FRONTEND-AUTONOMOUS-DRAIN` examples in ProcRef-specific prompt examples;
- old full-drain library files may still contain old names only if ProcRef-specific variants exist.

- [ ] **Step 2: Run focused tests**

Run:

```bash
pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q -k "materialize_lisp_work_item_inputs or proc_ref_delta or design_delta_selector or target_and_baseline"
```

Expected: all selected tests pass.

- [ ] **Step 3: Run workflow dry-runs**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml --dry-run

PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/lisp_frontend_autonomous_drain.yaml --dry-run --input steering_path=docs/steering.md
```

Expected: both dry-runs pass.

- [ ] **Step 4: Run diff check**

Run:

```bash
git diff --check
```

Expected: no output, exit 0.

- [ ] **Step 5: Commit validation/index cleanup**

If docs indexes changed:

```bash
git add docs/index.md workflows/README.md
git commit -m "Document ProcRef drain readiness"
```

Skip this commit if no index/docs changes were needed.

- [ ] **Step 6: Relaunch fresh only after all checks pass**

Do not resume `20260528T212850Z-minalo`. It was killed during the mixed-semantics wrapper run.

Relaunch with a fresh timestamp:

```bash
RUN_TS=$(date -u +%Y%m%dT%H%M%SZ)
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml \
  --input drain_state_root=state/LISP-PROC-REFS-PARTIAL-APPLICATION/drain-$RUN_TS \
  --input run_state_target_path=state/LISP-PROC-REFS-PARTIAL-APPLICATION/drain/run_state-$RUN_TS.json \
  --input drain_summary_target_path=artifacts/work/LISP-PROC-REFS-PARTIAL-APPLICATION/drain-summary-$RUN_TS.json
```

Expected first selector outcome:

```json
{
  "selection_status": "DRAFT_DESIGN_GAP",
  "source_design_path": "docs/design/workflow_lisp_proc_refs_partial_application.md"
}
```

Also verify generated design-gap architecture targets are under:

```text
docs/plans/LISP-PROC-REFS-PARTIAL-APPLICATION/design-gaps/
```

and implementation/report artifacts are under:

```text
artifacts/work/LISP-PROC-REFS-PARTIAL-APPLICATION/
artifacts/checks/LISP-PROC-REFS-PARTIAL-APPLICATION/
artifacts/review/LISP-PROC-REFS-PARTIAL-APPLICATION/
```
