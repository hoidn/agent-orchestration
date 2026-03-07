# Runtime Execution Lifecycle

This document describes what the orchestrator does at runtime for a workflow run.
It focuses on execution order and state transitions, not DSL authoring style.

Normative behavior is defined by `specs/`. This file is explanatory.

## Execution Timeline

```text
1) Load + validate workflow YAML (version-gated strict schema)
2) Initialize run root and state.json
3) Iterate steps in graph order (or goto targets)
4) For each step:
   a) evaluate `when` (may skip)
   b) enforce consumes preflight (if configured)
   c) execute step body (`assert`/command/provider/wait_for/for_each)
   d) validate deterministic outputs (`expected_outputs` or `output_bundle`)
   e) record published artifacts (if configured)
   e1) project normalized step `outcome` metadata for observable results
   f) compute next step (`on.success`, `on.failure`, `on.always`, fallback flow)
5) Terminate at `_end`, terminal step, or failure policy
6) Persist final run status and report artifacts
```

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
- `contract_violation` failures are represented as failed steps (typically exit code `2`).
- Non-zero exits route through failure handlers if defined; otherwise strict-flow/on-error policy applies.

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

## Control-Flow Resolution Order

Runtime resolves next step in this order:
1. Applicable `on.success` or `on.failure`
2. `on.always` (if present)
3. Default flow behavior (next sequential step or strict-flow/on-error behavior)

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
