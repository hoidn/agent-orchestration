# Step IO and Output Capture (Normative)

- Input handling
  - `input_file`: read literal contents; no substitution inside file contents.
  - When using a provider, the composed prompt (after optional injection) is passed via argv `${PROMPT}` or piped to stdin per provider template.

- Output handling
  - `output_file`: STDOUT is tee'd to this file and to the orchestrator capture pipeline.
  - Stderr is captured separately and written to logs when non-empty.

- Output capture modes
  - `text` (default): store up to 8 KiB in `state.json`. If exceeded, set `truncated: true` and write full stdout to `logs/<Step>.stdout`.
  - `lines`: split on LF; store up to 10,000 lines. On overflow, set `truncated: true` and spill full stdout to `logs/<Step>.stdout`.
  - `json`: parse stdout as JSON up to 1 MiB buffer. Parse failure or overflow → exit 2 unless `allow_parse_error: true`.
  - When `allow_parse_error: true` in json mode, the step completes with `exit_code: 0`, stores raw `output` (subject to 8 KiB limit), omits `json`, and records `debug.json_parse_error`.

- State fields
  - For `lines`/`json`, omit raw `output` to avoid duplication; include `truncated` flag and mode-specific fields.

## Tee semantics details

- With `output_file` set, the file receives the full stream while state/log limits apply.
- `text`: up to 8 KiB retained in state; full stdout goes to `logs/<StepName>.stdout` when truncated.
- `lines`: up to 10,000 lines retained in state; full stdout goes to `logs/<StepName>.stdout` when truncated.
- `json`: buffer up to 1 MiB for parsing; on overflow or invalid JSON, exit 2 unless `allow_parse_error: true`. The `output_file` always receives the full stream.
- Stderr is captured separately and written to `logs/<StepName>.stderr` when non-empty.

## Line splitting and normalization

- Lines are split on LF (`\n`). CRLF (`\r\n`) is normalized to LF in the `lines[]` entries.
- The raw, unmodified stdout stream is preserved in `logs/<StepName>.stdout` when truncation occurs or when JSON parsing fails.
