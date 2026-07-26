# Substrate Maintenance And Persistence Parsimony Track

- **Status:** proposed track; shape owner-approved 2026-07-26. No phase is
  selected by listing: M0, M1, and M4 each require their own component plan,
  and M2 requires an accepted design, before execution.
- **Relation:** parallel substrate track beside the active
  `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`
  (Q-track). One junction: M2 consumes Q3's prompt/effect identity
  definition.
- **Predecessor context:** the completed Procedure-First Roadmap
  (`docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`)
  and its Stage 6 YAML retirement, whose served-purpose machinery this track
  deletes.
- **Owner decisions pending:** (1) adjudication of the four retained
  baseline test failures; (2) rulings on the three recorded typecheck-family
  deferred divergences; (3) M2 depth (pure-replay only, or memo-first
  resume); (4) M4 go/no-go.

## Objective

Shrink the estate and simplify the persistence model without weakening any
verification, evidence, or resume guarantee: restore a green baseline,
delete served-purpose machinery, then loosen persistence from
"execution-coupled state everywhere" toward "effects are the durable
interface" — and only then split the oversized runtime modules along the
seams that loosening defines.

## Governing Bounds

- **Deletion over refactoring.** Every phase must delete more code than it
  adds; the sole exception is M3b's identity-key field on attempt records.
- **No weakened gates.** Fixing the baseline means porting or explicitly
  adjudicating tests, never skipping them to force green. Security-relevant
  coverage (path safety, CLI safety, secrets) must survive any porting.
- **No re-litigation.** The shelved type/union-parsimony candidates, the
  unselected E0 experiment, and the parked evolution roadmap stay out;
  consumer-triggered re-entry rules are unchanged.
- **One identity.** M2/M3 must consume the Q3 identity definition, not mint
  a second one. If Q3 is unstarted when M2 is wanted, M2 waits.
- **Loud re-spend.** Any memo miss that re-pays a provider call must raise a
  named diagnostic stating which key component changed (principle 28);
  silent re-payment is a defect.
- **Module rule applied locally.** The 500-line target applies to modules a
  phase touches; no repo-wide restructuring crusade.
- **Out of scope:** WCC middle-end modules (stable), provider isolation code
  (days old; let it stabilize), dashboard, and all security surfaces.
- Each behavior change uses TDD, narrow checks before broad non-security
  checks, and ordered independent specification then quality review.

## Phase Sequence

| Phase | Work | Entry condition | Completion gate |
| --- | --- | --- | --- |
| M0 | Green baseline | none — may start immediately | bare `pytest` collects without error and passes with no retained-failure set |
| M1 | Estate shrink | M0 complete | broad non-security suite green after deletions; capability/routing docs flipped to historical |
| M2 | Persistence-parsimony design | M1 complete; Q3 identity definition accepted; owner depth decision recorded | accepted design with executable feasibility fixtures for both components |
| M3 | Persistence implementation | M2 complete | per-tranche parity gates (below) |
| M4 | Structural decomposition | M3 complete or owner-recorded M2/M3 no-go; owner M4 go decision | touched modules split along the then-current seams; full suite green; no behavior change |

## Phase M0: Green Baseline

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

Gate: broad non-security suite green; `docs/capability_status_matrix.md`,
`docs/index.md`, and design README rows for retirement surfaces flipped to
historical; deletion totals recorded.

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

The design records the owner depth decision: (a) only, or (a)+(b). It must
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
- M2 serializes after Q3 (identity junction). M3 is exclusive with any
  other work on executor, checkpoint, or resume surfaces.
- M4 is exclusive with everything touching the modules being split.

## Verification

Narrowest owning checks first; fresh command output is the only accepted
evidence; the repository's broad non-security command runs at every phase
gate; `tests/test_workflow_lisp_drain_roadmap_routing.py` runs whenever
roadmap or routing docs change. No phase is complete on inspection alone.
