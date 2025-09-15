# Observability and Status JSON (Normative parts noted)

- Debug mode
  - `--debug` enables verbose logging: substitution traces, dependency resolution details, command construction, environment snapshot (masked), and file ops.
  - Prompt audit: with `--debug`, composed prompt text is written to `logs/<Step>.prompt.txt` with known secret values masked.

- Execution logs
  - Under `RUN_ROOT/logs/`: `orchestrator.log`, `StepName.stdout` (>8 KiB or JSON parse error), `StepName.stderr` (when non-empty), `StepName.debug` (when enabled).

- Error context (normative)
  - On step failure, record message, exit code, tails of stdout/stderr, and error context details (undefined variables, missing deps, substituted command, missing secrets, etc.).

- Progress and metrics
  - Optional `--progress` renders `[n/N] StepName: Running (Xs)...` and loop progress `[i/total]`.
  - State includes timing metrics: step duration, provider time, wait duration, file I/O counts where applicable.

- Trace context
  - Steps may include trace IDs in commands using variable substitution.

- Status JSON (normative schema; orchestrator does not consume)
  - Recommended path: `artifacts/<agent>/status_<step>.json`.
  - Example fields: `schema: "status/v1"`, `correlation_id`, `agent`, `run_id`, `step`, `timestamp`, `success`, `exit_code`, `outputs[]`, `metrics{}`, `next_actions[]`, `message`.
  - All file paths within a status JSON must be relative to WORKSPACE.

Orchestrator interaction: The orchestrator does not consume or act on status JSON files. They are for observability and external tooling only; control flow derives solely from the workflow YAML and `state.json`.

## Error Context (shape)

On step failure, record a structured error object similar to:

```json
{
  "error": {
    "message": "Command failed with exit code 1",
    "exit_code": 1,
    "stdout_tail": ["last", "10", "lines"],
    "stderr_tail": ["error", "messages"],
    "context": {
      "undefined_vars": ["${context.missing}"],
      "failed_deps": ["data/required.csv"],
      "substituted_command": ["cat", "data/file_20250115.csv"]
    }
  }
}
```

## Progress and Metrics

- `--progress` renders `[n/N] StepName: Running (Xs)...` and loop progress `[i/total]`.
- State includes: step duration, wait duration, provider time, and file I/O metrics where applicable.
