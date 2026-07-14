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
- `docs/design/workflow_lisp_language_server.md` owns the `.orc` language
  server contract implemented by Stage 8 (added by the 2026-07-13
  amendments).
- `docs/design/workflow_lisp_provider_live_binding.md` owns the tmux-hosted
  provider transport and `with-live-providers` contract implemented by
  Stage 7 (added by the second 2026-07-13 amendment).
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
| `2026-07-07-drain-migration-g8-retirement.md` | Phase 1 through Phase 4 are complete. Gates P3/P4/S3/S4, both typed-return waves, and the resolved-effect substrate are complete. The bounded Design Delta promotion handoff is recorded without archive, its historical parity artifact remains tracked after target retirement, and the ordered certification bundle plus temporary G8 build serializer are deleted. Stage 6 YAML archive remains later work. |
| `2026-07-10-workflow-lisp-native-transportable-returns-plan.md` | Stage-5 wave 1 landed ahead of Gates S3/S4 under the 2026-07-10 amendment. Treat it as a completed historical prerequisite; do not re-execute it. |
| `2026-07-10-workflow-lisp-typed-result-guidance-plan.md` | Completed Stage-5 wave 2. Root/field guidance and the combined v2.15 public promotion gate are landed; do not re-execute it. |
| `2026-07-13-procedure-first-substrate-gaps-plan.md` | Complete and independently gated. Caller-visible transitive effects are recomputed after specialization; do not re-execute this substrate before the tracked-plan pilot. |
| `2026-07-13-procedure-migration-identity-compatibility-plan.md` | Complete and gated; the final audited handoff to the pilot is `f5adcb79`. Do not re-execute it or edit the pilot family source under this plan. |
| `2026-07-13-procedure-first-pilot-plan.md` | Current selected plan. The 2026-07-14 architect decision (recorded in `2026-07-14-tracked-plan-pilot-identity-retirement-decision-request.md`) approved Path A — conditional reviewed internal identity retirement. Task 1A harness/evidence work is selectable with the repository run store and dedicated evidence store enumerated under a named owner; every pilot source edit remains prohibited until the complete pre-edit gate commits, and fail-closed reversion to strict compatibility stands. |
| `2026-07-13-resume-projection-integrity-hardening-design-plan.md` | Planned after the internal pilot. Its design/specification and resulting implementation plan must complete before migration waves begin; this row is not an implementation claim. |
| `2026-07-13-procedure-first-migration-waves-plan.md` | Planned after resume projection-integrity hardening implementation completes. Task 1 must rebaseline all prerequisites before any family migration. |
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
complete and independently reviewed, with SPEC PASS and CODE QUALITY PASS.
Task 4.3 is complete. Phase 4 is complete. Gate S3 is satisfied. The
semantic-migration freeze is lifted. Gate S4 passed holistic specification and
quality review on 2026-07-13. Both typed-return waves are complete and DSL
v2.15 is public. The resolved-effect substrate is complete and independently
gated. The procedure-migration identity-compatibility prerequisites are
complete and gated at handoff `f5adcb79`. The current selected plan is
`docs/plans/2026-07-13-procedure-first-pilot-plan.md`. The 2026-07-14
architect decision (Path A, recorded in
`2026-07-14-tracked-plan-pilot-identity-retirement-decision-request.md`)
makes Task 1A harness/evidence work selectable; every source edit remains
prohibited until the complete pre-edit gate commits. The named store owner
must still supply genuine attributable attestations after the recorded scans,
with the required isolation, quiescence, and immutable-evidence gate;
identity must not be inferred from usernames, filesystem metadata,
conversation context, or agent claims. Only after the pilot completes is it
followed by
`docs/plans/2026-07-13-resume-projection-integrity-hardening-design-plan.md`, completion
of the resulting implementation plan,
`docs/plans/2026-07-13-procedure-first-migration-waves-plan.md`,
`docs/plans/2026-07-07-yaml-retirement-program.md`,
`docs/design/workflow_lisp_provider_live_binding.md`, and
`docs/design/workflow_lisp_language_server.md`, in that order.

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

**Status (2026-07-13): SATISFIED.** The drain Phase-4 closeout records the
generic-route residue audit, two-family non-regressive parity, exact baseline
full-suite comparison, promoted `.orc` compile/dry-run evidence, and preserved
historical state/YAML twin. The semantic-migration freeze is lifted and Stage 4
was the next selector at Gate S3; it, both typed-return waves, and the
resolved-effect substrate and identity-compatibility prerequisites are now
complete. The tracked-plan pilot is the current selected plan; the 2026-07-14 architect
decision (Path A) makes Task 1A evidence work selectable while every source
edit stays behind the pre-edit gate. Projection-integrity hardening remains
later and must not start first.

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

**Gate S4 completed 2026-07-13.** The accepted frontend delta is
`docs/design/workflow_lisp_procedure_first_reuse_contract.md`; the reviewed
inventory contains 96 active internal calls (33 `procedure-candidate`, 25
`effect-adapter`, and 38 `legacy-retire`) plus three separate
`public-boundary` entries. Independent holistic review returned `GATE S4 SPEC
PASS` and `GATE S4 QUALITY PASS`. The three independently executable follow-on
plans are the effect-substrate, tracked-plan pilot, and migration-wave plans
dated 2026-07-13. Typed result guidance is implemented and compatible; the
resolved-effect substrate is now complete and independently gated. The
accepted identity-compatibility design's generic prerequisites are complete and
gated at `f5adcb79`. The pilot is selected next but remains stopped before Task
1A under the genuine known-store owner-attestation gate recorded in `45eadbdc`.

### Stage 5: Implement Procedure-First Reuse In Waves

Execute only accepted plans, in this order:

1. **Native transportable-return substrate — completed historical
   prerequisite.** `2026-07-10-workflow-lisp-native-transportable-returns-plan.md`
   has landed under the 2026-07-10 amendment. Do not replay it. Direct JSON roots
   and compiler-owned `__result__` carriage remain uniform across every currently
   transportable type; v2.15 is now public.
2. **Typed result-guidance substrate — complete.**
   `2026-07-10-workflow-lisp-typed-result-guidance-plan.md` landed the source,
   wire, prompt, IR, runtime-neutrality, and ordinary-loader gates and jointly
   promoted the v2.15 native-return and guidance contract. Do not replay it.
3. **Resolved-effect substrate wave — complete.**
   `2026-07-13-procedure-first-substrate-gaps-plan.md` separated body-local
   direct effects from caller-visible transitive effects and recomputes the
   latter after generic/`ProcRef` specialization. Its whole-plan specification
   and quality gates passed; do not replay it.
4. **Identity-compatibility prerequisites — complete.**
   `2026-07-13-procedure-migration-identity-compatibility-plan.md` passed its
   generic implementation, evidence, checksum-negative, and independent-review
   gates; the final audited handoff is `f5adcb79`. Do not re-execute it.
5. **Pilot wave — current selected plan, Path A approved 2026-07-14.**
   `2026-07-13-procedure-first-pilot-plan.md` resumes at Task 1A under the
   architect decision recorded in
   `2026-07-14-tracked-plan-pilot-identity-retirement-decision-request.md`:
   conditional reviewed internal identity retirement, evidence collection
   only. Every source edit remains prohibited until the complete pre-edit
   gate commits. The named store owner must still supply genuine attributable
   attestations after the recorded scans, with the required isolation,
   quiescence, and immutable-evidence gate; identity must not be inferred
   from usernames, filesystem metadata, conversation context, or agent
   claims. The
   resumed pilot then owns the reviewed internal retirement exception, the one
   family edit, and full public-wrapper parity. Missing or ineligible retirement
   evidence stops the pilot under strict compatibility.
6. **Resume projection-integrity hardening.** After the pilot, execute
   `2026-07-13-resume-projection-integrity-hardening-design-plan.md`, accept its
   generic design/specification and detailed implementation plan, then complete
   that implementation plan. This is a production-wave prerequisite, not a
   claim that hardening is already implemented.
7. **Small/library wave.** Only after item 6 completes, execute Tasks 1–3 of
   `2026-07-13-procedure-first-migration-waves-plan.md` with the recorded
   classification and parity gates.
8. **Effect-adapter evidence wave.** Execute Task 4 of that migration plan
   before production-family conversion. YAML adapter rows are audited, not
   translated into `.orc` procedure candidates.
9. **Production-family wave.** Execute Tasks 5–6 only after output, artifact,
   effect, resume, and checkpoint parity is computed.
10. **Compatibility retirement handoff.** Execute Tasks 7–8; delete no YAML
   family here, and advance to Stage 6 only through its existing retirement
   gates.

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

### Stage 7: Deliver Provider Live Binding

Stage 7 (added by the second 2026-07-13 amendment) implements
`docs/design/workflow_lisp_provider_live_binding.md`: tmux-hosted provider
invocations with a 1:1 invocation-to-pane invariant as the default transport,
and `with-live-providers`, a call-site structured-concurrency form that runs
N provider calls concurrently inside one atomic step, injects declared
peers' live tmux targets into member prompts, and settles by last-expression
dataflow while member agents interact free-form through their own tools.

It precedes the language server deliberately: it changes the authoring
language and the provider transport, and Stage 8's
ship-against-the-settled-estate rationale requires those changes to land
first.

Entry conditions:

1. The live-binding design has passed independent design review, with the
   T3 steering-viability probe outcome folded into the design first; an
   adverse probe routes to the design's stop/revise criteria (turn-boundary
   steering) before any planning.
2. A component execution plan exists under `docs/plans/` following the
   design's four-phase implementation handoff.

Execution follows the design's phases:

1. Pane transport behind a flag plus the pipe-vs-pane compatibility suite
   (feasibility item T1). Independently valuable observability; may be
   closed as its own tranche.
2. `provider_group` executable node and concurrent member runtime with
   settlement, grace, and termination semantics (feasibility item T2).
3. Frontend surface: `with-live-providers`, binding typecheck and
   `LiveBindingEffect`, lowering with source-map entries, prompt-composer
   binding injection with prompt-audit flags.
4. Steering viability (`interactive_input` template capability, T3), the
   real-CLI end-to-end smoke, spec deltas, and the transport default flip.

Gate S7 (the design's success criteria):

- the compatibility suite is green and the transport default is flipped
  with fresh evidence; T1-T3 outcomes are recorded;
- all of the design's verification-strategy checks pass with fresh output,
  including the fixture-agent interaction proofs and the real-CLI smoke;
- single-member equivalence is proven at IR and behavior level;
- spec deltas are landed and the capability matrix and documentation
  routing reflect implemented status.

Scope guard: Stage 7 covers only the design's v1. Cross-run binding,
multi-step members, typed steering vocabularies, event-driven wake-ups, and
background/join primitives are excluded; each requires its own design
treatment and an explicit amendment to this roadmap.

### Stage 8: Deliver The `.orc` Language Server

Stage 8 is the final stage (added by the first 2026-07-13 amendment as
Stage 7; renumbered by the second). It implements
`docs/design/workflow_lisp_language_server.md`: a stdio LSP server that is a
pure consumer of the existing compile entry points per frontend specification
§76.1, delivering save-driven diagnostics, go-to-definition, document symbols,
and completion for `.orc` authoring.

It runs last deliberately: the server's navigation and completion surfaces
should target the settled procedure-first stdlib, the `.orc`-primary
authoring estate, and the landed live-binding surface rather than chase
Stage 5-7 churn, and its v1 provides no substrate capability any earlier
stage needs.

Entry conditions:

1. The language-server design has passed independent design review, with any
   direction changes folded into the design doc before planning.
2. A component execution plan exists under `docs/plans/` following the
   design's three-phase implementation handoff.

Execution follows the design's phases:

1. Diagnostics core — translation layer, serialized compile driver, stdio
   server, CLI diagnostic-parity test. The design's feasibility items F1-F3
   are verified and recorded here; adverse F2/F3 outcomes route to the
   design's stop/revise criteria rather than ad-hoc workarounds.
2. Navigation — compile-snapshot retention, span interval index,
   go-to-definition, document symbols, completion.
3. Packaging and docs — `lsp` optional-dependency extra, editor-setup
   documentation, capability matrix row, routing updates.

Gate S8 (the design's success criteria):

- all of the design's verification-strategy checks pass with fresh output,
  including the stdio integration tests, the CLI diagnostic-parity test, and
  the end-to-end check against a real repository workflow;
- the default-install dependency set is unchanged;
- F1-F3 outcomes are recorded with the implementation evidence;
- the capability matrix and documentation routing reflect implemented status.

Scope guard: Stage 8 covers only the design's v1 (save-driven diagnostics
plus navigation). The deferred frontend prerequisites P1-P5 (diagnostic
accumulation, reader error recovery, hover type sidecar, source overlay,
compile caching) are each a separate frontend change requiring its own design
treatment and an explicit amendment to this roadmap; Stage 8 must not absorb
them.

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
- Stage 7 edits provider-executor, frontend, IR, and checkpoint surfaces and
  is serial with Stage 5-6 work at those shared surfaces; its phase-1
  transport tranche stays behind a flag until its compatibility gate passes.
- Stage 8 is additive at `orchestrator/lsp/` and packaging metadata and does
  not contend with earlier-stage code surfaces; its deferred P1-P5 frontend
  prerequisites are out of its scope and must not be started from Stage 8.

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
- identity-compatibility prerequisites pass before the internal pilot, and the
  pilot's strict-default or reviewed-retirement gate closes with genuine store
  attestations;
- checksum-compatible resume projection-integrity hardening is designed,
  specified, implemented, and reviewed before migration waves begin;
- selected real families have migrated with computed parity evidence;
- compatibility workflow-as-function paths have explicit remaining owners or
  are retired;
- YAML retirement proceeds against the procedure-first model rather than
  recreating reusable workflow wrappers;
- provider live binding v1 has shipped through Gate S7, with the
  pane-transport compatibility evidence and the fixture-agent interaction
  proofs recorded;
- the `.orc` language server v1 has shipped through Gate S8, with editor
  diagnostics proven at parity with the CLI compile path.

## Stop And Revise Conditions

Revisit this sequence if:

- executor closeout changes checkpoint or resume behavior rather than merely
  structure;
- drain migration requires a consumer-name special case;
- the broad contract cannot cover a non-drain candidate without runtime
  procedure values or hidden effects;
- procedure conversion changes a public run/resume identity without an
  explicit migration contract;
- the identity prerequisite gate, pilot retirement eligibility/attestation
  gate, or projection-integrity implementation gate cannot pass without
  weakening its accepted contract;
- YAML promotion would force the repository back toward workflows as the
  internal reuse unit.
