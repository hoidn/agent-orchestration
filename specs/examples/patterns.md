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

## Templating Prompts (Informative)

The orchestrator does not substitute variables inside file contents (see specs/variables.md). To generate a concrete prompt from a template, create it in a prior step, then reference the generated file via `input_file`.

### Option A: envsubst for `$VAR`/`${VAR}` tokens

Template (prompts/template.md):
```
Hello $AUTHOR,
Build $BUILD_ID for project $PROJECT.
```

Workflow steps:
```yaml
steps:
  - name: PreparePrompt
    command:
      - bash
      - -lc
      - |
        set -euo pipefail
        export PROJECT='${context.project}' BUILD_ID='${context.build_id}' AUTHOR='${context.author}'
        mkdir -p temp
        envsubst '$PROJECT $BUILD_ID $AUTHOR' < prompts/template.md > temp/prompt_${context.build_id}.md

  - name: AskClaude
    provider: claude
    provider_params: { model: "claude-sonnet-4-20250514" }
    input_file: "temp/prompt_${context.build_id}.md"
    output_capture: text
```

Notes:
- Passing an explicit list to envsubst (e.g., `$PROJECT $BUILD_ID $AUTHOR`) avoids accidental replacement of other `$…` tokens.
- Keep prompts/ on disk generic; generate concrete prompts in temp/.

### Option B: Tiny reusable script (Python string.Template)

Script (scripts/subst.py):
```python
#!/usr/bin/env python3
import argparse, os, sys
from string import Template

p = argparse.ArgumentParser()
p.add_argument("--in", dest="src", required=True)
p.add_argument("--out", dest="dst", required=True)
p.add_argument("kv", nargs="*")  # KEY=VALUE pairs
args = p.parse_args()

vars = {}
for pair in args.kv:
    if "=" not in pair:
        sys.exit(f"Invalid KV: {pair}")
    k,v = pair.split("=",1)
    vars[k] = v

with open(args.src, "r", encoding="utf-8") as f:
    text = f.read()

out = Template(text).safe_substitute(vars)
os.makedirs(os.path.dirname(args.dst), exist_ok=True)
with open(args.dst, "w", encoding="utf-8") as f:
    f.write(out)
```

Workflow steps:
```yaml
steps:
  - name: PreparePrompt
    command:
      - python3
      - scripts/subst.py
      - --in
      - prompts/template.md
      - --out
      - temp/prompt_${context.build_id}.md
      - PROJECT=${context.project}
      - BUILD_ID=${context.build_id}
      - AUTHOR=${context.author}

  - name: AskClaude
    provider: claude
    provider_params: { model: "claude-sonnet-4-20250514" }
    input_file: "temp/prompt_${context.build_id}.md"
    output_capture: text
```

Why this pattern:
- Complies with literal file semantics (no engine substitution in file contents).
- Keeps templates reusable; moves concrete data binding to a pre-step.
- Works with argv and stdin providers (Codex reads the prompt from stdin; the pattern is the same).

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
