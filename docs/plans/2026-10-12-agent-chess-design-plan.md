# Two-Agent Chess: Minimal Design and Plan

**Status:** Implemented and verified.

**Goal:** Alternate two prompts that play chess and exchange messages through a Markdown board passed as text.

## Design

The workflow carries one `String`: the complete current board, move history, and public messages. White receives that text and returns an updated version; Black receives White's version and returns the next. Repeat for a configurable number of rounds, defaulting to 100. Each round contains one call to each player.

Each short prompt instructs its player to make one move, preserve the history, append a message for the opponent, and return the complete updated Markdown. With `:returns String`, the agent writes a JSON string to the runtime's `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` file. The runtime decodes that string as the next board value; stdout is not the result channel. The agent need not create `partida.md`. Black's prompt also repeats the file-delivery instruction following a live missing-file failure; the [incident report](../reports/2026-10-13-claude-missing-result-file.md) records the evidence and a proposed general improvement.

Pass `--provider-externs-file providers.json` to bind `providers.white` and `providers.black` to registered providers. The package selects `codex` and `claude_unrestricted_workspace`. Each [provider template](../../orchestrator/providers/registry.py) specifies `command` and `input_mode` (`stdin` or `argv`) for prompt delivery. The runtime supplies the result-file transport; `:returns String` specifies the result type. Models remain workflow inputs.

A small Python command writes each returned string to a run-specific `partida.md`, after the provider result commits. It also writes the initial board before the first call. The next agent receives the string directly; it does not reread the mutable file.

Run the workflow in tmux so the user can watch the active agent's stdout/stderr live. Evaluated `run`/`resume` stream by default unless `--quiet` is used; the final JSON result remains a separate channel. Use one shared pane for the alternating calls: this route does not automatically create per-agent observation panes. Visibility depends on what the selected provider CLI emits.

The implementation is [chess.orc](../../experiments/agent_chess/chess.orc). It defaults to 100 rounds, with `rounds` configurable at launch. Unlike the original sketch, the compiler requires an explicit reachable `done`; the loop therefore carries a round counter and returns Black's result after the requested final round. The [drafting guide](../lisp_workflow_drafting_guide.md) and [evaluated IO contract](../../specs/io.md#evaluated-command-and-provider-io-target-235) govern the target-2.36 implementation.

The selected roles are Codex for White and Claude for Black. The real verification run overrides `rounds=1`; it does not change the workflow's default. Models are workflow inputs; the package defaults to `gpt-6.1-sol` and `claude-fable-5-1`.

## Boundaries

The MVP does not validate chess legality, parse the board, retry illegal moves, or automatically detect game completion. It stops at the round limit or an ordinary runtime failure. Agents may describe an outcome in their text; the workflow does not adjudicate it. This trades chess correctness for a small demonstration of alternating agent calls.

If validation is later requested, keep it behind one Python command with a thin `.orc` call. A rules library is not an MVP dependency.

Use existing run/resume semantics: committed provider results can be reused; unfinished attempts may repeat. The round bound is not a retry-spend guarantee. `partida.md` is a display copy, and a missing or stale copy can be rewritten from the saved result string; resume alone does not guarantee file regeneration.

## Implementation plan

- [x] Add `experiments/agent_chess/chess.orc`: module/type declarations, initial-board input, bounded alternating calls, and final string result.
- [x] Add the two short prompts and `providers.json` bindings, selecting models at setup time; include `--provider-externs-file` in the launch command.
- [x] Add a minimal Python writer and its command-boundary manifest; write the initial text and each player's committed result to `partida.md`.
- [x] Compile and run a short deterministic-provider smoke: verify White → Black → White ordering, exact text handoff, round termination, file contents, and reuse on resume. Check that terminal output arrives before provider exit while the JSON result is read separately. Test runtime contract failures rather than chess rules or literal prompt wording.
- [x] Document the tmux launch/attach commands and limitations, then try a bounded real-provider exchange with visible live output.

Verification on 2026-10-13: five new tests collected. The affected suite passed **78 tests** with `pytest -q -n 16 --dist=worksteal`, covering the chess package and evaluated providers, input documents, provider lifecycle, and invalidation smoke. Evidence is in `/tmp/agent-chess-execution-auf1856l/affected-tests.log`. Contract and independent code-quality reviews passed.

After integration into the main workspace, collection again found five tests and all five passed (`/tmp/agent-chess-execution-auf1856l/integrated-tests.log`). No orchestrator runtime code was changed for this package.

Live run `20261013T065534Z-zk5mh3` completed one verification round (`1. e4 e5`) with Codex White and Claude Black. Black's initial missing-file failure was corrected by repeating its delivery instruction, then resuming; White's attempt 1 was reused and Black committed attempt 2. The published board exactly matches Black's accepted string. Codex emitted tool activity in tmux; the selected Claude CLI profile emitted its final response without intermediate tool activity. This checks orchestration and recovery, not chess correctness or the reliability of a full 100-round game.

Upstream incorporation on 2026-10-13: the target-2.36 package was already present
as untracked files on `main` at `845b4152`; no dynamic-core conversion was needed.
Fresh collection found five tests, and `python -m pytest -q
tests/experiments/test_agent_chess.py` passed all five, including public
compile/run/resume and streaming checks with local provider stand-ins. The
README's standalone compile command also passed. Local receipts are in
`/tmp/chess-upstream-20261013-o0vboww3/`. This verification did not launch a new
paid-provider game or rerun the full repository suite.
