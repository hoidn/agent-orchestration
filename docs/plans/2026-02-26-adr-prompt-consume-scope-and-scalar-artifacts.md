# ADR: Reduce Prompt Handoff Noise with Explicit Prompt Consumes and Scalar Artifacts

**Status:** Proposed  
**Date:** 2026-02-26  
**Owners:** Orchestrator maintainers

## Context

Current `version: "1.2"` dataflow semantics combine two concerns under `consumes`:
1. Runtime dependency/provenance (`latest_successful`, freshness, pointer materialization).
2. Agent prompt context injection (`## Consumed Artifacts`).

This coupling encourages over-sharing. Workflows declare many artifacts for correctness, and all can end up injected into prompts, including operational noise (`pre_run_*`, queue paths, derived counters). It also pushes users to create pointer-style artifacts for scalar values (for example `failed_count_path`) just to make them consumable, which fragments state and prompts.

## Decision

### D1. Add `prompt_consumes` step field (explicit prompt subset)

Introduce an optional provider-step field:

```yaml
prompt_consumes: ["plan", "execution_log"]
```

Semantics:
- `consumes` remains the runtime/provenance contract.
- `prompt_consumes` controls which consumed artifacts are injected into prompt text.
- Validation: every `prompt_consumes` artifact name MUST appear in the step's `consumes` set.
- Injection order/position uses existing controls (`inject_consumes`, `consumes_injection_position`).

Backward compatibility:
- If `prompt_consumes` is omitted, preserve current behavior (inject all consumed artifacts).
- No behavior change for existing v1.2 workflows unless they opt in.

### D2. Add scalar artifacts to registry

Extend top-level `artifacts` so non-relpath values can be published/consumed directly.

Proposed shape:

```yaml
artifacts:
  failed_count:
    kind: scalar
    type: integer
  execution_log:
    kind: relpath
    pointer: state/execution_log_path.txt
    type: relpath
    under: artifacts/work
    must_exist_target: true
```

Rules:
- `kind: relpath` keeps current pointer-based behavior.
- `kind: scalar` has no required pointer; value is stored in artifact ledger as typed value.
- `publishes.from` can map to any `expected_outputs.name` whose parsed type matches artifact type.
- `consumes` for scalar artifacts enforces producer/policy/freshness the same way as relpath.
- Prompt injection renders scalar values directly (`- failed_count: 0`).
- Pointer materialization applies only to relpath artifacts.

### D3. Recommended workflow policy (non-DSL)

Use:
- `consumes` for correctness/provenance dependencies.
- `prompt_consumes` for minimal agent-visible context.

This separates "what must be true before running" from "what the model needs to read".

## Consequences

Benefits:
- Lower prompt noise and better model focus.
- Fewer artificial pointer artifacts for scalar values.
- Preserves deterministic contracts and freshness checks.
- Incremental adoption without breaking existing v1.2 workflows.

Trade-offs:
- One additional DSL field (`prompt_consumes`) to learn.
- Slightly more loader/executor complexity.

## Alternatives Considered

1. Keep status quo (`consumes` always injected): rejected due to persistent prompt noise and artifact fragmentation.
2. Heuristic auto-filtering of injected artifacts: rejected due to non-determinism and hard-to-debug behavior.
3. Disable consume injection by default globally: rejected as a breaking change for existing workflows.

## Proposed DSL Spec Additions

Step-level (provider steps):

```yaml
consumes: [ ... ]
prompt_consumes: [artifact_name, ...]   # optional subset of consumes
inject_consumes: true|false              # existing
consumes_injection_position: prepend|append
```

Artifact-level:

```yaml
artifacts:
  <name>:
    kind: relpath|scalar
    type: enum|integer|float|bool|relpath
    pointer: <relpath>        # required for kind=relpath, optional/forbidden for scalar
    under: <relpath>          # relpath only
    must_exist_target: bool   # relpath only
```

## Migration Plan

Phase 1 (non-breaking):
- Implement `prompt_consumes` with default fallback to "all consumes".
- Update one example workflow to demonstrate noise reduction.

Phase 2 (scalar support):
- Implement `kind: scalar` in loader + runtime publish/consume path.
- Add example workflow consuming `failed_count` scalar without pointer artifact.

Phase 3 (guidance):
- Update docs to recommend minimal `prompt_consumes` sets.

## Test Plan

Loader tests:
- `prompt_consumes` must be list of strings.
- `prompt_consumes` must be subset of `consumes` artifact names.
- `kind` validation and relpath/scalar field constraints.

Executor tests:
- Injection includes only `prompt_consumes` when present.
- Omitted `prompt_consumes` preserves current behavior.
- Scalar publish/consume works with policy/freshness checks.
- Scalar values render correctly in `Consumed Artifacts` block.

Integration tests:
- End-to-end workflow with `plan` + `execution_log` injected, while additional consumed artifacts are excluded from prompt.

## Example (target style)

```yaml
version: "1.2"
artifacts:
  plan:
    kind: relpath
    pointer: state/plan_path.txt
    type: relpath
    under: docs/plans
    must_exist_target: true
  execution_log:
    kind: relpath
    pointer: state/execution_log_path.txt
    type: relpath
    under: artifacts/work
    must_exist_target: true
  failed_count:
    kind: scalar
    type: integer

steps:
  - name: ReviewImplVsPlan
    provider: codex
    consumes:
      - artifact: plan
        policy: latest_successful
      - artifact: execution_log
        policy: latest_successful
      - artifact: failed_count
        policy: latest_successful
    prompt_consumes: ["plan", "execution_log"]
```

Result: correctness depends on all three artifacts, but prompt context includes only plan + execution log.
