# Run Identity and State (Normative)

- Run identification
  - `run_id` format: `YYYYMMDDTHHMMSSZ-<6char>` (UTC timestamp + random suffix)
  - `RUN_ROOT`: `.orchestrate/runs/${run_id}` under WORKSPACE

- State file schema (authoritative record)
  - `schema_version: "2.0"`
  - `run_id`, `workflow_file`, `workflow_checksum`
  - Timestamps: `started_at`, `updated_at`
  - `status`: `running | completed | failed`
  - `context`: key/value map
  - `bound_inputs`: v2.1+ typed workflow inputs bound before execution starts
  - `workflow_outputs`: v2.1+ typed workflow outputs exported after successful workflow completion
  - `error`: optional run-level error object for workflow-boundary failures such as output export contract violations
  - `steps`: map of step results
  - `for_each`: loop bookkeeping: `items`, `completed_indices`, `current_index`
  - v1.2+ runtime dataflow fields:
    - `artifact_versions`: `{artifact_name: [{version, value, producer, producer_name?, step_index}, ...]}`
    - `artifact_consumes`: `{consumer_identity: {artifact_name: last_consumed_version}}` with optional `__global__` aggregate entry
  - v1.8 control-flow fields:
    - `transition_count`: integer count of routed top-level step-to-step transfers
    - `step_visits`: `{step_name: visit_count}` for top-level non-skipped step entries
  - v2.0 identity fields:
    - `steps.<PresentationKey>.step_id`: durable internal identity for the recorded step result
    - `steps.<PresentationKey>.name`: human-facing display name retained for reports and compatibility views
    - `current_step.step_id`: durable identity for the currently running top-level step
    - `current_step.visit_count`: visit ordinal for the in-flight top-level step visit, when the runtime has already incremented `step_visits`

- Step status semantics
  - Step `status`: `pending | running | completed | failed | skipped`.
  - `when` false → `skipped` with `exit_code: 0` and no process execution.
  - Step results may include `output`, `lines`, `json`, `text`, `error`, `debug`, and `artifacts`.
  - Step results may include `name` and `step_id`; the presentation key in `steps` remains compatibility-oriented, while `step_id` is the durable lineage/resume identity.
  - Step results for top-level steps may include `visit_count`, meaning the visit ordinal of the recorded completed/skipped/failed result stored at that presentation key.
  - Resume uses persisted state only to choose the initial top-level restart point. After the executor reaches that point, repeated visits to the same top-level step name follow normal control flow and are not auto-skipped solely because an earlier visit completed.
  - v1.6 step results may also include normalized `outcome`:
    - `status`: `completed|failed|skipped`
    - `phase`: `pre_execution|execution|post_execution`
    - `class`: normalized failure/success classification (for example `completed`, `assert_failed`, `command_failed`, `provider_failed`, `timeout`, `contract_violation`, `pre_execution_failed`)
    - `retryable`: boolean
  - `artifacts` is a map of typed values parsed from `expected_outputs` and is available at `steps.<Step>.artifacts` when `persist_artifacts_in_state` is not set to `false`.
  - v1.7 `set_scalar` / `increment_scalar` reuse that same `steps.<Step>.artifacts` surface for local produced scalar values; successful publication still advances `artifact_versions` only through `publishes.from`.
  - v1.8 cycle-guard failures use `error.type: "cycle_guard_exceeded"` with `outcome.phase: "pre_execution"` and `outcome.class: "pre_execution_failed"`.
  - Tasks 1-5 of the DSL evolution roadmap were additive under schema `1.1.1`; v2.0 is the explicit stable-ID migration boundary.
  - Resume from pre-v2.0 state is rejected unless a dedicated upgrader is introduced in a later tranche.
  - v2.1 workflow signatures reuse the v2.0 state schema and append `bound_inputs` / `workflow_outputs` as additive fields under the same `schema_version: "2.0"` boundary.

- Output contract failure shape
  - If `expected_outputs` validation fails after a successful execution (`exit_code: 0`), the step is marked failed with:
    - non-zero `exit_code` (currently `2`)
    - `error.type: "contract_violation"`
    - `error.context.violations: []` describing individual contract violations

- Loop state representation
  - Per-iteration indexing: `steps.<LoopName>[i].<StepName>` stores step results for each iteration.
  - These indexed keys are presentation views. v2.0 lineage/freshness bookkeeping uses the qualified `step_id` embedded in each result payload (for example `root.loop_publish#0.produce_in_loop`).

- State integrity
  - Atomic writes: write temp file then rename.
  - Include workflow checksum to detect modifications.
  - On corruption: `resume --repair` attempts recovery from latest valid backup; `resume --force-restart` creates a new run.

- State backups and cleanup
  - When `--backup-state` is enabled or `--debug` is set, copy `state.json` to `state.json.step_<Step>.bak` before each step (keep last 3).
  - `clean --older-than <duration>` removes old run directories (see `cli.md`).

- Logs directory (see `observability.md`)
  - `logs/` contains `orchestrator.log`, `StepName.stdout` (when large or parse error), `StepName.stderr` (when non-empty), and optional debug artifacts.

## State File Schema (example)

The state file (`${RUN_ROOT}/state.json`) is the authoritative record of execution:

```json
{
  "schema_version": "2.0",
  "run_id": "20250115T143022Z-a3f8c2",
  "workflow_file": "workflows/pipeline.yaml",
  "workflow_checksum": "sha256:abcd1234...",
  "started_at": "2025-01-15T14:30:22Z",
  "updated_at": "2025-01-15T14:35:47Z",
  "status": "running",
  "context": { "key": "value" },
  "bound_inputs": {
    "max_cycles": 4
  },
  "workflow_outputs": {},
  "artifact_versions": {
    "execution_log": [
      {
        "version": 1,
        "value": "artifacts/work/latest-execution-log.md",
        "producer": "ExecutePlan",
        "step_index": 2
      }
    ]
  },
  "artifact_consumes": {
    "ReviewImplVsPlan": {
      "execution_log": 1
    },
    "__global__": {
      "execution_log": 1
    }
  },
  "transition_count": 3,
  "step_visits": {
    "ExecutePlan": 1,
    "ReviewPlan": 2
  },
  "steps": {
    "StepName": {
      "status": "completed",
      "name": "StepName",
      "step_id": "root.step_name",
      "exit_code": 0,
      "started_at": "2025-01-15T14:30:23Z",
      "completed_at": "2025-01-15T14:30:25Z",
      "duration_ms": 2145,
      "output": "...",
      "truncated": false,
      "debug": {
        "command": ["echo", "hello"],
        "cwd": "/workspace",
        "env_count": 42
      },
      "artifacts": {
        "plan_path": "docs/plans/plan-a.md",
        "review_score": 82
      }
    }
  },
  "for_each": {
    "ProcessItems": {
      "items": ["file1.txt", "file2.txt"],
      "completed_indices": [0],
      "current_index": 1
    }
  }
}
```

## State Integrity and Recovery

Corruption detection and backups:
- Include `workflow_checksum` to detect workflow modifications.
- Atomic updates: write to a temp file then rename.
- When `--backup-state` or `--debug` is enabled, before each step copy `state.json` to `state.json.step_<Step>.bak` and keep the last 3 backups.

Recovery mechanisms:
```bash
# Resume with state validation
orchestrate resume <run_id>

# Force restart ignoring corrupted state
orchestrate resume <run_id> --force-restart

# Attempt repair of corrupted state
orchestrate resume <run_id> --repair

# Archive old runs
orchestrate clean --older-than 7d
```

Schema boundary note:
- Post-v2.0 runtimes reject resume from pre-v2.0 state rather than silently remapping old name-keyed lineage/freshness data.
- When a resumed run reaches a terminal state, `current_step` must be cleared.
