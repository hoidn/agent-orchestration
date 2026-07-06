# Post-Foundation Composition And Stdlib Migration — Target Completion Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or
> superpowers:executing-plans for the direct-execution tasks. Tasks marked **[drain lane]** are
> executed by the orchestrator drain workflow, not by hand — the executing agent's job there is to
> author/verify gap records, launch and monitor the run (use the `launching-workflows` and
> `managing-workflows` skills), and verify evidence afterwards.

**Goal:** Bring `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md` (the
active target) to completion: all Section 29 success criteria hold, including strict machine-computed
`non_regressive=true` for the Design Delta family (SC21), a passed `--require-promotable` gate for any
YAML-primary replacement (SC22), and Tranche 9 post-promotion simplification done or explicitly waived.

**Architecture:** Tranches 0–8 are recorded complete in the reconciliation index
(`docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/post_wcc_reconciliation_index.md`: zero
`remaining_post_wcc` rows; single `deferred_promotion_gate`). The remaining work funnels through the
acceptance vehicle `docs/design/workflow_lisp_runtime_native_drain_authoring.md` (Design Delta
reference family, drained by the `LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R*` runs, currently R41)
plus the open rows of the owner-lane prerequisite ledger
(`docs/design/workflow_lisp_shared_owner_lane_prerequisites.md`), then closes with the promotion gate
and Tranche 9 simplification.

**Tech Stack:** Python orchestrator (`python -m orchestrator`), Workflow Lisp compiler
(`orchestrator/workflow_lisp/`), pytest, drain workflow
`workflows/examples/lisp_frontend_design_delta_drain.yaml`, migration-parity CLI.

## Global Constraints

Copied from the target design (Sections 19A, 25, 22) and repo rules — every task inherits these:

- **Evidence discipline:** fresh command output is required verification evidence; inspection alone is
  insufficient. Route identity must be recorded per evidence role (`LoweringRoute` + schema version);
  route-mismatched or unpinned evidence is stale (UAF-01/02).
- **Prohibited evidence (Section 25.2, selected):** hand-authored `non_regressive`; leaf compile
  success as promotable evidence; pointer/report/stdout as semantic state; documented restriction +
  diagnostic presented as variant-identity completion; provider steps required physically inline when
  ownership is a generated call boundary.
- **Ledger adoption-claim rule:** never re-implement owner-lane behavior in family-local
  adapters/wrappers/widened boundaries/compat rereads; on hitting a missing prerequisite, stop the
  slice and select the prerequisite gap (drain-authoring doc S16 stop-or-revise triggers).
- **Tranche 9 gate:** do not collapse `parity_constrained` shapes before `--require-promotable`
  passes and the YAML primary is retired — early collapse destroys the parity comparison units.
- **Foundation regression guard (Section 3):** if any of the nine foundation contracts regress
  (structured outputs, private value transport, StateLayout ownership, strict parity gating, …), stop
  promotion work until fixed and evidence refreshed.
- **Repo rules:** no worktrees; commit by explicit path (in-flight migration work is usually in the
  tree); prefer `orchestrator resume <run_id>` over fresh runs after a passed gate; run everything
  from repo root; narrowest pytest selectors first; no commit-message assistant attribution.
- **Status routing:** live status lives in the reconciliation index, run-state files
  (`state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R*/drain/run_state.json`), the route-readiness
  registry (`docs/workflow_lisp_route_readiness_registry.json`), and parity reports — never in the
  design docs themselves.

---

## Phase 0 — Stabilize the baseline

### Task 1: Settle the in-flight working tree and the R41 drain run

**Files:**
- Inspect: `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R41/drain/run_state.json`
- Inspect: 59 modified files (`git status --porcelain`), concentrated in
  `orchestrator/workflow_lisp/` and `workflows/library/lisp_frontend_design_delta/`
- Reference: `docs/plans/2026-07-02-runtime-native-drain-compiler-private-context-stdlib-composition-report.md` (untracked diagnostic)

**Interfaces:**
- Produces: a clean-or-accounted working tree and a known R41 disposition (live / crashed / complete)
  that every later task builds on.

- [ ] **Step 1: Determine whether R41 is live.** Check tmux sessions (`tmux ls`; sessions `38` and
  `orchestration` exist) and the run state history. If the drain process is live, do not disturb it —
  switch to the `managing-workflows` skill and let the current iteration finish before any commits.
- [ ] **Step 2: Classify the dirty tree.** `git diff --stat` and map each file to its gap
  (`workflow-lisp-design-delta-compatibility-carrier-retirement`,
  `workflow-lisp-runtime-native-drain-parent-callable-stdlib-backlog-drain-compile-smoke-regression`,
  the two completed phasectx/owner-boundary gaps, or drain-mechanics changes). Anything not mapped to
  a gap or plan is flagged to the user before proceeding.
- [ ] **Step 3: Run the focused suites for the dirty modules:**

```bash
pytest tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_resource_stdlib.py \
  tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_stdlib_form_migration.py -q
pytest tests/test_workflow_lisp_lexical_checkpoints.py tests/test_workflow_lisp_resume_plumbing_retirement.py \
  tests/test_workflow_lisp_parent_drain_census_alignment.py tests/test_workflow_lisp_phase_family_boundary.py -q 2>/dev/null \
  || pytest tests/ -q -k "lexical_checkpoint or resume_plumbing or parent_drain_census or phase_family"
```

  Expected: all pass. On failure: `superpowers:systematic-debugging`; do not commit failing work.
- [ ] **Step 4: Commit completed, evidence-backed gap work by explicit path** (only slices whose gap
  records show completion); leave genuinely in-progress files uncommitted and note them in the plan
  checklist.

### Task 2: Fresh full-band evidence baseline

**Files:**
- Test: the G6 counted suites (from `docs/workflow_lisp_g6_verification_gate.json`) plus feasibility,
  parity, resume, and verification-gate suites.

**Interfaces:**
- Produces: a dated baseline (append to this plan file, `## Evidence Log`) that later parity claims
  reference.

- [ ] **Step 1: Run the counted and gate suites:**

```bash
pytest tests/test_workflow_lisp_generic_stdlib_composition.py tests/test_workflow_lisp_procedures.py \
  tests/test_workflow_lisp_modules.py tests/test_workflow_lisp_phase_stdlib.py \
  tests/test_workflow_lisp_macros.py tests/test_workflow_lisp_drain_stdlib.py \
  tests/test_workflow_lisp_resource_stdlib.py tests/test_workflow_lisp_stdlib_form_migration.py -q
pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py \
  tests/test_workflow_lisp_migration_parity.py tests/test_workflow_lisp_verification_gate.py \
  tests/test_resume_command.py -q
```

  Expected: all pass (2026-06-10 reconciliation bands: 164/27/47/437).
- [ ] **Step 2: Record pass counts + git SHA in `## Evidence Log`** at the bottom of this file.
- [ ] **Step 3: Commit the log update.**

---

## Phase 1 — Close prerequisite and owner-lane gaps **[drain lane]**

The drain workflow executes these; gap plans live under
`docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R21/design-gaps/<gap-id>/` (architecture +
execution plan authored by the workflow's design-gap architect). Launch/monitor pattern for every
drain task in this phase:

```bash
# inside tmux (tmux skill); from repo root
python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml --dry-run  # preflight
python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml <recorded R41 inputs>
# crash recovery: python -m orchestrator resume <run_id>   (never relaunch past a passed gate)
```

### Task 3: Land the two named prerequisite gaps

**Gaps:**
- `std-drain-backlog-drain-gap-continue-loop-state-run-state-carrier-retirement`
- `workflow-lisp-runtime-native-drain-design-delta-parent-transition-authoring-stale-allowed-origins`

These block the two re-blocked R40 gaps (recovery status `PREREQUISITE_WORK_PENDING`).

- [ ] **Step 1:** Verify both gaps appear `available` in the current iteration's selector manifest
  (`state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R41/drain/iterations/*/selector-manifest.json`);
  if the selector cannot see them, fix the gap records under
  `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R21/design-gaps/` first.
- [ ] **Step 2:** Run/monitor the drain until both gaps reach `completed_design_gaps` in
  `run_state.json` with committed evidence (tests + gap progress report).
- [ ] **Step 3:** Verify each completion honestly: the loop-state carrier retirement must remove the
  run-state carrier (not thread or reclassify it — ledger P-3.4 prohibits carrier progress-claims);
  the stale-allowed-origins fix must update transition authoring guards
  (`orchestrator/workflow_lisp/transition_authoring.py`) with a negative fixture.

### Task 4: Resolve the shared-compiler blockers from the 2026-07-02 diagnostic

**Files:**
- Reference: `docs/plans/2026-07-02-runtime-native-drain-compiler-private-context-stdlib-composition-report.md`
- Modify (expected): `orchestrator/workflow_lisp/lowering/procedures.py`, `wcc/elaborate.py`,
  `wcc/defunctionalize.py`, `type_env.py`, `typecheck_calls.py`

**Interfaces:**
- Produces: the generic capabilities the re-blocked gaps need — imported `std/phase` specialization
  keeps owner type environments; loop-state carriers are stable first-class values (no
  `workflow_return_not_exportable` / `state__completed__plan_path` projection failures); private
  context transport stays private but executable; parent→child private-input propagation works.

- [ ] **Step 1:** Convert the report's 7 outstanding tasks into gap records (or fold into Task 3's
  gaps where they are the same defect) — each with a failing fixture first, per the report's 10
  resolution criteria.
- [ ] **Step 2:** Drain them; after each, rerun the Task 2 counted suites (guard suites must stay
  green — resolution criterion in the report).
- [ ] **Step 3:** Re-run the Design Delta work-item feasibility module and record the result:

```bash
pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q
```

### Task 5: Close the open owner-lane ledger rows

**Files:**
- Authority: `docs/design/workflow_lisp_shared_owner_lane_prerequisites.md`
- Test: `tests/test_workflow_lisp_drain_stdlib.py`, `tests/test_workflow_lisp_phase_family_boundary.py` (or equivalent),
  fixtures under `tests/fixtures/workflow_lisp/`

Open/partial rows and their required minimum behavior checks:

- [ ] **P-2.4 family gap re-entry convergence (OPEN, family-owned):** real-route smoke/fixture showing
  `GAP → CONTINUE`-with-recorded-typed-progress → terminal via progress the next selector pass reads
  through inputs it already consumes; negative check that `max_iterations_exhausted` stays terminal
  absent progress; provenance of the progress state. No hidden flags, no reread reports/pointer files,
  no forced selector DONE.
- [ ] **P-3.2 generic child-phase reuse (PARTIAL):** confirm the item-context-first reuse route is
  owned by shared contracts, not fixture-/caller-specific — evidence beyond the single
  `design_delta_item_ctx_child_phase_reuse.orc` fixture (a second family-shape fixture or a
  structural test on the shared contract).
- [ ] **P-3.3 called-workflow result branching + terminal reprojection (PARTIAL):** one fixture with
  the full 5-part shape (match child union; branch-local second-union helper; nested imported
  `finalize-selected-item` under proved branches; no `workflow_boundary_type_invalid`; no caller-name
  validator exemptions).
- [ ] **P-3.4 carrier retirement residue:** after Task 3's carrier gap lands, confirm
  `materialize_lisp_frontend_work_item_inputs` liveness. The parity report already records it
  `unreferenced` with an expiry condition; capability-matrix row 40 still calls it a live bridge —
  reconcile: either retire the adapter row or fix the matrix.
- [ ] **P-3.5 work-item summary ownership (OPEN/PARTIAL):** fixture proving imported
  `finalize-selected-item` returns a typed `SelectedItemResult` without body-owned summary
  materialization as a precondition; negative interior-publication check; repair any stale smokes
  expecting interior `item_summary.json`.
- [ ] **Final step:** update the ledger's evidence pointers for each closed row and commit.

### Task 6: Land the two re-blocked family gaps

**Gaps:**
- `workflow-lisp-design-delta-compatibility-carrier-retirement`
- `workflow-lisp-runtime-native-drain-parent-callable-stdlib-backlog-drain-compile-smoke-regression`

- [ ] **Step 1:** With Tasks 3–5 landed, drain both to completion (they were completed R32–R39 and
  re-blocked only on those prerequisites).
- [ ] **Step 2:** Verify the compile-smoke gap's evidence is the recorded parent-callable
  compile + dry-run/smoke with public inputs (feeds Task 9), and the drain run ends
  `drain_status: DONE` (not BLOCKED) in `artifacts/work/<run>/drain-summary.json`.

---

## Phase 2 — Complete the Design Delta reference-family acceptance

Authority: `docs/design/workflow_lisp_runtime_native_drain_authoring.md` S12–S15.

### Task 7: Consumed-artifact prompt modes (`content` / `reference` / `none`)

**Files:**
- Modify (expected): prompt-rendering lane in `orchestrator/workflow_lisp/` (consumer rendering /
  observability modules); `workflows/library/lisp_frontend_design_delta/*.orc` provider request records
- Test: new focused module or extension of the consumer-rendering census tests

No matrix row or test evidence exists for the `reference`/`none` modes (S6.2, S15); Track C1 covered
typed values as prompt inputs only.

- [ ] **Step 1:** Write failing fixtures: one provider request record per mode, asserting rendered
  prompt content includes the value (`content`), includes only a typed reference (`reference`), or
  omits it (`none`), with provenance retained in all three.
- [ ] **Step 2:** Implement, rerun, commit. Add a capability-matrix row for prompt modes.

### Task 8: Retirement pass (S12.1) — compat adapters, compiler hooks, resume-only plumbing

**Files:**
- Modify: `orchestrator/workflow_lisp/resume_plumbing_retirement.py` (Track R5, currently in-flight),
  `orchestrator/workflow_lisp/compatibility_bridges.py`, core compiler modules carrying
  Design-Delta-specific augmentation hooks (locate via
  `grep -rn "design_delta\|lisp_frontend_design_delta" orchestrator/workflow_lisp/ --include="*.py" | grep -v test`)
- Inputs: `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.compatibility_bridges.json`

**Interfaces:**
- Consumes: Track R5 (resume-plumbing retirement) and Track C3/C4/C5 (entry publication,
  compatibility-bridge metadata, rendering cleanup) from
  `docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md`.
- Produces: the S12.1 end state — every remaining bridge removed or isolated with owner + consumer +
  schema + retirement condition; no hand-authored compat paths; `PhaseCtx`/`ItemCtx`/`DrainCtx` as
  library records over generic `RunCtx`/resource/StateLayout; promoted route branches on no literals
  (`std/drain`, `backlog-drain`, `finalize-selected-item`, `phase_drain`).

- [ ] **Step 1:** Land Track R5 to completion (module + tests are dirty in the tree): census-driven
  retirement candidates, compatibility-decision manifest, fail-closed without checkpoint evidence.
  Run `pytest tests/test_workflow_lisp_resume_plumbing_retirement.py -q` → pass.
- [ ] **Step 2:** Retire the `*-compat` adapter procedures for selected-item / plan / implementation /
  finalization (S7.6): each retirement needs the dual-run report plus compiled `unreferenced`
  liveness (the G2 evidence rule from matrix row 40) — not just deletion.
- [ ] **Step 3:** Remove Design-Delta-specific compile-result augmentation hooks from core compiler
  modules; add an architectural denylist test that fails if a promoted-route compiler branch keys on
  the four literals above.
- [ ] **Step 4:** Rerun the counted suites + feasibility module; update the compatibility-bridges
  input JSON and boundary-authority JSON; commit.

### Task 9: Recorded parent-callable acceptance run (S14)

- [ ] **Step 1: Compile the entrypoint on the promoted route:**

```bash
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc \
  --entry-workflow lisp_frontend_design_delta/drain::drain
```

  Expected: compile + shared validation pass; boundary inspection shows only authored public inputs
  (no `RunCtx`/write-root/checkpoint-path/state-root inputs).
- [ ] **Step 2:** Execute the S14 dry-run and smoke with recorded public inputs; verify the S13.2
  runtime checks (typed request prompts with provenance; structured-bundle-only provider output;
  boundary publication from typed terminals; transition version/idempotency/write-set/audit
  validation; resume without public checkpoint inputs).
- [ ] **Step 3:** Walk S13.4's 17-item completion list against fresh evidence; record each item's
  evidence pointer in the gap/plan record. Any unmet item routes back to Phase 1/2 tasks — do not
  mark partial items complete.

---

## Phase 3 — Parity and promotion gates (SC21/SC22)

### Task 10: Review-revise machine-computed parity (Tranche 4 residue)

**Files:**
- Reference: `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md` Stages 13–17
- Inputs: `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`

- [ ] **Step 1:** Produce the missing promotion-side fixtures: caller-side terminal projection proofs;
  APPROVE / REVISE→APPROVE / BLOCKED / EXHAUSTED / resume / source-map / evidence-authority cases on
  the promoted `std/phase` route (legacy `ReviewReviseLoopExpr` bridge fixtures stay marked legacy).
- [ ] **Step 2:** Compute parity for the review-revise route through the CLI (next task's command with
  `--target` filter) rather than hand-authoring any `non_regressive` value.

### Task 11: Strict family non-regression gate (SC21)

- [ ] **Step 1: Compute parity:**

```bash
python -m orchestrator migration-parity \
  --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json \
  --output-root artifacts/work/review-parity-check \
  --target design_delta_parent_drain --require-non-regressive
```

  Expected: exit 0 with machine-computed `non_regressive=true` and complete, route-pinned
  parent-callable evidence. On failure, the report names the stale/missing evidence role — route the
  fix to the owning phase above and re-run (evidence must be recomputed, never edited).
- [ ] **Step 2:** Update the route-readiness registry entry for
  `workflows.library.lisp_frontend_design_delta.drain` (from `parent_callable_candidate` toward
  `family_non_regressive` / `promotion_eligible` as evidence supports) and commit.

### Task 12: Promotion gate and YAML-primary retirement decision (SC22) — **user gate**

- [ ] **Step 1:** Run the promotion gate:

```bash
python -m orchestrator migration-parity \
  --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json \
  --output-root artifacts/work/review-parity-check \
  --target design_delta_parent_drain --require-promotable
```

- [ ] **Step 2:** **Stop and present to the user**: promotable-parity results, the accepted-differences
  ledger, and the YAML-primary retirement proposal
  (`workflows/examples/lisp_frontend_design_delta_drain.yaml` demoted to compatibility/reference).
  Retiring the primary surface is an intentional product decision — the reconciliation index
  explicitly deferred it; do not proceed on gate success alone.
- [ ] **Step 3 (post-approval):** retire the YAML primary (registry + matrix + `workflows/README.md`
  routing updates), keeping it as labeled compatibility evidence per Section 26.

---

## Phase 4 — Tranche 9 post-promotion simplification

### Task 13: Collapse `parity_constrained` shapes

**Selectable only after Task 12 completes (gate passed + YAML primary retired).**

**Files:**
- Inputs: Tranche 0/7 boundary-justification records;
  `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.boundary_authority.json`;
  parity report `accepted_differences` (`parity-constrained-boundaries`)
- Modify: `workflows/library/lisp_frontend_design_delta/*.orc`

- [ ] **Step 1:** Enumerate every `parity_constrained` boundary, artifact, and compat bridge binding
  from the justification records into a checklist committed to this plan.
- [ ] **Step 2:** Per item: collapse parity-only workflow boundaries into typed procedures
  (compile-time specialization), replace parity-only artifacts with scoped values, remove
  consumer-less bridge bindings. Each collapse ships with compile + shared-validation + dry-run/smoke
  evidence and a recorded resume-identity disposition (new runs only, under the recorded lowering
  schema — never in-flight runs).
- [ ] **Step 3:** Rerun the family behavioral fixtures (outcomes unchanged, shapes simplified);
  update migration records, examples, and route-readiness labels.
- [ ] **Step 4:** Acceptance: no family shape carries `parity_constrained` without either a remaining
  justifying requirement or an open simplification work item; anything waived is recorded with owner
  and rationale.

---

## Phase 5 — Status hygiene and completion recording

### Task 14: Reconcile docs, registries, and record completion

**Files:**
- Modify: `docs/workflow_lisp_route_readiness_registry.json`, `docs/capability_status_matrix.md`,
  `docs/design/README.md`, `docs/index.md`, `docs/lisp_workflow_drafting_guide.md`,
  `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/post_wcc_reconciliation_index.md`

- [ ] **Step 1:** Fix the three `stale_needs_update` registry surfaces (`wcc_m3_branch_local_ref_leak`,
  `wcc_m3_nested_join_inside_arm`, `workflows.examples.review_revise_parametric_design_docs`) and
  re-label the 14 `migration_candidate` routes that Phase 3/4 actually moved.
- [ ] **Step 2:** Fix doc-status drift: README row for
  `workflow_lisp_private_runtime_state_and_consumer_value_flow.md` still says "Draft future target"
  while both tracks have substantial landed evidence; `workflow_lisp_review_revise_stdlib_parametric_integration.md`
  README label ("Designed/partial") vs its own header ("implemented companion design"). Per the
  `incoherence`/`consistency-quality-pass` discipline, the doc/README/matrix must agree.
- [ ] **Step 3:** Land the 10A.7 propagation (explicitly noted in the design as not yet landed):
  family-idiom guidance into `docs/lisp_workflow_drafting_guide.md` and the review criteria, so
  Section 10A stops being enforced only at acceptance review.
- [ ] **Step 4:** Update the reconciliation index: promotion-gate row from `deferred_promotion_gate`
  to completed (post Task 12), and record family migration complete against the target per Tranche 9
  acceptance. Walk Section 29's 22 success criteria one final time with evidence pointers; append the
  walk to `## Evidence Log`.
- [ ] **Step 5:** Move the target design's `docs/design/README.md` row from "Active target" to
  incorporated/completed status per the repo's convention for landed targets, and commit.

---

## Risks / open assumptions

1. **R41 may still be executing** — Phase 0 defers to the live run; all sequencing after Task 1
   assumes the tree is settled first.
2. **The reconciliation index declares the promotion gate non-blocking for target DONE**, while the
   design's own SC21/SC22 + Tranche 9 make promotion part of completion. This plan follows the design
   (ground-truth precedence: design > planning ledger). If the user intends "completion" to exclude
   YAML-primary promotion, Phases 3.12–5 shrink to Task 11 + hygiene — surfaced at the Task 12 user gate.
3. **Matrix row 40 vs parity report disagree on `materialize_lisp_frontend_work_item_inputs`
   liveness** (live bridge vs `unreferenced`) — resolved explicitly in Task 5/P-3.4 rather than assumed.
4. **Two prerequisite gap records may not exist yet as selectable gaps** (they appeared only as
   blocked-recovery references in R40) — Task 3 Step 1 verifies selector visibility before draining.

## Evidence Log

*(append dated entries: git SHA, suite pass counts, parity report paths)*

- **2026-07-06 (Task 2 baseline)** — HEAD `fceb8f8`, 52 dirty files (in-progress gap work).
  Counted stdlib band 395P/2F; feasibility 73P/20F; migration-parity 100P/0F; verification-gate
  20P/0F; resume 50P/6F; build-artifacts 174P/8F. Pre-existing on clean HEAD:
  `stdlib_form_migration` intrinsic-accounting failure, `expressions.py` collection error.
  Remaining failures are dirty-tree cascade from the open `interior_publication`
  census blocker (`c0.std_drain_materialized_shared_drain_result_summary`) and in-progress
  reference-family evidence inputs; resume-band failures (6) need triage during the phasectx gap.
