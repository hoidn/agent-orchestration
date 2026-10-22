# Comparison harness: maintained `.orc` workflows against single agent calls

Design and decisions: [`docs/design/orc_effectiveness_comparison_harness.md`](../../docs/design/orc_effectiveness_comparison_harness.md).
The harness runs a maintained workflow unchanged, records every agent call through a transparent
shim, pools the resulting patches blind, selects `score.orc` or an explicit reference/absolute rubric,
and summarizes against a criterion frozen before scoring.

Structural-search callers additionally enforce their
[external qualification contract](../../docs/design/orc_structural_search_driver.md#external-qualification-receipt)
before quality launch/resume, pooling, judging and readout. Generic comparison
launchers retain their own API and do not acquire this structural gate. This does
not waive the owner rule: a new quality experiment needs separately budgeted
family/measure precalibration and owner-approved provider spend. Historical
criteria and captured recipes confer no fresh permission.

| File | Role |
| --- | --- |
| `prepare.py` | command line: `run`, `collect`, `scan` (hits, then a verdict), `pool`, `calibrate`, `verify-pool` |
| `repos.py`, `scan.py`, `pool.py` | candidate builds and patches; the contamination scan; the blind pool and its check |
| `shim/claude`, `shim/codex` | first on `PATH` during a run and a judge's scoring; run the real CLI under bubblewrap (private `/tmp`, `/dev/shm` and process list; empty `/var/tmp`) with the bookkeeping variables stripped; record `calls/<n>/` |
| `control/direct_task.orc` | the control: the library `direct_task` plus `:timeout-sec 14400`; module `control/direct_task` |
| `control/review_once.orc` | one review of a given patch (difficulty calibration): `reviewed_change`'s `review-prompt`, `Review` and `ReviewReport`, copied, and its reviewer's binding; module `control/review_once` |
| `control/direct_task.providers.json`, `control/review_once.providers.json`, `providers/design_review_execute.json` | bindings for the control, the review-only arm and the E-B treatment |
| `score.orc`, `score.providers.json`, `providers/score_codex.json` | blind side-by-side ratings; a Claude and an OpenAI judge binding |
| `summarize.py` | `results.json` and `results.md`: runs, measures, verdict, agreement, anchors, scan verdicts |
| `criterion.template.json` | the fields to freeze, and hash, before scoring |

## Task package

`experiments/compare/tasks/<package>/` holds `task.txt` (what every arm receives), `intent.txt`
(what judges and reviewers receive), `base_commit`, `seed/` (files committed onto the base in every
candidate and clone, so they never appear in a patch), `anchors/<name>.diff` (all declared controls, built
against the seeded commit; the criterion selects the control roles), and optionally `hidden_tests.txt` (node ids, one per line, or a file
path for all its tests) with `hidden/` (test files copied over a copy of each clone, without `.git`,
before they run). Without both, hidden acceptance is skipped.

## Layout

The work root `W`, the pool `P` and the frozen runtime `RT` must not lie under the main checkout's
path prefix (for `/home/ollie/Documents/agent-orchestration`, that includes every sibling such as
`...-compare` or `...-repl`): those checkouts hold solutions, and the scan counts any mention of the
prefix as a hit. `prepare.py` refuses such paths. The frozen runtime must also lie outside the work
root `W`, where agents work, and `run` refuses one inside it. `W` and `P` must not lie under `/tmp`,
`/dev/shm` or `/var/tmp`, since the shims' sandbox mounts private or empty ones there and an agent would lose its working
directory; `run` and `pool` refuse them. `run` and `pool` also refuse a runtime with uncommitted
changes to tracked files, and record its `HEAD` as `runtime_commit` in `record.json` and
`mapping.json`. Current paths are supplied through the recipe placeholders; historical
[recorded runtime/work roots](../../docs/reports/documentation-history/experiments-compare-README-history.md#recorded-runtime-and-work-roots) are evidence.
`run` refuses a task base whose candidates do not ignore `.orchestrate/`, where run state lives.

What the sandbox isolates:
- each agent and judge CLI runs under `bwrap --dev-bind / / --bind <tree>/tmp /tmp --tmpfs /dev/shm --tmpfs /var/tmp
  --unshare-pid --proc /proc --die-with-parent`;
- hard-coded `/tmp` paths land in the tree's `tmp/` (a judge's own `tmp/` for judges), so they are
  private, and so are `/tmp` tmux sockets;
- `/dev/shm` is private, and the process list shows only the agent's own processes;
- `/var/tmp` is empty, because other sessions keep repository worktrees there.
- with `COMPARE_HIDE` set (colon-separated absolute directories; the structural search driver sets it for its
  mutator), each of them that exists is masked by an empty tmpfs after `--dev-bind / /`, and then
  `--bind <tree> <tree>` binds the tree back, so masking a parent of the tree leaves the tree reachable. Without
  the variable the `bwrap` command line is unchanged. The agent never sees it, like the other `COMPARE_*`
  variables.
- when the controller supplies `COMPARE_MAX_CALLS`, the shim atomically allocates
  its recorded call directory, then refuses an index beyond that nonnegative cap
  before invoking the real provider (exit 75). Zero and concurrent/resumed attempts
  use the same rule. The refusal retains provider/argv/stdout/stderr evidence and
  counts in ledger settlement; it is not successful usage. The cap is stripped
  from agent/tool environments. Without it, generic shim callers retain their
  existing behavior.
- `/tmp` is private per run, not per agent: `best_of_n`'s implementers share the tree's `tmp/`;
- the PID namespace ends with the call, so any server or tmux session an agent starts dies when
  its call ends.

What it does not isolate:
- the rest of the filesystem (except the `COMPARE_HIDE` directories), home and the network stay shared;
- other sessions' transcripts (`~/.claude/projects`, `~/.codex/sessions`) stay readable;
- the scan only detects reads there, it does not prevent them.

| Path | Holds |
| --- | --- |
| `W/records/<arm>/run-<k>/` (`R`) | `record.json`, `inputs.json`, `command.sh`, `resume.sh`, `calls/<n>/`, `collected/`, `run.log` |
| `<cwd>/.orchestrate/runs/<run_id>/` | the run's orchestrator state (memo, `run.json`, attempt files), in the working directory; `record.json` names it as `state_root`. For `best_of_n` it is `<tree>/.orchestrate/best-of-n-runs/<run_id>/`, linked from every `cand-k/.orchestrate/` |
| `W/agents/<16 hex>/` | the agents' tree: `cand-1` ... `cand-N`, `tmp/` (TMPDIR, and `/tmp` inside the sandbox) and `.model-guard/{claude,codex}` (first on the agent's `PATH`); `record.json` names the tree |
| `P/clones/<id>/` | applied-patch clones, what judges read |
| `P/judges/<16 hex>/` | one judge's working directory, with its `state/` and `tmp/` (its `/tmp` inside the sandbox) |
| `P/records/judges/<judge>/` | the judge's shim call records (`calls/<n>/`) and `scan.json` |
| `P/records/` | `mapping.json`, `patches/`, `score-inputs-<judge>.json`, `score-<judge>.sh`, `resume-<judge>.sh`, `results.json`, `results.md` |

`P/clones` is mode 0311 (traversable, not listable: judges get absolute paths); `chmod u+r` it
before deleting the pool. `W/agents`, `P` and `P/judges` must stay listable. The runtime opens every
ancestor of a workspace or state directory one component at a time with `O_RDONLY`, and a 0311
parent fails the run with `cannot open directory root component`. So an agent can list sibling
trees and an ancestor's records. The scan counts any mention of another tree's name as a hit, and
records live outside every tree. The orchestrator still writes `.orchestrate/` (workspace lock,
guard and a build cache) into the working directory; this repository's `.gitignore` ignores it.

## Recipe

Placeholders: `MAIN` the main checkout, `C` the recorded commit, `RT` the frozen runtime checkout,
`W` the work root, `T` the task package inside `RT`, `R` a records directory, `P` a pool, `SOL`
the solution commit.

```bash
git -C $MAIN worktree add --detach $RT $C        # 0. frozen runtime outside MAIN's prefix
PY=/home/ollie/miniconda3/bin/python H=$RT/experiments/compare
```

Model policy (owner, 2026-10-19): all experiment workflows use mid/low-tier models at or below
Sonnet/Terra, including judges, reviewers, coders and nested agents. The current measurement admits
exactly `claude-sonnet-5-5` and `gpt-5.6-terra`; Fable remains forbidden. Frozen high-model arms and
criteria preserve historical evidence and refuse new guarded launches until separately amended.
Changing a model does not authorize spend or establish calibration for a new model pair.

Agents share `$HOME`, so the harness guards instrumented CLI routes and checks recorded usage:

- **Guard.** The shims install the same `shim/model-guard` under both `<tree>/.model-guard/claude`
  and `codex`, first on the sandboxed agent's `PATH`, for top-level and nested CLI calls. Parallel
  installation leaves identical copies alone, creates missing copies by atomic hard link and
  restores edited copies by rename. Arguments, stdin, streams and status reach the real CLI.
  Claude defaults to Sonnet; the primary model is one exact ID. Explicit and fallback model arguments (separate or `=` forms,
  including every comma-separated fallback) must use the exact Sonnet ID. Optional
  `COMPARE_CLAUDE_MODELS`, forwarded as `ORC_ALLOWED_CLAUDE_MODELS`, can narrow this owner cap but
  cannot raise it. The forced Claude subagent model must also be Sonnet.
- **Codex.** The same guard defaults to Terra and checks long and short model arguments. It
  rejects review subcommands (which can select a separate `review_model`), profile, provider,
  local-model and feature-enabling overrides, and admits only scalar
  `model_reasoning_effort` configuration overrides used by the provider binding. It always adds
  `--disable multi_agent --disable multi_agent_v2 --disable multi_agent_v2_dynamic_tools`
  and `-c agents.enabled=false` to request that native agents be disabled; their dispatch does
  not pass through `PATH`. For `exec` (including alias `e`), it inserts these settings after
  the subcommand: Codex 0.163.0's subcommand `--config` overrides top-level config rather than
  merging it. Offline parser and inert public-dispatch checks verify this placement;
  they do not establish native tool suppression. Effective live prevention remains unqualified
  ([AT incident](../../docs/reports/2026-10-20-orc-structural-search-measurement-at.md)).
  False feature flags, transmitted configuration and an offline prompt without collaboration
  instructions do not prove that the actual executed provider cannot launch native tools.
  Further live calibration requires that proof; observed child sessions count toward its
  budget and consumption. The `app-server`
  protocol (whose turn messages can choose another model), cloud/remote/dispatch,
  queue/resume/fork session dispatch and `--approve-for-me` routes also refuse; these are unused
  by the provider bindings and may select independent server or reviewer models. Orchestrator
  resume remains supported because it invokes a fresh guarded `codex exec` call.
- **Claude native agents.** The shims and guard set
  `CLAUDE_CODE_SUBAGENT_MODEL=claude-sonnet-5-5` and `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1`.
  Explicit settings injection and cloud/environment/desktop/ultrareview/remote-control dispatch
  are refused because they can start independently configured agents. The environment pins cover
  Agent-tool subagents, teammates and workflow agents under the CLI contract
  ([run every subagent on one model](https://code.claude.com/docs/en/sub-agents#run-every-subagent-on-one-model),
  Claude Code 2.1.257 or later). Offline tests verify the variables reach the CLI, rather than
  claiming a live verification of its internals.
- **Scan and limits.** Absolute real-CLI paths, a reset `PATH`, dropped environment pins, older
  CLIs and direct APIs bypass prevention. The scan reads actual Claude assistant `message.model`
  and Codex `turn_context.model` metadata in attributed sessions, including nested sessions.
  Fable or any other forbidden/unknown model produces a non-clearable policy hit. Printed model
  names do not count as usage. Direct API calls without a scoped session are invisible, and
  sessions started at literal sandbox `/tmp/...` paths rather than under `TMPDIR` are not
  attributed to the tree. These guards do not claim prevention beyond instrumented routes.

1. **Prepare** one run per invocation. It prints the command, writes it to `R/command.sh` and
   writes `R/resume.sh`.

   ```bash
   $PY $H/prepare.py run --task $T --arm best_of_n --root $W --runtime $RT [--candidates 4]
   $PY $H/prepare.py run --task $T --arm reviewed_change --root $W --runtime $RT
   $PY $H/prepare.py run --task $T --arm design_review_execute --root $W --runtime $RT \
     --set planner_model=claude-sonnet-5-5 --set reviewer_model=gpt-5.6-terra
   $PY $H/prepare.py run --task $T --arm direct_task --root $W --runtime $RT \
     --set model=gpt-5.6-terra --set effort=high
   $PY $H/prepare.py run --task $T --arm review_once --root $W --runtime $RT \
     --apply $W/records/direct_task/run-<k>/collected/final.diff
   ```

   `best_of_n`, `reviewed_change` and `design_review_execute` retain historical internal model
   choices; preparation alone does not make them launchable under the current cap. Use the
   direct/review controls above or an explicitly amended measurement workflow.

   | arm | inputs | working directory of the command |
   | --- | --- | --- |
   | `best_of_n` | `task`, `intent`, `repos` (absolute candidates) | the agents' tree |
   | `reviewed_change` | `task`, `intent`, `repo` (the tree's absolute `cand-1`) | the tree's `cand-1` |
   | `design_review_execute` | `task`, `planner_model`, `reviewer_model` | the tree's `cand-1` |
   | `direct_task` | `task`, `model`, `effort` | the tree's `cand-1` |
   | `review_once` | `repo` (the tree's absolute `cand-1`), `intent`, `account` (fixed: "No account was provided."), `replies` (fixed: "none") | the tree's `cand-1` |

   `review_once` takes `--apply` (no other arm does): a collected `final.diff` of the same task
   package, applied unstripped with `git apply` onto the seeded candidate and left uncommitted, so
   the reviewer sees it as the uncommitted changes. A patch that does not apply is refused and
   leaves no run behind. `record.json` names the patch and its SHA-256 under `applied`.

   The command runs `python -P`, so a candidate's own `orchestrator/` cannot shadow `PYTHONPATH=$RT`.
   It puts `$H/shim` first on `PATH` and sets `COMPARE_ROOT=R`, `COMPARE_TREE` (the tree),
   `COMPARE_BASE` (the seeded commit) and `TMPDIR` (the tree's `tmp/`). Except for `best_of_n` it
   passes no `--state-dir`, so the state goes to the runtime's default `<cwd>/.orchestrate/runs` and
   every provider prompt names a result path inside the agent's workspace. Result paths must resolve inside the provider's workspace; see the
   [recorded incident](../../docs/reports/documentation-history/experiments-compare-README-history.md#provider-result-path-incident).
   `best_of_n`'s workspace is the tree, but its implementers work in `cand-k` and resolve the
   tree-relative result path there; its state goes to `<tree>/.orchestrate/best-of-n-runs`, and each
   candidate's `.orchestrate/best-of-n-runs` links to it, so the path resolves from either location. An
   agent that deletes its candidate's `.orchestrate/` (for example `git clean -fdx`) loses the link.
   The task bases' `.gitignore` covers `.orchestrate/` and `artifacts/`. Before an agent starts,
   the shims strip `PYTHONPATH`, `OLDPWD`, the `COMPARE_*` variables and their own directory from
   `PATH`, because these name the frozen runtime, the launch directory and the records. For an
   ordinary attempt (`ORCHESTRATOR_WORKSPACE_ROOT` unset) they also strip its
   `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` and `ORCHESTRATOR_PROVIDER_ATTEMPT_SITE_KEY`: a task repository that
   is the orchestrator reads them in its own code and tests, so an agent running those tests overwrote
   its result file; the prompt's `- path:` line names that file relative to the agent's working
   directory. A launch-workspace attempt (`ORCHESTRATOR_WORKSPACE_ROOT` set) keeps all three, because
   its prompt tells the agent to resolve paths against the workspace root and write the result to the
   bundle path; there the overwrite risk remains and is disclosed, not prevented. They then
   run the agent's CLI in the bubblewrap sandbox described under Layout, which needs `bwrap` on
   `PATH`. After the call they take each candidate's patch through a copy of its index, so what
   the agent staged stays staged.

2. **Run** in tmux. A run that stops on provider infrastructure is resumed from the same working
   directory (`resume.sh` does this), never relaunched.

   ```bash
   tmux new-session -d -s <name> "bash $R/command.sh > $R/run.log 2>&1"
   tmux new-session -d -s <name> "bash $R/resume.sh <run_id> >> $R/run.log 2>&1"   # run_id: the name under record.json's state_root
   ```

3. **Collect** pairs the memo's provider starts with `R/calls/<n>/` one to one. It copies the
   patches the comparator needs into `R/collected/`: every candidate for `best_of_n`, first and
   final for `reviewed_change`, final otherwise. A failed run is recorded with its reason and no
   patch. For `review_once` it also records the review (`variant`, `findings`, the whole `review`),
   its `blockers` (see Measures) and `candidate_changed`: whether the final patch differs, byte for
   byte, from the applied one. The reviewer may change only ignored files (its report under
   `artifacts/`, its result under `.orchestrate/`), so `true` means it edited the candidate.

   ```bash
   $PY $H/prepare.py collect --run $R
   ```

4. **Scan, then adjudicate**. `scan` records every hit with its file, line,
   pattern and an excerpt, and decides nothing. It searches:
   - the shims' stdout and stderr;
   - the Claude CLI's session files for the tree;
   - the codex rollouts started in the tree.

   The patterns are:
   - the main checkout's prefix;
   - the frozen checkout;
   - the records root `W/records`;
   - the layout `records/<arm>/run-<k>` and a pool's record files, wherever they lie (a run's own
     state is in its working directory, so no records path is legitimate);
   - another run's tree name;
   - `github.com`, `gh ` and `git fetch`;
   - the solution hash;
   - `Fable model` or `Forbidden model`: actual Claude assistant `message.model` or Codex
     `turn_context.model` metadata outside the admitted IDs, including nested attributed sessions.
     Printed text naming a model does not count.

   A path also matches when it is written under `~`, `$HOME` or `${HOME}`.

   For a run with hits, the controller reads them and records a verdict. `pool` refuses a run
   with hits and no verdict, excludes contaminated runs (listed with the reason) and includes
   cleared ones. A `Fable model` or `Forbidden model` hit breaks the model policy and cannot be cleared:
   - `scan --verdict cleared` refuses it;
   - `pool` excludes the run, and `summarize` excludes the judge, with the number of Fable messages.

   ```bash
   $PY $H/prepare.py scan --run $R --hash $SOL
   $PY $H/prepare.py scan --run $R --verdict contaminated --reason "<what the agent read>"
   $PY $H/prepare.py scan --run $R --verdict cleared --reason "<why the hits are benign>"
   ```

5. **Freeze the criterion** from `criterion.template.json` (measure names below) before pooling.
   Its SHA-256 becomes every scoring run's `criterion_sha256`.

6. **Pool** every run of one experiment at once. Batches follow D4:
   - one per `best_of_n` run, with one `direct_task` patch each;
   - two stage batches for `reviewed_change`;
   - otherwise one batch of all final patches.

   Both anchors join every batch. `--judge MODEL` uses `score.providers.json`;
   `--judge MODEL=FILE` uses another binding (`providers/score_codex.json` for an OpenAI judge,
   because a judge's directory is not a git repository). The pool prints one command per judge
   and writes it to `P/records/score-<judge>.sh`. Each judge has its own working directory and
   `--state-dir` under `P/judges/`.

   ```bash
   $PY $H/prepare.py pool --task $T --criterion <criterion.json> --out $P \
     --judge claude-sonnet-5-5 --judge gpt-5.6-terra=$H/providers/score_codex.json $W/records/best_of_n/run-* ...
   ```

7. **Score** one judge after another, behind the shims, which record the judge's calls in
   `P/records/judges/<judge>/`. After each judge, `verify-pool` restores any clone the judge
   changed, including one holding an ignored file such as `artifacts/x.md` that no patch shows, and
   exits non-zero if it had to. A judge stopped by a provider failure is resumed with
   `P/records/resume-<judge>.sh <run_id>` (the same `--state-dir`), never re-run. Then scan the
   judge and adjudicate its hits, as for a run. The scan searches the judge's calls, sessions and
   rollouts for this pool's records, the run records root, the records layout, another judge's
   directory, the frozen runtime and the main checkout. Judge scans recorded before roots sharing a
   name were all matched (the same-name roots fix) may under-report hits for a pool whose runs span
   several work roots; rescan those judges.

   ```bash
   bash $P/records/score-claude-sonnet-5-5.sh && $PY $H/prepare.py verify-pool --pool $P
   bash $P/records/resume-claude-sonnet-5-5.sh <run_id>      # only after a stop; run_id under P/judges/<dir>/state
   $PY $H/prepare.py scan --pool $P --judge claude-sonnet-5-5 --hash $SOL
   $PY $H/prepare.py scan --pool $P --judge claude-sonnet-5-5 --verdict cleared --reason "<why>"
   bash $P/records/score-gpt-5.6-terra.sh && $PY $H/prepare.py verify-pool --pool $P
   $PY $H/prepare.py scan --pool $P --judge gpt-5.6-terra --hash $SOL
   ```

8. **Summarize.** It refuses in these cases:
   - a criterion whose `judges` differ from the pool's;
   - a judge not scanned, scanned before its last call, or with hits and no verdict (a judge found
     contaminated is left out and listed);
   - a listed judge without exactly one completed scoring run;
   - a scoring run whose provider starts do not pair one to one with the judge's shim call records
     (the shims were not first on `PATH`);
   - a scoring run bound to another criterion hash;
   - a batch whose ratings do not line up with its clones.

   It writes `P/records/results.json` and `P/records/results.md`. With hidden acceptance,
   `results.json` gives every clone its pass fraction (`clones.<id>.hidden`) and its failing node
   ids (`clones.<id>.hidden_failed`).

   ```bash
   $PY $H/summarize.py --pool $P --criterion <criterion.json>
   ```

## Candidate-root arms and generic-command arms

`prepare.run_arm(task, arm, W, RT, spec=ArmSpec(...))` runs an arm the `ARMS` table does not name;
`arm` then only names `W/records/<arm>/` and must not be an `ARMS` name. `ArmSpec` gives the `.orc`
source, entry, source root, providers file and typed input fields, and optionally a command boundaries
file (passed to `run` as `--command-boundaries-file`) and a state directory (`--state-dir` for `run`
and `resume.sh`). Its paths may name a candidate root outside the runtime; that root faces the
runtime's refusals (main checkout prefix, inside `W`), and its state directory must lie outside the
main checkout's prefix and outside `/tmp`, `/dev/shm` and `/var/tmp`. With `command` set the arm is a
generic command: `command.sh` runs it from `cand-1` behind the shims with the same `COMPARE_*` and
`TMPDIR` environment and `R/inputs.json` as its single argument, and writes no `resume.sh`.
`record.json` names the kind as `arm_kind`: `orc` or `generic-command`. `prepare.py scan --run R
--hash SOL --root NAME=PATH ...` (repeatable; `prepare.scan(..., roots=[(name, path)])` from Python)
counts mentions of further prefixes, such as a search's archive, lineage log and holdout roots, as
hits named NAME.

`collect` reads a generic-command run from the `terminal.json` its command writes in its one run
directory under `record.json`'s `state_root` (`cand-1/.orchestrate/runs/<run_id>/terminal.json`):
`{"outcome": "completed" | "failed", "value", "failure": {"code", "message"} | null, "started_at",
"finished_at", "calls", ...}`, times in epoch seconds. It records `outcome`, `failure`, `calls` (the shims'
`calls/<n>/` directories), `wall_clock_sec` (`finished_at - started_at`) and, for a completed run, the
last call's `patch-cand-1.diff` as `collected/final.diff`; `selected` and `variant` stay null. It
refuses a state root without exactly one run directory holding a `terminal.json` (finish the run
first; other directories there, such as an orchestrator run the agent started from `cand-1`, are
ignored), a terminal whose `calls` (the provider calls it launched) differs from the shims' call count,
and a completed run without that patch. The structural search's I3 parent
(`experiments/orc_structural_search/three_arm/python/direct.py`) writes such a terminal.

## Criterion-selected scoring

Without `rubric`, the harness uses the historical `score.orc` criteria (`root_cause`,
`scope`, `generality`, `layering`). A criterion can select the reference workflow:

```json
{"rubric": {"workflow": "score_ref.orc", "entry": "score_ref::score",
            "criteria": ["completeness", "correctness", "scope", "layering"],
            "reference": "upstream"}}
```

Each batch then includes a disclosed reference built from
`anchors/<task-name>-upstream.diff`, alongside the three declared blind controls
for `control-means-v1`, or every package anchor for historical criteria without
a rule identifier. The
reference has its own random clone ID, is bound separately from the blind clone
list, and receives no rating, run value or hidden-acceptance result. All repositories
count toward the ten-repository batch limit. `mapping.json` records the rubric and
reference IDs; summarization rejects a different criterion rubric or bound reference.
Historical mappings without `rubric`, and descriptive string-valued `rubric`
metadata in criteria or mappings, retain the historical criteria.

A reference-free rubric selects `score_absolute.orc`, entry
`score_absolute::score`, with the same four criteria and `"reference": null`.
Its four independent 0–2 components sum to 0–8. Completeness and correctness
concern implemented required behavior; correctness is zero when none is
implemented. Scope and layering are scored independently, with no global zero.

Generic comparison pools support these routes. Structural V1 quality operations retain
V1 qualification and reject a selected reference rubric; generic calibration does
not grant structural quality authority.

## Natural task-difficulty calibration

Use `purpose: "calibration"`, `calibration_kind: "task_difficulty"`, `anchors: []`,
a reference-free rubric, declared `arms` and `runs_per_arm`. Generate fresh
independent solutions with the same direct workflow and task inputs, varying only
the frozen model binding. Use `prepare.run_arm` with the direct-task `ArmSpec`
for each arm; custom final-patch arms enter the ordinary pool. Per-run
`COMPARE_CODEX_MODELS` binds the exact Luna or Terra model; unset policy retains
Terra only. Native delegation remains disabled.

Pool every declared natural output under blind clone IDs, then use the ordinary
scoring and summarization path. Summarization checks the complete run/clone/judge
denominator before applying the criterion's primary mean-gap comparison. Missing,
excluded or invalid evidence cannot produce PASS. There are no artificial
controls, references or hidden-test runs. The selected
[task-difficulty plan](../../docs/plans/2026-10-22-simple-evaluation-calibration-plan.md)
freezes the models, sample counts, threshold and authorized spend. Apparatus tests
alone establish no task-difficulty result or campaign permission.

## Evaluator control checks from recorded patches

Artificial-control checks assess the evaluator, not task difficulty. Freeze a criterion with `purpose: "calibration"`, the selected rubric, declared
judges and per-task `anchors` before scoring. The explicit control-check rule is:

```json
{"calibration": {"rule": "control-means-v1", "margin": 1, "error_rate": 0},
 "anchors": {"TASK": {"upstream": "TASK-upstream", "stub": "TASK-stub",
                       "mutant": "TASK-mutant"}}}
```

For each task and each declared judge, include every declared batch and require
`mean(upstream) - max(mean(stub), mean(mutant)) >= 1`. Every judge must pass;
missing, excluded or invalid observations fail. There is no partial-order or
spread acceptance gate; spreads remain descriptive. A one-point margin is a
prospective separation choice, not a measured reliability estimate.

A control-check criterion without `calibration.rule` retains the historical four-role
upstream/stub/partial/mutant algorithm: P1/P2/P3, error rate and spread limit
are unchanged. Unknown rules refuse. Extra anchor files in a package are not
pooled when the criterion declares only three controls. Hidden acceptance is
secondary: calibration summarization performs no new hidden runs, leaves
`hidden`/`hidden_failed` null and retains construction diagnostics only.

1. Obtain applicable filler patches for the same task/seeded base and freeze
   their recorded paths and hashes.
2. Run `prepare.py calibrate` with `--task`, `--criterion`, `--out`, `--runtime`,
   repeated `--judge` and `--filler`, and explicit `--batches`, `--per-batch`,
   `--min-per-batch`, `--filler-seed`. This prepares the pool without provider
   calls, rejects duplicates/insufficient fillers and deals without replacement.
   Each batch contains the declared controls and any selected unscored reference.
   Capacity is ten minus those repositories: three controls permit seven
   fillers without a reference, six with one. Reservations use the same count.
3. Obtain the separate provider-spend approval, then follow scoring, pool
   verification, scan/adjudication and summarization above. Judge test execution
   still produces a `judge ran tests` scan hit requiring adjudication.
4. Read `results.json`'s `calibration` using the selected rule and its full
   declared observations. Existing rating, component and clone-join integrity
   refusals still apply.
5. `summarize.py --calibration-over` names every supplied pool under their common
   frozen criterion. Every pool must pass independently; cross-pool spread is
   descriptive for `control-means-v1`, while the historical rule retains its
   spread gate.

The [simple evaluation plan](../../docs/plans/2026-10-22-simple-evaluation-plan.md)
selects offline implementation and verification only, tracked there. No new
provider call is approved or executed by this change. New rubric source needs
fresh frozen criterion/source identities and fresh responses before live
qualification. C1 V2 retains original component recomputation, source hashes
and clone-ID joins; V1 rejects explicit rule keys and keeps its no-rule behavior.
Historical AT remains completed FAIL_NOT_QUALIFIED under its frozen criterion, as the
[measurement plan](../../docs/plans/2026-10-19-orc-structural-search-measurement-plan.md)
records. B/B2/C budgets remain separate and unused recovery allowance does not
transfer. Apparatus tests establish no live calibration or quality result.

For judge metering, join the recorded judge calls under `P/records/judges/MODEL`
with tree `P/judges/<mapping.judges[MODEL].dir>` and `mapping.created_at` through
`metering.receipts`. Pass the physical call count and returned `receipt_usage`
to `pricing.cost` with the frozen criterion's `price_table`. This is an operator
readout join, not a second pricing or session-discovery API; incomplete coverage
stays unavailable and list-price equivalent is not billed spend.

## Measures

`summarize.py` scores a clone as the judges' mean total of the four criteria (0 to 8). A run's
value is its selected candidate (`best_of_n`) or its final patch. Measures per arm:

- every arm: `<arm>.runs`, `.mean`, `.calls_mean`, `.wall_clock_mean`, `.hidden_mean`;
- `best_of_n` and `reviewed_change`: `.paired_gain_mean`, `.paired_gain_runs_positive`,
  `.paired_gain_runs_negative`;
- `best_of_n`: the same three for `group_gain`;
- `reviewed_change` with hidden acceptance: the same three for `hidden_paired_gain`, the final patch's
  hidden fraction minus the first patch's;
- every arm except `direct_task`: `.minus_control` and `.hidden_minus_control`.

A criterion entry is `{"measure", "op", "value"}`, with `op` one of `>=`, `<=`, `>` or `<`.
Failed and excluded runs are listed and carry no value.

`review_once` is not pooled or scored. `collect` records its `blockers`, the review blockers of
one patch: `REQUEST_CHANGES` counts its findings as the reviewer returned them, `WRONG_APPROACH`
counts 1, and `APPROVE` and `NEEDS_HUMAN` count 0 (`NEEDS_HUMAN` shows in `variant`).
