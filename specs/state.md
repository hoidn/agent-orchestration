# Run Identity and State (Normative)

- Run identification
  - `run_id` format: `YYYYMMDDTHHMMSSZ-<6char>` (UTC timestamp + random suffix)
  - `RUN_ROOT`: `.orchestrate/runs/${run_id}` under WORKSPACE

- State file schema (authoritative record)
  - `schema_version: "2.1"`
  - `run_id`, `workflow_file`, `workflow_checksum`
  - Timestamps: `started_at`, `updated_at`
  - `status`: `running | completed | failed`
  - `context`: key/value map
  - `bound_inputs`: v2.1+ typed workflow inputs bound before execution starts
  - `workflow_outputs`: v2.1+ typed workflow outputs exported after successful workflow completion
  - `finalization`: v2.3+ workflow finalization bookkeeping (`status`, `body_status`, `current_index`, `completed_indices`, `workflow_outputs_status`, optional `failure`)
  - `error`: optional run-level error object for workflow-boundary failures such as output export contract violations
    - v2.10 also uses this surface for provider-session quarantine failures (`type: "provider_session_interrupted_visit_quarantined"`)
  - `steps`: map of step results
  - `for_each`: loop bookkeeping: `items`, `completed_indices`, `current_index`
  - `repeat_until`: loop bookkeeping: `current_iteration`, `completed_iterations`, `condition_evaluated_for_iteration`, `last_condition_result`
  - v2.5+ reusable-call fields:
    - `call_frames`: call-frame records keyed by durable `call_frame_id`, with caller step identity, import alias, callee workflow file, bound inputs, body/finalization/export status, current nested execution position, and nested call-frame-local state
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
  - v2.10 provider-session observability:
    - canonical visit metadata records live under `.orchestrate/runs/<run_id>/provider_sessions/<step_id>__v<visit>.json`
    - stable masked transport spools live under `.orchestrate/runs/<run_id>/provider_sessions/<step_id>__v<visit>.transport.log`
    - successful fresh session steps may expose `steps.<Step>.debug.provider_session = {mode, session_id, metadata_path, publication_state, ...}`
  - v2.2 structured-control additions:
    - lowered branch markers and lowered branch-body steps are recorded as ordinary top-level step entries under presentation keys such as `RouteReview.then` and `RouteReview.then.WriteApproved`
    - the lowered join node keeps the authored statement presentation key (for example `RouteReview`) and materializes branch outputs there
  - v2.6 structured enum-branching additions:
    - lowered case markers and lowered case-body steps are recorded as ordinary top-level step entries under presentation keys such as `RouteDecision.APPROVE` and `RouteDecision.APPROVE.WriteApprovedAction`
    - the lowered join node keeps the authored statement presentation key (for example `RouteDecision`) and materializes case outputs there
  - v2.7 structured looping additions:
    - `steps.<RepeatUntilStatement>` stores the loop-frame result and latest materialized loop outputs
    - `steps.<RepeatUntilStatement>[i].<StepName>` stores one iteration's nested step result using qualified per-iteration `step_id` ancestry
    - `repeat_until.<RepeatUntilStatement>` persists `current_iteration`, `completed_iterations`, `condition_evaluated_for_iteration`, and `last_condition_result` for resume
  - v2.3 finalization additions:
    - lowered finalization steps are recorded as ordinary top-level step entries under presentation keys such as `finally.ReleaseLock`
    - `finalization.workflow_outputs_status` records whether workflow outputs are `pending`, `completed`, `failed`, `suppressed`, or `not_configured`
    - workflow outputs remain `{}` until finalization succeeds
  - v2.5 reusable-call additions:
    - `call_frames` persist nested execution state for inline `call` steps under schema `2.1`.
    - callee-private `artifact_versions` / `artifact_consumes` remain inside the call-frame-local nested state rather than leaking bare artifact names into the caller-global ledger.
    - caller-visible exported output provenance remains attached to the outer call step result and any published outer-step lineage entries.

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
  - v2.10 fresh provider-session steps publish their runtime-owned session handle on that same `steps.<Step>.artifacts.<publish_artifact>` surface only after the exact visit's atomic state finalization succeeds.
  - v1.7 `set_scalar` / `increment_scalar` reuse that same `steps.<Step>.artifacts` surface for local produced scalar values; successful publication still advances `artifact_versions` only through `publishes.from`.
  - v1.8 cycle-guard failures use `error.type: "cycle_guard_exceeded"` with `outcome.phase: "pre_execution"` and `outcome.class: "pre_execution_failed"`.
  - Tasks 1-5 of the DSL evolution roadmap were additive under schema `1.1.1`; v2.0 is the explicit stable-ID migration boundary.
  - Resume from pre-v2.0 state is rejected unless a dedicated upgrader is introduced in a later tranche.
  - v2.1 workflow signatures append `bound_inputs` / `workflow_outputs`; the later v2.5 reusable-call tranche moves the top-level schema to `2.1`.
  - v2.2 structured `if/else` also reuses schema `2.0`; lowered branch markers/join metadata are additive `steps.*` payload fields rather than a new schema boundary.
  - v2.6 structured `match` also reuses schema `2.0`; lowered case markers/join metadata are additive `steps.*` payload fields rather than a new schema boundary.
  - v2.3 structured finalization also reuses schema `2.0`; finalization bookkeeping and lowered `finally.*` step entries are additive fields.
  - v2.5 reusable `call` is the schema boundary that moves state to `2.1`, because bare artifact-name ledgers cannot preserve callee-private lineage or freshness safely.
  - v2.7 `repeat_until` extends schema `2.1` additively; loop-frame bookkeeping lives under the new top-level `repeat_until` map.

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
  - v2.10 interrupted session-enabled visits are quarantined instead of replayed on resume; quarantine clears the matching `current_step`, preserves older same-name terminal results, and records a durable run-level error that points to the canonical metadata and transport-spool paths.

- State backups and cleanup
  - When `--backup-state` is enabled or `--debug` is set, copy `state.json` to `state.json.step_<Step>.bak` before each step (keep last 3).
  - `clean --older-than <duration>` removes old run directories (see `cli.md`).

- Logs directory (see `observability.md`)
  - `logs/` contains `orchestrator.log`, `StepName.stdout` (when large or parse error), `StepName.stderr` (when non-empty), and optional debug artifacts.

## Reusable-Call State Contract (v2.5)

- Caller-visible exports
  - Declared callee outputs materialize only on the outer call step as `steps.<CallStep>.artifacts.<name>`.
  - When an exported call output enters caller-visible lineage, the outer call step is the external producer identity.
  - The callee-internal `outputs[*].from` origin is preserved as secondary provenance/debug metadata and does not masquerade as the caller-visible producer.

- Callee-private lineage
  - Callee-private artifact names must not occupy bare names in the caller-global artifact ledger.
  - Internal publish/consume state lives inside the call-frame-local state snapshot instead of the caller-global ledgers.
  - `since_last_consume` freshness inside a call frame is therefore enforced against the callee-private ledgers persisted under that frame.

- Resume boundary
  - Because call frames add new durable lineage and resume keys, resume from pre-`schema_version: "2.1"` state is rejected unless a tested upgrader ships with the same tranche.

## State File Schema (example)

The state file (`${RUN_ROOT}/state.json`) is the authoritative record of execution:

```json
{
  "schema_version": "2.1",
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
  },
  "repeat_until": {
    "ReviewLoop": {
      "current_iteration": 2,
      "completed_iterations": [0, 1],
      "condition_evaluated_for_iteration": 1,
      "last_condition_result": false
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
