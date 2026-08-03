# ES First Effectiveness Study Task 1 Review

Status: approved; ES Tasks 0–1 are complete and Task 2 is selected. Live
provider allocation remains gated on the exact Task-6 scientific-lock owner
adoption.

Reviewed implementation:

- base commit: `6ab6dae9`, tree
  `7d2daef2d1ad6941fc1aae186276956a5fbdb66c`
- implementation commit:
  `62a5c72db7a9d02814db42b275fe4de24d8abece`, tree
  `5eb5ca32743e7e261c23a282217e859d348f5c30`
- reviewed staged binary-diff SHA-256:
  `f5af2e69125e4bc8b0adebb90ee1c556d97b6df14255e2acf9668e39ec061c63`
- projection verification record:
  `experiments/orc_effectiveness/f1_es/projection-verification.json`
  (`sha256:fc05d8c5704460d08fb421961a5974ba92ce07fc340e60f6cf009ca4c5f18527`)

Ordered final-byte verdicts:

1. `ES_TASK1_SPEC_APPROVED`
2. `ES_TASK1_QUALITY_APPROVED`

## Findings resolved before approval

The reviewed candidate was corrected before the final ordered approvals to
require a strict integer `message_bytes` value and the exact projection-recipe
policy. Git verification was also made strict for reachable-object corruption,
with a regression that corrupts a reachable loose blob and requires `git fsck`
to fail closed. The specification reviewer approved the corrected exact bytes;
a distinct quality reviewer then approved the same bytes without another
change.

## Evidence and boundary

The canonical record proves the frozen source/exclusion/inventory vector, the
single-parentless projected commit and closed 2,204-object store, actual E1
refusal of the original submodule-bearing source and successful materialization
of the projection, static and dynamic import closure, and the exact ten-module
`ptycho311` baseline at 205 collected and 205 passed. The Task-1 postcommit
module passed 25 tests in 81.44 seconds; the routing/readiness control passed
112 tests in 5.99 seconds.

This approval closes only the history-free F1 projection. It does not freeze
the Task-2 task/evaluator package, adopt the proposed scientific lock, authorize
a provider-bearing ES attempt, implement E3, or make whole-repository,
effectiveness, security, isolation, or sandbox claims.
