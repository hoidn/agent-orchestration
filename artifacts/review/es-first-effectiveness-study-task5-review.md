# ES First Effectiveness Study Task 5 Review

Status: approved; Task 5 is complete. The owner-directed large-scope F1
refreeze is the next ES unit, and no live provider allocation is authorized.

Reviewed implementation:

- base commit:
  `55754da4043dc7eaef8ac385aaf6e2c528eb7e5b`, tree
  `d456188e6d5beb44708ef04b2dce179bcb114f70`
- implementation commit:
  `e5ec552d3c0b06c949f8d2186b692fa4a4b77f9a`, tree
  `1b0f0e67cdc7e3676d892fdd2245f1306f7057b7`
- reviewed staged binary-diff SHA-256:
  `6bda9528a2bc97858d6208957a515b3832d8d380e0a466c5e673547e4a49b91e`

Ordered final-byte verdicts:

1. `ES_TASK5_SPEC_APPROVED`
2. `ES_TASK5_QUALITY_APPROVED`

## Contract delivered

The reviewed controller executes the checked-in four-arm target-2.25 trial
through public `run_trial_entry` using injected deterministic provider
processes. It preserves E2 packet bytes, joins the private arm/label mapping,
accounts for every settlement and receipt, applies the closed hard-evidence
and review routes, and regenerates one deterministic report from immutable
records. Its terminal table covers 31 routes and 22 receipt slots.

The public provider-free end-to-end fixture proves four completed arms, both
zero-adjudication and one-adjudication review paths, sibling-preserving arm
failure, terminal reviewer failure, and interruption followed by the next
locked attempt ID. It never resumes an ES attempt. The fake Codex boundary is
local and deterministic; Task 5 made no real provider call and adopted no
scientific lock.

Generic prerequisite corrections preserve the same contract outside ES:

- typed imported `CallBoundary` results replay through their exact validated
  contract;
- provider attempts and phased delivery fail closed while preserving exact
  prompt, bundle, and execution-only environment authority;
- final-call evaluator drift and hard-evidence interruptions receive their
  canonical settlement-backed route IDs; and
- nested call-frame writes commit once at the aggregate root, detach mutable
  caller inputs, and preserve strict root/callee and checkpoint validation.

## Verification

Fresh focused candidate verification passed 1,048 tests in 926.59 seconds.
The final treatment-parity control passed 42 tests. The final broad
non-security gate passed **12,332 passed, 19 skipped** with five existing
multiprocessing deprecation warnings in 536.48 seconds.

An earlier broad replay had one unrelated Neovim LSP progress-notification
timeout. The exact node passed eight consecutive isolated replays, and the
unchanged final broad run passed it. No staged Task-5 file owns that LSP
surface.

## Boundary and next unit

Task 5 is complete at the implementation commit above. This review does not
freeze or adopt a prelaunch package, authorize an F1 arm, consume an attempt
ID or denominator row, or select E3 execution. Before Task 6 can freeze a
launchable package, the owner-directed large-scope F1 amendment must replace
the superseded small task, calibrate a genuine 5,000–10,000 implementation-LOC
controller-only reference product with tests and docs metered separately, and
pass its own provider-free review and owner-adoption gates.
