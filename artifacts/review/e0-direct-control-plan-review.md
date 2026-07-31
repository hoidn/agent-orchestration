# E0 Canonical Direct-Control Plan Review

Status: approved for E0-only execution

Reviewed candidate:

- commit: `b401c493a0e0c7a9614d96cd18bfb8f4fa29f494`
- tree: `291bc6130412a04ef9e3886cca23579c3fb325f0`
- plan:
  `docs/plans/2026-07-31-workflow-lisp-e0-direct-control-component-plan.md`
- plan SHA-256:
  `0e906fdf2daa06bf8d6bb9720cd71e1086174f46dda97cb8204add16aa490809`
- accepted trial-runs design SHA-256:
  `ed4b4090b71f4310e09aa59d3f347245c640c0727eceec8baf1344a14c53cf53`
- accepted E-design review SHA-256:
  `a4d68315385f659cf3d4be312ff301b312920ecc00ef0173f4c53cc3b83def6c`
- lean-pilot owner-handoff SHA-256:
  `6d814e74fa8c4c3d7c89b24e4cbaa1c8e9ea023c25ecf835bb9423df8268cf4d`

Ordered final verdicts:

1. `E0_PLAN_SPEC_APPROVED`
2. `E0_PLAN_QUALITY_APPROVED`

Review closed at `2026-07-31T11:37:45-07:00`.

## Findings resolved before approval

The proposal at `fd7648b9` was corrected at `a3d865cc` after specification
review found that successful execution alone did not prove the one-invocation
contract under the CLI's default retry policy. The corrected plan binds every
E0 execution to the existing `max_retries=0` surface and adds the opposing
retryable-failure proof.

The candidate was corrected again at `b401c493` after quality review found
that Tasks 2 and 3 could not truthfully manufacture a RED while production
changes were forbidden, and that one allocation row did not prove one
attempt. Task 1 is now the sole RED/GREEN behavior task; Tasks 2 and 3 are
expected-GREEN feasibility gates. Successful and failed fresh runs require
`last_allocated_ordinal == 1`, and completed reuse must leave allocation state
unchanged.

After those material corrections, ordered specification review was replayed
before a distinct quality review. Both approved the same exact candidate
above. No unchanged E-design, ML, M2, pilot, or successor surface was
re-reviewed.

## Approved boundary

The plan may select only E0: a target-2.23 library workflow with typed
task/model/effort inputs, exactly one composed provider boundary, and a direct
`Bool` result. It may add conformance tests and routing evidence, but no
compiler, runtime, loader, state, spec, retry-default, child-run, trial,
controller, historical selector, or E1+ behavior. E1/E2/E3 and C1/C2/C3
remain unselected.
