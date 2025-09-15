# Prompt Management and QA Patterns (Informative)

## Prompt Management Patterns

Directory purpose clarification:
- `prompts/`: Static, reusable prompt templates created by workflow authors before execution
- `inbox/`: Dynamic task files for agent coordination, created during workflow execution
- `temp/`: Temporary files for dynamic prompt composition and intermediate processing

Multi-agent coordination pattern:

```yaml
steps:
  # Step 1: Agent A creates artifacts
  - name: ArchitectDesign
    agent: "architect"
    provider: "claude"
    input_file: "prompts/architect/design.md"
    output_file: "artifacts/architect/log.md"

  # Step 2: Drop a small queue task (atomic write)
  - name: PrepareEngineerTask
    command: ["bash", "-lc", "printf 'Implement the architecture.' > inbox/engineer/task_${run.timestamp_utc}.tmp && mv inbox/engineer/task_${run.timestamp_utc}.tmp inbox/engineer/task_${run.timestamp_utc}.task"]

  # Step 3: Agent B processes task; inputs declared and injected
  - name: EngineerImplement
    agent: "engineer"
    provider: "claude"
    input_file: "inbox/engineer/task_${run.timestamp_utc}.task"
    output_file: "artifacts/engineer/impl_log.md"
    depends_on:
      required:
        - "artifacts/architect/system_design.md"
        - "artifacts/architect/api_spec.md"
      inject: true
```

Best practices:
- Keep static templates generic; build dynamic prompts at runtime.
- Use `inbox/` for agent work queues; keep lifecycle explicit in steps.
- Prefer `depends_on` + `inject` over shell-concatenated prompts.

## QA Verdict Pattern (non‑normative)

- Prompt and schema:
  - `prompts/qa/review.md` — instruct QA agent to output only a single JSON object to STDOUT (or to write to a verdict file); include guidance on logging explanations to `artifacts/qa/logs/`.
  - `schemas/qa_verdict.schema.json` — JSON Schema defining the verdict shape.
- Usage patterns:
  - STDOUT JSON gate: Set `output_capture: json` on the QA step and add an assertion step to gate success/failure deterministically.
  - Verdict file gate: Instruct the agent to write JSON to `inbox/qa/results/<task_id>.json`, then `wait_for` and assert via `jq`.

- Examples:
  - `workflows/examples/qa_gating_stdout.yaml`
  - `workflows/examples/qa_gating_verdict_file.yaml`

Notes:
- These patterns keep control flow deterministic without parsing prose. They complement (but do not depend on) the planned v1.3 hooks (`output_schema`, `output_require`).

