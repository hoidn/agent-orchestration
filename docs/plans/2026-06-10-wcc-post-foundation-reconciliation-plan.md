# WCC Post-Foundation Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate `feat/wcc-middle-end` as the accepted compiler substrate for the post-foundation composition work, then resume post-foundation implementation only on top of the WCC route.

**Architecture:** Keep `docs/design/workflow_lisp_core_calculus_middle_end.md` and `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md` separate. WCC owns how nested control, joins, loops, and stdlib lowering are compiled; the post-foundation design owns the remaining migration roadmap: private context, typed projection, certified adapters, resource transitions, parent-callable workflow families, and promotion evidence.

**Tech Stack:** Git integration branch, Workflow Lisp compiler/lowering/WCC modules, pytest characterization and Workflow Lisp suites, orchestrator dry-run/smoke checks, docs/plans reconciliation record.

---

## Context And Non-Negotiables

- Repo rule: do not create worktrees. Use the existing checkout after the active dirty changes are committed, shelved, or otherwise intentionally handled.
- Current mainline has post-foundation implementation work that continued on the legacy lowering route.
- `feat/wcc-middle-end` implements WCC M0-M4 and most of M5, including default WCC lowering for new compiles while preserving legacy schema-1 compatibility.
- The collision is semantic: both lines touch nested control and lowering internals. Merge resolution must be policy-driven, not textual.
- Do not merge the WCC design document into the post-foundation design document. Update the post-foundation design to consume WCC as its composition substrate.

## File Map

### Branch / Merge Inputs

- Read: `docs/design/workflow_lisp_core_calculus_middle_end.md`
- Read: `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
- Read: `docs/design/workflow_lisp_frontend_specification.md`
- Read: `docs/design/workflow_lisp_runtime_migration_foundation.md`
- Read: `docs/reports/2026-06-09-design-delta-drain-orc-migration-frontend-runtime-findings.md`
- Compare: `main...feat/wcc-middle-end`

### Likely Conflict Files

- Modify/resolve: `orchestrator/loader.py`
- Modify/resolve: `orchestrator/workflow/elaboration.py`
- Modify/resolve: `orchestrator/workflow/executable_ir.py`
- Modify/resolve: `orchestrator/workflow_lisp/compiler.py`
- Modify/resolve: `orchestrator/workflow_lisp/__init__.py`
- Modify/resolve: `orchestrator/workflow_lisp/build.py`
- Modify/resolve: `orchestrator/workflow_lisp/diagnostics.py`
- Modify/resolve: `orchestrator/workflow_lisp/lowering/control_dispatch.py`
- Modify/resolve: `orchestrator/workflow_lisp/lowering/control_loops.py`
- Modify/resolve: `orchestrator/workflow_lisp/lowering/context.py`
- Modify/resolve: `orchestrator/workflow_lisp/lowering/core.py`
- Modify/resolve: `orchestrator/workflow_lisp/lowering/effects.py`
- Modify/resolve: `orchestrator/workflow_lisp/lowering/phase_scope.py`
- Modify/resolve: `orchestrator/workflow_lisp/lowering/procedures.py`
- Modify/resolve: `orchestrator/workflow_lisp/lowering/workflow_calls.py`
- Modify/resolve: `orchestrator/workflow_lisp/typecheck_calls.py`
- Modify/resolve: `orchestrator/workflow_lisp/workflows.py`
- Modify/resolve: `orchestrator/workflow/executor.py`
- Modify/resolve: `orchestrator/workflow/loops.py`
- Modify/resolve: `orchestrator/cli/commands/resume.py`
- Modify/resolve: `tests/test_resume_command.py`
- Modify/resolve: `tests/test_workflow_lisp_build_artifacts.py`
- Modify/resolve: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- Modify/resolve: `tests/test_workflow_lisp_diagnostics.py`
- Modify/resolve: `tests/test_workflow_lisp_lowering.py`
- Modify/resolve: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify/resolve: `tests/test_workflow_lisp_source_map.py`

### WCC-Owned Files To Preserve

- Preserve/add: `orchestrator/workflow_lisp/wcc/model.py`
- Preserve/add: `orchestrator/workflow_lisp/wcc/elaborate.py`
- Preserve/add: `orchestrator/workflow_lisp/wcc/anf.py`
- Preserve/add: `orchestrator/workflow_lisp/wcc/analysis.py`
- Preserve/add: `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- Preserve/add: `orchestrator/workflow_lisp/wcc/lower.py`
- Preserve/add: `orchestrator/workflow_lisp/wcc/route.py`
- Preserve/add: `tests/workflow_lisp_characterization.py`
- Preserve/add: `tests/test_workflow_lisp_wcc_m1.py`
- Preserve/add: `tests/test_workflow_lisp_wcc_m2.py`
- Preserve/add: `tests/test_workflow_lisp_wcc_m3.py`
- Preserve/add: `tests/test_workflow_lisp_wcc_m4.py`
- Preserve/add: `tests/test_workflow_lisp_wcc_m5.py`
- Preserve/add: `tests/test_workflow_lisp_wcc_characterization.py`
- Preserve/add: `tests/fixtures/workflow_lisp/characterization/**`

### Post-Foundation Work To Rebase Onto WCC

- Preserve if still applicable: private executable context bridge changes.
- Preserve if still applicable: selector bundle typed projection changes.
- Preserve if still applicable: certified adapter declaration changes.
- Preserve if still applicable: resource-transition changes.
- Preserve if still applicable: parent-callable implementation/work-item composition changes.
- Retire or confine to legacy schema-1: bespoke nested structured-control helper hoisting.
- Preserve on legacy only or prove redundant on WCC: returned-variant / F3 fixes in legacy match lowering.

### Docs To Update After Integration

- Modify: `docs/index.md`
- Modify: `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
- Modify: `docs/design/workflow_lisp_core_calculus_middle_end.md`
- Modify: `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- Optionally modify: `docs/capability_status_matrix.md`
- Optionally modify: `docs/design/README.md`

## Merge Policy

- WCC is the default implementation route for new nested control, stdlib review/revise composition, loops, and union result normalization.
- Mainline helper-hoisting nested-control code is compatibility-only unless a test proves it remains required for schema-1 resume or legacy route behavior.
- Mainline F3 returned-variant behavior must remain correct on the legacy route or be explicitly covered by WCC route tests and documented as redundant for new compiles.
- Resume behavior must preserve both:
  - branch `feat/wcc-middle-end` schema-2 / mixed-schema resume safety; and
  - mainline stale `repeat_until` failed-step clearing from commit `9085577`.
- No WCC node, route name, `ProcRef`, provider ref, prompt ref, type object, or route metadata may leak into runtime artifacts, workflow outputs, provider/command payloads, or public source-map labels.
- Legacy lowerers may remain only where compatibility evidence says they are still needed. Each retained lowerer needs a retirement issue/gap or explicit compatibility label.
- Acceptance must include both WCC evidence and post-foundation evidence. WCC passing alone is not parent-callable family parity.

## Task 1: Freeze Compiler-Lane Drain Work

**Files:**
- Modify: `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`

- [ ] **Step 1: Inspect pre-existing work-instructions edits**

Run:

```bash
git status --short docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md
git diff -- docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md
```

Expected: understand whether `work_instructions.md` already has unrelated
active-drain edits. Do not bundle unrelated edits into the gate commit.

- [ ] **Step 2: Commit or park pre-existing work-instructions edits**

If the file already has unrelated edits, either:

- commit them separately with their own message; or
- restore/park them only with explicit human approval.

Expected: the subsequent gate commit contains only the reconciliation gate.

- [ ] **Step 3: Add a temporary selector gate**

Add text stating that until WCC/post-foundation reconciliation lands, the drain must not select new gaps that modify compiler lowering internals:

```markdown
Temporary reconciliation gate:

- Do not select new gaps that modify Workflow Lisp lowering, WCC, control
  dispatch, match/loop lowering, phase scope, procedure lowering, or workflow
  call lowering until `feat/wcc-middle-end` is integrated with this branch.
- If a selected gap requires those files, stop and select the WCC/post-foundation
  reconciliation work first.
- Orthogonal lanes may continue only when they avoid compiler/lowering files.
```

- [ ] **Step 4: Verify the gate is visible**

Run:

```bash
rg -n "Temporary reconciliation gate|feat/wcc-middle-end|compiler/lowering" \
  docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md
```

Expected: the new gate text is found.

- [ ] **Step 5: Commit and push the gate on main**

Run:

```bash
git add docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md
git commit -m "Gate post-foundation compiler work on WCC reconciliation"
git push origin main
```

Expected: one docs-only commit on `main`, pushed so the active drain and future
workers see the selector gate.

## Task 2: Capture Branch Inventory And Conflict Surface

**Files:**
- Create: `docs/plans/2026-06-10-wcc-post-foundation-reconciliation-inventory.md`

- [ ] **Step 1: Record branch divergence**

Run:

```bash
git fetch origin
git rev-parse feat/wcc-middle-end
git rev-parse origin/feat/wcc-middle-end
test "$(git rev-parse feat/wcc-middle-end)" = "$(git rev-parse origin/feat/wcc-middle-end)"
git rev-list --left-right --count main...feat/wcc-middle-end
git diff --name-only main...feat/wcc-middle-end > /tmp/wcc-files.txt
git diff --stat main...feat/wcc-middle-end > /tmp/wcc-stat.txt
```

Expected: local `feat/wcc-middle-end` exactly matches `origin/feat/wcc-middle-end`;
command output shows divergent commits and file list. If the local branch is
stale, update it or merge `origin/feat/wcc-middle-end` explicitly instead.

- [ ] **Step 2: Create the inventory document**

Create `docs/plans/2026-06-10-wcc-post-foundation-reconciliation-inventory.md` with:

```markdown
# WCC / Post-Foundation Reconciliation Inventory

## Branches

- Mainline branch:
- WCC branch:
- Merge base:
- Main-only commits:
- WCC-only commits:

## Overlap

### Compiler / Lowering Overlap

### Resume / Runtime Overlap

### Tests / Fixtures Overlap

### Workflow Config Overlap

## Policy

- WCC wins for new/default nested control and stdlib route.
- Legacy helper-hoisting remains compatibility-only if needed.
- Resume fixes from both sides must be preserved.
- Post-foundation non-compiler lanes remain authoritative for private context,
  projection, adapters, resources, and parent-callable parity.
```

- [ ] **Step 3: Fill the document from git output**

Use `/tmp/wcc-files.txt` and `/tmp/wcc-stat.txt`.

- [ ] **Step 4: Commit the inventory**

Run:

```bash
git add docs/plans/2026-06-10-wcc-post-foundation-reconciliation-inventory.md
git commit -m "Document WCC post-foundation reconciliation inventory"
```

Expected: one docs-only commit.

## Task 3: Create Integration Branch And Merge WCC

**Files:**
- Modify: conflict files reported by Git.

- [ ] **Step 1: Confirm clean enough worktree**

Run:

```bash
git status --short
```

Expected: no unrelated unstaged implementation changes. If there are unrelated changes, stop and commit or intentionally park them before merging.

- [ ] **Step 2: Create integration branch**

Run:

```bash
git switch main
git switch -c integrate/wcc-post-foundation
```

Expected: new branch `integrate/wcc-post-foundation`.

- [ ] **Step 3: Merge pinned WCC branch**

Run:

```bash
test "$(git rev-parse feat/wcc-middle-end)" = "$(git rev-parse origin/feat/wcc-middle-end)"
git merge --no-ff feat/wcc-middle-end
```

Expected: merge either succeeds or reports conflicts.

- [ ] **Step 4: List conflicts**

Run:

```bash
git diff --name-only --diff-filter=U
```

Expected: conflict files listed. Continue to Task 4.

## Task 4: Resolve Compiler / Lowering Conflicts By Policy

**Files:**
- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/loader.py`
- Modify: `orchestrator/workflow/elaboration.py`
- Modify: `orchestrator/workflow/executable_ir.py`
- Modify: `orchestrator/workflow_lisp/__init__.py`
- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `orchestrator/workflow_lisp/diagnostics.py`
- Modify: `orchestrator/workflow_lisp/lowering/control_dispatch.py`
- Modify: `orchestrator/workflow_lisp/lowering/control_loops.py`
- Modify: `orchestrator/workflow_lisp/lowering/context.py`
- Modify: `orchestrator/workflow_lisp/lowering/core.py`
- Modify: `orchestrator/workflow_lisp/lowering/effects.py`
- Modify: `orchestrator/workflow_lisp/lowering/phase_scope.py`
- Modify: `orchestrator/workflow_lisp/lowering/procedures.py`
- Modify: `orchestrator/workflow_lisp/lowering/workflow_calls.py`
- Modify: `orchestrator/workflow_lisp/typecheck_calls.py`
- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- Modify: `tests/test_workflow_lisp_diagnostics.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_source_map.py`
- Modify: WCC files if conflict markers appear.

- [ ] **Step 1: Preserve WCC route selection as default for new compiles**

Inspect:

```bash
rg -n "lowering_route|wcc_m4|legacy|schema" orchestrator/workflow_lisp/compiler.py
```

Expected: default new-compile route is WCC/schema-2 as implemented by `feat/wcc-middle-end`; legacy remains available only as compatibility.

- [ ] **Step 2: Preserve legacy route compatibility**

Inspect:

```bash
rg -n "legacy|schema-1|schema_1|wcc_m4" orchestrator/workflow_lisp/lowering orchestrator/workflow_lisp/compiler.py
```

Expected: legacy route still exists for old workflows/resume compatibility.

- [ ] **Step 3: Remove duplicate new-route helper-hoisting behavior**

In conflict resolutions, do not make helper hoisting the WCC/default route for new compiles. If helper hoisting remains, it must be reachable only through legacy/schema-1 compatibility.

Run:

```bash
rg -n "helper hoist|helper_hoist|hoist|legacy" orchestrator/workflow_lisp/lowering orchestrator/workflow_lisp/wcc
```

Expected: any helper-hoisting path is not part of WCC route implementation.

- [ ] **Step 4: Preserve F3 behavior where still relevant**

Run:

```bash
rg -n "returned variant|variant identity|source case|matched case|inject|variant-scoped" \
  orchestrator/workflow_lisp/lowering orchestrator/workflow_lisp/wcc tests
```

Expected: WCC tests prove returned variant identity from explicit injection; legacy behavior remains covered if legacy code is retained.

- [ ] **Step 5: Remove all conflict markers**

Run:

```bash
rg -n "<<<<<<<|=======|>>>>>>>" orchestrator tests docs workflows
```

Expected: no matches.

## Task 5: Reconcile Resume / Runtime Behavior

**Files:**
- Modify: `orchestrator/cli/commands/resume.py`
- Modify: `orchestrator/workflow/executor.py`
- Modify: `orchestrator/workflow/loops.py`
- Modify: `orchestrator/state.py`
- Modify: `tests/test_resume_command.py`

- [ ] **Step 1: Preserve schema-2 resume safety**

Run:

```bash
rg -n "schema|lowering_schema|mixed-schema|schema-2|schema_2|resume" \
  orchestrator/cli/commands/resume.py orchestrator/workflow orchestrator/state.py tests/test_resume_command.py
```

Expected: WCC branch's mixed-schema resume behavior is still present.

- [ ] **Step 2: Preserve stale repeat-until failed-step clearing**

Run:

```bash
rg -n "clear_loop_step|clears_stale_failed_nested_call_result|stale failed" \
  orchestrator/state.py orchestrator/workflow/executor.py orchestrator/workflow/loops.py tests/test_resume_command.py
```

Expected: `clear_loop_step` helper and regression test from commit `9085577` remain.

- [ ] **Step 3: Collect focused resume tests**

Run:

```bash
pytest --collect-only tests/test_resume_command.py -q \
  -k "entry_managed_write_root or lowering_schema or repeat_until_resume_clears_stale_failed_nested_call_result_while_child_reruns or repeat_until_resume_preserves_nested_call_frames_and_lowered_match_progress or repeat_until_smoke_resume_restarts_unfinished_iteration_without_replaying_completed_nested_steps"
```

Expected: selector collects the intended tests and does not return "no tests
ran".

- [ ] **Step 4: Run focused resume tests**

Run:

```bash
pytest tests/test_resume_command.py -k "entry_managed_write_root or lowering_schema or repeat_until_resume_clears_stale_failed_nested_call_result_while_child_reruns or repeat_until_resume_preserves_nested_call_frames_and_lowered_match_progress or repeat_until_smoke_resume_restarts_unfinished_iteration_without_replaying_completed_nested_steps" -q
```

Expected: selected tests pass.

## Task 6: Run WCC Evidence Matrix

**Files:**
- Test-only task.

- [ ] **Step 1: Collect WCC tests**

Run:

```bash
pytest --collect-only \
  tests/test_workflow_lisp_wcc_m1.py \
  tests/test_workflow_lisp_wcc_m2.py \
  tests/test_workflow_lisp_wcc_m3.py \
  tests/test_workflow_lisp_wcc_m4.py \
  tests/test_workflow_lisp_wcc_m5.py \
  tests/test_workflow_lisp_wcc_characterization.py -q
```

Expected: collection succeeds.

- [ ] **Step 2: Run WCC milestone suites**

Run:

```bash
pytest \
  tests/test_workflow_lisp_wcc_m1.py \
  tests/test_workflow_lisp_wcc_m2.py \
  tests/test_workflow_lisp_wcc_m3.py \
  tests/test_workflow_lisp_wcc_m4.py \
  tests/test_workflow_lisp_wcc_m5.py \
  tests/test_workflow_lisp_wcc_characterization.py -q
```

Expected: all selected WCC tests pass.

## Task 7: Run Post-Foundation Evidence Matrix

**Files:**
- Test-only task.

- [ ] **Step 1: Run parent-callable and design-delta feasibility tests**

Run:

```bash
pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q
```

Expected: pass, or failures identify WCC/post-foundation mismatches that need code resolution before continuing.

- [ ] **Step 2: Run workflow refs and output contract tests touched by mainline post-foundation work**

Run:

```bash
pytest \
  tests/test_workflow_lisp_workflow_refs.py \
  tests/test_output_contract_collections.py -q
```

Expected: pass.

- [ ] **Step 3: Prove mainline parent-callable fixture under WCC/default schema**

Run the post-foundation parent-callable implementation-phase fixture on the
integrated default WCC route. Use the exact test name if it exists after merge;
otherwise add or update one before proceeding.

Start with:

```bash
pytest --collect-only tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q \
  -k "parent_callable or implementation_phase or wcc"
pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q \
  -k "parent_callable and implementation_phase"
```

Expected: the parent-callable implementation-phase fixture compiles and, where
applicable, smokes under the WCC/default schema. If it requires helper-hoisting
specific behavior, record a WCC compatibility gap and fix the WCC route; do not
keep helper hoisting as the new/default path.

- [ ] **Step 4: Run core Workflow Lisp regression band**

Run:

```bash
pytest \
  tests/test_workflow_lisp_examples.py \
  tests/test_workflow_lisp_modules.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_build_artifacts.py -q
```

Expected: pass.

## Task 8: Run Orchestrator Smoke / Dry-Run Checks

**Files:**
- Test-only task.

- [ ] **Step 1: Dry-run the active post-foundation drain workflow**

Run:

```bash
python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml \
  --dry-run \
  --input target_design_path=docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md \
  --input baseline_design_path=docs/design/workflow_lisp_frontend_specification.md \
  --input steering_path=docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md \
  --input progress_ledger_path=state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json \
  --input drain_state_root=state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain \
  --input run_state_target_path=state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/run_state.json \
  --input artifact_work_root=artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN \
  --input artifact_review_root=artifacts/review/LISP-FRONTEND-AUTONOMOUS-DRAIN \
  --input artifact_checks_root=artifacts/checks/LISP-FRONTEND-AUTONOMOUS-DRAIN
```

Expected: dry-run succeeds. If required inputs differ, read the workflow input schema and rerun with the exact active run inputs.

- [ ] **Step 2: Dry-run representative `.orc` examples**

Run:

```bash
python -m orchestrator run workflows/examples/review_revise_design_docs.orc --dry-run
python -m orchestrator run workflows/examples/review_revise_parametric_design_docs.orc --dry-run
```

Expected: dry-runs succeed or fail only for known required-input omissions, not compiler crashes.

## Task 9: Commit Integration

**Files:**
- All resolved merge files.

- [ ] **Step 1: Check staged diff**

Run:

```bash
git diff --check
git status --short
```

Expected: no conflict markers; dirty files are exactly intended integration files.

- [ ] **Step 2: Commit merge**

Run:

```bash
git add <resolved-files>
git commit
```

Expected: merge commit records WCC/post-foundation integration.

Commit message guidance:

```text
Merge WCC middle-end with post-foundation composition work

- Keep WCC as the default new lowering route
- Preserve legacy/schema-1 compatibility where required
- Reconcile resume schema safety with stale repeat-until resume clearing
- Preserve post-foundation non-compiler lane work
```

## Task 9.5: Merge Integration Branch Back To Main And Push

**Files:**
- Git branch state only.

- [ ] **Step 1: Confirm all integration verification passed**

Run:

```bash
git status --short
git log --oneline --decorate -n 5
```

Expected: integration branch is clean except intentional follow-up docs if Task
10 has not run yet. Do not merge back to `main` until Tasks 6-9 have passed.

- [ ] **Step 2: Merge integration branch into main**

Run:

```bash
git switch main
git merge --no-ff integrate/wcc-post-foundation
```

Expected: `main` now contains the WCC/post-foundation integration merge.

- [ ] **Step 3: Push main**

Run:

```bash
git push origin main
```

Expected: remote `main` contains the integrated WCC route. Task 13 must operate
from `main`, not from the temporary integration branch.

## Task 10: Update Design Docs To A Resumption-Ready State

**Files:**
- Modify: `docs/index.md`
- Modify: `docs/design/workflow_lisp_core_calculus_middle_end.md`
- Modify: `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
- Modify: `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- Optionally modify: `docs/capability_status_matrix.md`
- Optionally modify: `docs/design/README.md`

- [ ] **Step 1: Update WCC design status**

In `docs/design/workflow_lisp_core_calculus_middle_end.md`, update status language
from draft/future-direction to accepted/implemented-with-evidence once the merge
and WCC evidence matrix pass.

Do not claim full primary workflow promotion.

- [ ] **Step 2: Update post-foundation prerequisite boundary**

In `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`, add a short prerequisite note near the top:

```markdown
Compiler substrate update:

The Workflow Core Calculus / WCC middle-end is the accepted implementation
substrate for this document's nested structured-control, union-normalization,
loop, and imported/std `.orc` composition work. New post-foundation compiler
work must target the WCC route. Legacy/schema-1 lowerers may remain only for
compatibility or explicit retirement evidence.
```

Expected: the post-foundation doc no longer reads as if it may define a second
composition-normalized graph separate from WCC.

- [ ] **Step 3: Update post-foundation design inventory**

In `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`, update current-state rows:

```markdown
| Nested structured control | Implemented through WCC route for new compiles | Legacy helper-hoisting retained only as schema-1 compatibility until retired |
| Union result normalization | Implemented on WCC by explicit inject/case separation; legacy route covered or compatibility-labeled | Remaining work is parity/evidence on parent-callable families |
| Review/revise-loop composition | Implemented through WCC M4 fixtures | Remaining work is parent-drain parity and non-compiler lanes |
```

- [ ] **Step 4: Rewrite post-foundation tranche dependencies**

In `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`,
revise tranche language so implementation can resume without ambiguity:

- Tranche 1 nested structured-control composition consumes WCC M3/M4/M5.
- Tranche 2 union-result normalization consumes WCC `inject`/`case` behavior.
- Tranche 4 imported/std `.orc` reuse consumes WCC M4 review-loop evidence.
- Remaining post-WCC work starts at private context, typed projection,
  certified adapters, resource transitions, parent-callability, and parity.

Remove or relabel any language that asks future workers to build bespoke
helper-hoisting, branch-scope graph, or review-loop compiler paths outside WCC.

- [ ] **Step 5: Add explicit "resume implementation from here" section**

Add a section to `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`:

```markdown
## Resume Point After WCC Integration

Post-foundation implementation should resume from the remaining non-WCC lanes:

- private executable context bridge;
- typed projection and selector/bundle materialization;
- certified adapter declarations;
- resource-transition ownership;
- parent-callable work-item and drain composition;
- migration parity/readiness labels; and
- legacy/schema-1 lowerer retirement only when backed by dual-compile evidence.

Do not add new nested structured-control features to the legacy route.
```

- [ ] **Step 6: Update work instructions gate**

Replace the temporary freeze with a post-integration selector rule:

```markdown
After WCC integration, select compiler/lowering work only when it targets the
WCC route or explicit legacy/schema-1 retirement. Do not add new nested-control
features to the legacy route except for compatibility regressions.
```

- [ ] **Step 7: Verify docs references**

Run:

```bash
rg -n "WCC|wcc-middle-end|legacy helper|schema-1|schema-2|Resume Point|post-foundation" \
  docs/design/workflow_lisp_core_calculus_middle_end.md \
  docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md \
  docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md \
  docs/index.md
```

Expected: updated status and selector policy are visible.

- [ ] **Step 8: Commit docs**

Run:

```bash
git add docs/design/workflow_lisp_core_calculus_middle_end.md \
  docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md \
  docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md \
  docs/index.md \
  docs/capability_status_matrix.md \
  docs/design/README.md
git commit -m "Align post-foundation plan with WCC implementation"
git push origin main
```

If optional docs were not changed, omit them from `git add`.

## Task 11: Reconcile Associated Gap Designs For Post-WCC Resumption

**Files:**
- Create/modify under: `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/`

- [ ] **Step 1: Inventory all active post-foundation gap designs**

Run:

```bash
find docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps -maxdepth 2 \
  -name 'implementation_architecture.md' -o -name 'execution_plan.md' | sort
```

Expected: complete list of gap architecture/plan docs that may guide resumed
implementation.

- [ ] **Step 2: Classify each gap**

Create or update an index file:

```text
docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/post_wcc_reconciliation_index.md
```

Use this table:

```markdown
| Gap | Status after WCC | Required action before drain may select it |
| --- | --- | --- |
| workflow-lisp-nested-structured-control-composition | superseded_by_wcc | retire or rewrite as legacy-retirement evidence |
| workflow-lisp-returned-variant-union-normalization | implemented_by_wcc_or_legacy_compat | verify tests; no new legacy work |
| ... | remaining_post_wcc | update dependency statement |
```

Allowed statuses:

- `superseded_by_wcc`
- `implemented_by_wcc`
- `legacy_compatibility_only`
- `remaining_post_wcc`
- `blocked_until_rewritten`

- [ ] **Step 3: Retire or rewrite solved WCC gaps**

Run:

```bash
rg -n "nested structured control|helper hoisting|review-revise-loop|variant normalization" \
  docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps
```

Expected: identify any stale gaps that should be retired, relabeled, or rewritten as WCC-retirement verification.

For each stale gap:

- If WCC fully implements it, mark it `superseded_by_wcc` in the index and add
  a note to the gap architecture saying implementation must not continue from
  that plan.
- If legacy compatibility remains necessary, rewrite the gap as a
  legacy/schema-1 retirement or compatibility-verification gap.
- If a gap still owns work not solved by WCC, update it to consume WCC and remove
  legacy-route implementation steps.

- [ ] **Step 4: Create or update only remaining post-foundation gaps**

Allowed downstream gaps:

- private executable context bridge;
- typed projection / selector bundle materialization;
- certified adapter declaration surface;
- resource-transition ownership;
- parent-callable work-item/drain composition;
- migration parity/readiness labels;
- legacy helper-hoisting retirement with dual-compile evidence.

- [ ] **Step 5: Each selectable gap must include WCC dependency statement**

Every new/updated gap should state:

```markdown
Compiler substrate: WCC is the default route for new compiles. This gap must
not add new nested-control behavior to the legacy/schema-1 lowerers except for
explicit compatibility tests.
```

- [ ] **Step 6: Add selector safety rule for stale gaps**

Update `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md` so the
selector must not select any gap marked `superseded_by_wcc` or
`blocked_until_rewritten` in the reconciliation index.

Add:

```markdown
Post-WCC gap-selection rule:

- Read `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/post_wcc_reconciliation_index.md`
  before selecting a gap.
- Do not select gaps marked `superseded_by_wcc` or `blocked_until_rewritten`.
- Prefer `remaining_post_wcc` gaps that do not touch compiler/lowering internals
  unless the gap is explicitly a WCC or legacy-retirement verification item.
```

- [ ] **Step 7: Commit gap updates**

Run:

```bash
git add docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps \
  docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md
git commit -m "Repoint post-foundation gaps to WCC substrate"
```

Expected: gap docs only.

## Task 12: Prove Post-Execution Design Consistency

**Files:**
- Read: `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
- Read: `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- Read: `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/post_wcc_reconciliation_index.md`
- Read/modify: stale gap docs if the checks fail.

- [ ] **Step 1: Check for prohibited legacy-route guidance**

Run:

```bash
rg -n "helper hoisting|bespoke nested|legacy nested|direct surface-to-step|compiler-special review" \
  docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md \
  docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps \
  docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md
```

Expected: matches are either absent or explicitly labeled
`legacy_compatibility_only`, `superseded_by_wcc`, or `retirement evidence`.

- [ ] **Step 2: Check all remaining selectable gaps mention WCC**

Run:

```bash
python - <<'PY'
from pathlib import Path
root = Path("docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps")
missing = []
for path in root.glob("*/implementation_architecture.md"):
    text = path.read_text(encoding="utf-8")
    if "remaining_post_wcc" in text or "Compiler substrate:" in text:
        continue
    if "superseded_by_wcc" in text or "blocked_until_rewritten" in text:
        continue
    missing.append(str(path))
if missing:
    raise SystemExit("Missing WCC status/dependency statement:\n" + "\n".join(missing))
print("all selectable gap designs declare WCC status or dependency")
PY
```

Expected: script prints success.

- [ ] **Step 3: Check work instructions and index agree**

Run:

```bash
rg -n "post_wcc_reconciliation_index|superseded_by_wcc|blocked_until_rewritten|remaining_post_wcc" \
  docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md \
  docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/post_wcc_reconciliation_index.md
```

Expected: work instructions point to the index; index contains statuses.

- [ ] **Step 4: Commit any consistency fixes**

If Steps 1-3 required additional doc edits:

```bash
git add docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md \
  docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md \
  docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps
git commit -m "Make post-foundation gaps resumable after WCC integration"
```

Expected: docs-only commit, or no commit if there were no additional changes.

## Task 13: Resume Or Relaunch Post-Foundation Drain On Main

**Files:**
- Runtime state/artifacts only.

- [ ] **Step 0: Confirm main contains reconciliation**

Run:

```bash
git switch main
git status --short
git branch --contains feat/wcc-middle-end | rg "main"
rg -n "Resume Point After WCC Integration|post_wcc_reconciliation_index" \
  docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md \
  docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md
```

Expected: current branch is `main`; `main` contains the WCC branch; design and
work instructions are reconciliation-aware.

- [ ] **Step 1: Inspect current active run**

Run:

```bash
python -m orchestrator report --run-id 20260609T213343Z-rsrr6i
```

Expected: know whether the old pre-integration run is still running, completed, or stale.

- [ ] **Step 2: Decide whether resume is semantically valid**

Resume the existing run only if all are true:

- workflow checksum/schema rules permit resume;
- the current selected gap is not marked `superseded_by_wcc` or
  `blocked_until_rewritten`;
- the current selected gap has been updated to consume WCC, or it is an
  orthogonal `remaining_post_wcc` gap;
- the run is not in the middle of a compiler/lowering implementation step based
  on stale legacy-route instructions.

If any condition fails, launch a new run after archiving the old run outcome.

- [ ] **Step 3: Prefer resume if valid**

If the run failed downstream but passed prior gates and the workflow/checksum can resume safely:

```bash
python -m orchestrator resume 20260609T213343Z-rsrr6i --stream-output
```

Expected: resumed run uses integrated code and does not crash on checksum/schema mismatch.

- [ ] **Step 4: Otherwise launch a new post-integration run**

If resume is invalid because the code/schema boundary changed too much, launch a new run from the integrated branch with explicit input paths.

Use tmux and include `--stream-output`.

- [ ] **Step 5: Monitor first selector decision**

Verify the selector does not pick a legacy-lowering nested-control gap unless it is explicitly a legacy retirement gap.

Run:

```bash
python -m orchestrator report --run-id <run_id>
```

Expected: current target is a WCC-compatible downstream gap or an orthogonal lane.

- [ ] **Step 6: Verify resume-ready outcome**

Run:

```bash
python -m orchestrator report --run-id <run_id>
```

Expected:

- run is `running` or `completed`, not failed;
- target design is still
  `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`;
- selected gap is `remaining_post_wcc` or explicit WCC/legacy-retirement
  verification;
- no selected gap asks for new legacy nested-control implementation.

## Final Verification Checklist

- [ ] `git diff --check` passes.
- [ ] WCC M1-M5 tests pass.
- [ ] WCC characterization tests pass.
- [ ] Resume schema/stale-repeat-until tests pass.
- [ ] Post-foundation design-delta feasibility tests pass.
- [ ] Active drain work instructions mention WCC as the accepted compiler route.
- [ ] Post-foundation design consumes WCC instead of defining a parallel structured-control graph.
- [ ] Post-foundation design contains an explicit resume point for remaining work after WCC integration.
- [ ] Every active/selectable gap design is classified in `post_wcc_reconciliation_index.md`.
- [ ] Stale gaps are marked `superseded_by_wcc`, `legacy_compatibility_only`, or `blocked_until_rewritten`.
- [ ] Work instructions prevent selector from choosing stale or blocked-until-rewritten gaps.
- [ ] No new compiler/lowering gaps target legacy helper-hoisting except explicit compatibility/retirement work.
- [ ] Runtime/docs do not claim YAML-primary promotion from WCC implementation alone.
- [ ] Post-execution state is sufficient to resume implementation of `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md` without further design reconciliation.
- [ ] `main` contains the WCC integration and has been pushed after verification.
- [ ] The parent-callable implementation-phase fixture compiles/smokes under the WCC/default schema, or a WCC gap is recorded and implementation is not resumed.
