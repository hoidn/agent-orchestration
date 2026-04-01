# Workflow Boundary `kind`/`type` Redundancy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove author-facing redundancy around workflow-boundary `inputs` / `outputs` that currently repeat `kind: relpath` and `type: relpath`, while preserving compatibility and keeping artifact contracts unchanged.

**Architecture:** Treat workflow-boundary contracts as effectively type-driven in authoring guidance and advisory linting. Keep current loader compatibility so existing workflows continue to load, but steer authors toward `type: relpath` alone for boundary paths and reserve `kind` as the meaningful discriminator for top-level `artifacts`. Add an advisory lint warning for explicit redundant boundary `kind: relpath`, then simplify canonical docs and workflow examples to match the preferred style.

**Tech Stack:** YAML DSL/spec docs, Python loader/linting, workflow examples/library workflows, pytest loader/linting/example coverage, orchestrator dry-run validation.

---

## Recommended Design

Recommended approach:
- keep workflow-boundary `kind` accepted for backward compatibility
- document that workflow `inputs` / `outputs` should normally omit `kind` and rely on `type`
- add a v2.9 advisory lint warning when a workflow boundary explicitly sets `kind: relpath` together with `type: relpath`
- update current examples and library workflows to use the simpler form

Rejected alternatives:
- remove `kind` from workflow boundaries immediately: too breaking for existing `2.1+` workflows
- do docs-only cleanup with no lint signal: too easy for old verbose patterns to persist indefinitely
- remove `kind` from all contract surfaces: wrong, because `artifacts` still need real `relpath|scalar` storage semantics

## Scope Boundaries

In scope:
- workflow `inputs`
- workflow `outputs`
- v2.x workflow examples and reusable library workflows
- authoring docs, spec wording, and advisory lint

Out of scope:
- top-level `artifacts`
- `expected_outputs`
- `output_bundle`
- historical ADR / plan docs except where they are the active implementation plan for this cleanup

## Task Breakdown

### Task 1: Pin the intended contract split in specs and authoring docs

**Files:**
- Modify: `specs/dsl.md`
- Modify: `specs/versioning.md`
- Modify: `docs/workflow_drafting_guide.md`
- Reference: `docs/plans/2026-02-26-adr-prompt-consume-scope-and-scalar-artifacts.md`

**Step 1: Clarify the workflow-boundary model in the DSL spec**

Document in `specs/dsl.md`:
- workflow `inputs` / `outputs` still accept `kind` for compatibility
- for boundary contracts, `kind: relpath` + `type: relpath` is redundant
- preferred authoring style is to omit `kind` when the boundary value is a relpath
- `under` and `must_exist_target` remain valid only for relpath-typed boundary values

**Step 2: Add the migration note in versioning**

Document in `specs/versioning.md`:
- this is an ergonomics cleanup, not a semantic runtime change
- existing workflows with explicit boundary `kind: relpath` remain valid
- v2.9+ lint may warn about redundant boundary `kind`

**Step 3: Update workflow author guidance**

Document in `docs/workflow_drafting_guide.md`:
- use `type: relpath` alone for workflow `inputs` / `outputs`
- keep `kind` only where it adds meaning, especially top-level `artifacts`
- show one before/after example

**Step 4: Read back the edited sections**

Run:

```bash
sed -n '1,80p' specs/dsl.md
sed -n '140,210p' specs/versioning.md
sed -n '180,240p' docs/workflow_drafting_guide.md
```

Expected:
- all three documents describe the same preferred authoring pattern

**Step 5: Commit**

```bash
git add specs/dsl.md specs/versioning.md docs/workflow_drafting_guide.md
git commit -m "docs: clarify workflow boundary relpath contracts"
```

### Task 2: Add failing tests for the preferred boundary form and new lint

**Files:**
- Modify: `tests/test_loader_validation.py`
- Modify: `tests/test_dsl_linting.py`
- Modify: `tests/test_workflow_output_contract_integration.py`

**Step 1: Pin the existing compatibility behavior**

Add loader/runtime tests covering:
- workflow `inputs` with `type: relpath` and no `kind`
- workflow `outputs` with `type: relpath` and no `kind`
- existing explicit `kind: relpath` + `type: relpath` still loads

**Step 2: Add failing advisory lint tests**

Add lint tests covering:
- warning on workflow `inputs.<name>.kind: relpath` + `type: relpath`
- warning on workflow `outputs.<name>.kind: relpath` + `type: relpath`
- no warning for top-level `artifacts`
- no warning for `kind: scalar`

**Step 3: Run narrow selectors to verify failure**

Run:

```bash
pytest tests/test_loader_validation.py tests/test_dsl_linting.py tests/test_workflow_output_contract_integration.py -k "relpath and (workflow or lint)" -v
```

Expected:
- new lint tests fail before implementation

**Step 4: Collect-only if test names/files changed**

Run:

```bash
pytest --collect-only tests/test_loader_validation.py tests/test_dsl_linting.py tests/test_workflow_output_contract_integration.py -q
```

Expected:
- the new tests are collected

**Step 5: Commit**

```bash
git add tests/test_loader_validation.py tests/test_dsl_linting.py tests/test_workflow_output_contract_integration.py
git commit -m "test: pin workflow boundary relpath contract ergonomics"
```

### Task 3: Implement advisory lint for redundant boundary `kind`

**Files:**
- Modify: `orchestrator/workflow/linting.py`
- Modify: `orchestrator/cli/commands/report.py` (only if output rendering needs path/suggestion tweaks)
- Modify: `orchestrator/cli/commands/run.py` (only if warning formatting needs alignment)
- Test: `tests/test_dsl_linting.py`

**Step 1: Add a boundary-contract lint rule**

In `orchestrator/workflow/linting.py`, add a rule that walks top-level workflow `inputs` and `outputs` and emits a warning when:
- `kind == "relpath"`
- `type == "relpath"`

Suggested warning shape:
- `code`: `redundant-boundary-kind-relpath`
- `path`: e.g. `inputs.design_path` or `outputs.plan_path`
- message explaining that workflow boundaries should prefer `type: relpath` alone

**Step 2: Keep the rule scoped**

Ensure the rule does not fire for:
- top-level `artifacts`
- scalar boundary contracts
- malformed contracts that already fail validation

**Step 3: Run narrow tests to make them pass**

Run:

```bash
pytest tests/test_dsl_linting.py tests/test_loader_validation.py tests/test_workflow_output_contract_integration.py -k "relpath and (workflow or lint)" -v
```

Expected:
- passing lint and compatibility tests

**Step 4: Commit**

```bash
git add orchestrator/workflow/linting.py tests/test_dsl_linting.py tests/test_loader_validation.py tests/test_workflow_output_contract_integration.py
git commit -m "feat: lint redundant workflow boundary relpath kind"
```

### Task 4: Rewrite current examples and library workflows to the preferred form

**Files:**
- Modify: `workflows/examples/dsl_follow_on_plan_impl_review_loop_v2.yaml`
- Modify: `workflows/library/follow_on_plan_phase.yaml`
- Modify: `workflows/library/follow_on_implementation_phase.yaml`
- Modify: `workflows/library/tracked_design_phase.yaml`
- Modify: `workflows/library/review_fix_loop.yaml`
- Modify: `workflows/README.md` (only if examples mention the verbose boundary form)

**Step 1: Remove redundant boundary `kind: relpath`**

For workflow `inputs` / `outputs` only:
- delete explicit `kind: relpath`
- keep `type: relpath`
- leave top-level `artifacts` unchanged

**Step 2: Verify no accidental artifact changes**

Run:

```bash
rg -n "kind: relpath|type: relpath" workflows/examples workflows/library
```

Expected:
- boundary contracts use `type: relpath` alone
- top-level artifacts may still use `kind: relpath` where required

**Step 3: Run workflow validation and focused tests**

Run:

```bash
pytest tests/test_workflow_examples_v0.py -k "workflow_examples_v0_load or follow_on_plan_impl_review_loop_v2" -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/dsl_follow_on_plan_impl_review_loop_v2.yaml --dry-run --input upstream_state_path=workflows/examples/inputs/dsl-follow-on-upstream-completed-state.json --input design_path=docs/plans/2026-03-06-dsl-evolution-control-flow-and-reuse.md --stream-output
```

Expected:
- example tests pass
- dry-run validation succeeds

**Step 4: Commit**

```bash
git add workflows/examples/dsl_follow_on_plan_impl_review_loop_v2.yaml workflows/library/follow_on_plan_phase.yaml workflows/library/follow_on_implementation_phase.yaml workflows/library/tracked_design_phase.yaml workflows/library/review_fix_loop.yaml workflows/README.md
git commit -m "refactor: simplify workflow boundary relpath contracts"
```

### Task 5: Optional follow-up decision on full schema cleanup

**Files:**
- Modify: `docs/backlog/active/2026-03-09-workflow-boundary-kind-type-redundancy.md`
- Optional future plan: `docs/plans/<future-date>-remove-workflow-boundary-kind.md`

**Step 1: Reassess after the lint/docs cleanup lands**

Decide whether the repo still wants a later breaking simplification:
- remove `kind` from workflow `inputs` / `outputs` entirely
- keep compatibility forever with lint-only guidance

**Step 2: If removal is desired, spin a new plan**

That later plan should cover:
- DSL version gate
- loader rejection path
- migration docs
- example rewrites already being complete from Task 4

**Step 3: Do not mix this with the compatibility-preserving cleanup**

Keep the current work scoped to:
- docs
- lint
- example authoring style

## Verification Summary

Minimum verification for the compatibility-preserving cleanup:

```bash
pytest --collect-only tests/test_loader_validation.py tests/test_dsl_linting.py tests/test_workflow_output_contract_integration.py tests/test_workflow_examples_v0.py -q
pytest tests/test_loader_validation.py tests/test_dsl_linting.py tests/test_workflow_output_contract_integration.py -k "relpath and (workflow or lint)" -v
pytest tests/test_workflow_examples_v0.py -k "workflow_examples_v0_load or follow_on_plan_impl_review_loop_v2" -v
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/dsl_follow_on_plan_impl_review_loop_v2.yaml --dry-run --input upstream_state_path=workflows/examples/inputs/dsl-follow-on-upstream-completed-state.json --input design_path=docs/plans/2026-03-06-dsl-evolution-control-flow-and-reuse.md --stream-output
git diff --check
```

Expected:
- compatibility tests still pass
- new lint warning is emitted only for redundant boundary `kind`
- current examples validate with the simpler boundary form
