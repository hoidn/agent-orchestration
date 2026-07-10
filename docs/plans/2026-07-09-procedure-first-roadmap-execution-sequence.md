# Procedure-First Roadmap Execution Sequence

Status: active work instructions
Created: 2026-07-09

## Objective

Sequence the remaining refactoring, parametric drain migration, broader
workflow-to-procedure transition, and YAML retirement work so that the
checkpoint-identity and migration-parity gates run against a stable compiler
and runtime substrate.

The target language model is:

- workflows remain durable public run and resume boundaries;
- typed procedures become the normal unit of internal reuse;
- provider, command, transition, publication, bridge, and child-workflow
  effects remain explicit and inspectable;
- no migration claim is made from compile success alone.

These are work-order instructions. They do not replace the semantic authority
of the Workflow Lisp frontend specification, the parametric type-system
design, or the runtime specifications.

## Governing Documents

- `docs/design/workflow_lisp_frontend_specification.md` owns the parent
  language contract.
- `docs/design/workflow_lisp_parametric_type_system.md` owns generic
  specialization, structural constraints, and the flagship drain migration
  contract.
- `docs/design/workflow_language_design_principles.md` owns the direction that
  procedures compose behavior while workflows remain explicit semantic
  boundaries.
- `docs/reports/2026-06-19-workflow-lisp-type-runtime-boundary-issues.md`
  recommendations 9 and 11 identify the still-design-gated typed-return and
  procedure-first generalization work.
- `docs/plans/2026-07-07-refactoring-dead-code-and-lowering-consolidation.md`
  supplies the original refactoring roadmap.
- The component execution plans named below govern their own tasks and checks.

If these work instructions disagree with a semantic design or normative spec,
the semantic design or spec wins. If an execution plan disagrees with this
ordering, update the plan's sequencing metadata without silently changing its
acceptance contract.

## Decision

Use bounded stabilization rather than either semantic-first execution or an
open-ended refactor-first program:

1. close only refactors that are already substantially executed;
2. freeze compiler/runtime structure long enough to execute the flagship
   parametric drain migration and its identity/parity gates;
3. use that migration as feasibility evidence for a broader procedure-first
   frontend design;
4. implement the generalization in bounded waves;
5. retire YAML authoring only after procedure-first `.orc` authoring is the
   proven production model.

This deliberately delays the drain migration until executor decomposition
reaches a clean gate. It avoids polishing additional unrelated surfaces before
semantic work begins.

## Current Plan Disposition

The executor must verify this table against the current checkout before acting;
plan checkboxes are not authoritative when commits and fresh checks disagree.

| Plan | Disposition in this sequence |
| --- | --- |
| `2026-07-07-refactoring-dead-code-and-lowering-consolidation.md` | Audit existing commits and run its final closeout; do not replay landed tasks. |
| `2026-07-07-lowering-fork-migration.md` | Completed through Task 9. Its final grep contains only drain-frozen residue; 386 lowering tests pass and the full-suite failure set matches the pre-plan baseline. |
| `2026-07-07-typecheck-family-completion.md` | Completed through its Task 7 closeout amendment. Structural/static gates are clean, 398 typecheck tests and 19 Design Delta smoke tests pass, and the full-suite failure set matches the pre-plan baseline. |
| `2026-07-07-build-module-split.md` | Completed through Task 6. Module/static gates are clean, 93 feasibility and 190 artifact tests pass, and the full-suite failure set matches the pre-plan baseline. |
| `2026-07-07-executor-decomposition.md` | Completed through Task 9. Its targeted executor surface and Design Delta smoke pass; the full-suite failure identities match the pre-Task-2 baseline. |
| `2026-07-08-boundary-report-followups.md` | Execute before the semantic freeze; it supplies terminology and negative-coverage evidence consumed by later design work. |
| `2026-07-07-drain-migration-g8-retirement.md` | Governs the parametric flagship migration and cleanup after re-anchoring to the refactored modules. |
| `2026-07-07-yaml-retirement-program.md` | Task 1 may inform later design. Its Design Delta family promotion is coordinated between drain Phases 2 and 3; other code-changing and promotion tasks wait until the procedure-first pilot is accepted. |

## Concrete Execution Sequence

### Stage 0: Make The Roadmap Durable And Re-anchor It

1. Audit the component plans' tracked status and review any pending plan changes
   using explicit paths.
2. Record which tasks are already represented by commits; do not mark them
   complete from inspection alone.
3. Replace stale file anchors in active plans with the current owning modules.
   In particular:
   - design-delta build/certification logic now lives primarily in
     `build_design_delta.py` rather than one monolithic `build.py` region;
   - drain/phase typechecking now has an owner module;
   - executor step-result helpers have already moved.
4. Run each component plan's narrow final checks before changing its status.
5. Establish a clean committed baseline for the files touched by Stages 1-3.

Gate S0:

- all plans used for execution are tracked;
- no active plan points at a function or module that no longer exists;
- unrelated user changes remain untouched;
- the baseline commit and fresh check results are recorded.

### Stage 1: Close The Active Refactoring Tranche

Execute in this order:

1. **Executor decomposition Task 9 closeout — completed 2026-07-09.** The
   corrected executor-surface suite passed, the full-suite failure identities
   matched the pre-Task-2 baseline, and the orchestrator smoke passed. Do not
   replay Tasks 2-8 or repeat this gate without a relevant code change.
2. **Lowering-fork closeout — completed 2026-07-09.** The final residue audit
   contains only the region frozen for drain retirement; the exact lowering
   selector and full-suite baseline comparison are recorded in the component plan.
3. **Typecheck-family closeout — completed 2026-07-09.** The omitted dispatch
   tail was resolved by the bounded Task 7 amendment; its structural, static,
   behavioral, smoke, and full-suite baseline gates are recorded in the component plan.
4. **Build-split closeout — completed 2026-07-09.** Task 6's full verification,
   import-cycle checks, compatibility re-export checks, and module-size report
   are recorded in the component plan. Large
   `build_design_delta.py` size is accepted temporarily because Stage 3 deletes
   the family-specific certification unit; do not start a second split first.
5. **Boundary-report follow-ups — active next, ownership-gated.** Tasks 1-3 are
   complete. Task 4 publication is paused while the report has uncommitted
   owner changes; do not start Task 5 from provisional discovery. Once the
   ownership gate clears, land the audit and applicable negative coverage.
   Recommendation 11 remains design-gated; this stage must not implement the
   broad transition.
6. Run the combined compiler/runtime baseline and one orchestrator smoke.

Gate S1:

- each refactor plan's final gate passes with fresh output;
- there is no live refactor editing `phase_drain.py`, `drain_terminal.py`, the
  design-delta certification lane, migration parity, executor state/resume, or
  typecheck owner modules;
- the full relevant baseline is recorded before the intrinsic-route snapshot.

After S1, impose a semantic-migration freeze: no discretionary compiler,
executor, build, typecheck, or lowering refactors until Stage 3 completes.

### Stage 2: Land The Parametric Drain Route

Re-anchor and execute `2026-07-07-drain-migration-g8-retirement.md` Phase 1:

1. Task 1.1 re-baseline and anchor verification.
2. Task 1.2 feasibility probes.
3. Task 1.3 intrinsic-route checkpoint-identity baselines.
4. Task 1.4 authored `backlog-drain-proc` and terminal settlement procedure,
   initially dormant.
5. Task 1.5 macro retarget plus checkpoint-identity comparison.
6. Task 1.6 consumer parity and obligation relocation.
7. Task 1.7 documentation and integration evidence.

Gate S2 is the drain plan's Gate P2. Do not proceed merely because the generic
procedure compiles. Required evidence includes:

- checkpoint identity is unchanged or an explicit reviewed remap exists;
- production consumers pass on the generic route;
- migration parity is non-regressive;
- certification evidence is green on the generic route;
- production reachability of the old intrinsic has ended.

Failure behavior:

- identity mismatch stops the route swap pending a reviewed identity decision;
- materially larger name-specific residue stops the migration-test claim;
- missing generic capability becomes a bounded type-system design gap, not a
  drain-name special case.

### Stage 3: Delete The Intrinsic And Close Its Evidence Lanes

Execute the drain plan's remaining phases in their gated order:

1. Phase 2: delete the intrinsic drain lowering, form-specific
   monomorphization, name-keyed validators, and compatibility registry heads.
2. Re-run parity and checkpoint evidence after deletion.
3. Coordinate YAML-retirement Task 5 family 1 only through the primary flip:
   register and prove the Design Delta `.orc` family, make it the primary
   production route, run fresh parity and end-to-end evidence, and record the
   promotion decision required by drain Gate P3. Stop before Task 5's archive
   bullet: retain the YAML twin and defer its deletion to Stage 6, as required
   by drain Phase 3 Task 3.4. Do not start other YAML family promotions here.
4. Phase 3: re-home the permanent smoke evidence and retire the
   design-delta-only certification bundle.
5. Phase 4: strip only the obsolete design-delta lanes from migration parity
   and build serialization while preserving the reusable parity kernel.
6. Update the parametric design, capability matrix, and documentation routing
   to distinguish the landed generic substrate from any still-future language
   generalization.

Gate S3:

- no production or fixture-only path is mistaken for the generic route;
- name-blindness and residue audits pass;
- remaining parity targets pass after design-delta lane removal;
- the semantic-migration freeze may lift only after this gate.

### Stage 4: Design The Broader Procedure-First Contract

Stage 4 may begin as documentation work after S2, while Stage 3 code cleanup is
finishing, but implementation cannot begin until S3.

Draft one frontend-spec delta that jointly resolves report recommendations 9
and 11:

1. workflows are public/resumable execution boundaries, not the default reuse
   unit;
2. pure helpers and effectful procedures share typed return semantics, while
   effect and resumability obligations remain explicit;
3. procedures may compose supported effect boundaries without becoming runtime
   procedure values or runtime closures;
4. public workflow outputs, artifacts, source maps, checkpoint identity, and
   runtime-projected contracts remain preserved;
5. the workflow-to-procedure migration test and non-candidate rules are
   explicit.

Required feasibility evidence:

- the landed `backlog-drain-proc` route;
- at least one ordinary non-drain candidate demonstrating that the proposed
  contract is not drain-specific;
- a negative case that must remain a workflow because it owns a public run,
  resume, publication, or external invocation boundary.

Then inventory current reusable workflow calls and classify each as:

- `public-boundary`: stays a workflow;
- `procedure-candidate`: eligible for migration;
- `effect-adapter`: migrate only after a named substrate gap lands;
- `legacy-retire`: delete rather than translate.

Gate S4:

- the frontend-spec delta is accepted;
- the inventory is reviewed;
- no production implementation starts from the diagnostic report alone;
- separate implementation plans exist for substrate changes, the pilot, and
  migration waves when those scopes are independently testable.

### Stage 5: Implement Procedure-First Reuse In Waves

Execute only accepted plans, in this order:

1. **Substrate wave.** Land only type, return, effect, lowering, source-map, or
   runtime-contract capabilities proven missing by Stage 4. Reuse the shared
   parametric specialization pipeline; do not add consumer-name branches.
2. **Pilot wave.** Convert a small non-public workflow family with real effects
   and typed returns. Preserve a public workflow wrapper only where an external
   run/resume boundary is required.
3. **Library/stdlib wave.** Convert reusable internal families with the same
   classification and parity gates.
4. **Production-family wave.** Convert eligible internal reuse only after
   output, artifact, effect, resume, and checkpoint parity is computed.
5. **Compatibility retirement.** Delete workflow-as-function shims only after
   the last consumer has migrated and negative coverage proves public workflow
   boundaries remain intact.

Every wave must pass:

- targeted type/lowering/runtime tests;
- source-map and diagnostic coverage;
- checkpoint/resume evidence when persisted identities are affected;
- computed migration parity for production consumers;
- one end-to-end orchestrator usage check.

### Stage 6: Resume YAML Retirement

Use the procedure-first model as the target authoring architecture:

1. Refresh or create the YAML-to-`.orc` language-gap list.
2. Rebase the YAML retirement plan against the post-procedure inventory.
3. Archive the already-demoted Design Delta YAML twin only after confirming
   the recorded Stage-3 promotion/parity artifact remains the historical
   decision evidence and the `.orc` primary still passes its preserved compile,
   smoke, and end-to-end checks on the post-procedure checkout. Do not require
   the retired `design_delta_parent_drain` parity target to be recreated.
4. Execute dashboard typed-surface and loader-validation separation work.
5. Continue with families after the already-promoted Design Delta family, one
   at a time through the retained parity kernel.
6. Deprecate YAML only after a real `.orc` production primary exists.
7. Delete YAML families and finally the user-facing YAML frontend only when
   the gap list is empty or explicitly waived and all production families are
   promoted.

Do not port a YAML family into a reusable `.orc` workflow when Stage 4
classifies that unit as a procedure candidate.

## Concurrency Rules

- Stages 0-1 use serial commits in the shared checkout. Their broad test suites
  and structural moves must not race each other.
- Stage 2 is exclusive with executor, typecheck, lowering, build, and parity
  refactors.
- After S2, Stage 4 documentation/inventory work may overlap Stage 3 code
  cleanup because it must not edit the frozen migration implementation.
- Stage 5 implementation and Stage 6 code changes are serial at shared
  validation/lowering/runtime boundaries. Independent documentation or estate
  inventory may proceed separately.

## Verification Ladder

Use the narrowest owning checks first, then advance only at explicit gates:

1. task-local unit/structural checks;
2. component-plan integration suites;
3. Workflow Lisp build-artifact and consumer feasibility suites;
4. checkpoint identity and migration-parity evidence;
5. end-to-end orchestrator smoke;
6. broad suite at tranche closeout.

Fresh output is required. A green check from before a route swap, module move,
or retirement deletion is not evidence for the later state.

## Completion Criteria

This roadmap sequence is complete when:

- the active refactoring plans are closed with fresh evidence;
- generic parametric drain composition is the only production route and the
  intrinsic/certification residue is retired;
- the frontend contract makes procedures the normal internal reuse unit while
  retaining workflows as public/resumable boundaries;
- selected real families have migrated with computed parity evidence;
- compatibility workflow-as-function paths have explicit remaining owners or
  are retired;
- YAML retirement proceeds against the procedure-first model rather than
  recreating reusable workflow wrappers.

## Stop And Revise Conditions

Revisit this sequence if:

- executor closeout changes checkpoint or resume behavior rather than merely
  structure;
- drain migration requires a consumer-name special case;
- the broad contract cannot cover a non-drain candidate without runtime
  procedure values or hidden effects;
- procedure conversion changes a public run/resume identity without an
  explicit migration contract;
- YAML promotion would force the repository back toward workflows as the
  internal reuse unit.
