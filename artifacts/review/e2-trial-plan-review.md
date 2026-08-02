# E2 `trial` Component Plan Review

Status: approved for E2 execution

Reviewed candidate:

- commit: `c6046d38e53dc495270f473592a55de47731e64d`
- tree: `40c533fc0ab21230415a5ce5d84dfcc677552f51`
- plan:
  `docs/plans/2026-08-01-workflow-lisp-e2-trial-component-plan.md`
- plan SHA-256:
  `abf62404ec0f7a443a9547e9bec2c86c32941e4ffc448ef5ca437e86170a1510`
- accepted trial-runs design SHA-256:
  `ed4b4090b71f4310e09aa59d3f347245c640c0727eceec8baf1344a14c53cf53`
- adopted program-search boundaries SHA-256:
  `a42a1db72b887eb94cfa7c3fe93fe6e7269e99daa2867ccd484d16bbe0f0d41b`
- language design principles SHA-256:
  `36a4b4d5626e0d6f7c3444c49f74856a7d4d11cb3bad745e2c475b8b80fe0951`
- accepted M2 pure-result-replay design SHA-256:
  `051b6330d122faa4e3f365e979e6dc07f4e070c50cb84134a52c1d3ef71efe27`
- E1 final-review SHA-256:
  `af816ae147b4c64f737c05a11a32cbfbea8e3ceba5594e9c2717f23a66486a34`
- E1-E3 owner-selection SHA-256:
  `a3ec1dcdd0d307f4ddfb3eecca7643c175b47d2173f3ba00fc99b7aa9b243e9d`

Ordered verdicts:

1. `E2_PLAN_SPEC_APPROVED`
2. `E2_PLAN_QUALITY_APPROVED`

Review closed at `2026-08-01T17:02:03-07:00`.

## Findings resolved before approval

The proposal at `ae7a9b28` described target-2.11 score-selection primitives
as reusable even though their single-winner semantics cannot express E2
repetitions, median aggregation, failures-as-outcomes, or success-rule
disposition. It also placed evaluator-exhaustion, evidence-freeze, and
outer-parent-settlement recovery REDs in Task 7 before Tasks 8 and 9 owned
those mechanisms.

Commit `c6046d38` explicitly excludes existing single-winner selection while
retaining only neutral scorer identity, strict-output, provider-execution,
and ledger-materialization seams. It keeps child scheduling/timeouts and
child-boundary recovery in Task 7, moves evaluator/freeze recovery to Task 8,
and moves outer settlement recovery to Task 9. Because plan bytes changed,
the specification review replayed before the distinct quality review; both
approved the exact corrected candidate above.

## Approved boundary

The plan selects target-2.25 E2 only: bounded static `trial` arms over exact
E1 `run-ref` configs, generated typed completed/failed outcomes, recursively
transportable structured collection elements, coordinator-owned single-writer
lifecycles, durable reconciliation, frozen/blinded whole-run evidence,
deterministic checks before judgment, trial-owned aggregation, a verdict
artifact, and a shared experimental SDK/CLI path. Tasks 1–10 retain their TDD,
ordered-review, focused, broad non-security, smoke, and postcommit gates.

The historical execution registry/handle proposal, E2O, C1-C3, E3 behavior,
and all security/isolation work remain outside this plan. Approval does not
claim target 2.25 or `trial` is implemented.
