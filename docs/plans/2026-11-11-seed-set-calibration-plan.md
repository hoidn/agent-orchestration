# Seed-Set Calibration Plan

**Status: Plan (not started).** This page plans the scaled-down research step
the owner set on 2026-11-11: calibrate a small task set, then find two to four
simple workflow programs that run reliably and do at least as well as one
direct call at acceptable cost, and package them as seeds for a later genetic
search. The [current roadmap](2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md)
owns the direction; `AGENTS.md` ("Experiment rules") and the
[structural search driver](../design/orc_structural_search_driver.md#task-family-and-evaluator)
own the calibration, dominance and cost rules; the
[comparison harness](../../experiments/compare/README.md) owns sandboxing, the
model guard and the scan. This plan owns its task set, thresholds, budget and
selection rule. Its commands are for this machine and are not copyable
examples. It authorizes no spend: each tranche needs the owner's approval and
a ledger row.

**Headline exit test (fails today):** `experiments/seed_set/results/seeds.json`
exists, names its criterion and task-list hashes, and lists either two to four
programs that passed the frozen selection rule or the stop that prevented it.

## What this size can and cannot support

This is seed selection, not a test of the roadmap's H-Q. With 12 to 16 tasks,
6 direct runs and 3 workflow runs per task, the 90% interval on a workflow's
difference from direct is roughly ±16 to ±18 points (planner's estimate for
pass rates near 50%).

- **Can show:** a program that breaks or fails to finish; its call cost; a
  difference from direct of about 20 points or more; whether a direct run
  ever fails the visible check (if not, retry and repair do nothing).
- **Cannot show:** differences under about 15 points; an ordering among the
  seeds; equality with direct (a seed that passes is "not observed to be
  worse"; one truly 10 points worse passes half the time); anything beyond
  small fixes in this repository on Haiku at medium effort, or about long
  pipelines.
- **"Better" is not the selection test.** A seed with direct's quality and
  more calls is dominated by direct under the driver's definition. The
  readout marks each seed as dominating direct, dominated by it, or neither.

## Facts established while planning

Checked 2026-11-11 with provider-free probes. *Probe* rows are single runs.

| Fact | State |
| --- | --- |
| Haiku in the harness | Not possible today. `experiments/compare/shim/model-guard` admits only `claude-sonnet-5-5` for Claude (a stub-CLI probe refused `claude-haiku-5-5`, with and without `ORC_ALLOWED_CLAUDE_MODELS`); `scan.find_hits` marks any other Claude model a non-clearable hit; both shims force subagents onto Sonnet |
| Task supply, this repository | Non-merge commits since 2026-07-01 that are fix-worded and change `tests/` plus at most 5 files and 200 lines under `orchestrator/`: 58 on the first-parent line, 114 in all history; 393 without the fix wording |
| Oracle yield | Of the 58: 44 have a new test function that fails on the parent and passes on the fix; 28 have two or more and a clean fixed run (*probe*, one run per side) |
| Evaluation time | `repos.build_candidate` 3 s and 141 MB per clone; the new tests take a median 8 s, at most 62 s (*probe*, load average 45) |
| Existing programs | `experiments/orc_structural_search/seeds/`: `direct`, `implement_check_diagnose_repair`, `implement_review_revise`, `best_of_n`, `plan_then_implement`, sharing `run((task) (intent) (repo)) -> Outcome`, `common.orc` and the `dev_check.py` command. All bind Sonnet with a second-vendor reviewer; review-revise runs three rounds |
| New programs | Drafts of retry (32 lines), implement-check-repair (39) and one-round implement-review-revise (45) compile at target 2.39 (*probe*). Loop iterations are separate effect identities, so a retry is a new call |

## Step 1: Zero-spend preparation (6 to 7 working days)

Every command runs with `experiments/thread_m/no_provider/` first on `PATH`
and `export PYTHONPATH=$PWD`; at the end `experiments/thread_m/no-provider.log`
does not exist. Stop below 20 GB free (`df -h / /home`). Also reused from
Thread M: `env-freeze.txt` as the environment record, the June 2026 cutoff
with its 2026-07-01 floor, and item 5's mining, oracle and split method. Its
pool snapshot is not needed.

**1a. Admit Haiku (1 day).** `shim/model-guard` accepts the exact ID
`claude-haiku-5-5` only when `ORC_ALLOWED_CLAUDE_MODELS` lists it; the default
stays Sonnet-only. Both shims pin `CLAUDE_CODE_SUBAGENT_MODEL` to the single
allowed Claude model. `scan.find_hits` takes an `expected_claude_model` from
`prepare.scan`. `tests/experiments/test_compare_model_cap.py` gains: Haiku
admitted only when listed; Opus, Fable and unknown IDs still refused; a Sonnet
answer in a Haiku-bound run is a non-clearable hit; the pin equals the bound
model.

**1b. Task packages (2 days), `experiments/seed_set/build_tasks.py`.**

- *Mine:* the facts table's filter over all non-merge history, dates on or
  after 2026-07-01, no reverts, one commit per `git patch-id --stable`, a
  base that ignores `.orchestrate/`. Order by
  `sha256("seed-set-2026-11-11|" + sha)`; at most two tasks share a changed
  source file.
- *Oracle and split:* as
  [Thread M item 5](2026-11-11-roadmap-thread-m-zero-spend-measurement-plan.md#item-5-task-pool-for-the-phase-5-benchmark),
  steps 4 and 5: five runs each on parent and fix; two or more fail-to-pass
  test functions, the first in seed order being the visible check; a hidden
  run under 120 s.
- *Package* (`experiments/seed_set/tasks/<sha10>/`, the harness layout):
  `base_commit`; `seed/tests/…` (the fix's test files without the hidden
  fail-to-pass functions) and `seed/dev-check.json` (the visible node);
  `hidden/tests/…` (the fix's full files); `hidden_tests.txt` (each hidden
  fail-to-pass function and each touched test file); `intent.txt` (the commit
  subject); `task.txt` (subject and body, the visible check command, and the
  instruction to leave `dev-check.json` and existing tests alone and not run
  the whole suite). Drop a task whose text is under 80 characters, repeats a
  source line the fix adds, or omits a name its hidden tests need.
- *Checks, five of five:* visible and hidden fail on the seeded base and pass
  with the fix; no hidden function name occurs in the seeded tree.
- *Freeze:* stop at 40 admitted tasks, listed in seed order in `tasks.jsonl`
  with hashes and changed-line counts: 20 drawn, the rest in reserve. Under
  20 admitted: drop the fix-wording filter once, then stop.

**1c. Programs (1 day), `experiments/seed_set/programs/`,** in the seed
catalog's layout and contract, target 2.39, every call `claude-haiku-5-5`,
`:timeout-sec 1200`, effort `medium` (bound explicitly on both models: the
vendor's defaults differ, Haiku medium and Sonnet high):

| File | Calls | State |
| --- | --- | --- |
| `direct.orc` | 1 | Copy of the catalog seed, rebound |
| `retry_until_check.orc` | 1–3 | New. At most three rounds of: `reset_clone.py` (restore the seeded tree), implement, `dev_check.py`; stop at the first pass |
| `implement_check_repair.orc` | 1–3 | New, from the catalog's check-diagnose-repair. Implement, check, repair in place with the check output, at most two repairs |
| `implement_review_revise.orc` | 2–3 | New, from the catalog's three-round version. Implement, one review, one revision if asked |

Plus `common.orc`, `dev_check.py`, `providers.json`, `commands.json` and
`calibration/direct_sonnet.orc`, which differs from `direct.orc` in the model
literal only. Compile each and run each once through the public CLI behind
the shims with a scripted provider.

**1d. Runner and readout (1.5 days), `experiments/seed_set/study.py`.** One
run: `prepare.run_arm(spec=ArmSpec(...))` with `COMPARE_CLAUDE_MODELS` and
`COMPARE_MAX_CALLS` set, launch, `collect`, `scan --hash <fix>`, then
`check_first_attempt` (visible) and `hidden_failures` (hidden) on the final
patch; one row in `runs.jsonl` keyed by record path and patch hash; delete
the run's `cand-*` trees. Four runs at a time. The readout computes the
offline arms, the intervals and the rule. `tests/experiments/test_seed_set.py`
checks on fixtures: a deterministic split, no hidden function in a seeded
file, the offline retry, the selection rule, refusal of an unscanned run.

**1e. Evaluator check (0.5 day).** Known controls: every task's base is
rejected and its reference fix accepted, five of five. For the family, on the
first three tasks an engineer who has not read the fix writes a second fix
from `task.txt` and the visible check; the hidden set must accept it, and an
over-fitted test drops the task. One sandbox run with a stand-in CLI that
applies the fix confirms the visible check passes inside the sandbox.

**1f. Freeze.** Commit; `git worktree add --detach /home/ollie/seedset-rt
<commit>`; work root `/home/ollie/seedset-work`. Write
`experiments/seed_set/criterion.json`: model IDs and efforts, runtime commit,
hashes of `tasks.jsonl` and every program, the envelope, replicates, every
threshold and rule of Steps 2 and 3, budget caps, stop rules and the price
table with source and date. Its sha256 goes in the ledger before the first
call. A later apparatus fix is a ledger row with the new hash; thresholds do
not change.

## Step 2: Calibration (paid)

**Smoke (at most 10 Haiku calls, 1 Sonnet call),** on the last reserve task,
which then leaves the reserve: one direct run per model and one run of each
workflow. Pass: session metadata shows only the bound model, every patch is
collected and scored and the scan is clean. Whether token receipts are
complete is recorded.

**Tranche (80 Haiku, 20 Sonnet):** on the 20 drawn tasks, `direct.orc` four
times and `direct_sonnet.orc` once. A run passes when no hidden node fails.
Four, because with two runs a task Haiku solves half the time would be
dropped half the time.

- *Per task:* a **survivor** has 1 to 3 Haiku passes of 4. A task at 4 of 4
  is too easy and one at 0 of 4 too hard; both are recorded and unused.
- *Gates, over all drawn tasks:* (G1) at least 12 survivors; (G2) Haiku pass
  rate between 20% and 80%; (G3) Sonnet pass rate minus Haiku pass rate at
  least 10 points; (G4) at least 90% of runs end with a scored patch and no
  forbidden-model hit; (G5) of ten failed runs drawn in seed order and read
  by hand, none failed only because a hidden test demands the reference's
  internals (such a task is dropped and G1 recounted).
- *One redraw (40 Haiku, 10 Sonnet)* if G1, G2 or G3 fails: ten reserve
  tasks, those with the most changed source lines if Haiku was above 80%, the
  fewest if below 20%, otherwise the next in seed order; gates recomputed
  over all 30.
- *If a gate still fails:* stop. No workflow is evaluated; the report gives
  the calibration table, execution outcomes and cost, and no quality claim.

G3 is an observed advantage with a standard error near 12 points, not a
significance test. Survivors beyond 16 are cut in seed order.

**Assumption for the owner to confirm with the budget.** No judge or rubric
call is made: the family is scored by hidden tests, so it is qualified by the
oracle check of Step 1, and this tranche applies the difficulty rule's shape
(natural solutions, only the model varies, a predeclared gap, the advantage
observed) to the test outcome. `AGENTS.md` names the blind rubric as primary
for difficulty calibration; this plan reads that as bound to rubric-scored
families.

## Step 3: Seed evaluation (paid, on the survivors)

| Arm | Runs per task | How |
| --- | --- | --- |
| Direct | 6, fresh | Live |
| Re-roll `Q(k)`: retry with at most `k` = 2, 3 attempts (best-of-`k` by visible check has the same quality at `k` calls); random-of-3; any-of-3 (upper bound) | none | Offline, averaged over every ordered triple of a task's six direct runs, using each run's controller-side visible result. `Q(1)` is direct |
| Retry parity | 2, on the first six survivors | Live `retry_until_check.orc`; passes if every run completes, mean calls are within 0.5 and pass rate within 25 points of the offline figure for those tasks |
| Implement-check-repair | 3 | Live |
| Implement-review-revise | 3 | Live |

Direct runs first. They are fresh because the calibration runs chose the
tasks and would bias the baseline. If the visible check failed in under 20%
of them, the parity runs and implement-check-repair are not launched and the
readout says the check has no selecting power on this set.

**Envelope and scoring.** 1,200 s per call, `COMPARE_MAX_CALLS` 1 or 3,
3,600 s per run. The final patch is scored whatever the typed outcome. A
failed run or a timeout scores 0; a provider or sandbox incident is resumed
once with `resume.sh`, then excluded and listed. Quality `q` is the mean over
tasks of the per-task pass fraction; cost `c` is mean provider calls per run,
admissible because every call is one model at one effort. Metered tokens
(`metering.receipts`) are reported beside it, priced at Haiku's higher
published tier; if nested sessions appear in over 10% of an arm's runs, cost
comparisons use tokens only.

**Selection rule (frozen).** `direct` is always in the set as the reference.
Another program is a seed when all hold:

1. at least 95% of its runs complete;
2. `q ≥ q_direct − 0.10`;
3. re-rolling at equal calls does not beat it: `q ≥ Q(k) − 0.10`, with `k`
   its mean calls rounded to 1, 2 or 3, halves up (vacuous for retry itself);
4. `c ≤ 3.0 × c_direct`, and the same for priced tokens where metered;
5. its distinctive step (a second attempt, a repair, a revision) ran in at
   least 20% of its runs;
6. for retry, the parity check passed.

The readout gives each arm's `q` and each difference from direct with a 90%
bootstrap interval over tasks (10,000 resamples, fixed seed), names every
comparison whose interval spans the tolerance, and applies the driver's
dominance test against direct with `tau_q = tau_c = 0.10`.

**Extension (reserved, at most 192 Haiku calls).** A live workflow that
misses or passes rule 2 or 3 by under 5 points gets two more runs per task,
once.

## Step 4: Output

`experiments/seed_set/`: `programs/`, `tasks/`, `tasks.jsonl`,
`criterion.json`, `results/runs.jsonl`, `results/readout.md` (one page: the
calibration table, the arm table with intervals, the rule applied, limits)
and `results/seeds.json` (selected programs with file hashes, `q`, `c`,
intervals, and the criterion, task-list and runtime hashes). A later search
passes the program paths as seeds; `mode1.check_seed_catalog` pins
`experiments/orc_structural_search/seeds/capped` today, so its plan either
copies the seeds there or changes that check.

## Budget request

| Tranche | Released by | Haiku cap | Sonnet cap |
| --- | --- | --- | --- |
| Smoke | Owner approval; criterion hash in the ledger | 10 | 1 |
| Calibration | Smoke passes | 80 | 20 |
| Redraw | A failed G1, G2 or G3 | 40 | 10 |
| Seed evaluation | All gates pass | 420 | 0 |
| Extension | The extension rule | 192 | 0 |
| **Cap** | | **742** | **31** |

Expected without redraw or extension: about 400 Haiku and 21 Sonnet calls.
The vendor's list prices put a Sonnet token at about 20 times a Haiku token
(table cached 2026-11-03; re-read at freeze). Tokens per call are unknown
until the smoke and are reported before the seed evaluation is released.
Allowance does not move between tranches; there is no top-up after a null.

## Stop rules

- Fewer than 20 tasks admitted after the one widening: stop before spend. The
  next source is external repositories by Thread M item 5's method, which
  needs the harness to accept another candidate source.
- A smoke failure: fix the apparatus offline; the owner renews the allowance.
- A hidden function name in a transcript or patch, or a scan hit on
  `github.com`, `git fetch` or the fix hash: the run is contaminated; three
  such tasks stop the study.
- A forbidden-model hit, over 10% of a tranche's runs excluded as incidents,
  a cap reached, or under 20 GB free: stop.
- Only `direct` passes the rule: record "no workflow qualified at this size".

## What this plan makes harder

- The seeds are tuned to one repository, one language and one model tier.
- Hidden tests sit in this repository from the freeze commit on; a later task
  set must use earlier bases or move the packages out.
- Retry and repair depend on a check the direct agent can already run, so a
  null there says little about checks an agent cannot run itself.

## Not verified while planning

- Whether the GitHub repository is public. If it is, the fixes are fetchable;
  the sandbox keeps network access, so the scan is the control.
- Call duration and tokens per call (the smoke measures both), and how often
  a direct run fails the visible check (the calibration runs measure it).
- Whether `metering.receipts` returns complete Claude usage from the private
  homes (the Phase 1 search logged consumption as unavailable). If not, cost
  is calls only, which the rule admits here.
- Whether Claude Code's in-process subagents can be switched off through the
  provider command; they are pinned to the bound model and counted instead.
- The oracle yield beyond one run per side and off the first-parent line, and
  whether one-line commit messages make usable task texts (the 80-character
  rule and the second-fix check are the screens).

## Ledger

| Date | Entry |
| --- | --- |
