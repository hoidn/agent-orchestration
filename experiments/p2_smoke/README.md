# P2 Live Smoke Kit

**Status: experiment kit, frozen by its manifest; not guidance.** It runs
tranche T1 of roadmap Phase 2, the live smoke of the parallel best-of-N
consumer ([A3](../../docs/plans/2026-11-11-roadmap-phase-2-qualification-metering-names-plan.md#a3-the-best-of-n-consumer-m)
and the [headline exit test](../../docs/plans/2026-11-11-roadmap-phase-2-qualification-metering-names-plan.md#headline-exit-test)).
The plan owns the budget and the ledger; this page only says how to run the
kit. `run_smoke.sh` is not a launcher pattern to copy.

Only `run_smoke.sh` spends provider calls, and only with
`P2SMOKE_SPEND_AUTHORIZED=yes` after the tranche is approved and recorded in
the plan's ledger. `readout.py` and a rehearsal call no model.

## What it shows, and what it cannot

The deterministic exit test
(`tests/test_phase2_exit_e2e.py`) shows with stand-ins that a parallel
best-of-N run survives a kill, resumes, and that `report` shows tokens per
step and a total. This smoke shows the same once with a real Claude CLI:

- the run is killed mid-map (two coders committed, two held) and completes
  on `resume`;
- no committed coder is dispatched again;
- every real call records complete usage, and `report --format json` shows
  tokens for each provider step and a total equal to their sum;
- the smoke stays under its cost ceiling, with no hook trace and no other
  model.

It cannot show: the quality of any change or of the judge's choice; any rate
(one run); a kill while a real call is in flight (the held coders never
started their CLI); the Codex adapter; anything about other tasks, models or
N. Measure-free figures only: no judge, no quality claim.

## The program and the kill

The workspace gets a copy of the runtime's
`experiments/orc_vs_single_call/workflows/best_of_n.orc` with exactly the
changes the deterministic tests make (target 2.37, the candidate map
`:parallel 2 :workspace repo`) and its three `:model` literals set to
`claude-haiku-5-5`; `run_smoke.sh` refuses a source whose literals are not
the expected ones. Four candidate repositories (`alpha` to `delta`) each hold
`calc.py` with `add` returning `a - b`; the task is the deterministic test's
(`inputs.json`).

The kill uses the exit test's mechanism: during the first `run`, the wrapper
holds the coders of `gamma` and `delta` (the last two items, started only
when `alpha` and `beta` commit) before their CLI starts, and the launcher
SIGKILLs the run's process group and the held wrappers once both are held.
It waits on files and the memo, never on a timer. `resume` then runs
`gamma`, `delta` and the judge. Five paid calls in all; the two held
attempts made no call and are the report's two `unknown_attempts` (so
`run.usage.partial` is true).

## Files

| File | Role |
| --- | --- |
| `manifest.json` | SHA-256 of every file below; its own SHA-256 goes in the plan's ledger |
| `criterion.json` | Checks, infrastructure-failure rules, spend limits, the pinned fixture commit, what one run cannot decide |
| `inputs.json` | The task and intent (the launcher adds the four repository paths) |
| `providers.json` | Both aliases on `claude_unrestricted_workspace_metered` |
| `run_smoke.sh` | Compiles, runs, kills, resumes, reports, writes `smoke.json` |
| `smoke_claude.sh` | The smoke's `claude`: nesting guard, the hold, call count and spend limits, isolation flags |
| `readout.py` | Verdict `pass`, `fail` or `undetermined` against the criterion; `--retry-check` |
| `rehearsal/claude` | The rehearsal stand-in (no model) |

Tests: [`tests/test_p2_smoke_kit.py`](../../tests/test_p2_smoke_kit.py)
(every launcher refusal, the wrapper's limits, the rehearsal end to end, the
retry, the readout on constructed results), on a closed `PATH`.

## How models and calls are bound

Every call is `claude-haiku-5-5`: the source copy's literals, checked by exact
id, and every model variable of the run's fresh environment (`env -i`). Both
aliases are on the Claude metered template, so every call prints transport
JSON and records `usage.json`; `codex` on the run's `PATH` is a stub that logs
and fails. Every call goes through `smoke_claude.sh`, first on the run's
`PATH`, which adds `--setting-sources project --strict-mcp-config
--disable-slash-commands --max-budget-usd 0.5` (user-level settings, plugins,
hooks, skills and MCP servers are not loaded; the
[PQ-1c README](../pq1c/README.md#how-the-models-and-calls-are-bound) has the
evidence) and refuses a `claude` started from inside the smoke. The
orchestrator runs from `RUNTIME` (`PYTHONPATH`; it refuses another import),
with provider observation (tmux) off.

## Spend limits

- USD 0.5 per call (`--max-budget-usd`); the CLI documents that the request in
  flight can pass it, and the kit does not bound that overshoot.
- At most 7 calls: the wrapper claims `launch-1` to `launch-7` in the slot
  ledger and refuses an eighth.
- USD 3 for the smoke: the wrapper refuses a call when the runtime's cap
  figure of every earlier launch (`cap_cost`: the larger of the CLI's
  reported cost and the highest-tier price), with USD 0.5 for each launch
  without complete usage including this one, passes USD 3. The `run` also
  has `--max-cost-usd 3`.
- `resume` has no `--max-cost-usd`. After the kill the held attempts have no
  `usage.json`, and a capped resume stops with `spend_cap_unmetered` by
  contract ([CLI, "Spend cap"](../../specs/cli.md)); the rehearsal confirmed
  it. The wrapper's limits apply to the resume's calls.
- Planned: 5 calls. One retry by `resume` uses at most the 2 calls left.
- A stop by a spend limit is an observation (`fail`), never retried.

## Run it

```bash
# A frozen runtime: a detached checkout of the main commit that holds this kit.
git worktree add --detach ~/p2smoke-rt <commit>
# P2SMOKE_MANIFEST_SHA256: the manifest digest recorded in the plan's ledger -- take it from the ledger,
# never from the kit (sha256sum of the kit's own manifest.json proves nothing).
export P2SMOKE_MANIFEST_SHA256=<the ledger's manifest_sha256>
P2SMOKE_SPEND_AUTHORIZED=yes bash ~/p2smoke-rt/experiments/p2_smoke/run_smoke.sh ~/p2smoke-rt ~/p2smoke-results
python ~/p2smoke-rt/experiments/p2_smoke/readout.py ~/p2smoke-results
```

Before anything is launched, `run_smoke.sh` refuses: from inside the smoke
(nested); without the authorization; without the ledger's manifest digest, or
with a kit file that differs from `manifest.json`; a binding other than
`claude-haiku-5-5` on the metered template; a `claude` that is the blocking
no-provider stub; a used slot; a runtime with uncommitted changes under
`orchestrator/` or in the source, or a kit with uncommitted changes; a CLI
version other than the first slot's; a run `PATH` where another directory
holds a `claude` or `codex`; a program that does not compile. The slot ledger
is `~/.local/state/p2smoke`, whatever the results directory.

Results: `RESULTS_DIR/smoke/` holds `smoke.json` (run id, exit codes, the kill
facts: coders committed before the kill and the held attempts; coders
committed after; every launch; native session ids; per-step and total usage
and cost; CLI version; runtime commit; kit hashes), `workspace/`, `bin/`,
`run.log`, `resume.log`, `report.json` and any `nested-calls.log`,
`refused-calls.log` or `codex-calls.log`.

**The one retry.** When `readout.py --retry-check RESULTS_DIR` exits 0 (the
first attempt is an infrastructure failure: an API error, a CLI that did not
start or answer, version drift, an isolation problem; after a kill as
planned; and no spend stop), the same command with
`P2SMOKE_INFRA_RETRY="<reason>"` resumes the same run once more into
`RESULTS_DIR/smoke-retry/`. The readout then uses the retry and lists the
replaced attempts. A first attempt that filed no `smoke.json`, or whose kill
did not happen as planned, cannot be retried by resume: it needs a new
tranche.

## Rehearse

```bash
HOME=$(mktemp -d) P2SMOKE_MANIFEST_SHA256=<digest> P2SMOKE_REHEARSAL_STANDINS=experiments/p2_smoke/rehearsal \
  bash experiments/p2_smoke/run_smoke.sh "$PWD" /tmp/p2smoke-rehearsal
python experiments/p2_smoke/readout.py /tmp/p2smoke-rehearsal     # exits 2: no verdict on a rehearsal
```

A rehearsal runs the whole path with `rehearsal/claude`, which must carry the
line `# p2smoke-rehearsal-stand-in: makes no provider call` and is refused
while `P2SMOKE_SPEND_AUTHORIZED` is set. Its slot ledger is
`RESULTS_DIR/rehearsal-ledger`; every record says `rehearsal: true`. Use a
temporary `HOME`: the stand-in writes its transcripts where the CLI keeps
them (`~/.claude/projects/`).

## Verdict

`readout.py` refuses (exit 2) a kit file that differs from the manifest, a
slot that ran with another manifest, a retry of a valid observation, and any
rehearsal. Otherwise: `undetermined` when an infrastructure failure holds
(the list is in `criterion.json`), `pass` when every check holds, `fail`
naming the checks that do not.
