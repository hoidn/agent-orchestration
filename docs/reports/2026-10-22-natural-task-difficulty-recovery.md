# Natural task-difficulty recovery: RPI gap fails, PRR judge excluded

Role: captured TD2 experiment methods and evidence. This
report authorizes no calls and is not a reusable launch recipe. The
[selected plan](../plans/2026-10-22-simple-evaluation-calibration-plan.md)
owns selection and the decision ledger; frozen criteria and external run artifacts
own the measurements. The [original interrupted pilot report](2026-10-22-natural-task-difficulty-calibration.md)
remains a separate, unchanged incident record.

The two-task set is **not calibrated**. All sixteen authorized sessions are
consumed: six incident starts and ten TD2 sessions. Eight natural solutions were
captured. RPI's blind scores give Luna mean 6 versus Terra mean 4.5, missing the
required Terra advantage. Retain that analysis with explicit uncertainty from
the review environment. PRR's judge is excluded because it penalized apparent
archive deletions caused by the sandbox; none of the candidate patches made
those deletions. No clean combined quality verdict is available.

## Method and budget

For each of `resume-projection-integrity` (RPI) and `pure-result-replay` (PRR),
the design requires two independent `gpt-5.6-luna` high direct attempts and two
independent `gpt-5.6-terra` high direct attempts. Both arms use the same
`control/direct_task.orc` workflow, task package, seeded base and tools, with the
frozen model binding as the treatment. Every original observation remains in
the denominator; there are no retries, replacements, repairs or selective drops.

One blind Terra-high judging session per task scores its four anonymized clones.
`score_absolute.orc` rates completeness, correctness, scope and layering from 0 to
2 each, totaling 0–8. The unchanged primary rule is
`terra_high.minus_control >= 2`: mean Terra score minus mean Luna score must be
at least two points on each task. The canonical summary joins ratings to clone
IDs and their original run IDs and refuses missing, excluded, duplicated or
invalid observations. No artificial controls, references or hidden-test runs
enter this calibration.

The original TD incident consumed six starts, including four forbidden Claude
starts, and remains invalid. The owner authorized ten fresh TD2 sessions
(eight generation sessions and two judges) within an overall cap of sixteen,
including those six historical starts. Each TD2 unit has a one-call cap;
generation concurrency is at most two. The original owner approval SHA256 is
`f84689a45a00d525660a7d88db0461c40ecc55c0712a7f523cd2a2991a4d170f`.
No raised budget or additional experiment is inferred from this report.

## Delivery outcome and prospective intake amendment

At the RPI checkpoint, both Luna attempts and the first Terra attempt completed.
The second Terra native CLI session left a captured 58,007-byte code patch but
omitted the workflow's `result.json`. Its original record remains
`failed/provider_result_missing`; no result file was synthesized. All four RPI
attempts have positive receipts for their exact actual model and independently
cleared contamination scans. These are integrity findings, not quality scores.

The completed-workflow protocol was interrupted. After observing that delivery
failure, and before any quality scores or judge dispatches, the controller
recorded an explicit amendment under the owner's instruction to fix and simplify
calibration: uniformly score the last raw snapshot from every original
terminal single-call attempt, including completed deliveries and terminal
delivery failures. An actually captured empty patch is admissible; an absent
snapshot, nonterminal attempt, excluded evidence or unverifiable receipt remains
missing evidence. Original status, failure, native transcript, patch and run
identity are retained. The amendment changes intake only; tasks, future
generation commands, models, sample counts, rubric and threshold are unchanged.
Any later qualification belongs exclusively to this amended protocol.

`pool.natural_attempt` constructs a temporary pooling view and binds the original
record, terminal memo, raw patch, exact-model positive receipt and native
transcript by path and SHA256. Summarization rechecks those sources. Generation
and judge commands retain the frozen execution runtime; pooling and summary use
a separate frozen analysis runtime under the already hidden evidence root.
The four untouched PRR generations continue from their original prepared commands.

The completed PRR Luna pair's independent audit covered 476 structured actions.
Luna1 read an archived YAML-retirement JUnit report in its own shared baseline;
three scan hits were historical main paths printed by that report or local test
fixtures, not reads of those external destinations. This exposure is disclosed:
coders could inspect the common baseline and run development tests, while blind
judges may not use test results. Other hits concerned generic tmux examples or
private temporary sessions. Five mistyped out-of-tree update requests explicitly
failed because the target files were absent; no successful external write or
protected-answer access was observed. The original hits remain recorded with
scoped clearance in `prr-luna-controller-adjudication.json`.

## Frozen identities and verification

External evidence root: `/home/ollie/sc-evidence/TD2-20261022`.
Criterion and packet paths below are under
`/home/ollie/sc-evidence/freeze-difficulty-recovery-20261022`;
operator source paths are under `/home/ollie/sc-evidence/preparation`.

| Artifact | Exact identity |
| --- | --- |
| Generation/judge runtime `/home/ollie/sc-runtime-difficulty-recovery` | commit `5d839b19236bc821fb08d04d7e4609a4da935eae` |
| Analysis runtime `preparation/runtime-natural-intake` | commit `ce48c89c1a9d8efd9095a328c30b0782faa911a3` |
| Original `criterion.json` | SHA256 `488196790454b9a1367a3b44acc55b4b1dab2c6ee0bdb46d45827bf5cc21215a` |
| Amended `criterion-natural-intake.json` | SHA256 `0d7440fed6cd1b0d70f5410313e144853360610ebf06dfdb376c3403bd716018` |
| Original `generation-packet.json` | SHA256 `2eb21b9248f40bc05ebab7f42a5c35ecc30d1373a56b57110c10792259b9e4cd` |
| PRR `generation-prr-packet.json` | SHA256 `b01d6574b34c2effa58c48b892bec43417d2b081321d4c428f06ad60b4d74801` |
| `task_difficulty_prr_operator.py` | SHA256 `f0af9ace8960723099f53838fe9f579dfddfa8bad5c1e38c4d3b14233483a731` |
| `task_difficulty_natural_analysis.py` | SHA256 `c31cfce841d472bb5756330c7550ab291cf9fcdd52f4037e3eeb151fad9dad18` |
| Amended `natural-judging-packet.json` | SHA256 `feb7a6f05935e5121ca6aab8ad8ba0a946ee7a00b90b43d3bea4f62d32cedf50`; 1,669 bound files |

The analysis operator verifies the fixed PRR packet hash and every referenced
file, and requires the PRR source, approval, launch manifest and completion
aggregates in its own phase lineage. It preserves the old criterion and runtime.

Judging preparation passed public pool verification and dry runs. Its CLI
preflight then incorrectly compared current mask enumeration against the masks
of already-finished generations, noticing the two newly created pools. The
failure is preserved. A reviewed read-only preflight verified all eight terminal
captures and unchanged generation identities, confirmed the pools were created
after generation, and checked the full current masks, freshness, authorization
and budget of both future judges. `natural-judging-scoped-preflight.json` records
this correction of scope; no frozen source, mask, criterion or launch command
changed. The original judge launch retained its approval and budget checks.

The intake implementation passed 402 affected tests using
`pytest -q -n 16 --dist=worksteal` in tmux, two public fake-provider smokes
(completed delivery and missing-result delivery with captured code), and
collection of 55 tests in the modified modules. Broad output and exit zero are
retained at `/tmp/compare-natural-intake-verify-vozg8lk5/pytest.log` and
`pytest.exit`. Six analysis-operator offline checks passed, including rejection
of an altered PRR source referenced by the frozen packet; their output and exit
zero are `/tmp/task-difficulty-natural-analysis-prr-review.log` and `.exit`.
These checks establish apparatus behavior, not task quality.

## Captured results and environment failure

| Task | Luna scores / mean | Terra scores / mean | Terra minus Luna | Interpretation |
| --- | --- | --- | --- | --- |
| RPI | 7, 5 / 6 | 4, 5 / 4.5 | −1.5 | Fails the frozen ≥2 threshold; retained with environment-exposure uncertainty |
| PRR | Excluded judgment | Excluded judgment | Unavailable | Judge used apparent deletions as scope evidence |

Scores are out of eight. RPI's reasons distinguish coverage of nested call
frames, persisted loop results, retry lineage and terminal error propagation.
They do not cite archive removal. These are the judge's diagnoses, not independently
verified technical findings, and this small result does not establish general
model superiority.

The archive masks left 48 tracked baseline files per RPI clone and 282 per PRR
clone invisible to Git's working-tree inspection. Git therefore displayed them
as deleted, even though the raw patches contain no change under
`docs/plans/evidence`. All four PRR rating reasons explicitly penalize unrelated
documentation/evidence removal. Its 240 test-execution scan hits were filenames
and deletion statistics: no test was run and no archived result content was
read. That false-positive scan explanation does not clear the separate, actual
distortion of the scope judgment. The controller recorded `contaminated` and
preserved the unmodified ratings. Canonical summarization refuses PRR because
its sole judge is excluded.

RPI's four reasons and public messages show no use of the apparent deletions.
The independent integrity review recommended retaining it for analysis with
explicit exposure uncertainty; this decision preceded root calculation of the
scores. Possible implicit influence cannot be ruled out. RPI is not represented
as a clean-environment replication, and no scores were manually corrected.

The frozen analysis runtime produced `natural-partial-readout.json` (SHA256
`7302dc2997ad14791a77d015ff9733849a7ff66da512c756dd4513fb99d54ea0`),
which binds the criterion, original judgments, exclusion, receipts and final inventory.
Its `two_task_qualification` is false. Supporting evidence in the TD2 root:

- `prr-judge-terminal-independent-audit.json`, SHA256
  `a38f49fc2543a1225a7f8332ff1cd8d0130ba4c5ff89f536ec8dba849b218e53`.
- `prr-judge-controller-adjudication.json` and the preserved pre-adjudication scan.
- `rpi-judge-masked-deletion-addendum.json`, SHA256
  `f3e7547e088b07aca89dbeb69d0549c7308eac4d103db83b3289c2fab2611a4c`.
- `natural-rpi-canonical-summary.log` and `natural-prr-canonical-refusal.log`.

Seven generation workflows delivered successfully; the eighth retains its
original `failed/provider_result_missing` status and natural patch. Both judges
delivered, but completion does not make PRR's judgment usable. Final native
inventory and structured-action audits record exactly ten TD2 roots, no native
children, no extra roots and no observed Claude/Fable activity in TD2. Including
the original incident gives sixteen starts, exhausting the owner's cap.

The six Terra receipts in TD2 total **USD 10.1998776** at the frozen prices:
USD 8.8558516 for generation and USD 1.344026 for judging. Luna's price is
unavailable, so the complete TD2 monetary cost is unavailable. This partial
total also excludes the earlier incident's incomplete cost.

## Environment correction and limits

The owner requested a proper environment fix without workarounds. The selected
offline correction builds a fresh review baseline without the protected archive
or its Git history, then applies the original candidate patch unchanged. It
records the derivation, rejects candidate edits to excluded paths and verifies
that Git shows exactly the real candidate changes. Original packages, outputs,
pools, ratings and criteria remain preserved. The correction is integrated on
main in `629c3b9c447c16baee7cea583498bd1f520a2950`, with independent review,
69 narrow checks, collection of 30 changed-module tests, the public real-Bubblewrap
fake-provider smoke and 432 affected parallel checks passed. The broad log is
`/tmp/compare-review-env-verify-dtds7cdv/pytest.log` with exit zero.

`review-environment-check.json` in the TD2 evidence root verifies the exact eight
actual raw patches in fresh review repositories: each archive is absent, each
review history has a new root, and all 40 capture-source hashes remain unchanged.
These are provider-free apparatus checks, not replacement judgments or new
experimental samples. No old ratings were changed.

The owner's later model-choice instruction selects a prospective **Luna low
versus Luna high** comparison under the current plan. It leaves this report's
Luna/Terra evidence unchanged. Its new outputs, effort declarations, frozen
criterion and budget must be established separately; the sixteen spent starts
do not authorize another call.

The no-Claude sandbox masks known
installations, auth/config and interactive shell startup profiles; registered
native metadata and structured actions are audited. These controls do not
universally prevent arbitrary API access or deliberate absolute-binary bypass.

Two samples per arm per task form a pilot, not a reliability estimate. A Terra
judge may favor its own family. The intake amendment followed an observed Terra
delivery failure, so the result cannot be represented as confirmation under the
original protocol. No ORC-benefit, campaign-quality or quality–cost Pareto claim
follows from this calibration. Luna has no frozen monetary price: unknown cost
must remain unavailable, not zero, and partial known costs must not be presented
as a complete total.
