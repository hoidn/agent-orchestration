# Criteria-search behavior comparison

## Inputs And Exclusions

This is an observed deterministic controller comparison using public CLI runs,
the real pinned compiler/runner, and explicitly scripted provider replies. It
does not measure research-model behavior, DAQ quality, difficulty calibration
or the truth of the fixture's named static-composition claim. No real provider
was called. Prior real-run results inform the motivating failure mode; their
files and verdicts are not rewritten or used as synthetic victories.

## Compared Versions

The original controller is preserved under
`artifacts/criteria-revision-20261023/before/adversarial.orc`; the candidate is
the active `adversarial.orc`. Exact compiled source hashes, original source
snapshots, request hashes, run states and per-phase outputs are indexed in the
[routing event trace](../../artifacts/criteria-revision-20261023/routing-event-trace.json).
The source-preimage hash map covers both entries, prompts, briefs and consumers.

## Scenario Setup

Each scenario starts in a fresh fixture workspace with its own state and
evidence. Original and revised controllers receive the same scripted reply
sequence. A round contains BUILD, CHALLENGE, paired execution, REVIEW, ANSWER
and integrity verification. Provider outputs name synthetic claims; no test
asserts literal prompt phrasing. The changed-criterion tests assert that prior
claims, positions, evidence references/digests and blockers reach both next
construction calls.

## Evidence Ledger

- **Observed:** red routes: three expected failures, one pass, 22.71 seconds;
  green routes: four passes, 25.69 seconds. Logs and complete run trees are in
  `artifacts/criteria-revision-20261023/red-routes*` and `green-routes*`.
- **Observed:** the old and new routes below follow recorded typed results;
  provider-call counts come from fixture request logs.
- **Specified:** criteria can change between new experiments, never
  retrospectively within an evaluated one; local refutations remain visible.
- **Inferred, unmeasured:** the revised prompts may produce broader criterion
  exploration by real researchers. These fixture runs cannot establish that.

## Deterministic Workflow Delta

Only a matching, eligible, intact ADVANTAGE can now terminate the search early.
Other outcomes append to history and proceed within the original round limit.
Acceptance fields, digest/claim agreement, integrity verification, malformed
provider handling and maximum four rounds remain in force. Provider judgment
selects meaningful criteria; `.orc` does not infer diversity from prose.

## Simulated Event Log

The linked JSON contains each committed phase, its output artifacts/value,
round number, terminal state and request provenance. Condensed observed routes:

| Scenario | Original route | Revised route |
| --- | --- | --- |
| Target: qualified recovery refutation, then different supported criterion | Round 1 commits COUNTEREXAMPLE and intact evidence; returns CLAIM_REFUTED. Four provider calls; second criterion never consumed. | Round 1 remains in history. Round 2 BUILD/CHALLENGE consume it; the supplied different claim receives eligible matching ADVANTAGE votes and intact evidence. DEMO_SUPPORTED, eight calls. |
| Hard: missing expert evidence for first criterion | Round 1 records NEEDS_EXPERT, false relevance and a blocker; returns INCONCLUSIVE. Four calls. | Blocker is retained. Round 2 receives the history and its separately eligible fixture claim can return DEMO_SUPPORTED. Eight calls; no earlier eligibility field is changed. |
| Simple: supported first criterion | Eligible ADVANTAGE and intact evidence return DEMO_SUPPORTED after four calls. Completed resume adds no effects. | Same outcome, call count and memoized completed resume. No added discovery phase or compulsory later round. |
| Bound: four scoped refutations | Returns CLAIM_REFUTED after the first, four calls. | Preserves all four refutations and returns INCONCLUSIVE at the limit, sixteen calls. |

## Decision Rationale

The target and hard cases directly exercise premature termination of the broader
search. The simple case establishes that useful early support is retained. The
bound case shows that repeated failures do not produce an impossibility claim
or expand the authorized round ceiling. The fixture's later favorable judgment
is supplied data, not evidence that a real model will find a better criterion.

## Comparison

The revised control allows a new criterion after a failed or expert-dependent
one and delivers the full prior record. It may use more of the existing round
allowance. A compact criteria map belongs in the existing dossier, with no
additional provider calls, typed phase or mandatory taxonomy. Updated prompt
guidance covers static checks and engineering costs as well as recovery, and
freezes each experiment's primary metric and margin before measurement.

## Assumptions And Falsifiers

Model compliance and criterion relevance remain cross-reviewed judgments.
A future authorized run that repeatedly renames the same metric, changes a
margin after results, or infers unmeasured ergonomics would falsify the intended
behavioral improvement even if all deterministic tests pass. An expert-dependent
criterion remains ineligible; another criterion does not erase its blocker.

## Regression Risks

Terminal CLAIM_REFUTED is removed from fresh outcomes; historical reports keep
their old schema and results. Future evaluation needs a new run. More rounds can
be consumed after local failures, still bounded by four and sixteen provider
sites. Synthetic fixture success does not qualify a live comparative study.

## Recommendation

**ADOPT_NARROWLY:** adopt the controller and coherent criteria-search guidance.
The complete package suite passed (37 tests), both entries compiled and passed
dry-run, the deployed smoke passed with eight fake calls and twelve confined
trials, and independent specification and quality reviews approved the change.
Do not relaunch the paid experiment or claim demonstrated improvement in model
search behavior from this comparison. Validate the report against the linked
JSON traces and the saved red/green logs. The source-preimage diff, whitespace/
JSON checks and historical-file preservation are recorded in the
[final verification](../../artifacts/criteria-revision-20261023/verification.json).
