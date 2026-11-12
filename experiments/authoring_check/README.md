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
| `run_session.sh` | Claims a slot, starts one session in a fresh random directory, runs `check.py` on it and files the results |
| `check.py` | The pass check: `compile`, then a visible case, two fixed hidden cases and one hidden case drawn when the check runs; each must reach the expected record with at least rounds + 1 completed command steps and exactly rounds + 1 calls to `line_count.sh` |
| `readout.py` | Per arm, sessions passed out of sessions run, known cost, sessions of unknown cost and the ledger charge; per session, fail reasons, tokens, cost, models, CLI version, wall time and failed `orchestrator` invocations |

The kit is tested end to end with a scripted stand-in for the agent CLI and
the no-provider stubs on `PATH`:
[`tests/test_authoring_check_kit.py`](../../tests/test_authoring_check_kit.py).

## Run it

Keep the environments and the sessions root outside the checkout (the
launcher refuses otherwise). Use an interpreter that has the repository's
dependencies. Run the *before* sessions before the tutorial merges, and read
out the first session (its `init` and `result` events, models and cost)
before starting the second.

```bash
KIT=experiments/authoring_check
python $KIT/build_env.py before /tmp/authoring-check/env-before
python $KIT/build_env.py after /tmp/authoring-check/env-after --commit <phase tip>
# three of each, one at a time; the budget must be approved first
AUTHORING_CHECK_SPEND_AUTHORIZED=yes bash $KIT/run_session.sh /tmp/authoring-check/env-before ~/authoring-check-sessions
AUTHORING_CHECK_SPEND_AUTHORIZED=yes bash $KIT/run_session.sh /tmp/authoring-check/env-after ~/authoring-check-sessions
python $KIT/readout.py ~/authoring-check-sessions
```

- *before* installs the Phase 1 base, `22dfb973` (the parent of the first
  Phase 1 code commit), and gives `docs/lisp_workflow_drafting_guide.md`.
- *after* installs the commit given with `--commit` and gives
  `docs/tutorial_first_pipeline.md`; it fails if that commit has no tutorial.

## What the launcher binds

- Model `claude-haiku-5-5`, with no `--fallback-model`.
- `--max-budget-usd 2` per session and a 20-minute wall limit (`timeout
  1200`); the session runs as its own process group, killed whole when it ends.
- Tools `Bash,Read,Write,Edit` only (no subagent tool), `--strict-mcp-config`
  with no MCP configuration, `--disable-slash-commands`, `--setting-sources
  project`, `--no-session-persistence`, `--permission-mode bypassPermissions`.
- A fresh environment (`env -i`): `HOME`, `USER`, `LANG`, `TERM=dumb` and
  `PATH` = the arm's `venv/bin`, then copies of the no-provider stubs (so
  `claude` and `codex` in the session and in the check fail and are logged),
  then `/usr/local/bin:/usr/bin:/bin`. The real CLI is started by its
  absolute path. Model variables are set to `claude-haiku-5-5`
  (`ANTHROPIC_MODEL`, `ANTHROPIC_DEFAULT_MODEL`,
  `ANTHROPIC_DEFAULT_{HAIKU,SONNET,OPUS,FABLE}_MODEL`,
  `ANTHROPIC_SMALL_FAST_MODEL`, `CLAUDE_CODE_SUBAGENT_MODEL` with
  `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1`); the advisor tool, CLAUDE.md files,
  auto memory, the refusal fallback and the auto-updater are off. Effort is
  not set: the CLI default applies and is recorded as such.
- Slots `<arm>-1` to `<arm>-3` are claimed once in
  `~/.local/state/authoring-check`, whatever sessions root is given. Deleting
  a session directory, using another root or rebooting does not free a slot,
  so no session is retried and there are at most six sessions in all.
- The first session records the `claude` version there; a later session on
  another version refuses unless `AUTHORING_CHECK_ALLOW_CLI_CHANGE=yes`.

The agent works in a fresh `/tmp/ac-XXXXXXXX` directory holding only
`GUIDE.md` and `line_count.sh`. After the check it moves to
`<sessions root>/<arm>-<n>/work`, beside `transcript.jsonl`
(`--output-format stream-json --verbose`), `claude.stderr`, `check.json`,
`session.json` and, if a stub was called, `no-provider.log`.

## What counts as a pass

`readout.py` counts a session as passed only when:

- `check.py` passed;
- the CLI ended with a `success` result inside the wall limit and the cap;
- the models on the `init` event, every assistant event and the result are
  exactly `claude-haiku-5-5` (an empty list fails);
- no tool call starts `claude` or `codex` or names another model, no nested
  Claude or Codex session was recorded for the session's directory, and no
  stub was called;
- no tool input or output names the checkout (absolute, under `~` or `$HOME`,
  or relative), the sessions root, or other sessions' stores.

A session directory without `session.json` (an interrupted launch) is a fail.
A session with no cost record is reported with cost unknown and charged the
USD 2 cap in the arm's ledger charge. The phase's check is met when at least
two of three *after* sessions pass; the *before* figure is recorded beside it.
