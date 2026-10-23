# Multi-Agent Orchestration — Master Spec (current targets 2.35–2.40)

Status: Normative master. This index defines scope, versioning, conformance, and the module map with stable links to sub-specs. The DSL version and the state schema version are distinct by design.

Current admission: source compilation, transitive source imports, retained
typed-program capsules, REPL loading and LSP analysis accept only registered
targets 2.35–2.40 throughout the dependency graph. All use evaluated execution;
individual effects retain their own admission and qualification gates.
Pre-2.35 source and old-profile resume/invalidation are retired. Historical
report/dashboard data access does not compile old source. See
[versioning](versioning.md#executable-support-and-historical-version-gates) and
[CLI admission](cli.md#executable-support-boundary).

- Version history and current target extensions
  - The entries below record feature introductions. A historical introduction
    does not admit its original source target or restore retired effects.
  - DSL: v1.1 baseline; v1.1.1 adds dependency injection; v1.2 adds artifact publish/consume dataflow contracts; v1.3 adds bundled deterministic I/O; v1.4 makes relpath consume preflight pointer-safe (read-only); v1.5-v1.8 add gates, typed predicates, scalar bookkeeping, and cycle guards; v2.0 adds scoped refs and stable internal step identities; v2.1 adds typed workflow signatures; v2.2 adds structured `if/else`; v2.3 adds structured `finally`; v2.5 adds reusable `imports` + inline `call`; v2.6-v2.12 add structured `match`, post-test `repeat_until`, score-aware gates, advisory linting, provider-session resume, adjudicated provider steps, and repeat-until exhaustion outputs; v2.13 adds managed provider jobs; v2.14 adds materialization, snapshot, variant-output, atomic variant-selection, and variant-proof surfaces; v2.15 adds native direct-root returns and typed result guidance; v2.16 adds bounded Workflow Lisp provider supervision; v2.17 adds static Workflow Lisp provider peer groups with recorded turn-boundary messaging; v2.18 adds bounded Workflow Lisp list traversal, mapping, list loop state, and rooted path joining; v2.19 adds exact transportable `Value`; v2.20 adds Workflow Lisp prompt fragments; v2.21 adds prompt output positions; v2.22 adds direct-fragment prompt-attempt identity and diagnostics; v2.23 adds explicit phased contract delivery; v2.24 adds pinned child execution through `run-ref`; v2.25 adds bounded static trials over `run-ref`; v2.26 adds strict Boolean control flow (`if`/`cond`); v2.27 adds opt-in fresh provider session-artifact publication; v2.28 admits whole closed unions in ordinary typed provider inputs and prompt value fills.
  - DSL v2.29 additionally admits already-transportable record/union lists as
    whole loop state and complete state-derived exhaustion results, including
    root-state and committed-boundary resume; see the
    [frontend loop contract](../docs/design/workflow_lisp_frontend_specification.md#131-bounded-loop).
  - DSL v2.30 admits resolved-inline pure-call composition and ordered schema-3
    lexical bindings, preserving selected-hook scope and eager exactly-once
    arguments. Private/effectful/unrepresentable calls remain outside that resolved-inline
    pure subset; the pre-2.30 pipeline is historical. See the
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
    checks at boundaries. W3 repetition reduction has its own
    target-2.36 contract; W2 optional effects are delivered by EL-1 at 2.39.
    W1/W4 and further write-once trials remain unselected with their existing gates. See
    [versioning](versioning.md) for target admission and the scoped surface.
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
  - DSL v2.36 extends the evaluated route with W3 local hooks and one
    four-argument `std/improve` API per source graph. The
    [version contract](versioning.md#versioning-and-migration-normative) and
    [W3 contract](../docs/design/workflow_lisp_write_once.md#6-w3-hooks-see-their-context)
    own the rules.
  - Target 2.37 parallel-map compilation and bounded execution have scoped
    acceptance; full public qualification and phase delivery remain pending.
    Follow [versioning](versioning.md#version-gating-summary) and the
    [Phase 5 status](../docs/plans/2026-10-07-evaluated-execution-phase-5-plan.md#status-entry-and-decisions)
    for its limits; it is not yet a copy-safe authoring surface.
  - Target 2.38 admits command-only confined run-ref children and the
    independent bounded Agent surface: run-local allocation and sequential
    native turns with typed results and memo commits. Public confined providers
    remain closed; [versioning](versioning.md#version-gating-summary) and the
    [capability matrix](../docs/capability_status_matrix.md) own their distinct limits.
    See the [Agent authoring guide](../docs/lisp_workflow_drafting_guide.md#agent-sessions-target-238)
    and [PQ-1a evidence](../docs/reports/2026-10-14-agent-sessions-pq1a-qualification.md).
    The real-provider acceptance comparison (PQ-1c) has not run and requires separate owner authorization.
  - Target 2.39 adds inference-default procedure contracts, optional checked
    restrictions, caller-owned composition and finite source admission.
    Imported 2.35–2.38 definitions retain their original contracts; see the
    [procedure contract](../docs/design/workflow_lisp_effect_ledger_simplification.md).
  - Target 2.40 adds typed serial durable host input and ordinary `std/host::HostReply[A]`; external answer/cancel settles the exact request and ordinary resume consumes it or expires it. The bounded [Python frontend](../docs/design/workflow_python_frontend.md) emits retained `.orc` and supplied manifests into the same checked compiler/runtime. See [DSL](dsl.md#evaluated-durable-host-input-target-240), [state](state.md#evaluated-durable-host-input-target-240) and [CLI](cli.md#python-authoring).
  - State schema: historical runs through 2.34 used `schema_version: "2.1"`;
    admitted evaluated runs at 2.35–2.40 publish `"3.0"`
    (see [state](state.md)).

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
    `wait_for`). The historical bounded concurrency exceptions were v2.16
    `with-live-providers` (exactly one worker and one supervisor), v2.17
    `with-live-provider-peers` (one static group of two through eight
    members), and v2.25 `trial` (a static bounded set of E1 child-run cells);
    each lowered to one atomic executable node and is retired with executable
    entries through 2.34. The bounded target-2.37 parallel map is the current
    exception; see [versioning](versioning.md#version-gating-summary).

- Quick links
  - Path safety: `security.md#security-and-path-safety-normative`
  - Injection modes and caps: `dependencies.md#injection-examples`
  - Output capture limits and tee semantics: `io.md#step-io-and-output-capture-normative`
  - CLI safety rails: `cli.md#workspace-execution-ownership`
  - Orchestration concept model (informative): `../docs/orchestration_start_here.md`
  - Runtime execution lifecycle (informative): `../docs/runtime_execution_lifecycle.md`
  - Python drafting guide (informative): `../docs/python_workflow_drafting_guide.md`
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

The runtime evaluates a checked closed program compiled from admitted `.orc`
source. An append-only effect memo owns execution and resume; `state.json`
is a schema-3.0 derived view. Workflow DSL targets and persisted state schemas
are separate version tracks. Unknown fields and unsupported targets reject;
[versioning](versioning.md) records current admission and historical feature
gates without restoring retired execution or source compatibility.

Commands and supported provider calls compose through typed values, calls,
conditionals and bounded loops. Parallel mapping is a bounded target-2.37
extension with separate qualification gates. Historical supervision, peer-group
and trial nodes do not supply current concurrency. Public confined providers
remain closed; bounded Agent Sessions and command-only confined children have
their own [capability limits](../docs/capability_status_matrix.md).

## Out of Scope

- General concurrency and parallel blocks; the bounded target-2.37 parallel
  map is the only current exception (the v2.16 supervision, v2.17 peer-group
  and v2.25 `trial` nodes are retired with executable entries through 2.34)
- While loops
- Parallel execution blocks
- Complex expression evaluation
- Event-driven triggers
