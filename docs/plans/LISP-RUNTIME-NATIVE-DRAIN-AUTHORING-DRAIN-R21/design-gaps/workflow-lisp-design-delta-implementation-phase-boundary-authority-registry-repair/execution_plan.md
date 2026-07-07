# Design Delta Implementation-Phase Boundary Authority Registry Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to execute this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees.

**Goal:** Convert the already-landed `implementation_phase` boundary-authority registry rebaseline from uncommitted working-tree drift into committed, gate-green evidence so the parent-drain compile route and focused feasibility selector no longer stop on `[workflow_boundary_authority_unclassified]` for a stale `implementation_phase` registry row.

**Architecture:** The causal failure is checked-registry drift, not a compiler/runtime defect: the fail-closed gate is correct, the compiled `implementation_phase` boundary evidence changed to new generated write-root identifiers, and the checked `design_delta_parent_drain.boundary_authority.json` row at HEAD still named the superseded review-revise-loop hashes. The source-of-truth repair is already present in the working tree, so the execution order is verify the landed rebaseline first, reconcile only if a boundary-authority lane is still red, then commit only the owned reconciliation under explicit scope control. What this makes harder later: future `implementation_phase` route changes must rebaseline the checked registry, and any focused guard that encodes those rows, at the same time instead of relying on tolerated stale entries.

**Tech Stack:** checked boundary-authority registry, shared compile/build validation, focused `pytest`, `python -m orchestrator compile`, `git`, `rg`

---

## Governing Inputs

Execute strictly against these authorities:

- `docs/index.md`
- `docs/design/README.md`
- `docs/capability_status_matrix.md`
- `docs/steering.md`
- `docs/work_definition_model.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R21/design-gaps/workflow-lisp-design-delta-implementation-phase-boundary-authority-registry-repair/implementation_architecture.md`
- `state/workflow_lisp/calls/20260706T130130Z-wy6yz2/root.drain_lisp_frontend_work_2.lisp_frontend_drain_iteration.route_selection.desig_c85ba94c9989/lisp-frontend-design-delta-design-gap-architect-v214/de14bca20ef59f36.json/work_item_context.md`

Target-design clauses that bind this slice:

- `docs/design/workflow_lisp_runtime_native_drain_authoring.md:718` Section 12.1 requires stale compatibility-era or superseded checked rows to be retired or rebaselined rather than preserved through bookkeeping drift.
- `docs/design/workflow_lisp_runtime_native_drain_authoring.md:824` Section 13.4 requires fixing the real promoted route and using the narrowest runnable checks that exercise that route.
- `docs/design/workflow_command_adapter_contract.md` governs checked-manifest discipline: rows may change only when compiled evidence proves the old row is stale, and the gate must remain fail-closed.

## Current Causal State

1. The blocked dependent slice was not failing on a drain-carrier regression. Its first failure was `[workflow_boundary_authority_unclassified] stale boundary authority registry row does not match compiled evidence` against `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.boundary_authority.json`.
2. The stale row belonged to `lisp_frontend_design_delta/implementation_phase::implementation-phase` and still named the superseded review-revise-loop generated hashes `proc_5588d9f88e40_6df541978dae_1` and `proc_f3ae8cb36a98_ad08cd0f8aa8_1`.
3. Fresh architecture/work-item evidence says the working tree already rebaselined those rows to the current compiled shapes `proc_96de13fa5abd_4dd411f3a486_1` and `proc_b1ad4a920aa2_54115ccd3ac8_1`, and the focused guard selectors plus the feasibility selector are already green on this checkout.
4. Therefore the expected happy path is verify-first, then commit the checked-registry reconciliation. Source edits beyond that are only for a still-red boundary-authority lane proved by fresh command output.

## Scope Guards

- Do not weaken, bypass, or downgrade the `workflow_boundary_authority_unclassified` gate or the stale-row rejection contract.
- Do not edit `orchestrator/workflow_lisp/build.py`, `orchestrator/workflow_lisp/phase_family_boundary.py`, or any `.orc` file unless fresh verification proves a generic defect that contradicts the architecture's root-cause classification. That outcome is unlikely and should be surfaced before expanding scope.
- Do not edit sibling checked manifests such as `value_flow_census.json`, `consumer_rendering_census.json`, `transition_authoring.json`, `resume_plumbing_retirement.json`, or parity inputs.
- Do not hand-edit anything under `artifacts/work/`.
- Do not commit whole dirty files from sibling work. Explicit path staging only.
- If focused boundary-authority hunks in `tests/test_workflow_lisp_build_artifacts.py` are entangled with sibling-lane hunks and cannot be isolated into a tested commit, stop and report `semantic_conflict` rather than committing foreign work.

## File Map

Owned:

- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.boundary_authority.json`
- `tests/test_workflow_lisp_build_artifacts.py` only if one of the three boundary-authority guard selectors proves that a checked expectation still encodes the superseded `implementation_phase` row shape

Read-only for this slice:

- `orchestrator/workflow_lisp/build.py`
- `orchestrator/workflow_lisp/phase_family_boundary.py`
- `workflows/library/lisp_frontend_design_delta/drain.orc`
- `workflows/library/lisp_frontend_design_delta/implementation_phase.orc`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json`

## Task 1: Prove The Rebaseline That Is Already In The Working Tree

- [ ] **Step 1: Run the focused boundary-authority guard trio**

```bash
pytest tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_boundary_authority_registry_covers_expected_rows \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_emits_boundary_authority_report_for_all_target_workflows \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_rejects_stale_boundary_authority_registry_row_mismatch \
  -q
```

Expected: `3 passed`. This proves the checked registry covers current compiled rows, the report includes `implementation_phase`, and a genuinely stale row still fails closed.

- [ ] **Step 2: Run the blocker's feasibility selector**

```bash
pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "selected_item_stdlib or parent_drain_build_and_execution_smoke" -q
```

Expected: the selector must not fail with `workflow_boundary_authority_unclassified`. A later sibling-owned checked-input failure is acceptable for this slice; record it verbatim if it appears.

- [ ] **Step 3: Re-run the real parent-drain compile gate**

```bash
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc \
  --entry-workflow lisp_frontend_design_delta/drain::drain \
  --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json \
  --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
```

Expected: the first failure must not be `[workflow_boundary_authority_unclassified]` on an `implementation_phase` row. Full success is acceptable; a later sibling-owned gate failure is also acceptable for this slice.

- [ ] **Step 4: Prove the exact stale-to-live hash swap in the owned registry**

```bash
rg -n "proc_5588d9f88e40_6df541978dae_1|proc_f3ae8cb36a98_ad08cd0f8aa8_1|proc_96de13fa5abd_4dd411f3a486_1|proc_b1ad4a920aa2_54115ccd3ac8_1" \
  workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.boundary_authority.json
git diff -- workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.boundary_authority.json
```

Expected:

- the superseded hashes are absent from the working-tree file;
- the current compiled hashes are present; and
- the dirty diff is boundary-authority row reconciliation rather than unrelated policy churn.

- [ ] **Step 5: Route on evidence**

If Steps 1-4 match expectations, skip Task 2 and continue to Task 3. If any boundary-authority lane is red, continue to Task 2. If the first failure is a different gate class, stop and record that causal failure instead of widening this slice.

## Task 2: Reconcile Only If Task 1 Proved A Boundary-Authority Lane Red

- [ ] **Step 1: Derive the compiled expected rows from the failing lane**

Use the boundary-authority report and expected-row projection from the failing guard or compile diagnostics to enumerate the current `(workflow_name, field_name, surface_kind)` rows for the parent-drain route, including `lisp_frontend_design_delta/implementation_phase::implementation-phase`.

- [ ] **Step 2: Rebaseline the checked registry and nothing else**

Edit `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.boundary_authority.json` so it contains only rows proven by compiled evidence:

- delete or update rows whose keys no longer exist in the compiled projection, including the stale `implementation_phase` review-revise-loop write-root rows named above;
- add rows only for genuinely live but currently unclassified compiled evidence; and
- keep classifications honest instead of relabeling stale rows to dodge the gate.

- [ ] **Step 3: Touch the focused guard file only if a named selector proves it necessary**

Update `tests/test_workflow_lisp_build_artifacts.py` only when one of the three Task 1 selectors still encodes the superseded row shape. Keep the changes limited to boundary-authority expectations for the reconciled registry. Do not absorb the unrelated dirty hunks already present in that file.

- [ ] **Step 4: Re-run the full Task 1 ladder**

Do not proceed until Task 1 is green under the repaired registry.

## Task 3: Commit Only The Owned Reconciliation

- [ ] **Step 1: Inspect scope before staging**

```bash
git status --short workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.boundary_authority.json tests/test_workflow_lisp_build_artifacts.py
git diff -- workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.boundary_authority.json
git diff -- tests/test_workflow_lisp_build_artifacts.py
```

Expected: the registry diff is entirely boundary-authority reconciliation. The test file may still be dirty from sibling work; only stage it if Task 2 proved a focused boundary-authority expectation change is required and separable.

- [ ] **Step 2: Stage only owned paths**

Happy-path command when the registry is the only file required:

```bash
git add workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.boundary_authority.json
```

If a focused `tests/test_workflow_lisp_build_artifacts.py` edit is required, stage only the separable owned hunk set with a non-interactive minimal patch workflow; if the hunk boundary is not cleanly isolatable, stop and report `semantic_conflict`.

- [ ] **Step 3: Verify the index before committing**

```bash
git diff --cached --name-only
git diff --cached --check
git diff --cached --stat
```

Expected:

- the cached set contains only the registry file, or the registry plus a minimal focused test hunk set;
- no whitespace or patch-format issues; and
- the staged diff is traceable to this reconciliation only.

- [ ] **Step 4: Commit with hooks enabled**

```bash
git commit -m "fix: reconcile design delta boundary authority registry"
```

Constraint: never use `--no-verify`. If commit hooks fail on this slice's staged content, fix the staged content or report the blocking failure.

## Task 4: Re-Prove Acceptance On The Post-Commit Tree

- [ ] **Step 1: Re-run the full acceptance ladder after the commit**

```bash
pytest tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_boundary_authority_registry_covers_expected_rows \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_emits_boundary_authority_report_for_all_target_workflows \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_rejects_stale_boundary_authority_registry_row_mismatch \
  -q
pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "selected_item_stdlib or parent_drain_build_and_execution_smoke" -q
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc \
  --entry-workflow lisp_frontend_design_delta/drain::drain \
  --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json \
  --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
```

Expected: same boundary-authority outcomes as Task 1, now on the committed tree.

- [ ] **Step 2: Confirm post-commit hygiene**

```bash
git status --short workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.boundary_authority.json tests/test_workflow_lisp_build_artifacts.py
git show --stat --oneline HEAD
```

Expected:

- the registry path is clean in the working tree;
- `tests/test_workflow_lisp_build_artifacts.py` is clean if it was part of this slice, or still dirty only with sibling-owned hunks that were intentionally left out; and
- `HEAD` contains only this slice's reconciliation commit.

## Completion Criteria

- Fresh post-commit command output satisfies every acceptance condition from the implementation architecture.
- The parent-drain direct compile's first failure, if any, is not the boundary-authority gate and not an `implementation_phase` stale-row complaint.
- The committed `design_delta_parent_drain.boundary_authority.json` no longer contains rows keyed to `proc_5588d9f88e40_6df541978dae_1` or `proc_f3ae8cb36a98_ad08cd0f8aa8_1`.
- The fail-closed contract remains intact: a genuinely stale row still fails, and no gate logic was weakened or bypassed.
- Every staged and committed hunk is traceable to the boundary-authority reconciliation owned by this gap.
