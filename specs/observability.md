# Observability and Status JSON (Normative parts noted)

- Debug mode
  - `--debug` enables verbose logging: substitution traces, dependency resolution details, command construction, environment snapshot (masked), and file ops.
  - Prompt audit: with `--debug`, composed prompt text is written to `logs/<Step>.prompt.txt` with known secret values masked.
  - `--stream-output` live-streams provider stdout/stderr to the parent console without enabling prompt audit, verbose debug logging, or state backups.

- Execution logs
  - Under `RUN_ROOT/logs/`: `orchestrator.log`, `StepName.stdout` (>8 KiB or JSON parse error), `StepName.stderr` (when non-empty), `StepName.debug` (when enabled).
  - v2.10 provider-session visits also create visit-scoped metadata and optional retained transport spools under `RUN_ROOT/provider_sessions/`.

- Error context (normative)
  - On step failure, record message, exit code, tails of stdout/stderr, and error context details (undefined variables, missing deps, substituted command, missing secrets, etc.).
  - v1.5 gate failures use `error.type: "assert_failed"` and `exit_code: 3`.
  - v1.6 typed predicate resolution/evaluation failures use `error.type: "predicate_evaluation_failed"` with structured predicate context.
  - v1.8 cycle guards use `error.type: "cycle_guard_exceeded"` with structured context (`guard`, `limit`, `observed`, `step`).

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

- Status/report surfaces
  - Step snapshots may include normalized `output.outcome` fields when present in `state.json`.
  - The normalized outcome surface is intended for human-readable reports and typed routing; it does not replace the underlying `status`, `exit_code`, or `error` fields.
  - v1.7 scalar bookkeeping steps report distinct kinds (`set_scalar`, `increment_scalar`) and expose their local produced values through the normal `output.artifacts` surface.
  - v1.8 status/report snapshots expose workflow-level `transition_count` / `max_transitions` and step-level `visit_count` / `max_visits` when present.
  - When a top-level step name is revisited, step snapshots may expose:
    - `visit_count`: total top-level visit count from `state.step_visits`
    - `current_visit_count`: visit ordinal of the in-flight `current_step` when that step name is currently running
    - `last_result_visit_count`: visit ordinal recorded on the latest persisted result at `steps.<StepName>`
  - v2.0 status/report snapshots may expose `step_id` alongside display `name`; display names remain the human-facing label, while `step_id` is the durable lineage/resume identity.
  - v2.1 status/report snapshots may expose `bound_inputs`, `workflow_outputs`, and any run-level workflow-boundary `error` object.
  - v2.10 status/report snapshots may expose:
    - `run.error` quarantine context for interrupted provider-session visits
    - `output.provider_session` step summaries including `mode`, `session_id`, `metadata_path`, and `publication_state`
  - v2.2 lowered structured-control nodes appear in snapshots as ordinary top-level entries:
    - branch markers use kind `structured_if_branch`
    - statement join nodes use kind `structured_if_join`
    - join-node `output.error` / `output.artifacts` / `output.debug.structured_if` show selected-branch materialization status
  - v2.6 lowered enum-branching nodes appear in snapshots as ordinary top-level entries:
    - case markers use kind `structured_match_case`
    - statement join nodes use kind `structured_match_join`
    - join-node `output.error` / `output.artifacts` / `output.debug.structured_match` show selected-case materialization status
  - v2.7 structured loop nodes appear in snapshots as ordinary top-level entries with kind `repeat_until`.
    - the loop frame keeps the authored step name
    - `output.artifacts` exposes the latest materialized loop-frame outputs
    - `output.debug.structured_repeat_until` may expose `current_iteration`, `completed_iterations`, `condition_evaluated_for_iteration`, and `last_condition_result`
  - v2.3 status/report snapshots may expose `run.finalization` bookkeeping and render lowered finalization steps as ordinary top-level entries with kind `finally`.
  - When finalization is present, `run.workflow_outputs` stays empty until cleanup completes successfully; failed cleanup reports `workflow_outputs_status: suppressed|failed` in `run.finalization`.
  - v2.5 reusable-call surfaces:
    - outer call steps render as ordinary top-level entries with kind `call`
    - outer call-step results may expose `output.call` metadata including `call_frame_id`, import alias, callee workflow file, bound inputs, export status, and exported-output provenance
    - nested callee execution is persisted under `state.call_frames` without changing the caller-visible outer step key
    - caller-visible exported outputs remain absent until callee body and callee finalization both succeed
    - report/debug surfaces may show secondary provenance for exported call outputs, but the caller-visible producer remains the outer call step

- Reusable-call diagnostics
  - Loader-facing failures should distinguish:
    - unknown import alias
    - caller/callee version mismatch
    - missing required `with:` bindings
    - missing or colliding reusable-workflow write-root bindings
    - source-asset path traversal outside the imported workflow source tree
  - Runtime-facing failures should distinguish:
    - `call_failed` outer-step failures when the callee run fails
    - callee output export contract failures
    - callee finalization failure with exports suppressed
    - call-frame resume/export state when a run is interrupted mid-call

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
