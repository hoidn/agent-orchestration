# Roadmap Thread M: Zero-Spend Measurement Plan

**Status: Plan (not started).** This page plans Thread M of the
[current roadmap](2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#thread-m-zero-spend-measurement-starts-in-phase-0):
five measurements that spend no provider calls. The roadmap owns the
hypotheses, their refutation conditions and the stop rules; `AGENTS.md`
("Experiment rules") and the
[structural search driver](../design/orc_structural_search_driver.md#task-family-and-evaluator)
own the rules for qualifying a task family and an evaluator; the
[comparison harness](../../experiments/compare/README.md) owns clone-id joins.
This plan owns only the method, paths and checks of the five items. Its
commands are written for this machine and are not copyable examples. It
authorizes no spend: any later provider call needs an owner-approved budget and
a row in the ledger of the plan that makes it.

**Goal:** turn four claims the project already paid for into counted results
(resume in real use, crash behaviour against LangGraph, errors before spend
against typed Python, what the old candidate pools can and cannot say), and
find out whether a task pool for the Phase 5 benchmark exists.

**Headline exit test (fails today):** `docs/reports/thread-m/` holds five
reports and `grep -c '^\*\*Verdict:' docs/reports/thread-m/*.md` counts one
verdict line in each. The task-pool report's verdict is either a pool size
with the hash of its frozen splits, or the stop.

## Global constraints

- No provider or model call, by any route. Every command of this plan runs
  with `experiments/thread_m/no_provider/` first on `PATH`; that directory
  holds two stubs, `claude` and `codex`, which append their arguments to
  `experiments/thread_m/no-provider.log` and exit 97. **Check at the end:** the
  log does not exist. The existing kill tests install their own stand-ins and
  are unaffected.
- Evidence roots outside the repository are read-only. Scripts open them for
  reading and write only under `experiments/thread_m/`,
  `experiments/task_pool/`, `docs/reports/thread-m/` and `/home/ollie/tm-pool/`.
- Numbers about past experiments come from the harness's stored clone-id join
  (`results.json` written by `experiments/compare/summarize.py`) or from a
  cited ledger line, never from a positional or re-derived join.
- Run from the repository root with `export PYTHONPATH=$PWD`: the editable
  install resolves `orchestrator` to an old worktree.
- The machine is loaded (load average about 40 on 32 cores) and disk is tight
  (36 GB free on `/`, 62 GB on `/home`, 2026-11-11). Run `df -h / /home` before
  any test run or pool build; stop below 20 GB free on the target filesystem.
  No broad test suite is part of this plan.
- Other sessions work in this checkout. Commit by pathspec only; touch no
  file outside the paths above. No assistant attribution in commit messages.
- Execution follows the repository's subagent policy: implementation and
  review by different agents. This plan names no model for any role.

## Facts established while planning

Checked on 2026-11-11. A row marked *probe* is a planning observation from one
scratch run, not a result.

| Fact | State |
| --- | --- |
| Type checkers | `pyright` 1.1.403 in the base Python 3.13.9 (works; needs `node`, present). `mypy` 2.4.0 only in the DAQ environment and in conda `ptycho311`; not in base |
| LangGraph | Only in `experiments/adversarial_daq/.venv` (Python 3.13.9, system site packages on): `langgraph` 1.2.16, `langgraph-checkpoint-sqlite` 3.1.2, `pydantic` 2.10.3. The directory is untracked. Its `orchestrator` import resolves to the pinned copy `research/agent-orchestration-main` (`bb9cb30d`), so only the LangGraph and typed-Python sides run in it |
| DAQ LangGraph code | 139-line `baseline.py` files under the ignored `artifacts/` tree (functional API, `SqliteSaver`, `durability='sync'`), specific to the DAQ simulator. Usable as an API reference, not as the pipeline |
| `gh` | 2.45.0 installed; its token is invalid. Unauthenticated GitHub REST works: 60 core requests per hour, 10 searches per minute |
| Other tools | `git` 2.43.0, `uv` 0.8.15, `bwrap` (no-network sandbox with an emptied home verified), `scipy` 1.16.0, Python 3.11, 3.12 and 3.13. No `docker` or `podman` |
| Haiku cutoff | The vendor's [models overview](https://platform.claude.com/docs/en/about-claude/models/overview) and the Haiku 5.5 model page both give `claude-haiku-5-5` a training data cutoff and a reliable knowledge cutoff of June 2026 (the same for `claude-sonnet-5-5`). Not established for `gpt-5.6-terra` |
| Existing kill tests | 665 collected tests in nine modules; the window campaign alone is 42 effects × 10 windows = 420 kill-and-resume cells over 11 scenarios, plus 10 must-not-repeat cells. Collected, not run |
| Pool data | E-B2, both Phase 1 pools and E-A have `results.json` with per-clone, per-judge ratings; E-A has `hidden: null` on all 54 clones. E-B3's pool directory is gone; its ratings and hidden fractions survive as two readout files keyed by the same 13 clone ids |
| Run state | 135 run memos survive in five roots; 3 show a second attempt of an effect. Phase 1's driver log has 79 rows, `resume_count` 0 on all 67 evaluation rows (*probe*) |
| LangGraph kill and resume | Graph API, SQLite, `durability="sync"`: after a hard kill inside the second node, resume re-ran only that node. Functional API: a completed task was re-run when the kill came immediately, not when it came 2 s later (*probe*) |
| Candidate repositories | GitHub search counts 5,880 public Python repositories with a permissive licence, over 500 stars and a push after 2026-07-01. In six hand-picked ones, fix-worded commits since that date touching source and tests in at most five source files numbered 0, 0, 1, 2, 47 and 79 (*probe*, before any test was run) |

## Order, parallelism and what each item decides

Step 0 first. Then items 1, 4 and 5 are independent and can run in parallel;
item 5 starts early because it is the long one. Item 3 reuses the typed Python
steps written for item 2, so 2 precedes 3 (or the shared file is written
first and the two then run in parallel). With one engineer: 0, 4, 1, start 5,
2, 3, finish 5.

| Item | Needs network | Needs tools not in base | Effort | Decides |
| --- | --- | --- | --- | --- |
| 0 Snapshot | no | no | 0.5 day | nothing; protects inputs that are not durable |
| 1 Resume retrospective | no | no | 2–3 days | nothing by rule; states how often resume was available, used and worked, as input to Phase 1 and to the H-G3 measurement |
| 2 H-G1 crash matrix | only if the DAQ environment is gone | LangGraph (DAQ environment) | 5–6 days | H-G1: supported, refuted, or parity |
| 3 H-G2 defect list | no | `mypy` (DAQ environment) | 4–5 days | H-G2: supported or refuted |
| 4 Pool reanalysis | no | no | 1.5–2 days | nothing; descriptive |
| 5 Task pool | yes (GitHub, PyPI) | no (`gh` login optional) | 10–15 days, go/no-go at day 4 | whether Phase 5 can run, at which size, and whether Phase 6 sets can be frozen |

Total: 5–6.5 engineer-weeks; about three calendar weeks with two people.

Roadmap stop rules this plan reports against:

- **H-G1 and H-G2.** If item 2 ends in parity and item 3 in "refuted", the
  engineering claim narrows to H-G3 and the "where chosen" statement, and the
  owner revisits whether a custom language is warranted (the
  [research charter's decision rule](2026-09-08-orc-research-charter.md#decision-rule)).
  Otherwise the reports name the cells and defect classes where ORC differs,
  and those become the claim.
- **Item 5.** If fewer than 60 tasks from 12 repositories can be frozen,
  Phase 5 does not run and H-Q is recorded as not tested.

## Step 0: Environment check and input snapshot

```bash
cd /home/ollie/Documents/agent-orchestration && export PYTHONPATH=$PWD
TMPY=experiments/adversarial_daq/.venv/bin/python
$TMPY -c "from importlib.metadata import version as v; print(v('langgraph'), v('langgraph-checkpoint-sqlite'), v('mypy'), v('pydantic'))"
# expected: 1.2.16 3.1.2 2.4.0 2.10.3
pyright --version; uv --version; bwrap --version; df -h / /home
```

If the DAQ environment is missing or prints other versions, build
`/home/ollie/tm-env` (network) and use its interpreter as `TMPY`:
`uv venv /home/ollie/tm-env --python 3.13 && uv pip install --python /home/ollie/tm-env/bin/python langgraph==1.2.16 langgraph-checkpoint-sqlite==3.1.2 mypy==2.4.0 pydantic==2.10.3`.
Save `$TMPY -m pip freeze` as `experiments/thread_m/env-freeze.txt` either way.

Copy these small files to `experiments/thread_m/inputs/<same relative name>`
and write `experiments/thread_m/inputs/SHA256SUMS`. A hash that differs from
the one below is recorded in the ledger, not repaired.

| Source | sha256 on 2026-11-11 (first 16) |
| --- | --- |
| `/home/ollie/Documents/agent-orchestration-compare-evidence/eb2/batch/pool/records/results.json` (and `mapping.json`, `patches/*.diff`) | `357b10ec5b9a2d8b` |
| `/home/ollie/Documents/agent-orchestration-compare-evidence/eb3/primary-readout.json` | `77d46bde3db6e385` |
| `/home/ollie/Documents/agent-orchestration-compare-evidence/eb3/hidden-secondary-readout.json` | `d1a8a819340cc407` |
| `/home/ollie/ss-pools/phase1/resume-projection-integrity/records/results.json` (and `mapping.json`, `patches/*.diff`) | `2426abe50453a8d8` |
| `/home/ollie/ss-pools/phase1/pure-result-replay/records/results.json` (and `mapping.json`, `patches/*.diff`) | `d8dcfc37d94939f7` |
| `/home/ollie/Documents/agent-orchestration-compare-evidence/ea/pool-records/results.json` (and `mapping.json`, `patches/*.diff`) | `944cc0fa93690d71` |
| `/home/ollie/ss-evidence2/log.jsonl`, `calls.json`, `joined.json`, `phase1-readout.json` | `796d689337b1186f` (log) |
| `/home/ollie/ss-evidence-incident1/log.jsonl`, `/home/ollie/ss3-evidence/log.jsonl` | recorded at copy |
| `/home/ollie/sc-evidence/ledger.md` | `a9ee1ac181021c8e` |
| every `memo.jsonl` found by `find <root> -maxdepth 7 -name memo.jsonl -not -path '*/cand-*'` under `/home/ollie/ss-work2`, `/home/ollie/ss-work-incident1`, `/home/ollie/ss3-work`, `/home/ollie/Documents/agent-orchestration-compare-evidence`, `experiments/adversarial_daq/.orchestrate` | recorded at copy (135 files expected) |

**Check:** `sha256sum -c experiments/thread_m/inputs/SHA256SUMS` passes and the
directory is under 20 MB. Above 20 MB, leave the memos external and keep only
their hashes. A missing source is listed in the ledger with the item it
affects; items 1 and 4 say below what they do without it.

## Item 1: Resume retrospective

**Question:** in the October experiments, how often was a provider-spending
run interrupted, how often was resume tried, how often did it work, how often
was the work relaunched instead, and how much provider time was lost?

**Definitions.**

- *Interruption:* a launched run that ended without its terminal result for a
  reason other than the task's own outcome (kill, host pause, quota or
  capacity refusal, envelope timeout, full disk, guard stop, CLI failure).
- *Resume attempted:* `orchestrator resume` or a harness `resume.sh` was run on
  that run. Evidence: a ledger sentence; a `launch-<k>.log` with k ≥ 1; a
  driver row with `resume_count` ≥ 1; or, in one `memo.jsonl`, a `started`
  record with attempt n+1 for an identity whose attempt n has no `committed`.
- *Resume succeeded:* the same run id reached `terminal` with outcome
  `completed` and kept its earlier commits.
- *Relaunch:* a new run id for the same unit of work (task, arm, replicate).
- *Time lost:* for a relaunch, the summed duration of every attempt in the
  abandoned run; for a successful resume, the duration of the uncommitted
  attempt only. *Time resume would have kept:* the summed duration of the
  committed attempts in an abandoned run. Durations come from memo `time`
  fields (epoch seconds: `committed` or `failed` minus `started`), from driver
  `wall_clock_sec`, or from a ledger sentence; each figure is labelled
  measured, ledger, estimated or unknown.

**Method.**

1. *Ledger census (by reading).* For each of the 18 October rows of
   [what the experiments established](../reports/2026-11-11-what-the-experiments-established.md)
   (E-A to PRR-P2), read the sources that page lists under "Sources for
   interruptions, resumes and relaunches" and write one row per interruption
   into `events.csv`: `study, unit, date, cause, provider_running, resume_attempted, resume_outcome, relaunched, time_lost_min, time_lost_basis, time_resume_would_keep_min, source`.
   `source` is a path with a section anchor, or a path with a line number
   when the file is immutable evidence. A study with no interruption gets one
   row with `cause=none` and the source consulted.
2. *Machine census.* Write `census.py` (standard library, under 150 lines). For
   each memo in the snapshot it reports the run id, terminal outcome,
   identities with more than one `started`, uncommitted starts, and attempt
   durations; for each driver `log.jsonl` it tabulates `outcome`,
   `resume_count`, `incidents` and `wall_clock_sec`; for each records
   directory under `/home/ollie/ss-work2/records`, `/home/ollie/ss-work-incident1/records`
   and `/home/ollie/ss3-work/records` it counts `launch-*.log` files.
3. *Reconcile.* For every study with surviving state, compare the two and list
   each difference. Totals are computed by `census.py --summary events.csv`,
   not typed.

**Inputs.** In the repository: the plans and reports named by the
"Sources" section above. Outside it: the Step 0 snapshot. Work roots of E-A,
E-B, E-B2 and E-B3 (`/home/ollie/compare-work*`, `/home/ollie/eb3-work`,
`/home/ollie/calib-runtime`) no longer exist; for those studies only the
copies under `agent-orchestration-compare-evidence` and the ledgers remain. If
a root is missing, the ledger census still stands, the study's machine column
reads "state not available", and time lost stays as the ledger states it.

**Outputs.** `experiments/thread_m/resume_retro/census.py`, `events.csv`,
`machine_census.json`; report `docs/reports/thread-m/resume-retrospective.md`
(one table per study, one totals table, the reconciliation list, and a
verdict line of the form "N interruptions, R resumes attempted, S succeeded,
L relaunches, T provider-hours lost of which K a resume would have kept").

**Acceptance check.** All 18 October studies appear; every row has a source
that resolves; the census reproduces two facts already on record (Phase 1:
five runs cut off after 25–70 minutes and relaunched, not resumed; DAQ: two
resumes, one after a CLI failure and one after a capacity failure) or the
report explains the difference; `tests/test_thread_m.py::test_resume_census`
passes on a three-memo fixture (clean, resumed, abandoned).

**Effort:** 2–3 days. **Main risk:** the ledgers are prose and the largest
studies' run state is deleted, so several time figures will be ledger
statements or unknown; the result is a count with stated gaps, not a
measurement of what resume saves.

## Item 2: H-G1 crash matrix

**Hypothesis, as the roadmap states it.** "For every kill point and effect
kind, a resumed run returns the same value, re-dispatches no committed effect
and recovers a completed uncommitted agent turn without re-dispatch."
**Refuted by:** "Any duplicated committed effect or lost completed turn. It
is parity, not an advantage, if LangGraph checkpoints pass the same matrix."
**Prior:** the [adversarial DAQ study](../../experiments/adversarial_daq/RECORD.md)
found parity on its resume claims.

### 2a. Publish the ORC matrix from the existing tests

Sources (all scripted providers):

| Module | Effect kinds | Kill points |
| --- | --- | --- |
| `tests/test_workflow_evaluated_recovery.py`, `tests/test_workflow_evaluated_recovery_branches.py`, tables in `tests/workflow_evaluated_recovery_cases.py`, gates in `tests/workflow_evaluated_recovery_helpers.py` | provider, command | windows W0–W9 of the first attempt of each of 42 effects in 11 scenarios; the launcher command again under `must_not_repeat` |
| `tests/test_workflow_evaluated_agent_turn_recovery.py`, `tests/test_workflow_evaluated_agent_consumer_smoke.py` | agent turn | started, intent, native completion, proof, committed, settled; orphaned process group; unprovable quiescence |
| `tests/test_workflow_evaluated_resume_kills.py` | command, provider | process-group kill after the first commit, through the CLI |
| `tests/test_workflow_evaluated_run_ref_kills.py` | child workflow | two parent settlement gaps × two child targets |
| `tests/test_workflow_evaluated_host_input_recovery.py` | human input | started, suspended, request view |
| `tests/test_workflow_evaluated_phased_recovery.py` | phased provider | to be tabulated from its parametrization |
| `tests/test_workflow_evaluated_parallel_resume.py` | parallel map | replay of recorded evidence only; live kill and resume is roadmap Phase 2 and is shown as "no test" |

What a window cell asserts (from `_expected_held`, `_expected_recovery` and
`_expected_dispatches`): the resumed value equals the uninterrupted value;
the committed memo prefix and every earlier effect file are byte-identical;
every other effect is dispatched once; the killed effect is dispatched once
for W0, W1 and W9, once as attempt 2 for W2–W5, and twice (attempts 1 and 2)
for W6–W8; a second resume changes no byte. Under `must_not_repeat`, W2–W8
refuse with `lexical_restore_pending_effect_unsafe` and change nothing. For an
agent turn killed between native completion and commit, the same attempt is
recovered with no second dispatch.

**Method.**

1. Write `orc_cells.py`: import `CELLS`, `BRANCH_CELLS` and `LAUNCH` and emit
   one row per cell (scenario, effect ordinal, effect class, window, asserted
   properties from the paragraph above).
2. For the other modules, collect node ids
   (`pytest --collect-only -q <modules>`) and write `cells.json` mapping each
   node id to effect kind, kill point and asserted properties, or to "not a
   kill-point cell" with a reason. The mapping must cover every collected id.
3. Run the nine modules once at a recorded commit, using the launch recipe of
   the [Phase 0 plan](2026-11-11-roadmap-phase-0-records-and-baseline-plan.md#task-4-test-baseline)
   (short `--basetemp`, existing session), after `df`:
   `pytest -q -n 16 --dist=worksteal -p no:cacheprovider --basetemp=/home/ollie/tm-bt --junitxml=experiments/thread_m/crash_matrix/orc-junit.xml <the nine modules>`.
4. Join cells to JUnit outcomes into `orc-matrix.csv` and render the
   kill point × effect kind table. A cell with no test says "no test"; a
   failing cell says what failed.

### 2b. The same pipeline shape on a LangGraph checkpointer

**Pipeline shape (decided):** the `improve` core scenario of the window
campaign: review (provider, answers REVISE), revision (provider), review
(provider, answers APPROVE), launch (command). It has both effect classes, a
loop and a branch, and the ORC side needs no new code. The agent-turn row
uses the same graph with the revision step served by a fake agent with a
native session store, against the six kill points of the ORC consumer smoke.

**Files** (in `experiments/thread_m/crash_matrix/`, run with `$TMPY`):
`steps.py` (typed step functions; shared with item 3), `fake_provider.py` (an
executable that appends `step|round|pid` to a dispatch log, can block after
dispatch or after writing half its reply, and answers from the step and
round, never from a call count), `lg_pipeline.py` (`StateGraph`, one node per
effect, `SqliteSaver`, `durability="sync"`, fixed `thread_id`),
`lg_kill_matrix.py` (baseline run, then one killed-and-resumed run per cell).
The graph API is used, one node per effect; the functional API is not, and
the report says so with the probe above.

**Kill points (decided).** Five points that both systems can be stopped at,
with a `SIGKILL` to the process group:

| Point | Meaning | ORC windows | LangGraph hook |
| --- | --- | --- | --- |
| K0 | before the step's dispatch | W0–W5 | node entry, before the provider is spawned |
| K1 | provider dispatched and running | W6 | the fake provider blocks after logging |
| K2 | provider has written half its reply | W7 | the fake provider blocks mid-write |
| K3 | reply complete, step not yet durable | W8; agent turn "completed", "proof" | before the checkpointer's `put`/`put_writes` for that node returns |
| K4 | step durable, next step not started | W9; agent turn "committed", "settled" | after that call returns |

**Same result (decided).** A cell passes when, after kill and resume:

1. the final value equals that system's own uninterrupted value;
2. every step that was durable at the kill has exactly one line in the
   dispatch log;
3. the killed step has at most the dispatches ORC is asserted to make: K0 1,
   K1–K3 2 for a provider or command, K3 1 for an agent turn, K4 1; for a
   step declared non-repeatable, never 2 (completing with one dispatch and
   refusing without a dispatch both pass);
4. invoking the finished run again dispatches nothing and returns the same
   value.

Each LangGraph cell runs in two variants: *library* (the checkpointer as
shipped) and *glue* (the node first looks up a completed turn or a
non-repeatable step's receipt by `thread_id/step/round` before dispatching).
The glue is counted in lines and kept free of pipeline-specific names.

**Verdict rule.**

- *Refuted:* any ORC cell fails property 1, 2 or the agent-turn part of 3.
- *Parity:* the library variant passes every cell ORC passes; or the glue
  variant does with at most 50 lines of glue. (The 50-line bound is a
  planner's decision, recorded in the ledger; the owner can change it before
  the run.)
- *Supported with a named difference:* otherwise; the report lists the cells
  LangGraph fails and the glue size at which it passes.
- Cells with no ORC test are listed as untested and count for neither side.

**Outputs.** `experiments/thread_m/crash_matrix/` (`orc_cells.py`,
`cells.json`, `orc-matrix.csv`, `orc-junit.xml`, the four LangGraph files,
`lg-results.json`); report `docs/reports/thread-m/crash-matrix.md` with the
ORC matrix, the shared K0–K4 table for both systems and both variants, the
ORC and LangGraph line counts of the pipeline, and the verdict.

**Acceptance check.** `cells.json` covers every collected node id of the nine
modules; `orc-junit.xml` names the commit and every mapped test has an
outcome; `lg-results.json` has 4 steps × 5 points × 2 variants, the agent-turn
row and the non-repeatable row, each with value, dispatch counts and pass or
fail; the LangGraph baseline run and one cell are repeated three times with
identical results; `tests/test_thread_m.py::test_lg_matrix_one_cell` passes
(K1 on the launch step, library variant).

**Effort:** 5–6 days (2a: 1.5; 2b: 3.5–4.5). **Main risk:** K3 and K4 hook a
library internal that is version-specific, so the mapping between ORC's
windows and LangGraph's is a judgement the report must show; the expected
outcome, given the DAQ prior, is parity except on agent-turn recovery and
non-repeatable steps.

## Item 3: H-G2 seeded defect list

**Hypothesis, as the roadmap states it.** "The checker rejects, before the
first provider call, defect classes that a typed Python equivalent reports
only at run time." **Refuted by:** "A typed Python control with a standard
type checker catching the same set."

**Pipeline.** The item 2 shape with a bounded loop: review (provider,
returns a variant APPROVE / REVISE / BLOCKED), revision (provider, returns a
record), at most three rounds with an exhaustion outcome, launch (command,
returns a record). The first effect is a provider call, so anything found at
run time has already spent at least one call. Two clean versions:

- `pipeline.orc` with `commands.json`, `providers.json`, `prompts.json`
  (hand-written, about 40 lines, newest target);
- `pipeline.py`: plain Python using `steps.py`; every provider and command
  result is a Pydantic model with `extra="forbid"` and strict types; variants
  are tagged unions matched with `match` and `assert_never`; provider and
  command names are `Literal` types; no `Any`, no `# type: ignore`.

**What "caught before the first provider call" means.**

- ORC: `python -m orchestrator compile pipeline.orc --command-boundaries-file commands.json --provider-externs-file providers.json --prompt-externs-file prompts.json --diagnostics-json`
  exits non-zero. `run` compiles first, so this holds for every input.
- Typed Python (primary): `$TMPY -m mypy --strict pipeline.py` or
  `pyright` in strict mode reports an error; either counts.
- Typed Python (secondary, reported beside the primary): `$TMPY -c "import pipeline"`
  fails with no effect run (model or registry validation at import).
- A failure during a scripted run does not count for either side, wherever it
  occurs; the number of provider dispatches before it is reported.

Each defect gets one outcome per side: `static` (diagnostic on the seeded
lines or naming the seeded symbol), `static-elsewhere`, `startup` (Python
only), `run-time after n provider calls`, or `silent` (the scripted run
completes).

**The defect list (fixed here; a change needs a ledger row before any check
is run).** *Observed* means the mistake is recorded in the
[authoring audit](../reports/2026-11-11-project-audit/authoring.md) (section
5), the [practical review](../reports/2026-11-11-roadmap-review/practical.md),
the DAQ study's `research/orc-notes.md` or the harness rulings R34 and R37;
*derived* means it comes from the roadmap's brief for this item.

| # | Author's mistake | Origin |
| --- | --- | --- |
| 1 | Reads a field the upstream record does not have (typo across a handoff) | observed |
| 2 | Uses a handoff field at the wrong type (Int compared with String) | observed |
| 3 | Builds a record without a required field | observed |
| 4 | Returns a different type from the declared workflow result | observed |
| 5 | Uses a name that was never bound | observed |
| 6 | Continues a loop with state of the wrong type | observed |
| 7 | Writes a loop with no bound | observed |
| 8 | Writes a bounded loop with no exhaustion outcome | observed (compiles in ORC today) |
| 9 | Calls a command missing from the command manifest | observed |
| 10 | Declares a command without a result type | observed |
| 11 | Passes a record where a command argument expects a scalar | observed (compiles in ORC today) |
| 12 | Provider reply lacks a declared field or has one of the wrong type | observed |
| 13 | A step writes its result somewhere other than its declared result path | observed |
| 14 | Omits a case when matching on a variant | derived |
| 15 | Reads a case's payload without matching on the case | derived |
| 16 | Misspells a case or constructor name | derived |
| 17 | References a provider or prompt missing from its manifest | derived |
| 18 | Command output does not match its declared result type | derived |
| 19 | Two branches of a conditional return different types | derived |
| 20 | Calls a sub-procedure with the wrong number or type of arguments | derived |
| 21 | Uses an optional value as if always present | derived |
| 22 | A prompt names an input that is not passed to it | derived |
| 23 | Reaches the launch step on a decision that is not APPROVE (well-typed logic error; neither side is expected to catch it) | control |

Excluded by rule: restrictions that exist in only one notation and are not a
mistake in the other (an effect given directly to `continue`, file name
equal to module name, an unbalanced parenthesis).

**Keeping the control honest.**

1. Both clean versions pass their checker with zero diagnostics and, with the
   scripted providers, produce the same dispatch log and final value.
2. A reviewer other than the control's author strengthens `pipeline.py` with
   one brief: make the type checkers catch more. This happens before any
   seeded variant is checked on either side.
3. Then `FREEZE.sha256` records the hashes of both clean versions, of
   `defects.json` and of every seed patch (`seeds/<n>.orc.patch`,
   `seeds/<n>.py.patch`, each at most five changed lines, each pair reviewed
   as the same mistake).
4. `run_checks.py` applies each patch to a copy, runs the checks above and a
   scripted run, and writes `results.csv`.
5. An idiom found afterwards that would let the control catch one more defect
   is listed in a separate column; it does not change the primary result.

**Verdict rule.** Let O be the defects with ORC outcome `static` or
`static-elsewhere`, and P the same for the typed Python primary check.
*Refuted* (parity) if P contains O. *Supported* otherwise; the report lists
O minus P and P minus O, split by origin, and repeats the comparison with the
secondary check and with the afterwards column. Defects from the consumer's
friction log are added later as a second, separately labelled list.

**Inputs.** `steps.py` from item 2; the sources named above.
**Outputs.** `experiments/thread_m/seeded_defects/` (`pipeline.orc`, three
manifests, `pipeline.py`, `defects.json`, `seeds/`, `run_checks.py`,
`results.csv`, `FREEZE.sha256`); report `docs/reports/thread-m/seeded-defects.md`.

**Acceptance check.** `FREEZE.sha256` is committed before `results.csv`
exists (two commits); `sha256sum -c FREEZE.sha256` passes; `results.csv` has
23 rows with both outcomes and a verbatim diagnostic or dispatch count each;
rerunning `run_checks.py` reproduces it byte for byte;
`tests/test_thread_m.py::test_seed_patches_apply` passes.

**Effort:** 4–5 days. **Main risk:** the result depends on how well the
control is written and on a list of which ten rows are the planner's own;
the split by origin and the afterwards column are there so a reader can
discount either.

## Item 4: Pool reanalysis (descriptive only)

**Pools and where their data lives** (Step 0 snapshot of each):

| Pool | Per-candidate table | Contents |
| --- | --- | --- |
| E-B2 | `eb2/batch/pool/records/results.json`, key `clones` | 18 clones on one task: 12 candidate patches, the stub and upstream anchors three times each; two judges; `hidden` on all |
| E-B3 | `eb3/primary-readout.json` (`clones.<id>.ratings`; it records the sha256 of the pool's `results.json`, `3c29fa7f…`) joined by clone id to `eb3/hidden-secondary-readout.json` (`clones.<id>.fraction`) | 13 clones on one task: 7 patch versions, 6 anchor clones; two judges |
| Phase 1 | `/home/ollie/ss-pools/phase1/<task>/records/results.json` for `resume-projection-integrity` (18 clones) and `pure-result-replay` (17) | 27 candidates and 8 anchor clones on two tasks; two judges; `hidden` on all |
| E-A | `ea/pool-records/results.json` | 54 clones, two judges, **no executed tests** (`hidden` is null on every clone). Used for the retest table only |

The harness's own join can produce the table: `summarize.py` already wrote
it. Each `clones.<id>` entry carries the judge's criterion ratings as the
judge copied the clone id back, and the hidden fraction for that clone. The
reanalysis reads those stored files and does not rerun `summarize.py` (the
work roots are gone, and a rerun would execute the hidden tests again). A
judge's score for a clone is the sum of its integer criterion ratings, as the
harness totals them. For E-B3 the two files are joined on the clone id and on
nothing else.

**Method.** Write `reanalyze.py` (standard library plus `scipy.stats`, under
200 lines):

1. *Join check first.* Reproduce from the loaded tables: E-B2 hidden means
   0.487 for both `design_review_execute` and `direct_task`; E-B3 hidden
   means 0.933 (direct) and 0.954 (`reviewed_change`); and each report's
   published anchor totals. A mismatch stops the script.
2. *Rank agreement.* Per pool and judge, over candidate patches only:
   Kendall tau-b and Spearman rho between judge score and hidden fraction,
   with n, the number of distinct hidden values, and the counts of
   concordant, discordant and tied pairs; whether the judge's top-scored
   patch is among the top hidden patches. The same for the two-judge mean.
3. *Retest spread.* Group clones with byte-identical `patches/<id>.diff`
   (sha256), which captures anchors repeated across batches and first and
   final patches that are equal. Per judge: each group's scores, range and
   the pooled within-group standard deviation. For E-B3, whose patches are
   not in the snapshot, group anchors by label; if
   `/var/tmp/eb3-science-20261016.tar.zst` yields `pool/records/patches`,
   use the bytes instead and say so. Cite, do not recompute, the rescoring of
   unchanged code in the LS10 and LS11 reports.
4. *Selectors.* Per pool, over final candidate patches: mean hidden fraction
   (the expectation of a random pick), maximum (oracle pick), and the hidden
   fraction of each judge's pick and of the two-judge mean's pick, ties
   averaged; each as a gain over random. The same within any arm that has two
   or more runs.

**Outputs.** `experiments/thread_m/pool_reanalysis/reanalyze.py`,
`per_candidate.csv`, `summary.json`; report `docs/reports/thread-m/pool-reanalysis.md`.

**The report must say that these pools cannot show:** an effect size for any
workflow; that selection would gain anything in use (the oracle here picks on
the scoring tests, so it is the any-of-N upper bound, and the pools mix arms
and models instead of being N draws from one generator); whether a judge is
valid in general (four tasks, all features of this repository, 7 to 14
candidates per pool, heavy ties, two judges, hidden tests that pin internal
names); statistical significance of any coefficient; or anything about the
Phase 5 task family. Historical scores are reported unchanged.

**Acceptance check.** The join check passes; `per_candidate.csv` has one row
per clone of the four pools with pool, clone id, arm, label, each judge's
score, hidden fraction and patch hash; the report contains the paragraph
above and no claim outside it; `tests/test_thread_m.py::test_reanalysis_join`
passes on a four-clone fixture whose two judges list clones in different
orders.

**Effort:** 1.5–2 days. **Main risk:** over-reading small numbers; the
external roots can disappear (Step 0 removes that risk).

## Item 5: Task pool for the Phase 5 benchmark

**Requirement** (roadmap, and the
[corrected protocol](../reports/2026-11-11-roadmap-review/experiment-design.md#corrected-minimal-protocol)):
natural fix commits with their own tests, from repositories other than this
one, at most five per repository and at least ten repositories, dated after
the bound models' training cutoffs where available; each task with a visible
failing check and a disjoint hidden scoring set; base failing and the
reference fix passing the hidden set in repeated runs; splits frozen by hash
before any call. No deliberately injected flaw is admitted.

**Decisions.**

- *Cutoff.* The default model is `claude-haiku-5-5`. Its cutoff is taken from
  the vendor's published model table; the engineer fetches the two pages
  named above again, stores them under `experiments/task_pool/cutoffs/` with
  URL, date and sha256, and reads the "Training data cutoff" row. On
  2026-11-11 it read June 2026, so the **date floor is 2026-07-01**: author
  date and committer date of the fix on or after it. Each task also records
  whether it is on or after 2026-08-01, as a stricter subset. For any other
  model the owner binds, the same lookup is done on that vendor's page; a
  later cutoff filters tasks by date at criterion freeze, and a cutoff that
  cannot be established is stated in the Phase 5 criterion as a limit.
- *Scope.* Python repositories with a pytest suite and a permissive licence
  (MIT, Apache-2.0, BSD), not forks, not archived, not this project or the
  owner's other projects. One toolchain keeps the build cost bounded.
- *Sizes.* Development 20, evaluation A 40, reserve 20 (the one permitted
  redraw of the development split), evaluation B 20, validation 30, sealed
  60. The **smallest useful pool is 60 tasks from 12 repositories**
  (development plus evaluation A, the roadmap's small tranche, with no
  redraw). 80 adds the reserve; 100 allows the full tranche; 190 also
  freezes the two sets Phase 6's generic search would need.
- *Seed.* The string `thread-m-pool-2026-11-11` orders everything below as
  `sha256(seed + "|" + id)`.

**Method.**

1. *List repositories* (12 unauthenticated search requests, saved raw under
   `experiments/task_pool/search/`):
   `https://api.github.com/search/repositories?q=language:Python+pushed:%3E2026-07-01+stars:%3E500+license:<mit|apache-2.0|bsd-3-clause|bsd-2-clause>+fork:false+archived:false&sort=stars&order=desc&per_page=100&page=<1..3>`,
   seven seconds apart. Order the repositories by the seed. They are screened
   in that order, never chosen by hand.
2. *Mine commits* (`mine.py`, local git only). Mirror each repository with
   `git clone --bare --filter=blob:none <url> /home/ollie/tm-pool/mirrors/<owner>__<repo>.git`.
   On the default branch's first-parent history since the floor, keep a
   commit when it changes at least one test `.py` file (path matches
   `(^|/)(tests?|testing)/|(^|/)test_[^/]*\.py$|_test\.py$`) and at least
   one other `.py` file; changes at most 5 non-test files and 200 non-test
   lines; changes no dependency manifest or lock file; has a subject or body
   matching `\b(fix(es|ed)?|bug|regression|crash|incorrect|wrong)\b`; is not
   a revert; and has no commit with the same `git patch-id --stable` before
   the floor. Order a repository's candidates by the seed and try them until
   5 are admitted or 15 were tried.
3. *Build the environment once per repository* (network): `uv venv` with the
   newest of Python 3.13, 3.12, 3.11 that the project's `requires-python`
   allows, then `uv pip install --exclude-newer <fix committer date> -e .`
   with the first of the extras `test`, `tests`, `testing`, `dev` (or a
   `requirements-dev.txt`, `requirements/test*.txt`) under which
   `pytest --collect-only` succeeds on the touched test files. Fifteen
   minutes per repository; a repository that does not build is dropped with
   its reason. Save `uv pip freeze` as the task's lock.
4. *Oracle check* (`oracle.py`; every test run is inside
   `bwrap --unshare-net --ro-bind / / --tmpfs /tmp --tmpfs /home/ollie --bind <work dir> <work dir> --ro-bind <venv and interpreter> ... --dev /dev --proc /proc`,
   ten-minute limit, JUnit output). Base is the fix's first parent. Run the
   touched test files, taken from the fix, five times on the base sources and
   five times on the fixed sources. *Fail-to-pass:* a test that fails or
   errors in all five base runs and passes in all five fixed runs.
   *Pass-to-pass:* passes in all ten. A test that is neither is left out of
   the hidden set; if it failed at least once on base and passed at least
   once on the fix, the task is dropped as unstable.
5. *Split, mechanically.* Group fail-to-pass tests by test function
   (parameters of one function stay together). A task needs at least two
   groups. The group first in seed order is the **visible check**; the
   **hidden set** is every other fail-to-pass group plus the pass-to-pass
   tests. The visible workspace is the base tree plus the fix's versions of
   the touched test files with every hidden fail-to-pass function deleted by
   `ast` line range; a support file the fix adds is included only if the
   visible check cannot be collected without it. Checks, five runs each: the
   visible check fails on the visible workspace and passes once the fix's
   non-test changes are applied; no hidden fail-to-pass test is collected
   from the visible workspace; no hidden function name occurs anywhere in it
   (`grep -rF`). If the pool falls short, one relaxation is allowed and
   labelled per task: parameter-level groups where each parameter id is the
   stem of a data file the fix adds.
6. *Task text.* The linked issue's title and body if the commit says
   `Fixes #N`, else the pull request's, else the commit message (REST, one
   request per task; `gh auth login` by the owner lifts the 60-per-hour
   limit). Remove any fenced block containing a line the fix adds to a
   non-test file; drop the task if such a line (20 characters or longer)
   remains or the text is under 80 characters. Record issue and pull request
   creation dates when fetched; a task whose issue predates the floor is kept
   and flagged.
7. *Evaluator check* (the separate check on known controls the binding rules
   require). For every task: the reference fix is accepted and the base is
   rejected by the hidden set, five of five (step 4). Over-fit screen for
   every task: a hidden fail-to-pass test that uses a name the fix newly
   defines with a leading underscore drops the task; a newly defined public
   name it uses must appear in the task text. Then, on ten development
   tasks from ten repositories, an engineer other than the pipeline's author
   writes a second correct fix from the task text and the visible check
   alone, structurally different from the reference; the hidden set must
   accept all ten. A rejection is examined: an over-fitted test drops the
   task and tightens the screen; a wrong alternative is corrected. The same
   check on naturally produced submissions stays in Phase 5's calibration
   tranche, which spends calls and is not part of this plan.
8. *Freeze.* Assign splits by `split.py`: order repositories and each
   repository's tasks by the seed. If at least 190 tasks exist, the last
   repositories in that order whose tasks total at least 90 are held out
   whole and dealt round-robin into validation 30 and sealed 60; otherwise
   no Phase 6 set is frozen. Deal the remaining tasks round-robin across
   repositories into one sequence: the first 20 are development, the next 40
   evaluation A, then reserve 20, evaluation B 20, and spares. Write
   `pool.jsonl` (one line per task: id, repository, licence, base and fix
   commits, dates, visible and hidden test ids, hashes of the visible files,
   the hidden files and the lock, changed lines and files, oracle log hash)
   and `splits.json`; put both hashes in `FREEZE.sha256`, in the ledger and in
   the report, and commit them before any provider call is planned.

Task files (visible and hidden test files, locks, logs) live under
`/home/ollie/tm-pool/tasks/<task id>/`; the repository stores pointers and
hashes only, so third-party code is not copied into it and the files can be
rebuilt from the mirrors.

**Stop rule and time box.** After the first 15 repositories are screened,
project the pool as (admitted tasks per screened repository) × (repositories
screenable in the remaining time, at most 120 in total). If the projection is
under 60, stop. Otherwise stop at 190 admitted tasks, 120 screened
repositories or 15 working days, whichever comes first. Final reading:

| Frozen pool | Consequence |
| --- | --- |
| Fewer than 60 tasks or fewer than 12 repositories | Phase 5 does not run; H-Q is recorded as not tested |
| 60–79 | Small tranche possible, no redraw |
| 80–99 | Small tranche with a redraw, or full tranche without one (owner's choice at decision 6) |
| 100–189 | Full tranche with a redraw; Phase 6 generic search cannot open on this pool |
| 190 or more | As above, with validation and sealed sets frozen |

**How likely the pool is to reach size.** The repository supply is not the
limit (about 5,900 candidates). The limits are the four-month window since
the cutoff, the per-commit yield, and the build effort. In the planning probe
most small libraries had zero to two eligible commits and only large, busy
projects had dozens, so the pool will come from perhaps one repository in
three or four, and the requirement of two failing test functions will remove
many single-test fixes. The planner's estimate, not a measurement: 60 tasks
about 80% likely, 80 to 100 about 65%, 190 about 35%. Each month adds about a
quarter to the window. A second risk cannot be measured without calls: small
fixes with a failing test in view may be too easy for the direct arm, which
the calibration tranche's 25–75% gate would then reject. To leave room for
that, `pool.jsonl` records size proxies per task and the round-robin deal
spreads them across splits.

**Outputs.** `experiments/task_pool/` (`mine.py`, `oracle.py`, `split.py`,
`search/`, `cutoffs/`, `screening.csv` with one row per screened repository
and per tried commit and its drop reason, `pool.jsonl`, `splits.json`,
`FREEZE.sha256`); report `docs/reports/thread-m/task-pool.md` (counts at each
filter, pool size, repositories, the table above applied, limits: Python
only, popular repositories, fixes with at least two failing test functions,
difficulty unknown).

**Acceptance check.** `sha256sum -c experiments/task_pool/FREEZE.sha256`
passes; no repository has more than five tasks; every task's dates are on or
after the floor; `oracle.py --recheck <three task ids drawn by the seed>`
reproduces their recorded test outcomes; the ten alternative fixes are
accepted; no task id appears in two splits; `tests/test_thread_m.py::test_split_is_deterministic`
and `::test_visible_file_has_no_hidden_function` pass on fixtures. If the
stop fired, the report states the count reached and the roadmap consequence.

**Effort:** 10–15 days (scripts 4, screening 5–8 mostly machine time,
evaluator check 1.5, report 1). **Main risk:** the pool does not reach 60, or
reaches it and is too easy; the first is known by day 4, the second only
after a paid calibration.

## What this plan makes harder

- Items 2 and 3 use one small pipeline shape. A parity or advantage found on
  it does not extend to parallel maps, child workflows or long pipelines.
- The LangGraph side pins `langgraph` 1.2.16 through an untracked
  environment and hooks a library internal; a later version may behave
  differently and the matrix would need rerunning.
- The pool is Python-only, drawn from popular repositories and from fixes
  with two or more failing test functions. A Phase 5 result on it holds for
  that population.
- Pointers-only storage keeps third-party code out of the repository but
  makes the pool depend on `/home/ollie/tm-pool/` and on upstream history
  staying fetchable.
- The comparison harness builds candidates from this repository's checkout
  and runs hidden tests with one interpreter. Pointing it at an external
  mirror and a per-task environment is Phase 5 work that this plan does not
  do.

## Not verified while planning

- Whether the nine kill-test modules all pass at the current commit, and how
  long they take under the present load (collected only).
- Which checkpointer call marks a node's result as durable in `langgraph`
  1.2.16; only a two-node kill and resume was tried.
- Whether `/var/tmp/eb3-science-20261016.tar.zst` contains the E-B3 pool's
  patch files (a listing returned nothing in 90 seconds).
- The yield of the oracle check on real fix commits; the probe counted
  commits before any test ran, in six repositories chosen by hand. Two of
  them showed a single commit since the floor, which may be an artefact of
  the shallow clone used.
- The training cutoff of `gpt-5.6-terra`.
- Whether `experiments/compare` can take an external repository as its
  candidate source without change.
- Issue and pull request dates, which need the REST API per task.

## Ledger

| Date | Entry |
| --- | --- |
| 2026-11-11 | Plan written. Provider spend limit for Thread M: zero calls. Any later spend needs an owner-approved budget and a ledger row in the plan that spends it. |
| 2026-11-11 | Planner's decisions, open to amendment by the owner before the item they govern starts: pipeline shape (review, revision loop, launch); kill points K0–K4 and their mapping to W0–W9; the four-part "same result" rule; glue of at most 50 lines counts as parity; H-G2 primary check is the type checker alone, either of `mypy --strict` and strict `pyright`; the 23-row defect list; pool scope Python with permissive licences; date floor 2026-07-01; function-level visible and hidden split; seed `thread-m-pool-2026-11-11`; split sizes and order; smallest useful pool 60 tasks from 12 repositories; reports under `docs/reports/thread-m/`. |
| 2026-11-11 | Step 0 done (commit `3776cf17`). Environment: DAQ interpreter prints `1.2.16 3.1.2 2.4.0 2.10.3` as expected, so `/home/ollie/tm-env` was not built and `TMPY=experiments/adversarial_daq/.venv/bin/python`; that interpreter is a symlink to `/home/ollie/miniconda3/bin/python`, so `env-freeze.txt` (317 lines) is the miniconda base freeze plus the venv. `pyright` 1.1.403 (prints a v1.1.414 update notice), `uv` 0.8.15, `bubblewrap` 0.9.0; `df -h / /home` 37 GB and 62 GB free before and after. Snapshot: 259 files, 11.6 MB of sources (14 MB on disk), under `experiments/thread_m/inputs/` at their paths relative to `/home/ollie` (the DAQ memo is at `Documents/agent-orchestration/experiments/adversarial_daq/.orchestrate/...`); 107 patch diffs (E-B2 18, resume-projection-integrity 18, pure-result-replay 17, E-A 54), 135 memos (ss-work2 67, ss-work-incident1 9, ss3-work 8, compare-evidence 50, DAQ 1) kept in the repository since the directory is under 20 MB. Every first-16 hash in the Step 0 table matches; hashes recorded at copy: `ss-evidence-incident1/log.jsonl` `debf710393cfdd9a`, `ss3-evidence/log.jsonl` `bdec081db2607988`. `sha256sum -c SHA256SUMS` passes. No source missing. 47 memos sit under `state/` or `.orchestrate/`, which the root `.gitignore` excludes; they were committed with `git add -f`, so later edits there show in `git status` but new files there need `-f`. Credential scan: no keys or tokens; three test-fixture strings in resume-projection-integrity patches (`hunter2`, `token-123`, `do-not-leak-this`) kept. Also created `experiments/thread_m/no_provider/{claude,codex}` (Global constraints); `no-provider.log` absent. Provider calls: zero. |
