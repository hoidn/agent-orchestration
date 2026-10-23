# Functional task-difficulty calibration implementation plan

**Current continuation:** this record retains the functional rubric and model hypotheses. LS8 execution closed with failed recorded predicates and a confirmed judge-brief contradiction; the [shared-contract rejudging plan](2026-10-23-functional-calibration-shared-contract-rejudging-plan.md) owns the selected two-judge correction using the same eight captures. See the [LS8 report](../reports/2026-10-23-luna-sol-filesystem-isolation-calibration.md) for unchanged historical ratings and limits.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Calibrate natural task difficulty with Luna high as the weaker hypothesis,
Sol 6.1 low as the stronger hypothesis, and one simple functional score out of eight.

**Architecture:** Add one criterion-selected scoring workflow to the existing
comparison harness. Preserve its clone-id join, natural-capture proof, exact
model/effort receipts, clean review baseline and complete denominators. Freeze
one new protocol before fresh observations; historical observations retain their
original rubric, labels and qualification results.

**Tech stack:** Existing Workflow Lisp scoring, Python comparison harness,
public orchestrator CLI, recording shims and Bubblewrap. No new dependency.

## Authority and selection

The owner requested: "can we just move luna high to 'dumb' role and use sol 6.1
low as the 'smart' one?" and "fix the rubric so that it's simpler". These select
the new model roles and evaluator correction. A stronger configuration is a
hypothesis, not a guaranteed ordering. The prior [LH report](../reports/2026-10-22-luna-effort-task-difficulty-calibration.md)
records failed separation: RPI low/high means 6/5, PRR 4.5/4. Its independent
component scores rewarded tidy incomplete implementations; no historical score
is changed to repair that measure.

The [comparison contract](../design/orc_effectiveness_comparison_harness.md)
owns generic rubric selection and evidence joins. The [measurement ledger](2026-10-19-orc-structural-search-measurement-plan.md)
owns current selection and later stage gates. This plan changes no structural
qualification V1/V2, campaign, reservoir, store or sealed rung-1 surface.

Offline implementation and preparation are complete. The owner replied
**"continue"** immediately after the explicit request for ten additional LS1
sessions, increasing the total cap from 26 to 36. That reply authorizes this
concrete packet: eight generations and two judges, with no retries. It does not
authorize other experiments or further budget increases.

**Current status:** LS1 stopped after four starts because its command detector
mistook `codex --help` for nested model dispatch. Two Luna RPI captures are
complete; two Sol RPI attempts were interrupted before terminal capture. No judge
ran and no new quality score exists. The owner explicitly approved LS2 with
eight sessions and total cap 38, including 30 historical starts. LS2 then stopped
after two new Sol starts because the detector still mistook subcommand help
(`codex exec --help`) for model dispatch. Both attempts lack terminal captures;
no judge ran. LS2 left 32 starts spent, with six unused under its cap 38. The
semantic detector repair is implemented and independently reviewed. LS3 is
prepared and reviewed. The owner approved its eight new sessions and total cap
40. Both Sol RPI attempts completed and were admitted. A host NVMe failure
and subsequent reboots then interrupted both Luna PRR attempts before settlement.
LS3 is stopped after four starts (36 overall); neither Sol PRR nor either judge
started. No new quality score exists. Task 6 records the independently reviewed LS4 recovery packet. The owner
approved six new sessions and total cap 42. Both Luna PRR captures are complete
and admitted. One Sol PRR provider terminated with `server_overloaded`; the other
completed and passed independent integrity review. LS4 is closed as scientifically
inconclusive after four starts (40 overall), without either judgment. Task 7
selected LS5: seven carried observations, one fresh Sol PRR generation and two
blind judges, with coordinator-declared total cap 43 under the updated owner
spending policy. LS5 is complete at 43 overall starts. Both blind judgments
passed integrity review and canonical closure. RPI Luna/Sol means are 4/6
(gap 2); PRR means are 3.5/6 (gap 2.5). Both satisfy separation but fail the
strict Sol mean <5 target, so both are `too_easy` and the two-task set remains
unqualified. The [LS5 report](../reports/2026-10-23-luna-sol-functional-calibration.md)
preserves the functional scores and recovery lineage. The owner's instruction
to iterate until the target is met selected the
[in-place failed-call calibration plan](2026-10-23-functional-calibration-inplace-failure-plan.md).
Its task packages and offline preflight passed, but LS6 stopped after seven starts
(50 overall) when one Sol attempt launched three unapproved shell CLI sessions.
No PRR generation or judge began. Task 9 routes to the
[single-call enforcement recovery plan](2026-10-23-functional-calibration-single-call-recovery-plan.md):
the corrected guard and all offline checks passed before LS7 dispatch under cap
60. LS7 then stopped after six starts (**56 overall**) on a separate filesystem
isolation incident: one PRR Luna attempt read and copied a historical implementation
from an unmasked home directory. Four RPI captures passed integrity review and
remain unscored; both PRR Luna attempts were interrupted, and no Sol PRR generation
or judge began. Task 10 now selects the reviewed
[filesystem isolation and LS8 plan](2026-10-23-functional-calibration-filesystem-isolation-plan.md):
prove and implement an explicit mount boundary offline, then prepare eight fresh
generations and two judges under prospective cap 66. No new quality or difficulty
result exists, and runnable environment proofs and concrete packet review precede
every new provider call.

Task 5 below records the approved LS3 recovery. The owner replied "yes" to the
eight-session/cap-40 proposal and reaffirmed Sol 6.1 for the stronger arm. That
model was already frozen as `gpt-6.1-sol` low; the scientific protocol is unchanged.

## Single functional score

Add `experiments/compare/score_functional.orc`, entry `score_functional::score`,
with the existing batch/intent/criterion-sha/judge-model input shape and ordered
clone results. Each rating contains only `clone`, `quality` and `reason`.
`quality` is one enum value S0 through S8. The rubric selector has
`criteria: [quality]` and `reference: null`.

The judge answers: **how much of the intended behavior actually works correctly
through its normal entry points?** Use these descriptive anchors, with odd
scores between adjacent anchors:

| Score | Functional meaning |
| --- | --- |
| 0 | None of the required behavior works |
| 2 | A small working part; most required behavior is absent or broken |
| 4 | A substantial working partial solution; major requirements remain absent or broken |
| 6 | Most required behavior works; some meaningful gaps remain |
| 8 | The requested behavior is complete and credibly correct across the stated cases |

Unused helpers, scaffolding and unreachable code do not count as working
behavior. Organization, patch size and code volume earn no independent points.
Design or scope problems matter when they cause a concrete functional defect or
regression. Explain the main working behavior and the most consequential gap
with code locations in one to three sentences. Judges inspect code without
running tests or using recorded test results. No reference, artificial defects,
control clones or hidden tests are introduced.

This is a new scale. Do not rescore LH into a passing calibration, compare new
totals numerically to its old additive totals, or count software smoke fixtures
as evidence that an actual judge measures functional quality correctly.
Passing this pilot accepts only its task-difficulty rule; later quality studies
still require the separate evaluator qualification owned by their governing plan.

## Prospective experiment

Use both current natural tasks, RPI and PRR, with their unchanged task packages,
seeded bases, tools and direct-task workflow. Holding tasks fixed initially
separates the owner-selected agent/evaluator changes from a difficulty change;
old additive scores cannot select difficulty under the new functional scale.

| Arm | Exact model | Effort | Fresh attempts per task |
| --- | --- | --- | --- |
| `direct_task` (weaker hypothesis) | `gpt-5.6-luna` | high | 2 |
| `sol_low` (stronger hypothesis) | `gpt-6.1-sol` | low | 2 |

One independent `gpt-6.1-sol` high judge per task rates all four anonymous clones
in one batch. Model/effort provenance stays concealed. Each generation retains
the existing 14,400-second limit; judges retain 3,600 seconds. Maximum two
concurrent generations; judges sequential; one physical call per unit. No
Claude/Fable, native delegation, retries, replacement samples or sealed-task
exposure. Raw captured output and original delivery outcomes remain unchanged.
The judge shares a model family with the stronger arm; blind provenance does
not establish absence of model-family preference or other judge bias.

The new criterion includes all three primary rules directly, on each task:

- `sol_low.minus_control >= 2`;
- `sol_low.mean > 3`;
- `sol_low.mean < 5`.

The owner's high-score target means the stronger arm here, despite its low
reasoning-effort setting. Both tasks must pass, with all two-by-two original
observations present and valid. No supplementary target helper is needed.
Report every individual score, mean, gap, elapsed time and metered usage.
Unknown model prices remain unavailable, not zero.

If the stronger mean is at least five, make the natural task harder; if at most
three, make it easier. In-range scores without the required gap mean insufficient
separation. Preserve the failed iteration and prospectively freeze any revised
task/seed and bounded spend before further observations. Do not force an ordering.

## Implementation and verification

### Task 1: Selected scoring workflow and canonical reader

- [x] Add the workflow above without changing historical `score_absolute.orc`.
- [x] Extend `experiments/compare/summarize.py` only enough to decode S0–S8 for
  the exact single `quality` field; historical component fields remain S0–S2.
  Update `validate_task_difficulty` admission for that same exact selector;
  quality S8 must survive the canonical join and complete-denominator checks.
  Reject mixed quality/component rubrics rather than guessing their scale.
  Keep the existing positional/clone-id join and sum (one field needs no weighting).
- [x] Add behavioral cases in `tests/experiments/test_compare_pool_summarize.py`
  or a focused adjacent module: endpoints/intermediate scores, unknown/out-of-range
  rejection, mismatched clones, mixed rubrics and unchanged historical component
  admission (including rejection of S3 for an old component).
- [x] Extend the public fake-provider smoke in
  `tests/test_workflow_evaluated_compare_score.py` to run the real new workflow,
  Sol-high binding, four natural captures and all three canonical predicates.
  Do not assert literal prompt phrasing or add a scoring framework.
- [x] Collect changed tests, run narrow checks and actual Bubblewrap/public CLI
  smoke, then the affected suite using `pytest -q -n 16 --dist=worksteal` in tmux.
  Obtain independent code review and inspect the final diff before integration.

### Task 2: Current documentation and historical closure

- [x] Record LH completion and its rubric limitation in the report and old plan.
- [x] Update current routing in the measurement plan, roadmap measurement paragraph,
  docs index, comparison README, capability row and concise AGENTS model policy.
  Preserve historical freezes and unrelated owner edits.
- [x] State the single functional score in the comparison contract, retaining
  criterion-selected historical rubrics and separate later quality-launch gates.

### Task 3: Freeze and qualify the next launch offline

- [x] Freeze a clean runtime after verified integration; declare the exact model
  and effort per arm, Sol-high judge, one functional rubric and all three rules.
- [x] Prepare eight fresh attempts and commands using existing public entry points;
  preserve the prior 26 starts, full LH/TD/TD2 evidence and native receipts.
- [x] Use a bounded experiment operator with complete inventory, no automatic
  retry and explicit owner budget binding. Reuse proven helpers without mutating
  previously frozen operators or introducing a campaign abstraction.
- [x] Validate commands, model policy, private masks and honest review baseline
  with zero-provider dry runs/fake CLI; freeze source, tests, inputs and proof.
- [x] Independently review the concrete packet; all 815 frozen hashes and the
  zero-start preflight passed review.
- [x] Obtain the ten-session authorization: the owner replied "continue" to the
  explicit proposal; overall cap 36 includes 26 historical starts. LS1 later
  stopped after four starts due to the apparatus incident recorded below.

## Decision ledger

| Decision | Consequence |
| --- | --- |
| Owner selects Luna high versus Sol 6.1 low | Fresh arm identities above; actual advantage must be observed |
| Owner requests simpler rubric | One functional 0–8 score; no independent style/scope credit |
| Existing strict target and gap retained | Apply to `sol_low`; both tasks and full denominators required |
| Owner replies "continue" to the reviewed ten-session proposal | Authorize LS1 eight generations and two judges, total cap 36 including 26 historical starts; no retries or other spend |
| LS5 canonical closure completes the experiment without qualifying the task set | Readout `2ba7325d` retains all eight observations and two blind judgments. RPI Luna/Sol means 4/6 (gap 2); PRR 3.5/6 (gap 2.5). Both fail strict Sol mean <5, so `two_task_qualification` is false and both tasks are `too_easy`. Three LS5 calls plus 40 historical starts exhaust declared cap 43. Preserve every original score and external-abort record. The owner's iteration direction requires naturally harder tasks under unchanged roles/rubric/thresholds; the next concrete design, freeze and budget remain prospective |

## Offline implementation evidence

The functional workflow and exact-selector reader are implemented. The affected
16-worker comparison suite passed 474 tests (`/tmp/compare-functional-verify-wzn07het/pytest.log`).
Independent review found lost historical smoke coverage and an oversized module;
the final revision restores all five historical cases alongside four functional
cases and shortens the stale module description without compressing code. The
final nine-case public Bubblewrap/orchestrator smoke passed in 18.03 seconds
(`/tmp/functional-calibration-revision-20261022/public-smoke-final.log`). Changed
modules collected 139 tests; the final focused quality/difficulty/workflow checks
passed 8/5/7 respectively. Historical scoring workflows remain byte-identical.

These checks use scripted providers and synthetic receipts; they establish
software mechanics, not task difficulty, judge validity or model superiority.
The LS1 operator has 32 passing offline checks and preserves 3,425 pinned
historical files. Concrete runtime/command/mask qualification is recorded below.

Integration is committed on main at `b56e8cd6a381ab91b40b750edcd0ae4ec0468f15`.
The affected suite on that integration passed **479 tests in 39.51 seconds**
(`/tmp/compare-functional-main-verify/pytest.log`, exit 0); all 21 pre-existing
dirty main files were preserved byte-identically. The isolated experiment runtime
`/home/ollie/sc-runtime-functional-calibration` is clean at
`b2d217acfbead475080847f16c82b1fae901aec5`, retaining the previously qualified
runtime plus the bounded functional-scoring commit. Its public functional review
smoke passed in 22.30 seconds (`/tmp/sc-functional-exact-runtime-smoke.log`, exit 0).
The selected workflow SHA-256 is
`297e629ebc5579b8889fd4629a3a4400d2024dcbc7a88e83034b4608e53ae0e7`.

## LS1 concrete launch packet (historical; interrupted)

The fresh protocol is frozen at
`/home/ollie/sc-evidence/freeze-functional-calibration-20261022/criterion.json`
(SHA-256 `464a0247e950939ee8eaa0d5e9eda42bca02ea4dcd4cfe0298b92a01f9fbecc2`).
The generation packet in the same directory, `generation-packet.json`, binds
815 files (SHA-256 `49e2fdd631cd4a698e8445135827458f1ac8536a66d60026b80740097e9b33d5`).
It includes exact runtime/operator/helper/test sources, all eight prepared
commands and inputs, invariants, the actual sandbox proof and copied verification
logs. The initial proposed manifest remains unchanged. The empty per-unit dry-run
logs and raw sandbox diagnostic directories remain outside this manifest; the
preparation exit proof and self-contained eight-unit sandbox proof are bound.

All eight public dry runs passed. The actual Bubblewrap check invoked eight fake
CLIs and zero providers, checked 142 protected paths per attempt, exact Luna-high
and Sol-low forwarding, disabled native delegation and hidden Claude/auth paths,
and preserved all 48 generation records/index files. Its proof is
`/home/ollie/sc-evidence/LS1-20261022/generation-mask-smoke.json`
(SHA-256 `eb480a2fa46fb80e8c672a2d5ee9b14a4aced5fb9470a9dabc46160ea0f7d2e3`).
The final operator preflight passed with **zero fresh starts, 26 historical
starts**, no native children, extra roots or forbidden calls; see
`/home/ollie/sc-evidence/LS1-20261022/generation-preflight.log` and `.exit`.
This preflight preceded approval and observed no fresh starts. The subsequent
owner approval binds the unchanged criterion and packet; the operator still
refuses any dispatch without that exact budget binding.

The authorized scope is exactly ten new sessions (eight generations plus two
judges), overall cap 36, no retries. Offline readiness is not a new quality result
or a task-family qualification, and this approval selects no other paid experiment.

Independent review passed the exact 815-file packet and its concrete commands,
inputs, source bindings, mask proof and complete zero-start inventory. The root
integrator separately verified every packet hash and the same preflight. The only
remaining launch prerequisite was the owner's bounded budget approval, now
recorded below.

## Authorized LS1 execution

The owner replied **"continue"** to the explicit ten-new-session/cap-36 request.
The exact reply and proposal context are recorded at
`/home/ollie/sc-evidence/LS1-20261022/owner-approval-generation.json`
(SHA-256 `9d7031818275849e7aab87bb78e2215a2f1ba87e43ec521f76d2af120c346566`).
The criterion and generation packet remain unchanged. A fresh preflight passed
before dispatch; the operator started the two RPI Luna-high attempts in tmux
`ls1-generation-20261022` on `/tmp/claude-tmux-sockets/sc-difficulty.sock`.
Initial run IDs are `20261023T024142Z-gswhyi` and `20261023T024142Z-4zxhpi`.
The operator stopped both Sol RPI processes on a false-positive command alert.
The remaining four generations and both judges never started. The original
packet, approval, persistent alert, interrupted records and usage remain intact;
LS1 is incomplete and cannot qualify either task.

## Task 4: LS2 apparatus recovery (historical; interrupted)

The frozen detector classified any shell command named `codex` as a possible
dispatch. Sol's actual structured action invoked `codex --help | head -45`; the
installed guard refused that informational request before backend dispatch.
Independent inventory found four native roots and no children, additional roots,
Claude/Fable calls or delegation. Neither interrupted Sol attempt has a terminal
capture, so neither is an observation of poor task performance.

Correct the classifier in a new source version: a top-level CLI with only a
known help/version flag is informational. Continue detecting interactive calls,
execution/resume/review, ambiguous extra arguments and later commands in a pipe
or command list. Keep the existing guards and inventory. This bounded shell
screen is not a universal defense against encoded commands or direct APIs.
Preserve the old operator and its non-clearable incident record unchanged.

LS2 retains the exact runtime, tasks, seeds, models, efforts, tools, timeouts,
functional rubric, review exclusions and all three qualification rules above.
Before any new generation or score, declare exactly these observations:

| Task/arm | Original LS1 captures carried forward | Fresh LS2 generations |
| --- | --- | --- |
| RPI / Luna high | Both completed attempts, unchanged | 0 |
| RPI / Sol low | 0 | 2 |
| PRR / Luna high | 0 | 2 |
| PRR / Sol low | 0 | 2 |

One fresh Sol-high judge per task still rates all four anonymous clones. The
two carried samples are selected for complete, uncontaminated terminal capture
before any quality score; no LS1 generation has been judged. Bind their original
record, completion, raw patch, receipt, native session and independent audit by
digest. The two existing scans need their normal public adjudication: first save
the complete pre-adjudication records, then change only scan-verdict metadata
using `prepare.adjudicate` and bind both versions. Original completion references
retain their historical pre-adjudication digests. Preserve identities and
delivery outcomes; use the existing
`pool.natural_attempt` intake and `pool.write_pool`, with the same task path and
seeded compare base. Do not rewrite delivery artifacts, fabricate a new terminal record,
silently relabel them as fresh or repair the interrupted Sol deliveries.

Accounting and evaluation have different denominators: LS2 launches only six
new generation units and two judges, while its evaluation contains all eight
declared natural observations (two carried plus six new). The historical 30
starts already include both carried Luna and both interrupted Sol calls. Thus
the recovery uses **eight new starts, overall cap 38**, with no retries,
replacement samples or other spend. The owner explicitly approved this increase
from cap 36 after reviewing the concrete packet; the old LS1 approval alone was
not sufficient. All new units use fresh paths; the original unused LS1 units
remain unused.

- [x] Preserve the incident inventory, captured usage and independent capture
  audit; report incomplete Sol task delivery separately from metering status.
- [x] Verify the classifier fix against the exact recorded action and genuine
  dispatch/pipeline/wrapper cases without invoking providers.
- [x] Prepare the six fresh commands and explicit two-capture manifest; verify
  unchanged task/baseline/model/effort provenance and no double-counted starts.
- [x] Qualify actual sandbox/CLI forwarding with fake providers, freeze all
  dependencies and proof, and obtain independent concrete-packet review.
- [x] Obtain owner approval for eight fresh starts and total cap 38, binding the
  concrete criterion/packet. The owner replied "yes" to the explicit proposal.
- [ ] Execute the six generations then two blind judgments; preserve every
  declared observation, audit integrity, and compute the canonical complete
  readout. A new interruption stops without automatic retry.

This amendment adds explicit carryover provenance to avoid repeating valid
generations. It does not change difficulty to obtain a preferred model ordering,
retroactively qualify LS1, rescore older iterations or select a campaign.

The independent audit at `/home/ollie/sc-evidence/LS1-20261022/incident-audit.json`
(SHA-256 `c618b7283ea86d7e7f11842b36044d490d42779a0b6118fc662374144b9bd68d`)
reviewed 442 structured actions across the four roots. `incident-accounting.json`
(SHA-256 `d16eed0a728e8b45216a1ef9f39cfc55ba209ab8d5c55d16f88afdb4e3f7c4a5`)
preserves captured usage, the original false-positive inventory and 30-start
accounting; complete final prices remain unavailable. `carryover-adjudication.json`
(SHA-256 `d3684336c9c87121f6fba7a8d8f83cc080a6615debb58e7c93bd1745aca87e62`)
records the public scan adjudications, exact before/after versions and both
canonical `natural_attempt` admissions. Only scan-verdict metadata changed;
all original delivery artifacts and the persistent detector alert remain intact.
Seven offline classifier checks pass, including the exact incident action and
genuine later/wrapped dispatches; independent code and recovery-plan review pass.
These are apparatus checks, not quality scores or provider-spend authorization.

## LS2 concrete recovery packet (historical; authorized then interrupted)

Freeze directory: `/home/ollie/sc-evidence/freeze-functional-recovery-20261022`.
The immutable `criterion.json` has SHA-256
`d4fd467d49c9cbebabf76dc073c2bb981e0ccf1135bddf368cd6030d7494a588`;
`carryover.json` has SHA-256
`61cd99f2f35d246c569b47e4981443e540cae3c5ed665f047b2e5f44ed1b75d6`.
The 825-file `generation-packet.json` has SHA-256
`31f27b72a762054f559f3508c913062150094b8774e0750077f6cadba84e658a`.
It binds the new operator, classifier regression and carryover/accounting checks,
generation and future judge qualification helpers, runtime dependencies, all six
prepared commands/inputs, preservation snapshot and copied verification evidence.
The operator SHA-256 is
`7cf4686ae727e4a0086829f13f026588150403581d737f883ca208c7dc14c8ed`.

Evidence lives under `/home/ollie/sc-evidence/LS2-20261022`. The six actual public
dry runs and six Bubblewrap/fake-CLI checks passed with zero providers; the latter
checked 143 protected paths per unit and preserved all 36 record/index files.
`generation-mask-smoke.json` has SHA-256
`9d2c3ec212ef680afaef5db3a73bd11c43a2af3f0754fc45daf5bbbdec7ee157`.
The operator passed 38 checks and collected all 38, its inlined classifier passed
the seven regression checks, and all 4,378 pinned historical files verified.
The unchanged runtime's earlier 479-test suite and exact public functional smoke
remain applicable; they were not rerun for external-operator-only changes.

The root independently verified every packet hash and reran the exact preflight:
**zero fresh starts, 30 historical**, with no native children, extra roots,
Claude calls or forbidden actions. This preflight preceded approval. The original
LS1 alert, packet, captures, incomplete Sol attempts and usage remain preserved.
Judge helpers exist and passed source review; actual judge-pool sandbox checks
must run after the six new captures create their concrete anonymous pools and
before either paid judge call. The eight-session authorization
covers both generations and judges; binding that same answer to the later
judging packet does not require a second budget request.

Independent review passed the concrete 825-file packet and every source binding,
all six exact commands/inputs, both canonical carryover admissions, full analysis
denominator and zero-start inventory. Its new report is
`/home/ollie/sc-evidence/LS2-20261022/generation-independent-review.json`
(SHA-256 `6b0fb9e6b2f52721e749e7d0dd9fce61523121a33abbe8f7abdd1e596f9592f2`).
All offline launch prerequisites are complete. Owner approval is recorded at
`/home/ollie/sc-evidence/LS2-20261022/owner-approval-generation.json`
(SHA-256 `6aec761d013b93ca4dd328d48848d792f9ad4608712cab399a18506d188842ee`).
The exact reply **"yes"** binds eight new sessions and total cap 38, including
the 30 already spent. A fresh approved preflight passed before dispatch. The
first two RPI Sol-low runs are `20261023T052532Z-1dkqnp` and
`20261023T052532Z-gmfzbc`, supervised by the bounded operator in tmux
`ls2-generation-20261022` on `/tmp/claude-tmux-sockets/sc-difficulty.sock`.
No retry or other experiment is authorized. The original pending-status snapshot
inside the frozen criterion remains unchanged; the separate approval is operative.

## LS2 subcommand-help interruption

The original LS2 operator stopped both Sol RPI processes after 32 seconds.
The flagged structured action was `codex exec --help | head -55`; another
attempt used top-level help. Both were refused by the unchanged model guard
before backend dispatch. The prior correction exempted only a CLI followed by
one informational flag, leaving this second false positive. That correction was
too narrow; stopped task delivery is not evidence of weak Sol performance.

The independent `LS2-20261022/incident-audit.json` has SHA-256
`9e78a6e6e3c296cfb94e58d48adc2fd03549920c0f9c10852151e4ae80699322`.
It reviewed all 12 structured actions across two exact Sol-low roots, with no
Claude, children, extra roots or actual delegation. Both attempts lack terminal
memos, raw captured patches and completion receipts. Four PRR attempts and both
judges never started. The 825 frozen files and 21 carried-capture files remain
intact. `incident-accounting.json` has SHA-256
`8ee1ca6c64b9e671c8d83bedffb9e79bc8ea623fee204686641366921deb5ba0`;
it preserves both captured usage counters, original alert and 32-start ledger.
No quality scores or task qualification follow.

Before another launch, verify informational CLI semantics against the installed
binary in a network-disabled, credential-free diagnostic environment, including
subcommands, flags, option values and the `--` terminator. Correct the whole
informational-versus-dispatch distinction rather than adding one command string
to an allowlist. Keep model guards unchanged and actual dispatch detection
intact; preserve both frozen operators and alerts. Any further prospective
recovery must retain the full analysis denominator, all spent starts and its own
concrete approval before paid dispatch. No automatic retry is authorized.

## Task 5: Prospective LS3 semantic-detector recovery

The installed CLI was probed without network or credentials and with an invalid
configuration that stops non-informational commands before session creation.
The 62-case proof at
`/home/ollie/sc-evidence/LS2-20261022/offline-cli-help-semantics-v2.json`
binds the exact installed binary and source. It distinguishes actual help/version
requests from option values, prompts and arguments after `--`; all probes created
zero model sessions. This is parser evidence, not classifier or model qualification.

In a new source version, classify informational commands using those semantics:
account for the command route, options with values, the option terminator and
simple shell redirections/wrappers. Continue inspecting subsequent commands in
lists and pipelines. Unknown options/routes or shell expansions gain no help
exemption. Preserve the existing model guard, native inventory and its explicit
limits; do not introduce a general shell parser or alter the experiment runtime.
Both exact incident actions and genuine dispatch shapes must have behavioral
regressions, including dispatch after an informational command.

The prospective recovery retains the same runtime, task packages and seeded
bases, models, efforts, tools, timeouts, functional rubric and all three primary
rules. Its analysis contains exactly the two originally declared, complete LS1
Luna RPI captures and six fresh generations: two Sol RPI, two Luna PRR and two
Sol PRR. One fresh Sol-high blind judge per task rates the four anonymous clones.
Use the existing carryover proof and canonical natural-capture intake; do not
rescore history, repair interrupted deliveries or omit an observation.

All 32 spent starts remain in accounting, including the two incomplete LS2 Sol
attempts. Completing the full comparison needs **eight new starts, proposed
overall cap 40**. Only six starts remain under the current approved cap 38.
Offline preparation is selected; a new concrete approval must bind the repaired
packet and the eight-session budget before any LS3 dispatch. That approval would
cover all six generations and both later judges, with no retries or other spend.
All new units use fresh paths. Unused LS1/LS2 units remain unused; original
operators, freezes, alerts, interrupted records and usage remain unchanged.

- [x] Implement and independently review the semantic classifier against the
  offline CLI evidence, both incident actions and real dispatch boundaries.
- [x] Prepare six fresh commands and the exact two-capture manifest; bind all
  historical accounting and verify unchanged natural-capture provenance.
- [x] Run public dry runs, fake-provider sandbox checks and complete inventory;
  freeze the dependencies/proof and independently review the concrete packet.
- [x] Obtain concrete owner approval for eight fresh sessions and total cap 40.
- [ ] Execute the generations and, after concrete pool/sandbox checks, the two
  blind judges; report all scores and the canonical complete readout. Stop on a
  new interruption without automatic retry.

The semantic classifier passed 14 offline checks and all 62 installed-parser
cases. Its new source has SHA-256
`25edb527c870b2550d58eb2f0d7a3eeecabe90798348a494cb4b4b12f95d5641`;
the evidence under `LS2-20261022/classifier-semantic-qualification.json` has
SHA-256 `f7cbb5ca0265e437db5b7a6e13a398829b70247c082ed00805862aa807cb802d`.
Independent review is `classifier-independent-review.json`, SHA-256
`1af2211a3a37bab48e99ff4473f7d2843d700858915feed4f85d5557b06a5abf`.
Both the root and reviewer replayed all 454 previously audited LS1/LS2 action
inputs through the new classifier, with zero alerts. The replay proof is
`classifier-historical-replay.json`, SHA-256
`0a1fcecc92570bd5a400f3a2b756c6db73c2c0c75cadcf6d0e304347bb3cea57`.
No command from those inputs was executed and no model session was started.
These checks preserve the original incident alerts and establish only the
bounded command-classification repair, not new quality scores or live readiness.

## LS3 concrete recovery packet (authorized; interrupted)

Freeze directory:
`/home/ollie/sc-evidence/freeze-functional-semantic-recovery-20261022`.
The `criterion.json` SHA-256 is
`e0db31a661d4b006416b74c9a65e4070cfc767b4910045d92e1c35014485f41a`;
`carryover.json` is
`2c524b6ba75f61407f015480f559e9d57c5e5911a5c21727602df28a8fa733d1`.
The 824-file `generation-packet.json` has SHA-256
`fceaa951ed7167a3a71c0ce26f5ebe64b72d3155ce58e41401ba4e9cfeae5cac`.
It binds the new operator, helpers, tests, prepared inputs/commands and proofs.

Evidence lives under `/home/ollie/sc-evidence/LS3-20261022`. Forty operator
checks and 14 semantic regressions against its actual inlined classifier passed;
all 40 operator tests collected and 4,569 historical files verified. Six public
dry runs and six actual Bubblewrap/fake-CLI checks passed with zero providers,
144 protected paths per attempt and all 36 record/index files unchanged.
`generation-mask-smoke.json` has SHA-256
`ed6c7396cd4371cb84568482e6e81ce96fa443b85c72922cc51fce06269f39a6`.
Both carried samples passed canonical intake with their 22 manifest files intact,
including the original LS2 carryover manifest. The analysis denominator remains
eight observations; physical new spend remains eight sessions including judges.

Independent concrete-packet review is `generation-independent-review.json`,
SHA-256 `15a14ca0aa88524fbe303f9f056e12d4e05404f3ae44ecb9aa473204e08f5f27`.
The root separately verified all 824 hashes and reran preflight: zero fresh
starts, 32 historical, no children, extra roots, forbidden actions or Claude.
Its evidence is `root-generation-preflight.log` and `.exit` (exit 0).
The unchanged runtime's 479-test suite and public functional smoke remain
applicable. Actual judge-pool sandbox checks remain due after new captures
produce the anonymous pools and before either paid judgment.

All offline launch prerequisites passed. Owner approval is recorded at
`LS3-20261022/owner-approval-generation.json`, SHA-256
`b106756edf227ef8fd1fea4fafccbe933a8a213cfd14ed08513122c6801401ff`.
The exact reply "yes" authorizes eight sessions, total cap 40 including 32
historical starts. It covers all six generations and both later judge calls,
with no retries or other spend. The follow-up "use sol 6.1 for smart" reaffirms
the frozen stronger model; its low effort and the Sol-high judge remain unchanged.
A fresh approved preflight passed before dispatch. The first Sol RPI run IDs
are `20261023T060305Z-dltv9j` and `20261023T060305Z-ov723i`, supervised by
the bounded operator in tmux `ls3-generation-20261022` on
`/tmp/claude-tmux-sockets/sc-difficulty.sock`. No new quality score exists.
The frozen criterion retains its original pending snapshot; this separate
approval is operative.

## Task 6: Recover from the host storage failure (authorized; running)

The host journal records the NVMe controller at PCI address `0000:05:00.0`
disappearing at 2026-10-23 06:47:17 UTC, failed reset, I/O errors, an aborted
EXT4 journal and `/home` becoming read-only. Reboots followed. The two live
Luna PRR sessions have NUL-tailed native logs and no terminal capture. Preserve
them as infrastructure-interrupted starts, never low-quality observations.
The current boot already disables NVMe/PCIe power saving; this is an observed
host change, not proof that hardware cannot fail again.

Preserve all four completed RPI observations, subject to exact-byte and canonical
intake verification: the two original LS1 Luna captures and two admitted LS3 Sol
captures. Prepare four fresh PRR generations (two Luna high, two Sol 6.1 low)
and two Sol 6.1 high judges in fresh paths. Keep tasks, runtime, tools, timeouts,
functional rubric, eight-observation analysis denominator and all three primary
rules unchanged. The cost of preserving the single-call protocol is that an
incomplete session cannot be resumed into a qualifying observation.

The four LS3 starts bring historical spend to **36**. The owner approved
**six new sessions and total cap 42**: four PRR generations and two blind judges.
The same approval covers both phases, with no automatic retries or other spend.
Unused units from previous interrupted protocols remain unused.

Reuse the bounded operator and existing helpers in a directly revised source,
without wrapper chains, new runtime machinery or changed guards. Bind each
carried capture to its actual source receipt/completion and original
pre-adjudication record snapshot. Preserve original records and hash crosswalks.
Keep interrupted raw logs byte-identical; any diagnostic reading of their valid
JSON prefixes must explicitly report the missing tail and must not fabricate a
complete native receipt or permit their intake as observations.

After the incident/reboots, nine historical `/tmp` verification logs/scripts
named by the LS3 preservation manifest are missing. Record their exact paths and old hashes as missing,
without recreating them or claiming their hashes verified. Verify every surviving
historical file, keep original manifests unchanged and rerun the affected offline
checks with durable evidence if their checks are prerequisites for the new
packet. Do not relax candidate capture, lineage, model, scan or denominator checks.

- [x] Record the host incident, exact physical starts, interrupted evidence and
  historical missing-file inventory; verify the completed captures independently.
- [x] Prepare the four fresh PRR units and four-capture carryover manifest; verify
  source-specific receipts, original outcomes and identical task baselines.
- [x] Run offline checks, public dry runs and actual fake-provider sandbox checks
  on the current boot; freeze and independently review the concrete packet.
- [x] Obtain approval for six fresh sessions and overall cap 42.
- [ ] Execute, admit terminal captures, prepare both anonymous pools, verify the
  concrete judge sandboxes, run the two approved judges and close canonically.

Incident accounting is preserved under `LS3-20261022/host-incident-accounting.json`
(SHA-256 `411315d4e9152ea60e562b0a3f073429d7dca1ec1f0c16c60c4a3c638b70b255`).
Independent review `host-reboot-independent-review.json`
(`17828524da64aa83a7ba5bb176aff5a710975c8982e62157b50bda1f065515dd`)
verifies all four RPI canonical intakes, 824 packet files, 22 earlier carryover
files and 4,560 surviving historical hashes. It records the nine missing `/tmp`
files and limits the interrupted PRR access audit to 284 surviving actions.
No complete interrupted-session receipt or quality score is inferred.

### LS4 concrete recovery packet (closed; external provider interruption)

Freeze: `/home/ollie/sc-evidence/freeze-functional-host-recovery-20261023`.

- `criterion.json`: `b5378a44b3d60fd8c4e823255090baa8a6c68d74c1d8d669bcf53ede332982b9`.
- `carryover.json`: `4df46ae3e08040e36d8a50ee87e5e19dfb5dc236a66081077d5c4ac8e91ad6fb`.
- `generation-packet.json`: `abaddaa769209d442d5eda72859cb0b9244c64af763f33250ece9144dee3d2ba`.

The packet binds 824 files, four fresh PRR commands and all 48 carryover
references. All four RPI observations pass canonical intake; the eight-observation
analysis keeps two samples per arm and task. The directly revised operator
preserves 28 core functions exactly, including inventory, classification, guards
and execution. Historical preservation verifies 4,780 surviving files and the
explicit nine-file absence manifest; missing files are not claimed verified.

Evidence under `/home/ollie/sc-evidence/LS4-20261023` includes four successful
public dry runs, four actual Bubblewrap/fake-CLI checks (145 protected paths per
unit, 24 record/index hashes unchanged), 60 passing offline checks and 46 collected
operator/contract tests. Fresh current-boot runtime evidence under
`LS3-20261022/host-reverification` records nine public smoke cases, 437 comparison
tests and 42 historical analysis/target checks passing, with zero providers.
The initial console-entry collection failure is retained; invoking pytest as a
Python module from the same checkout passed without runtime or test changes.

Independent review `LS4-20261023/generation-independent-review.json`, SHA-256
`60b42afe3af1c67fdc4362d5058390d018ab85c6af721ccbc99a2256d8bbe1bc`,
found no blocking issue. Root separately verified packet/carryover hashes and
reran preflight: zero new starts, 36 historical, no extra roots or forbidden
actions. Actual judge-pool sandbox checks remain due after PRR captures complete.

**Owner approval:** the reply "yes" authorizes six new sessions, raising the
total cap from 40 to 42 (36 already spent; four PRR generations and two Sol-high
judgments), no retries or other spend. Exact roles remain Luna high weak, Sol
6.1 low strong and Sol 6.1 high judge. Approval is recorded in
`LS4-20261023/owner-approval-generation.json`, SHA-256
`65bddc7c2adc630b7fdb178ee998fa7e10e70f721e156e40438df2852b5880c7`.
A fresh approved preflight passed. Luna PRR runs
`20261023T074303Z-w11lzt` and `20261023T074303Z-ctvb66` are supervised by the
frozen operator in tmux `ls4-generation-20261023`. No new quality score exists.
Present host operability and offline checks do not establish lasting storage
stability. The frozen criterion retains its pre-approval pending snapshot; the
separate approval record is operative.

The owner subsequently requested removal of the general provider-spend approval
rule from `AGENTS.md`. The maintained instruction now records experiment
decisions and spending limits in the plan ledger; it no longer requires an
automatic permission request for new or raised spend. This instruction change
does not mutate the frozen LS4 packet, its declared cap or historical evidence.


## Task 7: Close the provider-capacity incident and prepare a clean continuation

At 2026-10-23 08:14:48.210 UTC, Sol PRR run
`20261023T080607Z-wc6acr` ended with native error `server_overloaded` and workflow
`failed/provider_exit_nonzero`. It left a raw patch. A complete failed terminal
can pass the unchanged canonical intake; that mechanical admissibility does not
make an externally truncated attempt a clean task-difficulty observation.
Preserve its original terminal, raw patch, scan, native log and usage. Do not
assign a low score from the error, silently omit it from LS4, or report LS4 as
qualified. Both Sol attempts have now settled and passed capture-integrity review;
only the second is free of external interruption.

Hold both LS4 judges while this confound remains. The next comparison, if
prepared, is prospective and separate from LS4. Retain every valid observation
not externally aborted, without selecting by code quality, and generate fresh
solutions only for the externally interrupted slots. Retain legitimate failed
deliveries when their raw terminal captures qualify; do not require a successful
workflow envelope as a proxy for functional quality. A native provider abort such
as `server_overloaded` must stop scientific qualification even when the raw
capture is mechanically admissible.

The second Sol PRR attempt is valid and not externally aborted. The selected
continuation is **seven carried observations, one fresh Sol PRR generation and
two blind judges**. Forty historical starts plus three new starts have a
**prospective total cap 43**. The existing cap 42 and
no-retry LS4 freeze remain unchanged. The owner's later removal of the general
spend-approval rule delegates prospective spending decisions to the coordinator,
with exact limits recorded in the ledger. This selects only the minimum recovery
needed for the already requested calibration; it opens no unrelated experiment.

The new operator must bind a **budget declaration**, recording that owner policy
and the coordinator-selected cap, to each frozen packet. Do not fabricate an
owner approval of the new numeric cap or alter the old approval receipt. Keep
hard per-unit/overall budget enforcement and one original session per fresh unit;
the same declaration covers both later judges. This prospective policy change
removes the obsolete approval-request gate while preserving the spending bound.

Use a directly revised bounded operator and source-specific carryover manifest,
preserving all original outcomes and pre-adjudication hash crosswalks. Tasks,
models, tools, timeouts, functional rubric, eight-observation denominator and
three primary predicates remain unchanged. No new runtime feature, retry loop,
judge shortcut or altered historical score is selected.

- [x] Capture and independently audit both Sol attempts; record the external
  failure and all four LS4 starts, without spending either judgment.
- [x] Freeze the prospective carryover selection and exact remaining generation
  count; prepare and test fresh commands, masks and canonical intake offline.
- [x] Independently review the concrete packet and bind its declared minimum
  budget under the updated owner policy before any new provider start.
- [x] Execute the eligible continuation and both blind judges, then close through
  the canonical clone-id joins without attributing external aborts to difficulty.
  Execution is finished; scientific task-difficulty qualification failed.

LS4 closure evidence is `LS4-20261023/incident-accounting.json`, SHA-256
`6109000ff9f1f223d7dd8f2b58ddf2ca6953819ad92d10a20c639137d46ef976`.
Sol review `80b9a00d` audited 118 structured actions and all 20 scan hits;
public adjudication `2accda64` changes only scan verdicts. Both original failed
and completed captures pass canonical intake, with original outcomes, native
sessions, positive receipts and raw patches preserved. The failed first Sol
attempt remains scientifically confounded by `server_overloaded`; the second
is eligible. No LS4 pool or judge was launched, and no quality-based selection
was used for the seven carried observations.


### LS5 concrete continuation (completed; not qualified)

Freeze: `/home/ollie/sc-evidence/freeze-functional-capacity-recovery-20261023`.
Criterion `bd3a82099bb9645a1beab9f5efeb94ebbb6d483d7c9385528c5f76ffe46cd3ae`,
carryover `0a9b1e101a5d9ecf6b00e12679d851bb5737689a84f9525329628acd967e2871`,
and generation packet `874aa0aa4510ea475750f2ca531ce235c47d6a0f7b86d80a28144df19798a952`
bind the unchanged protocol, seven original canonical intakes and one fresh
Sol-low PRR command. Verification passed 58 narrow checks, 44 collected tests,
one public dry run and one actual fake-provider sandbox check. The packet binds
818 files and 81 carryover references; 4,967 surviving historical files remain
verified with the same nine explicit historical absences.

Independent review `LS5-20261023/generation-independent-review.json`
(`986bc1975f776e4179fe15b689051f28e106b4d080d6d7d51a0245b4e1aa0758`)
passed. Root separately verified the packet, carryover and report references and
preflight: zero fresh starts, 40 historical, no extra roots or forbidden actions.
The coordinator's `budget-declaration-generation.json`
(`057699a5bfcd6feab6ca28d4f5ce8dcca4133672a2f2803f608c8ee18d932dfe`)
binds one fresh generation plus both later judges to total cap 43 under the
owner's delegated spending policy. It is not a claim of numeric owner approval.
Generation ran in tmux `ls5-generation-20261023` without automatic retry.
Fresh-capture integrity and external-abort review passed before pooling; concrete
judge-pool sandbox checks passed before the two sequential blind judgments.


Fresh Sol PRR run `20261023T091047Z-en0mm6` completed without provider or capture
error. Integrity review `8409be95` audited 87 structured actions and all 15 scan
hits; public adjudication `6780fa9e` preserves the original record snapshot and
changes only `scan.verdict`. No external abort was observed. All eight natural
observations now pass canonical intake.

The judging packet is
`f9ecf9db12e0f51052910cf91b1f8437666dd7aebb835aa37315457cb0621b25` (860 files).
Independent review `3bb7d099` verified four anonymous clones per task, exact raw
patch joins, honest Git views without synthetic archive deletions, two public
dry runs and two actual fake-provider sandbox checks. Root verified its 42
references and preflight at one new/41 overall starts. Judgment declaration
`d84375db735d5bc6fb465e951305a1b6365114df9d77e9e6ddcb7cb6ea8c4745`
binds the same original cap-43 declaration to this packet. Both Sol-high judges
completed sequentially in tmux `ls5-judging-20261023`. RPI integrity review
`760b4346` and PRR review `6d000a8d` passed; public adjudications `21bd9591`
and `10e92ea7` cleared only scan verdicts, preserving all ratings and raw hits.
Canonical close exited zero and wrote `LS5-20261023/combined-readout.json`,
SHA-256 `2ba7325deb023dd254071348efef6bb3baee7d44738ab1a9f1bed0929e503486`.
Independent closure review `LS5-20261023/closure-independent-review.json`,
SHA-256 `12741dc301f195526eb43c00beb17e163cfbb4c0c3f94028f82c19fd8c730ad1`,
passed 67 reference checks, all eight original rating/patch/index joins, three
scan crosswalks and ten complete receipts, without rescoring.
RPI scores are Luna 4,4 and Sol 6,6; PRR scores are Luna 3,4 and Sol 6,6.
The gaps pass (2 and 2.5), but both Sol means of 6 fail the strict <5 target.
`two_task_qualification` is false and both adjustment directions are `too_easy`.
The [LS5 report](../reports/2026-10-23-luna-sol-functional-calibration.md) records
methods, exact evidence identities, consumption and limitations. Three new
physical calls plus 40 historical starts equal the declared cap 43; monetary
cost remains unavailable. Further iteration means designing naturally harder
tasks under the unchanged roles, functional rubric and three predicates, then
separately recording concrete prospective task/seed inputs and bounded spend.
No next task package, iteration budget or campaign is frozen by this closure.


## Task 8: Increase natural difficulty through settled-failure recovery

The [in-place failed-call calibration plan](2026-10-23-functional-calibration-inplace-failure-plan.md)
records the LS6 implementation, launch gates and subsequent integrity stop. Both new task packages
retain the original feature goals and add in-place recovery of a settled failed
call with present, valid and restorable checkpoint authority. Unknown interrupted
effects keep their existing barriers. PRR additionally requires the exact persisted
profile in caller and callee at each boundary, with no historical profile upgrade
or new zero-record exception. Conceptual design, complete task/fixture reviews,
real historical checkpoint feasibility, exact-package checks and the frozen
generation packet passed before dispatch.

All eight solutions must be fresh for the new task identities; no LS5 result is
rescored or carried. The coordinator selects ten new starts and prospective total
cap 53 under the owner's delegated spending policy. This selects offline work and
a bounded continuation, not an assertion of numeric owner approval or a frozen
launch packet. The controller runtime, rubric, roles, limits and three predicates
remain unchanged. The two historical tasks share this recovery obligation and do
not supply independent task-family evidence. No C1, V2, sealed-task or campaign
selection is added.


## Task 9: Enforce single-call dispatch and recover with equal tools

LS6 spent seven starts: two complete Luna observations, two interrupted Sol roots
and three undeclared nested Sol roots at effort `xhigh`. The guard disabled native
multi-agent features but admitted same-model shell CLI reentry; the monitor stopped
the batch. This is an integrity incident, not a difficulty result. Both Luna
observations passed separate integrity review, including one natural delivery
failure, and remain preserved without quality scores.

The [single-call recovery plan](2026-10-23-functional-calibration-single-call-recovery-plan.md)
owns the selected correction and prospective execution. It reuses cap-one policy
to block inherited CLI reentry before dispatch, including nested metadata queries.
That tool change requires both arms to be fresh: eight generations and two judges,
ten new starts, 50 historical and cap 60. The earlier conditional cap-58 carryover
proposal was superseded before any recovery call. No historical record/runtime
identity is relabeled; no task byte, rubric, model, effort or threshold changes.
Implementation, independent review, affected runtime tests, actual fake-provider
sandbox checks and hash-bound declarations precede the next dispatch.

LS7 completed those prerequisites and launched six sessions before an independent
review observed a PRR Luna attempt reading and copying a historical implementation
outside its candidate. The coordinator stopped both active PRR attempts and all
later dispatch. Four earlier RPI captures are independently accepted but unscored;
the interrupted PRR attempts are unusable, and both Sol PRR and both judges remain
unstarted. Total spend is **56 starts**. The linked plan records original artifacts,
public scan crosswalks, the incident and its preservation. Correct the general
filesystem boundary before selecting a fresh iteration; do not patch LS7 in place
or count this incident as a failed difficulty comparison.

## Task 10: Isolate the filesystem and prepare a fresh LS8 comparison

The [filesystem isolation plan](2026-10-23-functional-calibration-filesystem-isolation-plan.md)
owns the selected correction: replace ambient host-root access with an empty-root
Bubblewrap environment and explicit tool, unit-home and task grants. Judge grants
come from validated score inputs; generic batches/references retain their existing
contracts, while LS8 uses four anonymous clones and no references. Private-home
receipt discovery preserves existing signatures, original evidence and canonical
joins. Minimal native configuration, credentials, tools and result delivery require
executable offline proof before implementation acceptance and live preparation.

Distinct Sol plan review accepted the six-task plan before implementation. The
coordinator selects ten new sessions, 56 historical and total cap **66**, under the
owner's removed routine spend-approval policy. This is not numeric owner approval
or a launch declaration: runtime verification, exact freezes, independent packet
reviews and linked declarations remain required. Both arms produce all eight
observations afresh because their filesystem capabilities change; valid LS7 RPI
captures remain unscored history. Task bytes, model roles/efforts, the functional
rubric, gap and strict score interval remain unchanged. No C1/V2, sealed-task,
campaign or evaluator qualification follows from this correction.
