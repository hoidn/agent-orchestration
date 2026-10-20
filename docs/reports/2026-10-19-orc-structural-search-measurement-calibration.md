# ORC Structural Search Measurement Calibration: Step A

**Status:** completed historical calibration record. Step A failed: RPI failed
its frozen cross-batch spread rule; PRR passed. All eight calls completed
within the approved cap 10. This report records calibration of the measure, not an ORC benefit,
candidate-quality comparison or permission for a live search campaign.

**Authority:** the [measurement plan](../plans/2026-10-19-orc-structural-search-measurement-plan.md)
and its predeclared failure branch. The owner approved A's eight calls, cap 10
(`ac58e0ba`). Runtime I is `25ca21e1476f5c060feb04a838e1a6cbf844c63b`;
criterion freeze F is `cc5464acc0aa7bebe07964f073886bfda09114ba`.
The [judge criterion](../../experiments/compare/criteria/judge-calibration.json)
has SHA-256 `5991b7ce208c53d6b33654a0d8d644574798a1eaf26826632703c7541ff87796`;
the [family amendment](../../experiments/compare/criteria/calibration-amends-5.json)
has SHA-256 `8cef38ccaf7600b9add5bb51a231e242a00796a424fa92cc5eefb1739b26498e`.
The [frozen identities](/home/ollie/sc-evidence/freeze/identities.json) and
[operator ledger](/home/ollie/sc-evidence/ledger.md) retain the complete lineage.

## Design And Controls

Two tasks, `resume-projection-integrity` (RPI) and `pure-result-replay` (PRR),
each have two batches scored by `claude-sonnet-5-5` and `gpt-5.6-terra`, both
at high effort. Each batch has four blind controls (upstream, stub, partial, mutant), five retained
fillers and one disclosed, unscored upstream reference. Fillers are disjoint
across a task's batches and selected by frozen seed 20261019, before ratings;
[pool membership](/home/ollie/sc-evidence/A/pool-membership.json) records source
and pooled patch hashes, clone IDs and mapping hashes.

Every declared judge×batch pair must satisfy P1 (upstream − stub ≥ 4), strict P2
(stub < partial < upstream) and P3 (upstream − mutant ≥ 2), with error 0. Each control's
cross-batch spread per judge must be ≤ 2. Both task pools must pass. Missing,
excluded or incomplete observations fail the declared denominator.

The original hidden-fraction construction bands failed before judge calls.
The disclosed pre-judge amendment selected the first existing semantically
adequate partials/mutants, with independent behavioral proof. All failed
attempts and fractions remain recorded. This run performs no new hidden-test
execution; fractions are construction diagnostics, not calibration endpoints.

## Anchors First

Totals below come from the harness clone-ID join. Values in each cell are
batch 0 / batch 1; totals range from 0 to 8.

| Task | Judge | Upstream | Stub | Partial | Mutant | P1/P2/P3 | Maximum spread | Pool verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RPI | `claude-sonnet-5-5` | 8 / 8 | 0 / 0 | 6 / 6 | 5 / 5 | All pass | 0 | Fail (Terra spread) |
| RPI | `gpt-5.6-terra` | 8 / 8 | 0 / 0 | 5 / 5 | 0 / 4 | All pass | 4 | Fail |
| PRR | `claude-sonnet-5-5` | 8 / 8 | 0 / 0 | 3 / 3 | 5 / 5 | All pass | 0 | Pass |
| PRR | `gpt-5.6-terra` | 8 / 8 | 0 / 0 | 2 / 3 | 6 / 6 | All pass | 1 | Pass |

The [RPI joined result](/home/ollie/sc-pools/resume-projection-integrity/A/records/results.json)
reports zero P1, P2 or P3 failures across all four pairs, but Terra gives the
same mutant patch totals 0 and 4, exceeding the frozen spread limit 2. Consequently
RPI fails and A cannot qualify the measure for this two-task scope.

The [PRR joined result](/home/ollie/sc-pools/pure-result-replay/A/records/results.json)
passes every rule with maximum spread 1. All eight predeclared judge×batch
pairs across A pass P1/P2/P3; the RPI spread failure alone makes the combined
verdict fail. The [combined readout](/home/ollie/sc-evidence/A/combined-readout.json)
retains both result hashes and the full accounting.

The coordinator read all 36 RPI reasons; the
[reason audit](/home/ollie/sc-evidence/A/resume-projection-integrity-reason-audit.json)
records exact clone IDs and result hash. Both Terra reasons identify the same
`audit_scope` early return. The second credits retained duplicate-import and
frontend-provenance behavior; the first awards zero throughout. The observed
failure is inconsistent credit for the same control across batches. It does
not show failure to notice the mutation or establish that the disclosed
reference caused the inconsistency. Explicit reference-equality assertions
were 2 for Sonnet and 1 for Terra, descriptive only; neither the assertion count
nor inspection of filler scores changes the calibration verdict. The
[PRR reason audit](/home/ollie/sc-evidence/A/pure-result-replay-reason-audit.json)
also covers all 36 reasons, bringing the total to 72. Both PRR judges identify
the mutant early return; Terra's partial scope credit differs by one across
batches. PRR also has 2 explicit reference-equality assertions from Sonnet
and 1 from Terra, descriptive only.

## Hygiene And Cost

Both RPI judge scans were manually cleared with provenance retained: Sonnet's
one hit read its own persisted tool output; Terra's one hit printed a Markdown
row containing `pytest`, without invoking tests. PRR Sonnet's five path hits
were its own session's persisted assigned-clone diff outputs, manually cleared
after checking the originating tool actions. No forbidden actual model or test
execution was found. PRR Terra's 43 hits were manually cleared: three were
printed plan lines and forty were printed assigned-clone `AGENTS.md` test
guidance. The coordinator inspected every excerpt and all 54 native commands,
with no test invocation; [action provenance](/home/ollie/sc-evidence/A/pure-result-replay-terra-action-audit.json)
and the [scan verdict](/home/ollie/sc-pools/pure-result-replay/A/records/judges/gpt-5.6-terra/scan.json)
retain that adjudication. All 40 clones passed integrity verification after
each judge, and actual metadata names only the two admitted models.
The original hits and verdict reasons remain in each pool's
`records/judges/<judge>/scan.json`; no judge was silently excluded.

| Task | Judge | Completed calls | Receipt coverage | Frozen list-price equivalent USD |
| --- | --- | --- | --- | --- |
| RPI | `claude-sonnet-5-5` | 2 | Complete | 1.6860133 |
| RPI | `gpt-5.6-terra` | 2 | Complete | 2.1607700 |
| PRR | `claude-sonnet-5-5` | 2 | Complete | 2.4690925 |
| PRR | `gpt-5.6-terra` | 2 | Complete | 1.5677380 |
| Total | Both admitted models | 8 | 8 / 8 complete | 7.8836138 |

All four judge workflows completed; the operator exited 0 after exactly eight
calls, with no hidden-test runs. Elapsed launch-to-final-completion time was
2088.687624 seconds (about 34.81 minutes). Per-judge native receipts and pricing
are retained under [/home/ollie/sc-evidence/A](/home/ollie/sc-evidence/A). These
are standard short-context list-price equivalents under the frozen table,
not billed spend; no incomplete receipt was priced as zero.

## Consequence And Prospective A′

After A's eight calls had finished, the owner prohibited further Claude
experiment launches for today, **2026-10-19 in America/Los_Angeles**. No Claude
call was active at that directive. Offline preparation may continue, but the
predeclared Sonnet/Terra A′ is blocked today and still needs separate spend
approval. No Terra-only revision or model substitution is selected; a frozen
packet for a later date would not itself authorize a launch.

A is closed as failed, so B cannot proceed under this measure. The
predeclared single revision is rubric-only without a disclosed reference,
retaining both judges, controls, fillers and P1/P2/P3/spread thresholds.
`score_absolute.orc` implements that bounded revision at `eb2b0636`; independent
review approved it and four additional checks, and the author reported 92
focused checks passing. The broad run reported 1127 passed and one failure
in 229.39 s: an unchanged native-session timeout check exceeded its 1.1 s
deadline by approximately 0.000353 s. Both timeout parameterizations passed
the narrow repeat (2 passed), then the unchanged full suite passed **1128 in
227.79 s**, exit0. No production or test change was made to hide the failure;
[verification evidence](/home/ollie/sc-evidence/preparation/a2-verification/verification.json)
retains both attempts. This preparation supplies no calibration outcome.

Before A′ (pools A2), freeze a new implementation runtime and new criterion
identities. A′ would score nine blind clones per batch with the same models,
controls, fillers and rules, at eight calls, cap 10; it requires separate owner
approval. The declared 32 planned calls and maximum 50 across all stages are
planning bounds, not an approved allocation. With A completed at exactly eight
calls, the remaining stage caps sum to 40 (10 + 14 + 4 + 12), giving a realized
plus remaining worst case of 48; A's unused two-call reserve is not transferred.
The remaining planned calls are 32 (8 + 8 + 4 + 12), or 40 including A. Only
A (8 calls, cap 10) is approved; A′, B, B2 and C remain separately gated. No live `module` arm, cumulative campaign,
quality frontier or ORC effectiveness conclusion follows from this experiment.
