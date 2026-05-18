# Lisp Frontend Autonomous Drain Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a v2.14 workflow, based on the local NeurIPS backlog drain pattern, that drains Lisp frontend MVP/full-design work without phase-based roadmap gating by letting an agentic selector either choose an active backlog item or identify an unimplemented design gap, draft implementation architecture for it, and route that work into the plan/implementation stack.

**Architecture:** Add a sibling Lisp-specific workflow stack rather than mutating the NeurIPS stack. The top-level drain owns looping, state roots, manifests, route decisions, and final summaries; a selector owns the local judgment of choosing `SELECT_BACKLOG_ITEM`, `DRAFT_DESIGN_GAP`, `DONE`, or `BLOCKED`; a gap architect owns drafting one implementation architecture/work-item bundle from the design docs; a Lisp work-item workflow normalizes backlog-selected and design-gap-selected work into one plan -> implementation path. Use typed bundles/variants for routing and keep generated architecture/report files as artifacts, not prompt-only prose.

**Tech Stack:** YAML workflow DSL v2.14, existing orchestrator loader/runtime, Python helper scripts under `workflows/library/scripts/`, Markdown prompt assets under `workflows/library/prompts/`, pytest runtime tests with fake provider output.

---

## Context And Boundaries

Read these first:

- `docs/index.md`
- `docs/workflow_drafting_guide.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/design/workflow_command_adapter_contract.md`
- `workflows/examples/neurips_steered_backlog_drain.yaml`
- `workflows/library/neurips_backlog_selector.v214.yaml`
- `workflows/library/neurips_selected_backlog_item.v214.yaml`

Non-goals:

- Do not add roadmap phase gating or use `docs/backlog/roadmap_gate.json`.
- Do not modify the existing NeurIPS drain behavior except for shared utility fixes that tests prove are safe.
- Do not implement the Lisp compiler/frontend itself.
- Do not make the selector edit queues, move files, or own loop mechanics.
- Do not parse markdown reports for semantic state.

Important design choice:

- The selector may decide to work from a design gap, but a separate `DraftLispDesignGapArchitecture` workflow drafts the architecture/work-item bundle. This keeps selector agency high while preserving deterministic routing and artifact validation.

## Files

Create:

- `workflows/examples/lisp_frontend_autonomous_drain.yaml`
- `workflows/library/lisp_frontend_selector.v214.yaml`
- `workflows/library/lisp_frontend_design_gap_architect.v214.yaml`
- `workflows/library/lisp_frontend_work_item.v214.yaml`
- `workflows/library/lisp_frontend_plan_phase.v214.yaml`
- `workflows/library/lisp_frontend_implementation_phase.v214.yaml`
- `workflows/library/prompts/lisp_frontend_selector/select_next_work.md`
- `workflows/library/prompts/lisp_frontend_design_gap_architect/draft_implementation_architecture.md`
- `workflows/library/prompts/lisp_frontend_plan_phase/draft_plan.md`
- `workflows/library/prompts/lisp_frontend_plan_phase/review_plan.md`
- `workflows/library/prompts/lisp_frontend_plan_phase/revise_plan.md`
- `workflows/library/prompts/lisp_frontend_implementation_phase/implement_plan.md`
- `workflows/library/prompts/lisp_frontend_implementation_phase/review_implementation.md`
- `workflows/library/prompts/lisp_frontend_implementation_phase/fix_implementation.md`
- `workflows/library/scripts/materialize_lisp_frontend_work_item_inputs.py`
- `workflows/library/scripts/validate_lisp_frontend_design_gap_architecture.py`
- `workflows/library/scripts/finalize_lisp_frontend_drain_summary.py`
- `tests/fixtures/lisp_frontend_autonomous_drain/`
- `tests/test_lisp_frontend_autonomous_drain_runtime.py`

Modify:

- `docs/index.md`
- `workflows/README.md`
- optionally `docs/backlog/active/2026-04-29-workflow-authoring-frontend.md` to point at the new runnable workflow

Do not modify unless a test forces it:

- `workflows/examples/neurips_steered_backlog_drain.yaml`
- `workflows/library/neurips_selected_backlog_item.v214.yaml`
- `workflows/library/neurips_backlog_seeded_plan_phase.v214.yaml`
- `workflows/library/neurips_backlog_implementation_phase.v214.yaml`

## Target Workflow Shape

Top-level workflow name:

```yaml
version: "2.14"
name: "lisp-frontend-autonomous-drain-v214"
```

Core inputs:

```yaml
inputs:
  steering_path:
    type: relpath
    under: docs
    must_exist_target: true
  full_design_path:
    type: relpath
    under: docs/design
    default: docs/design/workflow_lisp_frontend_specification.md
    must_exist_target: true
  mvp_design_path:
    type: relpath
    under: docs/design
    default: docs/design/workflow_lisp_frontend_mvp_specification.md
    must_exist_target: true
  backlog_root:
    type: relpath
    under: docs/backlog
    default: docs/backlog/active
  progress_ledger_path:
    type: relpath
    under: state
    default: state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json
  drain_state_root:
    type: relpath
    under: state
    default: state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain
```

Selector statuses:

```text
SELECT_BACKLOG_ITEM
DRAFT_DESIGN_GAP
DONE
BLOCKED
```

Drain statuses:

```text
CONTINUE
DONE
BLOCKED
```

Work-item source kinds:

```text
BACKLOG_ITEM
DESIGN_GAP
RECOVERED_IN_PROGRESS
```

## Task 1: Add Runtime Fixtures

**Files:**

- Create directory: `tests/fixtures/lisp_frontend_autonomous_drain/`
- Create fixture docs:
  - `tests/fixtures/lisp_frontend_autonomous_drain/docs/steering.md`
  - `tests/fixtures/lisp_frontend_autonomous_drain/docs/design/workflow_lisp_frontend_specification.md`
  - `tests/fixtures/lisp_frontend_autonomous_drain/docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `tests/fixtures/lisp_frontend_autonomous_drain/docs/backlog/active/2026-05-18-existing-parser-item.md`
  - `tests/fixtures/lisp_frontend_autonomous_drain/state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

- [ ] **Step 1: Create a minimal fixture steering document**

The steering doc should say the workflow owns the Lisp frontend MVP/full design and may select either backlog items or unimplemented design gaps.

- [ ] **Step 2: Create minimal full-design and MVP docs**

Include obvious headings the selector can cite, such as:

```markdown
# Workflow Lisp Frontend Specification

## Implemented

- Documentation exists.

## Not Yet Implemented

- Parser and syntax objects.
- Type catalog integration.
- Provider-result lowering.
```

- [ ] **Step 3: Create one active backlog item**

Use the same frontmatter contract as existing backlog manifests:

```yaml
---
priority: 1
plan_path: docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/backlog/2026-05-18-existing-parser-item/execution_plan.md
check_commands:
  - python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q
related_design_sections:
  - workflow_lisp_frontend_mvp_specification.md#stage-1
---
```

Create the referenced plan file too, even if it is a short seed plan, because the manifest builder requires `plan_path` to exist.

- [ ] **Step 4: Verify fixture files are present**

Run:

```bash
find tests/fixtures/lisp_frontend_autonomous_drain -type f | sort
```

Expected: lists steering, design docs, one active backlog item, one seed plan, and progress ledger.

## Task 2: Add Lisp Work-Item Materializer

**Files:**

- Create: `workflows/library/scripts/materialize_lisp_frontend_work_item_inputs.py`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Write unit tests for backlog selections**

Add tests that call the script with:

- a selector bundle with `selection_status=SELECT_BACKLOG_ITEM`;
- a raw backlog manifest from `build_neurips_backlog_manifest.py`;
- `state_root=state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/items/...`.

Assert the output bundle contains:

```json
{
  "work_item_source": "BACKLOG_ITEM",
  "work_item_id": "2026-05-18-existing-parser-item",
  "work_item_context_path": "state/...",
  "check_commands_path": "state/...",
  "plan_target_path": "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/backlog/2026-05-18-existing-parser-item/execution_plan.md"
}
```

- [ ] **Step 2: Write unit tests for design-gap bundles**

The input is a validated gap architecture bundle from Task 3. Assert the materializer copies through:

- `work_item_source=DESIGN_GAP`;
- `architecture_path`;
- `work_item_context_path`;
- `check_commands_path`;
- `plan_target_path`;
- report target paths under `artifacts/work`, `artifacts/checks`, and `artifacts/review`.

- [ ] **Step 3: Implement the script**

Implementation requirements:

- reject absolute paths and `..`;
- require backlog selections to point under `docs/backlog/active`;
- parse backlog frontmatter with `yaml.safe_load`;
- require non-empty `check_commands`;
- require existing seed `plan_path` for backlog items;
- create selected work-item context under state;
- never move active backlog items;
- write one output JSON bundle.

- [ ] **Step 4: Run the focused tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k materialize -q
```

Expected: materializer tests pass.

## Task 3: Add Design-Gap Architecture Validator

**Files:**

- Create: `workflows/library/scripts/validate_lisp_frontend_design_gap_architecture.py`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Write tests for a valid architecture draft**

Input draft bundle:

```json
{
  "draft_status": "DRAFTED",
  "design_gap_id": "parser-syntax-objects",
  "architecture_path": "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-objects/implementation_architecture.md",
  "work_item_context_path": "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap/work_item_context.md",
  "check_commands_path": "state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap/check_commands.json",
  "plan_target_path": "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-objects/execution_plan.md"
}
```

Assert validator output is:

```json
{
  "architecture_validation_status": "VALID",
  "work_item_source": "DESIGN_GAP",
  "work_item_id": "parser-syntax-objects"
}
```

- [ ] **Step 2: Write tests for blocked and invalid drafts**

Cases:

- `draft_status=BLOCKED` returns `architecture_validation_status=BLOCKED`;
- missing architecture target returns `INVALID`;
- architecture path outside `docs/plans` returns `INVALID`;
- check commands path outside `state` returns `INVALID`.

- [ ] **Step 3: Implement validator**

The validator should:

- validate the draft bundle;
- validate referenced files exist for `DRAFTED`;
- require non-empty check commands JSON list;
- produce a normalized work-item bundle path for downstream work-item execution;
- avoid installing backlog items into `docs/backlog/active`.

- [ ] **Step 4: Run focused tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k architecture_validator -q
```

Expected: validator tests pass.

## Task 4: Add Lisp Selector Workflow And Prompt

**Files:**

- Create: `workflows/library/lisp_frontend_selector.v214.yaml`
- Create: `workflows/library/prompts/lisp_frontend_selector/select_next_work.md`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Write loader test for selector workflow**

Use `WorkflowLoader` to load `workflows/library/lisp_frontend_selector.v214.yaml`.

Assert:

- version is `2.14`;
- selector has inputs for `steering_path`, `full_design_path`, `mvp_design_path`, `manifest_path`, `progress_ledger_path`, and `run_state_path`;
- output `selection_status` allows `SELECT_BACKLOG_ITEM`, `DRAFT_DESIGN_GAP`, `DONE`, `BLOCKED`.

- [ ] **Step 2: Implement selector workflow**

Use a provider step with a `variant_output` or fixed `output_bundle` plus finalization. Prefer `variant_output` if current runtime validation supports the desired optional fields cleanly.

Required output shape:

```json
{
  "selection_status": "DRAFT_DESIGN_GAP",
  "design_gap_id": "parser-syntax-objects",
  "source_design_path": "docs/design/workflow_lisp_frontend_mvp_specification.md",
  "source_sections": ["Stage 1: frontend core without workflow execution"],
  "missing_component": "Parser and syntax objects",
  "proposed_scope": "Implement parser and source spans only.",
  "selection_rationale": "This is the first unimplemented MVP dependency."
}
```

Backlog selection shape:

```json
{
  "selection_status": "SELECT_BACKLOG_ITEM",
  "selected_item_id": "2026-05-18-existing-parser-item",
  "selected_item_path": "docs/backlog/active/2026-05-18-existing-parser-item.md",
  "selection_rationale": "Existing active backlog item directly covers parser MVP work."
}
```

- [ ] **Step 3: Write selector prompt**

Prompt rules:

- read `docs/index.md` if available;
- use full design, MVP design, active manifest, progress ledger, and run state;
- first choose a runnable active backlog item when one clearly covers the next valuable work;
- otherwise identify exactly one unimplemented design part and return `DRAFT_DESIGN_GAP`;
- return `DONE` only when no active backlog items and no unimplemented design gaps remain;
- return `BLOCKED` only when there is work but no safe next item can be selected or drafted;
- do not edit files.

- [ ] **Step 4: Run loader test**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k selector_loader -q
```

Expected: selector loader test passes.

## Task 5: Add Design-Gap Architect Workflow And Prompt

**Files:**

- Create: `workflows/library/lisp_frontend_design_gap_architect.v214.yaml`
- Create: `workflows/library/prompts/lisp_frontend_design_gap_architect/draft_implementation_architecture.md`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Write loader test for architect workflow**

Assert the workflow:

- consumes steering, full design, MVP design, progress ledger, and selector bundle;
- writes architecture and work-item context under declared target paths;
- validates with `validate_lisp_frontend_design_gap_architecture.py`.

- [ ] **Step 2: Implement architect workflow**

Inputs:

- `state_root`
- `steering_path`
- `full_design_path`
- `mvp_design_path`
- `progress_ledger_path`
- `selection_bundle_path`

Outputs:

- `architecture_validation_status`: `VALID|BLOCKED|INVALID`
- `work_item_bundle_path`: relpath under `state`, required for valid drafts

- [ ] **Step 3: Write architect prompt**

The prompt drafts:

- one implementation architecture under `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/<gap-id>/implementation_architecture.md`;
- one work-item context under state;
- one `check_commands.json`;
- one draft bundle JSON.

It must not write source code, mutate queues, or invent work outside the selected design gap.

- [ ] **Step 4: Run focused tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k architect -q
```

Expected: architect loader and validator tests pass.

## Task 6: Add Lisp Plan Phase

**Files:**

- Create: `workflows/library/lisp_frontend_plan_phase.v214.yaml`
- Create prompts under `workflows/library/prompts/lisp_frontend_plan_phase/`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Write loader test for plan phase**

Assert inputs accept:

- `full_design_path` under `docs/design`;
- `mvp_design_path` under `docs/design`;
- `work_item_context_path` under `state`;
- `progress_ledger_path` under `state`;
- `plan_target_path` under `docs/plans`;
- review report target under `artifacts/review`.

- [ ] **Step 2: Implement plan workflow**

Base it on `neurips_backlog_seeded_plan_phase.v214.yaml`, but remove roadmap inputs and prompts. Use `materialize_artifacts` for deterministic input/target setup.

Outputs:

- `plan_path`
- `plan_review_report_path`
- `plan_review_decision`: `APPROVE|REVISE`

- [ ] **Step 3: Write Lisp-specific plan prompts**

Plan prompt should make the approved plan self-contained for implementation. It should consume:

- full design;
- MVP design;
- work-item context;
- progress ledger.

Review prompt should reject:

- plans that drift outside selected backlog/gap scope;
- plans that silently implement full frontend beyond MVP boundary unless the work item says so;
- plans that omit verification.

- [ ] **Step 4: Run focused tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k plan_phase_loader -q
```

Expected: plan phase loader test passes.

## Task 7: Add Lisp Implementation Phase

**Files:**

- Create: `workflows/library/lisp_frontend_implementation_phase.v214.yaml`
- Create prompts under `workflows/library/prompts/lisp_frontend_implementation_phase/`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Write loader test for implementation phase**

Assert inputs accept:

- full and MVP design docs under `docs/design`;
- approved plan under `docs/plans`;
- check commands under `state`;
- execution/check/review report targets.

- [ ] **Step 2: Implement phase**

Base it on `neurips_backlog_implementation_phase.v214.yaml`, preserving:

- `pre_snapshot`;
- `select_variant_output`;
- `variant_output`/match behavior where applicable;
- check runner script if reusable.

Adjust prompt consumes to include full and MVP design docs instead of a single `docs/plans` design path.

- [ ] **Step 3: Write implementation prompts**

Prompts must:

- implement only the approved plan;
- use design docs as authority;
- run or preserve declared check commands;
- write structured completed/blocked outputs;
- not use report prose as semantic state.

- [ ] **Step 4: Run focused tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k implementation_phase_loader -q
```

Expected: implementation phase loader test passes.

## Task 8: Add Lisp Work-Item Workflow

**Files:**

- Create: `workflows/library/lisp_frontend_work_item.v214.yaml`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Write loader test for work-item workflow**

Assert imports are same-version v2.14:

- `plan_phase: ./lisp_frontend_plan_phase.v214.yaml`
- `implementation_phase: ./lisp_frontend_implementation_phase.v214.yaml`

- [ ] **Step 2: Implement work-item workflow**

Inputs:

- `state_root`
- `selection_status`
- `selection_bundle_path`
- `manifest_path`
- `work_item_bundle_path` optional or a required path whose content marks source
- `steering_path`
- `full_design_path`
- `mvp_design_path`
- `progress_ledger_path`
- `run_state_path`
- provider role inputs

Execution:

1. Materialize either backlog selection or design-gap bundle into normalized work-item inputs.
2. Call Lisp plan phase.
3. Assert/route only `APPROVE` plans into implementation.
4. Call Lisp implementation phase.
5. Record selected work item outcome in run state.

Keep queue movement out of the first tranche. For backlog items, leave existing active backlog file in place and use run state to prevent repeated selection until a real resource-transition design is added.

- [ ] **Step 3: Add run-state update behavior**

Either:

- use a new certified adapter script scoped to Lisp drain state; or
- extend `update_neurips_backlog_run_state.py` only if it is renamed/generalized and existing tests prove compatibility.

Prefer a new script if the old one is too NeurIPS-specific.

- [ ] **Step 4: Run focused tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k work_item_loader -q
```

Expected: work-item loader test passes.

## Task 9: Add Top-Level Autonomous Drain Workflow

**Files:**

- Create: `workflows/examples/lisp_frontend_autonomous_drain.yaml`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Write loader test for top-level workflow**

Assert:

- workflow loads under v2.14;
- there is no `roadmap_gate_path` input;
- imports are same-version v2.14;
- outputs include `drain_status`, `run_state_path`, and `drain_summary_path`.

- [ ] **Step 2: Implement top-level workflow**

Base it on `neurips_steered_backlog_drain.yaml`, but remove:

- `ReconcileBacklogRoadmapGate`;
- `DraftMissingBacklogItem` tied to roadmap gaps;
- any `roadmap_gate_path` input or artifact;
- phase-prefix eligibility.

Loop body:

1. Build raw backlog manifest from `docs/backlog/active`.
2. Prepare selector state root.
3. Call `lisp_frontend_selector`.
4. Match selector result:
   - `SELECT_BACKLOG_ITEM`: normalize and run `lisp_frontend_work_item`.
   - `DRAFT_DESIGN_GAP`: call `lisp_frontend_design_gap_architect`, then run `lisp_frontend_work_item` against the generated bundle.
   - `DONE`: set drain status `DONE`.
   - `BLOCKED`: set drain status `BLOCKED`.
5. Continue until `DONE` or `BLOCKED`, with a bounded `max_iterations`.

- [ ] **Step 3: Add final summary**

Use `finalize_lisp_frontend_drain_summary.py` to write:

```json
{
  "drain_status": "DONE",
  "run_state_path": "state/...",
  "completed_items": [],
  "completed_design_gaps": [],
  "blocked_items": {},
  "blocked_design_gaps": {},
  "history_count": 0
}
```

- [ ] **Step 4: Run loader test**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k top_level_loader -q
```

Expected: top-level loader test passes.

## Task 10: Add Runtime Smoke Tests With Fake Provider Outputs

**Files:**

- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Build test harness**

Copy the style of `tests/test_neurips_steered_backlog_runtime.py`:

- copy the fixture tree into `tmp_path`;
- copy required workflow library YAML, prompts, and scripts;
- patch provider execution to write deterministic output bundles;
- run `WorkflowExecutor` against the copied workflow.

- [ ] **Step 2: Test backlog-item branch**

Fake selector writes `SELECT_BACKLOG_ITEM`.

Fake plan provider writes an approved plan.

Fake implementation provider writes completed execution report.

Assert:

- drain returns `CONTINUE` for that iteration, then `DONE` on next selector pass;
- run state records the backlog item completed;
- drain summary exists.

- [ ] **Step 3: Test design-gap branch**

Fake selector writes `DRAFT_DESIGN_GAP`.

Fake architect writes architecture, work-item context, check commands, and draft bundle.

Fake plan and implementation providers complete.

Assert:

- architecture path exists under `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/`;
- plan path exists;
- implementation report exists;
- run state records the design gap completed;
- no backlog item had to exist for the design gap branch.

- [ ] **Step 4: Test blocked branch**

Fake selector writes `BLOCKED`.

Assert:

- workflow output `drain_status=BLOCKED`;
- no plan/implementation call executes.

- [ ] **Step 5: Test done branch**

Fake selector writes `DONE`.

Assert:

- workflow output `drain_status=DONE`;
- no plan/implementation call executes.

- [ ] **Step 6: Run smoke tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q
```

Expected: all Lisp autonomous drain tests pass.

## Task 11: Add CLI Dry-Run Validation

**Files:**

- No source changes unless validation exposes a workflow issue.

- [ ] **Step 1: Run dry-run with fixture inputs**

Run:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/lisp_frontend_autonomous_drain.yaml \
  --dry-run \
  --input steering_path=docs/steering.md \
  --input full_design_path=docs/design/workflow_lisp_frontend_specification.md \
  --input mvp_design_path=docs/design/workflow_lisp_frontend_mvp_specification.md \
  --input progress_ledger_path=state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json
```

Expected: loader/runtime dry-run succeeds. If the local repo lacks the progress ledger, create a checked-in example fixture under `workflows/examples/inputs/` and use that for dry-run instead of writing runtime state under `state/`.

- [ ] **Step 2: Run collect-only for new tests**

Run:

```bash
python -m pytest --collect-only tests/test_lisp_frontend_autonomous_drain_runtime.py -q
```

Expected: all intended tests are collected.

## Task 12: Update Docs And Indexes

**Files:**

- Modify: `docs/index.md`
- Modify: `workflows/README.md`
- Optionally modify: `docs/backlog/active/2026-04-29-workflow-authoring-frontend.md`

- [ ] **Step 1: Add workflow to docs index**

Under Lisp/frontend docs, add a reference to `workflows/examples/lisp_frontend_autonomous_drain.yaml` as the runnable workflow for autonomous Lisp frontend backlog/design-gap draining.

- [ ] **Step 2: Add workflow catalog row**

Add a row to `workflows/README.md`:

```markdown
| `workflows/examples/lisp_frontend_autonomous_drain.yaml` | Reusable call-based; input-required | `2.14` | `lisp-frontend-autonomous-drain-v214` | Agentic selector drain for Lisp frontend MVP/full-design work: selects active backlog items or drafts design-gap implementation architecture and routes both through the Lisp plan/implementation stack without roadmap phase gating. |
```

- [ ] **Step 3: Update backlog item pointer**

If editing the active backlog item, change `Plan: none yet` to point at this plan and mention the new workflow as the implementation vehicle.

- [ ] **Step 4: Verify docs links**

Run a local link check for touched docs:

```bash
python - <<'PY'
from pathlib import Path
import re, sys
files = [Path('docs/index.md'), Path('workflows/README.md'), Path('docs/backlog/active/2026-04-29-workflow-authoring-frontend.md')]
pat = re.compile(r'\[[^\]]+\]\(([^)]+)\)')
missing = []
for f in files:
    if not f.exists():
        continue
    for raw in pat.findall(f.read_text()):
        target = raw.split('#', 1)[0]
        if not target or '://' in target:
            continue
        if not (f.parent / target).resolve().exists():
            missing.append((str(f), raw))
if missing:
    for row in missing:
        print(row)
    sys.exit(1)
print('links ok')
PY
```

Expected: `links ok`.

## Task 13: Final Verification

**Files:**

- All created and modified files.

- [ ] **Step 1: Run targeted unit/runtime tests**

Run:

```bash
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q
```

Expected: pass.

- [ ] **Step 2: Run relevant existing NeurIPS regression tests**

Run:

```bash
python -m pytest tests/test_neurips_steered_backlog_runtime.py -q
```

Expected: pass. This proves the sibling workflow did not break the local NeurIPS drain.

- [ ] **Step 3: Run workflow dry-run**

Run the dry-run command from Task 11.

Expected: pass.

- [ ] **Step 4: Check diff hygiene**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors. Status should show only files intentionally touched by this plan, plus any unrelated pre-existing dirty files that must not be staged.

## Task 14: Stage And Commit

**Files:**

- Stage only files created or modified by this plan.

- [ ] **Step 1: Review staged diff**

Run:

```bash
git diff --stat
git diff --cached --stat
```

Expected: staged diff includes only Lisp autonomous drain workflow, prompts, scripts, tests, fixtures, and docs updates.

- [ ] **Step 2: Commit**

Run:

```bash
git commit -m "feat: add Lisp frontend autonomous drain workflow"
```

Expected: commit succeeds.

## Acceptance Criteria

- A new v2.14 top-level workflow exists for Lisp frontend MVP/full-design work.
- The workflow has no roadmap phase gate and no `roadmap_gate_path` input.
- The selector can choose either an active backlog item or an unimplemented design gap.
- Design-gap selection drafts an implementation architecture and normalized work-item bundle before invoking the plan/implementation path.
- Backlog-selected and design-gap-selected work both route through the same Lisp work-item stack.
- Selector agency is bounded by typed output contracts; the workflow owns loop control, state roots, artifact paths, and final routing.
- Tests cover backlog, design-gap, blocked, and done branches.
- Existing NeurIPS drain regression tests still pass.
- The docs index and workflow catalog make the new workflow discoverable.
