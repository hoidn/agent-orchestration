# Workflow Language Design Principles

Status: design guidance  
Scope: workflow DSL, workflow frontends, macro systems, shared validation,
semantic IR, executable IR

These principles define the semantic direction for workflow authoring surfaces.
They are not all normative runtime requirements today. Some describe current
v2.14 guarantees, while others describe requirements for future frontends such
as the Workflow Lisp frontend.

Use these labels:

- `current invariant`: already expected of the YAML DSL or runtime model.
- `v2.14 invariant`: introduced or sharpened by the v2.14 materialization,
  snapshot, and variant-output work.
- `frontend requirement`: required for any non-YAML frontend to be acceptable.
- `future direction`: desired higher-level language behavior that still needs a
  concrete lowering or runtime substrate.

## Compact Principles

- Design for typed transitions, not brittle gates.
- Structured bundles are authority; reports are views.
- Artifact values are authority; pointer files are representations.
- Freshness requires snapshot/hash evidence, not mtime.
- Validate before committing canonical state.
- Contracts may only narrow.
- Variant-specific references require proof.
- Frontends lower to core AST and shared semantic IR, not YAML text.
- Macros cannot hide effects.
- Procedures compose workflow behavior.
- Command steps are allowed; hidden semantic inline glue is not.
- State paths are derived from contexts, not hand-managed.
- Legacy parsing and pointer conventions are quarantined.
- Provider decisions produce structured state; reports remain views.
- Every generated semantic node is source-mapped.
- Promotion requires parity evidence, not successful compilation alone.
- Compiler-hidden generated values still need explicit ownership.
- Machine-computed gates are stronger than prose approval.
- Per-step decisions and terminal workflow outcomes are distinct state layers.

## Design Review Practices To Retain

Status: `frontend requirement`

Use these practices when reviewing DSL, frontend, compiler, or migration
designs:

- Architecture docs choose direction and name required contracts; normative
  runtime and validation behavior belongs in `specs/`.
- A frontend artifact that parses, typechecks, lowers, validates, or dry-runs is
  not automatically promotable. Promotion requires parity evidence for outputs,
  terminal states, artifacts, resume behavior, and accepted differences.
- Structured state, artifact values, contracts, snapshots, and semantic IR are
  authority. Reports, stdout, pointer files, debug projections, and source maps
  are views unless a specific contract says otherwise.
- Do not invent fake proof. For example, an `output_bundle` value is not
  variant-specific proof unless a variant-proof surface or compiler-owned
  projection establishes that proof.
- Compiler-hidden generated values still need owners, binding rules, validation
  timing, debug visibility, resume reconstruction, and public API boundaries.
- Prefer generic composition and stdlib lowering over name-specific compiler
  branches. If a compiler-special branch becomes necessary, revise the design
  before promotion.
- Keep per-step decisions separate from terminal workflow outcomes. For example,
  `REVISE` is a review decision, not completion.
- Exhaustion is explicit terminal non-completion, not approval and not hidden
  control-flow failure.
- Schema-backed JSON is acceptable only when a named schema or certified adapter
  validates it before publication and consumption.
- Promotion gates should be machine-computed from evidence. Authors must not
  assert non-regression by hand.
- Reconcile dependent docs when authority changes, especially drafting guides
  and stdlib/lowering docs.

## 1. Semantics Precede Syntax

Status: `frontend requirement`

Surface syntax is not the language's source of truth. YAML, Lisp, or any future
frontend are authoring surfaces over the same validated workflow semantics.

A frontend is acceptable only if it preserves or strengthens the core semantics.

## 2. Frontends Target Core AST, Not YAML Text

Status: `frontend requirement`

The Lisp frontend must lower to the shared core workflow AST and then through
the shared validation, semantic IR, and executable IR pipeline.

Generated YAML may exist as a debug, audit, or migration artifact. It must not
be the authoritative compiler target.

```text
frontend source
  -> frontend AST
  -> macro/procedure elaboration
  -> core workflow AST
  -> shared validation
  -> semantic IR
  -> executable IR
```

## 3. Do Not Hide Unresolved Semantics Behind Macros

Status: `frontend requirement`

Macros and frontend forms must generate proven core semantics. They must not
hide brittle behavior, unresolved authority questions, untyped side effects, or
runtime assumptions.

A macro that merely makes fragile YAML shorter is not a valid abstraction.

## 4. Prefer Typed Transitions Over Gates

Status: `future direction`

The language should model workflow progress as typed state transitions, not as
gate checks.

A gate asks:

```text
May I continue?
```

A transition states:

```text
State S changed to state S' because event E occurred, producing typed artifacts A.
```

Gate-shaped forms such as recovery gates, file-existence gates, status-string
gates, and markdown-parsing gates should be treated as design smells.

## 5. Resume Is State Reuse, Not Recovery

Status: `future direction`

Reusable prior work should be modeled as canonical state reuse.

Prefer:

```text
resume_or_start
```

over:

```text
recovery_gate
recover_or_run
check_previous_outputs
```

A resumed branch and a fresh branch must normalize to the same typed result.

## 6. Structured State Is Authoritative

Status: `current invariant`

Semantic workflow state must be represented as typed structured data: records,
unions, bundles, contracts, and IR values.

Human-readable text must not be the source of semantic truth.

## 7. Reports Are Views, Not State

Status: `current invariant`

Markdown reports may be produced, published, reviewed, and displayed.

New high-level workflow semantics must not parse reports to recover semantic
fields such as:

- `blocker_class`
- `review_decision`
- `phase_status`
- `drain_status`
- `selected_item_path`

Text extraction from reports is allowed only inside explicitly marked legacy
adapters or compatibility surfaces, with fixtures and deprecation markers.

## 8. Artifact Values Are Authoritative

Status: `v2.14 invariant`

An artifact value is the semantic authority.

A pointer file is only an optional materialized representation of that value.
Published artifacts store artifact values, not pointer-file paths.

Pointer files must not become hidden sources of truth.

## 9. Freshness Requires Evidence, Not Timestamps

Status: `v2.14 invariant`

mtime-only freshness must not be semantic authority.

Freshness should be based on durable evidence such as:

- before absent, after present
- before present, after present with different `sha256`

Timestamps may be recorded for debugging only.

## 10. Validate Before Committing

Status: `v2.14 invariant`

A structured output bundle must be fully validated before it becomes canonical
state.

The required pattern is:

1. construct candidate in memory
2. validate contracts and variant rules
3. write temporary file
4. atomic rename to canonical path
5. expose artifacts only after successful commit

Invalid bundles must not be left behind as canonical resume state.

## 11. Contracts May Only Narrow

Status: `v2.14 invariant`

When a value comes from an input, reference, artifact, or typed procedure
result, later declarations may refine its contract only by narrowing it.

They must not weaken, contradict, or erase the source contract.

## 12. Variant-Specific Values Require Proof

Status: `v2.14 invariant`

A discriminant may be globally available, but variant-specific fields are
available only under proof.

Valid proof sources include:

- `match` over the same discriminant
- explicit `requires_variant`
- compiler-generated proof context from a typed transition

General string predicates or ad hoc conditionals should not imply variant proof
unless explicitly supported by the semantic IR.

## 13. Procedural Composability Is First-Class

Status: `frontend requirement`

The language should support reusable workflow procedures, not only reusable
syntax.

Core authoring forms should include:

- `defworkflow`: exported callable workflow
- `defproc`: reusable effectful workflow procedure
- `defun`: pure helper
- `defmacro`: compile-time syntax transformer
- `defrecord`: product type
- `defunion`: tagged outcome type
- `defmodule`: namespace and exports

A real frontend should enable typed calls, lexical bindings, pattern matching,
and reusable workflow functions.

## 14. Macros Are Syntax; Procedures Are Behavior

Status: `frontend requirement`

Macros transform syntax.

Procedures represent reusable workflow behavior.

A construct with effects, provider calls, command calls, artifact publication,
state mutation, or workflow calls should be modeled as a typed procedure or
workflow, not merely as a macro.

## 15. Effects Must Be Explicit

Status: `frontend requirement`

Effectful forms must expose their effects to validation and IR.

Effects include:

- `reads`
- `writes`
- `publishes`
- `uses_provider`
- `uses_command`
- `calls_workflow`
- `updates_state`
- `moves_resource`
- `updates_ledger`
- `captures_snapshot`
- `materializes_pointer`

No macro, procedure, or frontend form may hide effects from the semantic IR.

## 16. Command Adapters Are Explicit Boundaries

Status: `frontend requirement`

Command steps are not inherently brittle. They are valid when they invoke an
external tool or a certified command adapter with typed inputs, typed outputs,
declared effects, fixtures, and source maps.

What is not acceptable in new high-level workflow code is hidden semantic glue:
inline Python or shell that rewrites state, parses reports, moves resources,
updates ledgers, checks status strings, or decides workflow outcomes without a
typed contract.

Procedural behavior must be represented as one of:

- a typed workflow procedure;
- a typed workflow call;
- a certified command adapter;
- a runtime-native effect.

See [Workflow Command Adapter Contract](workflow_command_adapter_contract.md)
for lint severity, allowlist metadata, migration sequence, and promotion
criteria.

## 17. Pure Helpers Must Remain Pure

Status: `frontend requirement`

Pure functions may compute paths, names, records, constants, schemas, and
static expressions.

Pure functions must not:

- read files
- write files
- call providers
- run commands
- inspect wall-clock time
- generate random values
- perform network access
- mutate workflow state

## 18. State Paths Should Be Derived, Not Hand-Managed

Status: `future direction`

High-level workflow code should not manually construct canonical state paths,
snapshot names, bundle paths, or pointer paths.

These should be derived from typed contexts such as:

- `RunCtx`
- `PhaseCtx`
- `ItemCtx`
- `DrainCtx`

Manual state path construction in high-level code is a lintable smell.

## 19. Resource Movement Is A Transition

Status: `future direction`

Moving a resource, updating a ledger, and exposing the resulting artifact state
should be one typed transition.

A resource transition must either commit coherently or fail before exposing new
semantic outputs.

## 20. Provider Decisions Produce Structured State

Status: `frontend requirement`

When a provider decides a workflow outcome, the provider protocol should produce
structured state: a typed bundle, tagged union, or validated command/provider
result. Markdown reports may accompany that state, but they remain views.

Provider-result and command-result forms should lower to output contracts,
variant contracts, prompt-contract injection where applicable, validation
before commit, and source-mapped artifact exposure. Prose-only provider results
belong behind legacy adapters during migration.

## 21. Higher-Order Workflow Composition Is Allowed, But Checked

Status: `future direction`

Workflow references may be passed as parameters for patterns such as backlog
drains, selectors, item runners, and gap drafters.

Such references must be statically resolved or module-linked,
signature-checked, version-checked, and effect-checked.

They must not become arbitrary runtime code loading.

## 22. Debug Projections Are Non-Authoritative

Status: `current invariant`

Debug YAML, rendered plans, reports, trace files, pointer files, and
human-readable summaries are projections.

They may aid inspection, review, testing, and migration.

They must not override typed state, artifact values, contracts, snapshots, or
semantic IR.

## 23. Legacy Adapters Are Quarantine Zones

Status: `frontend requirement`

Legacy adapters may bridge old scripts, pointer conventions, report parsers, or
command protocols.

They must be:

- explicitly marked legacy
- fixture-tested
- source-mapped
- linted
- preferably deprecated
- kept out of new high-level workflow abstractions

Legacy adapters are a subset of the broader certified-command-adapter boundary:
they are allowed only because they quarantine compatibility debt.

## 24. Source Maps Are Semantic Infrastructure

Status: `frontend requirement`

Every generated core AST node, semantic IR node, and executable step should map
back to the frontend source form that produced it.

Diagnostics should report:

- source file
- source span
- source form
- macro/procedure expansion stack
- generated core node
- semantic validation error

No abstraction is acceptable if it makes workflow failures harder to explain.

## 25. Lints Should Detect Semantic Smells

Status: `frontend requirement`

The compiler should lint for patterns that indicate brittle authoring,
including:

- manual state paths in high-level code
- markdown report parsing
- line-prefix semantic extraction
- pointer paths used as semantic values
- `variant_output` with no variant-specific fields
- manual `when` + `requires_variant` pairing
- mtime freshness checks
- resource moves outside `resource_transition`
- recovery gates instead of `resume_or_start`
- string status gates instead of typed unions
- hidden macro effects
- hidden semantic inline Python or shell
- command adapters without typed contracts

## 26. High-Level Constructs Must Reduce Brittleness

Status: `frontend requirement`

A new language form is justified only if it reduces at least one recurring
correctness burden:

- manual state management
- manual pointer management
- manual variant proof
- manual outcome routing
- manual resource transition logic
- manual recovery branching
- manual snapshot/candidate bookkeeping
- manual provider output validation
- manual report parsing

A construct that only reduces punctuation or indentation is not sufficient.

Do not promote every script into a runtime primitive. Promotion is justified
when the behavior needs runtime-level atomicity, resumability, source-map
fidelity, path-safety enforcement, or semantic IR visibility that a certified
command adapter cannot provide.

## 27. Preserve The Deterministic Runtime Model

Status: `frontend requirement`

The frontend must preserve the project's deterministic workflow model:

- explicit inputs
- strict contracts
- sequential or explicitly modeled control flow
- auditable provider calls
- validated command outputs
- filesystem-native run state
- reproducible artifact lineage

The frontend may make workflows more composable, but it must not make execution
less inspectable or less deterministic.

## Relationship To Normative Specs

This document is design guidance. The stable subset should eventually be
promoted into a normative semantic-authority spec covering:

- structured state versus reports
- artifact values versus pointer files
- validation-before-commit
- contract narrowing
- variant proof
- snapshot/hash evidence
- debug projections as non-authoritative views

Until that spec exists, field-level normative behavior remains in the existing
spec modules, especially `specs/dsl.md`, `specs/state.md`, `specs/security.md`,
and `specs/versioning.md`.
