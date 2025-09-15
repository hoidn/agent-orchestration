# Versioning and Migration (Normative)

- Tracks
  - DSL version: governs available fields and validation behavior.
  - State schema version: `schema_version` stored in `state.json`.

- v1.1 baseline
  - Core DSL: steps with provider/command/wait_for, conditionals, for_each.
  - No dependency injection.

- v1.1.1 additions (dependency injection)
  - `depends_on.inject`: shorthand `true` or object form `{ mode, instruction?, position? }`.
  - Validation is strict: workflows using injection MUST set `version: "1.1.1"` (or higher).
  - Migration from 1.1 to 1.1.1
    - Before: duplicate file lists in prompt and depends_on.
    - After: declare files once in `depends_on`; orchestrator injects into the prompt.
    - Benefits: DRY, glob support, maintainability, generic prompts.

- v1.2 planned (declarative per-item lifecycle)
  - `for_each.on_item_complete` with `success.move_to` / `failure.move_to` directories.
  - Version-gated: requires `version: "1.2"` or higher; otherwise validation error.
  - See acceptance items for timing, path safety, variable substitution, idempotency on resume.

## Declarative Task Lifecycle for for_each (v1.2)

Status: Planned future feature. Opt‑in, version‑gated. Does not change MVP defaults.

Version gating:
- Requires `version: "1.2"` or higher. Using `on_item_complete` at lower versions is a validation error (exit code 2).

Purpose:
- Reduce boilerplate by declaratively moving a per‑item task file after an iteration completes, based on item success/failure.

Schema (inside `for_each`):
```yaml
on_item_complete?:
  success?:
    move_to?: string   # Destination directory under WORKSPACE; variables allowed
  failure?:
    move_to?: string   # Destination directory under WORKSPACE; variables allowed
```

Semantics:
- Trigger timing: Evaluated once per item after its `steps` finish.
- Success: All executed steps ended with `exit_code: 0` after retries, and no `goto` escaped the loop before finishing.
- Failure: Any step failed after retries, or a timeout (124) remained, or a `goto` jumped outside the loop/`_end` before finishing.
- Recovery: If a step fails but is recovered by `on.failure` and the item completes, the item counts as success.
- Variable substitution: `${run.*}`, `${loop.*}`, `${context.*}`, `${steps.*}` are supported in `move_to`.
- Path safety: `move_to` follows the same rules as other paths and must resolve within WORKSPACE. Absolute/parent‑escape paths are rejected.
- Missing source: If the original item path no longer exists when applying the action, record a lifecycle error; do not change the item's result.
- Idempotency/resume: Lifecycle is idempotent; on resume, previously applied actions are not repeated.

State recording (per iteration):
```json
{
  "lifecycle": {
    "result": "success|failure",
    "action": "move",
    "from": "inbox/engineer/task_001.task",
    "to": "processed/20250115T143022Z/task_001.task",
    "action_applied": true,
    "error": null
  }
}
```

Example:
```yaml
version: "1.2"
steps:
  - name: CheckEngineerInbox
    command: ["find", "inbox/engineer", "-name", "*.task", "-type", "f"]
    output_capture: "lines"

  - name: ProcessEngineerTasks
    for_each:
      items_from: "steps.CheckEngineerInbox.lines"
      as: task_file
      on_item_complete:
        success:
          move_to: "processed/${run.timestamp_utc}"
        failure:
          move_to: "failed/${run.timestamp_utc}"
      steps:
        - name: Implement
          provider: "claude"
          input_file: "${task_file}"

        - name: CreateQATask
          command: ["bash", "-lc", "echo 'Review ${task_file}' > inbox/qa/$(basename \"${task_file}\").task"]

        - name: WaitForQAVerdict
          wait_for:
            glob: "inbox/qa/results/$(basename \"${task_file}\").json"
            timeout_sec: 3600

        - name: AssertQAApproved
          command: ["bash", "-lc", "jq -e '.approved == true' inbox/qa/results/$(basename \"${task_file}\").json >/dev/null"]
          on:
            failure: { goto: _end }  # Forces item failure; lifecycle will move to failed/
```

Planned acceptance:
1. Success path moves to `processed/…`; failure path moves to `failed/…`.
2. Failure recovered by `on.failure` and item completes → success move.
3. `goto` escaping the loop triggers failure move.
4. Unsafe `move_to` (outside WORKSPACE) rejected at validation.
5. Variable substitution in `move_to` resolves correctly.
6. Idempotent on resume; no double move.
7. Missing source logs lifecycle error; item result unchanged.

- v1.3 planned (JSON output validation)
  - For steps with `output_capture: json`: optional `output_schema` and `output_require[...]` assertions.
  - Incompatible with `allow_parse_error: true`.
  - Version-gated: requires `version: "1.3"` or higher.

## Version Gating Summary

| DSL version | Key features enabled | Notes |
| --- | --- | --- |
| 1.1 | Baseline DSL; providers (argv/stdin), `wait_for`, `depends_on` (required/optional), `when` (equals/exists/not_exists), retries/timeouts, strict path safety | State schema initially 1.1.1 (separate track). Unknown DSL fields rejected. |
| 1.1.1 | `depends_on.inject` (list/content/none), injection truncation recording | Workflows must declare `version: "1.1.1"` to use `inject`. |
| 1.2 (planned) | `for_each.on_item_complete` declarative per‑item lifecycle (move_to on success/failure) | Opt‑in; path safety and substitution apply. State gains per‑iteration `lifecycle` fields; state schema will bump accordingly when released. |
| 1.3 (planned) | JSON output validation: `output_schema`, `output_require` for steps with `output_capture: json` | Enforces schema and simple assertions; incompatible with `allow_parse_error: true`. |
