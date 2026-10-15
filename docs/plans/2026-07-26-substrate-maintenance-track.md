# Substrate Maintenance And Persistence Parsimony Track

- **Status:** residual substrate roadmap; no successor tranche is selected.
  M0, M1, ML, M2 component (a), M3a and MR-4 are historical complete at their
  recorded bounded depth. [Original closure receipts](2026-07-26-substrate-maintenance-track-history.md#original-status-and-closure-ledger)
  preserve exact commits, trees, measurements, rejected candidates and reviews.
  MC terminal closure remains governed only by its valid external record below.
  Remaining MR, M3b/M3c, component (b) and M4 retain their explicit entry gates.
  ME apparatus removal is recorded at `61b7d04d`; it is not an unselected future
  deletion. No successor implementation, provider run or experiment is selected.
- **Relation:** parallel substrate track beside the completed
  `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`
  (Q/L tracks). The accepted Q3 identity satisfies M2's entry prerequisite,
  but selected component (a) creates no memo key or second identity;
  component (b), if its evidence threshold ever reopens, must consume Q3's
  definition. MR-4 (compiler session state) was coupled to the L-series and
  completed at `836721ce` before L3 closed over its reentrant compile path.
- **Adopted amendment:**
  `docs/plans/2026-07-26-provider-at-least-once-loosening-amendment.md`
  (adopted as shape 2026-07-26; execution gated per phase) records the
  owner's provider-repeat direction and the 2026-07-26 audit evidence, and
  owns tranche-level scope and gates for ML, MC, MR, and the M1 inventory
  extension.
- **Predecessor context:** the completed Procedure-First Roadmap
  (`docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`)
  and its Stage 6 YAML retirement, whose served-purpose machinery this track
  deletes.
- **Completed context:** [M0 rulings and adjacent Q/L closure evidence](2026-07-26-substrate-maintenance-track-history.md#original-m0-rulings-and-adjacent-closure-context)
  remain historical; this roadmap does not reopen those gates.
- **Later-phase defaults remain recorded:** M2's historical pure-result-replay-only
  selection remains component (a);
  its named component-(b) re-entry evidence remains absent. M4 defaults to the
  bounded executor/validation split if its entry conditions still hold; ML-3
  remains deferred until the provider-isolation freeze lifts; and neutral-IR
  boundary redraw remains outside M4 absent its own accepted design.

## Objective

Shrink the estate and simplify the persistence model without silently
weakening any verification, evidence, or resume guarantee: every loosening
is an owner-adopted contract change with its costs recorded (the adopted
at-least-once amendment carries one such recorded downgrade — per-attempt
forensic records become best-effort after crashes). Restore a green
baseline, delete served-purpose machinery, then loosen persistence from
"execution-coupled state everywhere" toward "effects are the durable
interface" — and only then split the oversized runtime modules along the
seams that loosening defines.

## Governing Bounds

These are retained bounds on separately selected substrate work. Historical
profile descriptions and phase receipts do not override
[evaluated execution](../design/workflow_lisp_evaluated_execution.md) or the
[retirement cutoff](../design/workflow_lisp_executor_retirement.md). Remaining
gates do not by themselves select implementation against the old estate.

- **Deletion over refactoring.** Every phase must delete more code than it
  adds; the recorded exceptions are M3b's identity-key field on attempt
  records, MR-4's compiler session objects, and the minimum M2/M3a
  correctness machinery required for the reviewed pure-result feasibility
  contract. The M2/M3a exception is bounded to the replay profile, exact
  completion shell, atomic progress/settlement, transient typed dependency
  index, fail-closed persistence audit, and checkpoint/replay preparation.
  That tranche must report source LOC honestly and must strictly reduce both
  durable value count and state/sidecar bytes; it does not authorize adjacent
  refactoring or speculative cache machinery.
- **No weakened gates.** Fixing the baseline means porting or explicitly
  adjudicating tests, never skipping them to force green. Security-relevant
  coverage (path safety, CLI safety, secrets) must survive any porting.
- **No re-litigation.** The shelved type/union-parsimony candidates and all
  E-series work stay out of this track; the evolution follow-on roadmap
  (incorporated 2026-07-30 as the tracked E-series program) owns E
  sequencing, including the rules that M2 design acceptance precedes
  freezing E0 persistence/evidence contracts and that MC/MR/M4 never block
  E work. Consumer-triggered re-entry rules are unchanged.
- **One identity.** M2/M3 must consume the Q3 identity definition, not mint
  a second one. If Q3 is unstarted when M2 is wanted, M2 waits.
- **Loud re-spend.** Any memo miss or interrupted-attempt recovery re-run
  that re-pays a provider call must raise a named diagnostic stating the
  cause (principle 28); silent re-payment is a defect.
- **Module rule applied locally.** The 500-line target applies to modules a
  phase touches; no repo-wide restructuring crusade.
- **Out of scope:** WCC middle-end modules (stable), provider isolation code
  (days old; let it stabilize — ML-3 enters only under a recorded owner
  exception to this freeze), dashboard, and all security surfaces.
- Each behavior change uses TDD, narrow checks before broad non-security
  checks, and ordered independent specification then quality review.

## Phase Sequence

| Phase | Present disposition | Remaining gate |
| --- | --- | --- |
| M0 / M1 / ML | Historical complete; exact receipts linked below | No fresh selection |
| MC | Implementation complete; terminal status externally resolved | Valid external closure record; absent/unreadable/mismatching means not complete |
| MR | MR-4 historical complete; remaining tranches unselected | Explicit disposition of missed pre-M3 windows before re-entry |
| M2 | Historical complete at component (a) only | Component (b) requires its named evidence threshold and accepted design |
| M3 | M3a historical complete; 3b/3c unselected | Separate re-entry, replay/memo and component gates below |
| M4 | Unselected | M3 complete or owner-recorded M2/M3 no-go, and owner M4 go decision |
| ME | Apparatus removal recorded at `61b7d04d` | No current ME selection gate; no successor selected |

- <a id="phase-m0-green-baseline"></a>[Historical M0 baseline](2026-07-26-substrate-maintenance-track-history.md#phase-m0-green-baseline)
- <a id="phase-m1-estate-shrink"></a>[Historical M1 estate shrink](2026-07-26-substrate-maintenance-track-history.md#phase-m1-estate-shrink)
- <a id="phase-ml-provider-at-least-once-loosening"></a>[Historical ML at-least-once loosening](2026-07-26-substrate-maintenance-track-history.md#phase-ml-provider-at-least-once-loosening)

M0, M1 and ML are historical complete. Their original procedures, measured
results and closure records remain [verbatim in the historical record](2026-07-26-substrate-maintenance-track-history.md#completed-m0-m1-and-ml-phase-records).
They impose no fresh baseline or re-execution selection.

## Phase MC: Common-Helper Consolidation

**Terminal status:** resolved only by the deterministic external record
defined in the reviewed
[MC Common-Helper Consolidation Component Plan](2026-07-30-mc-common-helper-consolidation-component-plan.md).
The fresh census admits exact non-security canonical, scalar-validation,
status/session-predicate, timeout, and atomic-replacement clones into one
small `orchestrator/_common/` package. Protocol-specific serializers and
validators stay local. The report/monitor run-directory and symlink-policy
row, provider isolation, dashboard, experiments/E-series, WCC middle-end, and
every other security surface remain explicitly deferred.

Tasks 0–5 landed at `786c1fe4`, `2e6e58f9`, `ff9351bb`, `390f24d0`,
`f2453d06`, and original Task 5 commit
`71f61b267300d09ec18bbfca817ad18804e79503`, tree
`fe4fade1749955d23fe58cced2ff166eb271b406`. Broad-gate compatibility
correction `a15c38623afe3da7b29a016aa44a66b726842a1c`, tree
`ac7a7bf5272928ba985ffe57bce634b08492e9e8`, passed ordered
`MC_CORRECTION_SPEC_APPROVED` then `MC_CORRECTION_QUALITY_APPROVED` review,
29 focused tests, and 671 Task-5-plus-regressions tests. The rejected broad
attempt exposed the `NAME_MAX` temporary-basename and direct-script import
regressions; the corrected rerun passed 10,111 tests with 19 skipped and 5
warnings. The exact architecture census, admitted-path manifest,
outside-manifest proof, net-negative production census, new-test collection,
both broad attempts, command, and 2,673-pass final owner union are recorded in
the component plan.

This checked-in track does not encode live review, commit, or postcommit
status. A valid
`/home/ollie/.tmp/mc-common-helper-20260730/closure-verdicts.md` binding
ordered approval, the exact unchanged commit/tree, and a passing postcommit
selector means MC is historical complete through that commit; an absent,
unreadable, or mismatching record means MC is not complete. No successor
substrate tranche is selected.

Gate: admitted production LOC strictly negative; no residual admitted private
clone; exact byte/error/status parity; finite timeout and failed-temp cleanup
both-direction tests; touched-module and broad non-security suites green; one
ordered final specification then quality review.

## Phase MR: Behavior-Preserving Structural Refactors

Adopted amendment phase; tranche scope and gates remain in the amendment
(§Phase MR). MR-4 compiler session state is historical complete at
`836721ce` and is not reopened. MR-1 provider-family descriptor
parametrization, MR-2 attempt pipeline and step-loop extraction, MR-3
call-frame lifecycle unification, and MR-5 scoped error hygiene remain
unselected. The literal pre-M3 windows for MR-1..MR-3 and MR-5b/c have passed;
they require an explicit supersession/no-go or reviewed post-M3
re-sequencing act before execution.

## Phase M2: Persistence-Parsimony Design

**Status:** historical complete at component-(a)-only depth under the
[Pure-Result Replay design](../design/workflow_lisp_pure_result_replay.md) and
[feasibility component plan](2026-07-30-pure-result-replay-feasibility-component-plan.md).
[Exact feasibility and delivery receipts](2026-07-26-substrate-maintenance-track-history.md#m2-feasibility-and-delivery-receipts)
retain their original profile, outputs, bytes, tests and approvals. The following
profile description is the historical M2 design, not an evaluated execution
state schema or an additional current executable route.

The selected design stops persisting eligible successful compiler-generated
pure-projection values and reconstructs them deterministically from validated
bound inputs and durable effect results. It keeps effects and public workflow
boundaries durable, excludes recurrent/loop state, and requires one executable
fresh/interrupted-resume feasibility fixture with both-direction failure
coverage.

Component (b), effect-identity memo keys and memo-first resume, is not selected.
It re-enters only under the M0 decision brief's named evidence: positional
invalidation causes recovery re-spend in at least three distinct post-ML runs,
or forces one full-workflow re-execution. No such evidence is recorded. If it
re-enters, it must consume Q3's composed prompt/effect identity, state what
positional machinery it supersedes, keep live regions non-replayable, preserve
append-only evidence, and keep public boundaries durable and typed.

## Phase M3: Persistence Implementation

Tranches, each requiring selection, RED fixtures, and its own gate:

- **3a** Pure-result elision: historical complete under its
  [activation component plan](2026-07-30-pure-result-replay-activation-component-plan.md).
  [Original activation and closure evidence](2026-07-26-substrate-maintenance-track-history.md#m3a-activation-and-closure-receipts)
  preserves qualification and rejection/correction rationale. This historical
  profile does not restore old-target execution or select a later tranche.
- **3b** Identity keys: not selected; requires component-(b) re-entry and an
  accepted design. If admitted, dual-write first (no behavior change), then
  memo-first resume behind a flag, then default flip. Gate at each step:
  resume parity on recorded fixture runs, plus one real interrupted-run
  resume with fresh output; named `memo_miss` diagnostics proven by
  fixture.
- **3c** Loop-state checkpoint elision: not selected because its stated
  replay+memo prerequisite is absent. If later admitted, mid-loop resume via
  replay+memo.
  Gate: mid-list and mid-drain resume fixtures pass with no per-iteration
  checkpoint writes.

## Phase M4: Structural Decomposition

M4 remains unselected. Entry requires M3 complete or an owner-recorded M2/M3
no-go, plus the owner's M4 go decision. The [historical split default](2026-07-26-substrate-maintenance-track-history.md#original-m4-estate-and-split-default)
describes the old executor/validation estate and module sizes. Any separately
selected component plan must use the then-current seams, preserve behavior and
pass its full-suite gate; the old module inventory is not a current runtime
architecture requirement. No new abstractions are selected here.

## Phase ME: Lean-Pilot Apparatus Retirement And Removal

**Status:** apparatus retirement/removal recorded at `61b7d04d`. The
[frozen-input removal notice](../../experiments/orc_effectiveness/lean_pilot/README.md)
records the deleted apparatus and retained evidence. The
[current comparison harness](../design/orc_effectiveness_comparison_harness.md)
owns maintained comparison mechanics and their calibration/quality limits.
[The original ME scope and gate](2026-07-26-substrate-maintenance-track-history.md#original-me-selection-and-deletion-plan)
remain exact history; their former `PASS_E2`/selection prerequisite is not a
pending gate or authorization for another deletion. Frozen inputs, external
evidence and locked digests remain evidence rather than machinery. This record
neither rewrites scientific outcomes nor selects a successor experiment.

## Concurrency Rules

- The recorded M0/M1 and Q0–Q2 concurrency windows are historical; those
  completed phases do not authorize new interleaved work. Separately selected
  work must stage explicit paths and account for concurrent documentation edits.
- ML is historical complete. MR-1..MR-3 and MR-5b/c did not execute inside
  their recorded pre-M3 window and remain inert pending explicit disposition;
  the stale condition is not silently treated as satisfied. MC implementation
  is complete through Task 5 plus correction `a15c3862`; Task 6 status is
  externally resolved and is not a current selection. No successor substrate
  tranche is selected.
- ME apparatus removal is recorded; its old E gate consumption is historical.
  No E-series or Q/L gate is reopened and no successor is selected.
- MR-4 is historical complete at `836721ce`; no Q/L gate is reopened.
- M2 serialized after Q3 (identity junction) and after ML. Any separately
  selected M3b/M3c work remains exclusive with other work on executor,
  checkpoint, or resume surfaces.
- M4 is exclusive with everything touching the modules being split.

## Verification

Narrowest owning checks first; fresh command output is the only accepted
evidence; the repository's broad non-security command runs at every phase
gate; `tests/test_workflow_lisp_drain_roadmap_routing.py` runs whenever
roadmap or routing docs change. No phase is complete on inspection alone.
