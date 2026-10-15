# Example: Debugging Failed Runs (Informative)

Status: **Historical example — YAML execution retired.** The original body
below is preserved to interpret versioned schemas, validation and old run
records; its original commands and present tense are not current launch
instructions. Use the [current `.orc` drafting guide](../../docs/lisp_workflow_drafting_guide.md)
and [public lifecycle recipe](../../docs/lisp_workflow_drafting_guide.md#a-complete-235-recipe-compile-run-resume-report-invalidate).
Current admission, recovery and reader behavior remain owned by
[CLI](../cli.md) and [State](../state.md).

```yaml
version: "1.1"
name: "debugging_example"

steps:
  - name: ProcessWithDebug
    command: ["python", "process.py"]
    env:
      DEBUG: "0"
    on:
      failure:
        goto: DiagnoseFailure
        
  - name: DiagnoseFailure
    command: ["bash", "-c", "
      echo 'Checking failure context...' &&
      cat ${run.root}/logs/ProcessWithDebug.stderr &&
      jq '.steps.ProcessWithDebug.error' ${run.root}/state.json
    "]
```

## Investigating Failures

```bash
# Run with debugging
orchestrate run workflow.yaml --debug

# On failure, check logs
cat .orchestrate/runs/latest/logs/orchestrator.log

# Examine state
jq '.steps | map_values({status, exit_code, error})' \
  .orchestrate/runs/latest/state.json

# Resume after fixing issue
orchestrate resume 20250115T143022Z-a3f8c2 --debug
```

