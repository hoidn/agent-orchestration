# Authoring Check Kit

**Status: experiment kit, frozen once committed.** It implements the
[authoring-check protocol](../../docs/plans/2026-11-11-roadmap-phase-1-first-hour-plan.md#authoring-check-protocol)
of roadmap Phase 1: does a fresh agent session, given one document and the
CLI, write a working provider-free workflow? The plan owns the question, the
arms, the budget and the ledger; this page only says how to run the kit. The
readout reports execution outcomes and cost; it makes no quality claim.

Only `run_session.sh` spends provider calls, and only when
`AUTHORING_CHECK_SPEND_AUTHORIZED=yes` is set. Everything else calls no model.

## Files

| File | Role |
| --- | --- |
| `task.md` | The task given to every session, the same in both arms |
| `line_count.sh` | The existing script the workflow must call; logs each call to `line_count.calls` beside itself |
| `build_env.py` | Builds one arm: a virtual environment with `orchestrator` installed from a commit, and that arm's document as `GUIDE.md` |
| `run_session.sh` | Starts one session in a new directory, then runs `check.py` on it |
| `check.py` | The pass check: `compile`, then a visible and two hidden cases, each to the expected record, with `line_count.sh` called in the hidden runs |
| `readout.py` | Per arm, sessions passed out of sessions run; per session, tokens, cost, models, wall time and failed `orchestrator` invocations |

The kit is tested end to end with a scripted stand-in for the agent CLI and
the no-provider stubs on `PATH`:
[`tests/test_authoring_check_kit.py`](../../tests/test_authoring_check_kit.py).

## Run it

Keep every directory below outside the checkout (the scripts refuse
otherwise) and outside any directory that holds a `CLAUDE.md`; `/tmp` is
fine. Use an interpreter that has the repository's dependencies.

```bash
KIT=experiments/authoring_check
python $KIT/build_env.py before /tmp/authoring-check/env-before
python $KIT/build_env.py after /tmp/authoring-check/env-after --commit <phase tip>
# three of each, one at a time; the budget must be approved first
AUTHORING_CHECK_SPEND_AUTHORIZED=yes bash $KIT/run_session.sh /tmp/authoring-check/env-before /tmp/authoring-check/sessions
AUTHORING_CHECK_SPEND_AUTHORIZED=yes bash $KIT/run_session.sh /tmp/authoring-check/env-after /tmp/authoring-check/sessions
python $KIT/readout.py /tmp/authoring-check/sessions
```

- *before* installs the Phase 1 base, `22dfb973` (the parent of the first
  Phase 1 code commit), and gives `docs/lisp_workflow_drafting_guide.md`.
- *after* installs the commit given with `--commit` and gives
  `docs/tutorial_first_pipeline.md`; it fails if that commit has no tutorial.

## What the launcher binds

- Model `claude-haiku-5-5`, with no `--fallback-model`; variables that remap
  models (`ANTHROPIC_MODEL`, `ANTHROPIC_DEFAULT_*_MODEL`,
  `ANTHROPIC_SMALL_FAST_MODEL`, `CLAUDE_CODE_SUBAGENT_MODEL`) are removed.
- `--max-budget-usd 2` per session and a 20-minute wall limit (`timeout 1200`).
- Tools `Bash,Read,Write,Edit` only (no subagent tool), `--strict-mcp-config`
  with no MCP configuration, `--disable-slash-commands`, `--setting-sources
  project`, `--no-session-persistence`, `--permission-mode bypassPermissions`.
- The arm's `venv/bin` first on `PATH` and `PYTHONPATH` removed.
- Session directories are `<arm>-1` to `<arm>-3`, created once each. A fourth
  session of an arm, or a session directory that already exists, is refused,
  so no session is retried and the total cannot pass six sessions.

The transcript (`--output-format stream-json --verbose`) is saved as
`transcript.jsonl` beside the session's `work/` directory, with
`claude.stderr`, `check.json` and `session.json`.

## What counts as a pass

`readout.py` counts a session as passed only when `check.py` passed, the CLI
ended with a `success` result inside the wall limit and the spend cap, the CLI
reported no model other than `claude-haiku-5-5`, and no tool call named a
path under the checkout. A session directory without `session.json` (an
interrupted launch) is a fail. The phase's check is met when at least two of
three *after* sessions pass; the *before* figure is recorded beside it.
