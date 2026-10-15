# Experiment Model Guard Plan (No Fable In Experiment Calls)

Status: implemented and independently approved on `fix/no-fable-experiment-defaults`; 116 harness tests pass. No live experiment call was made for this change.

## Problem

Owner instruction, 2026-10-15: "make sure fable isnt being used for any experiment". The changed defaults cover the
calls that workflows make, but there is a second path:

- Agents share `$HOME`, and `~/.claude/settings.json` selects `claude-fable-5-1`.
- So any nested `claude` that omits `--model` or asks for Fable reaches Fable. This includes candidate tests run by an
  agent, and agents that launch Claude.
- The independent review found 220 such sessions: `Say OK only.` probes fired by candidate tests in Task 8 rung 2 and
  in E-B2 `design_review_execute`.

## Approach

Prevention on the known call path, plus detection as a backstop, inside the harness only. Global settings and
provider infrastructure stay unchanged.

1. **Guard wrapper.** Add `experiments/compare/shim/model-guard`, a `claude` stand-in.
   - It finds the next real `claude` on `PATH`, skipping its own directory.
   - It refuses any `--model X` or `--model=X` naming Fable (exit 2, without calling the CLI). The same applies to
     `--fallback-model`, in both forms and for every model in a comma-separated list.
   - It prepends `--model claude-opus-5-5` when no `--model` is given. A fallback model does not count as one.
   - Otherwise it passes arguments, stdin, streams and the exit status through unchanged.
2. **Shim.** On every call, the shim installs the guard as `$COMPARE_TREE/.model-guard/claude`, in the run's own
   tree. An identical guard is left alone. A missing one is created by hard-linking a fully written, executable
   temporary copy, which never replaces a file. Only an edited guard is replaced, by rename. Parallel calls therefore
   never write or replace a running script: `bwrap`'s `execvp` was seen to miss a file while it was being renamed
   over. On a failure the shim removes the temporary file and exits 70. That directory goes first on the sandboxed agent's `PATH`, after the shim and bookkeeping have been
   stripped.
   - Top-level `claude` calls run through it.
   - Codex agents, and anything they start, find it first.
   - The sandbox environment sets `CLAUDE_CODE_SUBAGENT_MODEL=claude-opus-5-5` and
     `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1`. By the [documented contract](https://code.claude.com/docs/en/sub-agents#run-every-subagent-on-one-model) (Claude Code 2.1.257 or later;
     2.1.301 is installed), these pin in-process subagents, teammates and workflow agents to Opus, and leave the main
     model unchanged.
   - The shim still makes one call record per provider start, tees the streams, passes the exit status through and
     captures patches as before. Because the guard lives at the tree root, it never enters a candidate's patch.
3. **Scan.** The Claude-session scan also reads each assistant message's `message.model` metadata. Printed text is
   never matched.
   - A Fable model there is a `Fable model` hit.
   - That hit cannot be adjudicated `cleared`.
   - A run or judge with it is excluded by `pool` and `summarize`, and every hit is listed.
   - The existing D5 hits and verdicts are unchanged.
4. **Tests first.** Behavioural tests go in the existing harness test modules:
   - a nested call with no model gets Opus;
   - `--model fable` and `--model=claude-fable-5-1` are refused without the CLI running;
   - an explicit non-Fable model is kept;
   - a Codex arm's nested `claude` gets Opus;
   - a Fable session under a nested pytest project directory is flagged, cannot be cleared, and is excluded from the
     pool.
5. **Disclosure.**
   - The Task 8 report gets a dated notice: 100 nested Fable probes.
   - The E-B2 report gets a dated notice: 120 nested Fable probes.
   - A compact audit file goes in the evidence directory.
   - Policy docs and memory are updated.

## What this makes harder, and its limits

- These paths bypass prevention. The scan can detect Fable only when the call leaves a Claude session under the tree's project slug; a direct API call without such a session is invisible:
  - a process that calls the real `claude` binary by absolute path;
  - one that resets `PATH`;
  - one that drops the two subagent variables;
  - a CLI older than 2.1.257;
  - one that calls the Anthropic API directly.
- The fake-CLI tests check that the variables reach the agent, not the vendor's implementation of them.
- Sessions started with a hard-coded `/tmp` working directory record under `-tmp-…` and cannot be attributed to a
  tree.
- `claude` subcommands get `--model` prepended when they have none, which may change how a subcommand parses.
