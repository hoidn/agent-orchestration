# Functional task-difficulty calibration implementation plan

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
no judge ran. Overall spend is 32 starts, with six unused under cap 38. The
semantic detector repair is selected offline; no new paid retry is selected.

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

## Task 4: Prospective LS2 apparatus recovery

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
