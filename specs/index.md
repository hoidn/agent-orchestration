# Multi-Agent Orchestration — Master Spec (v1.1 through v2.35)

Status: Normative master. This index defines scope, versioning, conformance, and the module map with stable links to sub-specs. The DSL version and the state schema version are distinct by design.

- Versioning
  - DSL: v1.1 baseline; v1.1.1 adds dependency injection; v1.2 adds artifact publish/consume dataflow contracts; v1.3 adds bundled deterministic I/O; v1.4 makes relpath consume preflight pointer-safe (read-only); v1.5-v1.8 add gates, typed predicates, scalar bookkeeping, and cycle guards; v2.0 adds scoped refs and stable internal step identities; v2.1 adds typed workflow signatures; v2.2 adds structured `if/else`; v2.3 adds structured `finally`; v2.5 adds reusable `imports` + inline `call`; v2.6-v2.12 add structured `match`, post-test `repeat_until`, score-aware gates, advisory linting, provider-session resume, adjudicated provider steps, and repeat-until exhaustion outputs; v2.13 adds managed provider jobs; v2.14 adds materialization, snapshot, variant-output, atomic variant-selection, and variant-proof surfaces; v2.15 adds native direct-root returns and typed result guidance; v2.16 adds bounded Workflow Lisp provider supervision; v2.17 adds static Workflow Lisp provider peer groups with recorded turn-boundary messaging; v2.18 adds bounded Workflow Lisp list traversal, mapping, list loop state, and rooted path joining; v2.19 adds exact transportable `Value`; v2.20 adds Workflow Lisp prompt fragments; v2.21 adds prompt output positions; v2.22 adds direct-fragment prompt-attempt identity and diagnostics; v2.23 adds explicit phased contract delivery; v2.24 adds pinned child execution through `run-ref`; v2.25 adds bounded static trials over `run-ref`; v2.26 adds strict Boolean control flow (`if`/`cond`); v2.27 adds opt-in fresh provider session-artifact publication; v2.28 admits whole closed unions in ordinary typed provider inputs and prompt value fills.
  - DSL v2.29 additionally admits already-transportable record/union lists as
    whole loop state and complete state-derived exhaustion results, including
    root-state and committed-boundary resume; see the
    [frontend loop contract](../docs/design/workflow_lisp_frontend_specification.md#131-bounded-loop).
  - DSL v2.30 admits resolved-inline pure-call composition and ordered schema-3
    lexical bindings, preserving selected-hook scope and eager exactly-once
    arguments. Private/effectful/unrepresentable calls remain excluded; older
    targets keep their existing pipeline. See the
    [frontend contract](../docs/design/workflow_lisp_frontend_specification.md#86-defun).
  - DSL v2.31 admits ordinary portable provider-context values, opt-in capture
    and fresh quoted-history binding. Supported Codex event coverage and atomic
    result/context publication are defined in `providers.md` and `io.md`.
    Native/cross-provider continuation remains outside the admitted contract.
  - DSL v2.32 admits the bundle-free Workflow Lisp `request-input` host
    operation and fixed `HumanReply` result. One root-owned request suspends
    execution; thin answer/cancel clients only settle it, while ordinary resume
    validates and consumes the exact reply. It adds neither native continuation
    nor provider-session reuse.
  - DSL v2.33 admits first-order generic unions (`defunion :forall` and type
    applications, instantiated at compile time, including applied-union
    `provider-result` and `defprompt` results) and the bundled `std/improve`
    review helper. Its effect inference includes imported procedures. Target
    admission is per defining module. It adds no generic records or explicit
    procedure type arguments. See `versioning.md`, which also lists the scope
    corrections that apply to every target.
  - DSL v2.34 implements decimal literals, numeric operators and finite-value
    checks at boundaries. Repetition reduction is a separate unapproved
    proposal; see [versioning](versioning.md) for the implemented surface.
  - DSL v2.35 is the evaluated-execution target: public `compile`, `run`,
    `resume` and `invalidate` operate on a checked closed program with a
    memo-backed run (`result_persistence_profile: evaluated_execution.v1`,
    state schema `3.0`). The
    [evaluated-execution design](../docs/design/workflow_lisp_evaluated_execution.md)
    owns the model; [versioning](versioning.md) owns target admission and
    availability; [state](state.md#evaluated-execution-persistence-profile-target-235),
    [io](io.md#evaluated-command-and-provider-io-target-235) and
    [cli](cli.md#evaluated-execution-target-235) own the run, request and
    command contracts.
  - State schema: `schema_version: "2.1"` for targets through 2.34; a
    target-2.35 evaluated run publishes `"3.0"` (see [state](state.md)).
  - Validation is strict: unknown fields are rejected at the declared DSL `version`.

- Precedence and scope
  - The spec defines the external contract: DSL, state schema, CLI behavior, acceptance criteria.
  - Implementation architecture (see [Architecture Overview](../docs/architecture_overview.md) and [Design Documentation Index](../docs/design/README.md)) provides non-normative implementation guidance. If in conflict, the spec governs.

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
    `with-live-providers` (exactly one worker and one supervisor), v2.17
    `with-live-provider-peers` (one static group of two through eight
    members), and v2.25 `trial` (a static bounded set of E1 child-run cells);
    each lowers to one atomic executable node.

- Quick links
  - Path safety: `security.md#path-safety`
  - Injection modes and caps: `dependencies.md#injection`
  - Output capture limits and tee semantics: `io.md#output-capture`
  - CLI safety rails: `cli.md#safety`
  - Orchestration concept model (informative): `../docs/orchestration_start_here.md`
  - Runtime execution lifecycle (informative): `../docs/runtime_execution_lifecycle.md`
  - Workflow Lisp drafting guide (informative): `../docs/lisp_workflow_drafting_guide.md`
  - Historical YAML translation guide (informative): `../docs/workflow_drafting_guide.md`
  - Workflow Lisp provider supervision (informative design):
    `../docs/design/workflow_lisp_provider_live_binding.md`
  - Workflow Lisp provider peer messaging (informative design):
    `../docs/design/workflow_lisp_provider_peer_messaging.md`
  - Workflow Lisp phased contract delivery (informative design):
    `../docs/design/workflow_lisp_phased_contract_delivery.md`
  - Workflow Lisp pinned child execution and trials (informative design):
    `../docs/design/workflow_lisp_trial_runs.md`

## Executive Summary

Versioning note: This specification defines the v1.1 baseline and includes later gates, typed predicates, bookkeeping, cycle guards, the v2.0 scoped-ref / stable-ID tranche, the v2.1 workflow-signature tranche, the v2.2-v2.3 structured-control/finalization tranches, the v2.5 reusable-call tranche, the v2.6-v2.8 `match` / `repeat_until` / score-gate tranches, the v2.9 advisory linting tranche, the v2.10 provider-session tranche, the v2.11 adjudicated-provider tranche, the v2.12 repeat-until exhaustion-output tranche, the v2.13 managed-provider-jobs tranche, the v2.14 materialization / snapshot / variant-output tranche, the v2.15 native-return/guidance tranche, the v2.16 provider-supervision tranche, the v2.17 provider-peer-group tranche, the v2.18 bounded-list-traversal tranche, the v2.19 exact-`Value` tranche, the v2.20 prompt-fragment tranche, the v2.21 prompt-output-position tranche, the v2.22 prompt-attempt-identity tranche, the v2.23 phased-contract-delivery tranche, the v2.24 pinned-child-execution tranche, the v2.25 bounded-static-trial tranche, the v2.26 strict-Boolean-control-flow tranche, the v2.27 fresh-session-artifact tranche, the v2.28 whole-union prompt-input tranche, the v2.29 rich-loop-value tranche, the v2.30 resolved-inline pure-call tranche, the v2.31 portable-context tranche, the v2.32 durable host-input tranche, the v2.33 first-order generic-union tranche, the v2.34 numeric-surface tranche, and the v2.35 evaluated-execution tranche. The state schema remains `schema_version: "2.1"` for targets through 2.34; a target-2.35 evaluated run publishes schema `"3.0"` derived views from its memo. Workflows written against older DSL versions remain valid, but post-v2.1 runtimes reject resume from pre-v2.1 state unless an explicit upgrader is introduced. The workflow DSL `version:` and the state `schema_version` follow separate version tracks by design. DSL validation is strict: unknown fields are rejected. Workflows that use `depends_on.inject` MUST set `version: "1.1.1"` (or higher), workflows that use dataflow contracts MUST set `version: "1.2"` (or higher), workflows that use bundle contracts MUST set `version: "1.3"` (or higher), workflows that use provider sessions MUST set `version: "2.10"` (or higher), workflows that use adjudicated provider steps MUST set `version: "2.11"` (or higher), workflows that use `repeat_until.on_exhausted` MUST set `version: "2.12"` (or higher), workflows that use `managed_jobs` MUST set `version: "2.13"` (or higher), workflows that use `materialize_artifacts`, `pre_snapshot`, `variant_output`, `select_variant_output`, or `requires_variant` MUST set `version: "2.14"` (or higher), Workflow Lisp native direct-root returns or typed guidance MUST target `2.15` (or higher), `with-live-providers` MUST target `2.16` (or higher), `with-live-provider-peers` MUST target `2.17` (or higher), bounded list constructors/operators/maps, eligible `List[T]` loop state, or `path/join-under` MUST target `2.18` (or higher), `defprompt` MUST target `2.20` (or higher), a prompt output position MUST target `2.21` (or higher), direct-fragment prompt-attempt identity evidence requires target `2.22`, explicit phased contract delivery requires target `2.23`, `run-ref` requires target `2.24`, `trial` requires target `2.25`, strict Boolean `if`/`cond` control flow requires target `2.26`, provider `:session-artifact` publication requires target `2.27`, whole-union prompt consumption requires target `2.28`, rich loop values require target `2.29`, resolved-inline pure-call composition requires target `2.30`, portable provider context requires target `2.31`, durable host input requires target `2.32`, first-order generic unions require target `2.33`, decimal literals and numeric operators require target `2.34`, and evaluated execution, explicit command closures and external-tool `:inputs` documents require target `2.35` (see `dsl.md` and `versioning.md`).

This system executes validated workflow bundles compiled from fresh `.orc`
source, including command and LLM-provider invocations. Most execution is
deterministic and sequential; v2.16 adds one narrowly bounded two-provider
supervision overlap, v2.17 adds one statically bounded two-through-eight
provider peer-group overlap, and v2.25 adds one statically bounded concurrent
set of E1 child-run trial cells. Each workflow-state/result boundary remains
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
  supervision node, v2.17's static two-through-eight-member peer-group node,
  and v2.25's static bounded E1-child `trial` node are the only bounded
  exceptions
- While loops
- Parallel execution blocks
- Complex expression evaluation
- Event-driven triggers
