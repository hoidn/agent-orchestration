# Drain Migration → G8 Retirement → Certification-Bundle Retirement → Parity-Lane Strip (Gated Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Phases 2–4 are hard-gated: do not dispatch any task in a phase until that phase's Gate (see Gate Ledger) is verified with fresh command output recorded in this file.**

**Goal:** Land Tranche 2 of `docs/design/workflow_lisp_parametric_type_system.md` — "Target: author the drain loop as a generic `defproc` in `std/drain.orc` and retire the intrinsic" — then, in strict evidence-gated order: delete the intrinsic drain lowering lane (Tranche G8 of `docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`), retire the design-delta certification compile bundle, and strip the design-delta lanes from `migration_parity.py` while preserving the permanent parity kernel.

**Architecture:** Phase 1 is the migration (design prerequisites 3–5): generic `backlog-drain-proc` body, macro re-target behind the frozen caller surface, checkpoint-identity gate, consumer parity. Phase 2 is prerequisite 6 + G8: a behavior-preserving resource-helper re-home followed by pure deletion of paths Phase 1 proved redundant. Phase 3 retires the fail-closed certification bundle that Phase 2 stops needing, honoring an explicit preserve-list. Phase 4 strips the design-delta constants/lanes from the parity machinery, leaving the permanent kernel (targets/report/index/gate evaluation + `migration-parity` CLI) intact for `cycle_guard_demo` and `design_plan_impl_stack`.

**Tech Stack:** Python 3.13, Workflow Lisp `.orc` frontend (`orchestrator/workflow_lisp/`), WCC/ANF middle-end, pytest.

**Drafted:** 2026-07-07 against commit `169711aa`. The parametric feasibility gates (capability plan Tasks 2, 3, 7, 9 — see `docs/plans/2026-07-06-parametric-type-system-capability-plan.md`) are complete and green at drafting time; the then-current drain-region files (`lowering/phase_drain.py`, `lowering/drain_terminal.py`, `typecheck_calls.py`, `wcc/defunctionalize.py`) were committed and clean. This sentence is a historical snapshot, not a current owner map.

## Relationship to prior plans

- `docs/plans/2026-07-06-backlog-drain-generic-migration-plan.md` is the detailed Phase-B draft for the migration. **This plan supersedes its sequencing**: its Tasks 1–6 and 8 are incorporated as Phase 1 below (with amendments noted per task); its Task 7 (intrinsic retirement) is re-gated as Phase 2 here. Its Anchor Map, Known Feasibility Gaps G1–G5, and body skeletons remain authoritative *inputs* — execute body-authoring detail from there, gates and sequencing from here. On conflict between the two plans, this plan governs.
- `docs/plans/2026-07-07-refactoring-dead-code-and-lowering-consolidation.md` (Tranche 0/1; may execute before or concurrently) freezes exactly the surfaces this plan later deletes. Its freezes are consistent with this plan's phase gates: nothing it touches inside `lowering/phase_drain.py`'s `_phase_stdlib_lower_backlog_drain_impl` family, `lowering/drain_terminal.py`, the Design Delta gates owned by `build_design_delta.py` and orchestrated from `build.py`, or `migration_parity.py`. Re-verify symbols at each task start — that plan and the now-tracked `2026-07-07-lowering-fork-migration.md` may have shifted ownership.
- This plan is roadmap item 5 of the refactoring plan's follow-on list.

### Execution re-anchor (2026-07-09)

The 2026-07-07 line-number anchors below are drafting history only where they are explicitly labeled as such. Execute against this current-owner map and re-locate by symbol name:

| Concern | Current owner and live symbols |
| --- | --- |
| Design Delta certification data and loading | `orchestrator/workflow_lisp/build_design_delta.py`: `DesignDeltaEvidence`, `load_design_delta_family_catalog`, `load_design_delta_evidence`, and the `_maybe_load_design_delta_*` loader family |
| Design Delta report/G8 serialization | `orchestrator/workflow_lisp/build_design_delta.py`: `DesignDeltaReportPayloads`, `serialize_design_delta_reports`, `_serialize_design_delta_g8_deletion_evidence`, and `DESIGN_DELTA_G8_*` constants |
| Build artifact persistence | `orchestrator/workflow_lisp/build_artifacts.py`: `_add_design_delta_artifacts` owns the Design Delta artifact export map and `_write_build_artifacts` owns payload writes; generic manifest/artifact writers remain preserved |
| Public build pipeline and stage call sites | `orchestrator/workflow_lisp/build.py`: `build_frontend_bundle`, `_select_and_reattach`, and `_emit`; this module also retains `_reference_family_versioned_roots` / `_resolve_reference_family_evidence_paths` and compatibility re-exports, but does not own the moved Design Delta serializer bodies |
| Drain expression typecheck owner | `orchestrator/workflow_lisp/typecheck_drain_phase.py`: `typecheck_backlog_drain_expr` |
| Shared typecheck helpers and dispatch | `orchestrator/workflow_lisp/typecheck_calls.py`: `workflow_ref_signature`, `validate_selector_workflow_ref`, `validate_run_item_workflow_ref`, `validate_gap_drafter_workflow_ref`, `_backlog_drain_blocker_class_type`; `orchestrator/workflow_lisp/typecheck_dispatch.py`: the `BacklogDrainExpr` dispatch branch into `typecheck_backlog_drain_expr` |
| Intrinsic drain lowering | `orchestrator/workflow_lisp/lowering/phase_drain.py`: `_callable_backlog_drain_*`, `_ensure_callable_backlog_drain_workflow`, `_phase_stdlib_lower_backlog_drain_impl`, `_validate_backlog_drain_provider_metadata`, and specialization helpers; `orchestrator/workflow_lisp/lowering/drain_terminal.py`: `lower_shared_drain_terminal_result` and intrinsic-only helpers |
| Surviving selected-item summary helper | `orchestrator/workflow_lisp/lowering/phase_drain.py` currently defines `_selected_item_summary_pointer_path`, but live search finds its sole non-definition consumer in `lowering/phase_resource.py`. Phase 2 must move the unchanged helper into `phase_resource.py` before any `phase_drain.py` region/module deletion; it is resource-lane behavior, not deletable drain residue |
| Lowering entry/dispatch sites | `orchestrator/workflow_lisp/lowering/control_dispatch.py` and `lowering/core.py`: `BacklogDrainExpr` dispatch/imports; `lowering/phase_helpers.py`: compatibility re-export of `_lower_backlog_drain`; `lowering/phase_stdlib.py`: `_phase_drain_lower` import and `_lower_backlog_drain` facade wrapper. Remove only the drain wiring and preserve every surviving phase/resource/flow export and wrapper |
| Migration parity | `orchestrator/workflow_lisp/migration_parity.py`: `DESIGN_DELTA_G8_*`, `_validated_design_delta_g8_deleted_rows`, and the G8-specific fold in `_resource_transition_parity_evidence` are family-specific deletion candidates; `ParityTarget`, `load_parity_targets`, report/index/gate schema machinery, `run_migration_parity`, and `_runtime_audit_transition_parity_evidence` are the preserved generic kernel |

## Global Constraints

- Run all commands from the repo root `/home/ollie/Documents/agent-orchestration`.
- The working tree contains the user's in-flight work. **Stage by explicit path only** (`git add <file> <file>`). Never `git add -A`, `git add -u`, or `git commit -a`.
- Commit messages: short imperative sentence, matching repo style (e.g. `Route selector and gap drafting to stronger models`). **No** conventional-commit prefixes, **no** mention of Claude/Claude Code, **no** Co-Authored-By trailers.
- No worktrees. Never use `--no-verify`.
- Narrowest pytest selectors first; treat fresh command output as the verification evidence. After changing any test module, run `pytest --collect-only <module>` on it.
- Do not touch `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R*` directories — they are compile-evidence inputs for the certification lane.
- Frozen surfaces (do not modify): the inline intrinsic expansion owned by `orchestrator/workflow_lisp/lowering/phase_drain.py`'s `_phase_stdlib_lower_backlog_drain_impl` family, `orchestrator/workflow_lisp/lowering/drain_terminal.py`, everything gated on the `lisp_frontend_design_delta/drain::drain` entry in `build_design_delta.py` plus its orchestration call sites in `build.py`, and `migration_parity.py`.
- If a step's verification fails twice in a row, stop and report instead of forcing it green.

### Phase-scoped amendments to the frozen-surface rules

The verbatim constraints above hold **unconditionally through Phase 1**. They lift per phase, and only for deletion/retirement — never for in-place edits of intrinsic behavior:

- `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R*` state dirs stay untouchable through **all four phases**. They are live compile-evidence inputs while the certification lane exists (read by `_reference_family_versioned_roots` in `build.py` and consumed by Design Delta report serialization); after Phase 3 they are historical run state whose cleanup is out of this plan's scope.
- `phase_drain.py`'s `_phase_stdlib_lower_backlog_drain_impl` family (the inline intrinsic expansion) and `drain_terminal.py` are frozen **through the end of Phase 1**. No pre-migration edits to the inline expansion: any change there perturbs generated step/checkpoint identity and poisons the Phase-1 identity-comparison baseline. The freeze lifts at the Phase-2 gate for **wholesale deletion only**.
- The `build_design_delta.py` surfaces gated on the `lisp_frontend_design_delta/drain::drain` entry, their artifact-map entries in `build_artifacts.py`, and their orchestration call sites in `build.py` are frozen through Phases 1–2 (they are the parity/G8 evidence machinery those phases depend on), with one narrow Phase-2 Task-2.2 exception: update only `DESIGN_DELTA_G8_IMPORTED_ONLY_REGISTRY_HEADS` (or another owning `DESIGN_DELTA_G8_*` classification constant only if Task 2.2's decision procedure proves it is required) to keep G8 classification aligned with the chosen form-registry disposition. Serializer algorithms, evidence validation, gate behavior, loaders/report serialization, artifact mapping, orchestration call sites, and every other Design Delta build behavior remain frozen through Phase 2. The general freeze lifts at the Phase-3 gate for retirement.
- `migration_parity.py` is frozen through Phases 1–3, with one narrow Phase-2 Task-2.2 exception: update only `DESIGN_DELTA_G8_IMPORTED_ONLY_REGISTRY_HEADS` (or another owning `DESIGN_DELTA_G8_*` classification constant only if Task 2.2's decision procedure proves it is required) to keep G8 classification aligned with the chosen form-registry disposition. Parity algorithms, target loading/handling, evidence validation, report/gate generation, and every other `migration_parity.py` behavior remain frozen through Phase 3. The general freeze lifts at the Phase-4 gate, bounded by the permanent-kernel line drawn in Task 4.1.
- Additional standing rule for every phase: hook shape contracts are owned by `docs/design/workflow_lisp_runtime_native_drain_authoring.md` (+ `workflow_lisp_shared_owner_lane_prerequisites.md`); on conflict with the flagship signature, "the signature adapts, not the shapes" (parametric design, Relationship To Other Docs). Raise conflicts, do not improvise.

## Gate Ledger

Record fresh command output under each gate before dispatching the phase. A gate is **not** satisfied by inspection or by this plan's drafting-time snapshot.

**Gate P1 (entry to Phase 1):**
1. Feasibility gates green: `pytest tests/test_workflow_lisp_checkpoint_identity_comparison.py tests/test_workflow_lisp_generic_stdlib_composition.py -q` → PASS. The design's drafting precondition — "may be drafted only when Tasks 2, 3, 7, and 9 … are complete and green" (capability plan, Scope and Phase-2 Gate) — is met.
2. Drain-region files clean: `git status --porcelain orchestrator/workflow_lisp/ | grep -E "phase_drain|drain_terminal|typecheck_drain_phase|typecheck_calls|defunctionalize"` → empty.

**Gate P2 (entry to Phase 2 — the redundancy proof; design prerequisites 3–5 green):**
1. Phase 1 Tasks 1.1–1.7 committed.
2. **Identity (prereq 4):** `pytest tests/test_workflow_lisp_checkpoint_identity_comparison.py -v` → PASS with the generic route active, against the recorded **intrinsic-route** baselines; the Phase-1 ledger entry in this file states either "identical" or cites the reviewed identity-migration commit. Design: checkpoint ids "unchanged across the intrinsic-to-generic route swap, or an explicit reviewed identity-migration step remaps persisted records".
3. **Parity (prereq 5):** `pytest tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_lisp_frontend_autonomous_drain_runtime.py -q` → at Task-1.1 recorded baselines (contract deltas documented in the Task 1.6 census).
4. **Certification lane green on the generic route:** the production compile command (Task 1.6 Step 4) exits 0 and the freshest `g8_deletion_evidence.json` reports `"status": "pass"`.
5. **Parity report:** `python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/review-parity-check --target design_delta_parent_drain --require-non-regressive` → exit 0; `artifacts/work/review-parity-check/design_delta_parent_drain.json` has `"non_regressive": true`.
6. **Intrinsic reachability shrunk to fixtures:** `grep -rln "backlog-drain-callable-boundary" workflows/` → empty (no production caller reaches the intrinsic; only `tests/fixtures/` hits remain, and they retire with Phase 2).

**Gate P3 (entry to Phase 3):**
1. Phase 2 Tasks 2.1–2.3 committed; name-blindness check (Task 2.3 Step 2) clean.
2. Certification lane still green **after** the deletion: production compile exits 0; freshest `g8_deletion_evidence.json` still `"status": "pass"` (now via the `spec is None` / imported-only branches of `_serialize_design_delta_g8_deletion_evidence` in `build_design_delta.py` — Task 2.2 decides which).
3. Final parity regeneration (same command as P2.5) → exit 0, `"non_regressive": true`; `promotion_eligibility` recorded in the Phase-2 ledger entry. This is the "G7 + promotion evidence -> G8" sequencing obligation discharged and recorded.
4. Promotion handoff completed and recorded (steering, user, 2026-07-07; governing sequence Stage 3): YAML-retirement Task 5 family 1 has run only through registration, fresh non-regressive parity, the `.orc` primary flip, and fresh end-to-end evidence. The `.orc` entry `lisp_frontend_design_delta/drain::drain` is the primary production route; Task 5's archive bullet has **not** run, and the YAML twin remains for Stage 6.

**Gate P4 (entry to Phase 4):**
1. Phase 3 Tasks 3.1–3.4 committed.
2. `design_delta_parent_drain` absent from `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`; parity index regenerated without it.
3. Production compile of the `.orc` entry green **without** the family-gated certification block (Task 3.4 Step 1 output recorded).
4. `python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/review-parity-check --require-non-regressive` → exit 0 over the remaining targets (`cycle_guard_demo`, `design_plan_impl_stack`).

---

## Phase 1 — Tranche 2 drain migration (design prerequisites 3–5)

Normative signature (parametric design, Tranche 2 — copy verbatim when authoring; body elided there and authored here):

```lisp
(defproc backlog-drain-proc
  :forall (CtxT SelectionT SelPayloadT GapPayloadT RunResultT GapResultT)
  ((ctx CtxT)
   (selector    ProcRef[(CtxT) -> SelectionT])
   (run-item    ProcRef[(std/context/ItemCtx SelPayloadT) -> RunResultT])
   (gap-drafter ProcRef[(CtxT GapPayloadT) -> GapResultT])
   (max-iterations Int))
  :where (…18 clauses, design doc Tranche 2…)
  -> std/drain/DrainLoopTerminal
  ...)
```

Frozen caller surface (design, quoted): "the caller-facing compatibility contract is the macro keyword surface — `(backlog-drain <name> :ctx … :selector … :run-item … :gap-drafter … :max-iterations …)` — which is **frozen** across the migration: existing call sites remain byte-stable."

### Task 1.1: Re-baseline and anchor verification

**Files:** Modify this plan (append `## Phase 1 Ledger` with the re-baseline record).
**Entry condition:** Gate P1 recorded above.

- [x] **Step 1:** Execute the 2026-07-06 plan's Task 1 Steps 1–3 verbatim (precondition check, Anchor Map re-verification greps, fresh suite counts for `test_workflow_lisp_drain_stdlib.py`, `test_workflow_lisp_design_delta_drain_migration_feasibility.py` [93 tests at drafting], `test_workflow_lisp_procedures.py`, `test_workflow_lisp_generic_stdlib_composition.py`, `test_workflow_lisp_build_artifacts.py`, `test_lisp_frontend_autonomous_drain_runtime.py`), recording results in **this** file's Phase 1 Ledger instead of the old plan.
- [x] **Step 2:** Additionally capture the pre-swap certification/parity baseline:
```bash
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
python -c "import json,glob,os; p=max(glob.glob('.orchestrate/build/*/g8_deletion_evidence.json'), key=os.path.getmtime); print(p, json.load(open(p))['status'])"
```
Expected: compile exits 0; artifact `status` prints `pass`.
- [x] **Step 3: Commit** — `git add docs/plans/2026-07-07-drain-migration-g8-retirement.md && git commit -m "Record drain migration re-baseline"`

### Task 1.2: Feasibility probes (hook kind, subset-match, loader-shape)

Execute the 2026-07-06 plan's **Task 2** as written (probe fixture `tests/fixtures/workflow_lisp/valid/drain_generic_hook_probe.orc`; compile through the shared-validated stage-3 entry). Its STOP outcomes stand: an effectful-proc-hook/`ProcRef` binding failure (gap G1) or a `source_map_missing` loader-shape failure (gap G5) is **BLOCKED — stop the plan and report**; an exhaustiveness failure on extra-variant unions (gap G3) is recorded as "extra-variant callers unsupported pending a design decision" and the fixture narrowed — the decision authority is the parametric design's Subset Semantics section, and the finding is raised, not resolved here.

Selectors: `pytest tests/test_workflow_lisp_generic_stdlib_composition.py -k hook_probe -v`, then the full module `-q`.
Commit: `Probe ProcRef hook feasibility for drain migration` (files per the old plan's Task 2 Step 3).

### Task 1.3: Intrinsic-route checkpoint-identity baselines (prerequisite 4, part 1)

Execute the 2026-07-06 plan's **Task 3** as written: snapshot the **intrinsic-route** `checkpoint_identity_map` for (a) `tests/fixtures/workflow_lisp/valid/drain_stdlib_backlog_drain.orc` and (b) `workflows/library/lisp_frontend_design_delta/drain.orc` into `tests/baselines/drain_checkpoint_identity/{exemplar,design_delta_drain}.json`, with freshness tests in `tests/test_workflow_lisp_checkpoint_identity_comparison.py`.

**These baselines must be committed before any edit to `std/drain.orc`'s macro or the production hook modules** — they are the pre-swap compiled-artifact evidence the design demands. Design (prereq 4, quoted): "This is the riskiest item in the migration and must not be discovered downstream of retirement."

Selectors: `pytest --collect-only tests/test_workflow_lisp_checkpoint_identity_comparison.py -q && pytest tests/test_workflow_lisp_checkpoint_identity_comparison.py -v`.
Commit: `Snapshot intrinsic-route drain checkpoint identities`.

### Task 1.4: Author `backlog-drain-proc` + `settle-drain-terminal` in `std/drain.orc` (prerequisite 3; dormant — macro untouched)

Execute the 2026-07-06 plan's **Task 4** as written, including its Step 1 (the G2 design amendment: read `_phase_stdlib_lower_backlog_drain_impl` to determine which `SelPayloadT` fields the body must project — expected `item-id`, possibly `item-state-root` — and land the one-clause `:where` delta in the design doc as its own commit, `Declare selection payload fields the drain body projects`).

Fixed decision rules (no TBDs):
- **Module:** `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc` — the design designates it by name ("author the drain loop as a generic `defproc` in `std/drain.orc`").
- **Terminal helpers:** prereq 3 (quoted): "Authored loop body in `std/drain.orc` using existing terminal helpers (`finalize-drain-terminal`, `consume-drain-terminal-effects`)" — the body composes these, it does not re-implement them.
- **`:where` block:** verbatim from the design's flagship signature plus the committed G2 clause(s). The `RunResultT` clauses match `std/resource` `SelectedItemResult`; the `GapResultT` clauses match `std/drain` `GapResult`; "the two field vocabularies differ deliberately and must not be conflated" (design, quoted).
- **Every reality-dependent constant** (the `:on-exhausted` blocker class, the selector-`BLOCKED` `reason → BlockerClass` mapping, the progress-report seed path) is read from `_phase_stdlib_lower_backlog_drain_impl` and its helpers in `lowering/phase_drain.py` and recorded in the fixture test — mirrored, never invented (old plan Task 4's "reality anchors" rule).
- **Minimal-caller fixture** `tests/fixtures/workflow_lisp/valid/minimal_caller_backlog_drain.orc`: types provide exactly the declared constraints and nothing more (design Acceptance Checks).

Selectors: `pytest tests/test_workflow_lisp_generic_stdlib_composition.py tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_build_artifacts.py -q` — dormant bar: new tests pass, nothing that consumed `std/drain` breaks.
Commit: `Author generic backlog-drain loop body in std/drain`.

### Task 1.5: Macro re-target + THE checkpoint-identity gate (prerequisite 4, part 2)

Execute the 2026-07-06 plan's **Task 5** as written: re-target `defmacro backlog-drain` in `std/drain.orc` onto `(settle-drain-terminal (backlog-drain-proc …))` with the keyword surface and argument order unchanged; convert the three production hooks (`stdlib_adapters.orc`, `work_item.orc`) per the Task-1.2-validated shape; `git diff workflows/library/lisp_frontend_design_delta/drain.orc` must be **empty** (byte-stable call site is a review gate).

- [ ] **THE GATE (explicit STOP-on-mismatch rule):** run `pytest tests/test_workflow_lisp_checkpoint_identity_comparison.py -v` — the freshness tests now compare the **generic route** against the Task-1.3 intrinsic-route baselines.
  - **Identical → record "identical" in the Phase 1 Ledger and proceed.**
  - **Any difference → BLOCKED. Do not commit the re-target.** Produce the row-level diff (which `(workflow, origin_key)` checkpoint ids changed/appeared/vanished), attach it to the ledger, and present the human the design's two sanctioned options: (a) make the generic route reproduce the intrinsic's generated-step identities; (b) "an explicit reviewed identity-migration step remaps persisted records" (design, Specialization Pipeline). **Neither is chosen unilaterally.** Resume runs of consuming workflows depend on these ids; a silent identity break is the failure mode this gate exists to catch.

Selectors: identity suite above, plus `pytest tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q` (failures here that are diagnostic-code shifts get inventoried for Task 1.6, not chased).
Commit (only if the gate passed): `Re-target backlog-drain macro onto the generic proc`.

### Task 1.6: Consumer parity via the existing certification lane (prerequisite 5)

Execute the 2026-07-06 plan's **Task 6** (obligation census; relocations; diagnostic contract deltas), with these amendments:

- The census section is appended to **this** plan's Phase 1 Ledger.
- Prereq 5 rule (quoted): "census/boundary/provider-metadata obligations move to shared validation surfaces, not into the generic body." Any obligation whose only home would be inside the generic body is a design conflict — **raise it**.
- Intrinsic-shape assertions in `tests/test_workflow_lisp_drain_stdlib.py` (for example, tests resolving the generated `std/drain::backlog-drain` child workflow) are reviewed contract deltas: rewrite them to assert the generic route's lowered shape and record each delta (`old assertion → new assertion, why`) in the census. Deleting a negative fixture outright requires showing its scenario is now impossible to author, not merely differently reported.

- [ ] **Step 4 (the certification lane IS the parity gate — run it):**
```bash
pytest tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_parent_drain_census_alignment.py tests/test_lisp_frontend_autonomous_drain_runtime.py -q
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/review-parity-check --target design_delta_parent_drain --require-non-regressive
```
Expected: suites at Task-1.1 baselines; compile exits 0 with all fail-closed census gates (value-flow, consumer-rendering, resume-plumbing, transition-authoring, compatibility-bridge, boundary-authority) green on the generic route; parity exits 0 with `"non_regressive": true`. The autonomous-drain runtime suite is end-to-end consumer evidence — failures there are real parity breaks, not contract deltas.
Commit: `Move drain obligations to shared surfaces with parity evidence` (explicit file list).

### Task 1.7: Documentation sync and integration evidence

Execute the 2026-07-06 plan's **Task 8** minus any retirement claims (the intrinsic still exists — record Tranche 2 prerequisites 3–5 as landed, prerequisite 6 as gated on this plan's Phase 2): update `docs/design/workflow_lisp_parametric_type_system.md` status parentheticals, `docs/design/workflow_lisp_runtime_native_drain_authoring.md` §12 status note, `docs/capability_status_matrix.md`. Integration evidence per repo rule:
```bash
python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml --dry-run
```
(or the launch wrapper recent runs actually used — check `.orchestrate/runs/`; record which command served as evidence).
Commit: `Record backlog-drain generic migration in design docs`.

---

## Phase 2 — G8 deletion: retire the intrinsic drain lowering lane (prerequisite 6)

**Gate: P2 (all six conditions recorded).** G8 contract (retirement design §17.1): "Delete only what evidence proves is dead." Selection rule (§2): "deletion-only, must not be selected until evidence from G2 through G7 proves every removed path is unused." Phase 1 is what makes the inline intrinsic expansion unused; the codified `g8_deletion_evidence` rows were already passing before Phase 1 and are **not** sufficient on their own (see Contradictions & Findings, item 3).

Deletion set authority (parametric design prereq 6, quoted): "the phase-drain lowerer, drain-terminal helper module's intrinsic-only paths, the form-specific monomorphizer, and the name-keyed validators."

### Task 2.1: Deletion inventory and dependency-ordered deletion

**Files (2026-07-07 drafting-time historical snapshot, re-anchored by current symbol below — Step 1 re-enumerates; the grep output, not this table, is the execution inventory):**

| Cluster | Current symbol re-anchor |
| --- | --- |
| Form-specific monomorphizer | `lowering/phase_drain.py` — `_callable_backlog_drain_specialization_key`, `_ensure_callable_backlog_drain_workflow` (synthesizes `std/drain::backlog-drain` children), `_callable_backlog_drain_enabled`, `_record_compatibility_backlog_drain_hit` |
| Phase-drain lowerer | `lowering/phase_drain.py` — `_phase_stdlib_lower_backlog_drain_impl` (including its local `_require_backlog_drain_public_params`), `_validate_backlog_drain_provider_metadata`, and drain-only specialization/provider helpers. Delete the whole module only after `_selected_item_summary_pointer_path` is re-homed and Step 1 shows no other non-drain survivor |
| Drain-terminal intrinsic paths | `lowering/drain_terminal.py` — `lower_shared_drain_terminal_result` and its intrinsic-only helpers; delete the module only after current import enumeration shows no survivor |
| Surviving resource helper | Move `_selected_item_summary_pointer_path` unchanged from `lowering/phase_drain.py` into its sole consumer/owner, `lowering/phase_resource.py`, before deleting drain code; remove the cross-import only after the resource owner defines it locally |
| Drain typecheck owner | `typecheck_drain_phase.py` — delete only `typecheck_backlog_drain_expr` plus imports/helpers proven exclusive to that handler by the live caller inventory. Preserve the module and its non-drain handlers `typecheck_phase_target_expr`, `typecheck_run_provider_phase_expr`, and `typecheck_produce_one_of_expr`; preserve shared `_expected_extern_operand`. The `_require_union_variant_field`, `_require_union_variant_path_field`, `_require_union_variant_exact_type`, and `_require_union_variant_exact_field_names` helpers are currently drain-only, but delete them only after current caller enumeration confirms no surviving use. |
| Shared typecheck helper dependencies | `typecheck_calls.py` — `validate_selector_workflow_ref`, `_backlog_drain_blocker_class_type`, `validate_run_item_workflow_ref`, `validate_gap_drafter_workflow_ref`; delete `workflow_ref_signature` only if current caller enumeration proves it is drain-only |
| Typecheck dispatch | `typecheck_dispatch.py` — the `BacklogDrainExpr` import and dispatch branch into `typecheck_backlog_drain_expr` |
| Elaboration + AST | `expressions.py` — `BacklogDrainExpr`, its `ExprNode` union membership, `_elaborate_backlog_drain`, and the `"backlog_drain"` elaboration-route entry; `drain_stdlib.py` — `BacklogDrainSpec` (delete module if empty); `expression_traversal.py` — `_backlog_drain_children` and `BacklogDrainExpr` traversal; `functions.py` and `__init__.py` — `BacklogDrainExpr` naming/export fallout |
| Specialization special case | `procedure_specialization.py` — `BacklogDrainExpr`-specific specialization/rewrite branches |
| WCC dispatch | `wcc/route.py` and `wcc/elaborate.py` — `BacklogDrainExpr` route/elaboration branches; `wcc/defunctionalize.py` — the `BacklogDrainExpr` branch that calls `_phase_stdlib_lower_backlog_drain_impl` |
| Lowering dispatch/facades | `lowering/control_dispatch.py` and `lowering/core.py` — `BacklogDrainExpr` branches and `_lower_backlog_drain` wiring, including `record_intrinsic_form_lowering("backlog-drain")` accounting; `lowering/phase_helpers.py` — drain compatibility re-export; `lowering/phase_stdlib.py` — `_phase_drain_lower` import and drain facade wrapper. Preserve the non-drain facade exports/wrappers in both files |
| Import fallout | `lowering/phase_resource.py` — remove only the obsolete `BacklogDrainExpr` and `phase_drain` imports after locally owning `_selected_item_summary_pointer_path`; `lowering/phase_scope.py`, `lowering/phase_flow.py` — now-unused `BacklogDrainExpr` imports |
| Inventory strings | `stdlib_contracts.py` — the `backlog-drain` / `BacklogDrainExpr` contract row. The drafting-time `stage7_metrics.py` hit is already absent in the current checkout and is not part of the live inventory |
| Fixtures/tests | `tests/fixtures/workflow_lisp/valid/drain_stdlib_backlog_drain_callable_boundary*.orc` and direct-boundary tests: convert to the macro form if guarding distinct behavior, else delete with a one-line rationale per fixture in the commit message body |

- [ ] **Step 1: Re-enumerate by grep (this output is the inventory of record):**
```bash
grep -rn "BacklogDrain\|backlog_drain\|backlog.drain" orchestrator/workflow_lisp/ --include="*.py" | grep -v stdlib_modules
grep -rln "backlog-drain-callable-boundary" orchestrator/ tests/ workflows/
grep -rn "drain_terminal\|phase_drain" orchestrator/ --include="*.py" | grep -v "test"
rg -n "_selected_item_summary_pointer_path|from \.phase_drain import|_phase_drain_lower|_lower_backlog_drain" orchestrator/workflow_lisp/lowering orchestrator/workflow_lisp/wcc
```
Record the diff against the table above in the Phase 2 Ledger. Any hit in `workflows/library/` outside fixtures → STOP (Gate P2.6 was not actually satisfied).
- [ ] **Step 2: Preserve the non-intrinsic resource helper first.** Move `_selected_item_summary_pointer_path` byte-for-byte into `lowering/phase_resource.py`, its only live non-definition consumer, then remove that module's import from `phase_drain.py`. Run `rg -n "_selected_item_summary_pointer_path" orchestrator/workflow_lisp/lowering` and record one definition plus the resource-lane call, with no surviving cross-import; run `pytest tests/test_workflow_lisp_resource_stdlib.py -q` before any drain deletion. This is an ownership move with unchanged path semantics, not part of the deletion count.
- [ ] **Step 3: Delete in dependency order** — drain dispatch/re-export sites (WCC route/elaborate/defunctionalize, `control_dispatch.py`, `core.py`, the drain compatibility re-export in `phase_helpers.py`, and only the drain import/wrapper in `phase_stdlib.py`) → only the `BacklogDrainExpr` import and dispatch branch in `typecheck_dispatch.py` → only `typecheck_backlog_drain_expr` and its proven-exclusive imports/helpers in `typecheck_drain_phase.py` → elaboration + route entry → AST node + spec dataclass → drain-only helpers in `typecheck_calls.py` (preserving any shared helper with a surviving caller) → lowering impl + monomorphizer → `drain_terminal.py` → import fallout. Do not delete `typecheck_drain_phase.py`: preserve `typecheck_phase_target_expr`, `typecheck_run_provider_phase_expr`, `typecheck_produce_one_of_expr`, `_expected_extern_operand`, and every import/helper they still consume. Re-run a symbol/caller inventory after removing the backlog-drain handler before deleting any `_require_union_variant_*` helper. Preserve all non-drain functions and exports in `phase_helpers.py`, `phase_stdlib.py`, and `phase_resource.py`. Verify between clusters with `python -c "import orchestrator.workflow_lisp" && pytest tests/ -q --collect-only > /dev/null && echo OK`; before deleting the `phase_drain.py` module, rerun the Step-1 import search and require zero surviving consumers. Multiple incremental commits, each staging its explicit file list, each compiling.
- [ ] **Step 4: Add the permanent CI guard** (retirement design §17.2: "Add CI guards against reintroducing name-keyed context recognition"): a small structure-lock test (in `tests/test_workflow_lisp_stdlib_form_migration.py` or a sibling) asserting `grep`-level absence of `BacklogDrainExpr`/`backlog_drain` branches under `orchestrator/workflow_lisp/` outside the sanctioned residue (form-registry record, stdlib-contract rows, `std/drain.orc` itself). This test outlives Phase 4's deletion of the `DESIGN_DELTA_G8_GREP_GUARDS` constants.
- [ ] **Step 5: Commit** (final commit of the sequence): `git commit -m "Retire the backlog-drain intrinsic lowering paths"`

### Task 2.2: Registry reclassification + G8 evidence decision procedure

**Files:** `orchestrator/workflow_lisp/form_registry.py`; possibly `orchestrator/workflow_lisp/build_design_delta.py` + `orchestrator/workflow_lisp/migration_parity.py` (one owning constant each — see the decision procedure; `build.py` only compatibility-re-exports the moved build symbol); `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc` (export list, if the boundary form's export is removed).

Background: `build_design_delta.py`'s removed-heads check (`_serialize_design_delta_g8_deletion_evidence`) passes a head in `DESIGN_DELTA_G8_REMOVED_REGISTRY_HEADS` = `("with-phase", "finalize-selected-item", "backlog-drain")` only when its spec is deleted (`get_form_spec(...) is None`), OR tagged `compatibility_route_only`, OR listed in `DESIGN_DELTA_G8_IMPORTED_ONLY_REGISTRY_HEADS` with `macro_bindable=True` (the `with-phase` precedent). `migration_parity._validated_design_delta_g8_deleted_rows` cross-checks the same constants. `with-phase` and `finalize-selected-item` are **out of scope** — they keep their current tags/handling.

- [ ] **Step 1: Delete the `backlog-drain-callable-boundary` spec from `form_registry.py` outright.** It is not in the removed-heads constant, so no evidence-machinery interaction; its `std/drain.orc` export and macro-alias plumbing go with it (reviewed contract delta per the old plan's Task 7 Step 1).
- [ ] **Step 2: Decide `backlog-drain`'s registry disposition by this rule:**
  - **Default (residue-precedent route):** reclassify the spec to mirror the current `review-revise-loop` `FormKind.STDLIB_EXTENSION` record: `kind=FormKind.STDLIB_EXTENSION`, `elaboration_route=None`, `macro_bindable=True`, drop the `compatibility_route_only` tag and the `remove_by` obligation. The parametric design sanctions exactly this residue ("registry entry, stdlib contract, output-contract shaping"). This route **requires** adding `"backlog-drain"` to `DESIGN_DELTA_G8_IMPORTED_ONLY_REGISTRY_HEADS` in both owning modules, `build_design_delta.py` and `migration_parity.py` — the `with-phase` "imported-only + macro-bindable" branch is the honest classification for a head that now reaches the compiler only via imported stdlib expansion.
  - **Alternative (full-deletion route):** delete the spec entirely — the check passes via `spec is None` with zero machinery changes — **only if** Step 3 proves nothing requires a registry record for a macro-bindable stdlib name (`review-revise-loop`'s existence, and the `_validate_form_specs` invariant pinning it, suggest the record is load-bearing for stdlib surfaces; verify, don't assume).
  - Record which route was taken and why in the Phase 2 Ledger. See Contradictions & Findings item 1 — this decision point is a known documentation/machinery conflict; flag it in the execution report either way.
- [ ] **Step 3: Verify the evidence check under the chosen route:**
```bash
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
python -c "import json,glob,os; p=max(glob.glob('.orchestrate/build/*/g8_deletion_evidence.json'), key=os.path.getmtime); d=json.load(open(p)); print(d['status'], d['hook_surface_delta']['imported_only_registry_heads'])"
```
Expected: exit 0, `pass`. A `design_delta_g8_removed_registry_head_present` compile error means the disposition and the constants disagree — fix the classification, never weaken the check.
- [ ] **Step 4: Commit:** `git add orchestrator/workflow_lisp/form_registry.py orchestrator/workflow_lisp/stdlib_modules/std/drain.orc <constants files if touched> && git commit -m "Reclassify backlog-drain registry head after intrinsic retirement"`

### Task 2.3: Phase-2 verification, residue audit, and final promotion evidence

- [ ] **Step 1: Full suites:**
```bash
pytest tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_generic_stdlib_composition.py tests/test_workflow_lisp_build_artifacts.py tests/test_lisp_frontend_autonomous_drain_runtime.py -q
pytest tests/test_workflow_lisp_checkpoint_identity_comparison.py -v
```
Expected: at Phase-1 baselines; identity tests still pass (retirement must not perturb the generic route's identities).
- [ ] **Step 2: Name-blindness check:** `grep -rn "backlog.drain\|backlog_drain\|BacklogDrain" orchestrator/workflow_lisp/ | grep -v stdlib_modules | grep -v README` → expected: the Task-2.2 registry record and stdlib-contract inventory rows only. Anything else is unfinished retirement.
- [ ] **Step 3: Residue audit** (design: "Residue materially above that is a signal to stop and reassess against the per-form migration test rather than push through"): compare surviving lines against the review-loop precedent (registry entry, stdlib contract, output-contract shaping); record counts + the `line_count_delta`/`hook_surface_delta` from the fresh `g8_deletion_evidence.json` in the Phase 2 Ledger (§17.3: "Deletion evidence reports line-count and hook-surface reduction"). Materially more residue → STOP and escalate.
- [ ] **Step 4: Final parity regeneration (the Gate P3 promotion evidence):** run the P2.5 parity command; record `non_regressive` and `promotion_eligibility` in the ledger.
- [ ] **Step 5: Docs:** update `docs/capability_status_matrix.md` (backlog-drain: library-provided via `std/drain` generic; intrinsic: retired) and the two design docs' status notes (prereq 6 landed; G8 drain rows discharged). Commit: `Record intrinsic drain retirement evidence`.

### Design Delta promotion handoff (Gate P3 transition)

After Task 2.3 and before recording Gate P3 as satisfied, execute `docs/plans/2026-07-07-yaml-retirement-program.md` Task 5 for **family 1 only**, bounded by the governing procedure-first sequence Stage 3:

- Complete/register the existing Design Delta `.orc` family and run fresh parity until `design_delta_parent_drain` is non-regressive with every required evidence role passing.
- Flip the production primary to `lisp_frontend_design_delta/drain::drain`, update its launch/routing/readiness surfaces, and run fresh compile plus smoke/end-to-end evidence on the `.orc` primary.
- Record those artifacts and the promotion decision in the Gate P3 ledger. These are additional requirements; none of Gate P3's deletion, certification, parity, or primary-route checks is relaxed.
- **Stop before Task 5's archive bullet.** Keep `workflows/examples/lisp_frontend_design_delta_drain.yaml` and any still-imported YAML library twins in place. Their archive is deferred to Stage 6, not Phase 3.
- After Phase 3 removes the `design_delta_parent_drain` parity target, do not recreate that target for the later archive. The historical promotion artifact plus the preserved compile, smoke, and end-to-end evidence govern Stage 6's archive check on the then-current checkout.

---

## Phase 3 — Certification-bundle retirement

**Gate: P3 (all four conditions, including the bounded promotion handoff above, recorded).** The bundle is FAIL-CLOSED compile machinery today (`LispFrontendCompileError`/`ValueError` on census-fingerprint mismatch in `resume_plumbing_retirement.py` and the certification region owned by `build_design_delta.py`) and was load-bearing until Phase 2 landed; deletion order below is chosen so the compile never demands an input that has already been deleted.

**Preserve-list (verified importers; do not delete):**
- `consumer_rendering_census.py` **schema kernel** — `observability_summaries.py` imports `CONSUMER_RENDERING_CENSUS_SCHEMA_VERSION` and consumes census payloads. Keep whatever the live importers outside the deleted block need; decision procedure in Task 3.3 Step 3.
- `phase_family_boundary.py` **generic core** — currently imported by `compiler.py`, `workflows.py`, `build_artifacts.py`, `build_design_delta.py`, `lowering/core.py`, `wcc/defunctionalize.py`, **and the runtime** (`orchestrator/workflow/loaded_bundle.py`, `checked_design_delta_public_input_names`). Commit `d1427d6e` is already generalizing it. Keep the module; only entry points whose sole callers die with the bundle may go.
- The parity kernel and its suite (`tests/test_workflow_lisp_migration_parity.py`) — Phase 4's boundary, not Phase 3's.
- Compile-input externs for the production entry: `design_delta_parent_drain.{commands,providers,prompts}.json` stay (they are ordinary compile inputs, not certification evidence).

### Task 3.1: Re-home one parent-drain smoke into parity evidence commands (FIRST)

**Files:** Create `tests/test_workflow_lisp_design_delta_smoke.py`; modify the two Design Delta evidence-command references in `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`.

`tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py` (6,353 lines / 93 tests) supplies the parity target's smoke evidence commands; it may be retired **only after** one parent-drain smoke lives elsewhere.

- [ ] **Step 1:** Extract the minimal parent-drain smoke (the `-k "smoke"` subset's compile-the-production-entry path) into `tests/test_workflow_lisp_design_delta_smoke.py`, reusing the feasibility module's loader helpers by import or by copy (prefer import while the module still exists; inline the helper when the module is deleted in Task 3.3).
- [ ] **Step 2:** `pytest --collect-only tests/test_workflow_lisp_design_delta_smoke.py -q && pytest tests/test_workflow_lisp_design_delta_smoke.py -q` → PASS.
- [ ] **Step 3:** Point the two `parity_targets.json` evidence-command refs at the new module; run the P2.5 parity command → exit 0.
- [ ] **Step 4: Commit:** `git add tests/test_workflow_lisp_design_delta_smoke.py workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json && git commit -m "Re-home parent drain smoke outside the feasibility suite"`

### Task 3.2: Remove the `design_delta_parent_drain` parity target (promotion decision)

**Files:** `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`; regenerated `artifacts/work/review-parity-check/index.json`.

- [ ] **Step 1:** Confirm Gate P3.3/P3.4 ledger entries exist (final non-regressive report + recorded promotion decision). The last `design_delta_parent_drain.json` report stays in `artifacts/work/review-parity-check/` as the historical promotion record — do not delete it.
- [ ] **Step 2:** Remove the `design_delta_parent_drain` target object from `parity_targets.json` (leaving `cycle_guard_demo`, `design_plan_impl_stack`).
- [ ] **Step 3:** `python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/review-parity-check --require-non-regressive` → exit 0; regenerated index lists only the two remaining families.
- [ ] **Step 4:** Record that later Stage-6 YAML archival must use the retained historical promotion artifact plus fresh preserved compile/smoke/end-to-end checks; it must not recreate the retired `design_delta_parent_drain` parity target.
- [ ] **Step 5: Commit:** `git add workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json artifacts/work/review-parity-check/index.json && git commit -m "Remove promoted design delta family from parity targets"`

### Task 3.3: Ordered bundle deletion

**Files (delete, in this order):**
1. The family-gated certification unit in `build_design_delta.py`: `DesignDeltaEvidence`, the `load_design_delta_*` / `_maybe_load_design_delta_*` loaders, census/bridge/retirement/boundary-authority gating, and the Design Delta report serializers; remove their public pipeline threading/call sites from `build.py` and their retired artifact-map entries/threading from `build_artifacts.py`. Preserve generic build pipeline/artifact/manifest kernels, `_reference_family_versioned_roots` / `_resolve_reference_family_evidence_paths` in `build.py` while they have a live caller, and the G8 serializer/constants/minimal payload plumbing until Phase 4.
2. Certification modules: `consumer_rendering_census.py` (kernel preserved per Step 3), `value_flow_census.py`, `rendering_cleanup.py`, `rendering_ergonomics.py`, `compatibility_bridges.py`, `transition_authoring.py`, `resume_plumbing_retirement.py`, `parent_drain_census_alignment.py`, `reference_family_conformance.py`.
3. Their suites: `tests/test_workflow_lisp_consumer_rendering_census.py` (unless the preserved kernel keeps assertions — split, don't drop coverage), `test_workflow_lisp_value_flow_census.py`, `test_workflow_lisp_rendering_cleanup.py`, `test_workflow_lisp_rendering_ergonomics.py`, `test_workflow_lisp_compatibility_bridges.py`, `test_workflow_lisp_transition_authoring.py`, `test_workflow_lisp_resume_plumbing_retirement.py`, `test_workflow_lisp_parent_drain_census_alignment.py`, `test_workflow_lisp_reference_family_conformance.py`, `test_workflow_lisp_design_delta_bridge_adapter_compatibility.py`, and (last, after Task 3.1 landed) `test_workflow_lisp_design_delta_drain_migration_feasibility.py`.
4. Certification manifests under `workflows/examples/inputs/workflow_lisp_migrations/`: the `design_delta_parent_drain.*` files **except** `{commands,providers,prompts}.json`, plus the dual-run vector files — each deleted only after Step 3's grep shows zero surviving loaders.

- [ ] **Step 1:** Delete the family-specific region from `build_design_delta.py`, its orchestration/threading call sites in `build.py`, and its retired artifact-map entries/threading in `build_artifacts.py`; verify: production compile command (P2 form) exits 0 **without** reading any certification manifest (`strace`-free check: temporarily `mv` one manifest aside, compile, restore — expected: compile succeeds either way once the block is gone). Do not delete the generic `build_frontend_bundle` / `_emit` pipeline, generic `_write_build_artifacts` / `_build_manifest` machinery, or G8-only residue reserved for Phase 4.
- [ ] **Step 2:** Delete modules + suites by explicit `git rm`, one commit per tier, verifying between tiers: `python -c "import orchestrator.workflow_lisp" && pytest tests/ -q --collect-only > /dev/null && echo OK`.
- [ ] **Step 3 (preserve-list decision procedure):** before touching each preserve-list module: `grep -rn "<module>" orchestrator/ --include="*.py" | grep -v test` — enumerate live importers outside the deleted block. For `consumer_rendering_census.py`: keep exactly the schema kernel `observability_summaries.py` consumes (constant + payload shaping); move it into `observability_summaries.py` only if the remainder of the module is otherwise empty. For `phase_family_boundary.py`: no deletion of any symbol with a surviving importer (the runtime `loaded_bundle.py` use of `checked_design_delta_public_input_names` included).
- [ ] **Step 4:** Delete manifests (tier 4) after `grep -rln "<filename>" orchestrator/ tests/ workflows/ | grep -v parity_targets` is empty per file.
- [ ] **Step 5: Commits** (per tier): `Delete design delta certification gating in build`, `Delete certification census and retirement modules`, `Delete certification manifests and feasibility suite`.

### Task 3.4: Phase-3 verification

- [ ] **Step 1:** Production compile (P2 form) → exit 0; `pytest tests/test_workflow_lisp_design_delta_smoke.py tests/test_workflow_lisp_drain_stdlib.py tests/test_lisp_frontend_autonomous_drain_runtime.py tests/test_workflow_lisp_build_artifacts.py -q` → PASS.
- [ ] **Step 2:** `pytest tests/ -q --collect-only > /dev/null && echo COLLECT_OK` → `COLLECT_OK`; then full suite in tmux: `pytest -q` (compare against a pre-Phase-3 capture).
- [ ] **Step 3:** Record in the Phase 3 Ledger: the state dirs `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R*` are no longer compile-evidence inputs (the Design Delta consumer of `_resolve_reference_family_evidence_paths` died with the block) but remain untouchable under this plan; YAML-twin deletion (`workflows/examples/lisp_frontend_design_delta_drain.yaml`) is deferred to procedure-first Stage 6 — note the pointer, do not delete here.
- [ ] **Step 4:** Docs sync: `docs/capability_status_matrix.md` rows for the certification lane → retired; `docs/index.md`/`docs/design/README.md` routing entries for the retired lane updated. Commit: `Record certification bundle retirement`.

---

## Phase 4 — Design-delta lane strip from the parity machinery

**Gate: P4 (all four conditions recorded).**

**Permanent-kernel boundary (NOT deleted, now or later):** `ParityTarget` loading, report/report-markdown/index generation, gate evaluation (`REPORT_SCHEMA_VERSION`/`INDEX_SCHEMA_VERSION`/`GATE_EVALUATION_SCHEMA_VERSION` machinery), `run_migration_parity`, the CLI command and its registration (`orchestrator/cli/commands/migration_parity.py`, `orchestrator/cli/main.py`), and everything `cycle_guard_demo` + `design_plan_impl_stack` exercise. The parity kernel is a permanent product surface, not migration debt.

### Task 4.1: Strip design-delta constants and lanes from `migration_parity.py`

**Files:** `orchestrator/workflow_lisp/migration_parity.py`; `tests/test_workflow_lisp_migration_parity.py` (expectation updates for removed lanes only).

**Deletion inventory (drafting-time anchors; re-locate by symbol name):**
- `DESIGN_DELTA_G8_DELETION_EVIDENCE_SCHEMA_VERSION`, `DESIGN_DELTA_G8_DELETED_MANIFEST_ROWS`, `DESIGN_DELTA_G8_RESOURCE_TRANSITION_HELPERS`, `DESIGN_DELTA_G8_REMOVED_REGISTRY_HEADS`, `DESIGN_DELTA_G8_IMPORTED_ONLY_REGISTRY_HEADS` (+ the Task-2.2 addition if the residue-precedent route was taken).
- The `g8_deletion_evidence` compile-artifact load and its family-specific threading through report/evidence-role evaluation.
- `_validated_design_delta_g8_deleted_rows` and its callers.
- The Design Delta fold inside `_resource_transition_parity_evidence`: G8-evidence threading, deleted-helper rows, and the `DESIGN_DELTA_G8_RESOURCE_TRANSITION_HELPERS` loop. Preserve `_runtime_audit_transition_parity_evidence` whenever a remaining target uses that generic core.

- [ ] **Step 1 (decision procedure for the fold):** determine whether the remaining targets exercise the `resource_transition_parity` role: `python - <<'EOF'` reading `parity_targets.json` roles/config for `cycle_guard_demo` and `design_plan_impl_stack`, plus `grep -n "resource_transition_parity" orchestrator/workflow_lisp/migration_parity.py`. If the role is design-delta-only → delete `_resource_transition_parity_evidence` and its role wiring entirely. If shared → strip only the g8/deleted-helper logic, keeping the `_runtime_audit_transition_parity_evidence` core. Record which in the Phase 4 Ledger.
- [ ] **Step 2:** Delete the inventory; `pyflakes orchestrator/workflow_lisp/migration_parity.py` → no new unused/undefined names.
- [ ] **Step 3:** Update `tests/test_workflow_lisp_migration_parity.py`: remove/rewrite tests pinning the deleted lanes; keep every kernel test. `pytest --collect-only tests/test_workflow_lisp_migration_parity.py -q && pytest tests/test_workflow_lisp_migration_parity.py -q` → PASS.
- [ ] **Step 4: Commit:** `git add orchestrator/workflow_lisp/migration_parity.py tests/test_workflow_lisp_migration_parity.py && git commit -m "Strip design delta lanes from migration parity"`

### Task 4.2: Strip the G8 serializer, artifact entry, and compatibility re-exports

**Files:** `orchestrator/workflow_lisp/build_design_delta.py`; `orchestrator/workflow_lisp/build_artifacts.py`; `orchestrator/workflow_lisp/build.py` only for surviving compatibility re-exports/imports; `tests/test_workflow_lisp_build_artifacts.py` for reviewed expectation updates.

**Deletion inventory (dead code since Task 3.3 deleted the sole caller — verify):** `_serialize_design_delta_g8_deletion_evidence` and `DESIGN_DELTA_G8_REMOVED_MANIFEST_ROWS`, `DESIGN_DELTA_G8_REMOVED_SCRIPT_PATHS`, `DESIGN_DELTA_G8_REMOVED_PYTHON_SYMBOLS`, `DESIGN_DELTA_G8_REMOVED_REGISTRY_HEADS`, `DESIGN_DELTA_G8_IMPORTED_ONLY_REGISTRY_HEADS`, `DESIGN_DELTA_G8_RETAINED_BRIDGES`, `DESIGN_DELTA_G8_PRECONDITION_EVIDENCE_REFS`, `DESIGN_DELTA_G8_GREP_GUARDS`, and `DESIGN_DELTA_G8_VERIFICATION_COMMANDS` in `build_design_delta.py`; the `g8_deletion_evidence` entry in `_add_design_delta_artifacts` and any now-empty payload plumbing in `build_artifacts.py`; compatibility imports/re-exports in `build.py`; and any orphaned `DESIGN_DELTA_PARENT_DRAIN_*` path constants proven unused by current symbol search.

- [ ] **Step 1:** `rg -n "DESIGN_DELTA_G8|g8_deletion" orchestrator/workflow_lisp/build*.py` → confirm every hit is a definition, compatibility re-export/import, payload field, or artifact-map entry with no surviving serializer caller. A surviving caller means Task 3.3 was incomplete — STOP, fix there first.
- [ ] **Step 2:** Delete from the owning modules; run `pyflakes orchestrator/workflow_lisp/build.py orchestrator/workflow_lisp/build_design_delta.py orchestrator/workflow_lisp/build_artifacts.py` with no new unused/undefined names; production compile (P2 form) → exit 0 (no `g8_deletion_evidence.json` emitted — expected; the Task 2.1 Step 4 CI guard now carries the §17 reintroduction protection).
- [ ] **Step 3:** `pytest tests/test_workflow_lisp_build_artifacts.py -q` → PASS (update any test pinning the artifact's existence — reviewed delta, noted in commit message).
- [ ] **Step 4: Commit:** `git add orchestrator/workflow_lisp/build.py orchestrator/workflow_lisp/build_design_delta.py orchestrator/workflow_lisp/build_artifacts.py tests/test_workflow_lisp_build_artifacts.py && git commit -m "Delete G8 deletion evidence serializer from build"`

### Task 4.3: Final verification and closeout

- [ ] **Step 1:** `python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/review-parity-check --require-non-regressive` → exit 0 over the two remaining families.
- [ ] **Step 2:** Full suite in tmux: `pytest -q`; production compile + a dry-run/launch through the promoted `.orc` primary as the orchestrator smoke. The retained YAML twin is not the primary launch path and remains untouched for Stage 6.
- [ ] **Step 3:** Docs: capability matrix + design-doc status notes (G8 drain rows: deleted; parity lane: kernel-only). Commit: `Record parity lane strip and closeout evidence`.
- [ ] **Step 4:** Report: per-phase line-count deltas, gate evidence summary, residue-vs-precedent comparison, and every flagged contradiction's disposition. Do not push; leave commits local for review.

---

## Contradictions & Findings (flagged at drafting, 2026-07-07 — do not resolve silently)

1. **Registry residue vs. G8 removed-heads check.** The parametric design sanctions a surviving registry entry as migration residue (review-loop precedent: `FormKind.STDLIB_EXTENSION`, `macro_bindable=True`, no compatibility tag), but `_serialize_design_delta_g8_deletion_evidence` in `build_design_delta.py` fails the compile for any surviving `backlog-drain` spec lacking the `compatibility_route_only` tag and absent from `DESIGN_DELTA_G8_IMPORTED_ONLY_REGISTRY_HEADS`. The prior retirement-safety judgment's "no gate-machinery changes needed to land the deletion" holds only for the full-registry-deletion variant; the sanctioned-residue variant needs a two-constant edit (the `with-phase` imported-only precedent). Task 2.2 codifies the decision procedure; the executor must flag the chosen route.
2. **Prior-plan sequencing.** `2026-07-06-backlog-drain-generic-migration-plan.md` bundles intrinsic retirement (its Task 7) into the migration plan; this plan re-gates it behind Gate P2. This plan governs; the old plan gets no edit (single-file constraint) — the supersession is recorded here only.
3. **Codified G8 evidence under-approximates the doc's gate.** The retirement design says G8 "must not be selected until evidence from G2 through G7 proves every removed path is unused", yet every codified `g8_deletion_evidence` row already passes while the intrinsic inline expansion runs on every production schema-2 compile (child `std/drain::backlog-drain` lowered with `preserve_owner_boundary=False`, `_callable_backlog_drain_enabled` → False → inline branch; proven by `tests/test_workflow_lisp_drain_stdlib.py` WCC_M4 tests). The codified rows track manifest rows/adapters/registry heads, not the lowering lane. The real gate is Phase 1 (Tranche 2); Gate P2 encodes that. Consider (out of scope here) a doc note aligning §17's acceptance rows with the lowering-lane evidence.
4. **Minor historical correction:** `resume_plumbing_retirement.py`'s fingerprint-mismatch gate raises `ValueError`, not `LispFrontendCompileError` as earlier context stated — same fail-closed effect; recorded for provenance without retaining a mutable line anchor.
5. **Concurrent-plan drift:** `stage7_metrics.py` still existed at drafting, but the 2026-07-09 re-anchor confirms it is absent. The Task 2.1 live symbol search, not the drafting snapshot, remains the inventory of record.

---

## Phase 1 Ledger

### Task 1.1 re-baseline record (2026-07-10)

#### Gate P1 evidence (fresh output, 2026-07-10)

1. Feasibility gates:

```text
$ pytest tests/test_workflow_lisp_checkpoint_identity_comparison.py tests/test_workflow_lisp_generic_stdlib_composition.py -q
............                                                             [100%]
12 passed in 0.94s
```

2. Drain-region files clean:

```text
$ git status --porcelain orchestrator/workflow_lisp/ | grep -E "phase_drain|drain_terminal|typecheck_drain_phase|typecheck_calls|defunctionalize"
(empty — grep exit 1, no matches)
```

Gate P1 SATISFIED.

#### Component-plan Task 1 Step 1 — preconditions

```text
$ pytest tests/test_workflow_lisp_checkpoint_identity_comparison.py -q
1 passed in 0.33s

$ git status --porcelain orchestrator/workflow_lisp/ tests/ workflows/library/
 M tests/test_workflow_non_progress_step_back_demo.py
 M workflows/library/prompts/workflow_step_back/diagnose_non_progress.md
```

Both dirty files are on the user-owned expected-dirty list; neither is an Anchor Map file; `orchestrator/workflow_lisp/` is clean. Precondition HOLDS. Note: the Task-1.1 working-tree amendment said only `tests/test_workflow_non_progress_step_back_demo.py` matches the status globs; `workflows/library/prompts/workflow_step_back/diagnose_non_progress.md` also matches the `workflows/library/` glob. Both are expected user-owned files outside the drain region — recorded as a drift note, not a blocker.

#### Component-plan Task 1 Step 2 — Anchor Map re-verification (per row)

STOP checks first: `grep -rn "backlog-drain-proc" orchestrator/ tests/` → no hits (exit 1) — no authored proc body exists in `std/drain.orc`; the intrinsic lowering is present. No STOP condition triggered.

| Anchor Map row | Drafting anchor (2026-07-06) | Current location (2026-07-10) | Status |
| --- | --- | --- | --- |
| Drain macro | `std/drain.orc:280-286` | `defmacro backlog-drain` at `std/drain.orc:280` | HOLDS |
| Authored terminal half | `std/drain.orc:128-279` | `empty/blocked/completed-drain-result-proc` at :128/:135/:145, `finalize-drain-terminal` :153, `consume-drain-terminal-effects` :177; `drain-run-state` resource :99, `record-drain-outcome` transition :102 (resource/transition sit just above the drafting range) | HOLDS (resource/transition at :99/:102) |
| Form registry entries | `form_registry.py:576-599` | `"backlog-drain"` :577, `elaboration_route="backlog_drain"` :584 and :596, `"backlog-drain-callable-boundary"` :589 | HOLDS |
| Elaboration | `expressions.py:982`, `_elaborate_backlog_drain` :3128, `BacklogDrainExpr`/`BacklogDrainSpec` `drain_stdlib.py:12-23` | route entry `expressions.py:982`; `_elaborate_backlog_drain` :3128; `BacklogDrainSpec` `drain_stdlib.py:13`; `BacklogDrainExpr` defined at `expressions.py:514` | HOLDS (`BacklogDrainExpr` clarified to `expressions.py:514`) |
| Typecheck dispatch | `typecheck_dispatch.py:1788` | `isinstance(expr, BacklogDrainExpr)` at `typecheck_dispatch.py:1115` (file now 1171 lines), dispatching into `typecheck_backlog_drain_expr` (`typecheck_drain_phase.py:39`) per the 2026-07-09 re-anchor | MOVED → :1115 |
| Name-keyed validators | `typecheck_calls.py:464-697` | `validate_selector_workflow_ref` :433, `validate_run_item_workflow_ref` :510, `validate_gap_drafter_workflow_ref` :600; re-anchor symbols `workflow_ref_signature` :273, `_backlog_drain_blocker_class_type` :496 present | MOVED → :433/:510/:600 |
| Intrinsic lowering | `phase_drain.py:399-1978` + helpers to :2455 | `_phase_stdlib_lower_backlog_drain_impl` def :345; `_validate_backlog_drain_provider_metadata` :1949; `_selected_item_summary_pointer_path` :1943; module 2410 lines | MOVED → :345 (module shrank to 2410 lines) |
| Form-specific monomorphizer | `phase_drain.py:208-391` | `_callable_backlog_drain_enabled` :154, `_callable_backlog_drain_specialization_key` :198, `_ensure_callable_backlog_drain_workflow` :253 | MOVED → :154-:264 |
| Python terminal duplicate | `drain_terminal.py:173+` | `lower_shared_drain_terminal_result` :173 (module 374 lines) | HOLDS |
| Schema-1 dispatch | `control_dispatch.py:151-154, 213-214` | import `from .phase_drain import _lower_backlog_drain` :60; `isinstance(expr, BacklogDrainExpr)` branch :150-151; no second dispatch site remains near :213 (only backlog hits are :60 and :151) | MOVED (second site gone; :60 + :150-151 remain) |
| WCC dispatch | `defunctionalize.py:3100-3108, 3243-3254` | `"backlog_drain"` accounting :3101; `BacklogDrainExpr` branch calling `_phase_stdlib_lower_backlog_drain_impl` :3243-3244; import :83. Additional live sites for Task 2.1's inventory: `wcc/route.py` :655, :1093; `wcc/elaborate.py` :327/:461/:1278/:2206-2209/:2338/:2692 | HOLDS (plus route/elaborate sites per re-anchor) |
| Inventory strings | `stage7_metrics.py:102`, `stdlib_contracts.py:90,271,273` | `stage7_metrics.py` absent (expected — Contradictions & Findings item 5); `stdlib_contracts.py` `form_name="backlog-drain"` :244, `backlog_drain_contract_invalid` diagnostics :270 | MOVED (stage7_metrics deleted; contracts → :244/:270) |
| Production consumer (sole) | `drain.orc:64`; hooks `stdlib_adapters.orc:26`, `work_item.orc:433`, `stdlib_adapters.orc:62` | `(backlog-drain design-delta …)` at `workflows/library/lisp_frontend_design_delta/drain.orc:64` with `:selector select-next-work-stdlib` (`stdlib_adapters.orc:26`), `:run-item run-selected-item-stdlib` (`work_item.orc:407`), `:gap-drafter draft-design-gap-stdlib` (`stdlib_adapters.orc:62`) | HOLDS (run-item hook MOVED → `work_item.orc:407`) |
| Blessed exemplar fixture | `tests/fixtures/workflow_lisp/valid/drain_stdlib_backlog_drain.orc` (98 lines) | present, 98 lines | HOLDS |
| Negative fixtures | ~12 under `tests/fixtures/workflow_lisp/invalid/` matching `backlog_drain_*`/`drain_ctx_*` | 10 matches (9 `.orc` + 1 `.json`): `backlog_drain_gap_drafter_non_record_payload_invalid.orc`, `backlog_drain_hidden_compatibility_bridge_public_boundary_invalid.orc`, `backlog_drain_hidden_compatibility_bridge_public_run_item_invalid.orc`, `backlog_drain_hidden_compatibility_bridge_reread_pointer_authority_invalid.json`, `backlog_drain_selector_blocked_extra_state_field_invalid.orc`, `backlog_drain_selector_blocked_reason_missing_invalid.orc`, `backlog_drain_union_call_boundary_invalid.orc`, `backlog_drain_workflow_ref_signature_invalid.orc`, `drain_ctx_contract_invalid.orc`, `drain_stdlib_backlog_drain_non_symbol_callee.orc` | HOLDS (count 10 vs drafting "~12") |
| Generic precedent | `std/phase.orc:82-149`, macro :150+ | `defproc review-revise-loop-proc` :82; `defmacro review-revise-loop` :150 | HOLDS |

#### Component-plan Task 1 Step 3 — fresh suite counts (2026-07-10)

| Module | Result |
| --- | --- |
| `tests/test_workflow_lisp_drain_stdlib.py` | `63 passed in 13.09s` |
| `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py` | `93 passed in 153.93s (0:02:33)` |
| `tests/test_workflow_lisp_procedures.py` | `128 passed in 1.12s` |
| `tests/test_workflow_lisp_generic_stdlib_composition.py` | `11 passed in 0.77s` |
| `tests/test_workflow_lisp_build_artifacts.py` | `190 passed in 288.84s (0:04:48)` |
| `tests/test_lisp_frontend_autonomous_drain_runtime.py` | `149 passed in 176.19s (0:02:56)` |

Zero failures, zero skips across all six modules — no failure identities to record. None of the known repo-wide baseline failures fall in these modules, as expected. **These counts are the Task-1.1 baselines cited by Gate P2.3 and Task 1.6.**

#### Task 1.1 Step 2 — pre-swap certification/parity baseline (intrinsic route)

```text
$ python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
exit 0
  "build_root": "/home/ollie/Documents/agent-orchestration/.orchestrate/build/0758b59a065ce8e0",
  "diagnostic_count": 0,
  "entry_workflow": "lisp_frontend_design_delta/drain::drain",
  "fingerprint": "0758b59a065ce8e0",
  "lowering_route": "wcc_m4",
  "lowering_schema_version": 2

$ python -c "import json,glob,os; p=max(glob.glob('.orchestrate/build/*/g8_deletion_evidence.json'), key=os.path.getmtime); print(p, json.load(open(p))['status'])"
.orchestrate/build/0758b59a065ce8e0/g8_deletion_evidence.json pass
```

Compile exit 0 with zero diagnostics; freshest `g8_deletion_evidence.json` status `pass`. This is the pre-swap intrinsic-route certification baseline for Gate P2.4.

### Task 1.2 / 1.2a probe record (2026-07-10)

#### G1 adjudication (2026-07-10)

The Task 1.2 probe hit gap G1 exactly as the STOP rule anticipated: the effectful-proc-hook /
`ProcRef` binding failure (outcome (c) of the component plan's Task 2 four-outcome table). The
human adjudicated on 2026-07-10: **extend the typechecker** (option "extend ProcRef"), preserving
the flagship `backlog-drain-proc` signature verbatim. Recorded as a **plan-required freeze
exception**: the semantic-migration freeze does not bar this change because it is plan-mandated
and explicitly user-adjudicated, not a discretionary refactor. Executed as Task 1.2a.

#### RED diagnostic (probe as the RED vehicle, pre-fix, fresh 2026-07-10)

```text
$ pytest tests/test_workflow_lisp_generic_stdlib_composition.py -k hook_probe -v
FAILED tests/test_workflow_lisp_generic_stdlib_composition.py::test_drain_generic_hook_probe_effectful_proc_hook_compiles_shared_validated

orchestrator.workflow_lisp.diagnostics.LispFrontendCompileError:
tests/fixtures/workflow_lisp/valid/drain_generic_hook_probe.orc:57:12:
[parametric_capability_undeclared] match on type parameter `SelectionT` requires declared `has-union-variant` capabilities
kind: validation
form: workflow-lisp > defproc > probe-generic
1 failed, 11 deselected in 0.34s
```

Line 57:12 is the match subject `(selector ctx)` in the committed variant-F (narrowed,
exhaustive variant-name-only 4-arm match) fixture shape; raised by the definition-scoped (raw)
pass, no `instantiated from` note.

#### Fix summary

- `orchestrator/workflow_lisp/procedure_typecheck.py` — `_apply_provisional_parametric_type`
  now descends into `ProcRefTypeRef` **return** positions, substituting the provisional
  `has-union-variant` capability union that `_provisional_parametric_match_types` synthesizes
  for a direct `TypeParamRef` parameter. ProcRef **parameter** positions deliberately stay raw
  (inference sinks, not match subjects). Single function touched; 14 lines added.
- `orchestrator/workflow_lisp/typecheck_proofs.py` untouched: its categorical
  `parametric_capability_undeclared` rejection of `TypeParamRef` match subjects is exactly the
  required negative behavior once declared capabilities are substituted upstream.
- `typecheck_dispatch.py` / `typecheck_calls.py`: zero changes (as the task brief expected).
- Unit tests pinning both directions in `tests/test_workflow_lisp_procedures.py`:
  `test_proc_ref_return_match_typechecks_with_declared_union_capabilities` (raw pass +
  instantiated specialization both typecheck) and
  `test_proc_ref_return_match_without_declared_capabilities_is_rejected`
  (`parametric_capability_undeclared` preserved when no capabilities are declared).
- Commits: `cab7741e` (typecheck extension + unit tests), `971597f7` (probe fixture + probe
  test — the component plan's sanctioned probe commit).

#### Post-fix probe outcomes

- **G1 cleared.** `pytest tests/test_workflow_lisp_generic_stdlib_composition.py -k hook_probe -v`
  → `1 passed, 11 deselected`. The committed probe fixture
  (`tests/fixtures/workflow_lisp/valid/drain_generic_hook_probe.orc`, variant-F shape: effectful
  `command-result` selector hook bound through `ProcRef[(CtxT) -> SelectionT]`, result consumed
  by an exhaustive 4-arm `match`) compiles through the shared-validated stage-3 entry.
- **G5 did not reproduce on the real ProcRef binding path.** The same shared-validated compile
  (`validate_shared=True`) of the ProcRef-bound effectful hook completed with zero diagnostics —
  no `source_map_missing`. This closes the Task 1.2 report's "weakly probed" caveat: the
  flagship's actual binding shape has now cleared loader-shape validation. (The
  known `source_map_missing` reproduction on trivially-bodied inline hooks —
  `minimal_caller_review_revise_loop.orc` — is unchanged and still routed frontend-only;
  production-shaped effectful hooks lower to real steps and pass.)
- **G3 confirmed as recorded finding** (post-fix re-probe of the preserved skeleton fixture:
  4-variant caller union, 2-arm generic match, shared-validated compile): the raw pass now
  clears and instantiation fails with literal diagnostic
  `union_match_non_exhaustive: match must cover every variant of `SelectionResult`; missing `GAP``
  carrying note `instantiated from <caller call site>`. Extra-variant callers remain unsupported
  pending a design decision; decision authority: the parametric design's Subset Semantics
  section (`docs/design/workflow_lisp_parametric_type_system.md`). Raised, not resolved. The
  existing pin `test_compile_stage3_rechecks_instantiated_generic_match_exhaustiveness` still
  passes, confirming instantiate-then-typecheck semantics are untouched.
- **Incidental (unchanged):** `procedure_type_param_unbindable` rejects constraint-only type
  parameters, so a single-hook probe cannot carry the flagship's field-typed SELECTED/GAP
  clauses (`(selection SelPayloadT)` / `(gap GapPayloadT)`); the committed fixture uses the
  variant-name-only clauses. The flagship is unaffected — `SelPayloadT`/`GapPayloadT` appear in
  the `run-item`/`gap-drafter` ProcRef positions.

#### Fresh suite results vs Task 1.1 baselines (2026-07-10, post-fix)

| Module | Baseline | Fresh result |
| --- | --- | --- |
| `tests/test_workflow_lisp_generic_stdlib_composition.py` | 11 passed | `12 passed in 0.79s` (+1: probe test) |
| `tests/test_workflow_lisp_procedures.py` | 128 passed | `130 passed in 1.14s` (+2: capability unit tests) |
| `tests/test_workflow_lisp_expressions.py` | — (owning typecheck module, no Task 1.1 baseline) | `50 passed in 0.31s` |
| `tests/test_workflow_lisp_phase_stdlib.py` | — (owning typecheck module, no Task 1.1 baseline) | `104 passed in 2.89s` |
| `tests/test_workflow_lisp_drain_stdlib.py` | 63 passed | `63 passed in 12.98s` |
| `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py` | 93 passed | `93 passed in 155.10s` |

Zero failures — no new failure identities; count deltas are exactly the added tests.

End-to-end certification compile (required for typecheck changes) re-run post-fix: exit 0, zero
diagnostics, fingerprint `0758b59a065ce8e0` (identical to the Task 1.1 baseline), freshest
`g8_deletion_evidence.json` status `pass`.

Task 1.2 has no checkbox line in this plan; this record is its completion evidence. Task 1.3 is
unblocked.

#### Task 1.3 — Intrinsic-route checkpoint-identity baselines (2026-07-10)

Committed `tests/baselines/drain_checkpoint_identity/{exemplar,design_delta_drain}.json` plus the
two freshness tests in `tests/test_workflow_lisp_checkpoint_identity_comparison.py`
(commit `8e2f8fcc`). Snapshots taken from the current intrinsic route, before any edit to
`std/drain.orc`, the macro, or the production hooks.

Map sizes: `exemplar.json` **5** rows (drain, selector-run, run-selected-item, gap-draft, and the
generated `std/drain::backlog-drain` child); `design_delta_drain.json` **70** rows across 17
workflows of the production compile closure (drain entry 7, `work_item::run-selected-item-stdlib`
25, `implementation_phase` 10, `plan_phase` 5, generated `std/drain::backlog-drain` 1, rest in
architect/adapters/transitions/selector/projections/bootstrap modules). The generated child's
`normalize_result` checkpoint id is identical in both baselines (context-independent), and both
maps were byte-identical across two consecutive compiles.

Fresh output (two consecutive runs, second shown):

```text
pytest --collect-only tests/test_workflow_lisp_checkpoint_identity_comparison.py -q  → 3 tests collected
pytest tests/test_workflow_lisp_checkpoint_identity_comparison.py -v                 → 3 passed in 1.82s
```

Two recorded deviations from the component plan's Task 3 skeleton (both widen, never weaken, the
Task 1.5 gate):

1. **The map spans every validated bundle of the compile, not just the entry executor.** Each
   bundle's runtime plan carries only its own workflow's lexical points, so an entry-only map for
   the exemplar would hold 1 row and omit the macro-generated `std/drain::backlog-drain` child —
   exactly the generated-step identities the migration puts at risk.
2. **Keys are `{workflow}::{origin}::{step_kind}`, not the skeleton's two-part form.** In the
   production module, `stdlib_adapters::draft-design-gap-stdlib`'s `recorded_progress` step
   carries two effect-boundary checkpoints (`call` ckpt:b521875b… and `resource_transition`
   ckpt:fe2e42e0…) with identical `(workflow, origin_key)`; the two-part key would silently drop a
   row. This is deterministic double-annotation, not run-to-run instability. The helper fails
   closed on any remaining duplicate key. `checkpoint_identity_map(executor)` itself is untouched;
   note for Task 1.5: its two-part keying is lossy on the production module.

Anchor drift noted: the task brief described the module as "currently 12 tests" — it held 1 test
at baseline (`test_checkpoint_identity_stable_across_recompiles`, parametric plan Task 9); all
pre-existing tests still pass. Task 1.3 has no checkbox line in this plan; this record is its
completion evidence.

### Task 1.4 authoring record — gap chain, adjudications, gap-C fix, generic drain body (2026-07-10)

Commits (chronological): `49fbad78` (G2 design amendment), `fd79b2e0` (G6 has-field typecheck
extension), `c0610bf6` (gap-C specialized-lowering fix + committed reproducers), `49f221f1`
(generic body + minimal-caller fixture + composition test), plus this ledger commit.

#### The gap chain (G6 → A → B → C → D)

Authoring the flagship body surfaced five pre-existing gaps, each reachable only after the
previous one cleared. Literal diagnostics (fresh reproductions recorded in the Task 1.4/1.4a/1.4b
reports, `.superpowers/sdd/`):

1. **G6 — `has-field` granted no body capability.** The five irreducible type-param projections
   (`ctx.run`, `ctx.ledger`, `ctx.run.artifact-root`, `selected.selection.item-id`,
   `selected.selection.item-state-root` — exactly the intrinsic's `item_ctx_value` construction)
   all rejected in the definition-scoped pass:
   `std/drain.orc:351:36: [record_field_unknown] type `CtxT` does not support field access`.
   **FIXED** (`fd79b2e0`, reviewed/approved): `provisional_shared_union_field_capabilities`
   (`parametric_constraints.py`) now admits declared `has-field` clauses alongside
   `has-shared-union-field`, producing the same definition-scoped capability the existing
   `resolve_field_access` consumer already honors. Adjudicated by analogy to the user's G1
   decision (extend the typechecker — `cab7741e` precedent). Undeclared fields still reject
   (negative test pins code + categorical message); call-site `has-field` checking and
   specialization passes untouched. Unit tests in `tests/test_workflow_lisp_procedures.py`
   (130 → 132).
2. **Gap A — a nested generic call loses its specialization rewrite.** The originally specified
   direct shape `(settle-drain-terminal (backlog-drain-proc …))` fails:
   `[proc_ref_signature_invalid] procedure ref `minimal_caller_backlog_drain::select-minimal`
   does not match `ProcRef[(CtxT) -> SelectionT]`: expected `ProcRef[CtxT -> SelectionT]`, got
   `ProcRef[MinimalDrainCtx -> MinimalSelection]`; first mismatch at parameter 1 `ctx``.
   Root cause (instrumented, Task 1.4a/1.4b): `_typecheck_parametric_procedure_call` succeeds and
   returns a rewritten call node, but every return path of the enclosing
   `typecheck_procedure_call_expr` keeps the ORIGINAL expr, so `discover_proc_ref_specializations`
   re-walks the raw inner call and validates the proc-ref argument against the raw parametric
   param type. A verified, scoped typed-call handoff fix exists (preserved diff; Task 1.4b report
   §3) but is **necessary-not-sufficient** — it unmasks gap D. **NOT LANDED** (user adjudication
   2026-07-10, below).
3. **Gap B — `done` cannot wrap an `if` in loop lowering.** The mirrored EMPTY-vs-COMPLETED split
   authored as `(done (if …))` fails:
   `[workflow_return_not_exportable] `loop/recur` could not project `result__items_processed`
   from `IfExpr` in this Stage 3 slice` (minimal fail/pass probe pair preserved).
   **Controller-sanctioned recorded body delta**: push `done` into the `if` branches —
   `(if (= state.items-processed 0) (done (variant … EMPTY …)) (done (variant … COMPLETED …)))`.
   Semantics identical; consistent with the `review-revise-loop-proc` precedent.
4. **Gap C — cross-module specialized generic loop lowering resolved caller unions by bare
   name.** With A worked around and B recorded, the compile failed in specialized lowering:
   `[type_unknown] unknown type `MinimalRunResult`` (span: the caller fixture's own `defunion`).
   Instrumented path: `control_loops.py:1179` (`_lower_loop_terminal_expr`) →
   `pure_projection.lower_pure_projection_step` → `_type_descriptor` (`pure_projection.py:767`)
   → `type_env.resolve_type(<bare caller union name>)` in the generic's defining-module
   environment; second surface `_field_type` (`pure_projection.py:704`). The same shape compiles
   same-module. **User adjudicated: fix in the machinery** — landed `c0610bf6` (record below).
5. **Gap D — procedure calls in argument position are unsupported by WCC elaboration at all**
   (monomorphic or generic): `TypeError: unsupported WCC elaboration node: ProcedureCallExpr` —
   a compiler crash, not a diagnostic — on a 24-line monomorphic single-module reproducer
   (`(wrap-status (status-mono ctx))`); the let*-bound control compiles. Root cause:
   `wcc/elaborate.py` supports effect calls at exactly three positions (workflow body/tail, let*
   binding, match subject); `_prebind_effect_argument_matches.replace_arg` pre-binds only
   `MatchExpr`/`LetStarExpr` arguments. **NOT FIXED** (user adjudication 2026-07-10, below).

#### Adjudications (all 2026-07-10)

- **G6** — extend the typechecker, by analogy to the user's G1 adjudication (`cab7741e`
  precedent); landed `fd79b2e0`, reviewed/approved.
- **Gaps A + D (user decision)** — sanction the **let*-bound composition shape**
  (`(let* ((terminal (backlog-drain-proc …))) (settle-drain-terminal terminal))`) for the
  minimal-caller fixture AND for Task 1.5's macro expansion; record A and D as documented
  language limitations; DEFER both machinery fixes to the post-S3 queue. Neither the preserved
  gap-A handoff diff nor any `wcc/elaborate.py` hoist was landed.
- **Gap B (controller-sanctioned)** — recorded body delta, no machinery change.
- **Gap C (user decision)** — fix in the machinery, scoped to specialized-procedure lowering.

#### Gap-C fix record (`c0610bf6`)

Chosen option: **construct descriptors from already-resolved type refs instead of bare names**
(the sanctioned minimal option; the alternative — composing the caller module's type environment
into the specialized lowering env — was rejected as a wider surface that risks caller/definer
name shadowing and touches every env consumer instead of the two failing sites).
`VariantCaseTypeRef` already carries `field_types`, the resolved per-variant field map installed
by its sole constructor `type_env.union_variant` (originally added for provisional `:forall`
unions — `type_env.py`). The two failing surfaces in `lowering/pure_projection.py` —
`_field_type` (VariantCaseTypeRef branch) and `_type_descriptor` (variant-case branch) — now
prefer that carried mapping and fall back to the name-based union re-lookup when it is absent or
incomplete. Same-module refs carry the identical mapping object the name lookup would return, so
descriptors are byte-identical wherever the old path succeeded; behavior changes only where the
bare-name lookup failed (exactly the cross-module specialized shape). Non-specialized paths are
behaviorally unchanged (canary evidence below).

TDD: committed cross-module reproducer
`tests/fixtures/workflow_lisp/modules/valid/generic_loop_union_cross_module/` (caller +
imported-module pair mirroring the `generic_stdlib_composition` multi-module compile) — RED at
`c0610bf6^` with `[type_unknown] unknown type `Selection`` at the caller's own `defunion`,
traceback frame-identical to the drain failure. A smaller pair proved practical, so the drain
fixture was not needed as the RED vehicle (choice recorded per brief). Reproduction detail worth
keeping: the failure requires a `continue` arm whose `loop-state` update projects a caller-union
binder field (`:note p.note`) — `done`-payload union construction alone lowers through the
materialize path and never reaches `lower_pure_projection_step`, which is why earlier
done-only probes passed. Same-module control committed as
`tests/fixtures/workflow_lisp/valid/generic_loop_union_same_module.orc` + regression test.
Canaries after the fix, before commit: identity suite **3 passed** (zero row
changes/appearances/disappearances) AND production compile exit 0, `diagnostic_count: 0`,
fingerprint **`0758b59a065ce8e0` unchanged**, freshest `g8_deletion_evidence.json` `pass` — the
machinery fix is invisible to the production closure.

#### Post-S3 deferred queue (user-adjudicated deferrals — do not land inside Phase 1)

1. **General ANF hoist for argument-position procedure calls** (gap D): extend
   `wcc/elaborate.py`'s `_prebind_effect_argument_matches.replace_arg` to pre-bind
   `ProcedureCallExpr` arguments the way match subjects already are. Blast radius: effect
   ordering and checkpoint identity for every shape that starts using it, plus
   provider/command/produce-one-of argument positions that share `replace_arg`; requires the
   identity + fingerprint canaries and a deliberate decision.
2. **Gap-A typed-call handoff fix**: rebuild `expr.args` with rewritten child nodes in
   `typecheck_procedure_call_expr` (verified experiment diff preserved and referenced in the
   Task 1.4b report, §3). Without the hoist it converts gap A's misleading diagnostic into
   gap D's crash, so it lands together with (1) or not at all.

#### Documented language limitation

**Procedure calls in argument position are unsupported; bind the result with `let*` and pass the
binding.** Today the nested shape crashes as a raw `TypeError` (gap D) or — for generic callees —
mis-reports as `proc_ref_signature_invalid` (gap A). Consequences recorded now:
- **Task 1.5**: the macro re-target MUST emit the let*-bound terminal shape, not the nested
  `(settle-drain-terminal (backlog-drain-proc …))` sketched earlier in this plan's Task 1.5
  description — this is the user-sanctioned amendment of the expansion shape.
- **Task 1.7**: the doc sync should surface the limitation in the drafting guidance
  (`docs/lisp_workflow_drafting_guide.md`).

#### Reality anchors mirrored from the intrinsic (read from the frozen
`_phase_stdlib_lower_backlog_drain_impl`, `lowering/phase_drain.py`; none invented)

| Anchor | Value | Intrinsic evidence |
| --- | --- | --- |
| G2 item-context projection | `run ← ctx.run`, `item-id ← selection.item-id`, `state-root ← selection.item-state-root`, `artifact-root ← ctx.run.artifact-root`, `ledger ← ctx.ledger` | `item_ctx_value`, phase_drain.py:602-608 |
| G2 clause types (design amendment `49fbad78`) | `(SelPayloadT has-field item-id String)`, `(SelPayloadT has-field item-state-root Path.state-root)` | std/drain `SelectionPayload` (drain.orc:21-23) + `ItemCtx.state-root` (context.orc:18) |
| G4 selector-BLOCKED mapping | constant `user_decision_required`; the selector's `reason` string is dropped; progress/items stay at loop state | `selector_blocked_compatibility_blocker`, phase_drain.py:653, applied at 1496-1518 |
| `:on-exhausted` class | `unrecoverable_after_fix_attempt`; items/progress retained from accumulator state | `on_exhausted.outputs`, phase_drain.py:1704-1709 |
| Progress-report seeding | literal `artifacts/work/drain-progress-report.md`, supplied by the caller as the trailing `(initial-progress-report WorkReport)` parameter via `__generated-relpath-seed__` (fixture now; Task 1.5's macro next) | `seed_progress_literal` phase_drain.py:654; `loop_state_seed_step` 1083-1099 |
| EMPTY vs COMPLETED | EMPTY selection with `items-processed = 0` → terminal EMPTY, else → COMPLETED | `empty_route_step` if/else, phase_drain.py:1256-1306 |
| run-item CONTINUE / BLOCKED | items +1 + progress ← `summary-path`; items unchanged + progress ← `summary-path` + blocker ← `blocker-class` | phase_drain.py:1428-1448 / 1450-1465 |
| gap CONTINUE / BLOCKED | no-op state carry; progress ← `progress-report-path` + blocker ← `blocker-class` (GapResult vocabulary) | phase_drain.py:1375-1389 / 1390-1405 |

#### Recorded deviations (authored body/fixture vs the component-plan Task 4 skeleton)

1. COMPLETED arm added to the EMPTY route — the skeleton omits it; the terminal union and
   `finalize-drain-terminal` carry it and parity would break without it (intrinsic 1256-1306).
2. `:state-root selected.selection.item-state-root` in the ItemCtx construction — the skeleton
   wrote `ctx.state-root`, contradicting the intrinsic (`selection_value.get("item-state-root")`,
   phase_drain.py:605).
3. Gap-CONTINUE arm uses a no-op `:items-processed state.items-processed` override — the parser
   rejects `(loop-state :like state)` with zero overrides (expressions.py:1234).
4. `settle-drain-terminal` declares `(writes drain-summary)` in addition to the skeleton's
   `uses-command` atom — declared effects must equal transitive inferred effects and
   `consume-drain-terminal-effects` declares `(writes drain-summary)`.
5. **Gap-B body delta**: EMPTY arm authored `(if … (done …) (done …))` instead of the skeleton's
   `(done (if …))` (controller-sanctioned; semantics identical).
6. **let*-bound fixture delta (gaps A/D)**: `minimal_caller_backlog_drain.orc` let*-binds the
   terminal instead of the originally specified direct nested call; the macro is still not
   exercised (Task 1.5).

#### Fresh verification (2026-07-10, tree at `49f221f1`, baselines compared by identity)

| Suite | Result | Baseline |
| --- | --- | --- |
| `test_workflow_lisp_generic_stdlib_composition.py` | collect-only **15**; **15 passed** | 12 + exactly the three added tests (two gap-C regression tests, one flagship composition test) |
| `test_workflow_lisp_drain_stdlib.py` | **63 passed** | 63 — identical |
| `test_workflow_lisp_procedures.py` | **132 passed** | 132 (post-`fd79b2e0`) — identical |
| `test_workflow_lisp_build_artifacts.py` | **190 passed** in 443.11s | 190 — identical |
| `test_workflow_lisp_design_delta_drain_migration_feasibility.py` | **93 passed** in 232.83s | 93 — identical |
| expressions + variant_proofs + phase_stdlib | **161 passed** | with composition = 176 vs the 173 four-module combined 1.4a baseline; delta exactly the three added tests |
| `test_workflow_lisp_checkpoint_identity_comparison.py -v` | **3 passed** — run twice: after the gap-C fix (pre-`c0610bf6`) and after the drain.orc authoring (pre-`49f221f1`) | 3 — **no row change/appearance/disappearance**; the dormant procs lower into no validated bundle |
| `defmacro backlog-drain` region | byte-identical (content-anchored extraction, HEAD vs authored tree; 295 bytes → 295 bytes) | required |

Production compile (P2 command), two runs:
- At `c0610bf6` (machinery fix only): exit 0, `diagnostic_count: 0`, fingerprint
  **`0758b59a065ce8e0`** unchanged, `g8_deletion_evidence.json` `pass`.
- At `49f221f1` (dormant procs in `std/drain.orc`): exit 0, `diagnostic_count: 0`,
  `lowering_route: wcc_m4`, `g8_deletion_evidence.json` `pass`, fingerprint
  **`24798cac21228fe6`**. The fingerprint change is mechanical and expected: `_fingerprint_build`
  content-addresses every module source in the compile closure (`_sha256_path` over
  `modules_by_name`), and `std/drain.orc` gained the dormant definitions — any completion of
  Task 1.4 changes it by construction. The behavioral pre-swap evidence — the intrinsic-route
  checkpoint-identity maps — is unchanged (identity suite green, zero rows), which is the gate
  Task 1.5 depends on. Review addendum (2026-07-10): one span-provenance artifact delta exists
  between the two builds — checkpoint `ckpt:375db64221bf1496a0e1d147` (the production
  `backlog_drain` effect boundary) changed its `binding_schema.schema_digest`, because the digest
  hashes `repr(type_ref)` (`wcc/defunctionalize.py:1072-1088`) and TypeRef reprs embed source
  spans, which the export additions shifted by two lines. Same mechanical class as the
  fingerprint; `checkpoint_id` and all identity rows unchanged; pre-existing machinery behavior.

Task 1.4 has no checkbox line in this plan; this record is its completion evidence. Task 1.5 is
unblocked, with its expansion shape amended to the let*-bound terminal per the A+D adjudication.
