# Workflow Lisp Language Quality And Domain Semantics Roadmap

- **Status:** active
- **Selected:** 2026-07-26 by the owner's post-Stage-8 prompt-calculus
  direction, the `Value` prerequisite decision at `deb95c04`, the standing
  direction to continue roadmap execution without another confirmation stop,
  and the subsequent owner direction to integrate the bounded language-server
  debugging-utility recommendations without reopening Gate S8
- **Predecessor:** completed Procedure-First Roadmap Execution Sequence
  (`docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`)
- **Scope:** the Q-series `Value`/prompt-calculus direction plus a parallel
  L-series of bounded `.orc` language-server reliability, diagnostic,
  navigation, recovery, and lifecycle improvements
- **Not selected:** the parked evolution roadmap, the slimmed E0 experiment,
  the shelved type/union-parsimony candidates, and the deferred LSP frontend
  prerequisites P1–P5

## Objective

Make prompts a checked Workflow Lisp domain surface without turning types into
a mandatory taxonomy. The sequence begins with the one loose transport
contract the prompt surface needs, then lands prompt fragments in independently
reviewed tranches whose consumers already exist.

The same active roadmap now carries a bounded language-server quality track.
That track improves the trustworthiness and actionability of the implemented
Stage-8 editor surface by consuming existing compiler structure. It does not
change Workflow Lisp runtime authority, create a second analyzer, or claim that
planned L-series behavior is already implemented.

This roadmap is the separate selection act required by the predecessor's
post-Stage-8 handoff. The predecessor remains historical and complete.

## Governing Bounds

- Principle 29 is binding: types are opt-in constraints; nominal names are
  reserved for load-bearing contracts.
- Prompt completeness is structural. No compiler claim about prose quality,
  persuasion, or model compliance is permitted.
- Provider calls and procedures remain different operation kinds even when
  their parameter and result types match.
- Prompt fragments and residuals are compile-time structure, never runtime
  transport values.
- Prompt identity is role-separated and used-dependency-minimal under
  `docs/design/workflow_lisp_program_search_boundaries.md`.
- No optimization, search, evolution, fitness, or parked E-series machinery is
  part of this roadmap.
- Each behavior change uses TDD, narrow checks before broad non-security
  checks, and ordered independent specification then quality review.
- Security, safety, secrets, and provider-isolation work remain outside scope.
- Gate S8 remains complete. L-series corrections and increments are successors
  to the implemented v1 surface, not a reopening or relabeling of Stage 8.
- The language server remains a read-only consumer of production compile entry
  points. L-series work may present or index compiler-retained structure, but
  may not parse diagnostic prose, infer types independently, execute workflows,
  or create runtime/debug authority.
- Diagnostic identity, CLI/LSP compile-request parity, exact source/config
  freshness, and fail-closed navigation remain binding unless an accepted
  stage amendment explicitly changes the relevant presentation or availability
  policy without weakening compiler authority.
- P1 diagnostic accumulation, P2 reader recovery, P3 span-to-type metadata, P4
  source overlays, P5 compile caching/incrementality, and any runtime debug
  transport remain deferred. Listing their dependent features below does not
  select those prerequisites.
- A roadmap status is routing, not capability evidence. Current authoring
  guidance continues to describe v1 until the owning L stage is implemented,
  verified, reviewed, and reflected in the capability matrix.

## Selected Sequence

### Q-Series: Prompt Calculus And Domain Semantics

| Stage | Work | Entry condition | Completion gate | Status |
| --- | --- | --- | --- | --- |
| Q0 | Transportable `Value` prerequisite | Stage 8 complete; owner prerequisite decision recorded | accepted design; reviewed implementation plan; target-2.19 implementation with direct-root, loader, runtime, resume, classic/WCC, docs, and broad non-security evidence | complete — reviewed target-2.19 implementation and evidence gate closed at `020c6138` |
| Q1 | Prompt core | Q0 complete; prompt-calculus design corrected and accepted | target-gated `defprompt`, imports, closed slot kinds, fully applied named fills, exact discharge/placeholder diagnostics, prompt-carried result derivation, deterministic flattening through existing prompt composition, one migrated real consumer | complete — implementation through `af45c4f1`; exact-tree gates and ordered final reviews accepted |
| Q2 | Output-position slots | Q1 complete; existing expected-output consumer and post-attempt wiring named in the accepted design | `:out` declaration and runtime postcondition share one path contract; both-direction runtime/E2E evidence | complete — implementation through `d0bb9a1d`; clean Task-7 closure after exact `a40b536c`/`4e2c4911` boundary repair; ordered final reviews accepted |
| Q3 | Prompt identity and diagnostics | Q2 complete; E4P ownership reconciled to this stage | role-separated prompt identity and hang/context-drift/provenance diagnostics with no ambient/import noise, building on Q1's fragment-program digest | complete — target-2.22 carrier, one-render trace, content-free five-role evidence, prelaunch publication, fixed comparison, additive reports, compatibility E2E, and closure under the [reviewed implementation plan](2026-07-27-workflow-lisp-prompt-identity-diagnostics-implementation-plan.md) |
| Q4 | Judgment views | Q3 complete; a concrete generic-reviewer/panel consumer is bound | result-plus-provenance inspection value and deterministic views over the existing evidence authority; no new outcome union or report authority | implemented closure candidate under reviewed amended plan `0f21636b`; original design accepted at `d7fe4549` and Q5-era design amendment accepted at `3c21ceb4`; current binding keeps current target-2.23 phased production, adds a target-2.23 explicit-composed panel sibling, and preserves a frozen target-2.21 compatibility control; Q5 Task 14 and canonical transplant are complete; Tasks 1–8 landed through Task 8 `000bfcfe`, including Task 7 prompt-binding correction `187336f7`, and Task 9's implicit-list ecosystem correction landed at `0187392f`; external Task 9 and final ordered reviews, reviewed closure commit, and postcommit focused control remain under the [implementation plan](2026-07-29-workflow-lisp-judgment-views-implementation-plan.md) |
| Q5 | Phased contract delivery | accepted design at `872a29af`; reviewed implementation plan at `45468c55`; Q3 complete; no Q4 dependency | explicit `:delivery :phased` plus bounded literal materialization attempts; exact `T1 || T2 == C` cut; identity-v2/evidence-v3 and report-v2 distinction between canonical `C`, legacy final-prompt identity, and ordered actual deliveries; proof-authoritative failed-start T0 with one handle-free Q5 cleanup-evidence union and exact active-handle validation before projecting unchanged adapter proofs; inert pre-start binding/locator values and post-start endpoint binding; T2 cleanup-pending/finished closure with one ingress outcome; full Q2 authority with no early publication; total reason projection with non-null reason-equal summaries; ledger-only digest validation; truthful terminal resource evidence; byte-identical omitted/composed path; real review consumer | complete at `70f4a759`, tree `fec729cb`, after the post-correction broad comparison, exact delta adjudication, and external ordered `Q5_FINAL_SPEC_APPROVED` then `Q5_FINAL_QUALITY_APPROVED`; Task 13's accepted real attempt and stop/supersession provenance remain historical evidence |

### L-Series: Language-Server Debugging Utility

| Stage | Work | Entry condition | Completion gate | Status |
| --- | --- | --- | --- | --- |
| L0 | Reliability and diagnostic actionability | Gate S8 complete; current v1 behavior characterized | no-watcher `didSave` reverse invalidation, intentional structured initialization failures, visible compiler-owned notes/expansion provenance, and a content-keyed pure-projection source cache pass focused state/driver/stdio/diagnostic/cache tests plus one real stdio E2E without changing diagnostic identity | complete — reviewed implementation closes the four bounded corrections and watcher-disabled real-stdio gate |
| L1 | Authored symbols and callable signatures | L0 complete; closed navigation/completion amendment accepted | authored type/resource/transition symbols and namespace-preserving procedure/workflow signature completion use existing compiler spans/catalogs, exclude generated shapes, and retain fail-closed freshness | complete — implemented, reviewed, and repository-real stdio closure gate passed |
| L2 | Recovery-safe static completion | L1 complete; two-tier completion design and component plan accepted | dirty/pending/invalidated/failed open entries receive only the process-frozen form registry as an incomplete list; stale callables remain closed and stale/closed/unassociated entries remain empty | complete — implementation through `10e3ccc3`; ordered `L2_FINAL_SPEC_APPROVED` then `L2_FINAL_QUALITY_APPROVED` |
| L3 | Per-source entry selection | L2 complete; immutable initialization-schema amendment accepted; compile-path reentrancy proven by completed substrate MR-4 | one canonical workspace process can select an exported workflow for a named application source while compiling library entries with no selection, with exact CLI request parity and restart semantics | complete — implementation through `fc1b01ee`, `9e59929d`, and xdist-evidence correction `8c704f3f` after ordered `L3_TASK1_SPEC_APPROVED` / `L3_TASK1_QUALITY_APPROVED`, restarted `L3_TASK2_SPEC_APPROVED` / `L3_TASK2_QUALITY_APPROVED`, and final `L3_FINAL_SPEC_APPROVED` / `L3_FINAL_QUALITY_APPROVED` under the [reviewed three-task implementation plan](2026-07-28-workflow-lisp-language-server-l3-per-source-entry-selection-implementation-plan.md) |
| L4 | Diagnostic lifecycle and compile progress | L3 complete; editor evidence and the current-only diagnostic/progress design are accepted | dirty/pending diagnostic visibility follows the accepted policy without losing contribution ownership, and capability-gated serialized compile progress is balanced across completion, error, cancellation, and supersession | final-review metadata correction — design accepted after ordered `L4_DESIGN_SPEC_APPROVED` then `L4_DESIGN_QUALITY_APPROVED`; [reviewed implementation plan](2026-07-28-workflow-lisp-language-server-l4-diagnostic-lifecycle-progress-implementation-plan.md) accepted after `L4_PLAN_SPEC_APPROVED` then `L4_PLAN_QUALITY_APPROVED`; implemented through `11629551` and `0d5f7009` after ordered `L4_TASK1_SPEC_APPROVED` / `L4_TASK1_QUALITY_APPROVED` and `L4_TASK2_SPEC_APPROVED` / `L4_TASK2_QUALITY_APPROVED`; real Neovim acceptance passed in Task 3 `bdd1e822` after `L4_TASK3_SPEC_APPROVED` then `L4_TASK3_QUALITY_APPROVED`; Task 4 focused 356 passed and broad comparison has zero new failures; closure diff `c41e2e756f1d0c6bc27bbd9a8b8bbbfc57c59fc121b0bd46dc548709c286b990` received `L4_TASK4_SPEC_APPROVED` then `L4_TASK4_QUALITY_APPROVED` before commit `1f64f153`, tree `7790ee0e`; that tree received `L4_FINAL_SPEC_APPROVED`, then final quality returned `CHANGES_REQUIRED` solely for stale review-status metadata, so that exact-tree verdict does not transfer to corrected bytes; completion requires fresh ordered `L4_FINAL_SPEC_APPROVED` then `L4_FINAL_QUALITY_APPROVED`; the final verdict is an external exact-tree record and no repository byte can self-attest its own post-commit review; historical routing named `Q5_F1_F2_FIX_SPEC_APPROVED` then `Q5_F1_F2_FIX_QUALITY_APPROVED` as Q5's next gates, and both were subsequently satisfied before Task 13 closed at `bb67f680`; Q5 Task 14 subsequently closed at `70f4a759`, tree `fec729cb`, after external ordered final reviews |
| L5 | Authored reference navigation | accepted design at `b8a41172`; Q1 catalog and L1 index landed; read-only feasibility gates admitted prompt heads and only final unexpanded direct-retained `proc-ref` occurrences in non-generated, non-specialized authored owners; macro heads defer shape-wide; no L3/L4 dependency — selected under the owner-reordering rule | exact authored prompt-head and admitted proc-ref-name definition hits; macro-consumed, erased, expanded, generated-owner, specialized-owner proc-refs and every macro head remain null; existing direct procedure/`(call ...)` hits regression-locked; WCC/generated calls excluded; every hit uses the full common preflight; real stdio resolves the review workflow prompt head while its macro/proc-ref tokens remain null and its direct call stays exact | complete — implementation through `95e05c01`, `042c0bc3`, `870f7db2`, `7233138a`, and `041754e6`; durable incorporation and closure under the [reviewed implementation plan](2026-07-27-workflow-lisp-l5-authored-reference-navigation-implementation-plan.md) |

The Q-series implementation stages execute in Q-table order except for Q5's
explicit lack of a Q4 dependency. Q5's design was accepted at `872a29af`, its
implementation plan passed ordered review and committed at `45468c55`, and Q3
is complete. Q5 Tasks 1–13 are implemented through `bb67f680`; the exact
combined invalid-then-valid real-provider gate passed and stop `3fc3a09e` is
superseded historical provenance. Task 14 closed at `70f4a759`, tree
`fec729cb`, after exact broad-delta adjudication and external
`Q5_FINAL_SPEC_APPROVED` then `Q5_FINAL_QUALITY_APPROVED`; no repository byte
self-attests either verdict.
Q3's target design is accepted after ordered `Q3_DESIGN_SPEC_APPROVED` then
`Q3_DESIGN_QUALITY_APPROVED`. Its
[reviewed implementation plan](2026-07-27-workflow-lisp-prompt-identity-diagnostics-implementation-plan.md)
is accepted at `ad5474c7`; implementation landed through compiler carriage
`507e4b58`, persistence/checkpoint `a4304c91`, one-render trace `f29aab84`,
pure identity `4b03b317`, prelaunch runtime `d3e5031c`, persisted authority
`1e3b32dc`, and report projection `63eefda5`, followed by Task-7 compatibility,
documentation, and closure gates.
L0, L1, L2, L3, and L5 are complete. L2 implementation landed through `70b83f32`,
`b399c041`, `ee213a43`, and `10e3ccc3`, followed by ordered
`L2_FINAL_SPEC_APPROVED` then `L2_FINAL_QUALITY_APPROVED`. L5 completed under
the owner-reordering rule: its accepted design, reviewed implementation plan,
and landed implementation ship only prompt heads plus the narrow
direct-retained proc-ref shape. L3 was selected after MR-4 closed its
compile-path-reentrancy prerequisite at `836721ce`. Its immutable per-source
initialization target passed ordered `L3_DESIGN_SPEC_APPROVED` then
`L3_DESIGN_QUALITY_APPROVED`. Its
[three-task implementation plan](2026-07-28-workflow-lisp-language-server-l3-per-source-entry-selection-implementation-plan.md)
passed ordered `L3_PLAN_SPEC_APPROVED` then `L3_PLAN_QUALITY_APPROVED`;
implementation landed through Task 1 `fc1b01ee`, Task 2 `9e59929d`, and
Task 2's xdist-evidence correction `8c704f3f` after their ordered
specification and quality reviews. L4's editor evidence, ordered design and
plan reviews, current-only diagnostic publication `11629551`,
compile-progress implementation `0d5f7009`, and repository-real Neovim/docs
Task 3 `bdd1e822` are landed. The exact Task 4 focused selector passes 356
tests and the broad comparison has zero new failures. Task 4 closure diff
`c41e2e756f1d0c6bc27bbd9a8b8bbbfc57c59fc121b0bd46dc548709c286b990`
received `L4_TASK4_SPEC_APPROVED` then `L4_TASK4_QUALITY_APPROVED` before
commit `1f64f153`, tree `7790ee0e`. That tree received
`L4_FINAL_SPEC_APPROVED`; final quality returned `CHANGES_REQUIRED` solely for
stale review-status metadata, so that exact-tree verdict does not transfer to
corrected bytes. Completion requires fresh ordered `L4_FINAL_SPEC_APPROVED`
then `L4_FINAL_QUALITY_APPROVED` against the corrected committed tree. The
final verdict is an external exact-tree record; no repository byte can
self-attest its own post-commit review.
L5 completion did not bypass any L3 gate.
The L-series is an owner-selected
priority queue rather than a
claim that every adjacent stage has a compiler dependency on its predecessor;
it executes in L-table order unless the owner explicitly reorders it. At most
one L stage is active at a time.

One Q implementation stage and one L stage may proceed concurrently only after
their component plans record disjoint behavioral ownership. The reviewed Q5
plan does not authorize a second Q implementation stage or bypass its P0–P2
prerequisite gates.
Shared routing files—including this roadmap, `docs/index.md`,
`docs/design/README.md`, and `docs/capability_status_matrix.md`—must be updated
serially at each stage gate. A later stage may be narrowed by its accepted
design, but may not absorb a deferred language mechanism merely because it is
adjacent.

A parallel substrate track
(`docs/plans/2026-07-26-substrate-maintenance-track.md`) runs beside this
roadmap. Its M0/M1 hygiene-and-deletion phases touch disjoint surfaces and may
interleave with Q0–Q2 and the L-series under the same explicit file-ownership
rule. Its M2 persistence-parsimony design consumes Q3's identity definition as
a second consumer (memo keys). Q3 remains authored and gated here; neither the
substrate track nor the L-series may mint a second prompt/effect identity
definition, and this roadmap absorbs no substrate work.

## Stage Q0: Transportable `Value`

**Status:** complete. The reviewed implementation and its focused,
classic/WCC, runtime, resume, normative, routing, broad non-security evidence,
failure classification, and exact staged-tree reviews are recorded in the
implementation selector below. Q1 subsequently completed through its own
reviewed implementation-plan and implementation gates.

Authority target:
`docs/design/workflow_lisp_transportable_value_type.md`.

Reviewed implementation selector:
`docs/plans/2026-07-26-workflow-lisp-transportable-value-implementation-plan.md`.

Required order:

1. independently review and accept the design;
2. draft a small implementation plan under `docs/plans/`;
3. independently review the plan;
4. implement through TDD using Subagent-Driven Development;
5. run focused contract/frontend/runtime/resume/classic-WCC checks;
6. update normative specs, capability/routing docs, and the drafting guide;
7. run the repository's broad non-security command;
8. obtain ordered final specification and quality reviews; and
9. commit exact reviewed paths plus a separate plan-only factual hash update.

Q0 must not implement `defprompt`, implicit value coercions, dynamic casts, or
field access on `Value`.

## Stage Q1: Prompt Core

Authority target:
`docs/design/workflow_lisp_prompt_calculus.md`.

**Status:** complete. The corrected design and reviewed implementation plan
landed at `53d2786b`; implementation and documentation closed through
`e9bac6fa`; the structural-test quality correction landed at `af45c4f1`.
Exact-tree collection, focused, and broad non-security evidence plus its
pre-Q1 control are recorded in the implementation plan. Ordered closing tokens
are `Q1_FINAL_SPEC_APPROVED`, `Q1_PROMPT_TEST_FIX_SPEC_APPROVED`, and
`Q1_FINAL_QUALITY_APPROVED`.

The accepted correction resolves these former review findings:

- remove procedure/provider signature interchangeability;
- define the closed kind/refinement/delivery/placeholder table;
- keep the first tranche to fully applied named slots rather than residual
  fragments;
- bind return ownership to one prompt declaration and the existing
  `ReturnSpec`/contract-rendering pipeline;
- define every refusal diagnostic and source owner;
- include one minimum `compiled_prompt_fragment_identity`: a canonical digest
  of exactly the referenced `defprompt` declarations plus normalized fully
  applied fill bindings, carried in semantic/executable IR and the receiving
  attempt's existing prompt snapshot before delivery; leave role separation,
  cross-attempt comparison, and diagnostic presentation to Q3;
- remove runtime prompt-reference and judgment-list examples not supported by
  the implemented list surface; and
- retain `:out`, residual partial application, judgment values, views, and
  optimization outside Q1.

Q1's required real consumer is the generic-reviewer pattern: one existing
extern prompt plus injected lens/target material is converted to importable
fragments without changing provider result authority or runtime behavior.

## Stage Q2: Output Positions

Authority target: an independently reviewed Q2 amendment to
`docs/design/workflow_lisp_prompt_calculus.md`, committed before the Q2
implementation plan.

**Status:** complete. The design received ordered independent
`Q2_DESIGN_SPEC_REAPPROVED` then `Q2_DESIGN_QUALITY_APPROVED`, the reviewed
implementation plan after `Q2_PLAN_SPEC_APPROVED` then
`Q2_PLAN_QUALITY_APPROVED`, implementation through `d0bb9a1d`, and the plan's
focused, broad non-security, normative, authoring, and ordered
`Q2_FINAL_SPEC_APPROVED` / `Q2_FINAL_QUALITY_APPROVED` closure. The exact
path-limited Task-7 projection was committed pre-review in mixed commit
`a40b536c` and exactly reverted by `4e2c4911`; the plan retains that bounded
incident without treating the mixed commit as reviewed:
`docs/plans/2026-07-26-workflow-lisp-prompt-output-positions-implementation-plan.md`.

Q2 owns only the `:path :out` delta. The declaration that instructs the
provider to write a path and the runtime postcondition checking that path must
share one authored slot. Caller-side delivery-mode overrides remain forbidden.
The design must bind one current expected-output consumer and demonstrate that
the new declaration removes duplicate path authority rather than adding
another copy.

## Stage Q3: Prompt Identity And Diagnostics

Authority target:
`docs/design/workflow_lisp_prompt_identity_diagnostics.md`, accepted after
ordered `Q3_DESIGN_SPEC_APPROVED` then `Q3_DESIGN_QUALITY_APPROVED` over
immutable snapshot `fdf16f362f93eae89c05600e6954a118270fe7b7` and landed in
accepted-design commit `9b2aa7ac`. The
[Q3 implementation plan](2026-07-27-workflow-lisp-prompt-identity-diagnostics-implementation-plan.md)
is reviewed and accepted at `ad5474c7`. Q3 is implemented for direct
fragment-backed target-2.22 calls and its Task-7 record owns the compatibility,
documentation, broad non-security, and ordered closure gates. The
content-addressed Q4 binding brief now selects the
`review_revise_design_docs` panel sibling, so both Q4 entry conditions are
satisfied. The Q4 design was accepted at `d7fe4549` after ordered
`Q4_DESIGN_SPEC_APPROVED` then `Q4_DESIGN_QUALITY_APPROVED`; its Q5-era binding
amendment was accepted at `3c21ceb4` after ordered amendment specification then
quality review. The corresponding reviewed amended implementation plan at
`0f21636b` passed ordered `Q4_PLAN_SPEC_APPROVED` then
`Q4_PLAN_QUALITY_APPROVED`.

Q3 is the sole roadmap owner of the E4P role-separation and diagnostic delta.
The predecessor's separate E4P list item is absorbed here and must not be
selected again. Q1's required fragment-program digest is the minimum identity
of the newly introduced compiled object; Q3 consumes it as the program-role
component rather than recomputing or replacing it.

Q3 adds role-separated identities for resolved input bindings, runtime-owned
prompt contributions, injected dependency content actually used by the
attempt, and provider policy. It excludes unused imports and ambient repository
state. Diagnostics expose those roles alongside Q1's fragment-program identity
to distinguish instruction drift, input drift, runtime-prelude drift, and
provider-policy drift in existing hang/context/provenance inspection paths.

Q3 does not introduce search or compare candidate fitness.

## Stage Q4: Judgment Views

Accepted authority:
`docs/design/workflow_lisp_judgment_views.md` at `d7fe4549`, after ordered
independent specification then quality review, plus its accepted Q5-era
binding amendment at `3c21ceb4`. The original pre-Q5 plan at `fbcba410`
passed ordered `Q4_PLAN_SPEC_APPROVED` then `Q4_PLAN_QUALITY_APPROVED`. The
reviewed amended implementation plan at `0f21636b` is the current execution
authority in
`docs/plans/2026-07-29-workflow-lisp-judgment-views-implementation-plan.md`
after fresh ordered `Q4_PLAN_SPEC_APPROVED` then `Q4_PLAN_QUALITY_APPROVED`.

Q4 may add an inspection-layer judgment value only after Q3 provides stable
attempt identity. The semantic authority remains the provider result plus
existing attempt evidence. Matrices, disagreement tables, and iteration
series are deterministic views and are never parsed back into workflow state.

The first consumer is the owner-adopted panel sibling of
`review_revise_design_docs`, bound by
`docs/reports/2026-07-27-q4-binding-decision-brief.md` and updated by the
accepted design's Q5-entry recensus. Current target-2.23 production remains
phased. A target-2.23 sibling imports the current types and fragment, makes
every review call explicitly composed, and keeps the byte-frozen target-2.21
fixture as a compatibility-only control. One child workflow per bounded
`list/map-effect` iteration lets the map carry `List[ReviewReportPath]` rather
than a list of union values. The design owns the narrowly identified WCC
composition seam that carries the existing `path/join-under` expression as a
child-call argument; it may not add runtime prompt references, higher-order
mapping, or recursive union-list transport.

Q5 Task 14 is closed and the consolidated lineage is transplanted to the
canonical working tree. The former Q4-only clone is not an implementation
base. The current binding preserves target-2.23 phased production, imports its
exports into a target-2.23 sibling whose review calls are explicitly composed,
and retains the exact pre-Q5 target-2.21 source as a compatibility-only control
that never owns imports. Q4 is an implemented closure candidate. Task 0 closed
on external census record
`sha256:1bdb694da1fda43fb0ed71e842cd16e54956b86bb5106aea380a5e17f681c7`;
Tasks 1–8 landed through Task 8 `000bfcfe`, including prompt-binding
correction `187336f7`, and Task 9's implicit-list ecosystem correction landed
at `0187392f`. Task 9 focused 643 passed; new-module collection found 91
tests; the final broad replay reported 11,072 passed, 5 failed, 24 skipped,
and 33 warnings. The failures are four inherited routing/retirement rows plus
one xdist-only read-only LSP build-digest race that passes in isolation, with
no Q4-owned failure remaining. The exact panel row in
`docs/workflow_lisp_route_readiness_registry.json` now binds its path and
surface to compile and execution evidence. External Task 9 and final ordered
reviews, the reviewed closure commit, and postcommit focused control remain.
M1 estate shrink remains outside Q4.

## Stage Q5: Phased Contract Delivery

Authority target:
`docs/design/workflow_lisp_phased_contract_delivery.md` (accepted after ordered
review at `872a29af`) and the reviewed
`docs/plans/2026-07-27-workflow-lisp-phased-contract-delivery-implementation-plan.md`
committed at `45468c55`.

**Current status:** complete at commit `70f4a759`, tree `fec729cb`. Real attempt
10 passed the unchanged combined invalid-then-valid consumer in 47.29s, and
ordered Task-13 reviews preceded `bb67f680`. The final post-correction broad
comparison retained zero new failures, focused Q5 passed 2,306 with its two
declared baseline nodes deselected, and external ordered
`Q5_FINAL_SPEC_APPROVED` then `Q5_FINAL_QUALITY_APPROVED` accepted the exact
final tree. Stop `3fc3a09e` and superseded broad candidates remain historical
provenance. Q3 is complete and Q5 has no Q4 dependency.

Deliver a fragment-backed provider call's one canonical composed prompt as two
successive turns inside one interactive provider attempt, with bounded
materialization-only correction. Target 2.23 adds explicit
`:delivery :phased` and a literal `:materialization-attempts` total in the
closed range `1..3` (default `2` when phased). Omitted delivery remains
composed. Explicit phased delivery requires the exact
`interactive_terminal_turn_queue.v1` capability and fails with named
diagnostics when it is absent or malformed; there is no capability-based
fallback.

Q5 owns a new single-attempt `PhasedProviderAttemptCoordinator`. It reuses only
the implemented interactive adapter's `start`, `offer`, `offer_close`, `join`,
and `abort` primitives plus the structural capability. It does not reuse or
claim ordinary-call support from the target-2.17 peer-group coordinator,
ledger, or `peer-finish`. Before Q5 implementation, P1/P2 must make the shared
production adapter accept the caller's whole-attempt deadline and return one closed
`InteractiveTerminalStartOutcome`: successful start carries the exact handle;
failed start carries `none|possible_or_allocated`, exact
`not_required|completed|incomplete` cleanup, provider-zero-survivor truth, and
the exact no-allocation or failed-cleanup proof. A missing handle proves
nothing. Production `interactive_terminal_start_cleanup_incomplete` maps to
possible-or-allocated/incomplete/false and truthful T0 failure. The extension
must preserve target-2.17 peer behavior and prove initial, retry, and close
offers when remaining budget is below the configured adapter timeout.

The coordinator partitions one canonical composed rendering as exact byte
slices `T1 || T2 == C`, accounts for runtime protocol/submit/diagnostic frames
outside `C`, validates the Q2 expected artifacts and structured bundle jointly
on every submit, retries only the materialization turn within the same provider
attempt, freezes the valid candidate, closes and joins naturally, then
publishes once. Invalid submissions embed complete content-free candidate
digest manifests and clear only preflight-absent bound candidate paths.
After natural join the lifecycle enters `JOINED_PENDING_COMMIT`; restoration
or state-commit failure ends failed without aborting the terminal handle and
retains candidates only as non-authoritative evidence. Receipt of a validated
natural proof is the irreversible in-memory transition before
`join_succeeded` evidence. Submit ingress is disabled, drained, closed, and
joined before join/publication. The closed T0–T4 terminalizer splits T2 into
cleanup-pending T2a and cleanup-already-finished T2b, emits exactly one cleanup
outcome overall, and permits at most one ingress start plus one finished-or-
failed outcome. `ingress_shutdown_failed` truthfully records incomplete
endpoint proof; post-proof failure makes zero abort/cleanup calls.

Before provider start, the opaque submit binding and candidate endpoint
locator are immutable inert process-local values only: they reserve no
address and create no socket, listener, worker, or endpoint resource. T0
discards them with zero coordinator-owned endpoint resources. Actual address
binding and endpoint allocation begin only after successful start; an address
race remains `submit_endpoint_allocation_failed` and follows the post-start
endpoint terminalizer. The ledger's one `provider_cleanup_proof` slot is
exactly
`null|NoBackendAllocationProof|PhasedFailedCleanupEvidence`, with
status-selected handle-free members and null limited to enumerated post-start
no-projection or invalid-handle-proof cases. Failed start constructs the
handle-free evidence directly because no handle exists. Post-start abort still
returns the unchanged handle-bound target-2.17 `FailedCleanupProof`; the
coordinator validates exact active handle identity before projecting its five
content-free fields, and missing/mismatched proof identity fails closed without
becoming ledger evidence.

Q5 preserves compiled Q1/Q2 fragment identities and composed-call Q3
attempt-identity-v1/functional-v2 evidence. Target 2.23 phased calls require
the landed/accepted Q3 substrate and add attempt identity v2 plus functional
evidence v3: canonical `C` is separate from exact ordered
task/materialization/retry delivery rows, and the fixed report-v2 amendment
uses explicit version and nullable legacy/canonical/actual-delivery fields
without calling `C` a delivered prompt.

One closed content-free `provider_prompt_phase_ledger.v1` sidecar records
canonical JSONL lifecycle rows, embedded complete candidate manifests, closed
validator precedence, before/during deadline diagnostics, and total
reason/value/source projection. Every diagnostic summary is the exact reason
token and is never null. Offline digest validation partitions every field into
a ledger-recomputable seal or opaque equality/order-bound reference and never
opens external bytes. The ledger and new attempt evidence are neither result
nor resume authority. Interrupted nonterminal visits use current sticky
quarantine semantics.

Q5 design, plan, prerequisites, and implementation through Task 13 are landed.
The evidence-surfacing and terminalization corrections after activation are
incorporated in the `bb67f680` lineage. The unchanged combined
invalid-then-valid real-provider gate then passed in one client, and ordered
Task 13 reviews approved the exact consumer/harness delta. The former
`3fc3a09e` stop remains in the implementation plan as explicitly superseded
history rather than current routing authority. Task 14 now owns
normative/routing closure, the fresh post-`5d8a3151` broad replay, exact
broad-delta adjudication, and external final exact-tree reviews.

## Stage L0: Reliability And Diagnostic Actionability

**Status:** complete. The content-keyed cache, one-probe save observer,
structured initialization failure mapping, visible compiler-owned diagnostic
notes/roles, and watcher-disabled real-stdio importer gate are implemented.
The broader MR-4 session-state refactor and P1–P5 remain separate.

Authority targets:
`docs/design/workflow_lisp_language_server.md` and
`docs/design/workflow_lisp_frontend_specification.md` §76.1.

Before implementation, write a bounded component plan that preserves one
authoritative disk probe per save and accepts the small presentation amendment
needed to make ordered diagnostic notes visible. Characterization must also
determine whether the file-content cache at `lowering/pure_projection.py:485`
is content-addressed or path-keyed: path-keyed caching in a long-lived server
process can serve stale content to a recompile the freshness layer correctly
triggered. If path-keyed, a minimal content-keyed correction joins L0's
reliability scope; the broader session-state refactor remains the substrate
track's MR-4. L0 otherwise owns exactly three changes:

1. Route a clean `didSave` snapshot through the existing reverse-revision
   observer so a changed imported source invalidates and schedules every
   trustworthy importer even when the client sends no watched-file
   notification. Avoid a second generation for the saved entry: if observation
   already advances it, do not apply `save_entry` again; an unchanged-content
   save must still force the existing single local save generation.
2. Translate existing structured `LispFrontendCompileError` failures from
   production initialization loading into intentional JSON-RPC invalid-params
   responses with stable diagnostic code/path evidence and no fake
   text-document diagnostic. Do not blanket-catch `Exception`, `OSError`,
   `RuntimeError`, or permission failures as client mistakes.
3. Preserve macro/helper role, call/definition role, and nullable expansion ID
   in diagnostic related-information labels, and present the compiler's
   ordered notes in the normal diagnostic message while retaining the same raw
   contribution, structured `data`, representative selection, and parity
   identity. Tests assert structure, order, and sentinel containment rather
   than freezing complete prose.

The gate includes changed and unchanged saves, dirty/unavailable dependencies,
unknown closures, diagnostic-target ownership, active-ticket cancellation,
one-probe evidence, missing/malformed initialization manifests, a
non-structured-error negative control, diagnostic aggregation, and a no-watcher
real-stdio importer E2E. Human rendering of every `form_path`, eager
`didOpen` reverse observation, multi-diagnostic recovery, unsaved-buffer
analysis, and runtime debugging are not part of L0.

## Stage L1: Authored Symbols And Callable Signatures

Authority target: an accepted closed-matrix amendment to
`docs/design/workflow_lisp_language_server.md`, reflected in the frontend
specification before the implementation plan.

**Status:** complete. The design was accepted after ordered independent
`L1_DESIGN_SPEC_APPROVED` then `L1_DESIGN_QUALITY_APPROVED`; the implementation
plan followed `L1_PLAN_SPEC_APPROVED` then `L1_PLAN_QUALITY_APPROVED`.
Implementation landed through `f1eecf65`, `ec2328dd`, `d174faf2`, and
`66163dc0`, followed by the repository-real stdio/status closure in Task 5 of
`docs/plans/2026-07-26-workflow-lisp-language-server-l1-implementation-plan.md`.

L1 may expose only compiler-retained authored structure:

- document symbols for authored enum, path, record, union, schema, resource,
  and transition definitions, in addition to the implemented module,
  procedure, and workflow symbols; and
- separate procedure, workflow, and form completion kinds with callable-root
  parameter, return, and procedure-effect details from existing signatures and
  import binding maps.

Generated, expanded, specialized, or span-ambiguous shapes remain excluded. A
procedure and workflow with the same visible label remain distinct completion
items. L1 does not add arbitrary-expression hover, type-token definition,
references, rename, signature inference, or nominal filtering.

The gate uses exact authored spans and source order, proves generated-shape
exclusion, exercises same-label procedure/workflow namespaces, and derives
details from compiler catalogs rather than LSP-owned copies.

## Stage L2: Recovery-Safe Static Completion

Authority target: the accepted two-tier completion amendment in the language
server design, frontend specification §76.1, setup guide, and drafting guide.

**Status:** complete under
`docs/plans/2026-07-27-workflow-lisp-language-server-l2-implementation-plan.md`.
The design passed independent specification review
`L2_DESIGN_SPEC_APPROVED` followed by independent quality review
`L2_DESIGN_QUALITY_APPROVED`; the component plan passed
`L2_PLAN_SPEC_APPROVED` followed by `L2_PLAN_QUALITY_APPROVED`.
Implementation landed through `70b83f32`, `b399c041`, `ee213a43`, and
`10e3ccc3`; ordered `L2_FINAL_SPEC_APPROVED` then
`L2_FINAL_QUALITY_APPROVED` close the stage.

For an open associated `.orc` entry under live initialization, the
process-frozen, target-neutral compiler-registry form heads remain available
while the entry is in a valid dirty-idle, current-pending,
dependency-invalidated, superseded, language-failed, or server-failed state.
That response is explicitly `isIncomplete=true` and contains no stale callable
from a prior snapshot. Clean/current/successful entries keep the full
implemented completion union. Configuration-stale, closed, unassociated,
unavailable, clean-idle, malformed, and index-failed entries remain empty.

Definition and document-symbol freshness do not change. L2 must not parse the
buffer, reuse a last-good callable index, schedule an unsaved compile, add
cursor/type filtering, or select P2/P4/P5.

## Stage L3: Per-Source Entry Selection

Authority target: an accepted immutable-initialization amendment to the
language server design and setup guide.

Replace the single selection applied indiscriminately to every compile entry
with a contained source-to-export selection contract, or an equivalently small
design proven against the production CLI request model. The accepted schema
must retain exactly one canonical workspace root, immutable configuration for
the process lifetime, explicit source roots, restart-on-context-drift, and
exact per-request CLI parity.

The minimum integration fixture opens one multi-export application source and
one library-only source in the same process. The application request carries
its selected workflow; the library request carries no selection; both compile
through the unchanged production Stage-3 entry point. This stage does not add
multi-root workspace support or infer an entry selection from editor focus.

Entry additionally requires proven compile-path reentrancy. The substrate
track's MR-4 compiler-session-state plan closed at `836721ce`, including
sequential multi-entry and real-LSP failure-recovery proofs with no
module-global state bleed. The structural prerequisite is therefore
satisfied; L3 must consume it without reopening that substrate.

## Stage L4: Diagnostic Lifecycle And Compile Progress

Authority target: an accepted editor-lifecycle amendment to the language
server design, based on observed client behavior rather than assumed UI
capabilities.

**Status:** final-review metadata correction. Diagnostic publication `11629551`, compile
progress `0d5f7009`, and repository-real Neovim/docs Task 3 `bdd1e822` passed
their ordered task reviews. The
[reviewed implementation plan](2026-07-28-workflow-lisp-language-server-l4-diagnostic-lifecycle-progress-implementation-plan.md)
passed ordered `L4_PLAN_SPEC_APPROVED` then `L4_PLAN_QUALITY_APPROVED`. Real
stdio and repository-real Neovim acceptance pass. Task 4's exact focused
selector passes 356 tests and its broad comparison introduces zero new
failures. Task 4 closure diff
`c41e2e756f1d0c6bc27bbd9a8b8bbbfc57c59fc121b0bd46dc548709c286b990`
received `L4_TASK4_SPEC_APPROVED` then `L4_TASK4_QUALITY_APPROVED` before
commit `1f64f153`, tree `7790ee0e`. That tree received
`L4_FINAL_SPEC_APPROVED`; final quality returned `CHANGES_REQUIRED` solely for
stale review-status metadata, so that exact-tree verdict does not transfer to
corrected bytes. Completion requires fresh ordered `L4_FINAL_SPEC_APPROVED`
then `L4_FINAL_QUALITY_APPROVED` against the corrected committed tree. The
final verdict is an external exact-tree record; no repository byte can
self-attest its own post-commit review.
The implemented target is
`docs/design/workflow_lisp_lsp_diagnostic_lifecycle_and_progress.md`, with
selection evidence in
`docs/reports/2026-07-28-workflow-lisp-l4-editor-lifecycle-probe.md`.

Diagnostics owned by a dirty or pending entry are hidden from presentation
while their exact contribution ownership remains retained. Multi-entry
deduplication, accepted-generation authority, and atomic replacement by a
current completion remain unchanged; `DiagnosticTag.Unnecessary` is not a
staleness marker.

Capability-gated LSP work-done progress wraps the serialized compile pump.
One balanced lifecycle covers coalesced work rather than one token per
generation, and terminates correctly on success, language error,
server error, close, cancellation, configuration staleness, and supersession.
L4 adds no telemetry, compile cache, parallel compiler execution, or runtime
session reporting.

## Stage L5: Authored Reference Navigation

Authority target:
`docs/design/workflow_lisp_lsp_authored_reference_navigation.md` (accepted at
`b8a41172` and incorporated into the language-server design as the owning
implemented amendment).

The implementation extends the definition index with exact authored
prompt-application heads by
joining already-retained original syntax to the typed prompt identity and
authored `defprompt` span. The projection is unique, whole-span-and-kind
checked, authored-token exact, canonical-target keyed, and fail-closed on a
missing, multiple, kind, identity, or span mismatch. It does not parse text or
resolve names in the LSP.

Read-only feasibility probes admitted only final unexpanded direct-retained
`ProcRefLiteralExpr` occurrences inside non-generated, non-specialized
authored owners. Their original exact `(proc-ref NAME)` syntax and procedure
catalog complete the canonical authored-definition join across local,
import-alias, canonical-qualified, `:only`, private, ambiguous, and legal
same-label cross-family cases. Macro-consumed, erased, generated-owner, and
specialized-owner proc-refs have no admitted final join and remain null.
Macro heads defer shape-wide because current expansion/export facts do not
retain canonical/module-qualified own-definition identity; L5 does not ship a
partial local-only macro route.

The review workflow's direct `(call ...)` callee still resolves over a
successful live stdio session. L5 added no direct-call behavior: direct
procedure and workflow calls remain regression coverage, while
WCC-reconstructed/generated calls remain excluded. Every new hit enters only
through the existing successful-current-snapshot preflight; unavailable,
unreadable, dirty, pending, dependency-invalidated, language/server-failed,
superseded, closed, unassociated, configuration-stale, source-stale,
source/configuration-stale, clean-idle, malformed, index-failed, unsupported,
ambiguous, generated, and outside-token requests remain silent null.

L5 depended only on the Q1 catalog and L1 index, had no L3/L4 dependency, and
completed under the L-series owner-reordering rule before MR-4 closed. MR-4
now satisfies L3's substrate gate. Ordered design/plan reviews, feasibility
gates, TDD, the real-stdio gate, and durable incorporation are recorded in the
[reviewed implementation plan](2026-07-27-workflow-lisp-l5-authored-reference-navigation-implementation-plan.md).
The completed surface remains limited to the admitted shapes.

## Explicitly Unselected Work

- The evolution follow-on roadmap remains parked and non-selectable.
- The slimmed E0 discriminating-benchmark probe remains eligible but
  unselected.
- Authored failure channels, structural union coercion, structural record
  admissibility, and named constraint bundles remain shelved until a live
  post-calculus consumer independently justifies one.
- Residual prompt partial application is deferred until repeated fully applied
  fragment use demonstrates the staging pain.
- Tolerant-but-loud boundary normalization — accepting a provider value
  whose type derives exactly one canonical reading, normalized with a named
  diagnostic instead of instructed-and-rejected (today's consumers: the
  relpath-spelling and schema-version guidance lines) — is eligible under
  design principle 30 (provider-attention conservation) and enters only
  via its own design act. Selection trigger: post-ML re-spend evidence
  attributing provider re-attempts to normalizable near-misses in three or
  more distinct runs, re-read under Q5 phased delivery. Q5 contains retry
  re-spend but does not remove the missing normalization, exact-literal, or
  referenced-artifact validation mechanisms and must not be credited as
  retiring this debt.
- Runtime prompt values, fragment-reference collections, type-parameterized
  fragments, semantic prompt checking, same-turn steering, and optimization
  remain outside this roadmap.
- LSP multi-diagnostic recovery, malformed-buffer partial ASTs, arbitrary
  expression hover, unsaved-buffer diagnostics/navigation, and incremental
  compilation remain deferred behind P1–P5 and require separate owner
  selection.
- Type-reference definition, complete references, and rename remain
  unselected until the compiler retains exact authored occurrence spans and a
  complete namespace-aware reference graph; the LSP must not guess from text.
- Runtime breakpoints, stepping, provider/state/artifact inspection, and
  failure streaming require a separately designed runtime/debug transport.
  They are not extensions of the compile-time LSP track.

## Verification And Closure

For each stage:

1. run the narrowest owning tests;
2. collect every new or renamed test module;
3. run adjacent tests for the contracts actually touched—Q stages include the
   relevant frontend/lowering/loader/runtime/resume lanes, while an L-only
   stage does not inherit runtime/resume selectors unless it changes those
   shared contracts;
4. run at least one end-to-end usage check; L stages require a real stdio or
   repository-real LSP E2E in addition to their unit/integration selectors;
5. update the owning design/normative specs, capability matrix, design router,
   docs index, drafting/setup guidance, and roadmap status from observed shipped
   behavior before final review;
6. run the exact broad non-security suite below in tmux;
7. classify any retained external failures against a fresh pre-stage control;
8. obtain specification approval before distinct quality approval; and
9. commit only the exact reviewed tree.

The reproducible broad command is below. The owner explicitly amended this
comparison authority on 2026-07-26, prospectively for the not-yet-executed
Q2–Q4 and L1–L4 gates, to keep every security-, safety-, secrets-, and
provider-isolation-owned module out of this roadmap's implementation and
verification scope. This amendment does not reinterpret the already closed
Q0, Q1, or L0 evidence.

```bash
pytest -q -n 16 --dist=worksteal \
  --ignore=tests/test_at61_at62_wait_for_path_safety.py \
  --ignore=tests/test_cli_safety.py \
  --ignore=tests/test_execution_safety.py \
  --ignore=tests/test_provider_isolation_attestation.py \
  --ignore=tests/test_provider_isolation_backend.py \
  --ignore=tests/test_provider_isolation_backend_identity_negatives.py \
  --ignore=tests/test_provider_isolation_bundle_broker.py \
  --ignore=tests/test_provider_isolation_candidate.py \
  --ignore=tests/test_provider_isolation_controller_lifecycle.py \
  --ignore=tests/test_provider_isolation_environment.py \
  --ignore=tests/test_provider_isolation_environment_cli.py \
  --ignore=tests/test_provider_isolation_execution.py \
  --ignore=tests/test_provider_isolation_network_preflight.py \
  --ignore=tests/test_provider_isolation_policy.py \
  --ignore=tests/test_provider_isolation_runtime_authority.py \
  --ignore=tests/test_provider_isolation_schema_resources.py \
  --ignore=tests/test_provider_isolation_workflow_continuation.py \
  --ignore=tests/test_provider_isolation_workflow_lifecycle.py \
  --ignore=tests/test_provider_launch_shim.py \
  --ignore=tests/test_secrets.py \
  --ignore=tests/test_workflow_provider_isolation_integration.py \
  -k 'not security and not secret and not isolation and not safety'
```

If a later security, safety, secrets, or provider-isolation module is added, it
is excluded by the same `-k` rule; the command itself remains the comparison
authority unless the owner amends it explicitly.

This roadmap closes when Q0–Q5 and L0–L5 satisfy their completion gates,
normative and authoring surfaces describe only shipped behavior, all twelve stage
gates have ordered approval, and routing names no active successor. Closure
does not select E0, revive any parked/shelved item, select P1–P5, or create a
runtime debugging surface.
