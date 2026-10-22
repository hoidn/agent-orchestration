# Simple evaluation implementation plan

Role: selected offline implementation plan. Owner instruction: “fix these issues.
simplify the evaluation, don't complicate it” (2026-10-22).

## Goal and accepted approach

Replace prospective calibration's several brittle gates with one control-separation
check. Keep the four independent 0–2 rubric components and existing 0–8 Rating
shape. Completeness and correctness concern implemented required behavior;
correctness earns no credit when none is implemented. Scope and layering are
independent: missing behavior does not automatically zero them.

New criteria select exactly
`calibration: {"rule": "control-means-v1", "margin": 1, "error_rate": 0}`
and exactly three roles: `upstream`, `stub`, `mutant`. For each task and each
declared judge, include every declared batch and require
`mean(upstream) - max(mean(stub), mean(mutant)) >= 1`.
Every judge must pass; missing, excluded or invalid observations fail. There is
no partial-order or spread acceptance gate. Preserve spreads as descriptive
evidence. One point is a prospective separation choice, not an estimated error
probability or claim of judge reliability.

No rule identifier means the unchanged historical algorithm; unknown identifiers
are rejected. Keep historical criteria, AT/F2 evidence, V1 qualification and seed
bytes unchanged. AT remains FAIL_NOT_QUALIFIED. New rubric source requires fresh
criterion/source identities and fresh responses before a live qualification.
This task authorizes offline code, documentation and verification, not new paid
calls. Earlier unused mechanical-recovery budget does not transfer.

This makes comparison with historical scores harder and stops treating batch
spread as a failure. Raw observations remain visible. No new framework, judge
rounds, tunable tolerances, dependencies or campaign/store machinery are added.

## Scope and sequence

- [x] Review this bounded contract independently. Accepted correction: the V1
  parser rejects any explicit rule identifier; it must not silently accept a new
  or unknown rule while applying historical semantics.
- [x] Update `compare/score_absolute.orc` and the shared calibration evaluator in
  `compare/summarize.py`, including `calibration_over`; retain the old branch
  exactly for frozen criteria. Each pool/stage passes independently; combining
  pools only reports their spread and cannot rescue a failed stage.
- [x] Select the three declared controls in `compare/pool.py` and use the same
  selection for `scoring.fillers_per_batch`, adaptive and judging reservations.
- [x] Propagate rule identity, roles and acceptance through existing C1
  `qualification.py` and `qualification_measure_v2.py`. Reuse canonical
  calibration in `readout_join`; retain original component/hash/clone joins.
  Reject explicit rule identifiers in `qualification_io.calibration` (V1).
  Leave legacy `scoring.anchor_checks` and `scoring_phase2` unchanged.
- [x] Update maintained harness/driver guidance, harness README and capability
  routing. Record coordination in the measurement ledger before any necessary
  cumulative-design/C1-plan edits; do not change their unrelated gates or roadmap.
- [ ] Verify narrow tests, new-test collection, offline public orchestrator/CLI
  smoke and affected experiment/integration suites; review the diff independently.
- [ ] Integrate while preserving unrelated working changes and historical files.

## Verification contract

Cover aggregate separation despite an isolated tie/high spread, insufficient
separation against either negative, independently failing judges, missing/excluded
observations, booleans/nonfinite values and unknown rules. Verify three-control
pool capacity and reservation agreement, C1 recomputation from original rating
components and rejection of mismatched rules/roles/hashes/incomplete evidence.
Retain the historical AT-shaped P2 failure under the original criterion. Exercise
the public offline prepare → simulated orchestrator scoring → summarize → C1
ingestion path. No literal prompt assertions or paid/hidden-test runs.

## Delivery evidence

The implementation and independent code/design reviews are complete. The new
measure has no live calibration evidence and makes no ORC-versus-direct
performance claim.

- Focused changed-module verification: 249 passed; six additional AT/role/capacity
  checks passed. Modified experiment modules collected 175 tests.
- Public scorer module: 10 collected and 10 passed (55.93 s), including public
  pool preparation, actual compile/run with a local Codex stub, scan, summary
  and C1 raw-rating ingestion. Independent review reran that integration test
  and 39 focused checks successfully. No real provider was called.
- Broad comparison and structural-search suite, `python -m pytest -q -n 16
  --dist=worksteal` over their 57 test modules: 1,276 passed and two failed
  (873.06 s). Both `direct_evaluation` variants of
  `test_unsupported_parent_refuses_before_reservation_or_launch` stopped at the
  runtime's clean-checkout guard because these implementation changes were
  uncommitted. Preserve that result; rerun the admission module on the clean
  implementation commit before integration. Log:
  `/tmp/sc-simple-evaluation-broad.log`.
- All changed guide/plan links pass. The capability matrix retains two
  pre-existing REPL-anchor failures outside this scope. `git diff --check`
  passes. Independent review verified 243 historical evidence hashes; the 15
  frozen criteria, protected roadmap/boundaries and main's 21 pre-existing dirty
  tracked files are unchanged.

Clean-commit admission verification and final integration remain pending.
