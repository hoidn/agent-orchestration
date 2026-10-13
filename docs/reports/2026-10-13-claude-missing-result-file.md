# Claude returned JSON text but did not create the required result file

Date: 2026-10-13. This is an observed delivery failure and a proposed prompt improvement, not an established diagnosis of the model's reasoning.

## What happened

The minimal chess workflow calls Codex as White and Claude as Black, passing the board, move history, and public messages as a `String`. The live smoke used `gpt-6.1-sol` and `claude-fable-5-1`, with one round. The workflow itself defaults to 100 configurable rounds.

In run `20261013T065534Z-zk5mh3`:

1. Codex wrote its JSON string to the required result file. The runtime accepted it and published the board after `1. e4`.
2. Claude's first attempt printed a fenced JSON string containing `1. e4 e5` in its assistant response, but did not create the result file.
3. The runtime rejected that attempt with `provider_result_missing`. The accepted board remained at White's `1. e4`.
4. After adding an explicit file-writing instruction to Black's prompt, `orchestrator resume` retried Black. Claude's second attempt created the file, and the run completed with `1. e4 e5`. White's committed result was reused; White remained on attempt 1, and Black completed on attempt 2.

The successful retry demonstrates that this configuration can deliver the file. It does not establish why the first attempt failed or prove that the revised wording caused the improvement.

## Exact injected output contract

The following block was generated automatically by the runtime and appended after Black's task instructions and typed board input. It was not authored in the chess prompt:

```text
## Output Contract
Produce one JSON value exactly as specified. If ORCHESTRATOR_OUTPUT_BUNDLE_PATH is present, write only to that runtime-owned authoritative target. Otherwise, do not create or modify the listed path; emit the JSON value as final assistant text only so the runtime can materialize it.
# Relpath values are workspace-relative. Include the declared `under` prefix in the value: for `under: artifacts/work`, write `artifacts/work/...`; for `under: artifacts/review`, write `artifacts/review/...`.
- path: .orchestrate/runs/20261013T065534Z-zk5mh3/effects/72a855a38f739ffa94692643bc61abec8e9db0e48f2d15d80e20eccfe7a4c4dc/attempt-1/result.json
  format: JSON value
  type: string
```

The shared renderer is [`_render_root_output_bundle_contract_block`](../../orchestrator/contracts/prompt_contract.py). The evaluated provider invocation supplies `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, and the result reader requires the file: see [`_prepare_provider_invocation` and `_provider_result`](../../orchestrator/workflow/evaluated/providers.py).

Here `:returns String` specifies the decoded result type. The file must contain one JSON-encoded string; it is not a request for a JSON object or a Markdown file. Provider stdout/stderr remain observable terminal output and do not substitute for the result file in this execution route. A separate Python command publishes the accepted string as the human-readable board.

## What we can and cannot conclude

The instruction already says to write to the runtime-owned target when the variable is present. It is reasonably clear. The observed failure is noncompliance with that delivery requirement; the available record does not distinguish misunderstanding, failure to inspect the environment, or omission of the required tool action.

The opening phrase “Produce one JSON value” emphasizes content before delivery. The conditional also presents a final-response alternative. Either could contribute to a model returning text, but those are hypotheses, not demonstrated causes. The term “JSON value” is technically correct and should not be replaced with “JSON object” when the declared return type is `String`.

## Local correction used for the retry

Black's prompt received this additional paragraph:

```text
Use your file-writing or shell tool to write that text as a JSON string to the exact file named by the ORCHESTRATOR_OUTPUT_BUNDLE_PATH environment variable. Read the variable and write the file before finishing; printing JSON in your reply does not deliver the result. Change no other files.
```

This repeats the delivery obligation at the application level. It allowed the smoke to continue without changing the runtime, weakening result validation, or manually fabricating the missing provider result. It is not evidence that every application should carry its own transport instructions.

## Suggested general fix

Have the runtime-generated contract state the delivery mechanism selected for that invocation, leading with the required action. For this file-based `String` result, an illustrative replacement is:

```text
## Output Contract
Write one JSON-encoded string to this file:
<runtime-provided result path>

Use a tool to create the file before finishing. The environment variable
ORCHESTRATOR_OUTPUT_BUNDLE_PATH identifies the same required target.
Returning the string in your assistant response does not deliver the result.

The file must contain valid JSON whose root value is a string.
```

The runtime should fill in the actual target. If a different provider transport requires final assistant text for runtime materialization, generate the corresponding text-delivery instruction for that invocation instead. Do not remove that supported path globally or ask an agent to choose between transports the runtime has already selected.

Keep the existing missing-file, JSON-parsing, and type checks. This proposal changes delivery guidance, not the result contract or the authority of stdout. The general renderer change is **proposed, not implemented** in the chess work.

Before adopting it, verify rendering for each supported delivery mechanism and compare multiple live attempts with the original and revised wording. Measure missing-file failures separately from invalid JSON and wrong result types. One failed attempt followed by one successful retry is insufficient to claim improved reliability.

## Local evidence

Evidence workspace: `/tmp/agent-chess-execution-auf1856l/live` (temporary local files).

- [Run state](/tmp/agent-chess-execution-auf1856l/live/.orchestrate/runs/20261013T065534Z-zk5mh3/state.json)
- [Black attempt 1: complete injected prompt](/tmp/agent-chess-execution-auf1856l/live/.orchestrate/runs/20261013T065534Z-zk5mh3/effects/72a855a38f739ffa94692643bc61abec8e9db0e48f2d15d80e20eccfe7a4c4dc/attempt-1/prompt.txt)
- [Black attempt 1: stdout containing the JSON response](/tmp/agent-chess-execution-auf1856l/live/.orchestrate/runs/20261013T065534Z-zk5mh3/effects/72a855a38f739ffa94692643bc61abec8e9db0e48f2d15d80e20eccfe7a4c4dc/attempt-1/stdout.txt)
- [Black attempt 2: accepted result file](/tmp/agent-chess-execution-auf1856l/live/.orchestrate/runs/20261013T065534Z-zk5mh3/effects/72a855a38f739ffa94692643bc61abec8e9db0e48f2d15d80e20eccfe7a4c4dc/attempt-2/result.json)
- [Published board](/tmp/agent-chess-execution-auf1856l/live/artifacts/agent_chess/live/partida.md)
