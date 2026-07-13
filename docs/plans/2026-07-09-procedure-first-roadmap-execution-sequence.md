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
| `2026-07-08-boundary-report-followups.md` | Completed through Task 6 and its final gate. Case 5 now has production runtime/source-map attribution evidence. |
| `2026-07-09-runtime-union-field-lineage-plan.md` | Completed through Task 6. The post-fix full suite retains exactly the six recorded baseline failures. |
| `2026-07-07-drain-migration-g8-retirement.md` | Phase 1 Tasks 1.1–1.7, Phase 2 Tasks 2.1–2.3, Phase 3 Tasks 3.1–3.4, and Phase 4 Tasks 4.1–4.2 are complete. Gates P3 and P4 are independently reviewed and satisfied. The bounded Design Delta promotion handoff is recorded without archive, its historical parity artifact remains tracked after target retirement, and the ordered certification bundle plus temporary G8 build serializer are deleted. Task 4.1 is complete and independently reviewed, with SPEC PASS and CODE QUALITY PASS. Task 4.2 is complete and independently reviewed, with SPEC PASS and CODE QUALITY PASS. The current selector is Phase 4 Task 4.3: final verification and closeout. Task 4.3 has not started. Final verification and final closeout have not begun. Stage 5 typed result guidance and Stage 6 YAML archive remain later work. |
| `2026-07-10-workflow-lisp-native-transportable-returns-plan.md` | Stage-5 wave 1 landed ahead of Gates S3/S4 under the 2026-07-10 amendment. Treat it as a completed historical prerequisite; do not re-execute it. |
| `2026-07-10-workflow-lisp-typed-result-guidance-plan.md` | Accepted and reviewed Stage-5 wave 2 plan. Gate P2 and landed native returns satisfy its two prerequisites, but it remains a later post-drain Stage-5 wave rather than the current selector. It adds root/field guidance and owns the combined v2.15 promotion gate. |
| `2026-07-09-workflow-lisp-structured-result-field-guidance-plan.md` | Superseded historical proposal; do not execute. Its scope is absorbed by the two 2026-07-10 plans above. |
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
5. **Boundary-report follow-ups and runtime union-field lineage — completed
   2026-07-10.** Cases 2 and 3 remain landed in `be6596ae` and `02f38549`.
   Case 5 is implemented in `194ad866` with its exact subject identity pinned
   in `962daa2d`; the boundary final gate passed 105 tests, and the post-fix
   full suite retained exactly the six recorded baseline failures.
   Recommendation 11 remains design-gated; this stage did not implement the
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

**Current next selection (2026-07-13):** Drain Phase 1 has landed the generic
route, reviewed identity migration with an empty persisted-record remap,
consumer parity, and F5 sibling contract. Task 1.7 documentation/integration
evidence and review are complete, and Gate P2 has passed its reviewed
six-condition verification. Phase 2 Tasks 2.1–2.3 and parametric prerequisite 6
are complete. The bounded Design Delta promotion handoff has now registered
strict promotable parity, flipped the `.orc` primary, and recorded fresh
compile, dry-run, and parent-smoke evidence while preserving the YAML twin.
Independent joint verification has now satisfied all four Gate P3 conditions,
and Task 3.1 has re-homed the focused parent-drain smoke with fresh parity
evidence. Task 3.2 then retired the promoted parity target while preserving
its historical promotion report for Stage 6. Task 3.3 then deleted the ordered
certification bundle with its permanent evidence re-homed. Task 3.4 then closed
Phase-3 verification with independent specification and code-quality review.
Gates P3 and P4 are independently reviewed and satisfied. Task 4.1 is complete
and independently reviewed, with SPEC PASS and CODE QUALITY PASS. Task 4.2 is
complete and independently reviewed, with SPEC PASS and CODE QUALITY PASS. The
active step is **drain Phase 4 Task 4.3: final verification and closeout**. Task
4.3 has not started. Final verification and final closeout have not begun.
Stage 5 typed result guidance and Stage 6 YAML archive remain later.
Typed result guidance (wave 2,
`2026-07-10-workflow-lisp-typed-result-guidance-plan.md`) has its P2
prerequisite satisfied but remains a later Stage-5/post-drain wave. The
semantic-migration freeze remains in force.

The completed Phase 1 execution order was:

1. Task 1.1 re-baseline and anchor verification.
2. Task 1.2 feasibility probes.
3. Task 1.3 intrinsic-route checkpoint-identity baselines.
4. Task 1.4 authored `backlog-drain-proc` and terminal settlement procedure,
   initially dormant.
5. Task 1.5 macro retarget plus checkpoint-identity comparison.
6. Task 1.6 consumer parity and obligation relocation.
7. Task 1.7 documentation and integration evidence — complete (2026-07-12).

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

The typed-return portion of Stage 4 is already resolved by
`docs/design/workflow_lisp_native_transportable_returns.md`. It establishes a
uniform language-wide return model, direct JSON roots for every currently
transportable type, compiler-owned `__result__` carriage, optional root and
record/union-field guidance, exact v2.15 wire schemas, typed examples, and
prompt-only guidance semantics. The independently reviewed execution plans are:

6. `2026-07-10-workflow-lisp-native-transportable-returns-plan.md` — completed
   under the amendment below; and
7. `2026-07-10-workflow-lisp-typed-result-guidance-plan.md` — its landed-wave-1
   and Gate-P2 prerequisites are satisfied; execute when the sequence reaches
   Stage 5, after drain Stage 3 and the intervening roadmap gate.

Wave 1 is a completed historical prerequisite and must not be replayed. When
Stage 5 selects wave 2, re-run only its Task 1 owner audit; landed wave 1 and
the closed drain gate are both prerequisites. Do not reopen the
accepted typed-return decisions unless the broader procedure-first design finds a
demonstrated conflict; record such a conflict as an explicit design amendment rather
than silently changing an implementation plan.

> **Amendment (2026-07-10, user adjudication):** Wave 1
> (`2026-07-10-workflow-lisp-native-transportable-returns-plan.md`) executes
> **ahead of** Gates S3/S4. Drain Phase 1 is paused at Task 1.5 on an
> architectural blocker whose resolution IS this plan's subject (requirement
> R-G7 and lane findings G-B/G-C/G-D, recorded in the drain plan's Phase 1
> Ledger and `.superpowers/sdd/task-1.5b-report.md` §4/§6): the generic loop
> lane cannot lower real production hook bodies until returns are natively
> transportable. Waiting for S3 would deadlock the roadmap. Wave-1 work is
> plan-required (non-discretionary), i.e. the same semantic-migration-freeze
> exception class as the six landed drain machinery extensions. Compensating
> control: every wave-1 implementation task must additionally pass the paused
> drain migration's behavioral canaries — the checkpoint-identity suite
> (`tests/test_workflow_lisp_checkpoint_identity_comparison.py`, zero row
> changes) and the P2 production drain compile (exit 0, zero diagnostics,
> `g8_deletion_evidence.json` pass) — so the frozen flagship's baselines stay
> authoritative while the substrate moves underneath it. Drain resumes at a
> Task 1.5 re-run once wave 1 lands.
>
> **Historical wave-1 landing record (2026-07-11):** all ten tasks of
> `2026-07-10-workflow-lisp-native-transportable-returns-plan.md` are complete
> with non-regressive record/union evidence and the checkpoint-identity/P2
> drain-compile canaries holding throughout. DSL v2.15 is not promoted — it
> remains an unreleased private preview enabled only by the Workflow Lisp
> compiler's own shared-validation call. At that checkpoint, the drain
> migration's Task 1.5 re-run was the next selected step under the resume
> condition, with typed result guidance (wave 2) sequenced after it rather than
> immediately after wave 1. The live selection is recorded above.

Gate S4:

- the frontend-spec delta is accepted;
- the inventory is reviewed;
- no production implementation starts from the diagnostic report alone;
- separate implementation plans exist for substrate changes, the pilot, and
  migration waves when those scopes are independently testable;
- the native-return and typed-guidance design remains compatible with the
  accepted broader procedure-first delta; landed wave 1 remains the historical
  prerequisite, and wave 2 is eligible for its owner rebaseline when Stage 5
  selects it now that drain Gate P2 is closed.

### Stage 5: Implement Procedure-First Reuse In Waves

Execute only accepted plans, in this order:

1. **Native transportable-return substrate — completed historical
   prerequisite.** `2026-07-10-workflow-lisp-native-transportable-returns-plan.md`
   has landed under the 2026-07-10 amendment. Do not replay it. Direct JSON roots
   and compiler-owned `__result__` carriage remain uniform across every currently
   transportable type; v2.15 is not promoted yet.
2. **Typed result-guidance substrate.** Execute
   `2026-07-10-workflow-lisp-typed-result-guidance-plan.md` when this Stage-5
   step is reached. Wave 1 has landed and drain Gate P2 has closed, satisfying
   its prerequisites; the Design Delta handoff, remaining drain phases, and
   intervening stages still precede this selection. Its completion gate jointly promotes the v2.15 native-return
   and guidance contract.
3. **Remaining substrate wave.** Land only type, return, effect, lowering,
   source-map, or runtime-contract capabilities proven missing by Stage 4.
   Reuse the shared parametric specialization pipeline; do not add
   consumer-name branches.
4. **Pilot wave.** Convert a small non-public workflow family with real effects
   and typed returns. Preserve a public workflow wrapper only where an external
   run/resume boundary is required.
5. **Library/stdlib wave.** Convert reusable internal families with the same
   classification and parity gates.
6. **Production-family wave.** Convert eligible internal reuse only after
   output, artifact, effect, resume, and checkpoint parity is computed.
7. **Compatibility retirement.** Delete workflow-as-function shims only after
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

After the narrow owning selectors, run broad, slow, or full pytest gates with
`pytest -q -n 16 --dist=worksteal`. Keep long runs in tmux and compare known
baseline failures by exact test identity.

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
