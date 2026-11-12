# PQ-1c Kit

**Status: experiment kit, frozen once committed.** It runs the
[PQ-1c protocol](../../docs/plans/2026-11-11-roadmap-phase-2-qualification-metering-names-plan.md#pq-1c-protocol)
of roadmap Phase 2: is the Agent Sessions variant of design-review-execute
worth keeping against the plain baseline? The plan owns the question, the
budget and the ledger; this page only says how to run the kit. Nothing here is
guidance beyond the kit.

Only `run_cell.sh` spends provider calls, and only when
`PQ1C_SPEND_AUTHORIZED=yes` is set after the owner approves the tranche.
`readout.py` and the rehearsal call no model.

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
| `criterion.json` | The axes, thresholds and the three outcomes (Retire, Retain, Improve), frozen before any call; its SHA-256 is `CRITERION_SHA256` in `readout.py` |
| `providers.json` | Both provider aliases on `claude_unrestricted_workspace_metered` |
| `inputs.json` | The task, and `planner_model` and `reviewer_model` set to `claude-haiku-5-5` |
| `run_cell.sh` | Runs one cell and files its evidence |
| `readout.py` | Computes the axes from the four cells and returns one outcome or `undetermined`, with reasons |

The kit is tested end to end with stand-in providers on a closed `PATH`:
[`tests/test_pq1c_kit.py`](../../tests/test_pq1c_kit.py).

## How the models are bound

The sources are not edited. Every model reaches a call through the
`planner_model` and `reviewer_model` inputs (the sources' defaults,
`claude-opus-5-5` and `gpt-6.1-sol`, are overridden), so every call is
`claude-haiku-5-5`. `providers.codex` is bound to the Claude metered template
too, so the Codex session adapter is not exercised and the reviewer is not
another model family. The metered template records usage and lets the
`--max-cost-usd 2` cap work. The sources fix `:effort "high"`; whether the
Claude CLI accepts it for Haiku is unverified: the first turn of the first
cell is the check.

Before anything is launched, `run_cell.sh` refuses: without the authorization
variable; when `inputs.json` or `providers.json` binds anything else, when the
template sets another model, or when the source binds `:model` to anything
but those two inputs (checked by exact id, so no Fable model or model above
the ceiling can pass); when `claude` resolves to a blocking no-provider stub;
when `criterion.json` is not the frozen one; for a cell other than the four;
for a slot already used; for a second infrastructure retry of a cell; when
the runtime has uncommitted changes under `orchestrator/` or
`workflows/examples/`; when the program does not compile with these bindings.

## Run a cell

```bash
# RUNTIME: a frozen checkout (its orchestrator package and workflow sources are used)
PQ1C_SPEND_AUTHORIZED=yes bash experiments/pq1c/run_cell.sh RUNTIME variant-clean ~/pq1c-results
# ... variant-resumed, baseline-clean, baseline-resumed, one at a time
python experiments/pq1c/readout.py ~/pq1c-results
```

- Slots `variant-clean`, `variant-resumed`, `baseline-clean` and
  `baseline-resumed` are claimed once in `~/.local/state/pq1c`, whatever the
  results root. A cell stopped by a cause outside the workflow may be run once
  more with `PQ1C_INFRA_RETRY="<reason>"` (slot `<cell>-retry`); the readout
  then uses the retry.
- Every orchestrator invocation runs with `PYTHONPATH=RUNTIME` (it refuses an
  `orchestrator` imported from elsewhere), a fresh environment (`env -i`) whose
  `PATH` holds only the cell's `bin` (`claude`, and a `codex` stub that logs
  and fails), the interpreter's directory, `/usr/bin` and `/bin`; every model
  variable is pinned to `claude-haiku-5-5`; the advisor, CLAUDE.md files, auto
  memory, the refusal fallback and the auto-updater are off. Provider
  observation (tmux) is off in every cell.
- Results go to `RESULTS_ROOT/<slot>/`: `cell.json` (bindings, runtime commit,
  fixture commit, source digest, criterion hash, exits, stop facts, seconds),
  `workspace/` (the clone and its run tree), `run.log`, `resume.log`,
  `report.json` (`report --format json`) and, for a clean cell,
  `invalidate.json` from `invalidate <run> <feedback identity>` on a copy
  (`invalidate-copy/`). The fixture repository is `RESULTS_ROOT/fixture.git`.

## Rehearse

Set `PQ1C_REHEARSAL_STANDINS=DIR` to run `DIR/claude` (a stand-in) instead of
the `claude` on `PATH`. Rehearsal slots live in
`~/.local/state/pq1c-rehearsal` and each cell records `rehearsal: true`. The
kit's tests rehearse the four cells with the agent-session stand-in printing
metered usage, under a temporary `HOME`: four provider calls per cell, sixteen
in all.

## What the readout can and cannot decide

It can decide completion, repeated dispatch, the invalidate behavior, whether
usage was recorded, and a cost difference outside the 0.8 to 1.25 band. It
cannot decide retained context, document quality, elapsed time, a cost
difference inside the band, or how often a cell fails. An unknown or partial
cost is never a number: it leaves the cost axis undetermined, and the outcome
is `undetermined` when that axis could still decide it. Cells that mix
rehearsal and real runs, differ in runtime, fixture or sources, or record a
model other than `claude-haiku-5-5` read out as `undetermined`. `readout.py`
refuses (exit 2) a criterion or a cell whose criterion hash is not the frozen
one. The owner then records whether what was observed justifies losing the
ability to invalidate feedback; readout and judgment go in the plan's ledger.

## Known gaps

User-level Claude Code settings and hooks still load: the template's command
is fixed and the kit does not pass `--setting-sources`. They apply to both
arms alike.
