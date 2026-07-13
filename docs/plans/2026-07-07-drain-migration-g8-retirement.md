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
| Design Delta certification data and loading | **Retired in Task 3.3.** `build_design_delta.py`, `DesignDeltaEvidence`, the family catalog/evidence loaders, and the `_maybe_load_design_delta_*` family are deleted and have no live owner. |
| Design Delta G8 serialization | **Retired in Task 4.2.** `build_design_delta.py`, `serialize_design_delta_g8_deletion_evidence`, and the `DESIGN_DELTA_G8_*` constants are deleted and have no live owner. |
| Build artifact persistence | `orchestrator/workflow_lisp/build_artifacts.py`: `_write_build_artifacts` owns only the surviving generic manifest/artifact writes; the temporary G8 artifact entry and payload threading are deleted. |
| Public build pipeline and stage call sites | `orchestrator/workflow_lisp/build.py`: `build_frontend_bundle`, `_select_and_reattach`, and `_emit` remain the generic public build pipeline; the Design Delta serializer import/call, payload plumbing, path constants, and compatibility re-exports are deleted. |
| Drain expression typecheck owner | **Retired in Task 2.1.** Commit `0a4a687a` deleted `typecheck_backlog_drain_expr`; `0f2fda63` deleted `BacklogDrainExpr` with its AST/elaboration surface. `orchestrator/workflow_lisp/typecheck_drain_phase.py` remains for generic phase-target/provider-phase responsibilities and the surviving `typecheck_produce_one_of_expr`; imported `std/drain.orc` procedures use the ordinary procedure/typechecking path. |
| Shared typecheck helpers and dispatch | **Retired in Task 2.1.** Commit `0a4a687a` deleted `workflow_ref_signature`, the three specialized workflow-ref validators, and `_backlog_drain_blocker_class_type`; `d8bd4e29` deleted the `BacklogDrainExpr` dispatch branch. `typecheck_calls.py` and `typecheck_dispatch.py` remain generic owners and contain no backlog-drain-specific dispatch. |
| Intrinsic drain lowering | **Retired in Task 2.1.** Commit `53588875` deleted `lowering/phase_drain.py`, `lowering/drain_terminal.py`, `_callable_backlog_drain_*`, `_ensure_callable_backlog_drain_workflow`, `_phase_stdlib_lower_backlog_drain_impl`, `_validate_backlog_drain_provider_metadata`, `lower_shared_drain_terminal_result`, and their intrinsic-only helpers; `18e90977` removed the adjacent intrinsic resource/fixture residue. The live drain body is the imported generic procedure/macro in `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`. |
| Surviving selected-item summary helper | `orchestrator/workflow_lisp/lowering/phase_resource.py`: `_selected_item_summary_pointer_path` is the final live owner, with its resource-lane consumer in the same module. Task 2.1 moved the helper unchanged before deleting `phase_drain.py`. |
| Lowering entry/dispatch sites | **Backlog-drain wiring retired in Task 2.1.** `lowering/control_dispatch.py`, `lowering/core.py`, `lowering/phase_helpers.py`, and `lowering/phase_stdlib.py` remain generic modules but contain no `BacklogDrainExpr`, `_lower_backlog_drain`, or `_phase_drain_lower` import, dispatch branch, facade, or compatibility re-export. |
| Migration parity | `orchestrator/workflow_lisp/migration_parity.py`: `ParityTarget`, `load_parity_targets`, report/Markdown/index generation, gate-evaluation schema machinery, `run_migration_parity`, and the CLI-facing two-family route are the preserved generic kernel. Task 4.1 deleted the Design-Delta/G8 constants, deleted-row validation, resource-transition evaluator, runtime-audit sub-lane, and family-specific role wiring. |

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
1. Phase 1 Tasks 1.1–1.7, including Task 1.6a, committed.
2. **Identity (prereq 4):** `pytest tests/test_workflow_lisp_checkpoint_identity_comparison.py -v` → PASS with the generic route active, against the recorded **intrinsic-route** baselines; the Phase-1 ledger entry in this file states either "identical" or cites the reviewed identity-migration commit. Design: checkpoint ids "unchanged across the intrinsic-to-generic route swap, or an explicit reviewed identity-migration step remaps persisted records".
3. **Parity (prereq 5):** `pytest tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_lisp_frontend_autonomous_drain_runtime.py -q` → at Task-1.1 recorded baselines (contract deltas documented in the Task 1.6 census).
4. **Certification lane green on the generic route:** the production compile command (Task 1.6 Step 4) exits 0 and the freshest `g8_deletion_evidence.json` reports `"status": "pass"`.
5. **Parity report:** `python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/review-parity-check --target design_delta_parent_drain --require-non-regressive` → exit 0; `artifacts/work/review-parity-check/design_delta_parent_drain.json` has `"non_regressive": true`.
6. **Intrinsic reachability shrunk to fixtures:** `grep -rln "backlog-drain-callable-boundary" workflows/` → empty (no production caller reaches the intrinsic; only `tests/fixtures/` hits remain, and they retire with Phase 2).

**Status (reviewed 2026-07-12): SATISFIED.** The durable evidence is recorded in
Phase 1 Ledger entry (k). Gate P2 admitted the reviewed Phase 2 sequence. Phase
2 Tasks 2.1–2.3 and the bounded Design Delta promotion handoff are now
complete. Gate P3 is also satisfied by the later independent joint proof
recorded in Phase 2 Ledger entry (f). Phase 3 Tasks 3.1–3.4 are complete and
reviewed. Gates P3 and P4 are independently reviewed and satisfied. Task 4.1 is
complete and independently reviewed, with SPEC PASS and CODE QUALITY PASS.
Task 4.2 is complete and independently reviewed, with SPEC PASS and CODE
QUALITY PASS. Task 4.3 is complete. Phase 4 is complete. Gate S3 is satisfied.
The semantic-migration freeze is lifted. The current selector is
**Procedure-First Roadmap Stage 4: Design The Broader Procedure-First
Contract**. Stage 5 typed result guidance and Stage 6 YAML archive remain later
work.

**Gate P3 (entry to Phase 3):**
1. Phase 2 Tasks 2.1–2.3 committed; name-blindness check (Task 2.3 Step 2) clean.
2. Certification lane still green **after** the deletion: production compile exits 0; freshest `g8_deletion_evidence.json` still `"status": "pass"` (now via the `spec is None` / imported-only branches of `serialize_design_delta_g8_deletion_evidence` in `build_design_delta.py` — Task 2.2 decides which).
3. Final parity regeneration (same command as P2.5) → exit 0, `"non_regressive": true`; `promotion_eligibility` recorded in the Phase-2 ledger entry. This is the "G7 + promotion evidence -> G8" sequencing obligation discharged and recorded.
4. Promotion handoff completed and recorded (steering, user, 2026-07-07; governing sequence Stage 3): YAML-retirement Task 5 family 1 has run only through registration, fresh non-regressive parity, the `.orc` primary flip, and fresh end-to-end evidence. The `.orc` entry `lisp_frontend_design_delta/drain::drain` is the primary production route; Task 5's archive bullet has **not** run, and the YAML twin remains for Stage 6.

**Status (independently reviewed 2026-07-12): SATISFIED.** Phase 2 Ledger entry
(e) records the bounded promotion handoff, and entry (f) records the later
fresh joint verification of conditions 1–4 at base HEAD
`c82d150286248661bbfe2d8cb338715f47a02d36`. This status-and-routing closure
does not alter the verified implementation or evidence surfaces. Gate P3 is
satisfied and now admits Phase 3. Tasks 3.1–3.4 are complete and reviewed.
Gates P3 and P4 are independently reviewed and satisfied. Task 4.1 is complete
and independently reviewed, with SPEC PASS and CODE QUALITY PASS. Task 4.2 is
complete and independently reviewed, with SPEC PASS and CODE
QUALITY PASS. Task 4.3 is complete. Phase 4 is complete. Gate S3 is satisfied.
The semantic-migration freeze is lifted. The current selector is
**Procedure-First Roadmap Stage 4: Design The Broader Procedure-First
Contract**. Stage 5 typed result guidance and Stage 6 YAML archive remain later
work.

**Gate P4 (entry to Phase 4):**
1. Phase 3 Tasks 3.1–3.4 committed.
2. `design_delta_parent_drain` absent from `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`; parity index regenerated without it.
3. Production compile of the `.orc` entry green **without** the family-gated certification block (Task 3.4 Step 1 output recorded).
4. `python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/review-parity-check --require-non-regressive` → exit 0 over the remaining targets (`cycle_guard_demo`, `design_plan_impl_stack`).

**Status (independently reviewed 2026-07-13): SATISFIED.** Phase 3 Tasks
3.1–3.4 are committed and reviewed. Task 3.4 received **SPEC PASS** and **CODE
QUALITY PASS** with no open findings. Its ledger entry records the exact green
production compile without the retired family-certification block and the
two-family non-regressive parity run. The target manifest and generated index
contain only `cycle_guard_demo` and `design_plan_impl_stack`; the retired
`design_delta_parent_drain` target is absent. Gates P3 and P4 are independently
reviewed and satisfied. Task 4.1 is complete and independently reviewed, with
SPEC PASS and CODE QUALITY PASS. Task 4.2 is complete and independently
reviewed, with SPEC PASS and CODE QUALITY PASS. Task 4.3 is complete. Phase 4
is complete. Gate S3 is satisfied. The semantic-migration freeze is lifted.
The current selector is **Procedure-First Roadmap Stage 4: Design The Broader
Procedure-First Contract**. Stage 5 typed result guidance and Stage 6 YAML
archive remain later work.

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

- [x] **THE GATE (explicit STOP-on-mismatch rule):** run `pytest tests/test_workflow_lisp_checkpoint_identity_comparison.py -v` — the freshness tests now compare the **generic route** against the Task-1.3 intrinsic-route baselines. *(DIFFERED — 70→100 rows, fully classified in 1.5c report §5; user adjudicated 2026-07-11 option (b) remap route, evidence-based, then land-now-certify-in-1.6 sequencing; reviewed remap landed as `6a28ddd4` — see "Task 1.5 identity remap adjudication + landing record" below.)*
  - **Identical → record "identical" in the Phase 1 Ledger and proceed.**
  - **Any difference → BLOCKED. Do not commit the re-target.** Produce the row-level diff (which `(workflow, origin_key)` checkpoint ids changed/appeared/vanished), attach it to the ledger, and present the human the design's two sanctioned options: (a) make the generic route reproduce the intrinsic's generated-step identities; (b) "an explicit reviewed identity-migration step remaps persisted records" (design, Specialization Pipeline). **Neither is chosen unilaterally.** Resume runs of consuming workflows depend on these ids; a silent identity break is the failure mode this gate exists to catch.

Selectors: identity suite above, plus `pytest tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q` (failures here that are diagnostic-code shifts get inventoried for Task 1.6, not chased).
Commit (only if the gate passed): `Re-target backlog-drain macro onto the generic proc`.

### Task 1.6: Consumer parity via the existing certification lane (prerequisite 5)

Execute the 2026-07-06 plan's **Task 6** (obligation census; relocations; diagnostic contract deltas), with these amendments:

- The census section is appended to **this** plan's Phase 1 Ledger.
- Prereq 5 rule (quoted): "census/boundary/provider-metadata obligations move to shared validation surfaces, not into the generic body." Any obligation whose only home would be inside the generic body is a design conflict — **raise it**.
- Intrinsic-shape assertions in `tests/test_workflow_lisp_drain_stdlib.py` (for example, tests resolving the generated `std/drain::backlog-drain` child workflow) are reviewed contract deltas: rewrite them to assert the generic route's lowered shape and record each delta (`old assertion → new assertion, why`) in the census. Deleting a negative fixture outright requires showing its scenario is now impossible to author, not merely differently reported.

- [x] **Step 4 (the certification lane IS the parity gate — run it):**
```bash
pytest tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_parent_drain_census_alignment.py tests/test_lisp_frontend_autonomous_drain_runtime.py -q
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/review-parity-check --target design_delta_parent_drain --require-non-regressive
```
Expected: suites at Task-1.1 baselines; compile exits 0 with all fail-closed census gates (value-flow, consumer-rendering, resume-plumbing, transition-authoring, compatibility-bridge, boundary-authority) green on the generic route; parity exits 0 with `"non_regressive": true`. The autonomous-drain runtime suite is end-to-end consumer evidence — failures there are real parity breaks, not contract deltas.
Commit: `Move drain obligations to shared surfaces with parity evidence` (explicit file list).

### Task 1.6a: F5 sibling contract-delta sweep (required before documentation sync)

- [x] Execute the approved [F5 sibling contract-delta design](2026-07-12-f5-sibling-contract-delta-design.md) through the detailed [F5 sibling contract-delta implementation plan](2026-07-12-f5-sibling-contract-delta-plan.md) using Subagent-Driven Development.
- Scope is exact until closure documentation: add the one promoted-hook fixture row in `docs/workflow_lisp_route_readiness_registry.json` and retarget only `tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py` from the retired child-callable representation to the parent-owned inline generic route. No production, stdlib, fixture, frozen migration, baseline, parity-target/report, or generated-artifact edit is permitted.
- Required gates: route-readiness registry plus CLI and cited feasibility evidence; full runtime-proof module with the four-case validation/lint matrix; the two directly affected modules; Task-1.6 four-suite gate; checkpoint identity; generic composition plus procedures; broad `pytest -q -n 16 --dist=worksteal` in tmux; prohibited-diff audit; spec and quality reviews.
- Durable proof obligations: fail-closed unique structural selection of the inline repeat; normal-fixture empty retained diagnostics paired with an in-memory low-level-boundary variant; dedicated/default and shared/default retain the structured finding; shared/strict and dedicated/strict reject; compiler-owned generated metadata resolves to source-mapped owners; generated nested structure validates; authored parent-ref fallback remains rejected even if both allowance collections list it.
- This governing plan is prose- and gate-led: no machine-readable selector or manifest enumerates its Phase 1 task numbers, so there is no routing-state companion edit. Historical `state/**/manifest.json` files are provenance for other drains and remain untouched.

Commit implementation in the two-file scope as the detailed plan prescribes; after all gates and both reviews pass, record the evidence in the Phase 1 Ledger and commit the roadmap-only closure as `Record F5 sibling contract evidence`. Do not claim Task 1.7 or Gate P2 complete from this sweep.

### Task 1.7: Documentation sync and integration evidence

Execute the 2026-07-06 plan's **Task 8** minus any retirement claims (the intrinsic still exists — record Tranche 2 prerequisites 3–5 as landed, prerequisite 6 as gated on this plan's Phase 2): update `docs/design/workflow_lisp_parametric_type_system.md` status parentheticals, `docs/design/workflow_lisp_runtime_native_drain_authoring.md` §12 status note, `docs/capability_status_matrix.md`. Reconcile the G5E current-evidence note in `docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md` with the accepted F5 contract: the promoted fixture is boundary-clean; an explicit in-memory low-level-boundary variant retains the machine-readable diagnostic under default lint; and rejection requires strict lint for both shared-callable and dedicated-runtime-proof profiles. Do not reintroduce a child workflow or describe `SHARED_CALLABLE` with default lint as a rejection policy. Integration evidence per repo rule:
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

- [x] **Step 1: Re-enumerate by grep (this output is the inventory of record):**
```bash
grep -rn "BacklogDrain\|backlog_drain\|backlog.drain" orchestrator/workflow_lisp/ --include="*.py" | grep -v stdlib_modules
grep -rln "backlog-drain-callable-boundary" orchestrator/ tests/ workflows/
grep -rn "drain_terminal\|phase_drain" orchestrator/ --include="*.py" | grep -v "test"
rg -n "_selected_item_summary_pointer_path|from \.phase_drain import|_phase_drain_lower|_lower_backlog_drain" orchestrator/workflow_lisp/lowering orchestrator/workflow_lisp/wcc
```
Record the diff against the table above in the Phase 2 Ledger. Any hit in `workflows/library/` outside fixtures → STOP (Gate P2.6 was not actually satisfied).
- [x] **Step 2: Preserve the non-intrinsic resource helper first.** Move `_selected_item_summary_pointer_path` byte-for-byte into `lowering/phase_resource.py`, its only live non-definition consumer, then remove that module's import from `phase_drain.py`. Run `rg -n "_selected_item_summary_pointer_path" orchestrator/workflow_lisp/lowering` and record one definition plus the resource-lane call, with no surviving cross-import; run `pytest tests/test_workflow_lisp_resource_stdlib.py -q` before any drain deletion. This is an ownership move with unchanged path semantics, not part of the deletion count.
- [x] **Step 3: Delete in dependency order** — drain dispatch/re-export sites (WCC route/elaborate/defunctionalize, `control_dispatch.py`, `core.py`, the drain compatibility re-export in `phase_helpers.py`, and only the drain import/wrapper in `phase_stdlib.py`) → only the `BacklogDrainExpr` import and dispatch branch in `typecheck_dispatch.py` → only `typecheck_backlog_drain_expr` and its proven-exclusive imports/helpers in `typecheck_drain_phase.py` → elaboration + route entry → AST node + spec dataclass → drain-only helpers in `typecheck_calls.py` (preserving any shared helper with a surviving caller) → lowering impl + monomorphizer → `drain_terminal.py` → import fallout. Do not delete `typecheck_drain_phase.py`: preserve `typecheck_phase_target_expr`, `typecheck_run_provider_phase_expr`, `typecheck_produce_one_of_expr`, `_expected_extern_operand`, and every import/helper they still consume. Re-run a symbol/caller inventory after removing the backlog-drain handler before deleting any `_require_union_variant_*` helper. Preserve all non-drain functions and exports in `phase_helpers.py`, `phase_stdlib.py`, and `phase_resource.py`. Verify between clusters with `python -c "import orchestrator.workflow_lisp" && pytest tests/ -q --collect-only > /dev/null && echo OK`; before deleting the `phase_drain.py` module, rerun the Step-1 import search and require zero surviving consumers. Multiple incremental commits, each staging its explicit file list, each compiling.
- [x] **Step 4: Add the permanent CI guard** (retirement design §17.2: "Add CI guards against reintroducing name-keyed context recognition"): a small structure-lock test (in `tests/test_workflow_lisp_stdlib_form_migration.py` or a sibling) asserting `grep`-level absence of `BacklogDrainExpr`/`backlog_drain` branches under `orchestrator/workflow_lisp/` outside the sanctioned residue (form-registry record, stdlib-contract rows, `std/drain.orc` itself). This test outlives Phase 4's deletion of the `DESIGN_DELTA_G8_GREP_GUARDS` constants.
- [x] **Step 5: Commit** (final commit of the sequence): `git commit -m "Retire the backlog-drain intrinsic lowering paths"`

### Task 2.2: Registry reclassification + G8 evidence decision procedure

**Files:** `orchestrator/workflow_lisp/form_registry.py`; possibly `orchestrator/workflow_lisp/build_design_delta.py` + `orchestrator/workflow_lisp/migration_parity.py` (one owning constant each — see the decision procedure; `build.py` only compatibility-re-exports the moved build symbol); `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc` (export list, if the boundary form's export is removed).

Background: `build_design_delta.py`'s removed-heads check (`serialize_design_delta_g8_deletion_evidence`) passes a head in `DESIGN_DELTA_G8_REMOVED_REGISTRY_HEADS` = `("with-phase", "finalize-selected-item", "backlog-drain")` only when its spec is deleted (`get_form_spec(...) is None`), OR tagged `compatibility_route_only`, OR listed in `DESIGN_DELTA_G8_IMPORTED_ONLY_REGISTRY_HEADS` with `macro_bindable=True` (the `with-phase` precedent). `migration_parity._validated_design_delta_g8_deleted_rows` cross-checks the same constants. `with-phase` and `finalize-selected-item` are **out of scope** — they keep their current tags/handling.

- [x] **Step 1: Delete the `backlog-drain-callable-boundary` spec from `form_registry.py` outright.** It is not in the removed-heads constant, so no evidence-machinery interaction; its `std/drain.orc` export and macro-alias plumbing go with it (reviewed contract delta per the old plan's Task 7 Step 1).
- [x] **Step 2: Decide `backlog-drain`'s registry disposition by this rule:**
  - **Default (residue-precedent route):** reclassify the spec to mirror the current `review-revise-loop` `FormKind.STDLIB_EXTENSION` record: `kind=FormKind.STDLIB_EXTENSION`, `elaboration_route=None`, `macro_bindable=True`, drop the `compatibility_route_only` tag and the `remove_by` obligation. The parametric design sanctions exactly this residue ("registry entry, stdlib contract, output-contract shaping"). This route **requires** adding `"backlog-drain"` to `DESIGN_DELTA_G8_IMPORTED_ONLY_REGISTRY_HEADS` in both owning modules, `build_design_delta.py` and `migration_parity.py` — the `with-phase` "imported-only + macro-bindable" branch is the honest classification for a head that now reaches the compiler only via imported stdlib expansion.
  - **Alternative (full-deletion route):** delete the spec entirely — the check passes via `spec is None` with zero machinery changes — **only if** Step 3 proves nothing requires a registry record for a macro-bindable stdlib name (`review-revise-loop`'s existence, and the `_validate_form_specs` invariant pinning it, suggest the record is load-bearing for stdlib surfaces; verify, don't assume).
  - Record which route was taken and why in the Phase 2 Ledger. See Contradictions & Findings item 1 — this decision point is a known documentation/machinery conflict; flag it in the execution report either way.
- [x] **Step 3: Verify the evidence check under the chosen route:**
```bash
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
python -c "import json,glob,os; p=max(glob.glob('.orchestrate/build/*/g8_deletion_evidence.json'), key=os.path.getmtime); d=json.load(open(p)); print(d['status'], d['hook_surface_delta']['imported_only_registry_heads'])"
```
Expected: exit 0, `pass`. A `design_delta_g8_removed_registry_head_present` compile error means the disposition and the constants disagree — fix the classification, never weaken the check.
- [x] **Step 4: Commit:** `git add orchestrator/workflow_lisp/form_registry.py orchestrator/workflow_lisp/stdlib_modules/std/drain.orc <constants files if touched> && git commit -m "Reclassify backlog-drain registry head after intrinsic retirement"`

### Task 2.3: Phase-2 verification, residue audit, and final promotion evidence

- [x] **Step 1: Full suites:**
```bash
pytest tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_procedures.py tests/test_workflow_lisp_generic_stdlib_composition.py tests/test_workflow_lisp_build_artifacts.py tests/test_lisp_frontend_autonomous_drain_runtime.py -q
pytest tests/test_workflow_lisp_checkpoint_identity_comparison.py -v
```
Expected: at Phase-1 baselines; identity tests still pass (retirement must not perturb the generic route's identities).
- [x] **Step 2: Name-blindness check:** `grep -rn "backlog.drain\|backlog_drain\|BacklogDrain" orchestrator/workflow_lisp/ | grep -v stdlib_modules | grep -v README` → expected during the Phase-2/3 boundary: exactly three sanctioned true registry/contract residue rows (two in `form_registry.py`, one in `stdlib_contracts.py`) plus the 12 frozen later-Phase certification/parity/inventory references that still exist only to prove and then retire the Design Delta evidence lanes. Any active AST, elaboration, typecheck, lowering, WCC dispatch, or form-specific-specialization site is unfinished intrinsic retirement; a frozen later-Phase evidence reference is not such a site and must remain until its owning Phase-3/4 task deletes it.
- [x] **Step 3: Residue audit** (design: "Residue materially above that is a signal to stop and reassess against the per-form migration test rather than push through"): compare surviving lines against the review-loop precedent (registry entry, stdlib contract, output-contract shaping); record counts + the `line_count_delta`/`hook_surface_delta` from the fresh `g8_deletion_evidence.json` in the Phase 2 Ledger (§17.3: "Deletion evidence reports line-count and hook-surface reduction"). Materially more residue → STOP and escalate.
- [x] **Step 4: Final parity regeneration (the Gate P3 promotion evidence):** run the P2.5 parity command; record `non_regressive` and `promotion_eligibility` in the ledger.
- [x] **Step 5: Docs:** update `docs/capability_status_matrix.md` (backlog-drain: library-provided via `std/drain` generic; intrinsic: retired) and the two design docs' status notes (prereq 6 landed; G8 drain rows discharged). Commit: `Record intrinsic drain retirement evidence`.

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

- [x] **Step 1:** Extract the minimal parent-drain smoke (the `-k "smoke"` subset's compile-the-production-entry path) into `tests/test_workflow_lisp_design_delta_smoke.py`, reusing the feasibility module's loader helpers by import or by copy (prefer import while the module still exists; inline the helper when the module is deleted in Task 3.3).
- [x] **Step 2:** `pytest --collect-only tests/test_workflow_lisp_design_delta_smoke.py -q && pytest tests/test_workflow_lisp_design_delta_smoke.py -q` → PASS.
- [x] **Step 3:** Point the two `parity_targets.json` evidence-command refs at the new module; run the P2.5 parity command → exit 0.
- [x] **Step 4: Commit:** `git add tests/test_workflow_lisp_design_delta_smoke.py workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json && git commit -m "Re-home parent drain smoke outside the feasibility suite"`

### Task 3.2: Remove the `design_delta_parent_drain` parity target (promotion decision)

**Files:** `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`; regenerated `artifacts/work/review-parity-check/index.json`.

- [x] **Step 1:** Confirm Gate P3.3/P3.4 ledger entries exist (final non-regressive report + recorded promotion decision). The last `design_delta_parent_drain.json` report stays in `artifacts/work/review-parity-check/` as the historical promotion record — do not delete it.
- [x] **Step 2:** Remove the `design_delta_parent_drain` target object from `parity_targets.json` (leaving `cycle_guard_demo`, `design_plan_impl_stack`).
- [x] **Step 3:** `python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/review-parity-check --require-non-regressive` → exit 0; regenerated index lists only the two remaining families.
- [x] **Step 4:** Record that later Stage-6 YAML archival must use the retained historical promotion artifact plus fresh preserved compile/smoke/end-to-end checks; it must not recreate the retired `design_delta_parent_drain` parity target.
- [x] **Step 5: Commit:** `git add workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json artifacts/work/review-parity-check/index.json && git commit -m "Remove promoted design delta family from parity targets"`

### Task 3.3: Ordered bundle deletion

**Files (delete, in this order):**
1. The family-gated certification unit in `build_design_delta.py`: `DesignDeltaEvidence`, the `load_design_delta_*` / `_maybe_load_design_delta_*` loaders, census/bridge/retirement/boundary-authority gating, and the Design Delta report serializers; remove their public pipeline threading/call sites from `build.py` and their retired artifact-map entries/threading from `build_artifacts.py`. Preserve generic build pipeline/artifact/manifest kernels, `_reference_family_versioned_roots` / `_resolve_reference_family_evidence_paths` in `build.py` while they have a live caller, and the G8 serializer/constants/minimal payload plumbing until Phase 4.
2. Certification modules: `consumer_rendering_census.py` (kernel preserved per Step 3), `value_flow_census.py`, `rendering_cleanup.py`, `rendering_ergonomics.py`, `compatibility_bridges.py`, `transition_authoring.py`, `resume_plumbing_retirement.py`, `parent_drain_census_alignment.py`, `reference_family_conformance.py`.
3. Their suites: `tests/test_workflow_lisp_consumer_rendering_census.py` (unless the preserved kernel keeps assertions — split, don't drop coverage), `test_workflow_lisp_value_flow_census.py`, `test_workflow_lisp_rendering_cleanup.py`, `test_workflow_lisp_rendering_ergonomics.py`, `test_workflow_lisp_compatibility_bridges.py`, `test_workflow_lisp_transition_authoring.py`, `test_workflow_lisp_resume_plumbing_retirement.py`, `test_workflow_lisp_parent_drain_census_alignment.py`, `test_workflow_lisp_reference_family_conformance.py`, `test_workflow_lisp_design_delta_bridge_adapter_compatibility.py`, and (last, after Task 3.1 landed) `test_workflow_lisp_design_delta_drain_migration_feasibility.py`.
4. Certification manifests under `workflows/examples/inputs/workflow_lisp_migrations/`: the `design_delta_parent_drain.*` files **except** `{commands,providers,prompts}.json`, plus the dual-run vector files — each deleted only after Step 3's grep shows zero surviving loaders.

- [x] **Step 1:** Delete the family-specific region from `build_design_delta.py`, its orchestration/threading call sites in `build.py`, and its retired artifact-map entries/threading in `build_artifacts.py`; verify: production compile command (P2 form) exits 0 **without** reading any certification manifest (`strace`-free check: temporarily `mv` one manifest aside, compile, restore — expected: compile succeeds either way once the block is gone). Do not delete the generic `build_frontend_bundle` / `_emit` pipeline, generic `_write_build_artifacts` / `_build_manifest` machinery, or G8-only residue reserved for Phase 4.
- [x] **Step 2:** Delete modules + suites by explicit `git rm`, one commit per tier, verifying between tiers: `python -c "import orchestrator.workflow_lisp" && pytest tests/ -q --collect-only > /dev/null && echo OK`.
- [x] **Step 3 (preserve-list decision procedure):** before touching each preserve-list module: `grep -rn "<module>" orchestrator/ --include="*.py" | grep -v test` — enumerate live importers outside the deleted block. For `consumer_rendering_census.py`: keep exactly the schema kernel `observability_summaries.py` consumes (constant + payload shaping); move it into `observability_summaries.py` only if the remainder of the module is otherwise empty. For `phase_family_boundary.py`: no deletion of any symbol with a surviving importer (the runtime `loaded_bundle.py` use of `checked_design_delta_public_input_names` included).
- [x] **Step 4:** Delete manifests (tier 4) after `grep -rln "<filename>" orchestrator/ tests/ workflows/ | grep -v parity_targets` is empty per file.
- [x] **Step 5: Commits** (per tier): `Delete design delta certification gating in build`, `Delete certification census and retirement modules`, `Delete certification manifests and feasibility suite`.

### Task 3.4: Phase-3 verification

- [x] **Step 1:** Production compile (P2 form) → exit 0; `pytest tests/test_workflow_lisp_design_delta_smoke.py tests/test_workflow_lisp_drain_stdlib.py tests/test_lisp_frontend_autonomous_drain_runtime.py tests/test_workflow_lisp_build_artifacts.py -q` → PASS.
- [x] **Step 2:** `pytest tests/ -q --collect-only > /dev/null && echo COLLECT_OK` → `COLLECT_OK`; then full suite in tmux: `pytest -q` (compare against a pre-Phase-3 capture).
- [x] **Step 3:** Record in the Phase 3 Ledger: the state dirs `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R*` are no longer compile-evidence inputs (the Design Delta consumer of `_resolve_reference_family_evidence_paths` died with the block) but remain untouchable under this plan; YAML-twin deletion (`workflows/examples/lisp_frontend_design_delta_drain.yaml`) is deferred to procedure-first Stage 6 — note the pointer, do not delete here.
- [x] **Step 4:** Docs sync: `docs/capability_status_matrix.md` rows for the certification lane → retired; `docs/index.md`/`docs/design/README.md` routing entries for the retired lane updated. Commit: `Record certification bundle retirement`.

---

## Phase 4 — Design-delta lane strip from the parity machinery

**Gate: P4 (SATISFIED; all four conditions recorded and independently
reviewed).**

**Permanent-kernel boundary (NOT deleted, now or later):** `ParityTarget` loading, report/report-markdown/index generation, gate evaluation (`REPORT_SCHEMA_VERSION`/`INDEX_SCHEMA_VERSION`/`GATE_EVALUATION_SCHEMA_VERSION` machinery), `run_migration_parity`, the CLI command and its registration (`orchestrator/cli/commands/migration_parity.py`, `orchestrator/cli/main.py`), and everything `cycle_guard_demo` + `design_plan_impl_stack` exercise. The parity kernel is a permanent product surface, not migration debt.

### Task 4.1: Strip design-delta constants and lanes from `migration_parity.py`

**Files:** `orchestrator/workflow_lisp/migration_parity.py`; `tests/test_workflow_lisp_migration_parity.py` (expectation updates for removed lanes only).

**Deletion inventory (drafting-time anchors; re-locate by symbol name):**
- `DESIGN_DELTA_G8_DELETION_EVIDENCE_SCHEMA_VERSION`, `DESIGN_DELTA_G8_DELETED_MANIFEST_ROWS`, `DESIGN_DELTA_G8_RESOURCE_TRANSITION_HELPERS`, `DESIGN_DELTA_G8_REMOVED_REGISTRY_HEADS`, `DESIGN_DELTA_G8_IMPORTED_ONLY_REGISTRY_HEADS` (+ the Task-2.2 addition if the residue-precedent route was taken).
- The `g8_deletion_evidence` compile-artifact load and its family-specific threading through report/evidence-role evaluation.
- `_validated_design_delta_g8_deleted_rows` and its callers.
- The Design Delta fold inside `_resource_transition_parity_evidence`: G8-evidence threading, deleted-helper rows, and the `DESIGN_DELTA_G8_RESOURCE_TRANSITION_HELPERS` loop. Preserve `_runtime_audit_transition_parity_evidence` whenever a remaining target uses that generic core.

- [x] **Step 1 (decision procedure for the fold):** determine whether the remaining targets exercise the `resource_transition_parity` role: `python - <<'EOF'` reading `parity_targets.json` roles/config for `cycle_guard_demo` and `design_plan_impl_stack`, plus `grep -n "resource_transition_parity" orchestrator/workflow_lisp/migration_parity.py`. If the role is design-delta-only → delete `_resource_transition_parity_evidence` and its role wiring entirely. If shared → strip only the g8/deleted-helper logic, keeping the `_runtime_audit_transition_parity_evidence` core. Record which in the Phase 4 Ledger.
- [x] **Step 2:** Delete the inventory; `pyflakes orchestrator/workflow_lisp/migration_parity.py` → no new unused/undefined names.
- [x] **Step 3:** Update `tests/test_workflow_lisp_migration_parity.py`: remove/rewrite tests pinning the deleted lanes; keep every kernel test. `pytest --collect-only tests/test_workflow_lisp_migration_parity.py -q && pytest tests/test_workflow_lisp_migration_parity.py -q` → PASS.
- [x] **Step 4: Commit:** `git add orchestrator/workflow_lisp/migration_parity.py tests/test_workflow_lisp_migration_parity.py && git commit -m "Strip design delta lanes from migration parity"`

### Task 4.2: Strip the G8 serializer, artifact entry, and compatibility re-exports

**Files:** delete `orchestrator/workflow_lisp/build_design_delta.py`; modify `orchestrator/workflow_lisp/build_artifacts.py` and `orchestrator/workflow_lisp/build.py` only for the temporary G8 pipeline/import/re-export removal; modify `orchestrator/workflow_lisp/build_manifest_io.py` only if its stale module-dependency docstring requires synchronization; update `tests/test_workflow_lisp_build_artifacts.py` and `tests/test_workflow_lisp_stdlib_form_migration.py` for reviewed expectation/ownership changes.

**Deletion inventory (the temporary G8 artifact pipeline intentionally preserved through Task 4.1):** `serialize_design_delta_g8_deletion_evidence` and `DESIGN_DELTA_G8_REMOVED_MANIFEST_ROWS`, `DESIGN_DELTA_G8_REMOVED_SCRIPT_PATHS`, `DESIGN_DELTA_G8_REMOVED_PYTHON_SYMBOLS`, `DESIGN_DELTA_G8_REMOVED_REGISTRY_HEADS`, `DESIGN_DELTA_G8_IMPORTED_ONLY_REGISTRY_HEADS`, `DESIGN_DELTA_G8_RETAINED_BRIDGES`, `DESIGN_DELTA_G8_PRECONDITION_EVIDENCE_REFS`, `DESIGN_DELTA_G8_GREP_GUARDS`, and `DESIGN_DELTA_G8_VERIFICATION_COMMANDS` in `build_design_delta.py`; the `build_frontend_bundle` import/call and payload threading in `build.py`; the `g8_deletion_evidence` payload/entry in `_write_build_artifacts` and any now-empty payload plumbing in `build_artifacts.py`; compatibility imports/re-exports in `build.py`; and any orphaned `DESIGN_DELTA_PARENT_DRAIN_*` path constants proven unused by current symbol search. Removing this inventory leaves `build_design_delta.py` empty, so delete the module rather than retaining an empty compatibility shell.

- [x] **Step 1:** First run `rg -n "DESIGN_DELTA_G8|g8_deletion" orchestrator/workflow_lisp/build*.py` and confirm every build-module hit is confined to the temporary G8 artifact pipeline (serializer definition, `build_frontend_bundle` import/call, payload field/threading, artifact-map entry/emission, constants, or compatibility re-export). Then run the repo-global code search `rg -n "DESIGN_DELTA_G8|g8_deletion|serialize_design_delta_g8_deletion_evidence" orchestrator/ tests/` and classify every hit, including intentional tests and guards that protect the retirement boundary without consuming the temporary artifact. A consumer outside the temporary pipeline, or any surviving artifact gate or parity dependency, means the inventory is incomplete — STOP and resolve it before deletion. The temporary serializer caller is expected here and does not reopen Task 3.3.
- [x] **Step 2:** Delete from the owning modules, including `git rm orchestrator/workflow_lisp/build_design_delta.py`; run `pyflakes orchestrator/workflow_lisp/build.py orchestrator/workflow_lisp/build_artifacts.py` (plus `orchestrator/workflow_lisp/build_manifest_io.py` only if its docstring is updated) with no new unused/undefined names. Production compile (P2 form) → exit 0. `FrontendBuildResult.artifact_paths` plus the emitted manifest are authoritative for the current build; verify they omit G8 evidence, and assert physical `g8_deletion_evidence.json` absence only under a fresh temporary build root. Reused build roots are not pruned, so do not add a G8-specific cleanup path or a broad filesystem-absence gate. The Task 2.1 Step 4 CI guard now carries the §17 reintroduction protection.
- [x] **Step 3:** `pytest tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_stdlib_form_migration.py -q` → PASS (update tests pinning the artifact or temporary module ownership — reviewed deltas, noted in the commit message).
- [x] **Step 4: Commit:** `git add orchestrator/workflow_lisp/build.py orchestrator/workflow_lisp/build_artifacts.py orchestrator/workflow_lisp/build_manifest_io.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_stdlib_form_migration.py && git commit -m "Delete G8 deletion evidence serializer from build"` (omit `build_manifest_io.py` from `git add` if unchanged; the `git rm` is already staged).

### Task 4.3: Final verification and closeout

- [x] **Step 1:** `python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/review-parity-check --require-non-regressive` → exit 0 over the two remaining families.
- [x] **Step 2:** Full suite in tmux: `pytest -q`; production compile + a dry-run/launch through the promoted `.orc` primary as the orchestrator smoke. The retained YAML twin is not the primary launch path and remains untouched for Stage 6.
- [x] **Step 3:** Docs: capability matrix + design-doc status notes (G8 drain rows: deleted; parity lane: kernel-only). Commit: `Record parity lane strip and closeout evidence`.
- [x] **Step 4:** Report: per-phase line-count deltas, gate evidence summary, residue-vs-precedent comparison, and every flagged contradiction's disposition. Do not push; leave commits local for review.

---

## Contradictions & Findings (flagged at drafting, 2026-07-07 — do not resolve silently)

1. **Registry residue vs. G8 removed-heads check.** The parametric design sanctions a surviving registry entry as migration residue (review-loop precedent: `FormKind.STDLIB_EXTENSION`, `macro_bindable=True`, no compatibility tag), but `serialize_design_delta_g8_deletion_evidence` in `build_design_delta.py` fails the compile for any surviving `backlog-drain` spec lacking the `compatibility_route_only` tag and absent from `DESIGN_DELTA_G8_IMPORTED_ONLY_REGISTRY_HEADS`. The prior retirement-safety judgment's "no gate-machinery changes needed to land the deletion" holds only for the full-registry-deletion variant; the sanctioned-residue variant needs a two-constant edit (the `with-phase` imported-only precedent). Task 2.2 codifies the decision procedure; the executor must flag the chosen route.
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

#### Task 1.5 — three rounds (1.5 / 1.5a / 1.5b), PAUSED pending native-transportable-returns wave 1

**Status: Phase 1 PAUSED at Task 1.5 (user adjudication, 2026-07-10).** Three execution rounds
each ended pre-gate on newly discovered machinery gaps; THE GATE was never reached, no swap
commit exists, the frozen macro/call-site surfaces and the committed identity baselines are
untouched, and every round restored to a fully green baseline. Full evidence:
`.superpowers/sdd/task-1.5-report.md`, `task-1.5a-report.md`, `task-1.5b-report.md`.

**Landed and reviewed during the rounds (both stay):**
- `6e4b2c7c` — *Honor derived hidden phase context in procedure bodies* (sixth gap, typecheck
  layer: `hidden_context_omission_allowed` keyed exclusively off the active WORKFLOW signature;
  fix threads a proc-shaped signature gated on `eligible_private_context_source_param_names`).
  Review: spec PASS 7/7, quality Approved (2 Minor, carried).
- `9459395f` — *Honor proc-local hidden context during inline lowering* (eighth gap: the same
  eligibility check re-run at lowering with the enclosing caller's signature; fixed on BOTH
  inline lanes — `lowering/procedures.py` and `wcc/defunctionalize.py::_lower_wcc_procedure_call`
  must be edited in pairs for any context-threading change). Verified closed on the real
  production run-item body through the production loop lane. Review: spec PASS 7/7, quality
  Approved (3 Minor, carried). All canaries at baseline after both commits: identity 3,
  drain_stdlib 63, composition 15, procedures 132, feasibility 96 (93 + 3 new tests),
  fingerprint `24798cac21228fe6` unchanged, g8 `pass`.
- Also validated: the re-targeted let*-bound macro expansion itself compiles through the FROZEN
  caller keyword surface (1.5 report §5); the compiler-oracle `:effects` sets for all three
  hooks are recorded (1.5 report §3, 1.5a report §2.1) for the eventual re-run.

**The architectural blocker (1.5b report §4, complete one-round classification):** the generic
loop's `repeat_until` body lowers hook bodies on the FRONTEND expression lane, not WCC. Minimal
command-result hooks pass `_procedure_private_boundary_valid`/`_procedure_private_body_valid`
and get promoted to private `%…v1` workflows; the REAL production hook bodies do not qualify,
fall back to inline lowering inside the loop body, and hit frontend-lane restrictions the WCC
route long since lifted:
- **gap-7 residue** — `workflow_return_not_exportable`: the union-return exporter
  (`lowering/values.py::_record_expr_value_at_path`) requires a literal `record` expression at
  every intermediate node of every leaf path; record-typed fields populated by projection
  reference (`select-next-work-stdlib`'s `check_commands`) have no construction to move. The
  user-sanctioned inline-construction body delta was verified INSUFFICIENT (clears the first
  offender; the class fires one level deeper; a bounded widening experiment cleared it and then
  exposed G-B behind it — serial body-delta adjudication provably cannot converge).
- **G-B** — `workflow_boundary_type_invalid` ×6: cross-branch structured refs into the
  selector-call step unresolved + structured if/else below top level rejected (v2.2 limit).
- **G-C** — same-file call bindings inside loop-lane inline proc bodies must resolve to
  workflow inputs (`work_item.orc:318:14`, `route-blocked-implementation`).
- **G-D** — crash, not a diagnostic: `ValueError: pure boolean conditions require WCC
  pure-projection lowering` (`conditionals.py:94`) on `draft-design-gap-stdlib`'s frozen body.
Per-gap reproducers: `hook_conversion_probe.py {select|gap|run-item} [--pre-delta]`
(session scratchpad; reconstruction recipe in 1.5b report §3).

**Adjudications (user, 2026-07-10, all recorded in the SDD ledger):** sixth gap → extend the
typechecker (landed, `6e4b2c7c`); gaps 7+8 hybrid → gap-8 machinery fix (landed, `9459395f`) +
gap-7 body delta (verified insufficient, STOP honored, not committed); final → **PAUSE Phase 1
pending native-transportable-returns wave 1**
(`docs/plans/2026-07-10-workflow-lisp-native-transportable-returns-plan.md`), whose intake
receives requirement **R-G7** (1.5b report §6: union-variant returns must lower regardless of
payload authoring shape — let*-bound references, projection references, and inline
constructions are semantically equivalent pure values) plus the G-B/G-C/G-D lane findings,
since transportable returns through the generic loop lane is the actual production requirement.

**Resume condition:** native-transportable-returns wave 1 lands → re-run Task 1.5 from the
preserved swap patch (1.5a report §8 / scratchpad `task-1.5a-part2-swap-current.patch`, which
carries the oracle effect sets) under the standing identity protocol — the identity decision
(reproduce-identities vs reviewed remap) still WAITS for the real row-level diff. Caveat for
that future gate read (1.5b report F3): the earlier §5 promoted-bundle identity predictions
were derived from promotable minimal hooks and do NOT apply if real bodies lower inline —
read the eventual row table on its own evidence.

### Task 1.5 identity remap adjudication + landing record (2026-07-11)

**(a) Adjudications (user, 2026-07-11, two rulings).** First: THE GATE's row diff resolved as
**option (b) — remap route, evidence-based**: adopt the promoted `%…v1` identities produced by
the generic route; regenerate the design-delta identity baseline post-swap as a reviewed
migration step; record the zero-exposure persisted-state scan as the remap evidence (the remap
table is EMPTY); regenerate the transition-authoring allowlist manifest in the same reviewed
step. This lifted exactly two freezes:
`tests/baselines/drain_checkpoint_identity/design_delta_drain.json` (exemplar stays untouched)
and `design_delta_parent_drain.transition_authoring.json` (minimal, purpose-preserving).
Second (same day, after the census-gate cascade discovery below): **sequencing =
land-now-certify-in-1.6** — the swap+baseline+manifest commit lands with the P2-exit-0
requirement removed from the landing gate set; Task 1.6 greens the certification lane. Two
census sub-decisions are named and **explicitly deferred to Task 1.6 for census-level
treatment and user adjudication there, not decided here**: (1) regenerating
boundary-authority/value-flow evidence would place span-sensitive parametric digest hex into
PRODUCTION exact-match keys for the first time (checkout-location-sensitive P2 compile);
(2) the promoted `%work_item.…run-selected-item-stdlib.v1` is not a family-profile target
workflow, so the 22 boundary-authority rows keyed by the old run-item identity would LEAVE the
checked surface (deletion, not re-key) unless the profile's target set gains the promoted
identity.

**(b) Gate classification summary** (full row table: `.superpowers/sdd/task-1.5c-report.md` §5;
machine-readable diff preserved as scratchpad `gate_row_diff.json`): baseline 70 rows → live
100 rows; **38 unchanged / 0 changed-in-place / Class A: 30 vanished ↔ 30 appeared one-to-one
promoted re-key** (`%stdlib_adapters.…select-next-work-stdlib.v1`,
`%stdlib_adapters.…draft-design-gap-stdlib.v1`, `%work_item.…run-selected-item-stdlib.v1`) /
**Class B: 2 → 16 terminal restructure** (intrinsic terminal + intrinsic child replaced by
generic-loop rows + 14 settle-drain-terminal expansion rows) / **Class C: +16 bundle-set
expansion** (finalizer + phase-helper bundles now separately validated). Zero changed-in-place
rows = no identity drift on any untouched workflow.

**(c) Zero-exposure scan (the empty-remap evidence).** All 32 vanished checkpoint ids
extracted from `gate_row_diff.json` (scratchpad `vanished_ids.txt`). Persisted checkpoint
records live under `.orchestrate/runs/<run>/workflow_lisp/checkpoints/` as
`index/ckpt:<id>.json` + `records/ckpt:<id>/record:*.json`. Across ALL in-repo run state only
FIVE ckpt ids exist as persisted records (runs 20260615T010145Z-xl2f1b,
20260617T225133Z-mey25t): `12b0c09084888034c3b6643f`, `612454f9eb48b18f6709868d`,
`9e96d2cdde6051d0bdfabc50`, `d2553c2c3a954e553e791195`, `d9f8da44ae6b7bc2d61346d6` — zero
intersection with the vanished set (checked by filename AND content grep; reproduced fresh at
landing, 2026-07-11). External trees `/home/ollie/Documents/PtychoPINN/.orchestrate`,
`/home/ollie/Documents/ptychopinnpaper2/.orchestrate`,
`/home/ollie/Documents/EasySpin/.orchestrate`: zero `ckpt:*` checkpoint files, zero content
matches (reproduced fresh at landing). Frozen `state/` dirs: zero content matches. Only other
appearances of vanished ids: `logs/ExecuteImplementation.stderr` diagnostic echoes (not
resumable state) and the committed superseded build artifacts under
`.orchestrate/build/24798cac21228fe6/`. **No persisted checkpoint record anywhere is keyed by
a vanished identity — the remap table is empty.**

**(d) Digest span-sensitivity caveat.** Class B loop rows and Class C finalizer rows embed
`repr(TypeRef)`-derived parametric digests (`1d96b1db061e.7ae4672feb00`, `526af52fe5a8` in
this tree) that hash absolute-path SourceSpans: deterministic within a fixed tree (every
digest-embedded id reproduced byte-identically between the 1.5c gate run and the 1.5d landing
regeneration), NOT stable across checkouts/paths. Repo-root invocation is the stability
convention for the identity suite. Backlog item: make digest inputs span-insensitive —
**escalated** by the cascade discovery: extending the remap to boundary-authority/value-flow
manifests would move this sensitivity from test baselines into production compile gates
(deferred sub-decision (1) above).

**(e) Baseline + manifest regeneration record.**
- Baseline: regenerated with the identity suite's own `_identity_map_for` machinery from the
  repo root, serialization preserved (sorted keys, indent 2, trailing newline). Pre-write
  cross-check against the 1.5c live map passed exactly: 100 rows; 38 shared keys with
  byte-identical ids; 32 vanished and 62 appeared matching `gate_row_diff.json` by key AND id.
  Exemplar baseline byte-untouched (verified; the exemplar fixture imports nothing, so its
  `backlog-drain` head elaborates through the intrinsic route the swap does not touch).
- Manifest: ONE row added, nothing removed or altered —
  `low_level.imported_drain_terminal_effects` (`step_kind: resource_transition`,
  `step_id_contains: "std_drain_consume_drain_terminal_effects_"`), sanctioning the generic
  route's four imported settle-terminal `outcome` transitions authored in `std/drain.orc`;
  keyed on the stable stdlib helper name (no digest hex, no occurrence index), mirroring the
  existing `low_level.imported_finalize_selected_item` convention. Post-retarget live report:
  `status: pass`, 0 violations / 0 extra / 0 stale / 0 source-shape.
- **Correction to the 1.5c §4 transition-authoring mechanism (recorded so the ledger carries
  the corrected record):** the promoted re-key did NOT unmatch run-item's allowlist rows —
  those rows key on `module_name` + step-id substring, which survive promotion, and zero rows
  went stale. The actual `ordinary_body_violations` were the four imported
  `…std_drain_consume_drain_terminal_effects_1__match_terminal__{empty,completed,blocked,exhausted}__outcome`
  transitions misattributed to the high-level drain module because
  `_module_name_from_path` only recognizes design-delta library paths — not run-item row
  unmatching.

**(f) Production fingerprint + certification-lane state (Task 1.6 Step 4 input).**
**Certification lane red at frozen census gates pending Task 1.6; fingerprint
unchanged-as-stale at `24798cac21228fe6`** (no new fingerprint minted at this commit — the
post-swap P2 compile fail-closes before fingerprinting). Sequential unmasking order of the
census gates against the swapped route (each fail-closed gate masks every gate behind it;
this ordering is the certification input Task 1.6 Step 4 consumes):
1. transition-authoring — **green** (fixed by this landing's manifest row);
2. boundary-authority — **red, next blocker**: `workflow_boundary_authority_unclassified`;
   22 stale rows (all `lisp_frontend_design_delta/work_item::run-selected-item-stdlib`) +
   11 missing `lisp_frontend_design_delta/drain::drain` `managed_write_root` rows, 6 of them
   digest-embedded (`design_delta_parent_drain.boundary_authority.json`);
3. value-flow census — **red, proven by probe** (temporary mechanically regenerated registry,
   restored after): `value_flow_census_invalid`, missing + stale `compiled_boundary::…`
   checked rows (`design_delta_parent_drain.value_flow_census.json`);
4. not yet reached, grep-proven old-identity exposure:
   `design_delta_parent_drain.consumer_rendering_census.json`,
   `design_delta_parent_drain.compatibility_bridges.json`,
   `design_delta_parent_drain.family_profile.json`.
Landing-commit gate evidence (all fresh at `6a28ddd4`): identity suite **3 passed** against
the regenerated baseline; composition+procedures **151 passed** (16+135); drain_stdlib +
feasibility **36 failed / 124 passed** — failure identities exactly the 1.5c §4 classes with
the two `transition_authoring_invalid` flips now dying one gate later as
`workflow_boundary_authority_unclassified`
(`test_design_delta_parent_drain_build_and_execution_smoke_emit_default_resume_artifact`,
`test_design_delta_parent_drain_public_input_only_cli_dry_run_still_fails_without_runtime_owned_hidden_bindings`);
full inventory in `.superpowers/sdd/task-1.5d-report.md` §4.3. Consumer-suite contract deltas
(including `tests/test_workflow_lisp_transition_authoring.py`'s literal-manifest asserts)
remain Task 1.6 work. Landed as `6a28ddd4`
(`Re-target backlog-drain macro onto the generic proc`: `std/drain.orc` macro swap +
`stdlib_adapters.orc`/`work_item.orc` hook conversion + regenerated baseline + manifest row;
`drain.orc` call site byte-stable, diff empty).

### Task 1.6 obligation census + consumer-parity record (2026-07-12; historical round-1 state — superseded by the closure record below)

**(a) Certification-lane state.** All six fail-closed census gates are GREEN on the generic
route: P2 production compile exit 0, `diagnostic_count: 0`, **NEW production fingerprint
`c5cf03b2755308a3`** (replaces stale `24798cac21228fe6` as the certification anchor);
`g8_deletion_evidence.json` `"status": "pass"`. Landed as: manifest re-keys `4e1a4c6b`
(`Re-key drain evidence manifests onto generic-route identities`), consumer fixture
conversions `c8ed7ab7`, consumer test retargets `5059c9e8`. The Task 1.6 **Step 4 checkbox
stays UNCHECKED**: the four-suite lane is not fully green and the migration-parity gate is
red — every remaining red reduces to one of three characterized machinery-level parity
breaks (item (f)), not a contract delta; full evidence (including the parity-lane result)
in `.superpowers/sdd/task-1.6-report.md`.

**(b) Obligation census — where each drained obligation now lives (prereq-5 rule:
shared validation surfaces, not the generic body).** No obligation moved into the generic
body; no design conflict raised. Movements, all mechanically regenerated from compiled
generic-route evidence via each gate's own machinery (scratchpad scripts
`regen_boundary_authority_16.py` — the gate's
`build_design_delta_boundary_authority_expected_rows` — `regen_value_flow_census_16.py`,
`rekey_consumer_rendering_16.py`, each with abort guards limiting deletions to the
adjudicated identity; never hand-invented):
1. `design_delta_parent_drain.boundary_authority.json`: 143 → 132 rows. −22 stale rows
   (ruling 2, item (c)) + 11 regenerated `lisp_frontend_design_delta/drain::drain`
   `managed_write_root` rows (authority class `generated_internal` forced by the gate's
   leak rules): 6 generic-loop write roots (digest-embedded, ruling 3) + 5
   settle-terminal write roots.
2. `design_delta_parent_drain.value_flow_census.json`: 180 → 169 rows. −22/+11
   `compiled_boundary::…` checked rows mirroring (1); coverage `workflow_surfaces` drops
   the now-rowless `lisp_frontend_design_delta/work_item::run-selected-item-stdlib` and
   `std/drain::backlog-drain` (loader fail-closes on rowless surfaces); U0 row
   `std_drain.materialized.shared_drain_result_summary` re-keyed from the synthesized
   `std/drain::backlog-drain` child surface onto the parent
   `lisp_frontend_design_delta/drain::drain` surface (obligation relocation: the shared
   drain-summary timed view is now expressed by the settle-drain-terminal match-terminal
   effects on the parent).
3. `design_delta_parent_drain.consumer_rendering_census.json`: 65 → 64 rows. C0 row
   `c0.std_drain_materialized_shared_drain_result_summary` re-keyed with (2)'s U0 row
   (surface + `step_id_suffix` `__shared_drain_result__summary` →
   `__materialize_view__drain_summary`); C0 row
   `c0.work_item_summary_summary_path_compiled_boundary` DELETED as a forced ruling-2
   cascade (item (c)).
4. `design_delta_parent_drain.resume_plumbing_retirement.json`: `source_census.fingerprint`
   refreshed to the regenerated value-flow census sha256 (the gate cross-checks it).
5. transition-authoring: already landed in Task 1.5 (`low_level.imported_drain_terminal_effects`).
6. compatibility-bridges + family-profile manifests: NO changes needed — their gates pass
   against generic-route evidence unchanged (their `run-selected-item-stdlib` grep hits are
   module/step-substring keys that survive promotion). The family-profile target set was
   NOT extended to `%work_item.…v1` (ruling 2).

**(c) Ruling-2 deletion record (user-adjudicated verification narrowing; recorded, not
silently absorbed).** All 22 deleted boundary-authority rows keyed
`lisp_frontend_design_delta/work_item::run-selected-item-stdlib`: **16 managed_write_root**
(the run-item candidate's approved/blocked/exhausted lane write-root bundle paths), **5
runtime_context_input** (`item-ctx__{artifact-root,ledger,run__artifact-root,run__state-root,state-root}`),
**1 flattened_output** (`return__summary-path`). (The 1.5d §3 sub-count "17 managed_write_root"
summed to 23 and was off by one; the adjudicated and landed total is 22, verified 16/5/1
against `4e1a4c6b`.) Why: post-swap, `run-selected-item-stdlib` is a defproc hook promoted
to `%work_item.lisp_frontend_design_delta/work_item::run-selected-item-stdlib.v1`, which is
NOT a family-profile target workflow, so the gate no longer projects these rows and they
cannot be re-keyed — only deleted. **What is no longer authority-checked:** the promoted
run-item bundle's write-root set, its item-ctx context inputs (item-ctx is now a
caller-supplied proc parameter — public inputs on the promoted bundle, bound by the loop
body from the drain's own checked context), and its flattened summary-path output.
**Forced cascade (23rd row, consumer-rendering):** C0 row
`c0.work_item_summary_summary_path_compiled_boundary` referenced the deleted U0 row
`compiled_boundary::…run-selected-item-stdlib::return__summary-path` via `u0_row_id`; the
consumer-rendering gate fail-closes on dangling U0 references
(`consumer_rendering_census_row_stale`), and no re-key target exists (no flattened_output
row among the 11 regenerated). The exact-path item-summary durability obligation REMAINS
checked by the surviving bridge row `c0.work_item_summary_summary_path`
(`bridge_file`/`durable_bridge` on `lisp_frontend_design_delta/work_item::run-work-item`);
only the compiled-boundary inventory MIRROR — already `track_c_decision: BLOCKED` for
independent retirement — left the checked surface.

**(d) Ruling-3 digest acceptance + escalated standalone backlog item.** 6 of the 11
regenerated boundary rows and their value-flow mirrors embed span-sensitive digest keys
(`…proc_1d96b1db061e_7ae4672feb00…`,
`__wcc_effect_subject_{7c09dee08b30662c,90e3060fa0e568d9,9914652854f6db53}`), continuous
with the committed manifests' `_proc_96de13fa5abd`/`_proc_b1ad4a920aa2` practice. The
production compile is now checkout-location-sensitive for the first time (digests hash
absolute-path SourceSpans). **Standalone escalated backlog item: make digest inputs
span-insensitive** — explicitly NOT attempted in Task 1.6 per the ruling.

**(e) Contract deltas (old assertion → new assertion, why; every delta reviewed; no
negative fixture deleted).** Fixture conversions (`c8ed7ab7`): the defworkflow hooks in
`drain_stdlib_backlog_drain_{parent_terminal_reprojection,branch_local_terminal_contract_alignment,stdlib}.orc`
and `backlog_drain_hidden_compatibility_bridge_public_run_item_invalid.orc` converted to
`defproc` + `:effects ((uses-command …))` + `:lowering inline` per the production/minimal-
caller shape (the generic macro requires proc hooks); the
`design_delta_work_item_runtime/lisp_frontend_design_delta/{stdlib_adapters,work_item}.orc`
runtime mirror byte-synced to the post-swap library (the mirror-equality tests' own
contract). Test retargets (`5059c9e8`), by class:
- **Intrinsic-shape → generic lowered shape** (the plan's named class): the
  `std/drain::backlog-drain` child-workflow resolutions and `call == "std/drain::backlog-drain"`
  asserts in `test_workflow_lisp_drain_stdlib.py`
  (`compile_stage3_module_preserves_{parent_terminal_reprojection,branch_local_terminal_contract_alignment}…`,
  both `…preserves_imported_call_and_projection_provenance` tests) and
  `test_workflow_lisp_design_delta_drain_migration_feasibility.py`
  (`compiles_with_hidden_private_context`, `entrypoint_adopts_stdlib_owner_routes`,
  `stdlib_parent_delegation_audit…`, `preserves_runtime_native_transition_calls…`) now
  assert: no `std/drain::backlog-drain` in lowered names; exactly one `repeat_until` loop
  step (max_iterations preserved) lowered inline in the parent with origin-map provenance;
  projection/blocked-reason refs re-keyed from
  `…__stdlib-result__call_std/drain::backlog-drain.artifacts.…` to the digest-free
  `…__std/drain::settle-drain-terminal_1__std/drain::finalize-drain-terminal_1__match_terminal.artifacts.…`;
  the settle-terminal lane asserted in the parent (per-terminal-case
  `resource_transition` + `materialize_view` across EMPTY/COMPLETED/BLOCKED/EXHAUSTED —
  the generic replacement for `_assert_child_backlog_drain_uses_shared_terminal_lane`);
  hook calls asserted against the promoted `%…v1` identities (ruling 1).
- **Identity re-keys (rulings 1+4, mechanical):** bundle lookups
  `lisp_frontend_design_delta/work_item::run-selected-item-stdlib` →
  `%work_item.lisp_frontend_design_delta/work_item::run-selected-item-stdlib.v1`, with the
  compile route moved to the parent-drain entry (the proc's validated bundle exists only
  where the macro calls it): `selected_item_stdlib_{smoke_helper_matches…,keeps_run_state_bridge_private,direct_route_returns_canonical…}`.
  `smoke_helper` additionally asserts item-ctx is NOT a private runtime-context binding and
  the helper inputs equal the promoted bundle's public inputs exactly (the test-surface
  mirror of item (c)'s deleted runtime_context_input rows); `direct_route` executes the
  promoted bundle with unchanged bound inputs and unchanged expected outputs (runtime
  behavior identity evidence).
- **Source-text splits:** `"(defworkflow run-selected-item-stdlib"` split anchors →
  `"(defproc run-selected-item-stdlib"` (4 sites; text-mechanical).
- **Closure-only:** `run-selected-item-stdlib` expected in module-only lowered names →
  asserted ABSENT (a defproc lowers only where called; module-only compile of
  work_item.orc produces no standalone bundle for it).
- **Negative fixture (scenario preserved, differently reported):**
  `rejects_hidden_compatibility_bridge_public_run_item_fixture`: code
  `workflow_signature_mismatch` (message named `run_state_path`) →
  `proc_ref_signature_invalid` ("procedure ref argument arity does not match parametric
  signature", `form_path` pinned to the drain workflow); the smuggled extra
  `run_state_path` hook parameter remains impossible to author — the parametric proc-ref
  checker rejects it at the macro boundary but reports arity, not the parameter name.
- **Transition-authoring report test** (1.5d §9 F5): compiled-origin module set
  `{transitions, work_item}` → `+ lisp_frontend_design_delta/drain`; the literal
  single-row `drain::drain` equality → behavioral asserts: the `recorded_summary`
  transition row still matched by `low_level.record_drain_terminal_outcome`, plus exactly
  four imported settle-terminal rows matched by `low_level.imported_drain_terminal_effects`
  (`resource_transition`, std/drain.orc path, one per terminal arm), and nothing else on
  the drain workflow. `preserves_runtime_native_transition_calls…` adds
  `std_drain_consume_drain_terminal_effects` to its sanctioned imported-transition markers
  (mirroring that manifest row) and keeps asserting no OTHER raw drain-module transitions.

**(f) Consumer-parity evidence and the three machinery-level parity breaks (Step 4 gate
NOT passed; STOP-and-report per plan discipline; adjudication requested).** Fresh at
`5059c9e8`: census-alignment **10 passed**; autonomous-drain runtime **149 passed** (the
plan's end-to-end consumer evidence — GREEN); drain_stdlib **61 passed / 2 failed**;
feasibility **89 passed / 7 failed / 1 deselected**; transition-authoring 13 passed;
canaries at every commit: identity 3/3, composition+procedures 151. **Migration-parity is
RED / cannot complete at HEAD**: its own smoke evidence command fails on the break-3
smokes (harness logs: 4 failed / 2 passed), and its artifact-parity evidence child is
memory-unbounded (kernel-OOM-killed at 123 GB unattended; watchdog-aborted at 42.5 GB
monitored) — a second hotspot of the break-1 family; the on-disk
`design_delta_parent_drain.json` parity artifact remains the STALE 2026-07-07 run. Every
remaining red is one of three characterized generic-route parity breaks in UNFROZEN
shared machinery — none is a contract delta, none was fixable inside Task 1.6's freeze
set (details, quantification, and repro in `.superpowers/sdd/task-1.6-report.md`):
1. **CLI lint path-explosion** (`orchestrator/workflow/linting.py`
   `_lint_bundle_redundant_relpath_boundary_kinds` recurses `bundle.imports` with no
   visited-set; `orchestrator/cli/commands/run.py:399` materializes the list on EVERY
   `orchestrator run`): the generic route's bundle graph (68 bundles, 496 import edges)
   path-expands to 5,417,640 visits and exactly **66,781,802 warnings** (measured 4.97M
   warnings / 5.97 GB in 150 s before timeout) — `orchestrator run`/`--dry-run` of the
   production drain is effectively unbounded (OOM-scale). Blocks
   `test_design_delta_parent_drain_public_input_only_cli_dry_run_still_fails_without_runtime_owned_hidden_bindings`
   (deselected in the evidence runs above; it froze all prior four-suite runs at test #100).
2. **Loop-exhaustion state snapshot off-by-one** (`orchestrator/workflow/loops.py`
   `_exhaustion_frame_artifacts` recognizes only a single `*__body__state` step; the
   generic drain body updates state per match arm —
   `…__body__selected__continue__state`, `…__body__gap__continue__state` — so recognition
   silently falls back to iteration-ENTRY state): `:on-exhausted` reports the previous
   iteration's `progress_report_path` (`item-3-progress.md` where the intrinsic reported
   `item-4-progress.md`). Fails `test_parent_terminal_reprojection_executes_projected_parent_outputs[payload3]`
   and `test_branch_local_terminal_contract_alignment_executes_parent_outputs…[payload2]`.
3. **Terminal-transition `must_exist_target` on zero-write paths**: the generic route
   types `DrainOutcomeRequest.progress_report_path` as `WorkReport` (must-exist → runtime
   `missing_target` check via `orchestrator/workflow_lisp/contracts.py:1068` +
   `orchestrator/contracts/output_contract.py:939`), while the intrinsic terminal lane's
   `_drain_terminal_transition_config` used a bare path descriptor with no existence
   requirement; on EMPTY/selector-BLOCKED/gap-only/EXHAUSTED-without-writes terminals the
   progress report was never written (the seed materializes a path value, not a file; the
   arm's transition runs before its own materialize-view), so the run FAILS
   (`resource_transition_contract_invalid`/`missing_target`) where the intrinsic completed.
   Fails the 7 feasibility smokes
   (`smokes_selector_{done,blocked,design_gap}_path`, `smokes_blocked_recovery_path`,
   `design_gap_{converges_via_recorded_run_state,exhausts_without_recorded_progress}`,
   `imported_selector_ctx_carried_context_smoke`).
   All three touch frozen surfaces or shared machinery (`std/drain.orc` is byte-frozen;
   the executors/lint are cross-cutting) — per the plan's discipline, machinery fixes are
   raised, not landed unilaterally. Pre-existing out-of-lane fallout (not Task 1.6 lane,
   pre-dating its commits, 13 → 6 after the fixture conversions): 6 failures in
   `test_workflow_lisp_{route_readiness,stdlib_runtime_proof_boundary}.py`, same
   intrinsic-shape/registry classes, inventoried in the report §10.

### Task 1.6 fix-wave record (2026-07-12; historical pre-closure state — superseded by the closure record below)

**(a) Adjudications applied (user, 2026-07-12).** (1) PB1 = dedupe bundle-graph walks per
distinct bundle; (2) PB2 = fix the exhaustion-state recognizer + fail-fast on ambiguity;
(3) PB3 = retype `DrainOutcomeRequest.progress_report_path` to a non-must-exist path type
(seed materialization and shared-transition-machinery relaxation explicitly NOT
sanctioned); (4) the 6 out-of-lane failures stay a sibling task (untouched). Review
finding F-1 (terminal-lane helper weaker than the intrinsic helper) ruled MUST FIX.

**(b) Landed fixes (canaries identity 3/3 + composition/procedures 151 fresh at every
commit; fresh at base `29f74d40` as well, resolving the reviewer's mid-chain canary ⚠️):**
- `d16c8583` — F-1: `_assert_parent_uses_generic_shared_terminal_lane` now carries every
  intrinsic-helper check on the generic lane: exact per-case request-binding refs
  (computed from the loop step name, digest-free), exact recorded variants (EXHAUSTED
  records "BLOCKED"), `has_blocker` True/False per case, `run_state` absence, finalize
  `return__variant`/progress/blocker/items sourcing, no `return__run-state`, consume-lane
  hidden write-root inputs, `record-drain-outcome-audit.jsonl` generated path, and
  `state/drain-run-state.json` absence. Report §6's "equal or greater specificity" claim
  corrected (F-2's `resource_stdlib` misattribution also corrected).
- `0877dcf0` — PB2: `orchestrator/workflow/loops.py::_exhaustion_frame_artifacts` now
  prefers the executed `…__continue__state` arm update (the branched generic-drain shape)
  over the stale `…__body__state` iteration-entry binding, ignores skipped arms, keeps the
  single-snapshot shape working, and RAISES `LoopStateIntegrityError` on ambiguous
  executed candidates instead of silently reporting entry-frame state. TDD: new unit
  module `tests/test_workflow_loops_exhaustion_state.py` (7 tests; RED before the fix)
  plus the two adjudicated drain_stdlib exhaustion parametrizations RED→GREEN.
  Exhaustion now reports iteration N's progress path (intrinsic semantics restored).
- `2eb0e99a` — PB1: `orchestrator/workflow/linting.py` walk deduped per distinct bundle
  (identity = provenance path + workflow name, object-id fallback; diamond-import TDD
  test asserting warning multiplicity 1). Measured on the production drain bundle: lint
  66,781,802 warnings/unbounded → **404 warnings in 0.001 s**. Second hotspot pinned and
  fixed: `LoadedWorkflowBundle.__repr__` (dataclass auto-repr recursed imports once per
  path; any failing bundle-graph assertion allocated tens of GB — the 123 GB OOM victim)
  → bounded summary repr, TDD'd. The CLI dry-run test
  (`…public_input_only_cli_dry_run…`) now PASSES with nothing deselected.
- `0506e658` — parity-lane consumer fixes (the `artifact_parity` evidence selection,
  outside the four-suite lane, pre-existing post-swap by mechanism): hidden-compat
  fixtures converted to generic authorable shape (proc hooks cannot thread an unbound
  bridge — the omission mechanism is defworkflow-only, so the hidden bridge moved to the
  drain body's own omitted-binding call; scenario preserved: guard tests still fire
  `workflow_boundary_authority_unclassified` on the publicly-authored bridge);
  carried-context test re-keyed to `selector::select-next-work` (the adapter the hook
  calls); derived child-phase-binding test re-keyed to the promoted
  `%work_item.…run-selected-item-stdlib.v1` (source param `item-ctx`, run-anchor inputs
  added); transitions-report artifact test gains the drain module + promoted gap-drafter
  identity (D15/D8 class). `artifact_parity` selection: 94/94 green.

**(c) PB3 — STOPPED for re-adjudication; the sanctioned retype cannot compile.**
Attempted exactly as ruled (`WorkReportTarget` from std/phase — relpath, artifacts/work,
must-exist false — on `DrainOutcomeRequest.progress_report_path`); patch preserved
(scratchpad `pb3-retype-attempt.patch`), `std/drain.orc` restored byte-identical,
identity suite 3/3 after restore. Two blocking facts:
1. `type_refs_compatible` (type_env.py:961) requires identical `must_exist` on path
   types — there is no in-language conversion between `WorkReport` and any non-must-exist
   path type. Every partition of the outcome-record chain
   (terminal → request → state → result → summary) crosses a WorkReport↔Target seam, and
   pushing the seam outward reaches ONLY design-frozen vocabulary: the flagship
   `initial-progress-report WorkReport` parameter, the `:where` `summary-path WorkReport`
   clauses, and public `DrainResult`.
2. New mechanism evidence: the runtime failure fires at the transition STEP's RESULT
   extraction (`executor.py::_resource_transition_artifacts` validating the
   `output_bundle` field spec derived from `DrainOutcomeResult`), NOT at request
   validation (`coerce_transition_value` never checks existence). So even a compiling
   request-side retype would not fix the smokes; the result-side contract is the gate.
Re-adjudication options: (i) allow must-exist WIDENING in path-type compatibility
(one-directional, type-system change); (ii) relax `must_exist_target` on transition
result-extraction contracts (transition results record path VALUES; the step writes no
files — the intrinsic lane's descriptors deliberately had no existence requirement;
machinery change the prior ruling excluded, but chosen with the old request-side model);
(iii) an in-language relpath retype form; (iv) other.

**(d) Parity-evidence lane repaired + regenerated.** The 07-11/07-12 aborted parity runs
had left `artifacts/work/review-parity-check/logs/*` inconsistent with the checked
report (`evidence_refs.compile.stdout.sha256` mismatch), which failed the P2 compile's
reference-family conformance gate after the fact. Post-PB1 a full-target
`migration-parity` run (all three families; single-target runs fail closed on the
sibling reports' garbage-collected build manifests) completed and atomically rewrote
reports+logs+index: `cycle_guard_demo` and `design_plan_impl_stack` non-regressive;
`design_delta_parent_drain` remained REGRESSIVE for two independent reasons: its smoke
evidence retained 4 PB3 failures, and `parent_callable_compile` rejected the promoted
parent-owned loop because `_parent_loop_control_reasons` still required the pre-swap hook
aliases plus the retired `::project-selector-action.v1` alias (PB4). P2 compile green
again.

**(e) Step-4 state after the fix wave (fresh, nothing deselected).**
Four suites: **7 failed / 312 passed** — drain_stdlib 63/63, census-alignment 10/10,
autonomous-drain runtime 149/149, feasibility 90 passed / 7 failed, ALL seven the PB3
zero-write-terminal smokes; the CLI dry-run test passes. P2 compile exit 0,
`diagnostic_count: 0`, fingerprint **`c5cf03b2755308a3`** (unchanged — the PB3 retype did
not land, so no fingerprint change occurred), `g8_deletion_evidence` pass.
migration-parity: completes post-PB1; `--require-non-regressive` remains red for
`design_delta_parent_drain` pending both PB3 result-extraction correction and PB4 promoted
parent-loop recognition. The sanctioned final commit
(`Move drain obligations to shared surfaces with parity evidence`) remains WITHHELD until
the complete Step-4 gate goes green.

**(f) F-N1 correction and closure-patch status (2026-07-12).** The earlier claim that
migration parity was red solely from PB3 was a `stale_duplicate`: fresh review proved the
PB4 `parent_callable_compile` failure was structural and PB3-independent. PB3 landed as
`7812876c` (`Relax declared transition result extraction`); PB4 landed as `11f3b782`
(`Recognize promoted drain hook ownership`). Focused suites and both mandatory canaries
were green at each patch commit, but Task 1.6 Step 4 remains unchecked until the controller
runs and records the complete gate.

**(g) Task 1.6 closure record (2026-07-12).** The approved PB3 ruling removes
`must_exist_target` only from declared-transition result-extraction schemas, recursively
through supported collection containers; request validation, named path types, and all
non-transition contracts remain strict. The approved PB4 ruling recognizes the exact
promoted selector/run-item/gap-drafter hook trio as one parent-owned repeat route without
requiring the retired projection alias; split sibling repeats and the legacy selector
remain rejected. The nested-path and nested-repeat quality fixes are included in the
reviewed implementation range **`263a73fd..9bbc2290`**. Final review: **spec PASS** and
**quality APPROVED**, with no findings after the fix loop.

Fresh complete Step-4 evidence: the four suites passed **319 tests in 298.21s**, nothing
deselected. Production compile exited 0 with `diagnostic_count: 0`, unchanged fingerprint
**`c5cf03b2755308a3`**, and `g8_deletion_evidence` status `pass`. The required
single-target migration-parity command exited 0 with `reports_written: 1`,
`targets_processed: 1`, `non_regressive_targets: [design_delta_parent_drain]`,
`regressive_targets: []`, and `overall_pass: true`; the report records
`non_regressive: true`. Final canaries: identity **3 passed** and
composition+procedures **151 passed**. The committed checkpoint-identity baselines were
not regenerated or changed. Task 1.6 is complete; Step 4 is closed.

**(h) Task 1.6a F5 sibling contract-delta closure (2026-07-12).** The reviewed
implementation commits are `57c09c3e` (registry add), `106bd5e5` (registry order fix),
`19a36e2e` (runtime-proof retarget), `c14737d3` (non-vacuity fix), and `b497140b`
(diagnostic-policy pin); the final tested implementation tip was **`b497140b`**. The
implementation changed exactly `docs/workflow_lisp_route_readiness_registry.json` and
`tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py`. The prohibited production,
stdlib, fixture, frozen, parity, baseline, and generated-artifact diff was empty.

Fresh gate evidence: collect-only **15 collected**; the two affected modules **32 passed
in 4.04s**; the cited feasibility selector **1 passed in 0.99s**; the Task-1.6 four-suite
gate **319 passed in 386.25s**, with nothing deselected; checkpoint identity **3 passed in
2.04s**; generic composition plus procedures **151 passed in 2.13s**. The broad normal
baseline moved from exit 1 with **16 failed / 4268 passed / 11 skipped** to exit 1 with
**10 failed / 4281 passed / 11 skipped in 112.00s**. Its exact expected ten-row identity
set has SHA-256 `db2a609cfc7fc9910c1377a8d83962c3368b947067fbc3e712781883355c15bd`;
the broad log has SHA-256
`639eee2bbcd621dc134e9c9bd791642328feb4214cc51442f02ba3f7caaddb72`.

The normal promoted fixture is boundary-clean. An explicit in-memory low-level-boundary
variant retains the structured warning under default lint and is rejected under strict
lint for both shared-callable and dedicated-runtime-proof profiles. The nested-structure
allowance is load-bearing, generated owner metadata resolves correctly, and an authored
parent reference remains rejected even when both allowance collections name it. Final
review was **spec PASS with no findings** and **quality APPROVED after the fix loop**.
Task 1.6a is complete. Task 1.7 is next; Gate P2 remains open.

**(i) Task 1.7 evidence under review (2026-07-12; not completion).** Documentation
and routing synchronization landed in **`d883f5da`** (`Record backlog-drain generic
migration in design docs`). The verification below was executed fresh against that
current checkout; only the required workflow-input binding set was reconstructed from
historical run metadata.

The literal plan command,
`python -m orchestrator run workflows/examples/lisp_frontend_design_delta_drain.yaml
--dry-run`, exited **2** with `Workflow input binding failed`, as expected for this
input-required wrapper. The fresh replay used the exact `argv` binding set in
`.orchestrate/runs/20260706T161146Z-j82v71/monitor_process.json`; the run id remains
provenance, while this tracked command is the durable reproduction surface. It replaces
the recorded Python script executable with `python -m orchestrator`, omits only the
recorded `--stream-output`, adds `--dry-run`, and preserves every recorded
`--input NAME=VALUE` pair byte-for-byte:

```bash
python -m orchestrator run \
  workflows/examples/lisp_frontend_design_delta_drain.yaml \
  --dry-run \
  --input steering_path=docs/steering.md \
  --input target_design_path=docs/design/workflow_lisp_runtime_native_drain_authoring.md \
  --input baseline_design_path=docs/design/workflow_lisp_frontend_specification.md \
  --input post_wcc_inventory_path=docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/post_wcc_current_state_inventory.json \
  --input command_adapter_contract_path=docs/design/workflow_command_adapter_contract.md \
  --input backlog_root=docs/backlog/active \
  --input progress_ledger_path=state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R46/progress_ledger.json \
  --input drain_state_root=state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R48/drain \
  --input run_state_target_path=state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R46/drain/run_state.json \
  --input drain_summary_target_path=artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R48/drain-summary.json \
  --input artifact_work_root=artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R48 \
  --input artifact_checks_root=artifacts/checks/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R48 \
  --input artifact_review_root=artifacts/review/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R48 \
  --input architecture_index_root=docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R21/design-gaps \
  --input design_gap_draft_provider=codex \
  --input design_gap_draft_model=gpt-5.5 \
  --input design_gap_draft_effort=high \
  --input blocked_design_revision_provider=claude \
  --input blocked_design_revision_model=fable \
  --input blocked_design_revision_effort=high \
  --input selector_provider=claude \
  --input selector_model=fable \
  --input selector_effort=high \
  --input implementation_execute_provider=codex \
  --input implementation_review_provider=codex \
  --input done_review_provider=codex
```

That current-checkout replay exited **0** with `Workflow validation successful`; it also
reported the pre-existing `import-output-collision` warning for `drain_status` across
`import:done_review` and `import:work_item`.

Fresh tests: `pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py
-q` passed **97 tests in 162.92s**; the required parallel-form confirmation
`pytest -q -n 16 --dist=worksteal
tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py` passed **97 tests
in 36.69s**; and `pytest tests/test_workflow_lisp_verification_gate.py -q` passed
**20 tests in 7.49s**. Task 1.7 remains pending review. Gate P2 remains open, and this
entry makes no intrinsic-retirement or Phase 2 completion claim.

**(j) Task 1.7 closure and review record (2026-07-12).** Task 1.7 is complete.
This ledger entry is the durable review record for the contiguous reviewed range
**`d883f5da^..a3095f76`**, containing **`d883f5da`**, **`3b47838a`**, and
**`a3095f76`**. The spec-compliance reviewer returned final **PASS** after verifying
the routing, G8 boundary, integration-evidence mapping, and completion status. The
documentation-quality reviewer returned final **APPROVED** after verifying the
durability of the 58-token command reproduction and all 26 inputs, cross-document
routing consistency, and the absence of completion overclaim. Both results are from
the final re-review after **`a3095f76`**, with no findings. The integration and test
evidence is recorded in the preceding entry; this closure does not restate or broaden
those claims. **At this Task-1.7 review point, Gate P2 was the next open
selector** and still required its own fresh six-condition verification. This
historical entry makes no Gate P2 pass, intrinsic-retirement, or Phase 2
completion claim; entry (k) records the later gate result.

**(k) Gate P2 redundancy proof and reviewed closure (2026-07-12).** Gate P2 is
**SATISFIED** on reviewed HEAD
**`44560e99807fa5fbbbb3c5c4529ba2a906516249`**. All evidence below was produced
from that checkout under `tmp/gate-p2-44560e99/`; timestamps are UTC.

1. **Committed Phase 1:** ancestry verification found the closure commits for
   Tasks 1.1–1.7, including Task 1.6a: `c5d5e21b`, `971597f7`, `8e2f8fcc`,
   `49f221f1`, `6a28ddd4`, `74fa51e7`, `5bfd7ebe`, and `6e7eb1e7`
   (Task 1.7 implementation begins at `d883f5da`; routing cleanup ends at the
   reviewed HEAD). Condition 1 passed.
2. **Reviewed identity migration:**
   `pytest tests/test_workflow_lisp_checkpoint_identity_comparison.py -v`
   passed **3 tests in 2.01s** from `2026-07-13T00:08:09Z` through
   `00:08:11Z`; log SHA-256
   `57757302d838b5b54d464da96c4688f5aa87e4b73bad9eb958c7a67d238e7626`.
   This is not a literal-identity claim. Commit `6a28ddd4` and the adjudication
   ledger at `47481f95` record the reviewed identity migration; the
   zero-exposure scan found no vanished identity in persisted checkpoint state,
   so the persisted-record remap is empty.
3. **Consumer parity:** the exact Gate-P2 three-suite selector passed
   **309 tests in 329.08s** from `2026-07-13T00:08:22Z` through `00:13:51Z`,
   with nothing deselected; log SHA-256
   `8036a64095f75f13891902d80055e073108d032977d691a7c47fb15871b546c0`.
   This is the Task-1.1 aggregate baseline after the reviewed Phase-1 contract
   deltas.
4. **Generic-route certification:** the production compile ran from
   `2026-07-13T00:14:08Z` through `00:14:10Z` and exited 0 with zero
   diagnostics, `wcc_m4`, schema 2, and fingerprint `c5cf03b2755308a3`;
   compile-log SHA-256
   `3b21344aba8bac48ddae46222918ae404baa5053740971fc17d521d28492f97a`.
   The freshest certification artifact was regenerated at
   `.orchestrate/build/c5cf03b2755308a3/g8_deletion_evidence.json` at
   `2026-07-13T00:14:49.395567518Z`; it reports `status: pass` and has SHA-256
   `a3eefb08edf48118f2853efc42e45a9c0711c10cf5351aaea7fd436066230667`.
5. **Fresh migration parity:** the exact single-target command ran from
   `2026-07-13T00:14:46Z` through `00:20:54Z`, exited 0, wrote one report for
   one target, and reported `design_delta_parent_drain` non-regressive with
   overall gate pass and no regressions; CLI-log SHA-256
   `7f71f42a416a2bfde0f084880a67e414ed1500a3491a486b5d3b0b9937393a59`.
   The report was generated at `2026-07-13T00:20:54Z`, is contract-valid and
   evidence-complete, and all 14 evidence-reference hashes match. Its SHA-256
   is `06b9111b540c2f072f07ce61ace9f0b10703a2b0f69aca340f183e51ea496c39`;
   the passing gate-evaluation SHA-256 is
   `99f736dd240a58d9aa94bbbec547709621b25d7655b0f07e2246a4d6f9e154d7`.
6. **Intrinsic reachability:** the production-workflow grep returned no hits
   (expected grep exit 1); its empty log was written at
   `2026-07-13T00:20:54.657427228Z` and has SHA-256
   `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
   The independent fixture search found exactly three sanctioned hits under
   `tests/fixtures/`; its log was written at
   `2026-07-13T00:20:54.674427489Z` and has SHA-256
   `651b570f0e21223e174e409ef0f84d81f9116609a239fb1cce8f500d92468e9e`.

Independent final review agreed with the evidence boundary:
`/root/gate_p2_spec_review` returned **PASS overall. No findings.** and
`/root/gate_p2_quality_review` returned **APPROVED** after independently
verifying all 37 referenced parity hashes. Its one non-blocking consistency
note is intentionally not folded into this gate: the identity test's historical
name/comments still say “intrinsic route” even though `6a28ddd4` intentionally
regenerated the baseline for the generic route. The ledger wording above is the
authority for the gate claim; a later clean wording pass may rename that test
without reopening P2.

**Historical routing effect at the Gate P2 checkpoint:** Gate P2 closed Stage 2
and admitted Stage 3; the selector at that checkpoint was **Phase 2 Task 2.1**,
not typed result guidance. After Phase 2 Tasks 2.1–2.3 completed, the bounded
Design Delta promotion handoff became the next selector. That historical
routing statement is superseded by Phase 2 Ledger entry (e), which records the
handoff's later completion. The current selector is independent
all-four-condition Gate P3 verification and closure. Execute the drain plan's
remaining phases in gated order; typed result guidance remains the later
Stage-5/post-drain wave defined by the governing procedure-first sequence.

## Phase 2 Ledger

**(a) Task 2.1 deletion inventory and implementation candidate (2026-07-12).**
The candidate implementation range is **`b34e1cf4..b2f924dc`**: the
dependency-ordered deletion sequence through `18e90977`, followed by the
review-driven structure-guard and contract correction in `fd5aff6f` and the
nested-dispatch guard corrections in `07d90364` and `b2f924dc`. At this
candidate point Task 2.1 remained the current selector pending re-review, and
Task 2.2 had not started: the form-registry/export disposition and G8
imported-only classification decision remained untouched.

**Step-1 inventory diff.** The fresh inventory found every live deletion
cluster listed in the drafting table: WCC, lowering dispatch/facades, typecheck
dispatch and handler, elaboration/AST/traversal, procedure specialization, the
form-specific monomorphizer, and the intrinsic terminal/lowering modules.
`stage7_metrics.py` was absent as the re-anchor predicted. The
`backlog-drain-callable-boundary` search found no production or
`workflows/library/` hit; its source hits were the expected registry record, one
test module, and three fixtures. Additional name-bearing hits occurred in the
frozen Design Delta/parity and post-WCC inventory lanes plus transition
authoring. The `resource.py` context helpers were separately proved drain-only
and deleted as inventory fallout. The surviving form-keyed stdlib contract and
registry/evidence residue is reserved for Task 2.2 and later Phase-2
verification.

The selected-item summary helper had one definition, one resource-lane caller,
and one cross-import. Commit `3873c321` moved it unchanged into
`lowering/phase_resource.py`; the post-move search showed one local definition,
one resource caller, and no `phase_drain` import. The remaining deletion then
proceeded in dependency order through commits `6db9ab7c`, `d8bd4e29`,
`0a4a687a`, `0f2fda63`, `4743d3ea`, `53588875`, `c37c6ad5`, and
`18e90977`. Relative to `b34e1cf4`, the initial candidate changed 43 files,
with 239 insertions and 6,609 deletions, including deletion of
`drain_stdlib.py`, `lowering/drain_terminal.py`, and
`lowering/phase_drain.py`. Non-drain handlers and facade behavior were
preserved.

**Fixture disposition.** The ordinary callable-boundary fixture was deleted
because the canonical public-macro fixture covers the surviving generic route.
The bare intrinsic and intrinsic-`DrainCtx` fixtures were deleted with their
retired handlers while historical exemplar evidence remained untouched. The
rich-GAP fixture was renamed and converted to imported macro/procedure hooks,
and the non-record GAP fixture was converted likewise, preserving its generic
`parametric_constraint_unsatisfied` rejection. Stage-7 fixtures and tests whose
only contract was the removed name-keyed validator/lowerer were deleted; the
retained Stage-7 plan-gate/selected-item tests and generic production suites
cover surviving behavior.

**Verification and review boundary.** The initial endpoint collected 275
changed tests, passed the exact integration selector with **470 passed**, and
passed the post-amend focused selector with **55 passed**. The broad
work-stealing suite reported **4,236 passed, 8 failed, 11 skipped**; the eight
failure identities matched the established unrelated baseline. Review then
identified a structure-guard coverage gap and stale ownership/diagnostic
metadata in the form-keyed stdlib contract. Commit `fd5aff6f` adds contextual
AST checks for string-keyed comparisons, dictionaries, subscripts, and match
values while explicitly preserving the sanctioned registry/contract and frozen
evidence/inventory lanes. Its mutation proof first failed with zero detected
sites, then detected all three injected comparison/subscript/dictionary sites;
the corrected contract plus both guard tests pass together. Independent quality
review then found that tuple/set membership and mapping `.get(...)` dispatch
could bypass those direct-node checks. Commit `07d90364` extends the same
mutation proof to five sites and recursively checks comparison containers plus
mapping `get`/`pop`/`setdefault` keys. Review of that correction found it also
matched descriptive strings nested in arbitrary comparison calls and mapping
default values; `b2f924dc` narrows recursion to literal comparison-container
keys and mapping argument zero, with negative mutation cases preserving
descriptive/default text. The final endpoint and re-review are recorded below.
This candidate entry makes no Task 2.2 start, Task 2.3 residue/parity, or Gate
P3 claim.

**(b) Task 2.1 final verification, review, and closure (2026-07-12).** The final
implementation endpoint is **`c810f17a`**. The permanent guard's mutation
sequence proved both sides of its contextual contract: direct and
container-keyed comparison/dispatch recognition plus mapping key lookup are
rejected, while retired-looking descriptive call arguments and mapping default
values remain allowed. The final changed-test collection ran from
`2026-07-13T01:46:03Z` through `01:46:04Z` and collected **459 tests**; the
five focused guard/contract checks ran from `01:45:56Z` through `01:45:58Z`
and passed. The exact integration selector ran from `01:40:24Z` through
`01:41:24Z` and passed **471 tests**. The broad 16-worker work-stealing suite
ran from `01:41:32Z` through `01:43:20Z` and reported **4,237 passed, 8 failed,
11 skipped**; sorted failure identities matched the established unrelated
baseline exactly (`cmp` exit 0).

Independent final review returned **PASS** for specification conformance and
**APPROVED** for quality, with no remaining findings. The seven pre-existing
user-dirty paths were preserved exactly, and no Task 2.2-owned surface was
changed. **At that Task-2.1 closure checkpoint, Task 2.1 was complete and Phase
2 Task 2.2 was current.**

**(c) Task 2.2 registry reclassification, evidence limitation, and closure
(2026-07-12).** The reviewed implementation is commits **`6fc50c3f`**
(`Reclassify backlog-drain registry head after intrinsic retirement`) and
**`a92db6ec`** (`Guard retired backlog-drain callable export`). The decision
procedure selected the **residue-precedent route**: `review-revise-loop`
demonstrates that a public imported stdlib macro keeps a load-bearing
`FormKind.STDLIB_EXTENSION` record, and the parametric design explicitly
sanctions the same registry/stdlib-contract/output-shaping residue for
`backlog-drain`. The surviving record is therefore macro-bindable, has no
elaboration route, compatibility tag, or removal obligation, and reaches the
compiler only through imported stdlib expansion. The obsolete
`backlog-drain-callable-boundary` registry spec was deleted; fresh search found
no production `.orc` export or macro alias to remove. Both owning
`DESIGN_DELTA_G8_IMPORTED_ONLY_REGISTRY_HEADS` constants now contain exactly
`("with-phase", "backlog-drain")`; no other frozen build or parity machinery
changed. This is the recorded disposition of Contradictions & Findings item 1.

**TDD and focused verification.** The initial five-test RED run failed on all
five intended boundaries: old intrinsic classification, both old evidence
constants, old emitted evidence, and parity's failure to require the new
imported-only head. The corresponding GREEN run passed **5 tests**. The
registry/form/build/parity slice then passed **42 tests**. Specification review
found that the first candidate guarded only the Python registry and not the
`.orc` export boundary; `a92db6ec` added a behavioral import test that requests
`backlog-drain-callable-boundary` from `std/drain` and requires the sole
`module_export_missing` diagnostic. Its exact check passed **1 test**, and the
expanded focused slice passed **43 tests**. Changed-module collection was
successful (339 tests before the added export check; 340 after it).

**G8 evidence and the fail-closed current-checkout limitation.** Before the
implementation commit advanced `HEAD`, the exact production compile exited
**0** with zero diagnostics, lowering route `wcc_m4`, and fingerprint
`c5cf03b2755308a3`. Its freshly written
`.orchestrate/build/c5cf03b2755308a3/g8_deletion_evidence.json` reported
`"status": "pass"` and imported-only heads
`["with-phase", "backlog-drain"]`; the artifact SHA-256 was
`8b6e1bbe4f966cb2dacaa19022ae594ac22e09f5a202db68608005c88e83711c`.
After `HEAD` advanced, the same current-checkout compile correctly failed
closed with `reference_family_parity_report_invalid`: the checked parity
report's required G8 artifact hash no longer matches the newly emitted
artifact. The 16-worker four-module sweep reported **290 passed, 49 failed**;
independent review separated **48** failures intercepted by that stale checked
parity/G8 hash from one pre-existing `StopIteration` identity already recorded
in `tmp/f5-prechange-failure-identities.txt`. This entry deliberately does
**not** claim that the current compile or parity gate is green. Task 2.3 owns
the final parity regeneration and current-checkout promotion evidence; Task
2.2 does not mutate that artifact or weaken the fail-closed check.

Independent final re-review returned **PASS** for specification compliance and
**APPROVED** for quality after the export-boundary guard landed. The seven
pre-existing user-dirty paths remain preserved. **At that checkpoint Task 2.2
was complete and Phase 2 Task 2.3 was the selector.** No Task 2.3 work,
Phase-2 completion, or Gate P3 claim was made by entry (c); entry (d)
supersedes that historical routing state.

**(d) Task 2.3 verification, residue audit, and promotion-evidence closure
(2026-07-12).** Task 2.3 was executed at **`0b051f22`**. It completes Phase 2
without satisfying Gate P3: the report truthfully leaves primary promotion
ineligible, so the bounded Design Delta promotion handoff is the next selector.

**Artifact bootstrap and ordinary compile.** The checked parity report initially
contained the pre-Task-2.2 G8 hash, so current-checkout compilation correctly
failed closed before a new report could be produced. The executor used the
canonical guarded regeneration environment
(`ORCHESTRATOR_MIGRATION_PARITY_REGENERATING_FAMILY`,
`ORCHESTRATOR_MIGRATION_PARITY_REGENERATING_REPORT`,
`ORCHESTRATOR_MIGRATION_PARITY_REGENERATING_MARKDOWN`, and
`ORCHESTRATOR_MIGRATION_PARITY_REGENERATING_INDEX`) for one preliminary
single-target parity regeneration. This was a supported bootstrap-order
deviation, not a validation bypass. The ignored
`tmp/task23-artifact-bootstrap-pre-0b051f22/` snapshot contains a full copy of
the pre-bootstrap canonical parity-output tree—top-level report, Markdown view,
index, and gate artifacts plus all target logs—and a separate SHA-256 inventory
of that tree. A fresh unrestricted inventory found 51 files (42 target-log
files; `du -sh` reported `1.3M`). The compile build root was not copied. No
artifact was manually edited and no validation rule was weakened. The final
ordinary production compile,
with no regeneration environment, exited **0** with zero diagnostics, lowering
route `wcc_m4`, and fingerprint `c5cf03b2755308a3`; its log SHA-256 is
`500927780b1cfb06e493aedf22323f19a5d98afc4397c798f7830ac08d6cbafe`.

**Suites and name-blindness.** The exact six-suite command completed with
**611 passed and one failed** in 698.33 seconds. The sole failure is the
established
`test_design_delta_parent_call_work_item_boundary_projection_records_derived_work_item_phase_binding`
`StopIteration` identity; no new failure identity appeared. This is not an
all-green claim. The log SHA-256 is
`94701d3038db12c21373484fc7a1efcfad278b612348b54faab7b6e03099118a`.
The checkpoint-identity selector passed **3 tests** (log SHA-256
`290158fbdec31e2d3d9eff8245ec0ebce3741388103aba8097010835b057553d`).
The raw name search produced 15 lines: 12 frozen later-phase evidence/inventory
lines (including `transition_authoring.py`) and exactly three effective
sanctioned true-residue rows—two in `form_registry.py` and one in
`stdlib_contracts.py`—with zero unexpected intrinsic-lane lines. Its log
SHA-256 is
`a21302b211b99d0b2a2af6151c6d70233860791f26a97e1bfbccb3db6add747a`;
the permanent structure guard passed **2 tests** (log SHA-256
`313103f234941842aac08b7e638591433cdd0e4a9b3f72bff37bfe1b9a3bf00c`).

**Residue and G8 evidence.** The review-loop precedent has ten Python
name-bearing lines, compared with three true `backlog-drain` residue lines; the
residue is therefore not materially above the precedent. The fresh
`g8_deletion_evidence.json` reports `status: pass`, SHA-256
`8b6e1bbe4f966cb2dacaa19022ae594ac22e09f5a202db68608005c88e83711c`,
and `line_count_delta` counts of six removed manifest rows, five removed Python
symbols, three removed registry heads, and zero removed scripts. Its
`hook_surface_delta` records imported-only heads `with-phase` and
`backlog-drain`, removed heads `with-phase`, `finalize-selected-item`, and
`backlog-drain`, plus both `literal_executor_family_allowlist_removed` and
`name_lane_fallback_removed` as true.

**Final parity and promotion boundary.** The ordinary P2.5 single-target command
exited **0** with `overall_pass: true`, `non_regressive: true`, and all 17
evidence roles passing or contractually dry-run-waived. The command log SHA-256
is `2b5e6fc8452bac612a18271e44b4332115994413f140d95f38c1243f6672b9b0`.
The report was generated at `2026-07-13T02:49:19Z`; its
`promotion_eligibility.eligible_for_primary_surface` is **false** with the exact
blocked reason `parent-family candidate only; YAML primary replacement requires
strict promotable family evidence`. The report SHA-256 is
`c85aa06f7aac3e471e2b2b776d3d2e6abbac09ed374af827a073a73df30162a3`,
its Markdown view is
`f507d147d8e5b163c7a674e6b570a34bfbd06ff3d8cbd5c75014b1c9f8f5c289`,
the index is
`d0bf4babc9941583e688769f6a9423921f0e77d8471f6bf452789f0669861f3f`,
and the passing gate evaluation is
`628ea6f8f1fb86a9179cca7ee0304a0afb21e6d020e0ee9dc8f86e2c97a30d97`.

**Routing effect.** Phase 2 Tasks 2.1–2.3 and parametric prerequisite 6 are
complete. Gate P3 remains open because condition 4 still requires the handoff;
the recorded false promotion eligibility makes that boundary explicit. Execute
`docs/plans/2026-07-07-yaml-retirement-program.md` Task 5 for family 1 only
through registration, fresh strict parity, the `.orc` primary flip, and fresh
end-to-end evidence; stop before its archive bullet. Do not enter Phase 3 or
select typed result guidance yet.

**(e) Gate P3 condition-4 promotion handoff evidence (2026-07-12).** The
bounded YAML-retirement Task-5 family-1 handoff is committed in
**`2f80eb14`** (`Register Design Delta drain for primary promotion`) and
**`17d66bf6`** (`Promote Design Delta workflow routing to orc`). The first
commit changes the checked target and route-readiness entry from
parent-callable candidate metadata to the strict `promotion_eligible` /
`wcc_default` contract with no accepted differences. The second makes
`workflows/library/lisp_frontend_design_delta/drain.orc` the documented
primary while retaining the YAML twin as compatibility/reference material.

**Strict parity evidence.** The selected-family command was:

```bash
python -m orchestrator migration-parity \
  --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json \
  --output-root artifacts/work/review-parity-check \
  --target design_delta_parent_drain \
  --require-promotable
```

It exited **0** with `gate_mode: require_promotable`, `overall_pass: true`, one
report written, one target processed, and no regressive target. The canonical
report was generated at `2026-07-13T04:58:48Z`; its SHA-256 is
`fae2be568838d911a86a3b8862ebc573221a4e31d050d89acb797c82d87d41f9`,
the Markdown view is
`a53789c0b8b4e3474abc9b4c1244383013b4c2ae2ab6bf2d8ad699948b01367c`,
the index is
`c89a7b4a6b2548d18e58adb5f9ac1f213b1586d6c723ee665b39f779a0b3e714`,
and the passing gate evaluation is
`c1061d35a0152b6d0588aa9429f47fa72eb3b859da95d3a65029988f06d74cd6`.
The selected-family command log SHA-256 is
`96634aa2418c37e5c4e161079d88cc7b23b79d7749d86dec84ad98b491c932c0`.
All 17 evidence roles pass, including the executed dry-run role; all eight
required family roles pass. The canonical gate row is `report_valid:
true`, `evidence_complete: true`, `non_regressive: true`,
`eligible_for_primary_surface: true`, and `primary_surface: orc`. A fresh
post-smoke audit matched all **37** path/hash references in the report.

**Fresh compile and launch evidence.** The ordinary production compile was
run before and after the parent smoke with the checked provider, prompt, and
command manifests. Both runs exited **0**, emitted zero diagnostics, retained
the `wcc_m4` / schema-2 route and fingerprint `c5cf03b2755308a3`, and produced
byte-identical logs with SHA-256
`3b21344aba8bac48ddae46222918ae404baa5053740971fc17d521d28492f97a`.
The final build manifest SHA-256 is
`43772ef4ca53c187086e53c4546e8eed8f8a05a791d36b48a0d5a2db6ad7a9a1`;
the final `g8_deletion_evidence.json` reports `status: pass` and has SHA-256
`8b6e1bbe4f966cb2dacaa19022ae594ac22e09f5a202db68608005c88e83711c`.
The exact parent-smoke selector ran under 16-worker work stealing and passed
**6 tests in 8.14 seconds**; its log SHA-256 is
`55258d0e290a0daee2513645e577314e2f34f33b07deec3dc34045802760d6ba`.

The parity target no longer waives dry-run evidence. Its checked command runs
the `.orc` primary directly with the production entry and extern manifests,
then binds exactly the nine-entry `workflow_public_input_contracts` surface.
The first four inputs are `steering_path=docs/steering.md`,
`target_design_path=docs/design/workflow_lisp_runtime_native_drain_authoring.md`,
`baseline_design_path=docs/design/workflow_lisp_frontend_specification.md`, and
`architecture_targets__design_gap_id=workflow-lisp-family1-promotion`; the
remaining five use these existing, semantically aligned paths:

- `architecture_targets__architecture_path=docs/plans/2026-07-07-drain-migration-g8-retirement.md`
- `architecture_targets__work_item_context_path=artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R38/section14-parent-dry-run/work_item_context.md`
- `architecture_targets__check_commands_path=state/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/drain/iterations/4/design-gap-architect/check_commands.json`
- `architecture_targets__plan_target_path=docs/plans/2026-07-07-yaml-retirement-program.md`
- `existing_architecture_index_path=artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R38/section14-parent-dry-run/existing-architecture-index.md`

The canonical parity dry-run exited **0** in 2.737 seconds with status `pass`;
its stderr and stdout SHA-256 values are respectively
`f962f0ac0a523440c942d725668705e9d91087001a8b87f584132b1459a1063c`
and `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
An independent invocation of the same `.orc` primary also exited **0** with
`Workflow validation successful`. It emitted the existing redundant-relpath
and imported-output-collision lint categories; its complete log SHA-256 is
`ac85aff2358f87dac010a7fd575ce6400c7daeb61c24d579302ce9156464e693`.
No source or workflow file was changed to obtain either result.

**Archive boundary and routing effect.** A content diff against `17d66bf6`
was empty for `workflows/examples/lisp_frontend_design_delta_drain.yaml` and
all six currently present Design Delta `v214` library twins
(`design_gap_architect`, `done_review`, `implementation_phase`, `plan_phase`,
`selector`, and `work_item`). All seven files still exist. The YAML-retirement
Task-5 table's stale `+ 5` count was corrected to `+ 6`; no YAML or `v214`
archive step ran. Condition 4 is now recorded, but Gate P3 remains **pending**
until an independent command set verifies and closes all four conditions
together. The next selector is that Gate P3 verification, not Phase 3 and not
typed result guidance.

**(f) Gate P3 independent joint proof and reviewed closure (2026-07-12).** All
four Gate P3 conditions were re-run together at base HEAD
**`c82d150286248661bbfe2d8cb338715f47a02d36`** between
`2026-07-13T05:26:41Z` and `05:45:35Z`. The complete runner summary is
`tmp/gate-p3-c82d1502/summary.md`, SHA-256
`1e2b95052d6d7e3880f832cdc7330db85fb1ae3dd440520d4f119679889c0383`.
The initial audit step `15` returned 1 because its runner derived one path key
incorrectly; corrected audit `15b` and the final audit `22` returned 0 and
matched every reference. This was a transparent evidence-runner correction,
not an artifact or product-code repair.

1. **Deletion and name blindness:** ancestry checks found all Phase-2 closure
   commits through `049efd5d`. The exact search
   `grep -rn 'backlog.drain\|backlog_drain\|BacklogDrain' orchestrator/workflow_lisp/ | grep -v stdlib_modules | grep -v README`
   produced exactly 15 source lines: three sanctioned true registry/contract
   residue rows and 12 frozen later-Phase certification/parity/inventory
   references. It found zero AST, elaboration, typecheck, lowering, WCC
   dispatch, or form-specific-specialization sites. The five permanent
   structure/classification/export guards passed **5 tests**; their log
   SHA-256 is
   `b41f5289e05bfc39de949fd886e9345eff8395618de78c2ea86db03a0fadf16d`.
2. **Post-deletion certification:** the exact production command
   `python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json`
   exited 0 with zero diagnostics, `wcc_m4`, schema 2, and fingerprint
   `c5cf03b2755308a3`; compile-log SHA-256
   `3b21344aba8bac48ddae46222918ae404baa5053740971fc17d521d28492f97a`.
   The fresh G8 artifact reports `status: pass`, imported-only heads
   `with-phase` and `backlog-drain`, and SHA-256
   `8b6e1bbe4f966cb2dacaa19022ae594ac22e09f5a202db68608005c88e83711c`.
3. **Ordinary and strict parity:** the ordinary command
   `python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/review-parity-check --target design_delta_parent_drain --require-non-regressive`
   exited 0 with one selected non-regressive target and overall pass; log
   SHA-256
   `7f71f42a416a2bfde0f084880a67e414ed1500a3491a486b5d3b0b9937393a59`.
   The final strict command used the same arguments with
   `--require-promotable`; it exited 0 with no regressions and log SHA-256
   `96634aa2418c37e5c4e161079d88cc7b23b79d7749d86dec84ad98b491c932c0`.
   Final canonical SHA-256 values are report
   `b621cc139a5b828334a1b61b22f84e5d66341854515924d3734e7d70790ad880`,
   Markdown
   `5a274e9224e81a44e7515b32b92fb7f0fb503832011f2e38c9e76667a66de481`,
   index
   `bf045d816b215e547b9fcb99b66d028e4b45018ab3a57c33c35aefd328c00cd0`,
   and strict gate
   `7ca1cbcbce097577c65d57b5406d79148580a6b1f0756c81b3ed218fc9dd0173`.
   The final audit matched **47/47** path/hash references, **14/14** fresh
   command logs, and **15/15** fresh required build artifacts. The four narrow
   sibling fail-closed parity checks passed; log SHA-256
   `f299cb0ffb4580215f4b9643a2f31cdf09e6c57c46f955b1d1c6a26a088f6fb3`.
4. **Bounded promotion handoff:** the checked nine-public-input `.orc` dry-run
   command recorded in entry (e) was invoked independently and exited 0 with
   `Workflow validation successful`; log SHA-256
   `d47037ef49b7ab03223bf82b832c810f11c85cd013acdfe9e600cd43e8c48f44`.
   The exact smoke command
   `pytest -q -n 16 --dist=worksteal tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k design_delta_parent_drain_smokes`
   passed **6 tests in 7.94s**; log SHA-256
   `1b1e849eb086bb90f8024f802bdc477b2ed80d3ddeac03cb5f1fd12c951ce126`.
   The parent YAML twin and all six `v214` twins remain present and byte-equal
   to `17d66bf6`; no archive ran. No guarded regeneration environment was
   needed, and no canonical artifact was edited by hand.

Independent specification review returned **PASS** with no findings.
Independent evidence/quality review returned **APPROVED**, including the
artifact freshness, strict/ordinary parity distinction, name-blindness
classification, and archive boundary. There is no machine-readable task
selector for this prose-led plan; the routing authority is the synchronized
plan/index/status surface. Gate P3 is therefore **SATISFIED**. At this
historical Gate-P3 closure checkpoint, the sole current selection was **Phase
3 Task 3.1**; Phase 3 Ledger entry (a) supersedes that selector after recording
Task 3.1 completion. This closure did not start Task 3.1, Task 3.2+, Phase 4,
typed result guidance, or YAML archive.

## Phase 3 Ledger

### (a) Task 3.1 parent-drain smoke re-home and parity refresh (2026-07-13)

Task 3.1 landed as `c14b77d4` (`Re-home parent drain smoke outside the
feasibility suite`). The new
`tests/test_workflow_lisp_design_delta_smoke.py` compiles the checked-in
`lisp_frontend_design_delta/drain::drain` production entry through the existing
feasibility loader, asserts the schema-2 validated and lowered entry, and
records the Task-3.3 obligation to inline that minimal loader before the
feasibility module is deleted. A behavioral manifest test requires both
`smoke_or_integration` and `terminal_state_parity` to run this focused module
and rejects the old feasibility-module route. TDD evidence was one passing and
one failing test before the two manifest references moved, then **2 passed**;
fresh closure evidence collected two tests and passed both in 1.89 seconds.

Changing the whole parity manifest identity produced the expected fail-closed
bootstrap cycle. An ordinary production compile first exited 2 with
`reference_family_parity_report_invalid`. A first selected refresh then exited
2 because the unselected sibling reports still carried the old whole-manifest
SHA; an all-target attempt refreshed those sibling identities but truthfully
left Design Delta regressive because its unguarded dry-run still consumed the
stale report. Exactly one preliminary selected regeneration therefore used the
documented four path-matched
`ORCHESTRATOR_MIGRATION_PARITY_REGENERATING_*` variables for the whole command;
it exited 0 and wrote one non-regressive report. No validation rule or artifact
was edited by hand.

All subsequent commands were ordinary. The all-target refresh exited 0 with
three reports written and all three families non-regressive. The exact selected
P2.5 command exited 0 with one non-regressive Design Delta target, and the final
selected `--require-promotable` command exited 0 with `overall_pass: true`.
The final manifest SHA-256 is
`49a39c9ed86bde9c13f1b5f2e8426490cd1ba3646142b5ea3b3f1a32e24ded8d`;
canonical hashes are report
`26ba415a25334175430dcd98195fe97c500baef6fa26b02e6a221a9b499b86a4`,
Markdown
`f808a0ea319e9ad4ceb1471bff99c71b2c9bd60f99786498f783ffa29c3cd8ba`,
index
`f10ed53c3ad6583560ee5f6a9dc1bb395c011ed756ea6ec3845d5fb39858d476`,
and strict gate
`833874c61afd09e9c4f903a5c523824a4ff1e0a26d27937c8f5bcb30ae48e889`.
The final row is report-valid, evidence-complete, non-regressive,
promotion-eligible, and `primary_surface: orc`; independent review matched all
**77** declared path/hash references.

An independent unguarded production dry-run exited 0 and ended with
`Workflow validation successful`; its complete stderr log SHA-256 is
`6dbcc05db174b9425ea9d4c89ac6c1c391a17fe59aebb06e1aaf37b22287c77a`
(existing lint warnings only). The repository-required broad run
`pytest -q -n 16 --dist=worksteal` recorded **4,244 passed, 8 failed, 11
skipped** in 103.35 seconds; all eight failure identities exactly match the
latest Gate-P3 baseline, and the log SHA-256 is
`72d36cfcb3853b69027fd08b7f8db1e55836edbe60b9470fbb826869f97b7236`.

Independent specification review returned **PASS** with no findings.
Independent quality/evidence review returned **APPROVED**, with no Critical or
Important findings and one non-blocking static-typing precision note. The
seven pre-existing user-dirty paths remain preserved. Task 3.1 is complete;
the sole current selection is **Phase 3 Task 3.2: remove the
`design_delta_parent_drain` parity target (promotion decision)**. This closure does not start Task 3.2,
Task 3.3+, Phase 4, typed result guidance, or YAML archive.

### (b) Task 3.2 promoted parity-target retirement (2026-07-13)

Task 3.2 is complete through `de193187` (`Remove promoted design delta family
from parity targets`), `8e8cbbdc` (`Retire stale promoted target assertions`),
and `91546530` (`Preserve promoted design delta parity record`). The TDD RED
run added the retirement assertion and failed against the still-three-target
manifest; GREEN followed removal of the promoted target. Subsequent tests
retired now-stale target-specific assumptions while preserving the permanent
parity-kernel coverage. The final
`parity_targets.json` SHA-256 is
`5cda1470b0ae0afb743f67b7cf3cb32ef7bcdb6abfa97072cfc3caedd6305535`
and contains only `cycle_guard_demo` and `design_plan_impl_stack`.

The exact ordinary parity command exited 0, wrote two reports for two targets,
and classified both remaining families as non-regressive. The regenerated
index SHA-256 is
`c00a97a74ebfdddebe1b0d00d2fa7ab25b4ac6afa0b307e13237c93671b907ea`;
the gate-evaluation SHA-256 is
`481e196ae9ec97488d9e5ec3b70537ac5e635bf3f9a1234dab133598060cf078`;
the remaining report SHA-256 values are
`cdb401bd8a18ea7da464ddaf8723febf5d4a32e1ef58b39601056d628edc7317`
for `cycle_guard_demo` and
`76bc7e203a7b735f03e785289273737c638eb2173f75aed4b32942a0a8e463f3`
for `design_plan_impl_stack`. Independent evidence review matched all **34**
referenced paths and hashes with zero mismatches. The last historical Design
Delta promotion report is now tracked and remains byte-identical: JSON
SHA-256
`26ba415a25334175430dcd98195fe97c500baef6fa26b02e6a221a9b499b86a4`
and Markdown SHA-256
`f808a0ea319e9ad4ceb1471bff99c71b2c9bd60f99786498f783ffa29c3cd8ba`.
The regenerated index, gate, and command logs remain ignored runtime outputs
by design; their hashes are recorded here while the immutable historical
promotion reports are the durable Stage-6 decision evidence. The clean archive
guard passed, and no YAML or `v214` twin was archived.

Fresh module checks collected **101 tests**; the focused behavioral selector
passed **1 test**, and the full module passed **101 tests**. Independent
specification review returned **PASS** and independent quality/evidence review
returned **APPROVED**. The repository-required broad command
`pytest -q -n 16 --dist=worksteal` exited 1 with **4,183 passed, 61 failed, 11
skipped**. Review classified that initial result as eight established baseline
failures, 50 current-manifest-versus-immutable-promotion-report certification
failures rooted at
`reference_family_parity_report_invalid` (historical manifest SHA
`49a39c9ed86bde9c13f1b5f2e8426490cd1ba3646142b5ea3b3f1a32e24ded8d`
versus current SHA
`5cda1470b0ae0afb743f67b7cf3cb32ef7bcdb6abfa97072cfc3caedd6305535`),
and three stale tests that still selected the retired live target. The Task-3.2
corrective follow-up retargets those three tests to the surviving family or
the tracked historical report. That follow-up landed as `b7fe457c` (`Retire
remaining live parity target assumptions`); its focused selectors passed **3
tests**, and the route-readiness, focused-smoke, and migration-parity modules
passed **121 tests** under 16-worker work stealing. A fresh broad rerun then
reported **4,186 passed, 58 failed, 11 skipped**. Its failures are exactly the
eight established baseline identities plus the 50 planned certification
failures above; no live-target lookup failure remains. This is the intended
fail-closed boundary that Task 3.3 consumes.
The artifacts must not be weakened or rewritten; Task 3.3 removes the
still-live certification block that consumes this retired target identity.

Task 3.2 removed only the promoted parity target. It did not start Task 3.3,
delete any certification module or manifest, alter the retained historical
report, or archive the YAML family. The sole current selector is **Phase 3
Task 3.3: ordered bundle deletion**. Later Stage 6 must use the retained
historical promotion artifact together with fresh compile, smoke, and
end-to-end evidence on the then-current checkout; it must never recreate the
retired `design_delta_parent_drain` parity target.

### (c) Task 3.3 ordered certification-bundle deletion (2026-07-13)

Task 3.3 is complete through the ordered deletion commits `bdf87e61` (`Delete
design delta certification gating in build`), `21598d34` (`Delete
certification census and retirement modules`), and `0cbddb7b` (`Delete
certification manifests and feasibility suite`). Permanent post-WCC inventory
and route-readiness evidence was re-homed in `8112d61a` and `aafec532`.
Evidence-reference validation and its direct production-owner proofs were then
hardened through `f348cb71`, `43528925`, `36aa6c48`, `e044bc0d`, and
`3fce6617`. The generic build/artifact kernels, the live
`consumer_rendering_census.py` schema constant, every live
`phase_family_boundary.py` symbol, the parity kernel, the three ordinary
Design Delta compile-input externs, and the historical promotion report remain
preserved. All 13 retired certification-manifest filenames have zero live
references.

Independent review of the complete Task-3.3 implementation returned **SPEC
PASS** and **CODE QUALITY PASS**, with no open Critical or Important findings.
Fresh controller verification passed **542 focused tests**. The active
pointer-retirement backlog commands passed **14 tests** and **6 tests**, and
the checked dry-run exited 0. The route-readiness registry validated all
**54/54** surfaces and the post-WCC inventory validated all **14/14** surfaces
with no issues. The exact production compile exited 0 with fingerprint
`ad5a84000ed20a84`, emitted the surviving G8 artifact with pass status, and
reported only the seven known generic lint warnings exposed by removal of the
family-specific certification profile. Full collection found **3,918 tests**.

The repository-required broad command `pytest -q -n 16 --dist=worksteal`
reported **3,901 passed, 6 failed, 11 skipped**. The failure set is exactly the
six surviving established identities:

- `tests/test_workflow_output_contract_integration.py::test_provider_valid_output_bundle_overrides_raw_nonzero_exit`
- `tests/test_workflow_semantic_ir.py::test_semantic_ir_adds_typed_prompt_input_lineage_without_runtime_evidence`
- `tests/test_workflow_semantic_ir.py::test_executable_ir_artifact_omits_compile_time_and_frontend_internal_payload_keys`
- `tests/test_workflow_semantic_ir.py::test_compiled_bundle_semantic_ir_preserves_command_boundary_classification`
- `tests/test_provider_role_routing.py::test_design_delta_drain_defaults_route_work_to_codex_gpt54`
- `tests/test_neurips_steered_backlog_runtime.py::test_neurips_steered_backlog_runtime_drafts_gap_item_and_continues_without_relaunch`

The other two pre-Task-3.3 baseline failures were certification-only tests and
were intentionally deleted with their owners: the value-flow census assertion
left with `tests/test_workflow_lisp_value_flow_census.py`, while the Design
Delta derived work-item boundary-projection assertion left the retained build
artifact suite together with the certification projection it tested. Neither
is counted as a repaired failure or recreated after its owner contract was
deleted.

The seven pre-existing user-dirty paths remained byte-preserved and were never
staged:

- `docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md`
- `docs/plans/2026-07-01-workflow-audit-tier-fixes.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md`
- `state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt`
- `tests/test_workflow_non_progress_step_back_demo.py`
- `workflows/examples/non_progress_step_back_demo.yaml`
- `workflows/library/prompts/workflow_step_back/diagnose_non_progress.md`

Task 3.3 did not run Task 3.4 documentation synchronization, change the
certification capability-status/evidence rows, strip the Phase-4 parity lanes,
archive YAML, or begin Stage 5/Stage 6. The sole current selector is **Phase 3
Task 3.4: Phase-3 verification**; Task 3.4 has not started. Phase 4, Stage 5
typed result guidance, and Stage 6 YAML archive remain later work.

### (d) Task 3.4 Phase-3 verification (2026-07-13; independently reviewed and closed)

The exact P2-form production compile exited 0 on the promoted
`workflows/library/lisp_frontend_design_delta/drain.orc` entry with WCC M4,
lowering schema 2, fingerprint `ad5a84000ed20a84`, and the seven known generic
lint diagnostics. The surviving Phase-4-owned G8 deletion-evidence artifact
reports `status: pass`. The required focused selector passed **274 tests in
222.28s**. Full collection then found **3,918 tests in 1.77s**.

The exact serial `pytest -q` command ran to completion in the isolated tmux
session `drain-t34-full`, exited 1, and reported **3,901 passed, 6 failed, 11
skipped in 379.35s**. An exact sorted-set comparison matched all six failure
node IDs, with no additions or omissions, against the surviving established
Task-3.3 baseline:

- `tests/test_workflow_output_contract_integration.py::test_provider_valid_output_bundle_overrides_raw_nonzero_exit`
- `tests/test_workflow_semantic_ir.py::test_semantic_ir_adds_typed_prompt_input_lineage_without_runtime_evidence`
- `tests/test_workflow_semantic_ir.py::test_executable_ir_artifact_omits_compile_time_and_frontend_internal_payload_keys`
- `tests/test_workflow_semantic_ir.py::test_compiled_bundle_semantic_ir_preserves_command_boundary_classification`
- `tests/test_provider_role_routing.py::test_design_delta_drain_defaults_route_work_to_codex_gpt54`
- `tests/test_neurips_steered_backlog_runtime.py::test_neurips_steered_backlog_runtime_drafts_gap_item_and_continues_without_relaunch`

The compiler source contains no reference to
`_resolve_reference_family_evidence_paths`,
`_reference_family_versioned_roots`, or the
`LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R` prefix. The deleted Design Delta
consumer therefore cannot feed those historical run roots into compilation.
All **28** matching state directories remain present and untouched; their
cleanup is outside this plan. The retained
`workflows/examples/lisp_frontend_design_delta_drain.yaml` twin also remains
present and untouched. Procedure-first Stage 6 owns any later archive decision
and must use the preserved historical promotion report plus then-fresh compile,
smoke, and end-to-end evidence; it must not recreate the retired parity target
or certification bundle.

The Gate-P4 two-family evidence command exited 0 with overall pass, wrote two
reports, and classified `cycle_guard_demo` plus `design_plan_impl_stack` as
non-regressive. Fresh SHA-256 values are
`3989d7f1cf89c0011cd5adc4e0153133f54a4e700d0f13309949bfdacbef3ece`
for `index.json`,
`58d87c89b0dc9e67f8ea6656c30569ee11b32b03d7cd26208407e76e6d10e89e`
for `gate_evaluation.json`,
`35a41d87ab8b6a997e7c7703f183b9734a54806cd2f0a81526d814d3795a31d1`
for `cycle_guard_demo.json`, and
`106f9825dcc2a2046106c3212f03499bbb7263f4bbf2c63d6a95588e911f182c`
for `design_plan_impl_stack.json`. This is recorded for later Gate-P4 closure;
it does not begin Phase 4.

The documentation consistency pass classified the stale live references as
`stale_duplicate` plus `discoverability_gap`. It removed all active routing
references to the **32** Task-3.3-deleted paths, added an explicit retired
certification-bundle capability row, and routed current claims to direct owner
tests, route readiness, production compile/runtime evidence, and the preserved
historical promotion report. The broader audit found the remaining references
only in **63** design, plan, execution-ledger, and report provenance surfaces
outside the Task-3.4-owned active routing set; those surfaces were deliberately
preserved. JSON parsing passed, the
route-readiness CLI validated **54/54** surfaces, the post-WCC inventory CLI
validated **14/14** surfaces, and the focused routing/documentation modules
passed **59 tests** after the machine-readable `current selector is` grammar
was preserved.

Task 3.4 received **SPEC PASS** and **CODE QUALITY PASS** with no open findings.
Its exact compile and two-family parity evidence satisfy Gate P4 conditions 3
and 4; the committed Task 3.1–3.4 sequence and retired target/index state
satisfy conditions 1 and 2. Gates P3 and P4 are independently reviewed and
satisfied. The current selector is **Phase 4 Task 4.1: strip design-delta
constants and lanes from migration parity**. Task 4.1 has not started, and no
Task-4.1 deletion has begun. Stage 5 typed result guidance and Stage 6 YAML
archive remain later work.

## Phase 4 Ledger

### (a) Task 4.1 parity-lane strip (2026-07-13; independently reviewed and closed)

The target-role decision procedure found that neither `cycle_guard_demo` nor
`design_plan_impl_stack` declares `required_family_evidence_roles`,
`runtime_audit_artifacts`, or `family_evidence_artifacts`.
`resource_transition_parity` was therefore a Design-Delta-only role, so Task
4.1 deleted that evaluator and its wiring rather than retaining an unexercised
runtime-audit sub-lane. The permanent target-loading, report/markdown/index,
gate-evaluation, projection/view, CLI, and two-family parity kernel remains.

The implementation landed as `c258572c` (`Strip design delta lanes from
migration parity`) and its guard-hardening follow-up `8072ac8a` (`Harden parity
lane retirement guard`). The main deletion changed **431 production lines**
(4 insertions, 427 deletions), a **423-line net reduction**;
that commit records **1,150 deletions** overall while replacing the retired
family-specific expectations with kernel-preservation coverage. The TDD RED
absence check failed on all eight still-present retired symbols before the
deletion. GREEN verification passed **87 migration-parity tests**, **16
adjacent stdlib-form-migration tests**, **26 key-migration tests**, **58
route/readiness plus stdlib tests**, and **6 migration-parity CLI tests**. The
strict two-family parity command exited 0 with overall pass and classified both
remaining targets as non-regressive. After the quality follow-up, the focused
guard slice passed **11 tests** and the complete touched slice passed **111
tests**; `pyflakes` and `py_compile` were clean.

Independent review returned **SPEC PASS** and **CODE QUALITY PASS** with no
open findings. The consistency pass also resolved a Task-4.2
`semantic_conflict`: Task 3.3 intentionally retained the temporary G8 artifact
pipeline, including its `build_frontend_bundle` serializer caller, through
Phase 4. Task 4.2 therefore expects that bounded call/payload/emission path and
stops only for a consumer outside the temporary pipeline or a surviving
artifact gate or parity dependency. This correction changes no Task-4.2 scope
and makes no production/build edit.

Gates P3 and P4 are independently reviewed and satisfied. Task 4.1 is complete
and independently reviewed, with SPEC PASS and CODE QUALITY PASS. The current
selector is **Phase 4 Task 4.2: strip the G8 serializer**. Task 4.2 has not
started, and no Task-4.2 deletion has begun. Stage 5 typed result guidance and
Stage 6 YAML archive remain later work.

### (b) Task 4.2 G8 build-serializer retirement (2026-07-13; independently reviewed and closed)

The dependency-graph and repo-global inventory found no external consumer of
the temporary G8 artifact pipeline and no surviving artifact gate or parity
dependency. Task 4.2 therefore deleted the serializer, artifact entry, payload
threading, compatibility re-exports, orphaned path constants, and the now-empty
`build_design_delta.py` module. The deletion landed as `02156ffd` (`Delete G8
deletion evidence serializer from build`) with **10 insertions and 270
deletions**.

TDD began with one expected RED failure proving that a fresh build still
advertised the G8 artifact. GREEN verification passed **96 build-artifact plus
stdlib-form-migration tests**, **18 smoke tests**, and the **114-test combined
slice**. An independently run broader build/compile slice passed **180 tests**.
The exact P2 production compile exited 0 with fingerprint
`ad5a84000ed20a84`, WCC route `M4`, and schema version 2. Both authoritative
surfaces—`FrontendBuildResult.artifact_paths` and the emitted manifest—omit G8
evidence. A fresh temporary build root contains no
`g8_deletion_evidence.json`; a reused root may retain an unreferenced historical
orphan, which is accepted by the explicit non-pruning contract rather than
hidden behind a G8-specific cleanup path.

Independent review returned **SPEC PASS** and **CODE QUALITY PASS** with no
open findings. Gates P3 and P4 remain independently reviewed and satisfied.
Tasks 4.1 and 4.2 are complete and independently reviewed.

### (c) Task 4.3 final verification and Gate S3 closeout (2026-07-13)

Task 4.3 ran from base `3b6fb0a5bd765440435334768fc83527727a05c9`.
The exact strict two-family command exited **0**, wrote two reports, reported
`overall_pass: true`, and classified both `cycle_guard_demo` and
`design_plan_impl_stack` as evidence-complete and non-regressive. Fresh
SHA-256 values are
`77f8e6083996575571ad8810936a3385a8f6e59420191dc35898621d30e04b1c`
for `index.json`,
`e06def3a14b3f45f8865d4747a2a7ec0bbd4b55e53951ab55225799427518380`
for `gate_evaluation.json`,
`79beca943b68741827f6a3edecdcaf063a2a3e5a49bf7c83a32315ea9e41fc54`
for `cycle_guard_demo.json`, and
`51add85cf99acc5077ba9208d2588bb2e81174990f821456a6bf010266a3d048`
for `design_plan_impl_stack.json`. These generated kernel outputs remain
ignored runtime evidence; the tracked Design Delta historical report was not
regenerated or staged.

The exact serial `pytest -q` command first ran to completion in the isolated
tmux session `drain-t43-full`, exited **1**, and reported **3,905 passed, 6
failed, 11 skipped in 401.63s**. After the final routing-guard additions, the
same exact command ran again from the final tree in tmux session
`drain-t43-serial-final` and reported **3,909 passed, the same 6 failures, and
11 skipped in 404.33s**. The sorted failure set is exactly the six established
post-Task-3.4 baseline node IDs, with no additions or omissions:

- `tests/test_workflow_output_contract_integration.py::test_provider_valid_output_bundle_overrides_raw_nonzero_exit`
- `tests/test_workflow_semantic_ir.py::test_semantic_ir_adds_typed_prompt_input_lineage_without_runtime_evidence`
- `tests/test_workflow_semantic_ir.py::test_executable_ir_artifact_omits_compile_time_and_frontend_internal_payload_keys`
- `tests/test_workflow_semantic_ir.py::test_compiled_bundle_semantic_ir_preserves_command_boundary_classification`
- `tests/test_provider_role_routing.py::test_design_delta_drain_defaults_route_work_to_codex_gpt54`
- `tests/test_neurips_steered_backlog_runtime.py::test_neurips_steered_backlog_runtime_drafts_gap_item_and_continues_without_relaunch`

The exact P2-form production compile of the promoted
`lisp_frontend_design_delta/drain::drain` entry exited **0** with fingerprint
`ad5a84000ed20a84`, WCC route M4, lowering schema 2, zero error diagnostics,
and the seven established generic low-level-path warnings. Its CLI artifact
set has 14 paths including the manifest; the manifest advertises the 13
current products and no G8 evidence. The reused fingerprint directory still
contains an unadvertised historical `g8_deletion_evidence.json`, which is the
explicitly accepted non-pruning behavior, not a current artifact. The checked
promoted-`.orc` dry-run used the nine public inputs recorded by the boundary
projection, exited **0**, and ended with `Workflow validation successful`.
The compatibility YAML twin was neither launched nor modified.

Fresh closeout checks passed the route-readiness CLI at **54/54** surfaces and
the post-WCC inventory CLI at **14/14** surfaces. The focused
routing/readiness/post-WCC/build/stdlib/parity/Design-Delta-smoke slice passed
**279 tests** before the documentation update. The routing change was TDD'd:
the new Stage-4 selector/closeout guard first failed against the old Task-4.3
selector and then passed after all 13 live authorities moved together. The
final-tree focused slice passed **283 tests** after adding the hardened
closeout and conflicting-selector mutation cases. The repository-required
final-tree command `pytest -q -n 16 --dist=worksteal` reported **3,908 passed,
7 failed, and 11 skipped in 100.98s**. Its one additional identity,
`tests/test_adjudicated_provider_runtime.py::test_deadline_expiring_during_promotion_starts_no_terminal_ledger`,
failed because the one-second provider deadline expired before pending-ledger
materialization under parallel full-suite load. The exact node then passed all
**14** isolated serial reruns (0.34--0.38s each), and the final-tree serial
suite above restored exactly the established six-failure set. No runtime code
was changed or test weakened for this non-reproducing load-sensitive failure.

#### Per-phase textual line-count delta

LOC is Git textual additions/deletions between reviewed gate boundaries;
"production" means `orchestrator/` plus `workflows/library/`. The Phase-4 row
is the direct endpoint diff, not summed per-commit churn, and excludes the
seven user-dirty paths explicitly enumerated in the Phase-3 preservation
record and reconfirmed below.

| Phase boundary | Production additions/deletions (net) | Overall additions/deletions (net) |
| --- | ---: | ---: |
| Phase 1, `c5d5e21b^..b34e1cf4` | +1,154 / -142 (**+1,012**) | +14,348 / -1,317 (**+13,031**) |
| Phase 2, `b34e1cf4..9f22f333` | +36 / -3,791 (**-3,755**) | +1,344 / -6,794 (**-5,450**) |
| Phase 3, `9f22f333..0d73a6c3` | +620 / -12,568 (**-11,948**) | +22,293 / -45,482 (**-23,189**) |
| Phase 4 closeout, `0d73a6c3..Task-4.3 tree` | +7 / -624 (**-617**) | +594 / -1,537 (**-943**) |

Phase 1 includes the roadmap-authorized native-return wave-1 interlude, which
accounts for +546 production and +4,876 overall net; the other Phase-1
intervals account for +466 production net. Phase 3's additions include the
preserved 19,270-line historical promotion report. Through the Task-4.2 base,
the four phase snapshots are net **-15,308 production lines** and **-16,701
lines overall**. The large decrease is the intended deletion of replaced
special-case machinery: the Phase-2 intrinsic lane, the Phase-3 certification
modules/suites/manifests, and the Phase-4 Design-Delta-only parity/serializer
lanes. The generic drain route and permanent parity kernel remain.

#### Residue, contradictions, and preservation

The final residue comparison remains below the accepted precedent: the
review-loop precedent has ten Python name-bearing lines, while `backlog-drain`
has three true sanctioned residue rows (the macro-bindable registry record and
stdlib contract/output-shaping ownership). No compiler dispatch or
consumer-name branch was reintroduced. Every drafting-time contradiction has
an explicit disposition:

1. The registry conflict took the reviewed **residue-precedent route**:
   `backlog-drain` remains a macro-bindable `STDLIB_EXTENSION` like
   `review-revise-loop`; the callable-boundary record is absent. The temporary
   imported-only evidence constants used during retirement are now deleted.
2. The prior-plan sequencing conflict was resolved by explicit supersession:
   this plan governed, and the July-6 plan's intrinsic-retirement task stayed
   historical until Gate P2 admitted the Phase-2 deletion.
3. The G8 artifact's under-approximation was not treated as admission
   evidence. Gate P2's Phase-1 reachability/redundancy proof was the real gate;
   deletion occurred only after it passed, and the temporary artifact is now
   retired.
4. The exception-type correction remains accurate provenance: the old
   fingerprint mismatch raised `ValueError` with the same fail-closed effect.
   Its owning certification module was later deleted in Phase 3.
5. The concurrent-plan drift used the live inventory: `stage7_metrics.py` had
   already been deleted before this plan's execution and was not counted or
   deleted again in Phase 2.

All **28** protected historical
`state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R*` directories remain. The
YAML twin's Git blob remains `a3f4663d458248d20ef76a810bf917dd874376eb`,
identical to `HEAD`. The tracked historical Design Delta promotion report and
Markdown remain at SHA-256
`26ba415a25334175430dcd98195fe97c500baef6fa26b02e6a221a9b499b86a4`
and
`f808a0ea319e9ad4ceb1471bff99c71b2c9bd60f99786498f783ffa29c3cd8ba`.
The seven pre-existing user-dirty paths were byte-preserved and never staged.

**Gate S3 disposition: SATISFIED.** Production and fixture-only routes remain
distinguished, the permanent name-blindness and residue guards pass, and both
remaining parity targets pass after Design-Delta lane removal. Task 4.3 is
complete. Phase 4 is complete. Gate S3 is satisfied. The semantic-migration
freeze is lifted. The current selector is **Procedure-First Roadmap Stage 4:
Design The Broader Procedure-First Contract**. Stage 4 owns the frontend-spec
delta jointly resolving recommendations 9 and 11 plus the reviewed reusable
workflow-call classification inventory. Stage 5 typed result guidance and
Stage 6 YAML archive remain later work; neither starts in this closeout.
