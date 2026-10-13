# Two-agent chess

This target-2.36 workflow sends one shared text value to White, then sends
White's returned text to Black. Each configured round calls both agents in
that order. The initial value and each accepted provider result overwrite the
same caller-selected Markdown file; the workflow returns Black's final string.
The String contains the position, full move history, and public messages. The
provider result contract requires a JSON string at the root.

The workflow defaults to 100 rounds. Omit the `rounds` input for that
default budget; set it to a smaller value for a short game or smoke run. It does
not check move legality, adjudicate the game, detect checkmate or draws, or
stop early when a game ends.

`providers.black` uses the existing `claude_unrestricted_workspace` profile so
Claude can write its result bundle in the attempt directory. Use it only in a
trusted local workspace. The selected board file is display output; workflow
state and recovery remain in the Orchestrator run.

From the repository root, compile and run one smoke round with the shipped
initial position. Change the path to a new filename for each game:

```bash
python -m orchestrator compile experiments/agent_chess/chess.orc \
  --source-root experiments \
  --entry-workflow agent_chess/chess::run \
  --provider-externs-file experiments/agent_chess/providers.json \
  --prompt-externs-file experiments/agent_chess/prompts.json \
  --command-boundaries-file experiments/agent_chess/commands.json

python -m orchestrator run experiments/agent_chess/chess.orc \
  --source-root experiments \
  --entry-workflow agent_chess/chess::run \
  --provider-externs-file experiments/agent_chess/providers.json \
  --prompt-externs-file experiments/agent_chess/prompts.json \
  --command-boundaries-file experiments/agent_chess/commands.json \
  --input-file experiments/agent_chess/inputs.json \
  --input path=artifacts/agent_chess/partida-2026-10-12.md \
  --input rounds=1
```

For a live shared view, start one session on the repository's tmux socket, run
the command in that session, then attach to it from another terminal:

```bash
tmux -S /tmp/claude-tmux-sockets/claude.sock new-session -s agent-chess
# In another terminal:
tmux -S /tmp/claude-tmux-sockets/claude.sock attach -t agent-chess
```

Run the `orchestrator run` command above in that session. Read the current
board at any time with `cat artifacts/agent_chess/partida-2026-10-12.md`, and
resume an interrupted or failed run with `python -m orchestrator resume RUN_ID`.

Evaluated runs stream provider stdout/stderr by default unless `--quiet` is
used. Visibility depends on the CLI: Codex showed tool activity in the live
smoke; the current Claude print-mode profile showed its final response without
intermediate tool activity. tmux displays what each CLI emits.
