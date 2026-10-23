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

Offline implementation and preparation are selected. **No fresh paid dispatch
is authorized yet:** twenty-six historical sessions are spent. Prepare a concrete
ten-session packet (eight generations and two judges), proposing an overall cap
of thirty-six. Approval of that bounded packet is the final launch prerequisite;
the owner's general continuation instruction does not supply a new numeric cap.

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

- [ ] Freeze a clean runtime after verified integration; declare the exact model
  and effort per arm, Sol-high judge, one functional rubric and all three rules.
- [ ] Prepare eight fresh attempts and commands using existing public entry points;
  preserve the prior 26 starts, full LH/TD/TD2 evidence and native receipts.
- [ ] Use a bounded experiment operator with complete inventory, no automatic
  retry and explicit owner budget binding. Reuse proven helpers without mutating
  previously frozen operators or introducing a campaign abstraction.
- [ ] Validate commands, model policy, private masks and honest review baseline
  with zero-provider dry runs/fake CLI; freeze source, tests, inputs and proof.
- [ ] Independently review the concrete packet, then request only the missing
  ten-session authorization (proposed overall cap 36). Do not launch beforehand.

## Decision ledger

| Decision | Consequence |
| --- | --- |
| Owner selects Luna high versus Sol 6.1 low | Fresh arm identities above; actual advantage must be observed |
| Owner requests simpler rubric | One functional 0–8 score; no independent style/scope credit |
| Existing strict target and gap retained | Apply to `sol_low`; both tasks and full denominators required |
| Prior 26-session cap is exhausted | Offline preparation proceeds; proposed ten further sessions remain unapproved |

## Offline implementation evidence

The functional workflow and exact-selector reader are implemented. The affected
16-worker comparison suite passed 474 tests (`/tmp/compare-functional-verify-wzn07het/pytest.log`).
Independent review found lost historical smoke coverage and an oversized module;
the final revision restores all five historical cases alongside four functional
cases and shortens the stale module description without compressing code. The
final nine-case public Bubblewrap/orchestrator smoke passed in 18.03 seconds
(`/tmp/functional-calibration-revision-20261022/public-smoke-final.log`). Changed
modules collected 139 tests; the focused reader/difficulty/workflow checks passed
9/5/3 respectively. Historical scoring workflows remain byte-identical.

These checks use scripted providers and synthetic receipts; they establish
software mechanics, not task difficulty, judge validity or model superiority.
The LS1 operator has 32 passing offline checks and preserves 3,425 pinned
historical files. Concrete runtime/command/mask qualification remains Task 3.
