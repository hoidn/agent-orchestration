# Procedure-First Roadmap Execution Sequence

Status: complete historical work instructions
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
- `docs/design/workflow_lisp_provider_live_binding.md` owns the
  observation-only provider-pane and bounded `with-live-providers`
  supervision contract implemented by Stage 7 (added by the second
  2026-07-13 amendment).
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
| `2026-07-13-procedure-first-pilot-plan.md` | Complete. Evidence landed at `63e03330`, `e6a85cb7`, `de522c76`, `f5dbac88`, `76205d4f`, and `0769e837`; holistic specification and quality reviews approved HEAD `0769e837`. Exactly two dedicated runs completed, and the route remains `leaf_runtime_candidate` / `migration_candidate` / `migration_evidence_only`. Historical clean artifact equality is `not_asserted`. This is one reviewed internal pilot, not a general compatibility, family-wave, promotion, or YAML-retirement claim. |
| `2026-07-13-resume-projection-integrity-hardening-design-plan.md` | Complete. Characterization landed at `1cd60767`, the accepted design at `52e2b05f`, the normative state/acceptance contract at `00135832`, and the reviewed implementation plan at `26a5d3db`; holistic routing reviews and fresh focused/broad validation passed at closeout. This row does not claim runtime implementation. |
| `2026-07-13-resume-projection-integrity-hardening-implementation-plan.md` | Complete at `fdf1e06b`. The generic runtime hardening, focused acceptance gate, deterministic public CLI smoke, broad baseline-equivalence check, and independent specification/quality reviews are recorded in the plan. Do not re-execute it as the live selector. |
| `2026-07-13-procedure-first-migration-waves-plan.md` | Historical complete. Task 1's post-hardening rebaseline completed at `4983afff` plus correction `fa16bcf0`; Task 2 completed at `daff694c`. Task 3 retained seven internal calls under strict compatibility. Task 4 completed its three audit groups at `c9687539`, `26d9ecd0`, and `848ceb52`. Task 5 retained four finalizer-projection calls in `docs/plans/2026-07-16-design-delta-finalizer-projection-checkpoint-retention-plan.md`, six blocked-recovery/finalization calls in `docs/plans/2026-07-16-design-delta-blocked-recovery-lowering-retention-plan.md`, nine phase-orchestration calls in `docs/plans/2026-07-16-design-delta-phase-orchestration-retention-plan.md`, and two completed-finalization calls in `docs/plans/2026-07-16-design-delta-completed-finalization-lowering-retention-plan.md`, reconciling 4 + 6 + 9 + 2 = 21 retained calls. Task 6 retained the sole private drain-builder call under `docs/plans/2026-07-16-design-delta-drain-builder-checkpoint-retention-plan.md`: the complete compiling inline hypothetical removes one caller-owned checkpoint and adds none, so no source or history migration occurred. Task 7 handed all 63 legacy-retire rows to Stage 6 at `7e6adc36`. Task 8 sealed 565 passed/6 skipped focused, 36 passed routing, and 4992 passed/17 skipped with six established unrelated broad failures adjudicated as four digest-exact plus two logger-location-only. Specification PASS and quality APPROVED closed the wave. The final queue is 0 procedure candidates, 32 effect adapters, and 63 legacy-retire rows, plus 13 separate public entries and one history row; this is not universal procedure-first adoption. |
| `2026-07-16-tracked-design-phase-identity-retirement-plan.md` | Complete by fail-closed eligibility stop. The generic scanner found 26 supported old-identity consumers in the completed pilot root, so the source stayed unchanged and the row moved to `effect-adapter`. This was not a competing roadmap selector and authorized no YAML edit, remap, or cross-source resume claim. |
| `2026-07-16-design-plan-impl-implementation-phase-identity-retirement-plan.md` | Complete by fail-closed eligibility stop. The generic scanner found 24 supported old-identity consumers in the completed pilot root, so the source stayed unchanged and the row moved to `effect-adapter`. This was not a competing roadmap selector and authorized no run, YAML edit, remap, or cross-source resume claim. |
| `2026-07-16-same-file-build-checks-identity-retirement-plan.md` | Complete by fail-closed route-eligibility stop. The containing route is live/current and therefore requires strict compatibility; the source stayed unchanged and the row moved to `effect-adapter` even though known-store scans found zero matching consumers. This was not a competing roadmap selector and authorized no run or owner gate. |
| `2026-07-16-design-delta-exported-workflow-retention-plan.md` | Complete after specification PASS and quality APPROVED. Seven calls remain active `effect-adapter` because their five unique callees are exported CLI-selectable workflows that cannot use reviewed internal retirement; five separate public-boundary records make that negative explicit. No source/run mutation or store/owner gate occurred. |
| `2026-07-09-workflow-lisp-structured-result-field-guidance-plan.md` | Superseded historical proposal; do not execute. Its scope is absorbed by the two 2026-07-10 plans above. |
| `2026-07-07-yaml-retirement-program.md` | Stage 6 complete. Tasks 1-7 are complete: all five queues are drained, exactly the two specified `.orc` ports are primary, no authored workflow YAML/YML remains, fresh execution is ORC-only, and the user-facing loader and project PyYAML dependency are absent. The 1,020-passed/5-skipped focused gate, fresh non-mutating `.orc` smoke, scoped broad comparison with zero new failures against the owner-adopted baseline, and ordered specification PASS/quality APPROVED reviews closed the stage at `d9baa120`. |
| `2026-07-23-provider-live-binding-implementation-plan.md` | Completed Stage-7 v1 selector. Provider-supervision v1 implementation landed through `4d4f05c7` and completed Tasks 1-15 and Gate S7-v1: provider observation, structural turn-boundary resume, the `provider_supervision.v1` coordinator/runtime, target-2.16 frontend/IR, deterministic and real-provider integration, normative docs, 6,978-passed/17-skipped broad comparison with the four exact retained failures and zero new failures, and ordered `TASK15_SPEC_APPROVED` / `TASK15_QUALITY_APPROVED` reviews. The separately reviewed v1.1 selector in the next row subsequently closed Stage 7 before Stage 8. |
| `2026-07-24-provider-peer-messaging-v1.1-implementation-plan.md` | Completed Stage-7 v1.1 selector. It binds accepted design commit `8001c016` / digest `4f21cec1...`; received ordered `PLAN_SPEC_APPROVED` / `PLAN_QUALITY_APPROVED`; and landed Tasks 1-11 through `b08c04a6`: the structural capability, interactive adapter, receiving-attempt ledger and peer protocol, single-writer `provider_peer_group.v1` runtime, target-2.17 frontend/projections, deterministic integration, and real two-/three-member gates. Task 12 completed normative/routing updates and final focused/broad/compatibility/real verification, then received ordered `TASK12_FINAL_SPEC_APPROVED` / `TASK12_FINAL_QUALITY_APPROVED`. Gate S7-v1.1 and Stage 7 are closed; the selected list-traversal interstage subsequently completed. |
| `2026-07-25-workflow-lisp-pure-list-traversal-implementation-plan.md` | Completed reviewed post-Stage-7 interstage selector. It binds the accepted target-2.18 design at `80df0616` / digest `e161d45e...` and received ordered `LIST_PLAN_SPEC_APPROVED` / `LIST_PLAN_QUALITY_APPROVED` plus final exact-byte reaffirmations. Its seven TDD tasks are complete; it neither renumbers nor expands Stage 8. Consult the component plan for exact completion evidence. |
| `2026-07-25-workflow-lisp-language-server-implementation-plan.md` | Completed Stage-8 selector. It binds the accepted design at `cfcac27f` and completed nine independently reviewed TDD tasks: exact-byte read tracing; read-only build-core extraction; single-root state/driver; the F1-F3 request-parity gate; pure diagnostic contributions; stdio/watcher transport; exact authored-callee provenance; closed navigation; and packaging/E2E/routing closure. Gate S8 is complete; consult the component plan for exact implementation and verification records. |
| `2026-07-23-refusal-diagnosability-fixes-plan.md` | Queued small fix; not a competing selector. Applies design principle 28 (refusals name their rule) to the entry-bootstrap name-allowlist gate: denial diagnostic, declared-property rule replacing the name key, and promoted-route identity non-drift verification. Execute after the current YAML-retirement task or opportunistically between capture windows. |
| `2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md` | Incorporated as the tracked current E-series program by owner decision 2026-07-30. Its authoritative current mapping is E0 canonical direct control, E1 `run-ref`, E2 trials, and E3 external control; the old slimmed E0 probe remains unselected and, with the historical E0-E5 proposal, is superseded reference only. The accepted E0/C1 designs and completed lean-pilot owner handoff make the proposed `2026-07-31-workflow-lisp-e0-direct-control-component-plan.md` review-eligible, but no E implementation is selected until that plan passes ordered review and its status-only selection delta lands. E4P remains exclusively absorbed by successor Stage Q3. |

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

**Historical selection record (2026-07-13):** Drain Phase 1 has landed the generic
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
complete and gated at handoff `f5adcb79`. The tracked-plan pilot subsequently
completed at `0769e837` after the six recorded evidence commits, exactly two
completed dedicated runs, focused 544/2 and broad 4743/13 gates with the six
accepted unrelated failures, and holistic specification/quality approval.
The design/specification/implementation-plan artifacts are complete at
`1cd60767`, `52e2b05f`, `00135832`, and `26a5d3db`. The generic runtime
hardening then completed at `fdf1e06b` with its focused acceptance gate,
deterministic public CLI smoke, broad baseline-equivalence check, and final
independent specification/quality reviews. The completed hardening plan is now
historical execution evidence. The procedure-first migration wave is complete;
its execution record is
`docs/plans/2026-07-13-procedure-first-migration-waves-plan.md`. Its Task 1
rebaseline completed at `4983afff` plus `fa16bcf0`. Task 2's small-example
family is complete; Steps 1 and 2 retained ineligible boundaries
after deterministic scans found 26 and 24 supported old-identity consumers,
and Task 2 Step 3 retained the same-file helper because its live/current route
requires strict compatibility. Task 2 completed at `daff694c`. Task 3 retained
seven calls at exported workflow boundaries and passed its unchanged-source
integration, inventory, and both review gates. Task 4 completed its three
independently approved YAML audit groups at `c9687539`, `26d9ecd0`, and
`848ceb52`. Task 5's reviewed
`docs/plans/2026-07-16-design-delta-finalizer-projection-checkpoint-retention-plan.md`
decision retained four calls under strict compatibility. The later blocked
recovery/finalization decision,
`docs/plans/2026-07-16-design-delta-blocked-recovery-lowering-retention-plan.md`
retained the exported classifier under strict compatibility and five finalizer
calls because their inline conversion fails with
`pure_expr_operand_type_mismatch`; no finalizer hypothetical executable,
checkpoint delta, or affected-route runtime parity is claimed.
The subsequent phase-orchestration decision,
`docs/plans/2026-07-16-design-delta-phase-orchestration-retention-plan.md`,
retained eight calls because their four callees are exported public workflows
and retained the private pending call because its compiling inline
hypothetical removes one caller-owned workflow-call boundary checkpoint and
adds twelve caller-owned inline checkpoints with different checkpoint/storage
identities and a different generated presentation-path namespace. No runtime-
parity claim is made. This leaves 3 procedure candidates, 29 effect adapters,
and 63 legacy-retire rows, plus 13 separate public entries and one history row
at the phase-orchestration boundary. The completed-finalization decision,
`docs/plans/2026-07-16-design-delta-completed-finalization-lowering-retention-plan.md`,
then retained two calls because its complete exact-path inline hypothetical
fails shared validation with exactly two `workflow_boundary_type_invalid`
diagnostics for blocker-class variant proofs. No hypothetical executable,
checkpoint, resume, or runtime delta is claimed. Task 5's four groups reconcile
4 + 6 + 9 + 2 = 21 retained rows. Task 6 then retained its sole builder call
under `docs/plans/2026-07-16-design-delta-drain-builder-checkpoint-retention-plan.md`
because the compiling inline hypothetical removes one caller-owned checkpoint
and adds none. The current inventory is 0 procedure candidates, 32 effect
adapters, and 63 legacy-retire rows, plus 13 separate public entries and one
history row. Task 7 completed its exact Stage-6 handoff at `7e6adc36`, and
Task 8 sealed the wave with 565 passed/6 skipped focused, 36 passed routing,
and 4992 passed/17 skipped plus six established unrelated broad failures:
four digest-exact and two logger-location-only. The final specification review
returned PASS and quality review returned APPROVED. YAML retirement Tasks 1-6
then completed the reviewed gap contract, digest-bound persisted dashboard
surface, shared mapping-validation authority, deprecation and author routing,
both dedicated `.orc` port promotions, and every gated archive/deletion queue.
Task 7 subsequently made the fresh frontend ORC-only, removed the user-facing
loader and project PyYAML dependency, passed its 1,020-passed/5-skipped focused
gate, and passed a fresh non-mutating `.orc` dry-run smoke. Its final scoped
broad comparison recorded 6,386 passed, 15 skipped, and the four exact retained
owner-baseline failures with zero new failures; ordered independent review
returned specification PASS and quality APPROVED at `d9baa120`. Stage 6 is
complete. Stage 7 provider-supervision v1 implementation landed through
`4d4f05c7` and completed Task 15 and Gate S7-v1; the recorded-peer-messaging
v1.1 implementation then completed Tasks 1-11 through `b08c04a6`. Task 12
completed its normative/routing and closing verification and received ordered
`TASK12_FINAL_SPEC_APPROVED` / `TASK12_FINAL_QUALITY_APPROVED`, closing Gate
S7-v1.1 and Stage 7. The amended list-traversal design passed ordered review
and was accepted at `80df0616`; its independently reviewed seven-task
implementation plan subsequently completed the selected interstage. Stage 8
subsequently completed through its reviewed language-server plan and
post-completion controller correction. The numbered roadmap is complete; the
separate language-quality successor roadmap is now the current selector.

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
complete. The tracked-plan pilot later completed and passed holistic review at
`0769e837`. Projection-integrity design/specification/plan artifacts are
complete through `26a5d3db`; the runtime implementation and its reviewed
acceptance gate later completed at `fdf1e06b`. The hardening plan is historical
evidence, and the migration-wave plan is now selected.

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
gated at `f5adcb79`. The pilot subsequently completed through `0769e837` with
exactly two completed dedicated runs and holistic specification/quality
approval. This closes one evidence-only internal pilot, not general resume
compatibility or a family migration wave.

### Stage 5: Implement Procedure-First Reuse In Waves

The procedure-first migration wave and Stages 6-7 are complete.
Provider-supervision v1 closed Gate S7-v1 through `4d4f05c7`; the
owner-amended v1.1 component plan completed Tasks 1-11 through `b08c04a6` and
Task 12 through both ordered reviews, closing Gate S7-v1.1. The accepted
list-traversal design at `80df0616` and its reviewed implementation plan have
completed the selected interstage. Stage 8 subsequently completed, including
its reviewed controller correction. The current selector is the separate
language-quality successor roadmap.

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
5. **Pilot wave — complete.**
   `2026-07-13-procedure-first-pilot-plan.md` completed the single reviewed
   internal retirement pilot through `0769e837`. It proves its own retained
   public-wrapper parity and evidence-only retirement only; it does not
   generalize cross-source resume, compatibility, promotion, or family waves.
6. **Resume projection-integrity runtime hardening — complete.** The
   design/specification/plan artifacts are complete at `1cd60767`, `52e2b05f`,
   `00135832`, and `26a5d3db`; the implementation and final reviewed gate are
   complete at `fdf1e06b`. The completed
   `2026-07-13-resume-projection-integrity-hardening-implementation-plan.md`
   is historical execution evidence, not the live selector.
7. **Small/library wave — complete through Task 3.** Task 1 of
   `2026-07-13-procedure-first-migration-waves-plan.md` completed its
   post-hardening rebaseline at `4983afff` plus `fa16bcf0`. Task 2's
   small-example family is complete at `daff694c`. Task 2 Step 1's
   `docs/plans/2026-07-16-tracked-design-phase-identity-retirement-plan.md`
   closed fail-closed because a known retained store contains 26 supported
   old-identity consumers; the callee remains a workflow and its row is now an
   `effect-adapter`. Task 2 Step 2's
   `docs/plans/2026-07-16-design-plan-impl-implementation-phase-identity-retirement-plan.md`
   reached the same fail-closed result with 24 supported consumers. Task 2
   Step 3's
   `docs/plans/2026-07-16-same-file-build-checks-identity-retirement-plan.md`
   retained the helper because its containing route is live/current and
   requires strict compatibility. Task 2's integration gates, inventory
   reconciliation, and both reviews passed at `daff694c`. Task 3 then retained
   seven calls because their five callees are exported CLI entries; both
   reviews passed.
8. **Effect-adapter evidence wave — complete.** Task 4 audited all 25 YAML
   rows in three independently approved groups at `c9687539`, `26d9ecd0`, and
   `848ceb52`. No YAML was translated or modified by this classification wave.
9. **Production-family wave — complete on retained-boundary evidence.** Task 5's
   `docs/plans/2026-07-16-design-delta-finalizer-projection-checkpoint-retention-plan.md`
   passed final specification and quality re-review and closed the finalizer-
   projection subfamily as a strict-compatibility retention: four calls remain
   effect adapters. The subsequent blocked recovery/finalization decision,
   `docs/plans/2026-07-16-design-delta-blocked-recovery-lowering-retention-plan.md`
   retained the exported classifier under strict compatibility and five
   finalizer calls after their exact-path inline conversion failed with
   `pure_expr_operand_type_mismatch`. No finalizer hypothetical executable,
   checkpoint delta, or affected-route runtime
   parity is claimed. The phase-orchestration decision,
   `docs/plans/2026-07-16-design-delta-phase-orchestration-retention-plan.md`,
   then retained eight calls on four exported public boundaries and the
   private pending call because its caller-owned workflow-call boundary
   checkpoint is removed and twelve caller-owned inline checkpoints are added
   with different checkpoint/storage identities and a different generated
   presentation-path namespace. The completed-finalization decision,
   `docs/plans/2026-07-16-design-delta-completed-finalization-lowering-retention-plan.md`,
   then retained two calls because shared validation emitted exactly two
   `workflow_boundary_type_invalid` diagnostics and no hypothetical executable.
   Task 5's groups reconcile 4 + 6 + 9 + 2 = 21 retained calls. The Task 6
   decision,
   `docs/plans/2026-07-16-design-delta-drain-builder-checkpoint-retention-plan.md`,
   retains the sole private builder call because its compiling inline
   hypothetical removes a caller-owned checkpoint and adds none. The queue is
   0 procedure candidates, 32 effect adapters, and 63 legacy-retire rows, plus
   13 separate public entries and one history row. This is not universal
   procedure-first adoption because all 32 effect adapters remain.
10. **Compatibility retirement handoff and closeout — complete.** Task 7's
   exact Stage-6 handoff landed at `7e6adc36`; Task 8 then sealed 565 passed/6
   skipped focused, 36 passed routing, and 4992 passed/17 skipped with the six
   established unrelated broad failures adjudicated as four digest-exact plus
   two logger-location-only. Whole-wave specification PASS and quality APPROVED
   advanced the selector to Stage 6 Task 1 without deleting a YAML family.
   Tasks 1-7 are complete. The Task-7 ORC-only frontend, focused checks,
   non-mutating smoke, scoped broad comparison with zero new baseline failures,
   and ordered specification PASS/quality APPROVED reviews closed Stage 6 at
   `d9baa120`.

Every wave must pass:

- targeted type/lowering/runtime tests;
- source-map and diagnostic coverage;
- checkpoint/resume evidence when persisted identities are affected;
- computed migration parity for production consumers;
- one end-to-end orchestrator usage check.

### Stage 6: Resume YAML Retirement

**Status:** Complete. Tasks 1-7 are complete and every fixed queue is drained.
The Task-7 product work made fresh execution ORC-only while retaining the
bounded completed-run state-only compatibility surface. The user-facing YAML
loader and project PyYAML dependency are absent, the authored workflow estate
is empty, the focused gate passed 1,020 tests with 5 skipped, and a fresh
`.orc` dry-run smoke left the run-root count unchanged. The final scoped broad
comparison matched the owner-adopted baseline with zero new failures, and both
independent reviews approved the final product tree at `d9baa120`.
Provider-supervision v1 and peer messaging v1.1 are complete through Gates
S7-v1 and S7-v1.1; Stage 7 is closed after the latter's ordered Task 12
reviews.

Use the procedure-first model as the target authoring architecture. The
2026-07-14 steering amendment to
`docs/plans/2026-07-07-yaml-retirement-program.md` selects deletion-first
retirement:

The former pilot-quiescence scheduling window is closed. The early independent
estate-deletion queue retained its deletion-first semantics and passed its
repository-reference and owner-bound supported-root gates before deletion. All
later queue-specific gates also closed without changing queue membership or
dependency order.

1. Run the estate deletion sweep as an early independent tranche — complete.
   The non-survivor queue was drained in bounded dependency-ordered batches
   after its reference and supported-consumer gates passed.
2. Refresh the YAML-to-`.orc` language-gap list only for the two surviving
   families — complete at `docs/workflow_yaml_orc_gap_list.md`; its blocking
   gates remain binding on the later port work.
3. Archive the already-demoted Design Delta YAML twins only after confirming
   the recorded Stage-3 promotion/parity artifact remains the historical
   decision evidence and the `.orc` primary still passes its preserved compile,
   smoke, and end-to-end checks on the post-procedure checkout — complete. The
   retired `design_delta_parent_drain` parity target was not recreated.
4. Complete dashboard typed-surface, loader-validation separation, and the
   fresh-root deprecation plus new-author-routing surface — complete and
   independently reviewed.
5. Port `verified_iteration_drain` and `generic_run_watchdog` to `.orc`
   through the retained parity kernel — complete. Both dedicated `.orc`
   primaries are promoted, and their former YAML twins subsequently passed
   Task 6's deletion gates and were retired.
6. Execute Task 6's gated archive and deletion queues in their fixed dependency
   order — complete. Each archive, port-source, and owner-directed holdout gate
   closed independently rather than treating promotion as deletion evidence.
7. Delete the user-facing YAML frontend under Task 7 after the estate reached
   zero — complete. Fresh YAML/YML execution rejects before mutation; the
   authored loader and project PyYAML dependency are removed. The final scoped
   broad comparison introduced zero new owner-baseline failures, and ordered
   independent review returned specification PASS and quality APPROVED at
   `d9baa120`.

Do not port a YAML family into a reusable `.orc` workflow when Stage 4
classifies that unit as a procedure candidate.

### Stage 7: Deliver Provider Live Binding

Stage 7 (added by the second 2026-07-13 amendment) implements
`docs/design/workflow_lisp_provider_live_binding.md`. The adverse pre-plan T3a
probe closed the original direct `send-keys` design: installed clients queued
ordinary input, while client-owned interruption left prior tool work live. The
2026-07-23 revision therefore keeps the provider pipe/JSONL transports
authoritative, attempts one observation-only pane per invocation, and defines
`with-live-providers` v1 as exactly one worker plus one supervisor inside one
workflow-state/result boundary. The supervisor observes the worker and returns
the prelude `ProviderSteeringDirective` union. `CONTINUE` selects the fresh
worker turn; `STEER` reaps the runtime-owned process group and performs one
validated provider-session resume turn with free-form guidance plus a fresh
typed output contract.

The 2026-07-24 owner amendment retains that v1 surface and adds a distinct
v1.1 phase, revised in
`docs/design/workflow_lisp_provider_peer_messaging.md`: target `2.17` adds a
separate static `2..8` member peer-group form and executable node. Declared
members send free-form text by binding name through an exact attempt-bound
runtime surface; the coordinator fsyncs the receiver ledger before an
opt-in interactive adapter offers the text for a natural later turn.
Cooperative readiness, acknowledgement, finish, and natural-close receipts
close lifecycle ambiguity. Peer messaging never cancels, resumes, selects,
or settles a member, and peer groups have no forcing edge; v1 `STEER` remains
the only successful forcing move. Target `2.16` and
`provider_supervision.v1` remain unchanged. Same-turn or unrecorded raw-pane
steering remains excluded.

**Current Stage 7 status:** Complete. v1 Tasks 1-15 and Gate S7-v1 are
implemented through `4d4f05c7`. The owner-amended v1.1 design resolved its
initial `CHANGES_REQUIRED` review and received `DESIGN_SPEC_APPROVED` and
ordered `DESIGN_QUALITY_APPROVED`. Its execution plan at
`docs/plans/2026-07-24-provider-peer-messaging-v1.1-implementation-plan.md`
received ordered `PLAN_SPEC_APPROVED` and `PLAN_QUALITY_APPROVED`. Tasks 1-11
are complete through `b08c04a6`, including deterministic and real two- and
three-member gates. Task 12's normative/routing updates and final
focused/broad/compatibility/real verification completed and received ordered
`TASK12_FINAL_SPEC_APPROVED` / `TASK12_FINAL_QUALITY_APPROVED`, closing Gate
S7-v1.1. The selected list-traversal interstage subsequently completed, so
Stage 8 became eligible and subsequently completed.

It precedes the language server deliberately: it changes the authoring
language and provider execution/observation contracts, and Stage 8's
ship-against-the-settled-estate rationale requires those changes to land
first.

Entry conditions:

1. The live-binding design has passed independent design review, with the
   adverse T3a outcome and the reviewed turn-boundary revision folded into the
   accepted design before planning.
2. A component execution plan exists under `docs/plans/` following the
   design's four-phase implementation handoff.
3. The v1.1 amendment receives independent design review before its execution
   plan is drafted or implementation begins.

Execution follows the design's phases:

1. Observation/cancellation substrate: observation mirror behind a flag,
   shared real-shape session codec, cancellable process-group control, T1
   non-interference, and an early real Codex identity → cancel/owned-PGID →
   resume spike. A failed real boundary stops Stage 7 before group/frontend
   implementation.
2. `provider_supervision.v1` executable node and single-writer coordinator:
   immutable concurrent member execution, `ProviderSteeringDirective`
   arbitration, one bounded resume turn, attempt/evidence ownership, atomic
   state/result publication, interrupted-visit quarantine, and T2/T3b
   fixtures.
3. Frontend surface: two-member `with-live-providers`,
   `LiveSupervisionEffect`, reserved prelude directive union,
   post-specialization member extraction, WCC/schema-2 carriage,
   pure-settlement lowering, source maps, and target DSL 2.16.
4. Capability promotion and integration: structural
   `session_support.turn_boundary_resume`, the real supervisor/worker T3b
   smoke, spec deltas, default observation enablement, capability matrix, and
   authoring/docs updates.
5. Recorded peer messaging v1.1: independently review the amendment, add and
   review a focused execution-plan delta, then implement target-`2.17`
   `with-live-provider-peers`, `provider_peer_group.v1`, runtime-owned
   peer-ready/send/ack/finish, receiver-ledger-before-offer, natural
   turn-boundary delivery and close, coordinator serialization, and the
   static `2..8` member authoring boundary without changing v1 settlement or
   `STEER` semantics.

Gate S7-v1 (the original design's success criteria):

**Gate status:** complete. Task 15 recorded 475 collected, 473 focused passed,
both real-provider E2Es passed, a 6,978-passed/17-skipped broad comparison
with only the four exact retained Stage-6 failures and zero new failures, and
ordered `TASK15_SPEC_APPROVED` / `TASK15_QUALITY_APPROVED` reviews.

- the observation non-interference suite is green for ordinary, streaming,
  session, adjudicated, and managed-provider invocation paths, and ordinary
  mirror failure degrades observability rather than provider results;
- the phase-1 real Codex boundary and final real supervisor/worker smoke both
  pass, with canonical preterminal identity, owned-PGID cancellation proof,
  joined capture/executor work, and a corrected resumed typed result;
- T2 proves the group coordinator is the only workflow-state writer and all
  coordinator event orderings produce one selected-result/state outcome;
- both-direction directive, result-authority, crash-quarantine, attempt,
  frontend, WCC, IR, checkpoint, and end-to-end checks pass with fresh output;
- spec deltas are landed and the capability matrix and documentation
  routing reflect implemented status.

Gate S7-v1.1 additionally requires:

**Gate status:** complete. Implementation Tasks 1-11 landed through `b08c04a6`.
Task 12's final routing (`50 passed`), focused (`717 passed`), broad
(`7,479 passed`, `21 skipped`, the four exact retained failures, zero new
failures), target-2.16 compatibility (`1 passed`, `11 deselected`), and
combined real-provider (`6 passed`) verification are complete. Ordered review
returned `TASK12_FINAL_SPEC_APPROVED` / `TASK12_FINAL_QUALITY_APPROVED`; Gate
S7-v1.1 and Stage 7 are closed.

- the 2026-07-24 amendment has an independent approved design review and a
  reviewed execution-plan delta;
- sender/receiver identity, receiver-ledger append, ordering, failure,
  cooperative receipts, natural-boundary delivery and close, and coordinator
  single-writer behavior have both-direction unit and integration coverage;
- peer messaging cannot directly cancel, resume, steer, settle, or publish a
  member, and unrecorded/raw-pane delivery remains rejected;
- static `2..8` member type/effect/lowering and runtime ownership rules match
  the reviewed plan, while the shipped two-member v1 form remains
  non-regressive;
  and
- focused, broad non-security, real-provider smoke where load-bearing, and
  ordered independent specification/quality reviews pass.

Gate S7 closes only after both sub-gates close.

Scope guard: Stage 7 covers the shipped v1 plus the owner-proposed v1.1
recorded-peer-messaging/static-peer-group amendment after its required
revision and approved independent review. Peer messaging combined with
`STEER`, provider-native duplex protocols, dynamic membership,
same-turn or unrecorded raw-pane steering, more than one forcing `STEER`,
effectful settlement, cross-run binding, filesystem rollback, and general
background/join primitives remain excluded; each requires its own design
treatment and an explicit roadmap amendment.

### Selected Interstage: Review And Implement Pure List Traversal

**Current status:** Complete. Independent design review
required amendments to the `bef65fdf` proposal; the corrected principle-29
design was accepted at `80df0616` after ordered
`LIST_DESIGN_SPEC_APPROVED` / `LIST_DESIGN_QUALITY_APPROVED`. The reviewed
`docs/plans/2026-07-25-workflow-lisp-pure-list-traversal-implementation-plan.md`,
which received ordered `LIST_PLAN_SPEC_APPROVED` /
`LIST_PLAN_QUALITY_APPROVED` and final exact-byte reaffirmations, completed all
seven tasks.
Its governing accepted design is
`docs/design/workflow_lisp_pure_list_traversal.md`.
This is the one small implementation plan required by the interstage gate;
the component plan owns its exact completion evidence.

This selected interstage work had no Stage 8 dependency. The interstage is
complete; it neither renumbers nor expands Stage 8. Stage 8 is complete.

### Stage 8: Deliver The `.orc` Language Server

Stage 8 is the final stage (added by the first 2026-07-13 amendment as
Stage 7; renumbered by the second). It implements
`docs/design/workflow_lisp_language_server.md`: a stdio LSP server that is a
pure consumer of the existing compile entry points per frontend specification
§76.1, delivering save-driven diagnostics, go-to-definition, document symbols,
and completion for `.orc` authoring.

**Current status:** Complete. Gate S8 is complete under the reviewed nine-task
implementation plan.

It runs last deliberately: the server's navigation and completion surfaces
should target the settled procedure-first stdlib, the `.orc`-primary
authoring estate, and the landed live-binding surface rather than chase
Stage 5-7 churn, and its v1 provides no substrate capability any earlier
stage needs.

Entry conditions:

1. The language-server design has passed independent design review, with any
   direction changes folded into the design doc before planning.
2. A component execution plan exists under `docs/plans/` following the
   design's dependency order.
3. The selected list-traversal interstage is complete.

Conditions 1 and 2 are satisfied by accepted design commit `cfcac27f` and
`docs/plans/2026-07-25-workflow-lisp-language-server-implementation-plan.md`.
Condition 3 is satisfied by the completed list-traversal interstage. All
Stage-8 entry conditions were met before implementation began.

Execution followed the reviewed plan's nine tasks:

1. Trace the exact bytes parsed by every Stage-3 read while preserving legacy
   parser judgments.
2. Extract the shared read-only in-memory build core; keep `_emit` as the sole
   persistent writer.
3. Implement one-root immutable state, exact source/configuration freshness,
   reverse invalidation, and the serialized compile driver.
4. Capture the production-normalized request at its shared build seam and
   prove F1-F3 before diagnostics transport or navigation exists.
5. Implement pure coordinate translation and deterministic
   current-generation diagnostic contribution ownership.
6. Expose only those reviewed transitions through a frame-clean stdio and
   watcher transport with optional dependencies.
7. Preserve exact direct-authored callee spans without changing compiler
   judgments or indexing generated/ambiguous calls.
8. Add the closed current-snapshot definition/symbol/completion surface under
   Principle 29, without server parsing or nominal filtering.
9. Run real stdio/repository E2E and broad non-security evidence, package the
   optional server, update authoritative docs, and close Gate S8.

Gate S8 is complete. Its design success criteria were:

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

### Post-Stage-8 Successor Handoff (input list; closed at Stage 8)

This section is the input manifest for a successor roadmap, not additional
stages of this one. This roadmap's charter is complete at Stage 8, and this
document is historical. A deliberately small successor roadmap ("language
quality and domain semantics") may be authored from the items below only
through a separate selection act; this handoff is not a selector. None is
selected by listing, and each may enter a future successor only through its own
design review under principles 28 and 29 and the standing proportionality rule
(named consumer, smallest truthful scope, revert-able).

**Selection act completed 2026-07-26:** the active successor is
`docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`.
It selects the prompt-calculus direction and its target-2.19 `Value`
prerequisite as stages Q0-Q4. The slimmed E0 probe remains unselected, the
parsimony candidates remain shelved, and the parked evolution roadmap remains
non-selectable.

**Amendment 2026-07-30:** the evolution follow-on roadmap is since
incorporated as the tracked E-series program (see its status header and
current-shape section). It remains not a selector, and E implementation
remains unselected pending the gates recorded there.

Provenance: items 1 and 4 are the two salvaged survivors of the parked
2026-07-22 evolution follow-on roadmap (owner decision 2026-07-24, per the
architectural critique at
`artifacts/review/roadmap-follow-on/architectural-critique.md`; boundary
invariants extracted to
`docs/design/workflow_lisp_program_search_boundaries.md`). Items 2 and 3
are the 2026-07-25 owner-directed language directions:

1. **Slimmed E0 discriminating-benchmark probe.** Eligible only after Stage 8
   closes. Scope: a bounded (order one week) experiment answering whether any
   benchmark discriminates guided program search from enumeration and
   hill-climbing baselines on this substrate, per the parked roadmap's E0
   intent but without its gate lattice or decision-record machinery. Requires
   its own small plan; a null result parks the search program permanently
   without further process.
2. **Prompt calculus direction (owner-directed 2026-07-25) — selected by the
   successor roadmap.** `docs/design/workflow_lisp_prompt_calculus.md`: a typed
   compositional prompt layer (defprompt fragments with typed slots,
   prompt-carried signatures, partial application, completeness
   checking, E4P-based prompt identity, judgment views). Subsumes the
   E4P diagnostics item below as its component 3/4. First tranche after
   its design review: defprompt + slot-discharge checking + call-site
   result derivation. Prerequisite: the opt-in transportable top value
   type (`Value`), extracted from item 3 by owner decision 2026-07-26 —
   the first tranche's loose unstated-return default cannot ship
   without it.
3. **Type-and-union parsimony candidates (owner taste direction
   2026-07-25; shelved as a workstream by owner decision 2026-07-26).**
   Not a queue. Ergonomics claims are only verifiable against real
   authoring practice, and the prompt calculus is about to reshape that
   practice, so no candidate is selected in advance. Former candidate
   (d), the opt-in transportable top value type, leaves this list
   entirely: prompt-carried signatures default unstated returns to
   `Value`, making it a prerequisite of item 2's first tranche rather
   than an ergonomics candidate. The shelved candidates — (a) a declared
   authored failure channel giving propagate-only outcomes a home
   outside nominal unions; (b) structural union coercion; (c) structural
   record admissibility; (e) `defconstraint` named constraint bundles
   (existing consumer: `std/drain`'s repeated nine-clause `:where`
   block) — re-enter only when a live consumer demonstrates the pain,
   each through its own small design under principles 28 and 29. (a)'s
   expected consumer moment is the calculus hardening phase; (b) and (c)
   are likely mooted by the union diet plus (a) and must re-justify
   against post-calculus idioms. The existing structural-constraint
   machinery (`is-record`, `has-field`, `has-union-variant`) remains the
   checker substrate for any that return.
4. **Prompt-identity diagnostics (E4P discipline) — absorbed by successor
   Stage Q3.** Apply the role-separated prompt-identity split (boundary
   invariant 8) to the existing system's diagnostics for provider hangs,
   context drift, and prompt provenance. Q3 is the sole roadmap owner of this
   delta; this handoff item must not be selected again.

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
- provider live binding v1 and the recorded-peer-messaging/static-N-member
  v1.1 amendment have shipped through Gate S7, with observation
  non-interference, fixture/real supervisor-turn-boundary, message-ledger,
  delivery-ordering, and non-forcing proofs recorded;
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
