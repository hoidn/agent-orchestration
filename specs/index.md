# Multi-Agent Orchestration — Master Spec (v1.1 through v2.21)

Status: Normative master. This index defines scope, versioning, conformance, and the module map with stable links to sub-specs. The DSL version and the state schema version are distinct by design.

- Versioning
  - DSL: v1.1 baseline; v1.1.1 adds dependency injection; v1.2 adds artifact publish/consume dataflow contracts; v1.3 adds bundled deterministic I/O; v1.4 makes relpath consume preflight pointer-safe (read-only); v1.5-v1.8 add gates, typed predicates, scalar bookkeeping, and cycle guards; v2.0 adds scoped refs and stable internal step identities; v2.1 adds typed workflow signatures; v2.2 adds structured `if/else`; v2.3 adds structured `finally`; v2.5 adds reusable `imports` + inline `call`; v2.6-v2.12 add structured `match`, post-test `repeat_until`, score-aware gates, advisory linting, provider-session resume, adjudicated provider steps, and repeat-until exhaustion outputs; v2.13 adds managed provider jobs; v2.14 adds materialization, snapshot, variant-output, atomic variant-selection, and variant-proof surfaces; v2.15 adds native direct-root returns and typed result guidance; v2.16 adds bounded Workflow Lisp provider supervision; v2.17 adds static Workflow Lisp provider peer groups with recorded turn-boundary messaging; v2.19 adds exact transportable `Value`; v2.20 adds Workflow Lisp prompt fragments; v2.21 adds prompt output positions.
  - State schema: `schema_version: "2.1"`.
  - Validation is strict: unknown fields are rejected at the declared DSL `version`.

- Precedence and scope
  - The spec defines the external contract: DSL, state schema, CLI behavior, acceptance criteria.
  - Implementation architecture (see `arch.md`) provides ADRs and non-normative implementation guidance. If in conflict, the spec governs.

- Module map (normative unless marked informative)
  - DSL and Control Flow: `dsl.md`
  - Variable Model: `variables.md`
  - Providers and Prompt Delivery: `providers.md`
  - Step IO and Capture Limits: `io.md`
  - Dependencies and Injection: `dependencies.md`
  - Run Identity and State: `state.md`
  - Queues and Wait-For: `queue.md`
  - CLI Contract: `cli.md`
  - Observability and Status JSON: `observability.md`
  - Security and Path Safety: `security.md`
  - Versioning and Migration: `versioning.md`
  - Acceptance Tests: `acceptance/index.md`

- Out of scope
  - General authored concurrency/parallel blocks, while loops, unrestricted
    complex expressions, and event-driven triggers (beyond polling via
    `wait_for`). The bounded concurrency exceptions are v2.16
    `with-live-providers` (exactly one worker and one supervisor) and v2.17
    `with-live-provider-peers` (one static group of two through eight
    members); each lowers to one atomic executable node.

- Quick links
  - Path safety: `security.md#path-safety`
  - Injection modes and caps: `dependencies.md#injection`
  - Output capture limits and tee semantics: `io.md#output-capture`
  - CLI safety rails: `cli.md#safety`
  - Orchestration concept model (informative): `../docs/orchestration_start_here.md`
  - Runtime execution lifecycle (informative): `../docs/runtime_execution_lifecycle.md`
  - Workflow drafting guide (informative): `../docs/workflow_drafting_guide.md`
  - Workflow Lisp provider supervision (informative design):
    `../docs/design/workflow_lisp_provider_live_binding.md`
  - Workflow Lisp provider peer messaging (informative design):
    `../docs/design/workflow_lisp_provider_peer_messaging.md`

## Executive Summary

Versioning note: This specification defines the v1.1 baseline and includes later gates, typed predicates, bookkeeping, cycle guards, the v2.0 scoped-ref / stable-ID tranche, the v2.1 workflow-signature tranche, the v2.2-v2.3 structured-control/finalization tranches, the v2.5 reusable-call tranche, the v2.6-v2.8 `match` / `repeat_until` / score-gate tranches, the v2.9 advisory linting tranche, the v2.10 provider-session tranche, the v2.11 adjudicated-provider tranche, the v2.12 repeat-until exhaustion-output tranche, the v2.13 managed-provider-jobs tranche, the v2.14 materialization / snapshot / variant-output tranche, the v2.15 native-return/guidance tranche, the v2.16 provider-supervision tranche, the v2.17 provider-peer-group tranche, the v2.19 exact-`Value` tranche, the v2.20 prompt-fragment tranche, and the v2.21 prompt-output-position tranche. The state schema remains `schema_version: "2.1"`. Workflows written against older DSL versions remain valid, but post-v2.1 runtimes reject resume from pre-v2.1 state unless an explicit upgrader is introduced. The workflow DSL `version:` and the state `schema_version` follow separate version tracks by design. DSL validation is strict: unknown fields are rejected. Workflows that use `depends_on.inject` MUST set `version: "1.1.1"` (or higher), workflows that use dataflow contracts MUST set `version: "1.2"` (or higher), workflows that use bundle contracts MUST set `version: "1.3"` (or higher), workflows that use provider sessions MUST set `version: "2.10"` (or higher), workflows that use adjudicated provider steps MUST set `version: "2.11"` (or higher), workflows that use `repeat_until.on_exhausted` MUST set `version: "2.12"` (or higher), workflows that use `managed_jobs` MUST set `version: "2.13"` (or higher), workflows that use `materialize_artifacts`, `pre_snapshot`, `variant_output`, `select_variant_output`, or `requires_variant` MUST set `version: "2.14"` (or higher), Workflow Lisp native direct-root returns or typed guidance MUST target `2.15` (or higher), `with-live-providers` MUST target `2.16` (or higher), `with-live-provider-peers` MUST target `2.17` (or higher), `defprompt` MUST target `2.20` (or higher), and a prompt output position MUST target `2.21` (or higher).

This system executes validated workflow bundles compiled from fresh `.orc`
source, including command and LLM-provider invocations. Most execution is
deterministic and sequential; v2.16 adds one narrowly bounded two-provider
supervision overlap and v2.17 adds one statically bounded two-through-eight
provider peer-group overlap. Each workflow-state/result boundary remains
atomic. Agents may
coordinate through filesystem queues (`inbox/`, `processed/`, `failed/`).
Steps capture outputs as text, line arrays, JSON, or validated structured
bundles with deterministic control flow and bounded loops. Keep authoring
surfaces distinct: workflow-boundary `inputs`/`outputs`, runtime dependencies
(`depends_on`, `consumes`), provider prompt sources (`input_file`,
`asset_file`, `asset_depends_on`), and artifact storage or lineage
(`artifacts`, `expected_outputs`, `output_bundle`, `publishes`).

## Out of Scope

- General concurrency and parallel blocks; v2.16's exactly-two-provider
  supervision node and v2.17's static two-through-eight-member peer-group node
  are the only bounded exceptions
- While loops
- Parallel execution blocks
- Complex expression evaluation
- Event-driven triggers
