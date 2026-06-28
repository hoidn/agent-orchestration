# Workflow Lisp Runtime-Native Drain Selector Stdlib Call Contract Regression Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair `lisp_frontend_design_delta/stdlib_adapters::select-next-work-stdlib` so the Design Delta parent drain compiles on the current WCC route by calling `selector::select-next-work` through the accepted single-`ctx` boundary, while preserving imported-selector carried-context evidence.

**Architecture:** Keep this slice family-owned and narrow: confirm the current regression with the parent-drain compile harness, replace only the stale flattened selector call in `workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc` with `(call select-next-work :ctx ctx)`, and preserve the existing projection from `SelectorPublicResult` to `DesignDeltaSelectionResult`. Acceptance is limited to the direct parent-drain compile plus the focused owner-route and carried-context selectors; the downstream runtime smoke lane remains contextual follow-up evidence only while the separate shared `std/phase` prerequisite is still red. This avoids reopening `std/drain`, selector request-record design, or projection deduplication, and it deliberately leaves that deduplication, shared `std/phase` prerequisite repair, and broader mirror cleanup for later slices.

**Tech Stack:** Workflow Lisp `.orc` modules in `workflows/library/lisp_frontend_design_delta/`, imported stdlib drain routing in `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`, focused compile/build/runtime regression checks in `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py` and `tests/test_workflow_lisp_build_artifacts.py`, and CLI compile verification via `python -m orchestrator compile`.

---

## Scope Lock

This plan owns only the selected regression:

- repair `select-next-work-stdlib` so its internal workflow call matches `selector::select-next-work ((ctx DesignDeltaDrainCtx))`;
- keep `select-next-work-stdlib` exported with the same signature and return type;
- preserve the carried `ctx` private-runtime-context evidence recorded for the imported selector adapter; and
- verify the fix with the existing focused compile and build-artifact checks already referenced by the work-item context, while recording the downstream runtime smoke lane as non-gating follow-up evidence until the shared `std/phase` prerequisite is green.

This plan does **not** own:

- changes to `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`;
- selector provider prompt/request-record redesign;
- `std/drain::backlog-drain` semantics or workflow-ref arity changes;
- gap-drafter payload carriage, terminal reprojection, work-item finalization, or transition cleanup;
- compiler/typechecker/WCC changes unless the direct call repair unexpectedly exposes a separate compiler regression; or
- whole-module runtime-fixture mirror cleanup outside `stdlib_adapters.orc`, including the currently stale mirrored `projections.orc`, `selector.orc`, and `types.orc`; or
- command adapters, helper scripts, report parsing, pointer files, stdout JSON, or compatibility-bundle rereads.

## Known Pre-Existing Verification Constraints

The repo currently has unrelated Design Delta runtime-fixture drift outside this
slice: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_work_item_runtime_fixture_mirror_matches_library_module_set`
is already red because mirrored `projections.orc`, `selector.orc`, and
`types.orc` no longer match the authoritative library modules.

Treat that failure as contextual evidence, not as an acceptance gate for this
plan. This slice may still keep
`tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/stdlib_adapters.orc`
byte-aligned when that specific mirrored file remains authoritative, but it
must not broaden scope to realign the unrelated stale modules.

The repo also has a separate shared prerequisite outside this slice:
`tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_parent_drain_imported_selector_ctx_carried_context_smoke`
currently fails in
`orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` with
`[type_unknown] unknown type ReviewLoopResult`.

Treat that failure as shared-owner context, not as an acceptance gate for this
plan. The selector-adapter repair should still rerun the smoke lane and record
whether it has turned green, but if it remains red with the same shared
`std/phase` prerequisite, this slice must split or link that prerequisite gap
instead of widening the owned fix.

## Authority Set

Use these as the governing inputs while executing:

- `docs/index.md`
- `docs/steering.md`
- `docs/capability_status_matrix.md`
- `docs/design/README.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-selector-stdlib-call-contract-regression-reopen/implementation_architecture.md`
- `state/workflow_lisp/calls/df05676c2af04fdaab9fd38aa72379e2/root.drain_lisp_frontend_work_0.lisp_frontend_drain_iteration.route_selection.desig_f289187df7d2/lisp-frontend-design-delta-design-gap-architect-v214/de14bca20ef59f36.json/work_item_context.md`
- `workflows/library/lisp_frontend_design_delta/selector.orc`
- `workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc`
- `workflows/library/lisp_frontend_design_delta/drain.orc`
- `workflows/library/lisp_frontend_design_delta/types.orc`
- `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/stdlib_adapters.orc`
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- `tests/test_workflow_lisp_build_artifacts.py`

## File Ownership Map

Inspect first:

- `workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc`
- `workflows/library/lisp_frontend_design_delta/selector.orc`
- `workflows/library/lisp_frontend_design_delta/drain.orc`
- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`
- `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/stdlib_adapters.orc`
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- `tests/test_workflow_lisp_build_artifacts.py`

Modify in this slice:

- `workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc`
- `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/stdlib_adapters.orc` only when that specific mirrored file still mirrors the authoritative library module byte-for-byte

Modify only if verification proves the checked tests no longer reflect the accepted boundary:

- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- `tests/test_workflow_lisp_build_artifacts.py`

Do not treat this slice as owner of:

- `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/projections.orc`
- `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/selector.orc`
- `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/types.orc`
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_work_item_runtime_fixture_mirror_matches_library_module_set`

Do not modify in this slice:

- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`
- compiler/typechecker/WCC modules
- command-boundary manifests
- `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/progress_ledger.json`

## Task 1: Capture The Current Regression And Confirm The Owned Boundary

**Files:**

- Inspect: `workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc`
- Inspect: `workflows/library/lisp_frontend_design_delta/selector.orc`
- Inspect: `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`
- Inspect: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- Inspect: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] **Step 1: Confirm the stale flattened selector bindings are still present**

Run:

```bash
rg -n "call select-next-work|:steering|:target_design|:baseline_design|:manifest|:progress_ledger|:run_state" \
  workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc \
  workflows/library/lisp_frontend_design_delta/selector.orc \
  orchestrator/workflow_lisp/stdlib_modules/std/drain.orc
```

Expected:

- `selector.orc` shows `defworkflow select-next-work ((ctx DesignDeltaDrainCtx))`;
- `std/drain.orc` shows the owner route calling selector refs as `:ctx ctx`; and
- `stdlib_adapters.orc` still shows the stale flattened keyword call that this slice owns.

- [ ] **Step 2: Reproduce the parent-drain compile failure before editing**

Run:

```bash
python -m orchestrator compile \
  workflows/library/lisp_frontend_design_delta/drain.orc \
  --entry-workflow lisp_frontend_design_delta/drain::drain \
  --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json \
  --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
```

Expected:

- compile fails before the edit;
- the failure is `workflow_signature_mismatch`; and
- the unexpected binding reported from `workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc` is `steering` or another stale flat selector binding, not a new unrelated diagnostic.

- [ ] **Step 3: Confirm the focused regression harness still targets this route**

Run:

```bash
python -m pytest --collect-only \
  tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py \
  tests/test_workflow_lisp_build_artifacts.py \
  -q
```

Expected:

- collection succeeds; and
- the module set contains the focused selector-owner-route tests this slice will use after the repair.

- [ ] **Step 4: Record the known unrelated fixture-mirror drift without promoting it into this slice**

Run:

```bash
python -m pytest \
  tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_work_item_runtime_fixture_mirror_matches_library_module_set \
  -q
```

Expected:

- this selector may already fail before any edit because unrelated mirrored modules drifted;
- if it fails, the mismatched files are outside this slice's owned edits unless `stdlib_adapters.orc` is also reported; and
- the result is recorded as pre-existing context, not as a blocker for executing or verifying this plan.

## Task 2: Repair The Family-Owned Selector Adapter Call Site

**Files:**

- Modify: `workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc`
- Modify with the same source bytes when the checked mirror remains authoritative: `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/stdlib_adapters.orc`
- Inspect while editing: `workflows/library/lisp_frontend_design_delta/selector.orc`

- [ ] **Step 1: Replace the stale flattened selector call with the accepted single-context call**

Implementation requirements:

- inside `defworkflow select-next-work-stdlib`, change the `selection` binding from the removed flattened keyword call to:

```lisp
(call select-next-work
  :ctx ctx)
```

- keep `select-next-work-stdlib` as `((ctx DesignDeltaDrainCtx)) -> DesignDeltaSelectionResult`;
- do not widen the workflow boundary, add wrapper workflows, or introduce helper scripts; and
- do not change the downstream payload projection fields unless compile/typecheck forces a narrowly related fix.

- [ ] **Step 2: Preserve the existing projection behavior**

Implementation requirements:

- keep the current `selected-payload` and `design-gap-payload` construction equivalent to the pre-fix logic;
- preserve the existing `SELECTED`, `GAP`, `EMPTY`, and `BLOCKED` result mapping into `DesignDeltaSelectionResult`;
- keep `ctx.run_state_path` as the carried run-state value for `EMPTY` and `BLOCKED`; and
- leave any duplication with `lisp_frontend_design_delta/stdlib_payloads::project-selection-result` untouched in this slice.

- [ ] **Step 3: Keep the checked runtime fixture mirror aligned if it still mirrors the library module**

Implementation requirements:

- compare only `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/stdlib_adapters.orc` against the authoritative library file for this slice;
- if that specific mirrored file is still intended to mirror the library module, update it in the same change; and
- do not widen the edit to unrelated mirrored modules even if the whole-module mirror selector remains red;
- if `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/stdlib_adapters.orc` is still part of the authoritative mirror set, copy the updated authoritative `stdlib_adapters.orc` contents into that fixture in the same change;
- do not reinterpret, reformat, or independently edit the mirrored fixture logic; and
- if the mirror invariant itself appears obsolete, stop and record that as a separate gap instead of silently drifting the fixture in this slice.

- [ ] **Step 4: Sanity-check that no stale flat selector call remains in the edited adapter**

Run:

```bash
rg -n "call select-next-work|:steering|:target_design|:baseline_design|:manifest|:progress_ledger|:run_state" \
  workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc
```

Expected:

- the `call select-next-work` site now binds only `:ctx ctx`; and
- any remaining `:steering_path`, `:target_design_path`, `:baseline_design_path`, `:progress_ledger_path`, or `:run_state_path` references are only payload-field reads from `ctx`, not call arguments to `select-next-work`.

- [ ] **Step 5: If the fixture file was updated, confirm byte equality for the owned mirrored file only**

Run:

```bash
cmp -s \
  workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc \
  tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/stdlib_adapters.orc
```

Expected:

- exit status `0` when the fixture file was updated because it still mirrors the authoritative module; or
- this check is skipped only when the per-file mirror invariant was confirmed obsolete and recorded as a separate gap.

## Task 3: Verify Compile And Carried-Context Evidence

**Files:**

- Verify against: `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/stdlib_adapters.orc`
- Verify against: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- Verify against: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] **Step 1: Re-run the direct parent-drain compile**

Run:

```bash
python -m orchestrator compile \
  workflows/library/lisp_frontend_design_delta/drain.orc \
  --entry-workflow lisp_frontend_design_delta/drain::drain \
  --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json \
  --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
```

Expected:

- compile exits successfully;
- there is no `workflow_signature_mismatch` for the selector adapter; and
- the repaired route still compiles through the current WCC/imported-stdlib path.

- [ ] **Step 2: Run the focused owner-route and carried-context regression selectors**

Run:

```bash
python -m pytest \
  tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_parent_drain_entrypoint_adopts_stdlib_owner_routes \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_artifacts_record_imported_selector_carried_context \
  -q
```

Expected:

- both selectors pass;
- the parent drain compile path now reaches imported `std/drain::backlog-drain`;
- and build artifacts still record one private carried `ctx` binding for `select-next-work-stdlib`.

- [ ] **Step 3: Probe the downstream runtime smoke lane without making it a completion gate**

Run:

```bash
python -m pytest \
  tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_parent_drain_imported_selector_ctx_carried_context_smoke \
  -q
```

Expected:

- if the shared `std/phase` prerequisite has landed, the selector passes and no `private_exec_context_bootstrap_unsupported` regression appears;
- if the selector is still red, the failure is recorded as shared-owner context only when it remains the non-owned `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` `[type_unknown] unknown type ReviewLoopResult` diagnostic; and
- any new failure that points back into `stdlib_adapters.orc` or another owned selector-boundary regression is treated as new evidence to classify under Task 4 before widening scope.

- [ ] **Step 4: If the owned mirrored file was updated, confirm its byte alignment separately from the known broader mirror drift**

Run:

```bash
cmp -s \
  workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc \
  tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/stdlib_adapters.orc
```

Expected:

- exit status `0` when this slice updated the owned mirrored file; and
- no claim is made here about unrelated mirrored modules covered by the separately failing whole-module selector.

- [ ] **Step 5: Re-run collection for the focused modules**

Run:

```bash
python -m pytest --collect-only \
  tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py \
  tests/test_workflow_lisp_build_artifacts.py \
  -q
```

Expected:

- collection succeeds cleanly after the edit; and
- no test discovery or import regressions were introduced while fixing the adapter route.

## Task 4: Handle Follow-On Diagnostics Without Expanding Scope

**Files:**

- No default modifications; inspect only if verification fails

- [ ] **Step 1: Classify any remaining failure before touching more code**

Decision rules:

- if verification still fails with another selector boundary mismatch inside `stdlib_adapters.orc`, keep the fix in the same file only if it is the same single-context regression class;
- if the next failure comes from `std/drain`, shared compiler/typecheck modules, the known `std/phase` `ReviewLoopResult` prerequisite, gap-drafter payload carriage, or terminal reprojection, stop and record it as a separate gap instead of widening this slice;
- if the failure suggests scripts, adapter manifests, report parsing, or compatibility-bundle rereads, reject that path because `docs/design/workflow_command_adapter_contract.md` and the implementation architecture forbid solving this regression with hidden command glue.

- [ ] **Step 2: Record bounded completion evidence**

Completion checklist:

- the only production source change is the family-owned selector adapter call site, with the checked runtime fixture mirror updated only to preserve byte alignment when that invariant still applies;
- direct compile succeeds on the documented Design Delta parent entrypoint;
- the focused owner-route and carried-context pytest selectors pass, with module-level `--collect-only` still clean;
- the downstream runtime smoke selector is either green or recorded as still blocked only by the pre-existing shared `std/phase` `ReviewLoopResult` prerequisite; and
- the resulting implementation can be summarized as a selector-boundary repair, not a broader drain-family migration milestone.
