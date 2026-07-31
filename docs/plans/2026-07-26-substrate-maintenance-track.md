# Substrate Maintenance And Persistence Parsimony Track

- **Status:** active substrate track; shape owner-approved 2026-07-26. M0 is
  historical complete at commit `f15b888d0c4862f7e229b990255d5f34c7392591`,
  tree `8a75f24fde68b657d2f84b28aa8b4d34df5089cf`, under the reviewed
  [M0 Green Baseline Implementation Plan](2026-07-29-m0-green-baseline-component-plan.md)
  and external closure-record SHA-256
  `88f35cdd872ba9e5a9602d3e756ee81e2911c2384e74c6fa2388cdb907e2ba0e`.
  Its postcommit control passed 418 tests. M1 was selected by the externally
  reviewed Task 0 commit `4e71093d` in the
  [M1 Estate Shrink Implementation Plan](2026-07-29-m1-estate-shrink-component-plan.md).
  M1 is historical complete at commit
  `57c2604e595d22dc9d9d656409607f81b332b5f8`, tree
  `fc0fdbefe2cdd99cf0f9de604aa63582f79425ea`. Its postcommit selector passed,
  and the external closure record has SHA-256
  `b5c0624bd6759e4cf2a3d0153c42a1aa9068ebcab2050c15237d9cb74b95470b`.
  ML was selected by the reviewed ML-0 commit
  `e2e39422f8fe52ad35dd6a174bc108f65bcf2050`. Phase ML is historical
  complete. ML-1 closed at commit
  `9c14dae37310755bd9cbd3de03b9256433acd9fe`, tree
  `0b149f96ace8873b0381a4cd530468b1d24a083f`; ML-2 closed at commit
  `b8783f66db4680bdec048e1b54ac14c1ae8b4d1b`, tree
  `b833b03cb91396cddf64a12cbbbc8d016cd306ad`; and ML-4 Tasks 1–4 landed
  at `c45928f4`, `b3370858`, `ed19624c`, and `758c67e0`, with final closure
  through the commit containing this record. Final controls passed 5 E2E,
  156 owning adjudication, 3 lock-control tests with 120 deselected, and
  9,714 broad non-security tests with 19 skipped and 5 warnings.
  Amendment phases ML, MC, MR and the M1 inventory extension were adopted into
  this shape 2026-07-26 by owner direction (provider-repeat cost model and
  incorporation request). Phase M2 is historical complete at its recorded
  component-(a)-only depth: the accepted
  [Pure-Result Replay design](../design/workflow_lisp_pure_result_replay.md)
  is implemented through `159a8f5e`, `5644bd73`, and `cf0490d1`, with
  completed-resume compatibility correction `ce02cd17`, under the
  reviewed
  [Pure-Result Replay Feasibility Component Plan](2026-07-30-pure-result-replay-feasibility-component-plan.md).
  Its broad non-security gate passed 9,868 tests with 19 skipped and 5
  warnings, followed by ordered final specification and quality approvals.
  M3a Tasks 1–3 landed under its reviewed
  [Pure-Result Replay Activation Component Plan](2026-07-30-pure-result-replay-activation-component-plan.md)
  after ordered `M3A_ACTIVATION_PLAN_SPEC_APPROVED` then
  `M3A_ACTIVATION_PLAN_QUALITY_APPROVED` reviews of corrected proposal
  `6e06b4c0`: root activation at `3442aef2`, fresh-frame activation at
  `b931b7b8`, and boundary locks at `8a01bc2b`. The Task 4 closure candidate
  is in progress. Its first broad gate exposed generic typed-literal,
  metadata-bearing value-document, and sparse-union replay gaps; the TDD
  correction passed the 10 original failures and a 375-test integration
  matrix. Ordered `M3A_INTEGRATION_FIX_SPEC_APPROVED` then
  `M3A_INTEGRATION_FIX_QUALITY_APPROVED` reviews approved exact
  production/unit-test diff SHA-256
  `5ae2e6c279b6e3aa36bf28920debc5d3999254533c4f8e199ffb8d88888195f3`;
  the first final quality review then found and rejected a cache-hit witness
  bypass. Its TDD correction requires the current exact visit plus either the
  exact durable shell or exact active result matching the private cache. The
  restarted final specification review then rejected that active form when a
  cursor also targeted the same node. Its TDD correction rejects the relevant
  cursor while retaining an unrelated downstream cursor, and passes 122 owner
  tests, the unchanged 259 production-shape tests, a 381-test combined matrix,
  569-test collection, a 968-test focused gate, and a 9,896-pass broad
  non-security gate with 19 skips and 5 warnings. M3a is historical complete
  at `76427bdedbbac300bbd82d45db7fa6e24a770f84`, tree
  `c5d8247ab6d47b209d14ee203513a0eda876acb1`, after restarted ordered final
  reviews and a 189-pass postcommit control. External closure-record SHA-256:
  `fa8530a87a61f484e19ed1b3d5716f6e30b2061efb4ff12769bfc0b6051cf42b`.
  MC, MR, M3b, M3c, and M4 are not selected by listing and still require
  their own component plans.
- **Relation:** parallel substrate track beside the completed
  `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`
  (Q/L tracks). The accepted Q3 identity satisfies M2's entry prerequisite,
  but selected component (a) creates no memo key or second identity;
  component (b), if its evidence threshold ever reopens, must consume Q3's
  definition. MR-4 (compiler session state) was coupled to the
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
  [M0 component plan](2026-07-29-m0-green-baseline-component-plan.md). The
  fail-closed replacement-rule pointer landed at `b21679c7`, the two ordinary
  `let-proc` route rows at `ebbcb8a3`, and the exact retirement diagnostic
  projection at `1a049620`.
- **M0 closure:** no M0 ruling remains pending. The implementation, metadata
  repairs, focused gate, authoritative bare green gate, ordered reviews,
  exact-byte commit, and 418-pass postcommit control are complete at the
  commit/tree and external closure record above.
- **Adjacent completed context:** L4 is complete at commit
  `251d9d53674e863fddae4535ea4f7022914287cd`, tree
  `e2417d395cbcabe9adaffb136759ebff3d42b677`, under external closure-record
  SHA-256
  `94b47f87035549191d698c63bf93b706740791d1e3ec45a29750e662fa4bf804`.
  Q4 is complete at commit
  `f3335637b90feb0a87ac4c538bafac7704ac0d87`, tree
  `ccec170be8757c9e4fd5ed8ece6f93b04fc03299`, under external closure-record
  SHA-256
  `85bc4ddfaa11915ad3d1066fdf736c1c5fd09ebb9ae65fc367f1038b685e258c`.
  These hashes are non-authoritative M0 context only. Task 5 neither edits nor
  re-reviews the unchanged owning Q/L routers and does not reopen either gate.
- **Later-phase defaults remain recorded:** M2's pure-result-replay-only
  default is selected;
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

| Phase | Work | Entry condition | Completion gate |
| --- | --- | --- | --- |
| M0 | Historical green baseline | complete at `f15b888d` under the reviewed [M0 component plan](2026-07-29-m0-green-baseline-component-plan.md) and external exact-commit closure | satisfied: bare `pytest` green; exact reviewed bytes committed; 418-pass postcommit control |
| M1 | Estate shrink + adopted inventory extension | selected at reviewed Task 0 commit `4e71093d` under the [M1 component plan](2026-07-29-m1-estate-shrink-component-plan.md) | satisfied at `57c2604e`, tree `fc0fdbef`; ordered reviews and postcommit selector passed |
| ML | Provider at-least-once loosening | historical complete: selected at `e2e39422`; ML-1 at `9c14dae3`; ML-2 at `b8783f66`, tree `b833b03c`; ML-4 Tasks 1–4 at `c45928f4`, `b3370858`, `ed19624c`, and `758c67e0`, with closure through the commit containing this record | satisfied: 5 E2E passed; 156 owning adjudication tests passed; 3 lock-control tests passed with 120 deselected; broad non-security suite 9,714 passed, 19 skipped, 5 warnings |
| MC | Common-helper consolidation | M0 complete; Q0-listed files deferred until Q0 closes | net LOC strictly negative; no residual private clones; touched-module suites green |
| MR | Behavior-preserving structural refactors | per-tranche: MR-5a after M0; MR-1 after ML-1; MR-2 after ML; MR-3 with/after ML-2; MR-4 Q-coordinated | golden-parity gates per tranche; MR-1..MR-3 complete before M3 starts |
| M2 | Persistence-parsimony design | historical complete: ML complete; Q3 identity accepted; owner depth fixed at component (a) | satisfied by accepted pure-result replay design, executable feasibility fixture, broad gate, and ordered final reviews |
| M3 | Persistence implementation | M3a historical complete at `76427bde`, tree `c5d8247a`; 3b/3c retain their separate gates | M3a satisfied by refreshed focused/broad evidence, ordered final review, exact closure commit, and 189-pass postcommit control; no later tranche is selected by this row |
| M4 | Structural decomposition | M3 complete or owner-recorded M2/M3 no-go; owner M4 go decision | touched modules split along the then-current seams; full suite green; no behavior change |

## Phase M0: Green Baseline

**Status:** historical complete under the reviewed
[M0 Green Baseline Implementation Plan](2026-07-29-m0-green-baseline-component-plan.md).
Its bounded implementation preserves the current fail-closed entry-bootstrap
eligibility rule. Ordered reviews approved the exact candidate, commit
`f15b888d0c4862f7e229b990255d5f34c7392591` records tree
`8a75f24fde68b657d2f84b28aa8b4d34df5089cf`, and the postcommit control
passed 418 tests. External closure-record SHA-256:
`88f35cdd872ba9e5a9602d3e756ee81e2911c2384e74c6fa2388cdb907e2ba0e`.

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

Pre-review evidence at baseline HEAD
`1a049620c01e8ee929f3d4fefec37b909b3a41ec`, tree
`274cf99dbb0554d11bdf54307d9bb8fd918a4a5a`: exact focused ownership run
**740 passed in 38.72s** (exit `0`, log SHA-256
`9e7fb0a058cffa2e3eb6e8b7a5e0d6b42ec60f7afcabb2b982ca14d03b9ace81`);
repository-standard xdist control **3 failed, 12,224 passed, 28 skipped,
90 warnings in 168.46s** (exit `1`, log SHA-256
`e78dd7862c555dec6109e3831195c750cdc44043d0508d994ff1a675a5675138`),
with all three xdist-only shared-path races disclosed and passing together in
serial isolation; authoritative bare run **12,227 passed, 28 skipped in
1229.78s** (exit `0`, zero collection errors/failures, log SHA-256
`5b63aca18c2c013395aecede0210e4b522f7c846549ed23d879505635f226810`).
The xdist result is not a pass.

Gate: satisfied. The fresh bare result, ordered final reviews, exact candidate
commit, and postcommit focused control all passed.

## Phase M1: Estate Shrink

**Status:** historical complete. The M0 prerequisite is historical
complete, and external specification-then-quality approval plus commit
`4e71093d` selected the exact Task 0 candidate in the
[M1 Estate Shrink Implementation Plan](2026-07-29-m1-estate-shrink-component-plan.md).
Tasks 0–9, final ordered reviews, the reviewed closure commit, and postcommit
control are complete at commit
`57c2604e595d22dc9d9d656409607f81b332b5f8`, tree
`fc0fdbefe2cdd99cf0f9de604aa63582f79425ea`, under external closure-record
SHA-256
`b5c0624bd6759e4cf2a3d0153c42a1aa9068ebcab2050c15237d9cb74b95470b`.
The postcommit selector passed. The component plan owns Tasks 0–9, the archive
contract, exact deletion/gate evidence, and closure binding. That reviewed
selection explicitly corrected two stale scope assumptions:
route readiness is current and only its migration coupling retires; and
“terminal-legacy-read compatibility” means the executable completed-YAML
resume fast return, not read-only report/dashboard rendering. This paragraph
supersedes the adopted inventory extension and older M1 wording only to those
two bounded extents.

Scope:

1. Retirement-machinery closeout: delete `orchestrator/retirement/`
   (`attempt_migration`, `broad_evidence`, `materialization`, `safe_io`,
   `source_bindings`, and package exports) and
   `orchestrator/workflow_lisp/procedure_identity_retirement.py` with their
   dedicated tests and fixtures. The fresh direct-estate census is 76 files /
   55,289 physical lines. Surviving mixed tests are decoupled first, and the
   217-file `docs/plans/evidence/yaml-retirement/` tree is preserved.
2. Run-store closeout: after all run-creating checks, reversibly archive every
   terminal run, the owner-dispositioned YAML/YML nonterminal set, and the
   state-less orphan. Retain the six current-format nonterminal `.orc` runs.
   Delete only the completed-YAML resume fast return; state-only report and
   dashboard views remain.
3. Adopted amendment inventory extension (amendment §M1 Inventory
   Extension): fsq queue half plus `specs/queue.md` resolution, drained
   migration-parity/post-WCC gates, two prompt gate scripts, nine redundant
   executor `frontend_kind` compatibility lines, demo wheel exclusion, and
   loader strays. Route readiness and `frontend_kind` provenance are retained
   as current behavior.

Closure candidate: commits `4e71093d`, `0f4db4fa`, `2f7d736f`, `95644b8f`,
`cb96425d`, `96a02c9f`, `3f5008fc`, and `dae747e7` implement Tasks 0–7.
The tracked deletion census is 91 files, 69,910 physical lines, and 2,769,680
bytes. The 217-file / 29,750,265-byte YAML evidence tree remains at
`8df00515e3d88a7d9783dd3ff76286cff973044b`. Collection found 9,692 tests,
selected 9,675, and excluded the owner's 17 security tests; the focused gate
passed 1,858 with one skip and the broad gate passed 9,656 with 19 skips. The
wheel contains no demo or `.pt` members. Task 8 archived 4,168 run directories
under quiet-census digest `063385d73b1f4f222ac2ebf4f44c3190363af4b74c952c8540c0ac1610136922`,
regular-file-manifest digest
`7c240c68c3a4b6067fb8315aee9a174e12e45c8cf943ad791181c3d0ffbfc213`,
and retained-six digest
`a0f6f197e1cf9d0b5c6c5f2581007c50d31658397c6fa297c89042b5e87c1c0b`.
Retirement generators and drained gates are historical; strict runtime
contracts and route readiness remain current.

Gate: satisfied. Ordered final reviews approved the exact candidate once,
commit/tree above record it, and the postcommit selector passed.

## Phase ML: Provider At-Least-Once Loosening

**Status:** historical complete. ML was selected at ML-0 commit
`e2e39422f8fe52ad35dd6a174bc108f65bcf2050`. ML-1 closed at commit
`9c14dae37310755bd9cbd3de03b9256433acd9fe`, tree
`0b149f96ace8873b0381a4cd530468b1d24a083f`, after implementation, Task 7
verification, and ordered final reviews; its postcommit control passed 72
tests. ML-2 closed at commit
`b8783f66db4680bdec048e1b54ac14c1ae8b4d1b`, tree
`b833b03cb91396cddf64a12cbbbc8d016cd306ad`. ML-4 Tasks 1–4 landed at
`c45928f4`, `b3370858`, `ed19624c`, and `758c67e0`; final closure is through
the commit containing this record. Its final controls passed 5 E2E, 156
owning adjudication, 3 lock-control tests with 120 deselected, and 9,714 broad
non-security tests with 19 skipped and 5 warnings. The normative contract
remains the owner-adopted amendment as expressed in `specs/`.

Adopted amendment phase; tranche scope and gates live in the amendment
(§Phase ML). The reviewed-plan candidates are:

- [ML-1 Provider At-Least-Once Recovery](2026-07-30-provider-at-least-once-recovery-component-plan.md):
  quarantine → guarded discard-and-rerun for ordinary, session, supervision,
  peer-group, and the subsequently landed phased route;
- [ML-2 Provider Attempt Allocator Simplification](2026-07-30-provider-attempt-allocator-simplification-component-plan.md):
  plain monotonic counter plus one run-lifetime lock; and
- [ML-4 Adjudication Rerun Recovery](2026-07-30-adjudication-rerun-recovery-component-plan.md):
  exact-scope adjudication mismatch → discard-and-rerun.

ML-3 bundle-transfer journal collapse remains deferred under the provider-
isolation/security exclusion and is not selected. Committed-result reuse is
preserved; recovery re-runs emit named re-spend diagnostics. No Q5 or L-series
gate is reopened or re-reviewed. This closure does not auto-select MC, MR, M2,
M3, or M4.

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

**Status:** historical complete at the owner-recorded
component-(a)-only depth. The accepted
[Pure-Result Replay design](../design/workflow_lisp_pure_result_replay.md)
passed the initial `M2_FEASIBILITY_SPEC_APPROVED` then
`M2_FEASIBILITY_QUALITY_APPROVED` direction gate. Under the reviewed
[Pure-Result Replay Feasibility Component Plan](2026-07-30-pure-result-replay-feasibility-component-plan.md),
Task 0 landed at `09c286dc`, the fixture/index tranche at `159a8f5e`, atomic
profile witnesses at `5644bd73`, runtime/checkpoint integration at `cf0490d1`,
and completed-resume compatibility correction at `ce02cd17`.

Fresh post-correction evidence collected 100 tests and passed the 11-module
feasibility matrix with 694 tests in 8.31 seconds (log SHA-256
`f374f391c96e6b1535bd212ac707cf77feae6f44fa630dfb4664c5b6e54b1336`).
Canonical executable IR SHA-256
`d24c09692754cf5d3846f99a694a6e108013ee0a6764878a7f5a1101c7f224cc`
and runtime-plan SHA-256
`1857767685cf7e67d43acbb819105eb8ce9e5b6b62fc720bffef7ca365762bbb`
are equal across profiles. Outputs, artifacts, diagnostics, and settlement have
exact parity; replay calls are `[E1, E2]`, E1 executes exactly once, historical
pure bundles count 2, replay pure bundles count 0, and A/B replay rows are exact
shells. Equivalent resumed samples reduce durable leaves from 80 to 72
(8 fewer; 10.0%), `state.json` from 4,975 to 4,636 bytes (339 fewer;
6.814070%), and run-owned sidecars from 26,452 to 15,561 bytes (10,891 fewer;
41.172690%).

The public historical-profile CLI smoke completed with output `count=3`,
`label=tick`, and no `result_persistence_profile` in state. Source change from
Task 0 through the Task 3 correction is orchestrator +3,518/-84 across 12
files and tests +5,911/-15 across 12 files, total +9,429/-99 across 24 files
(numstat log
SHA-256
`e8144fdb40bf2ab36a9abb197fb18bd9e8672004e54ee5e82026ab829aff037c`).
The first broad candidate passed 9,867 tests with 19 skipped and 5 warnings but
exposed one completed-resume evidence-revalidation regression. Correction
`ce02cd17` passed ordered specification then quality review, 160
affected-module tests, and the post-correction 694-test feasibility matrix.
The routing selector passes 67 tests in 1.48 seconds. The corrected broad
non-security gate passed 9,868 tests with 19 skipped and 5 warnings in 147.90
seconds (log SHA-256
`76308a56635e67d21a84f1254b812e41d4eebde7dc2444fe9cb6dd31a1e7c637`).
Ordered final review passed `M2_FEASIBILITY_FINAL_SPEC_APPROVED` then
`M2_FEASIBILITY_FINAL_QUALITY_APPROVED` against the same closure bytes. M3a
Tasks 1–3 landed under the separately reviewed activation plan at
`3442aef2`, `b931b7b8`, and `8a01bc2b`.

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

- **3a** Pure-result elision: implementation closure candidate under the
  reviewed
  [activation component plan](2026-07-30-pure-result-replay-activation-component-plan.md).
  Tasks 1–3 landed at `3442aef2`, `b931b7b8`, and `8a01bc2b`. The supported
  automatic creation policy now selects the exact profile for typed public
  `.orc` new-root/force-restart creation and fresh non-iterative typed Workflow
  Lisp children. Generic initialization remains explicit opt-in; ordinary
  resume, existing roots/frames, non-Workflow-Lisp callees, iteration-owned
  frames, and recurrent pure state keep historical/durable behavior. A fresh
  retry selects without predecessor mutation.

  Fresh public-route measurement records exact output/artifact/diagnostic/
  settlement parity with explicit-profile and historical controls. Against the
  route-identical absent-profile control, durable leaves decrease 106 → 98,
  `state.json` 6,539 → 6,199 bytes, and sidecars 622,815 → 611,912 bytes
  (external log SHA-256
  `4017d50f06235cb2a3687d57f45de3abff2b737f66afe1fb574b5fc8e20036ea`).
  The pre-correction Task 4 candidate passed its focused/routing gate. Its
  first broad run recorded 10 failures, 9,865 passes, 19 skips, and 5 warnings
  and exposed the generic replay gaps now covered by the TDD correction. The
  correction passed ordered specification then quality review against exact
  diff SHA-256
  `5ae2e6c279b6e3aa36bf28920debc5d3999254533c4f8e199ffb8d88888195f3`.
  The pre-final-review candidate collected 563 tests, passed 67 routing tests
  and 962 focused tests, then passed 9,890 broad non-security tests with 19
  skipped and 5 warnings (broad log SHA-256
  `8787a8eb3411c707cd636287b56b68945d80ba63e83ecb82fa5648aff7d356d7`).
  The immediately prior replay's only failure was the candidate-owned stale
  routing assertion; its 9,889-pass/1-failure log is retained at SHA-256
  `2b36ceadfc64a435be41b8faf45cc2030068a9a66d86fca16a89165f2eccc369`.
  The first final specification review approved exact diff `d03dc333`, but the
  following quality review correctly rejected a cache-hit witness bypass. The
  TDD correction now rejects missing/non-one visits and missing/malformed
  cache-hit rows while retaining the exact active-result view used during
  fresh execution. Restarted specification review then rejected a relevant
  running cursor beside that active result. The TDD correction rejects a cursor
  targeting the same presentation/step identity while preserving an unrelated
  downstream cursor. It passes 122 owner tests, the unchanged 259 production
  shapes, 569-test collection, 968 focused tests, and a refreshed 9,896-test
  broad non-security gate with 19 skipped and 5 warnings in 147.72 seconds
  (log SHA-256
  `d4324439f68b6881f353d5e3f436cc4d460f4728b0359d3b8297a795284efb6d`).
  Restarted ordered final review approved exact complete diff
  `a4a25c19851dc2ea13ccc9e736069a97b9cbe637bfb3ed62e7c28b4d7b8c8b55`;
  commit `76427bde`, tree `c5d8247a`, records those bytes and its postcommit
  owner-plus-routing control passed 189 tests. M3a is historical complete.
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
