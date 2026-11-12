# Low-Value Test Removal Plan

**Status: Plan, executed 2026-11-11.** Owner instruction of 2026-11-11: remove about
8,000 low-value tests. This is the test half of Lane D of the
[current roadmap](2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#lane-d-delete-and-unify-background-time-boxed),
taken early. It deletes tests only; no runtime, language or spec behavior
changes. No provider spend.

**Starting point:** 18,567 collected test items in 661 modules at `7267e3c2`.
"Tests" are counted as collected pytest items, so the target is about 43% of
the suite.

## What counts as low value

| Tier | Kind | Rule |
| --- | --- | --- |
| A | Dead code | The code under test is retired or unreachable from the production CLI path: trial, adjudication, peer groups, supervision, the old IR stack and its bundles, `StateManager` mutation methods, retired targets and YAML-era surfaces |
| A | Document and prompt text | The test asserts literal document text, routing rows, approval tokens, hashes or plan statuses, or literal prompt wording |
| A | Finished history | The test checks a one-time migration that is complete, or a historical fixture kept only for it |
| A | Duplicate | Another test asserts the same thing on the same path |
| B | Redundant cases | A parametrized test with many cases on one branch; keep one case per distinct branch and boundary |
| B | Implementation detail | The test asserts how a private helper is called, and a behavioral test of the same path remains (named in the record) |
| C | Marginal | Cheap and overlapping; the overlapping test that remains is named |

Never candidates: kill, resume, crash-recovery and re-dispatch tests; memo
durability; closed-program checker soundness; validation of provider and
command results; security, confinement and credential handling; CLI
end-to-end tests; regression tests that cite a bug, unless the code is dead;
any file with another session's uncommitted changes; helper modules that
remaining tests import.

The number is a target, not a quota. If fewer than 8,000 items meet the rule,
the shortfall is reported and nothing that fails the rule is deleted to fill
it.

## Steps

1. **Classify (read-only).** Reviewers each take one group of modules and
   record every candidate: module, test or `*`, item count, tier, kind, the
   code it covered, and one line of reason.
2. **Select.** The coordinator totals the records by tier and picks tiers A,
   then B, then C until the target is met.
3. **Remove** on branch `chore/prune-low-value-tests` in its own worktree.
   Shared helpers and fixtures are removed only when nothing left imports
   them.
4. **Verify.** Collection has no errors; the remaining suite's failing ids
   are within the [Phase 0 baseline](2026-11-11-roadmap-phase-0-records-and-baseline-plan.md);
   the removal record lists every removed test with the code it covered.
5. **Merge** to `main` by fast-forward when no other session's change
   overlaps.

There is no coverage tool in this environment, so the safeguard is the rule
above plus the removal record, not a coverage comparison.

## Ledger

| Date | Entry |
| --- | --- |
| 2026-11-11 | Owner instruction received; inventory taken (18,567 items, 661 modules). Interpretation recorded: 8,000 means collected items; low value is defined by the table above. |
| 2026-11-11 | Classified by six reviewers plus a second pass of 25 cheaper reviewers on the owner's suggestion. 3,356 items met the rule; 337 were held back (historical-run views pending an owner decision, major-project script tests, security tests on dead code). The second pass added 116 items, all confirmed before removal. |
| 2026-11-11 | Removed 3,134 items (18,491 to 15,357 on a clean tree), 204 files changed, about 75,000 lines deleted. Two reviewer rows were found wrong during removal and skipped. The pruned suite's failures were within the baseline; merged as `439361d9`. The shortfall against 8,000 is reported, not filled: the rest of the suite is mostly kill and resume, confinement, checker and validation tests. |
| 2026-11-11 | Not done here: 908 closed-campaign tests are skipped by default instead of deleted (`ORCHESTRATE_CAMPAIGN_TESTS=1` runs them); about 220 historical-run tests wait on the owner's decision about the dashboard and `report`. The removal records per group are session scratch; the list of removed tests is recoverable from `git diff f0005f17 a32cef14 -- tests`. |
