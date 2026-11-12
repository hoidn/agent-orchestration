# PQ-1c Kit

**Status: experiment kit, frozen by its manifest.** It runs the
[PQ-1c protocol](../../docs/plans/2026-11-11-roadmap-phase-2-qualification-metering-names-plan.md#pq-1c-protocol)
of roadmap Phase 2: is the Agent Sessions variant of design-review-execute
worth keeping against the plain baseline? The plan owns the question, the
budget and the ledger; this page only says how to run the kit. Nothing here is
guidance beyond the kit, and `run_cell.sh` is not a launcher pattern to copy.

Only `run_cell.sh` spends provider calls, and only when
`PQ1C_SPEND_AUTHORIZED=yes` is set after the owner approves the tranche.
`readout.py` and a rehearsal call no model.

## Result

Run on 2026-11-12: runtime `bac6f00d`, Claude CLI 2.1.322, every call
`claude-haiku-5-5`, manifest SHA-256
`22974744964c7f179e713c203ddbb7fdfbe5be9903e0738cab497dfa63c47211`. All four
cells are valid observations and no retry was used: 16 calls, USD 0.333.

| Cell | Completed | Native sessions | Elapsed | Metered cost |
| --- | --- | --- | --- | --- |
| `variant-clean` | yes | 2 | 381 s | USD 0.120 |
| `baseline-clean` | yes | 4 | 349 s | USD 0.069 |
| `variant-resumed` | yes (stopped with exit 75 after two turns, resumed) | 2 | 253 s | USD 0.083 |
| `baseline-resumed` | yes (stopped with exit 75 after two turns, resumed) | 4 | 296 s | USD 0.061 |

- No committed turn was dispatched again, no attempt started twice, and usage
  was recorded for every call.
- Invalidating the feedback step: refused in the variant (exit 2,
  `invalidate_coordinator_committed`, bytes unchanged); done in the baseline
  (exit 0).
- Cost ratio, variant over baseline: 1.74 clean, 1.38 resumed. The first two
  turns cost about the same in both arms; the variant's two later turns run
  in a session that already holds the earlier turns, and read more cached
  tokens and wrote more output.
- **Outcome by the frozen criterion: Retire, by cost** (both ratios at or
  above 1.25).
- **Owner judgment: Agent Sessions is kept.** Its value is the workflow
  patterns it allows, which a comparison on one pattern that both arms can
  express does not measure
  ([roadmap decision 11](../../docs/plans/2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md#owner-decisions)).
  The figures above are the known price of using a session.

These are measure-free figures from one run per cell: no judge, no quality
claim. They decide nothing about retained context, document quality, elapsed
time or failure rates. The approval is used up; do not run a cell again
without a new one. The raw run roots are outside the repository
(`/home/ollie/pq1c-results`; `readout.json` there has SHA-256
`8ec99942997cb9671d8fcaa40cca5dfd6c97f366d0fe35c386b245f59237ac6b`); the
[plan ledger](../../docs/plans/2026-11-11-roadmap-phase-2-qualification-metering-names-plan.md#ledger)
has one row per cell.

## The protocol in brief

Four cells, one run each: the variant
`workflows/examples/design_review_execute_agents.orc` and the baseline
`design_review_execute.orc`, sources unchanged, each run clean and resumed.
Each cell runs on a fresh clone of one fixture repository holding the
documents of the consumer tests' `design_docs` fixture, with the same task
text (`inputs.json`). A resumed cell is stopped right after the reviewer's
first turn is durable (`settled` for the variant's agent turn, `committed` for
the baseline's provider step; nothing is in flight), then resumed. The
readout reports measure-free figures only: no judge and no quality claim.

## Files

| File | Role |
| --- | --- |
| `manifest.json` | The SHA-256 of every file below; its own SHA-256 is recorded in each cell and in the plan's ledger |
| `criterion.json` | The axes, thresholds, outcomes, readings, infrastructure-failure and isolation rules, spend limits and the pinned fixture commit |
| `inputs.json` | The task, and `planner_model` and `reviewer_model` set to `claude-haiku-5-5` |
| `providers.json` | Both provider aliases on `claude_unrestricted_workspace_metered` |
| `run_cell.sh` | Runs one cell and files its evidence |
| `cell_claude.sh` | The cell's `claude`: the flags and the nesting guard below |
| `readout.py` | Computes the axes from the four cells and returns one outcome or `undetermined`, with reasons |

`run_cell.sh` and `readout.py` both refuse when any file differs from
`manifest.json`, and the readout refuses a cell that ran with another
manifest, so a changed criterion, task, launcher or readout cannot be mixed
with cells run before the change.

The kit is tested end to end with stand-in providers on a closed `PATH`:
[`tests/test_pq1c_kit.py`](../../tests/test_pq1c_kit.py) and
[`tests/test_pq1c_readout.py`](../../tests/test_pq1c_readout.py).

## How the models and calls are bound

The sources are not edited. Every model reaches a call through the
`planner_model` and `reviewer_model` inputs (the sources' defaults,
`claude-opus-5-5` and `gpt-6.1-sol`, are overridden), so every call is
`claude-haiku-5-5`. `providers.codex` is bound to the Claude metered template
too, so the Codex session adapter is not exercised and the reviewer is not
another model family. The metered template, not the
`claude_unrestricted_workspace` the protocol names, is used because a run
under `--max-cost-usd` needs metered templates. The sources fix
`:effort "high"`; whether the Claude CLI accepts it for Haiku is unverified.

Every call goes through `cell_claude.sh`, first on the run's `PATH`, which
adds `--setting-sources project --strict-mcp-config --disable-slash-commands
--max-budget-usd 0.5`: the operator's user-level settings, plugins, hooks,
skills, agents and MCP servers are not loaded, and one call cannot spend more
than USD 0.5 by the CLI's own count. It sets `PQ1C_IN_CELL` for the session it
starts and refuses (exit 97, logged to `nested-calls.log`) a `claude` started
from inside a cell, so the agent's shell cannot start an unmetered session of
another model. No other directory on the run's `PATH` may hold a `claude` or
`codex`; `codex` itself is a stub that logs and fails.

No one needs to edit their personal settings. Evidence that the flags leave
user-level hooks and environment out, gathered on this host without a model
call:

- `~/.claude/settings.json` has no `hooks` or `env` key (key names read
  only). Its user-level hooks come from the enabled plugins: ponytail and
  superpowers both register `SessionStart` hooks for `startup`.
- The CLI documents that `SessionStart` and `Setup` hook events are always in
  a stream-json stream (`--include-hook-events` in the CLI reference). The six
  authoring-check sessions recorded on this host with the same three flags
  (`/home/ollie/authoring-check/sessions`) have no hook event and none of the
  plugins' injected text, and their init events list only the built-in
  plugins: `enabledPlugins`, a user setting, was not applied, so the user
  settings file, with any `hooks` or `env` it might hold, was not loaded.
- `--setting-sources` selects which of `user`, `project` and `local` settings
  load (`claude --help`, CLI reference).

The readout checks this again for every call: a hook event in a call's stream,
or a hook record (`attachment` with a `hookEvent`) in the cell's session
transcripts, makes the cell an infrastructure failure.

## Spend limits

- USD 0.5 per call (`--max-budget-usd 0.5`, in the wrapper): the real bound,
  USD 2 for a run of four calls. The CLI documents that spend can pass this
  budget by the request in flight; the kit does not bound that overshoot.
- `--max-cost-usd 10` for the run, checked before each call. That cap prices
  every token at the model's highest tier, five times Haiku's ordinary rate,
  so four calls at the per-call ceiling price at USD 10; a lower cap would
  stop a run before the per-call ceilings do (USD 2 would stop it near USD 0.40
  of real spend).
- Four paid calls per cell, sixteen for the four cells, plus **one
  infrastructure retry in all** (one cell, four calls): at most **20 paid
  calls**, at most **USD 10** by the per-call ceilings, plus the documented
  overshoot of each call.
- A stop by either limit (`spend_cap_reached`, or the CLI's
  `error_max_budget_usd`) is a cost outcome, not infrastructure: the cell did
  not complete, it is never retried, and its recorded cost is reported.
- A retry (`PQ1C_INFRA_RETRY="<reason>"`, slot `<cell>-retry`) is allowed only
  for a cell whose first attempt finished as an infrastructure failure
  (`readout.py --retry-check`), or died without filing its record; never while
  the first attempt runs, never for a valid observation (a cost stop is one),
  and never a second time.
- The first cell records the CLI version in the ledger (`claude-version`); a
  later cell on another version refuses. `DISABLE_AUTOUPDATER=1` is set in
  every cell's environment (`claude --help` documents no other switch), but the
  operator's other sessions can still update a shared install.

## Run a cell

```bash
# RUNTIME: a frozen checkout (its orchestrator package and workflow sources are used)
# PQ1C_MANIFEST_SHA256: the manifest digest recorded in the plan's ledger -- take it from the ledger, never
# from the kit (sha256sum of the kit's own manifest.json proves nothing)
export PQ1C_MANIFEST_SHA256=<the ledger's manifest_sha256>
PQ1C_SPEND_AUTHORIZED=yes bash experiments/pq1c/run_cell.sh RUNTIME variant-clean ~/pq1c-results
python experiments/pq1c/readout.py ~/pq1c-results   # check variant-clean before going on
# then variant-resumed, baseline-clean, baseline-resumed, one at a time
```

Run `variant-clean` first and read its record before the other cells: its
first turn is where `--effort high` for Haiku, the wrapper flags and the
metered transport meet a real CLI for the first time. A failure there is an
infrastructure failure, and the readout says so.

Before anything is launched, `run_cell.sh` refuses: without the authorization
variable; without `PQ1C_MANIFEST_SHA256`, or when it differs from the kit's
`manifest.json` (a kit edited consistently and committed cannot run); a binding other than `claude-haiku-5-5` on the metered template, or
a source that binds `:model` to anything but the two inputs (checked by exact
id, so no Fable model or model above the ceiling can pass); a kit file whose
SHA-256 differs from `manifest.json`; a CLI version other than the first
cell's; a kit or runtime (`orchestrator/`, `workflows/examples/`) with
uncommitted changes; a `claude` that is a blocking no-provider stub; a cell
name other than exactly one of the four; a used slot; a retry outside the
rule above; a run `PATH` where another directory holds a provider CLI; a
program that does not compile with these bindings.

- Slots are claimed once in `~/.local/state/pq1c`, before the first call,
  whatever the results root.
- Every orchestrator invocation runs with `PYTHONPATH=RUNTIME` (it refuses an
  `orchestrator` imported from elsewhere) and a fresh environment (`env -i`)
  with every model variable pinned to `claude-haiku-5-5`; the advisor,
  CLAUDE.md files, auto memory, the refusal fallback and the auto-updater are
  off. Provider observation (tmux) is off in every cell.
- Results go to `RESULTS_ROOT/<slot>/`: `cell.json` (bindings, the manifest
  digest and kit-file hashes, runtime and fixture commits, source digest, CLI
  and Python versions, price-table digest, native sessions and hook records,
  exits, stop facts, seconds; written whole), `workspace/` (the clone and its run
  tree), `run.log`, `resume.log`, `report.json` (`report --format json`) and,
  for a clean cell, `invalidate.json` from `invalidate <run> <feedback
  identity>` on a copy (`invalidate-copy/`). The fixture repository is
  `RESULTS_ROOT/fixture.git`.

## Rehearse

Set `PQ1C_REHEARSAL_STANDINS=DIR` (and leave `PQ1C_SPEND_AUTHORIZED` unset) to
run `DIR/claude` instead of the `claude` on `PATH`. The stand-in must carry the
line `# pq1c-rehearsal-stand-in: makes no provider call`, be under 1 MB, and
be neither the `claude` on `PATH` nor an installed CLI under
`~/.local/share/claude`. Rehearsal slots live in
`~/.local/state/pq1c-rehearsal` and each cell records `rehearsal: true`. The
kit's tests rehearse the four cells under a temporary `HOME` with the
agent-session stand-in printing metered usage: four provider calls per cell,
sixteen in all.

## What the readout can and cannot decide

It can decide completion, repeated dispatch, the invalidate behavior, whether
usage was recorded, and a cost difference outside the 0.8 to 1.25 band. It
cannot decide retained context, document quality, elapsed time, a cost
difference inside the band, or how often a cell fails.

Only workflow-level outcomes decide. A cell is an infrastructure failure, and
the readout `undetermined`, when:

- its record is missing, unreadable or names another cell, or its fixture is
  not the pinned commit;
- no turn committed (unless it stopped for cost), or the cap could not meter
  a call (`spend_cap_unmetered`);
- a provider attempt shows no usage or no output tokens;
- codex was called, or a `claude` was started inside the cell;
- a call ended with an API error (an `is_error` result with an
  `api_error_status`, or text starting `API Error`: overloaded, 5xx, rate
  limit, login); a failure the model produced stays a workflow outcome;
- a hook event in a call's stream, or a hook record in the cell's session
  transcripts;
- a call's init event is missing, lacks a key the check reads, or lists what
  the isolation flags should have removed: a plugin that is not built in, an
  MCP server, a skill, a slash command, an agent outside the built-in set, or
  another model (the built-in plugins and agents are the ones a real isolated
  session lists on this host);
- the CLI's sessions for the workspace (`~/.claude/projects/<path>/`: each
  `<id>.jsonl` transcript and each `<id>/` folder, which is all a call without
  session persistence leaves) are not exactly the sessions the attempts name
  (2 for a variant cell, 4 for a baseline cell): an extra one means a CLI ran
  outside the journal. This
  detects such spend; it cannot prevent it, and its cost is outside every cap;
- a resumed cell lacks the evidence of its stop and its resume.

Cells that mix rehearsal and real runs, or differ in runtime commit, fixture,
CLI version, Python version, price table or sources, also read out as
`undetermined`. `readout.py` refuses (exit 2) a kit file that differs from
`manifest.json`, a cell that ran with another manifest, and a retry of a cell whose first attempt is a valid observation; with
a retry it names the attempt it used and the one it replaced.

Readings of the protocol, written into the criterion before it was frozen:

- a repeated dispatch of a committed turn counts toward Retire only in
  variant cells;
- a resumed run that fails at the workflow level before the stop counts as
  not completed;
- a pair's cost ratio exists only when both of its cells completed: a
  baseline that failed is never a cheap baseline, and a pair with a cell that
  did not complete leaves the cost axis undetermined;
- a cost that is not a finite number above zero, or a partial one, is never a
  number;
- a stop by the spend cap or the per-call budget counts as not completed, not
  as infrastructure.

The owner then records whether what was observed justifies losing the
ability to invalidate feedback; readout and judgment go in the plan's ledger.

## Known gaps

The wrapper's flags are verified against `claude --help` (2.1.322) and a
recorded fresh isolated session, not in a real `-p --resume` session; the
readout checks each call's init event afterwards. The agent can still start a
CLI by its absolute path; only the `PATH` route is closed, and the transcript
count detects the likely case afterwards. The built-in plugin and agent sets
are those of CLI 2.1.322; if a built-in plugin leaves a hook record in a real
transcript, every cell reads out undetermined (fails closed) and the first cell
shows it.
