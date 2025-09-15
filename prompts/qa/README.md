# QA Review Prompts

Reusable assets for QA agents that must produce deterministic, machine‑parsable verdicts.

## Output Contracts
- STDOUT JSON (fast path): Output ONLY a single JSON object to STDOUT. No prose, no code fences. First non‑whitespace must be `{`, last must be `}`. The workflow will parse it with `output_capture: json` and assert fields.
- Verdict file (robust path): Print nothing to STDOUT. Write the JSON verdict to `inbox/qa/results/<task_id>.json`. The workflow will `wait_for` the file and assert with `jq`.

## Files
- `prompts/qa/review.md`: Template prompt that:
  - States the JSON‑only STDOUT contract and defers explanations to `artifacts/qa/logs/`.
  - Relies on schema injection via `depends_on.inject: content`.
- `schemas/qa_verdict.schema.json`: JSON Schema defining the verdict shape.

## Usage Patterns

1) STDOUT JSON gate
```yaml
- name: QAReview
  provider: "claude"
  input_file: "prompts/qa/review.md"
  output_capture: json
  depends_on:
    required: ["schemas/qa_verdict.schema.json"]
    inject:
      mode: content
      instruction: "Conform to this JSON Schema. Output ONLY JSON to STDOUT."
- name: AssertApproved
  command: ["bash","-lc","test \"${steps.QAReview.json.approved}\" = \"true\""]
```

2) Verdict file gate
```yaml
- name: QAReview
  provider: "claude"
  input_file: "prompts/qa/review.md"
  output_capture: text  # ignore stdout
  depends_on:
    required: ["schemas/qa_verdict.schema.json"]
    inject:
      mode: content
      instruction: "Conform to this JSON Schema. Write ONLY the verdict to inbox/qa/results/${context.task_id}.json"
- name: WaitForVerdict
  wait_for:
    glob: "inbox/qa/results/${context.task_id}.json"
    timeout_sec: 3600
- name: AssertApproved
  command: ["bash","-lc","jq -e '.approved == true' inbox/qa/results/${context.task_id}.json >/dev/null"]
```

## Provider Tips
- Prefer `input_mode: stdin` providers for long prompts; avoid `${PROMPT}` in stdin mode per spec.
- Keep `allow_parse_error: false` for JSON steps to fail fast on non‑JSON outputs.
- If using argv providers, keep prompts concise to avoid argv length limits; otherwise use stdin mode.

## Correlation & Logging
- Use a stable `task_id` and file basenames to correlate verdicts to source tasks.
- Write human‑readable reasoning to `artifacts/qa/logs/<task_id>.md` (the orchestrator does not consume this for control flow).
