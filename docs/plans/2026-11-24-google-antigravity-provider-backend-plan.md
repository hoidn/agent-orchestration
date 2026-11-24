# Google Antigravity (`agy`) Provider Backend Plan

**Status:** executed 2026-11-24 (Tasks 1 to 5); written by the coordinating session on the owner's goal "build a google
antigravity provider backend". This page is a plan and a record, not copy-safe guidance:
[specs/providers.md](../../specs/providers.md) owns the contract.

## Goal and scope

Make Google Antigravity's command-line agent (`agy`) a built-in provider at the level of the Claude
backend's plain, metered and session calls:

| In scope | Not in scope (reason) |
| --- | --- |
| Built-in templates `agy` and `agy_metered` with model and effort call-policy bindings | Price rows for the Gemini models (the price-table hash is pinned by several experiment kits, and the Antigravity model names have no verified list-price mapping). Usage reports tokens; cost is `None` and a spend cap refuses the model as unpriced |
| Session support: a fresh command and a resume command by conversation id | A native-store adapter for Agent Sessions recovery (the conversation store's format is unknown and it is the owner's own store) |
| A stream codec for `agy --output-format stream-json` (session id, assistant text, tool activity, terminal result) | Interactive (terminal) session support |
| A usage reader: token rows from the stream | Confinement and isolation lanes (OMP only today) |
| The test guard blocks a real `agy`; tests use a stand-in | Any experiment use: the experiment model rules in `AGENTS.md` are unchanged |
| Spec, capability matrix and README rows | Replacing the existing `gemini` template (its CLI is absent; left as it is) |

## Findings (live probe, `agy` 1.5.16, 2026-11-24)

Five completed calls and four refused ones on `gemini-3.8-flash`, effort `low` (one at `high`), from an
empty scratch repository, with `GEMINI_API_KEY` removed from the environment. Captures:
`tests/fixtures/agy/` once Task 1 lands (paths rewritten).

**Command line**

- `agy -p <prompt>` (alias `--print`) runs one turn and exits. `-p` takes the next argument as the
  prompt, whatever it looks like, so every other flag goes before it.
- The prompt cannot come from stdin in text mode: a trailing `-p` is a usage error (exit 2), and
  `-p -` sends a literal dash. The backend delivers the prompt in argv.
- `--model gemini-3.8-flash --effort low` works; `init.model` then reads `gemini-3.8-flash`. A model
  id with an effort suffix (`gemini-3.8-flash-low`) also works alone, and conflicts with `--effort`
  (exit 1). The backend passes the base model and the effort separately.
- `--conversation <id>` resumes; `--dangerously-skip-permissions` makes `permission_mode`
  `always-proceed` (the default is `request-review`); `--print-timeout` bounds the turn.
- Exit codes seen: 0 success, 1 a refused call (with a terminal `result` line), 2 a usage error (no
  JSON at all).

**`--output-format stream-json`: one JSON object per line, keyed by `event`**

```
{"event":"init","conversation_id":"<uuid>","init":{"model":"gemini-3.8-flash","cwd":"...","tools":[...],"permission_mode":"always-proceed"}}
{"event":"step_update","step_update":{"conversation_id":"<uuid>","step_index":1,"state":"ACTIVE","step_type":"agent_response","text_delta":"ok"}}
{"event":"step_update","step_update":{"conversation_id":"<uuid>","step_index":1,"state":"DONE","step_type":"agent_response","text_delta":"\n","duration_seconds":2.48,"usage":{"input_tokens":10501,"output_tokens":1,"thinking_tokens":0,"cache_read_tokens":0,"total_tokens":10502}}}
{"event":"step_update","step_update":{"conversation_id":"<uuid>","step_index":2,"state":"ACTIVE","step_type":"tool","tool_name":"write_file","tool_info":{...}}}
{"event":"result","result":{"conversation_id":"<uuid>","status":"SUCCESS","response":"ok\n","duration_seconds":2.51,"num_turns":1,"usage":{...}}}
```

- Step types seen: `user_input`, `agent_response`, `tool`, `system_message`. States: `ACTIVE`, `DONE`.
- A refused call prints one line: `result` with `status: "ERROR"`, an `error` string, an empty
  `conversation_id` and all-zero usage; there is no `init` line.
- **Usage arithmetic.** In every step and result seen, `total_tokens = input_tokens + output_tokens`;
  `thinking_tokens` is inside `output_tokens`; `cache_read_tokens` is outside `input_tokens`. No
  cache-write count is reported.
- **`result.usage` is cumulative over the conversation,** not the call: a resumed call's result
  showed `num_turns: 2` and the sum of both turns. The `DONE` `agent_response` steps of one call sum
  to that call's own usage (checked on a three-request call: 16,278 input, 1,860 output, 18,328 cache
  read).

**Credential**

- `agy` signs in with the owner's Google account (a subscription login under `~/.gemini`). The
  binary also reads `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `GOOGLE_GENAI_USE_VERTEXAI` and
  `GOOGLE_APPLICATION_CREDENTIALS` (names found in the binary; behaviour not tested), and this
  machine's environment sets `GEMINI_API_KEY`. `AGENTS.md` allows no API key.

**Not established:** whether `agy` prefers the API key over the login when both exist; failure shapes
other than a refused model (a usage limit, a network loss, a turn cut by `--print-timeout`, a failed
tool); the conversation store's format; `--output-format json`.

## Decisions (coordinator, 2026-11-24)

- **D1. Names.** Templates `agy` and `agy_metered`, after the CLI, as `claude` and `codex` are.
  Metadata mode `agy_stream_json_stdout`.
- **D2. Commands.** Flags first, prompt last:
  - plain: `agy --model ${model} --effort ${effort} --dangerously-skip-permissions -p ${PROMPT}`
  - metered and session fresh: the same with `--output-format stream-json` before `-p`
  - session resume: the fresh command with `--conversation ${SESSION_ID}` before `-p`
  - defaults `model: gemini-3.8-flash`, `effort: low` (the pair the probe verified); input mode argv;
    call-policy bindings `model` to `model` and `effort` to `effort`; `turn_boundary_resume: false`.
  - The bypass flag follows the built-in `codex` template; the same trusted-workspace warning applies.
- **D3. No API key reaches a built-in `agy` call.** The four variables above are removed from the
  child's environment on every launch path (plain, metered, session fresh and resume). The command's
  first token stays `agy` (run creation pins the first token's binary, so an `env -u ...` prefix would
  pin `env`). A workflow that wants key-based access declares its own template.
- **D4. Usage rows come from the steps, never from `result.usage`.**
  1. One row: the model is `init.model` (the call's policy model when there is no `init` line);
     `input`, `output` and `cache_read` are the sums over the call's `step_update` lines that carry
     `usage`, the last line per `step_index`; `cache_write` is 0. Source `step_update.usage`;
     `complete` is true when a `result` line was seen.
  2. No step usage and a `result` line whose usage is all zero: reported with no rows, complete
     (source `result.usage`): the CLI refused the call before any request.
  3. Anything else without step usage: `unknown` / `no_usage_event`.
  4. A counter that is not a non-negative integer, or a usage object whose `total_tokens` is not
     `input_tokens + output_tokens`: `malformed`. The reader does not guess a different arithmetic.
- **D5. Codec.** Session id: every non-empty `conversation_id` (top level, in `step_update`, in
  `result`); two different ids are a conflict. Assistant text: the `text_delta` strings of
  `agent_response` steps, joined. Tool activity: `Tool started: <name>` on a tool step's first
  `ACTIVE` line and `Tool completed: <name>` on its `DONE` line. Terminal: the `result` line;
  `result_subtype` is its `status` and `is_error` is `status != "SUCCESS"`.
- **D6. Spend cap.** `agy_stream_json_stdout` joins the metered transports, so the cap's refusal for
  an `agy` call names the missing price (`model_unpriced`), not a missing transport.
- **D7. Known ceiling: prompt size.** Linux limits one argv string to about 128 KB. A longer prompt
  fails at launch. `--input-format stream-json` would lift it and is not probed.

## Tasks

1. **Backend (implementer, Opus high).** D1 to D7 in `orchestrator/providers/` (`types.py`,
   `registry.py`, a new `session_transport_agy.py`, `session_transport.py`'s factory, `usage.py`),
   `orchestrator/workflow/evaluated/spend_cap.py`, and the test guard (`tests/conftest.py`
   `GUARDED_CLIS`). Fixtures from the probe captures under `tests/fixtures/agy/`. Tests: the usage
   reader (fresh, resumed, tool-using, refused, cut, malformed, total mismatch), the codec, the
   templates and bindings, the environment rule on each launch path, and one end-to-end run through
   the public command line with a stand-in `agy` (a metered step writes `usage.json` with token rows
   and `report` shows them; a session step resumes by conversation id if the public surface offers a
   provider-session step for argv templates).
2. **Contract and routing (same implementer).** `specs/providers.md` (metadata modes, the quick
   reference table, "Metered templates and usage": source, arithmetic, unpriced models, the
   environment rule, the prompt-size ceiling), `docs/capability_status_matrix.md`, the README's
   "Agent CLIs driven" row.
3. **Independent review (reviewer, Opus high),** then the author fixes accepted findings.
4. **Integration (coordinator).** Narrow selectors, the whole suite, merge to `main`, index row,
   ledger.
5. **Live check (coordinator).** One metered `agy` step through the public command line on
   `gemini-3.8-flash` effort `low` in a scratch workspace; compare `usage.json` with the stream.

## Ledger

| Date | Entry | Detail |
| --- | --- | --- |
| 2026-11-24 | Goal | Owner: "build a google antigravity provider backend". |
| 2026-11-24 | Probe | Nine `agy` 1.5.16 invocations from a scratch repository, `GEMINI_API_KEY` unset: five completed model calls on `gemini-3.8-flash` (four at `low`, one at `high` with two tool calls), about 50,000 input, 1,900 output and 26,800 cache-read tokens in all; four refused before any request (two usage errors, an unknown model, a model and effort conflict). Run by the coordinator as development probes on the owner's Google login; no experiment, no quality claim. |
| 2026-11-24 | Plan | This page; decisions D1 to D7. |
| 2026-11-24 | Built | Tasks 1 and 2 by an implementer on a branch: templates `agy` and `agy_metered`, mode `agy_stream_json_stdout`, the codec, the usage reader, `env_unset` on the template applied where the executor composes the child environment, the spend-cap transport set, the test guard, tests with a stand-in `agy`, and the spec, matrix and README rows. Found: the template's session commands run through the executor, but no public step can use them, because agent turns require a native-store adapter (out of scope). |
| 2026-11-24 | Review | Independent reviewer: ready after fixes. Accepted and fixed by the author: the zero-usage report is limited to the refused shape (no `init`, empty conversation id, status not `SUCCESS`); `complete` needs a `SUCCESS` result and, on a fresh conversation, step sums equal to the result's total; three more variables removed (`GOOGLE_GENAI_USE_ENTERPRISE`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`; seven in all), and the spec says which names are removed and that file-based credentials are not controlled, not that the login is used; a Claude model id served by `agy` that matches a price row is priced by it as a lower bound (no cache-write count); a loud failure when a metered insert would not sit before `-p ${PROMPT}`; `env_unset` validated. Declined: a shared base class for the Claude and `agy` codecs. D3 and D6 above are superseded on these points by the spec. |
| 2026-11-24 | Live check | Two calls through the public command line from the branch, `gemini-3.8-flash` effort `low`, scratch workspace, `GEMINI_API_KEY` set in the parent: `agy_metered` exited 0, wrote its result, and `usage.json` (13,166 input, 201 output, 8,813 cache read, complete) equals the stream's step sums and the result line's total; `report` shows the tokens with no cost. Plain `agy` exited 0, wrote its result, usage `unknown` / `no_transport` as for every plain template. |
| 2026-11-24 | Suite and merge | Whole suite on the branch merged with `main`: 24,953 passed, 72 failed. 71 are the known launch artefacts of a whole-suite run from a new tmux session (`test_prompt_resume_child` 55, the provider-isolation backend tests 10, `test_executor_retirement_cutoff` 2, nanoBragg 4). The other, `test_workflow_evaluated_item_io.py::test_nested_public_orchestrator_clears_parent_coordinate_in_own_serial_launch`, failed because the run was started without `PYTHONPATH` set to the tree, so its nested `python -m orchestrator` imported the stale editable install; its module passes with `PYTHONPATH` set (12 passed). No provider-guard hit. Fast-forwarded to `main` at `e5a4fb6f`. |
