# E2E Examples (Informative)

Status: Informative. These examples illustrate realistic end-to-end flows that touch multiple spec areas. They are not normative; the authoritative contracts live in the individual spec modules under `specs/`.

## 1) QA Gating via STDOUT JSON

Relevant specs: `io.md#output-capture`, `providers.md`, `dsl.md#control-flow`, `observability.md` (status JSON optional)

```yaml
version: "1.1"
name: "qa_gating_stdout"

steps:
  - name: ImplementFeature
    provider: "claude"
    input_file: "prompts/engineer/generic_implement.md"
    output_file: "artifacts/engineer/impl_log.md"

  - name: QAVerdict
    provider: "claude"
    input_file: "prompts/qa/review.md"     # prompt instructs: output ONLY a single JSON object to STDOUT
    output_capture: "json"                  # gate on JSON parse
    allow_parse_error: false                # parse failure = step failure

  - name: AssertApproved
    command: ["bash", "-lc", "jq -e '.approved == true' <<< '${steps.QAVerdict.output}' >/dev/null"]
    on:
      failure: { goto: _end }
```

Notes:
- Ensures deterministic gating without parsing prose.
- Maps to acceptance around JSON capture, parse errors, and control flow.

## 2) Multi-Agent Inbox with Wait-For

Relevant specs: `queue.md` (wait_for, inbox conventions), `dsl.md` (for_each), `dependencies.md` (inject), `security.md` (path safety)

```yaml
version: "1.1.1"
name: "multi_agent_inbox_e2e"

providers:
  claude:
    command: ["claude", "-p", "${PROMPT}", "--model", "${model}"]
    defaults: { model: "claude-sonnet-4-20250514" }

steps:
  - name: ArchitectDesign
    agent: "architect"
    provider: "claude"
    input_file: "prompts/architect/design_system.md"
    output_file: "artifacts/architect/design_log.md"

  - name: CreateEngineerTask
    command: ["bash", "-lc", "echo 'Implement the architecture' > inbox/engineer/task_001.tmp && mv inbox/engineer/task_001.tmp inbox/engineer/task_001.task"]

  - name: WaitForEngineerTask
    wait_for:
      glob: "inbox/engineer/*.task"
      timeout_sec: 300
      poll_ms: 500
      min_count: 1

  - name: ImplementWithClaude
    agent: "engineer"
    provider: "claude"
    input_file: "prompts/engineer/generic_implement.md"
    output_file: "artifacts/engineer/impl_log.md"
    depends_on:
      required:
        - "artifacts/architect/*.md"
      inject: true

  - name: MoveToProcessed
    command: ["bash", "-lc", "mkdir -p processed/${run.timestamp_utc} && mv inbox/engineer/*.task processed/${run.timestamp_utc}/"]
```

Notes:
- Demonstrates file-queue conventions, blocking wait, and prompt injection.
- Keep per-item lifecycle explicit (moves are authored in steps).

