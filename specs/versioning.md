# Versioning and Migration (Normative)

- Tracks
  - DSL version: governs available fields and validation behavior.
  - State schema version: `schema_version` stored in `state.json`.

- v1.1 baseline
  - Core DSL: steps with provider/command/wait_for, conditionals, for_each.
  - No dependency injection.

- v1.1.1 additions (dependency injection)
  - `depends_on.inject`: shorthand `true` or object form `{ mode, instruction?, position? }`.
  - Validation is strict: workflows using injection MUST set `version: "1.1.1"` or any later supported DSL version.
  - Migration from 1.1 to 1.1.1
    - Before: duplicate file lists in prompt and depends_on.
    - After: declare files once in `depends_on`; orchestrator injects into the prompt.
    - Benefits: DRY, glob support, maintainability, generic prompts.

- v1.2 additions (artifact dataflow contracts)
  - Top-level `artifacts` registry with `kind: relpath|scalar` contracts.
    - `relpath` (default) retains canonical pointer-file materialization.
    - `scalar` supports typed values (`enum|integer|float|bool`) without pointer-file indirection.
  - Step-level `publishes` and `consumes` for producer/consumer linkage.
  - Provider prompt convenience controls for consume dataflow:
    - `inject_consumes` (default true)
    - `consumes_injection_position` (`prepend|append`, default `prepend`)
    - `prompt_consumes` (optional subset of consumes to inject into prompt)
  - Runtime enforcement:
    - publication ledger in state (`artifact_versions`)
    - consume preflight (`latest_successful`) with optional freshness (`since_last_consume`)
    - deterministic contract failures (`exit_code: 2`, `error.type: "contract_violation"`).

- v1.3 additions (JSON-bundled deterministic I/O)
  - Step-level `output_bundle` allows one JSON file to publish multiple deterministic artifacts with typed validation.
  - Step-level `consume_bundle` writes resolved consumes into one JSON file after consume preflight.
  - `publishes.from` may reference either `expected_outputs.name` or `output_bundle.fields[*].name`.
  - Existing v1.2 behavior remains valid; relpath consume pointer materialization still applies in v1.3.
  - Recommended workflow policy:
    - Heavy execution/fix steps: keep flexible (`output_capture: text|lines`), minimal deterministic outputs.
    - Assessment/review/gate steps: keep strict (`output_capture: json`, `allow_parse_error: false`), publish decision artifacts.
    - Control flow should branch on strict published artifacts, not raw prose logs.

- v1.4 additions (read-only consume pointer semantics)
  - Relpath consume preflight no longer mutates registry pointer files.
  - Consumed values continue to resolve through runtime state (`_resolved_consumes`) and optional `consume_bundle`.
  - Backward compatibility: v1.2/v1.3 workflows retain legacy pointer-materialization consume behavior.
  - Migration recommendation for command steps: read consumed artifact values from `consume_bundle` JSON rather than relying on consume-time pointer rewrites.

- v1.5 additions (first-class gates)
  - Step-level `assert` becomes a first-class execution form.
  - `assert` reuses the legacy `equals|exists|not_exists` condition surface and is exclusive with `provider|command|wait_for|for_each`.
  - False assertions fail with `exit_code: 3` and `error.type: "assert_failed"`.
  - Assertion failure remains observable to normal `on.failure.goto` routing.

- v1.6 additions (typed predicates and normalized outcomes)
  - `when` and `assert` accept typed predicates:
    - `artifact_bool`
    - `compare` with `eq|ne|lt|lte|gt|gte`
    - `all_of|any_of|not`
  - Typed predicates use structured `ref:` operands and do not reuse legacy `${...}` string interpolation.
  - Initial structured refs are limited to `root.steps.<Step>...` and reject bare `steps.`, `self.`, `parent.`, and untyped `context.*`.
  - Step results gain normalized `outcome.{status,phase,class,retryable}` fields for observable results.
  - This tranche remains on state schema `1.1.1`; the added `outcome` object is an additive field under existing step results.

- v1.7 additions (scalar bookkeeping runtime primitive)
  - Step-level `set_scalar` emits one declared scalar artifact as a local step result without shelling out.
  - Step-level `increment_scalar` reads the latest published version of the same declared scalar artifact, adds a numeric literal, and emits the updated local step artifact.
  - Both forms are exclusive with `provider|command|wait_for|assert|for_each`.
  - Publication still happens only through `publishes.from`; scalar bookkeeping does not mutate the top-level artifact ledger directly.
  - This tranche remains on state schema `1.1.1`; local scalar artifacts reuse the existing `steps.<Step>.artifacts` and `artifact_versions` surfaces.

- v1.8 additions (cycle guards)
  - Workflow-level `max_transitions` bounds routed transfers between settled top-level steps.
  - Step-level `max_visits` bounds top-level non-skipped step entries after `when` evaluation.
  - Guard failures use `error.type: "cycle_guard_exceeded"` and fail the target step in pre-execution state.
  - Guard failures stop the run even when the guarded step declares `on.failure.goto` and even when CLI `--on-error continue` is set.
  - `transition_count` and `step_visits` persist under state schema `1.1.1`; skipped steps do not consume visit budget and internal retries do not consume extra visits.
  - The first tranche rejects nested/`for_each` `max_visits` usage until stable internal IDs land.

- v2.0 additions (scoped refs and stable internal step ids)
  - Steps may declare an authored stable `id` distinct from display `name`.
  - The loader assigns internal `step_id` values to every step; authored ids stabilize those values across sibling insertion, while compiler-generated ids are only checksum-stable.
  - Typed predicates extend structured refs to `self.steps.<Step>...` and `parent.steps.<Step>...`.
  - State schema moves to `schema_version: "2.0"` and persists `step_id` on step/current-step records.
  - Artifact lineage/freshness bookkeeping moves to qualified internal identities, including per-iteration `for_each` producer/consumer keys.
  - Resume from pre-v2.0 state is rejected unless a future tranche ships an explicit upgrader.

- v2.1 additions (workflow signatures)
  - Top-level `inputs` and `outputs` declare typed workflow-boundary contracts without pointer-file semantics.
  - CLI `run` supports `--input name=value` and `--input-file <json>` binding for top-level workflow inputs.
  - Successful binding is exposed inside the workflow through `${inputs.<name>}` and typed `ref: inputs.<name>`.
  - Successful workflow completion may export `workflow_outputs` by validating each declared `outputs.<name>.from` binding against the same typed contract family.
  - This tranche remains on state schema `2.0`; `bound_inputs` and `workflow_outputs` are additive top-level state fields.

- v2.2 additions (structured `if/else`)
  - Top-level steps may use structured `if` / `then` / `else` instead of raw `goto` diamonds.
  - `if` reuses the existing condition surface (`equals|exists|not_exists` or typed predicates).
  - `then` and `else` accept either a bare `Step[]` list or an object with:
    - optional stable `id`
    - required `steps`
    - required `outputs` for this tranche when statement outputs are exposed downstream
  - Branch-local steps are not addressable from the root workflow scope; downstream refs must target the statement node itself.
  - Branch outputs are materialized onto the statement node and become available at `root.steps.<Statement>.artifacts.<name>`.
  - The loader lowers the authored statement into stable branch markers, lowered branch-body steps, and a join node whose `step_id` derives from the authored statement/branch ancestry.
  - The first tranche is conservative:
    - only top-level structured `if/else` is accepted
    - `goto` / `_end` routing inside branch steps is rejected
    - state schema remains `2.0`; lowered-node metadata is additive under existing step results

- v2.3 additions (structured finalization)
  - Workflows may declare a top-level `finally` block as either `Step[]` or `{ id?, steps: Step[] }`.
  - Finalization steps are lowered into stable top-level execution nodes under `finally.<StepName>` presentation keys and `root.finally.<block-id-or-finally>.*` durable ancestry.
  - Finalization runs once after the workflow body settles on either success or failure.
  - Resume restarts from the first unfinished finalization step instead of replaying completed cleanup.
  - When the workflow body succeeds and finalization fails, the run fails with `error.type: "finalization_failed"`.
  - When the workflow body already failed and finalization also fails, the original body failure remains primary and the finalization failure is recorded as secondary diagnostic state under `finalization.failure`.
  - Workflow `outputs` remain withheld until finalization succeeds and are suppressed on finalization failure.
  - This tranche remains on state schema `2.0`; `finalization` bookkeeping and lowered cleanup-step metadata are additive top-level fields.

- v2.4 contract boundary (reusable-call docs lock; not executable by itself)
  - Reserves the future reusable-workflow path taxonomy before runtime support lands:
    - workflow-source-relative `imports`, nested imports, `asset_file`, and `asset_depends_on`
    - workspace-relative runtime paths unchanged for `input_file`, `depends_on`, `output_file`, deterministic relpath outputs, and bundle paths
  - Locks the first `call` tranche as inline and non-isolating.
  - Requires reusable workflows to surface DSL-managed write roots as typed `relpath` inputs and requires call sites to bind distinct values where multiple invocations could alias the same managed paths.
  - Locks the first-tranche same-version caller/callee rule and callee-private `providers` / `artifacts` / `context` defaults.
  - Schedules a state-schema bump for Task 11 because the current bare artifact-name ledger cannot represent call-scoped internal lineage and freshness safely.
  - Current loader/runtime support still stops at the implemented v2.3 surface; `v2.4` is a contract boundary, not an already-executable workflow version.

- v2.5 additions (imports + `call`)
  - Top-level `imports` plus step-level `call` / typed `with:` binding.
  - Only declared callee outputs cross the boundary and materialize on the outer call step.
  - State schema moves to `schema_version: "2.1"` with persisted `call_frames`, deferred export state, and preserved internal provenance for exported outputs.
  - Callee-private artifact lineage and freshness stay inside the call-frame-local nested state rather than the caller-global ledgers.

- v2.6 additions (structured `match`)
  - Top-level steps may use structured `match` over a typed enum ref.
  - `match.cases` must cover every allowed enum value on the selected artifact or input.
  - Cases reuse the same block/output pattern as v2.2 `if/else`: `Step[]` or `{ id?, steps, outputs }`.
  - Case-local steps stay scoped to the selected case; downstream refs target the statement node outputs.
  - This tranche remains on state schema `2.0`; lowered case markers/join metadata are additive `steps.*` payload fields.

- v2.7 additions (post-test `repeat_until`)
  - Top-level steps may use structured `repeat_until` with `{ id?, outputs, condition, max_iterations, steps }`.
  - Iteration `0` always executes once; `condition` is evaluated only after each completed iteration.
  - `condition` reads loop-frame outputs through `self.outputs.<name>` and must not read inner multi-visit body steps directly.
  - Loop-frame outputs materialize on the authored step itself, so downstream refs target `root.steps.<Statement>.artifacts.<name>`.
  - Resume persists `repeat_until` iteration bookkeeping (`current_iteration`, `completed_iterations`, `condition_evaluated_for_iteration`, `last_condition_result`) under state schema `2.1`.
  - First tranche remains conservative: body steps reject `goto`, nested `for_each`, and nested `repeat_until`.
  - Direct nested `call`, `match`, and `if/else` bodies are allowed and lower into loop-local executable nodes that keep body-local structured refs on `self.steps.*` and outer lexical refs on `parent.steps.*`.

- v2.8 additions (score-aware gates)
  - Typed predicates also accept `score: { ref, gt?, gte?, lt?, lte? }` for benchmark-style threshold and band checks.
  - `score` remains predicate sugar over numeric typed refs; it does not add a separate routing or decision surface.
  - `score` requires a numeric structured ref, at least one bound, and rejects mixed `gt`+`gte` or `lt`+`lte` declarations.

- v2.9 additions (authoring linting and normalization)
  - CLI dry-run and report surfaces may emit advisory lint warnings without turning them into validation failures.
  - Initial warnings cover shell gates that should become `assert`, stringly `when.equals` routing that should become typed predicates, raw `goto` diamonds that should become structured control, and imported/exported output-name collisions.
  - Advisory lint also warns when top-level workflow-boundary `inputs` or `outputs` redundantly declare `kind: relpath` together with `type: relpath`; prefer `type: relpath` alone on workflow boundaries.
  - This warning is intentionally scoped away from top-level `artifacts`, `expected_outputs`, and `output_bundle`, where relpath/storage semantics still rely on artifact-style contracts.
  - Warning presence does not change runtime or workflow-load exit codes in the first pass.

- v2.10 additions (provider-session resume)
  - Scalar `string` becomes a general typed scalar contract for workflow `inputs`/`outputs`, top-level scalar `artifacts`, `expected_outputs`, `output_bundle.fields`, and scalar bookkeeping.
  - `type: string` preserves exact values end-to-end; unlike the older text-backed scalar types, the runtime does not trim leading/trailing whitespace.
  - Provider steps authored directly under the root workflow `steps:` list may declare `provider_session`:
    - `mode: fresh` requires `publish_artifact`
    - `mode: resume` requires `session_id_from`
  - Provider templates may declare `session_support` with:
    - `metadata_mode`
    - `fresh_command`
    - optional `resume_command`
  - `${SESSION_ID}` is legal only inside `session_support.resume_command`, which must contain exactly one placeholder when present.
  - Fresh session handles are runtime-owned publications: the handle is materialized on `steps.<Step>.artifacts.<publish_artifact>` and appended to `artifact_versions` only after the exact visit's final step result, same-visit lineage appends, and matching `current_step` clearance are committed together.
  - Resume consumes still participate in ordinary lineage selection, but the reserved `session_id_from` consume is excluded from prompt injection and `consume_bundle`.
  - Session-enabled visits create canonical observability artifacts under `.orchestrate/runs/<run_id>/provider_sessions/`.
  - `orchestrate resume` quarantines interrupted session-enabled visits instead of replaying them; `--force-restart` remains the explicit escape hatch.

- DSL evolution rollout roadmap
  - `v1.5`: D1 `assert`
  - `v1.6`: D2 typed predicates + structured `ref:` + normalized outcomes
  - `v1.7`: D2a scalar bookkeeping
  - `v1.8`: D3 cycle guards
  - `v2.0`: D4-D5 scoped refs + stable internal IDs
  - `v2.1`: D6 workflow signatures
  - `v2.2`: D7 structured `if/else`
  - `v2.3`: D8 `finally`
  - `v2.4` (docs/contract boundary): D9 reusable-call contract
  - `v2.5`: D10 imports + `call`
  - `v2.6`: D11 `match`
  - `v2.7`: D12 `repeat_until`
  - `v2.8`: D13 score-aware gates
  - `v2.9`: D14 authoring linting and normalization
  - `v2.10`: first-class provider-session resume

- Ordering note
  - D2a scalar bookkeeping is intentionally sequenced before D3 cycle guards.
  - Rationale: scalar bookkeeping only extends the current top-level name-keyed execution/result shape, while cycle guards introduce persisted counters and resume-sensitive control-flow state.
  - The first durable identity and schema migration remains reserved for the later D4-D5 tranche.

- Planned future (declarative per-item lifecycle)
  - `for_each.on_item_complete` with `success.move_to` / `failure.move_to` directories.
  - Version gating and rollout details are deferred until feature implementation.

## Declarative Task Lifecycle for for_each (Planned)

Status: Planned future feature. Opt‑in, version-gated. Does not change current defaults.

Version gating:
- To be finalized at implementation time.

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

- Future planned (JSON stdout validation assertions)
  - For steps with `output_capture: json`: optional `output_schema` and `output_require[...]` assertions.
  - Incompatible with `allow_parse_error: true`.
  - Version-gating target will be finalized when implemented.

## Version Gating Summary

| DSL version | Key features enabled | Notes |
| --- | --- | --- |
| 1.1 | Baseline DSL; providers (argv/stdin), `wait_for`, `depends_on` (required/optional), `when` (equals/exists/not_exists), retries/timeouts, strict path safety | State schema initially 1.1.1 (separate track). Unknown DSL fields rejected. |
| 1.1.1 | `depends_on.inject` (list/content/none), injection truncation recording | Workflows must declare `version: "1.1.1"` or a later supported version to use `inject`. |
| 1.2 | `artifacts(kind=relpath|scalar)`, `publishes`, `consumes`, `prompt_consumes` with runtime publish/consume enforcement | Keeps `expected_outputs` as file-validation primitive; adds provenance/freshness guarantees plus optional prompt-noise reduction and scalar consume flow. |
| 1.3 | `output_bundle`, `consume_bundle`, and `publishes.from` support for bundle fields | Reduces deterministic I/O fragmentation while preserving v1.2 publish/consume guarantees. |
| 1.4 | Read-only relpath consume semantics (no consume-time pointer mutation) | Preserves v1.2/v1.3 behavior by version; command steps should prefer `consume_bundle` for deterministic consumed values. |
| 1.5 | `assert` gate steps with dedicated `assert_failed` failure channel | First-class control-flow gates without shell glue; still uses legacy condition forms. |
| 1.6 | Typed predicates, structured `ref:`, normalized `outcome.*` fields | Opt-in typed gate surface; no reinterpretation of legacy `${steps.*}` semantics. |
| 1.7 | `set_scalar`, `increment_scalar` | Narrow runtime primitive for local scalar artifact production plus normal `publishes.from` lineage. |
| 1.8 | `max_transitions`, `max_visits` | Resume-safe cycle guards for top-level raw-graph workflows with persisted transition/visit counters. |
| 2.0 | Stable step `id`, scoped `self.steps.*` / `parent.steps.*` refs, qualified lineage/freshness | Establishes the durable internal identity boundary and the `schema_version: "2.0"` state model. |
| 2.1 | Top-level `inputs`/`outputs`, `${inputs.*}`, `ref: inputs.*`, and CLI input binding | Typed workflow-boundary signatures layered on top of the v2.0 identity/state model. |
| 2.2 | Top-level structured `if/else` with lowered branch markers/join nodes | Branch-local work stays scoped to `then` / `else`; downstream refs target statement outputs on the join node. |
| 2.3 | Top-level `finally` with resume-safe cleanup progress and deferred workflow outputs | Cleanup runs once after body success/failure, keeps stable finalization ids, and suppresses workflow outputs on cleanup failure. |
| 2.4 | Reusable-call contract boundary only (not executable by itself) | Locks path taxonomy, same-version rule, write-root parameterization, and accepted operational-risk language before runtime work lands. |
| 2.5 | `imports` + inline `call` with typed `with:` binding | Uses `schema_version: "2.1"` for persisted call-frame lineage/export state. |
| 2.6 | Top-level structured `match` with exhaustive enum case coverage | Case-local work stays scoped to the selected case; downstream refs target statement outputs on the join node. |
| 2.7 | Top-level post-test `repeat_until` with loop-frame outputs and resume-safe iteration bookkeeping | Loop conditions read only `self.outputs.*`; downstream refs target the loop frame outputs on the authored step; direct nested `call`, `match`, and `if/else` bodies are allowed. |
| 2.8 | Score-aware predicate helper `score` for thresholds and score bands | Thin sugar over numeric typed predicates; keeps benchmark gating inside the existing `when` / `assert` / structured-control surfaces. |
| 2.9 | Advisory authoring linting / normalization hints surfaced in CLI dry-run and report output | Warns about migration candidates without turning valid workflows into validation failures. |
| future (planned) | `for_each.on_item_complete` declarative per-item lifecycle (move_to on success/failure) | Opt-in lifecycle automation; detailed gating/version target will be set when implemented. |
| future (planned) | JSON stdout validation: `output_schema`, `output_require` for steps with `output_capture: json` | Enforces schema and simple assertions; incompatible with `allow_parse_error: true`. |
