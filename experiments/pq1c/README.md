# PQ-1c Kit

**Status: experiment kit, frozen by its criterion.** It runs the
[PQ-1c protocol](../../docs/plans/2026-11-11-roadmap-phase-2-qualification-metering-names-plan.md#pq-1c-protocol)
of roadmap Phase 2: is the Agent Sessions variant of design-review-execute
worth keeping against the plain baseline? The plan owns the question, the
budget and the ledger; this page only says how to run the kit. Nothing here is
guidance beyond the kit, and `run_cell.sh` is not a launcher pattern to copy.

Only `run_cell.sh` spends provider calls, and only when
`PQ1C_SPEND_AUTHORIZED=yes` is set after the owner approves the tranche.
`readout.py` and a rehearsal call no model.

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
| `criterion.json` | The axes, thresholds, outcomes, readings, infrastructure-failure rules and spend limits, and the SHA-256 of every file that defines a cell (`frozen_files`); its own SHA-256 is `CRITERION_SHA256` in `readout.py` |
| `inputs.json` | The task, and `planner_model` and `reviewer_model` set to `claude-haiku-5-5` (frozen) |
| `providers.json` | Both provider aliases on `claude_unrestricted_workspace_metered` (frozen) |
| `run_cell.sh` | Runs one cell and files its evidence (frozen) |
| `cell_claude.sh` | The cell's `claude`: the flags and the nesting guard below (frozen) |
| `readout.py` | Computes the axes from the four cells and returns one outcome or `undetermined`, with reasons |

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

## Spend limits

- USD 0.5 per call (the wrapper) and USD 2 per run (`--max-cost-usd 2`,
  checked before each call; a resumed cell is capped at USD 2 over the run).
- Four paid calls per cell, sixteen for the four cells, plus **one
  infrastructure retry in all** (one cell, four calls): at most **20 paid
  calls**, and at most USD 10 by the caps (5 runs at USD 2). The CLI's budget
  stop may overshoot by the request in flight; that is not measured.
- A retry (`PQ1C_INFRA_RETRY="<reason>"`, slot `<cell>-retry`) is allowed only
  for a cell whose first attempt finished as an infrastructure failure
  (`readout.py --retry-check`), or died without filing its record; never while
  the first attempt runs, never for a valid observation, and never a second
  time.

## Run a cell

```bash
# RUNTIME: a frozen checkout (its orchestrator package and workflow sources are used)
PQ1C_SPEND_AUTHORIZED=yes bash experiments/pq1c/run_cell.sh RUNTIME variant-clean ~/pq1c-results
python experiments/pq1c/readout.py ~/pq1c-results   # check variant-clean before going on
# then variant-resumed, baseline-clean, baseline-resumed, one at a time
```

Run `variant-clean` first and read its record before the other cells: its
first turn is where `--effort high` for Haiku, the wrapper flags and the
metered transport meet a real CLI for the first time. A failure there is an
infrastructure failure, and the readout says so.

Before anything is launched, `run_cell.sh` refuses: without the authorization
variable; a binding other than `claude-haiku-5-5` on the metered template, or
a source that binds `:model` to anything but the two inputs (checked by exact
id, so no Fable model or model above the ceiling can pass); kit files whose
SHA-256 differs from `frozen_files`, or a criterion other than the frozen
one; a kit or runtime (`orchestrator/`, `workflows/examples/`) with
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
- Results go to `RESULTS_ROOT/<slot>/`: `cell.json` (bindings, frozen-file
  hashes, runtime and fixture commits, source digest, criterion hash, exits,
  stop facts, seconds; written whole), `workspace/` (the clone and its run
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
the readout `undetermined`, when its record is missing, unreadable or names
another cell; when no turn committed; when it stopped for a spend cap or the
per-call budget; when a provider attempt shows no model output or no usage;
when codex was called; when a call's init event lists a plugin, an MCP server
or another model; or when a resumed cell lacks the evidence of its stop and
its resume. Cells that mix rehearsal and real runs, or differ in runtime,
fixture or sources, also read out as `undetermined`. `readout.py` refuses
(exit 2) a criterion or a cell recording another criterion or other frozen
files, and a retry of a cell whose first attempt is a valid observation; with
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
  number.

The owner then records whether what was observed justifies losing the
ability to invalidate feedback; readout and judgment go in the plan's ledger.

## Known gaps

The wrapper's flags are verified against `claude --help` (2.1.322) only, not
in a real `-p --resume` session; the readout checks each call's init event for
plugins and MCP servers afterwards. The agent can still start a CLI by its
absolute path; only the `PATH` route is closed.
