# Substrate Maintenance And Persistence Parsimony Track

- **Status:** active substrate track; shape owner-approved 2026-07-26. M0 is
  selected and in progress under the reviewed
  [M0 Green Baseline Implementation Plan](2026-07-29-m0-green-baseline-component-plan.md).
  M1 remains ineligible until M0's green gate closes and then requires its
  own reviewed component plan before selection. Amendment phases ML, MC, MR
  and the M1 inventory extension were adopted into this shape 2026-07-26 by
  owner direction (provider-repeat cost model and incorporation request). No
  other phase is selected by listing: ML, MC, MR, and M4 each require their
  own component plan, M2 requires an accepted design, and ML additionally
  requires its ML-0 reviewed spec amendment before execution.
- **Relation:** parallel substrate track beside the active
  `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`
  (Q/L tracks). Two junctions: M2 consumes Q3's prompt/effect identity
  definition, and MR-4 (compiler session state) is coupled to the
  L-series — later L stages, notably L3's per-source entry selection,
  raise per-process compile pressure on exactly the reentrancy MR-4
  fixes, so MR-4 schedules in coordination with both series and should
  complete before or with L3.
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
- **Recorded M0 rulings and landed work:** the three deleted-loader safety
  test modules were ported at `e1594634`; the retained baseline output/IR
  failures were adjudicated at `b16a49f5`; and the entry-bootstrap refusal
  was named at `76452fdc`. The three typecheck-family rulings are closed:
  the extern-operand narrow/wide fork at `6620f186`, the dead
  semantic-adapter local at `ae67ea16`, and `let-proc` hidden-context
  equivalence at `6182ae48` plus `7dcd177c`. Their evidence and dispositions
  are recorded in the
  [M0 decision brief](../reports/2026-07-26-m0-decision-brief.md) and the
  reviewed
  [M0 component plan](2026-07-29-m0-green-baseline-component-plan.md).
- **Remaining M0 closure:** no M0 ruling remains pending. Only bounded M0
  closure work remains pending under the reviewed component plan: the
  replacement-rule diagnostic pointer, two landed `let-proc` fixture route
  rows, the retirement-artifact diagnostic projection, and the green-baseline
  gate and final reviews.
- **Later-phase defaults remain recorded, not currently pending:** M2 defaults
  to pure-result replay only unless its named re-entry evidence appears; M4
  defaults to the bounded executor/validation split if its entry conditions
  still hold; ML-3 remains deferred until the provider-isolation freeze lifts;
  and neutral-IR boundary redraw remains outside M4 absent its own accepted
  design.

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

- **Deletion over refactoring.** Every phase must delete more code than it
  adds; the recorded exceptions are M3b's identity-key field on attempt
  records and MR-4's compiler session objects.
- **No weakened gates.** Fixing the baseline means porting or explicitly
  adjudicating tests, never skipping them to force green. Security-relevant
  coverage (path safety, CLI safety, secrets) must survive any porting.
- **No re-litigation.** The shelved type/union-parsimony candidates, the
  unselected E0 experiment, and the parked evolution roadmap stay out;
  consumer-triggered re-entry rules are unchanged.
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

| Phase | Work | Entry condition | Completion gate |
| --- | --- | --- | --- |
| M0 | Green baseline | selected and in progress under the reviewed [M0 component plan](2026-07-29-m0-green-baseline-component-plan.md) | bare `pytest` collects without error and passes with no retained-failure set |
| M1 | Estate shrink + adopted inventory extension | completed M0 green gate; own reviewed component plan selected | broad non-security suite green after deletions; capability/routing docs flipped to historical |
| ML | Provider at-least-once loosening | M1 complete; Q0 implementation gate passed; ML-0 spec amendment reviewed and landed | amendment per-tranche gates; kill-mid-provider crash-resume E2E green; broad non-security suite green |
| MC | Common-helper consolidation | M0 complete; Q0-listed files deferred until Q0 closes | net LOC strictly negative; no residual private clones; touched-module suites green |
| MR | Behavior-preserving structural refactors | per-tranche: MR-5a after M0; MR-1 after ML-1; MR-2 after ML; MR-3 with/after ML-2; MR-4 Q-coordinated | golden-parity gates per tranche; MR-1..MR-3 complete before M3 starts |
| M2 | Persistence-parsimony design | ML complete; Q3 identity definition accepted; owner depth decision recorded | accepted design with executable feasibility fixtures for both components |
| M3 | Persistence implementation | M2 complete | per-tranche parity gates (below) |
| M4 | Structural decomposition | M3 complete or owner-recorded M2/M3 no-go; owner M4 go decision | touched modules split along the then-current seams; full suite green; no behavior change |

## Phase M0: Green Baseline

**Selection:** selected and in progress under the reviewed
[M0 Green Baseline Implementation Plan](2026-07-29-m0-green-baseline-component-plan.md).
Its bounded work preserves the current fail-closed entry-bootstrap eligibility
rule and does not begin or prepare M1.

Scope:

1. The three collection-broken modules
   (`tests/test_at61_at62_wait_for_path_safety.py`, `tests/test_cli_safety.py`,
   `tests/test_secrets.py`) import `orchestrator.loader`, deleted with the
   YAML parser at `827a1eab`. Port each test to the current typed pipeline
   entry points; retire a test individually only when its behavior is
   YAML-parser-specific, with rationale recorded per test.
2. Adjudicate the four retained baseline failures: fix, or formally retire
   with recorded rationale. After M0 no gate may use a
   known-failure-set comparison.
3. Execute `docs/plans/2026-07-23-refusal-diagnosability-fixes-plan.md`
   (fully specified; three tasks).
4. Resolve the three recorded typecheck-family deferred divergences
   (extern-operand narrow/wide fork; dead semantic-adapter local; let-proc
   hidden-context gate) per owner rulings; each is a small fix once ruled.
5. Remove the inert capture-window commit hook and its closed marker file.

Gate: fresh `pytest` output showing clean collection and a green run (or an
explicit, minimal, per-test-adjudicated skip list), committed as evidence.

## Phase M1: Estate Shrink

**Eligibility:** ineligible and unselected while M0 is in progress. M1 requires
the completed M0 green gate and its own reviewed component plan before
selection.

Scope:

1. Retirement-machinery closeout: delete `orchestrator/retirement/`
   (broad_evidence, attempt_migration, materialization, state_store,
   source_bindings) and
   `orchestrator/workflow_lisp/procedure_identity_retirement.py` with their
   tests and fixtures (~19k lines). Preconditions verified in the component
   plan: no live imports outside the deleted set, CLI surface pruned,
   retirement evidence confirmed recorded under
   `docs/plans/evidence/yaml-retirement/`.
2. Run-store closeout: archive terminal runs in `.orchestrate/runs`
   (~4,200), explicitly close or annotate the ~90 nonterminal legacy runs,
   then delete the terminal-legacy-read compatibility path.
3. Adopted amendment inventory extension (amendment §M1 Inventory
   Extension): fsq queue half plus `specs/queue.md` resolution, the
   drain-gate CLI cluster, the two gate scripts, `frontend_kind` vestiges,
   demo packaging, and loader strays.

Gate: broad non-security suite green; `docs/capability_status_matrix.md`,
`docs/index.md`, and design README rows for retirement surfaces flipped to
historical; deletion totals recorded.

## Phase ML: Provider At-Least-Once Loosening

Adopted amendment phase; tranche scope and gates live in the amendment
(§Phase ML): ML-0 normative spec amendment, ML-1 quarantine →
discard-and-rerun, ML-2 allocator simplification to a plain counter plus
one run-lifetime lock, ML-3 bundle-transfer journal collapse (enters only
under a recorded owner exception to the isolation freeze), ML-4
adjudication-resume re-run. Committed-result reuse is preserved; recovery
re-runs emit named re-spend diagnostics.

## Phase MC: Common-Helper Consolidation

Adopted amendment phase; scope and gates in the amendment (§Phase MC):
one `orchestrator/_common/` package (atomic IO, canonical digests, scalar
validation, status/type predicates) replacing ~60 drifted clone sites; net
LOC strictly negative.

## Phase MR: Behavior-Preserving Structural Refactors

Adopted amendment phase; tranche scope and gates in the amendment
(§Phase MR): MR-1 provider-family descriptor parametrization, MR-2 attempt
pipeline and step-loop extraction (M4 prep), MR-3 call-frame lifecycle
unification, MR-4 compiler session state (Q-track-coordinated; recorded
deletion-bound exception), MR-5 scoped error-hygiene rider.

## Phase M2: Persistence-Parsimony Design

One design document with two components, each with an executable
feasibility fixture:

- **(a) Pure-result replay.** Stop persisting pure node results; resume
  recomputes them deterministically from persisted effect results
  (principle 27; shared golden vectors). Semantics unchanged; ledger
  shrinks; resume-compatibility checking narrows to effect boundaries.
- **(b) Effect-identity memo keys.** Key each completed provider/command
  attempt by call identity — composed prompt identity (Q3) plus input
  digests plus call policy. Resume becomes memo-first: re-execute the
  graph, hit the memo for every matching key, re-pay only misses, each
  miss named. Positional resume remains as fallback during transition.

The design records the owner depth decision: (a) only, or (a)+(b); (b)
presupposes the adopted at-least-once contract (amendment §Target
Contract). It must
state what (b) supersedes (the positional resume-compatibility machinery's
runtime role) and what it must not touch (live regions are non-replayable
and remain region-scoped; evidence records remain append-only; workflow
public boundaries remain durable and typed).

## Phase M3: Persistence Implementation

Tranches, each with RED fixtures and its own gate:

- **3a** Pure-result elision. Gate: golden-run byte parity on diagnostics,
  artifacts, and settlement results between persisted and recomputed
  execution; measured ledger reduction recorded.
- **3b** Identity keys: dual-write first (no behavior change), then
  memo-first resume behind a flag, then default flip. Gate at each step:
  resume parity on recorded fixture runs, plus one real interrupted-run
  resume with fresh output; named `memo_miss` diagnostics proven by
  fixture.
- **3c** Loop-state checkpoint elision; mid-loop resume via replay+memo.
  Gate: mid-list and mid-drain resume fixtures pass with no per-iteration
  checkpoint writes.

## Phase M4: Structural Decomposition

Split `orchestrator/workflow/executor.py` (10.1k lines) and
`orchestrator/workflow/validation.py` (6.7k lines) along the seams M3
stabilizes — effect execution, replay/memo, region runtime, settlement —
using the owner-module extraction method proven by the typecheck-family
completion plan. Behavior-preserving only; full suite green; no new
abstractions beyond the module boundaries themselves.

## Concurrency Rules

- M0 and M1 touch test, retirement, run-store, and hook surfaces only; they
  may interleave with Q0–Q2, which touch frontend/prompt surfaces. Commits
  stage explicit paths; the standing benign-delta absorption regime covers
  concurrent doc edits.
- ML, MR-1..MR-3, and MR-5b/c touch executor/resume/state surfaces: they
  enter only after the active Q0 implementation gate (Q0's plan protects
  `state.py`, `provider_attempts.py`, `prompt_dependency_evidence.py`,
  `call_frame_state.py`, and `providers/`), run strictly before M3, and may
  overlap the design-only M2 window. MC may interleave with M1/ML but
  defers call-site migration in Q0-listed files until Q0 closes; MR-5a may
  start after M0.
- MR-4 runs only in coordination with the Q-track — before or after Q1,
  never concurrent with Q1 elaboration churn.
- M2 serializes after Q3 (identity junction) and after ML. M3 is exclusive
  with any other work on executor, checkpoint, or resume surfaces
  (MR-1..MR-3 therefore complete before M3 starts).
- M4 is exclusive with everything touching the modules being split.

## Verification

Narrowest owning checks first; fresh command output is the only accepted
evidence; the repository's broad non-security command runs at every phase
gate; `tests/test_workflow_lisp_drain_roadmap_routing.py` runs whenever
roadmap or routing docs change. No phase is complete on inspection alone.
