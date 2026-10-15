# Claude plain stream-json form: mini-probe receipt (Task 6a, D8a)

This probe qualifies nothing; it feeds PQ-1a and gates Plan B on the Claude completion rule.

## Run

- Date: 2026-10-14. CLI: `claude --version` → `2.1.300 (Claude Code)`. Model: `haiku` (store reports `claude-haiku-5-5`).
- Command (run once, in tmux session `claude-miniprobe`, `PYTHONPATH` = the agent-sessions worktree):

  ```bash
  python scripts/experiments/native_session_cli_probe.py --provider claude --execute --model haiku \
    --command-form plain --max-calls 3 --output-dir /tmp/claude-plain-form-1792027184
  ```

- Model calls: **3** (bound 3). Exit 0, status `PLAIN_CAMPAIGN_COMPLETE`. Staged credential removed after the run; none remains under the evidence directory.
- Argv per call: the `claude_unrestricted_workspace.session_support` commands from the provider registry, unchanged
  (`-p --output-format stream-json --verbose --model haiku --effort low --permission-mode bypassPermissions`; resumes add
  `--resume <stdout session id>` right after `-p`), prompt on stdin, no `--json-schema`.
- Private evidence: `/tmp/claude-plain-form-1792027184/` (mode 0700; stdout/stderr/stdin logs, `observations.json`, native snapshots).

## Per call

The single native file was `projects/<workspace>/<session>.jsonl` after every call; every resume appended to it.
Stdout carried exactly one `result/success` event per call and one stable `session_id`.

| Call | Phase | rc | Quiescent | Duration s | Submitted user line | Tool round | Final row(s) | Snapshot SHA-256 |
|---|---|---|---|---|---|---|---|---|
| 1 | fresh (review) | 0 | yes | 5.3 | 3 | assistant `tool_use` 22 → user `tool_result` 23 | assistant `end_turn` **33 (thinking) + 34 (text), same `message.id`** | `46a368ce4f4e55f4a952d75da6e8498cbb4ffbaab1b5795f1176d9e5a5af9937` |
| 2 | resume (write) | 0 | yes | 4.4 | 39 (parent → 34) | 43 → 44 | assistant `end_turn` 48 | `aaccdf5b7334a25d0077bb80af6aa268c6d7a25d9882b97753d71b8ecb39fb29` |
| 3 | resume (review) | 0 | yes | 4.2 | 54 (parent → 48) | 57 → 58 | assistant `end_turn` 62 | `fd52e7cc47633853c5ceb3f6efab487eec323c51a982e1f3604582357bc36fe5` |

Other row kinds between those lines are non-`user`/`assistant` and outside the turn walk: `queue-operation`, `attachment`
(environment, model, deferred_tools_delta, agent_listing_delta, skill_listing, total_tokens_reminder, session_context, date,
credential_org, remote_session_change, prompt_snapshot, mcp_instructions_delta), `atis-latch`, `api-request-shape`,
`api-request-blob`, `api-request`, `last-prompt`, `mode`, `cost-state`. No `isMeta` user rows, no sidechain rows, no
`toolEndsTurn` rows, no resume-padding rows were seen.

## Native-store adapter (Task 5, as committed at ec7ce943)

`native_store_adapter(CLAUDE_STREAM_JSON_STDOUT)`, applied offline to each snapshot with the call's nonce as `prompt_marker`
and the previously bound position as `after`:

| Call | `head().position` | `head().open_turn` | `completed_turn` |
|---|---|---|---|
| 1 | None | True | None |
| 2 | None | True | None |
| 3 | None | True | None |

Cause: turn 1's final assistant message (with a thinking block) is written as two rows, one per content block, both with
`stop_reason: end_turn` and the same `message.id`. `_claude_turn_final` requires exactly one final row, so turn 1 is
incomplete, and every later turn is unlinkable to it. Turns 2 and 3 (no thinking block) each pass the existing checks in
isolation; their submitted rows descend from the last row of the previous final (34, 48).

Offline simulation only (not committed): treating only the last row of each assistant `message.id` as a final binds all
three calls in sequence — positions (turn 1, line 34), (turn 2, line 48), (turn 3, line 62), `open_turn=False`,
`completed_turn` bound each with `user_line` 3, 39, 54.

## Verdict

`completion_marker: end_turn` — every plain-form turn ends in the native store with an assistant `stop_reason: end_turn`
row; no `toolEndsTurn` row was observed in these 3 calls.

Gate note: the store-only completion exists, but the committed Claude adapter does not bind it when the final message is
split across content-block rows (observed on 1 of 3 turns, the one with a thinking block). Task 5's Claude completion rule
needs to treat one assistant `message.id` (its last row) as the single final before the Claude adapter can drive Plan B.
