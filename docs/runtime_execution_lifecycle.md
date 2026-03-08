# Runtime Execution Lifecycle

This document describes what the orchestrator does at runtime for a workflow run.
It focuses on execution order and state transitions, not DSL authoring style.

Normative behavior is defined by `specs/`. This file is explanatory.

## Execution Timeline

```text
1) Load + validate workflow YAML (version-gated strict schema)
2) Bind workflow `inputs` (v2.1+, if declared), lower any v2.2 structured `if/else`, lower loop-local v2.7 `repeat_until` body `if/else` / `match`, lower any v2.3 `finally`, assign any v2.7 `repeat_until` body step ids, then initialize run root and state.json
3) Iterate steps in graph order (or goto targets)
4) For each step:
   a) apply workflow/step cycle guards for the routed target (`max_transitions`, then `max_visits`)
   b) evaluate `when` (may skip)
   c) enforce consumes preflight (if configured)
   d) execute step body (`assert`/command/provider/wait_for/for_each/call)
   e) validate deterministic outputs (`expected_outputs` or `output_bundle`)
   f) record published artifacts (if configured)
   f1) project normalized step `outcome` metadata for observable results
   g) compute next step (`on.success`, `on.failure`, `on.always`, fallback flow)
   h) increment `transition_count` if control transfers into another top-level step
5) If declared, run workflow `finally` exactly once after the body settles on success or failure
6) Export workflow `outputs` (v2.1+, if declared) only after successful finalization, then persist final run status and report artifacts
```

Identity note:
- v2.0 assigns every step a durable internal `step_id`.
- Presentation keys in `state.steps` remain name-oriented for compatibility, but lineage/freshness bookkeeping and resume-facing identity now use `step_id`.
- `for_each` iterations derive qualified identities such as `root.loop_publish#0.produce_in_loop`.
- v2.2 structured `if/else` lowers to branch markers, lowered branch-body nodes, and a join node that keeps the authored statement presentation key.
- v2.3 structured `finally` lowers to stable cleanup-step identities under `finally.<StepName>` while keeping durable ancestry rooted under `root.finally.<block-id-or-finally>`.
- v2.5 `call` keeps the authored outer step as the caller-visible node and persists nested callee execution under `state.call_frames[call_frame_id]`.
- v2.7 `repeat_until` keeps the authored loop frame as the caller-visible node, derives per-iteration nested identities such as `root.review_loop#1.iteration_body.run_review_loop` or `root.review_loop#1.iteration_body.route_decision.revise_path.write_revision`, and persists resume bookkeeping under `state.repeat_until`.
- `resume` uses persisted run position only to choose the initial top-level restart point. After execution reaches that point, normal control-flow semantics resume, so a later `goto` may revisit the same top-level step name without being auto-skipped.
- When finalization is partially complete, `resume` restarts at the first unfinished cleanup step instead of replaying completed cleanup.
- When a run stops inside a `call`, `resume` reuses the unfinished `call_frame_id` and restarts the callee from its first unfinished nested step instead of replaying completed nested work.
- When a run stops inside `repeat_until`, `resume` uses `state.repeat_until` plus indexed nested step results to restart from the first unfinished nested step in the current iteration; if that iteration's condition already evaluated, resume advances without replaying the settled iteration.
- During such revisits, `state.steps.<StepName>` still stores the latest completed/skipped/failed result for that top-level name, while `current_step` may refer to a later in-flight visit of the same step. The visit ordinals distinguish them: `current_step.visit_count` is the active visit, and `steps.<StepName>.visit_count` is the last persisted result visit.

## Run Artifacts

Primary run directory:
- `.orchestrate/runs/<run_id>/`

Core files/directories:
- `state.json`: authoritative execution record
- `logs/`: stdout/stderr spill files, prompt audits (debug mode), orchestrator logs
- `summaries/`: optional advisory step summaries when enabled by CLI flags

Console visibility:
- `--stream-output` live-streams provider stdout/stderr to the terminal during execution.
- `--debug` also streams provider output, but additionally enables prompt-audit and debug-mode artifacts.

## Step State Machine

```text
pending -> running -> completed
pending -> running -> failed
pending -> skipped
```

Key notes:
- `when` false produces `skipped` with `exit_code: 0`.
- `assert` false produces `failed` with `exit_code: 3` and `error.type: "assert_failed"`.
- `cycle_guard_exceeded` fails the target step before body execution; explicit `on.failure.goto` may recover, otherwise the run stops.
- `contract_violation` failures are represented as failed steps (typically exit code `2`).
- `call` executes an imported workflow inline with its own nested state, private providers/artifacts/context defaults, and caller-visible outputs exported only after the callee body and callee finalization succeed.
- Non-zero exits route through failure handlers if defined; otherwise strict-flow/on-error policy applies.
- After a resumed run terminates, `current_step` is cleared the same way it is for non-resumed runs.
- For structured `if/else`, non-selected lowered branch nodes appear as `skipped`, while the selected-branch outputs are materialized on the join node under the authored statement name.
- For `repeat_until`, the loop frame stays `running` while iterations are in progress, materializes declared loop outputs after each completed iteration, and fails with `repeat_until_iterations_exhausted` if `max_iterations` is reached before the condition becomes true.
- For structured `finally`, cleanup failures after body success become the run's primary failure; if the body already failed, cleanup failures are recorded as secondary diagnostics under `state.finalization`.

## Provider Step Runtime Order

For provider steps, runtime behavior is effectively:

```text
compose prompt
  = input_file literal
  + optional depends_on injection
  + optional consumed-artifacts injection (v1.2+)
  + optional output-contract suffix

execute provider command template (argv or stdin mode)

capture stdout/stderr

validate deterministic outputs if declared
```

Prompt composition details are normative in `specs/providers.md`.

## Consume/Publish Runtime Semantics (v1.2+)

Before step execution:
- `consumes` preflight selects artifact versions according to policy/freshness.
- Missing or stale required artifacts fail preflight with `contract_violation`.
- In v1.4, relpath consume preflight is pointer-safe/read-only (no pointer-file mutation).
- Optional `consume_bundle` writes resolved consume values to deterministic JSON for the step.

After successful step execution + output validation:
- `publishes` appends new artifact versions to `artifact_versions` in state.
- `artifact_consumes` tracks last consumed version(s) for freshness enforcement.
- For `call`, callee-private publish/consume state remains inside the persisted call frame; only declared callee outputs cross back to the caller-visible outer step.

## Control-Flow Resolution Order

Runtime resolves next step in this order:
1. Applicable `on.success` or `on.failure`
2. `on.always` (if present)
3. Default flow behavior (next sequential step or strict-flow/on-error behavior)

After the next top-level target is known, the executor increments `transition_count`. If the next routed target would exceed `max_transitions`, that target fails pre-execution on entry.

Special target:
- `_end`: explicit successful termination.

## Retry and Timeout Behavior

- `timeout_sec` applies to command/provider execution and can produce exit code `124`.
- Provider steps have retry defaults for retryable exit codes.
- Command steps retry only when per-step retry config is present.
- Step-level retry config overrides default/global retry behavior.

See `specs/dsl.md`, `specs/providers.md`, and `specs/io.md` for normative details.

## for_each Runtime Shape

At runtime, loop results are recorded per iteration:
- `steps.<LoopName>[i].<NestedStepName>`

Loop variables are resolved per iteration (`item`, alias, `loop.index`, `loop.total`).
Typed predicates in v2.0 may also read scoped refs from the current loop scope (`self.steps.*`) or the enclosing scope (`parent.steps.*`) without changing legacy `${steps.*}` substitution semantics.

## Failure Taxonomy (Common)

- process failure: command/provider non-zero exit
- gate failure: first-class `assert` evaluated false
- timeout failure: enforced timeout (often exit `124`)
- parse failure: invalid JSON capture when strict JSON mode required
- contract failure: deterministic output or consume/publish contract violation
- predicate evaluation failure: typed predicate/ref resolution failed before the step body could complete

These are reflected in step `status`, `exit_code`, and `error` fields in `state.json`.

## Runtime vs Authoring Boundary

This file describes runtime behavior.
For writing workflow YAML and prompt patterns, use:
- `docs/orchestration_start_here.md`
- `docs/workflow_drafting_guide.md`
