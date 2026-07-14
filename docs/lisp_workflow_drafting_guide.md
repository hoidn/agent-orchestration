# Workflow Lisp Drafting Guide

Status: informative
Preferred authoring frontend: Workflow Lisp / `.orc` where the required forms
are supported
Normative contracts: `specs/`
Primary audience: workflow authors, workflow-library maintainers, and
prompt/workflow reviewers
Compatibility audience: maintainers inspecting generated Core DSL/YAML,
migration fixtures, and legacy workflows

This guide explains how to author deterministic workflows using the Workflow
Lisp frontend. It is about authoring choices, not runtime implementation.
Normative DSL and runtime contracts live under `specs/`.

Design references:

- [Capability Status Matrix](capability_status_matrix.md)
- [Workflow Lisp Frontend Specification](design/workflow_lisp_frontend_specification.md)
- [Workflow Lisp Core Calculus And Compiler Middle-End](design/workflow_lisp_core_calculus_middle_end.md)
- [Workflow Lisp Frontend MVP Specification](design/workflow_lisp_frontend_mvp_specification.md)
- [Workflow Lisp Core Statement Taxonomy](design/workflow_lisp_core_stmt_taxonomy.md)
- [Workflow Lisp Semantic Workflow IR](design/workflow_lisp_semantic_workflow_ir.md)
- [Workflow Lisp Executable IR](design/workflow_lisp_executable_ir.md)
- [Workflow Lisp Macro Surface Contract](design/workflow_lisp_macro_surface_contract.md)
- [Workflow Lisp Frontend Standard Library Lowering](design/workflow_lisp_stdlib_lowering.md)
- [Workflow Lisp Parametric Type System](design/workflow_lisp_parametric_type_system.md)
- [Workflow Lisp Procedure-First Reuse Contract](design/workflow_lisp_procedure_first_reuse_contract.md)
- [Workflow Lisp Runtime Closures Boundary](design/workflow_lisp_runtime_closures_boundary.md)
- [Workflow Lisp Unified Frontend Design](design/workflow_lisp_unified_frontend_design.md)
- [Workflow Lisp Native Transportable Returns And Typed Result Guidance](design/workflow_lisp_native_transportable_returns.md)
- [Workflow Language Design Principles](design/workflow_language_design_principles.md)
- [Workflow Command Adapter Contract](design/workflow_command_adapter_contract.md)
- [Workflow Lisp Generic Core, Expression Surface, And Adapter Retirement](design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md)
- [Workflow Lisp Private Runtime State And Consumer Value Flow](design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md)
- [Workflow Lisp Runtime-Native Drain Authoring](design/workflow_lisp_runtime_native_drain_authoring.md)

Use this guide for authoring judgment. Use
[Capability Status Matrix](capability_status_matrix.md) for current
availability and copy-safety status. Use the component-contract docs for
current-checkout behavior. Use the unified design for future or deferred
surfaces. Use [Workflow Lisp Runtime-Native Drain Authoring](design/workflow_lisp_runtime_native_drain_authoring.md)
as the concrete checklist for Design Delta Drain-style authoring shape.
Use `specs/` for normative runtime and DSL behavior.

During the coexistence period, use [Workflow Drafting Guide](workflow_drafting_guide.md)
for YAML-specific authoring guidance. When the YAML guide is deprecated, preserve
it as a compatibility guide rather than deleting it.

Use `.orc` for new high-level workflows when the needed frontend forms are
available and the workflow does not depend on runtime behavior that still exists
only in YAML. Use YAML only for:

- legacy workflows;
- compatibility fixtures;
- low-level runtime tests;
- debug projections;
- generated Core DSL inspection;
- cases not yet supported by the Lisp frontend.

For migrations, keep the existing YAML workflow authoritative until the `.orc`
version has compile, shared-validation, dry-run or smoke, and parity evidence.
Do not deprecate the YAML version only because an `.orc` version parses.

Before copying a checked-in `.orc` example or fixture, check
`docs/workflow_lisp_route_readiness_registry.json`. Registry labels provide
the copy-safety and route/readiness classification: `wcc_default` is current
WCC/schema-2 evidence, `legacy_schema1_compat` is compatibility evidence,
`migration_candidate` needs migration parity before promotion claims, and
`stale_needs_update` is not current guidance. Compiler and lowering tests that
cover registry entries should pin `LoweringRoute` explicitly unless the test
intentionally exercises `DEFAULT_LOWERING_ROUTE`; route identity and
`lowering_schema_version` are evidence freshness fields. Leaf compile/runtime
labels are useful progress evidence, but they are not promotable
workflow-family evidence.

Migration promotion checklist:

- Treat compile, typecheck, lower, shared validation, and dry-run as necessary
  evidence, not as promotion approval.
- Require output contract parity, terminal-state parity, artifact parity, and
  resume/reuse parity against the characterized YAML primary behavior.
- Let migration tooling compute `non_regressive`; do not write or approve that
  value by hand.
- Keep structured bundles, typed artifacts, runtime state, and variant proof as
  authority. Do not route migration behavior through reports, stdout, pointer
  files, or debug YAML.
- Do not expose compiler-generated write roots or result-bundle paths as public
  entrypoint inputs. Debug projections may show generated bindings only with
  origin metadata.
- Do not treat `output_bundle` fields as variant-specific proof. Use
  `variant_output`, `match` proof, `requires_variant`, or a compiler-owned
  validator/projection that establishes equivalent proof.
- Keep review decisions and terminal loop results separate. `REVISE` must run a
  revise/fix path or exhaust explicitly; it is not completion.
- Validate schema-backed JSON, such as carried review findings, before it is
  published to loop state and again before it is consumed after resume.
- Evidence paths are produced by workflow, checks, or materializer steps.
  Review providers inspect and judge evidence, but they should not author
  evidence identity. Do not put consumed evidence paths such as `checks_report`
  in provider output contracts unless the provider actually produces that
  artifact; carry them from state or inputs when terminal results need them.
- When a provider already owns a validated structured-output bundle path, use
  `provider-bundle-path` to expose a typed relpath view such as
  `selection_bundle_path`; do not add a helper script or pointer file that only
  echoes the same bundle identity.

When promotion evidence is evaluated with `python -m orchestrator
migration-parity`, treat the per-target JSON report as evidence authority only.
The tool computes `non_regressive`; it does not accept that field from the
manifest, and strict reuse validation can invalidate stale reports even when
their embedded evidence still looks superficially complete.

Use strict modes only when you want the command to act as a release gate:

- advisory mode (no extra flag) still writes reports and derived views, but it
  exits `0` whenever generation and validation succeed;
- `--require-non-regressive` exits `1` unless each selected target has a valid,
  complete, current report whose embedded evidence recomputes to
  `non_regressive=true`;
- `--require-promotable` exits `1` unless each selected target is both
  non-regressive and eligible for primary-surface promotion.

`non_regressive` and promotable are intentionally different. A target can be
non-regressive yet remain `primary_surface=yaml` because the migration design
still blocks promotion. The machine-readable gate decision lives in
`gate_evaluation.json`, not in the per-target report payload. Keep
`primary_surface`, `report_valid`, and `evidence_complete` as derived gate or
index views rather than authoring or editing them into parity reports.

For the most useful Workflow Lisp review/fix model for targeted design-doc
reviews, read `workflows/examples/review_revise_design_docs.orc`. It runs a
bounded stdlib `.orc` review/fix loop over a parameterized target design doc,
optional context docs, and review focus. Treat it as the preferred fresh
starting point for targeted design-doc review/fix authoring. The earlier
`workflows/examples/review_revise_parametric_design_docs.orc` remains useful
provenance for the real-life-tested review path, but it hardcodes one design
set and is not the preferred copy target.

For the smallest concrete Workflow Lisp teaching example, read
`workflows/examples/kiss_backlog_item.orc`. It shows a single backlog item
flowing through typed plan and implementation provider results plus bounded
review/fix loops. Treat it as a compact shared-validation reference and
inspiration corpus, not as a direct template for new workflows, not as the main
`.orc` model, and not as a production queue drain: it can compile and dry-run
through the `.orc` runtime bridge, but it does not include the selector, queue
movement, recovery, and parity evidence required to replace the mature YAML
backlog drains.

## Core Rule

Author narrow public workflow boundaries over typed procedures and structured
results. Workflows own public run/resume/invocation/publication identity;
procedures are the normal internal reuse unit.

Do not author brittle gates, pointer plumbing, report parsers, candidate-path
selectors, or manual state-file choreography.

Good high-level workflow code should look like typed composition:

```lisp
(defworkflow run-selected-backlog-item
  ((selection SelectionInput)
   (providers NeuripsProviders))
  -> SelectedItemResult

  (let* ((selected
           (resolve-selected-item selection))

         (plan
           (ensure-approved-plan
             :selected selected
             :providers providers.plan))

         (implementation
           (call implementation/run
             :inputs (make-implementation-inputs selected plan)
             :providers providers.implementation)))

    (finalize-selected-item
      :selected selected
      :plan plan
      :implementation implementation)))
```

It should not look like low-level runtime plumbing:

```lisp
(step ...)
(pre-snapshot ...)
(select-variant-output ...)
(requires-variant ...)
(write-pointer ...)
(parse-markdown-report ...)
```

Those lower-level concepts may still exist after lowering, but they should not
dominate high-level authored Lisp.

## Runtime-Native Authoring Direction

For new high-level Workflow Lisp, pass typed domain values by default and let
lowering/runtime own execution mechanics.

Preferred authoring shape:

- provider calls receive typed prompt-input records or small typed values;
- private runtime context, generated paths, checkpoint identity, and write roots
  are hidden from public entrypoints and ordinary user-facing calls;
- deterministic local reshaping uses pure typed projection instead of Python;
- durable state changes use `resource-transition` or certified transition
  adapters;
- prompt text, public summaries, observability, and compatibility files are
  renderings at consumer seams; and
- body-level `materialize-view` is reserved for justified timed publications or
  low-level compatibility work.

For example, the high-level call should usually be:

```lisp
(run-work-item item)
```

not:

```lisp
(run-work-item item item-ctx state-root artifact-root summary-path)
```

The compiler/runtime may still bind a private item/resource context in
executable IR. That context is visible in source maps, Semantic IR, and build
evidence, but it is not a public authored workflow input.

## Prompt Externs

Prompt externs are compile-time build bindings, not workflow-boundary inputs.
They tell the Workflow Lisp frontend which shared provider prompt source field
to emit when a workflow refers to a named prompt extern.

- String shorthand means `asset_file`.
- Use `asset_file` for reusable library prompts and other workflow-source-owned
  prompt assets.
- Use explicit `input_file` object bindings for workspace-owned or
  runtime-generated prompt material.
- Runtime prompt existence checks, path-root enforcement, and prompt-read
  diagnostics still belong to the shared provider/runtime layer.

Examples:

```json
{
  "prompts.implementation.execute": "prompts/implementation/execute.md",
  "prompts.project.review": {
    "input_file": "prompts/workspace/project-review.md"
  }
}
```

## 1. Mental Model

Think in five layers.

| Layer | Author concern | Typical `.orc` forms | Runtime/lowering concern |
| --- | --- | --- | --- |
| Types and contracts | What values exist? | `defpath`, `defenum`, `defrecord`, `defunion`, `defschema` | Contracts, path safety, artifact shapes |
| Procedures and workflows | Which boundary is public, and what behavior is internally reusable? | `defworkflow`, `defproc`, `defun`, `call`, `let*` | Public run/resume identity, graph structure, procedure lowering, workflow calls |
| Structured results | What did a provider or command produce? | `provider-result`, `command-result`, `match` | Output validation, prompt contract, variant proof |
| Transitions | What state changed? | `resume-or-start`, `resource-transition`, `review-revise-loop`, `backlog-drain` | Atomic commit, durable state, effects |
| Runtime substrate | How is it executed? | Usually not hand-authored | Core AST, semantic IR, snapshots, bundles, artifacts |

The authoring pipeline is:

```text
.orc source
  -> frontend AST
  -> macro/procedure elaboration
  -> Core Workflow AST
  -> shared validation
  -> validated executable IR
  -> derived runtime plan and semantic IR
  -> existing runtime
```

Generated YAML, if emitted, is a debug projection. It is not semantic or
executable authority.

The first question is not "which YAML field do I need?"

Ask these first:

- What typed input does this workflow receive?
- What typed result does it return?
- Does this need durable public run/resume/invocation/publication identity, or
  is it an internal procedure or pure helper?
- Which provider, command, filesystem, state, or ledger effects occur?
- Which result is fixed-shape state and which result is an outcome union?
- Where should variant proof be established?
- Which state transition is being performed?

If the answer starts with "I need a step that checks whether a file exists,"
step back. You probably need a typed result, a transition, or a certified
adapter.

## 2. Availability Model

The Lisp frontend now supports substantially more than the original MVP, but
current compiler behavior, current component contracts, future design targets,
and production workflow migration are separate questions.

For current availability and copy-safety status, start with
[Capability Status Matrix](capability_status_matrix.md). This section explains
the status labels used in authoring guidance; the matrix is the routing table
for individual surfaces.

Use these labels in docs and examples when needed:

| Label | Meaning |
| --- | --- |
| Implemented | Accepted by the current compiler and covered by local fixtures/tests |
| Library | Standard-library form; may lower to existing primitives or certified adapters |
| Designed | Part of the accepted design, but not yet implemented |
| Future | Intended direction, not yet available |
| Legacy | Compatibility-only; avoid in new workflows |

The currently implemented authoring surface includes:

- `defenum`
- `defpath`
- `defrecord`
- `defunion`
- `defschema`
- `defworkflow`
- `defproc`
- `defun`
- `defmacro`
- modules, imports, and exports
- `let*`
- `if`, including computed pure `Bool` conditions
- the closed pure-expression operator surface (`=`, `!=`, `<`, `<=`, `>`,
  `>=`, `and`, `or`, `not`, `+`, `-`, `*`, `min`, `max`, `string/concat`,
  `string/empty?`, `symbol/name`, `some?`, `or-else`, `record-update`),
  lowering through compiler-generated `pure_projection` steps; see Section 9A
- `match`
- `loop/recur`
- `call`
- `WorkflowRef[...]` and `(workflow-ref ...)`
- native returns for every currently transportable type across workflows,
  providers, commands, procedures, and workflow calls when targeting the
  public DSL v2.15
- `provider-result`
- `command-result`
- `with-phase`
- `phase-target`
- `run-provider-phase`
- `resume-or-start`
- `review-revise-loop` as an implemented authoring surface; the ordinary
  imported stdlib lowering route exists in the current checkout, while
  primary-migration parity evidence for each workflow family remains governed
  by
  `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `resource-transition` through declared runtime-native transitions, with
  certified adapters only as explicit compatibility backends
- `finalize-selected-item`
- `backlog-drain`
- debug YAML renderer
- source-map and build-artifact emission

The ProcRef tranche currently supports compile-time-only procedure composition:
`ProcRef[...]` type annotations, explicit `(proc-ref ...)` literals,
module-aware resolution and diagnostics, keyword-only `bind-proc` partial
application, residual-signature specialization before lowering, forwarding
through `ProcRef[...]` parameters, and lexical invocation through ProcRef-bound
call heads. ProcRef values are still compile-time-only: they cannot cross
runtime transport seams or survive into executable runtime state.

Current component-contract boundaries:

- current macro support is implemented, deterministic, and bounded by
  [Workflow Lisp Macro Surface Contract](design/workflow_lisp_macro_surface_contract.md);
- standard-library forms are ordinary authoring guidance only when their
  lowering contract is supported and their generated effects/source maps remain
  visible; see [Workflow Lisp Frontend Standard Library Lowering](design/workflow_lisp_stdlib_lowering.md);
- Semantic IR and Executable IR are formalized current-checkout component
  contracts, but they have different authority lanes: Semantic IR is semantic
  authority, and Executable IR is executable authority;
- Core statement-family identity comes from the current shared Core AST
  taxonomy, not from ad hoc frontend-only statement names.

Designed or future, but not current authoring:

- runtime first-class procedures or closures
- provider-selected or command-produced procedure values
- procedure values stored in workflow outputs, records, unions, artifacts,
  provider results, command results, state, ledgers, or loop-carried runtime
  state
- dynamic runtime procedure dispatch
- stronger multi-resource transactional backends beyond the current
  runtime-native transition contract
- generic `defworkflow` headers or type-parameterized workflow entrypoints

Runtime closures remain future runtime-owned callable values. Current work only
proves disabled-profile rejection and source-map diagnostics. Do not author
runtime closure values, dynamic procedure dispatch, or procedure-valued runtime
state.

Native returns and typed guidance are landed: a `.orc` source declaring
`(:target-dsl "2.15")` may
return `Bool`, `Int`, `Float`, `String`, an enum, a declared path, an
`Optional[T]`, a `List[T]`, or a `Map[String, T]` directly from
`defworkflow`, `provider-result`, `command-result`, effectful `defproc`, and
workflow calls, without wrapping it in a one-field record. Typed result
guidance uses `(result T :description ... :format-hint ... :example ...)`, and
record/union payload fields accept the same optional keys. Examples are typed
pure constants. Path examples must be safe but need not exist at compile time.
DSL v2.15 is public through ordinary loader entrypoints. Follow the
[Capability Status Matrix](capability_status_matrix.md) for current status.

Some migration slices now have evidence, but YAML remains authoritative for a
workflow until that specific `.orc` version has compile, shared-validation,
dry-run or smoke, and parity evidence.

Do not present a form as ordinary authoring guidance unless the guide labels
whether it is implemented, library-backed, designed, future, or legacy.

## 3. Semantic Authority Rules

These rules are frontend-independent. They apply to `.orc`, generated Core AST,
generated/debug YAML, and runtime IR.

Semantic IR is the typed semantic authority surface for validated workflows.
Executable IR is the validated executable authority surface. Runtime plans,
source maps, debug YAML, summaries, and reports are derived views unless a
specific contract says otherwise.

### 3.1 Structured State Is Authority

Structured records, unions, bundles, and typed artifacts are semantic authority.

Reports, rendered plans, summaries, debug YAML, logs, and pointer files are
views or materialized representations.

Bad:

```lisp
(command-result extract-blocker
  :argv ("python" "scripts/extract_line.py" "--prefix" "Blocker Class:")
  :returns BlockerClass)
```

Better:

```lisp
(defunion ImplementationAttempt
  (COMPLETED
    (execution-report Path.execution-report))
  (BLOCKED
    (progress-report Path.progress-report)
    (blocker-class BlockerClass)
    (blocker-reason String)))

(provider-result providers.execute
  :prompt prompts.implementation.execute
  :inputs (inputs.design inputs.plan)
  :returns ImplementationAttempt)
```

The provider may write a markdown report, but the markdown report is not parsed
later to recover semantic state.

### 3.2 Reports Are Views

Use reports for human review, provenance, explanation, and diagnostics.

Do not use reports as the only source of:

- review decision;
- blocker class;
- phase status;
- selected item path;
- drain status;
- resource transition result.

If a report contains those values, the same values must also exist in structured
state.

### 3.3 Artifact Values Are Authority

A path artifact value is the semantic value. A pointer file may contain or
represent that value, but the pointer file path is not the value unless the
contract explicitly says so.

Bad:

```text
execution-report := "state/execution_report_path.txt"
```

Better:

```text
execution-report := implementation.execution-report
```

The runtime may materialize `state/execution_report_path.txt` for a legacy
command or prompt, but that file is a representation.

### 3.4 Freshness Requires Durable Evidence

Do not use mtime-only freshness for routing or semantic selection.

Use snapshot/hash evidence through the lowered runtime substrate. High-level
`.orc` should normally express `provider-result`, `command-result`, or another
structured producer result. The compiler/runtime may lower that to snapshots,
content hashes, validated bundle commits, and variant selection.

mtime may be recorded for debugging only.

### 3.5 Validate Before Committing State

Canonical state should be visible only after validation succeeds.

The intended sequence is:

1. build candidate result;
2. validate type, contract, path, variant, and effect constraints;
3. write temp state;
4. atomically rename;
5. expose typed artifacts;
6. publish values.

Do not leave invalid canonical state behind for resume/recovery.

### 3.6 Contracts May Only Narrow

If a value comes from an input, artifact, or reference, later declarations may
refine it only by narrowing. They may not weaken:

- type;
- path kind;
- `under` root;
- must-exist requirement;
- target-existence requirement;
- variant availability.

### 3.7 Variant-Specific Fields Need Proof

For unions, the discriminant is always available. Variant-specific fields are
available only inside a proof context.

Good:

```lisp
(match attempt
  ((COMPLETED c)
    c.execution-report)

  ((BLOCKED b)
    b.progress-report))
```

Bad:

```lisp
attempt.execution-report
```

A computed pure `Bool` condition, such as `(= status "READY")`, may route
control flow, but it is proof-neutral: it does not unlock variant-specific
fields, optional payloads, or union narrowing. `match` remains the only
construct that establishes variant proof.

### 3.8 Do Not Hand-Manage Runtime State

Avoid hand-authoring:

- state bundle paths;
- snapshot names;
- candidate paths;
- temporary bundle paths;
- pointer files;
- report line-prefix extractors;
- manual variant selectors;
- manual gate outputs.

If high-level `.orc` contains many of those, it is probably written at the wrong
abstraction level.

## 4. Choosing The Right Authoring Unit

Use the smallest unit that represents the behavior truthfully.

| Need | Use | Avoid |
| --- | --- | --- |
| Durable public run/resume/invocation/publication boundary | `defworkflow` | Workflow solely for internal reuse |
| Reusable effectful graph behavior | `defproc` | Copy-pasted steps |
| Pure path/record/schema helper | `defun` | Command step |
| Compile-time syntax abbreviation | `defmacro` | Effectful macro |
| Provider returns structured state | `provider-result` | Markdown parsing |
| Command returns structured state | `command-result` | Stdout scraping |
| Outcome-shaped result | `defunion` + `match` | Stringly gates |
| Fixed-shape result | `defrecord` | Fake tagged union |
| Queue/ledger movement | `resource-transition` or certified adapter | Shell move + hidden ledger update |
| Resume prior state or run fresh | `resume-or-start` | Recovery gate |
| Review/fix loop | `review-revise-loop` where its lowering contract is supported for the promotion target | Raw back-edge or shell counter |
| Select/run/gap/repeat | `backlog-drain` | Hand-authored drain loop |

## 5. Types First

Start every workflow family by defining the values it moves across boundaries.

### 5.1 Paths

Use `defpath` for reusable path contracts.

```lisp
(defpath Path.state-file
  :kind relpath
  :under "state"
  :must-exist false)

(defpath Path.state-existing
  :kind relpath
  :under "state"
  :must-exist true)

(defpath Path.execution-report
  :kind relpath
  :under "artifacts/work"
  :must-exist true)

(defpath Path.execution-report-target
  :kind relpath
  :under "artifacts/work"
  :must-exist-target false)

(defpath Path.progress-report
  :kind relpath
  :under "artifacts/work"
  :must-exist true)

(defpath Path.check-commands
  :kind relpath
  :under "state"
  :must-exist true)
```

A value of type `Path.execution-report` is the report path value. It is not the
pointer file path.

### 5.2 Enums

Use `defenum` for stable decision tokens.

```lisp
(defenum DrainStatus
  CONTINUE
  BLOCKED
  EMPTY)

(defenum BlockerClass
  missing_resource
  unavailable_hardware
  roadmap_conflict
  external_dependency_outside_authority
  user_decision_required
  unrecoverable_after_fix_attempt)
```

For the first-tranche parametric review/revise route, `ReviewDecision` is not a
two-value enum example. That route uses the stdlib-owned `ReviewDecision` union
defined in
`docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`.

Enums support contract validation, stable equality-based routing,
prompt-contract generation, and typed diagnostics. Workflow Lisp `match`
currently consumes unions, not enums; use `if` with same-type enum equality
when routing on an enum value.

### 5.3 Records

Use `defrecord` for fixed-shape state.

```lisp
(defrecord ImplementationInputs
  (design Path.design)
  (plan Path.plan)
  (check-commands Path.check-commands)
  (execution-report-target Path.execution-report-target)
  (checks-report-target Path.checks-report-target)
  (review-report-target Path.review-report-target))
```

Use a record when all fields are part of one fixed shape. Good candidates are
workflow inputs, provider settings, resolved selected-item inputs, target path
bundles, command result bundles, and context records.

### 5.4 Unions

Use `defunion` for outcome-shaped state.

```lisp
(defunion ImplementationAttempt
  (COMPLETED
    (execution-report Path.execution-report))

  (BLOCKED
      (progress-report Path.progress-report)
      (blocker-class BlockerClass)
      (blocker-reason String)))
```

Use a union when different outcomes have different valid fields. Do not use a
union when every variant has the same fields. That is a fixed-shape record with
an enum field.

Construct one declared union variant with the explicit `variant` form:

```lisp
(variant ImplementationAttempt COMPLETED
  :execution-report execution-report-path)
```

Keep the union type and variant name explicit. Use the same keyword/value field
shape as `record`. Constructing a union does not prove later field access;
variant-specific reads still need `match` or another proof-bearing path.

Bad:

```lisp
(defunion SelectedItemInputs
  (ACTIVE_SELECTION)
  (RECOVERED_IN_PROGRESS))
```

Better:

```lisp
(defrecord SelectedItemInputs
  (selection-mode SelectionMode)
  (selected-item-active-path Path.backlog-active)
  (selected-item-in-progress-path Path.backlog-in-progress)
  (selected-item-context-path Path.state-existing)
  (check-commands-path Path.state-existing))
```

### 5.5 Schemas

Use `defschema` when several records share a field group.

```lisp
(defschema ReportTargets
  (execution-report-target Path.execution-report-target)
  (checks-report-target Path.checks-report-target)
  (review-report-target Path.review-report-target))
```

A schema is not a workflow. It is reusable contract structure.

## 6. Workflows, Procedures, Pure Helpers, And Macros

### 6.1 `defworkflow`

Use `defworkflow` for durable public workflow boundaries.

```lisp
(defworkflow implementation/run
  ((ctx PhaseCtx)
   (inputs ImplementationInputs)
   (providers ImplementationProviders))
  -> ImplementationResult

  ...)
```

Current parameter forms are:

- `(name Type)`
- `(name Type :default <literal>)`

Use `:default` only on public workflow-boundary inputs that flatten to one
workflow input contract. Supported authored defaults in the current slice are:

- string literals for `String` and path / relpath boundary types
- integer literals for `Int`
- float literals for `Float`
- boolean literals for `Bool`
- enum-member symbols for enum boundary types

Do not use `:default` for record or union boundaries, collections, `nil`,
`WorkflowRef`, `ProcRef`, or computed expressions. Omitting a defaulted binding
uses the callee's compiled workflow-input default; passing a value still
overrides the default.

Use `defworkflow` when:

- operators or external callers run or resume the unit directly;
- the unit has an externally invocable CLI/API workflow-entry registration or
  export contract;
- the unit has an independently addressable child-workflow identity;
- the unit owns stable public inputs, defaults, outputs, or terminal lifecycle;
- the unit should appear as an operator-visible workflow boundary in run state;
- the unit owns public artifact names or publication policy; or
- callers depend on its independent checkpoint/state namespace.

Keep workflow boundaries narrow. Pass typed inputs in and typed outputs out.
Being called from another unit or belonging to a library does not by itself
justify `defworkflow`; ordinary module export of a reusable procedure is not a
workflow-entry export. Use `defproc` for internal reuse.

### 6.2 `defproc`

Use `defproc` for reusable internal effectful graph behavior.

Status boundary: the procedure-first migration and private-workflow adoption
rules below are accepted design but remain Stage 5-gated. Do not promote a
family on this guidance alone; use the capability matrix and procedure-first
roadmap for current availability and pilot readiness.

```lisp
(defproc ensure-approved-plan
  ((ctx PhaseCtx)
   (selected SelectedItemInputs)
   (roadmap RoadmapState)
   (providers PlanProviders))
  -> PlanGateResult

  :effects
    ((reads selected.selected-item-context-path)
     (uses-provider providers.generate providers.review)
     (writes Path.plan-target)
     (writes Path.review-report)
     (updates-state ctx))

  ...)
```

A macro rewrites syntax. A procedure represents reusable internal workflow
behavior. If
the abstraction has effects, prefer `defproc` or a compiler-owned
standard-library form over `defmacro`.

Procedure-first migrations select `:lowering inline` explicitly. Inline
lowering keeps runtime state, checkpoint, resume, and publication ownership on
the retained public workflow. Use `:lowering private-workflow` only when the
migration contract and evidence identify a private state, resume, or debug
namespace; the generated boundary remains internal and does not replace a
public workflow.
In the current slice, that namespace need is recorded in migration evidence;
it is not a new source annotation beyond choosing the
`:lowering private-workflow` mode.
`:lowering auto` remains available for identity-free helpers, but its selected
route is not a stable persisted identity promise. Keep a `defworkflow`
boundary whenever its public run/resume/invocation/publication identity is part
of the contract.

Procedure effects have two useful views. The direct summary covers effects
introduced by the body. The caller-visible transitive summary also includes
called procedures, selected ProcRef hooks, and child workflows. The accepted
model requires generic specialization to recompute that transitive summary
after type and ProcRef resolution and before lowering. Provider, command,
transition, bridge,
publication, and child-workflow effects must remain explicit. Returning a
value or artifact from a procedure never publishes it implicitly; public
publication stays on the workflow boundary.

This is accepted semantics, not current carrier shape. Today
`procedure_typecheck.direct_effects` conservatively includes callee transitive
effects. Mandatory Stage 5 substrate work must establish a distinct body-local
direct view and recompute the caller-visible transitive view after
specialization before the pilot.

Current parametric boundary: generic `defproc` headers with `:forall` are
implemented for compile-time-only specialization. The compiler infers concrete
type bindings from call sites, materializes monomorphic specializations before
lowering, and erases those type parameters before runtime-visible artifacts
such as lowered workflows, source maps, Semantic IR, and Executable IR are
emitted. `:where` clauses for generic `defproc` use the fixed clause order
`:forall`, params, `:where`, `->`. The constraint vocabulary, subset
semantics, and specialization pipeline are owned by
[Workflow Lisp Parametric Type System](design/workflow_lisp_parametric_type_system.md);
the stable spellings, summarized:

- `(T is-record)`
- `(T is-union)`
- `(T has-field field Type)`
- `(T has-union-variant VARIANT)`
- `(T has-union-variant VARIANT (field Type) ...)`
- `(T has-shared-union-field field Type)`

The `Type` position in `has-field`, `has-union-variant`, and
`has-shared-union-field` may name another `:forall` parameter, which is how
cross-parameter contracts are expressed — for example, constraining a hook's
payload parameter to be the same type as the selector union's
`SELECTED.selection` field.

Constraint checks run against resolved concrete call-site types before the
specialization is accepted, and every clause carries subset semantics: it
proves a required capability; no clause forbids extra caller fields or
variants or proves exact shape. `has-shared-union-field` is intentionally
narrow: it allows branch-free projection only of the named field after the
constraint is validated; it does not prove which variant is present, and it
does not make variant-specific fields available outside a proof-bearing
`match` — and adding a caller variant that lacks the shared field breaks that
constraint. Variant and field names referenced by a stdlib definition's
`:where` clauses are frozen public vocabulary for callers. Generic
`defworkflow` remains out of scope in the current compiler surface.

### 6.3 `defun`

Use `defun` for pure helper logic.

```lisp
(defun phase-target
  ((ctx PhaseCtx)
   (name String))
  -> Path.state-file

  (path/join ctx.state-root name))
```

A `defun` may construct records, construct symbolic paths, select fields,
combine strings, compute constants, and build type-level descriptors. Pure
computation inside a `defun` uses the closed pure-expression operator surface
(Section 9A); the body either folds at compile time or lowers to the same
pure-expression payload the runtime evaluator executes.

A `defun` may not read files, write files, call providers, call workflows, run
commands, inspect wall-clock time, or generate random values.

If it has an effect, it is not a `defun`.

### 6.4 `defmacro`

Macros are for syntax, not hidden workflow behavior.

A macro may construct AST, introduce hygienic bindings, expand shorthand into
typed forms, and emit source-map frames.

A macro may not perform filesystem I/O, perform network I/O, depend on
wall-clock time, call providers, run commands, weaken contracts, emit executable
IR directly, or hide effects.

The current `defmacro` surface is a deterministic frontend-only syntax
expander. It supports top-level template macros, hygienic introduced names,
imported macro visibility, source-map provenance, and validation through the
ordinary frontend pipeline. It does not support compile-time I/O, runtime macro
values, intentional capture syntax, alternate validators, or direct Semantic IR
or Executable IR generation.

Macro-origin failures are owned by the same layer that would own the expanded
form without a macro. Macro provenance is additive; it does not create a second
validation stack. See the macro surface contract for the current diagnostic
ownership matrix.

Ordinary workflow authors should rarely need user-defined macros. Prefer
standard-library procedures and compiler-owned forms until there is evidence
that custom macros are needed.

## 7. Modules, Imports, And Exports

Use modules to make workflow libraries navigable.

```lisp
(defmodule neurips.implementation
  (import neurips.common :as common)
  (export
    ImplementationInputs
    ImplementationProviders
    ImplementationResult
    run)

  ...)
```

Prefer explicit imports:

```lisp
(import neurips.implementation :as impl)
(import neurips.plan :as plan)
```

Then call workflows clearly:

```lisp
(call impl/run
  :ctx implementation-ctx
  :inputs implementation-inputs
  :providers providers.implementation)
```

Rules:

- export only stable workflow/library surfaces;
- keep internal helpers private;
- avoid wildcard imports;
- avoid duplicate names that canonicalize to the same field name.

## 8. Structured Provider Results

Use `provider-result` when a provider produces structured state.

`:returns` may name a record, a union, or (with `(:target-dsl "2.15")`) any
other currently transportable type directly — `Bool`, `Int`, `Float`,
`String`, an enum, a declared path, `Optional[T]`, `List[T]`, or
`Map[String, T]`. A direct return lowers to one generated `output_bundle`
field named `__result__` with `json_pointer: ""`; the provider writes the
plain JSON value, and authored code never names `__result__`.

```lisp
(let* ((attempt
         (provider-result providers.execute
           :prompt prompts.implementation.execute
           :inputs (inputs.design inputs.plan)
           :returns ImplementationAttempt)))

  ...)
```

The provider must produce structured output matching the return type. The
result travels through one channel: a validated bundle written at the
runtime-bound output location the provider receives with its injected
output contract. JSON printed to stdout is never the result — stdout and
stderr are observability evidence only, for providers and commands alike.
The bound-path bundle is the current sanctioned transport, not part of the
authored contract: `:returns` declares the contract, and any future result
channel must pass the same fail-closed validation.

Markdown reports may be written and referenced by fields in the structured
result, but the report is not parsed later for semantic state.

Good pattern:

```lisp
(let* ((attempt
         (provider-result providers.execute
           :prompt prompts.implementation.execute
           :inputs
             (inputs.design
              inputs.plan)
           :targets
             ((execution-report inputs.execution-report-target)
              (progress-report (phase-target ctx "progress-report.md")))
           :returns ImplementationAttempt)))

  (match attempt
    ((COMPLETED c)
      (review-completed-implementation
        :ctx ctx
        :inputs inputs
        :execution-report c.execution-report
        :providers providers))

    ((BLOCKED b)
      b)))
```

Bad pattern:

```lisp
(let* ((report
         (provider-result providers.execute
           :prompt prompts.implementation.execute
           :returns Path.execution-report))

       (blocker-class
         (command-result parse-blocker-class
           :argv ("python" "extract_line.py" report "Blocker Class:")
           :returns BlockerClass)))

  ...)
```

This turns a human-facing report into semantic state. That belongs only in a
marked legacy adapter.

### Prompt Obligations

The return type defines the structured result contract.

Prompts should describe:

- task objective;
- scope boundaries;
- required structured output;
- human-facing report expectations;
- forbidden shortcuts;
- domain-specific evidence requirements.

Prompts should usually avoid:

- runtime pointer internals;
- orchestrator state paths;
- snapshot selection mechanics;
- variant proof mechanics;
- workflow routing internals.

## 9. Structured Command Results

Use `command-result` when a deterministic command or certified adapter returns
structured state.

`:returns` may name a record, a union, or (with `(:target-dsl "2.15")`) any
other currently transportable type directly. If current behavior genuinely
has a meaningful fixed result shape, model that shape as a record. Otherwise,
prefer a direct scalar/enum/path/optional/list/map return over inventing a
transport-only one-field wrapper.

```lisp
(defrecord ChecksResult
  (checks-report Path.checks-report)
  (status String))

(command-result run-checks
  :argv
    ("python"
     "workflows/library/scripts/run_checks.py"
     "--commands" inputs.check-commands
     "--report" inputs.checks-report-target)
  :returns ChecksResult)
```

`command-result` requirements:

- the command has declared inputs;
- the command has declared outputs;
- the command exposes structured result state;
- the command's effects are visible;
- the result is exposed only after validation succeeds;
- stdout parsing is not semantic authority.

### Certified Command Adapters

Use a certified adapter when the runtime does not yet have a native effect.

Examples:

- legacy queue move script;
- legacy ledger update script;
- legacy report normalizer;
- legacy path resolver;
- legacy external tool wrapper.

A certified adapter must have a registered adapter name, declared argv shape,
declared input/output contracts, declared effects, fixtures, source-map origin,
and a migration/deprecation note if it should become runtime-native later.

Bad:

```lisp
(command-result move-item
  :argv ("python" "-c" "... complex inline script ...")
  :returns Json)
```

Better:

```lisp
(command-result normalize-summary
  :adapter normalize_result
  :inputs
    ((execution_report completed.execution_report)
     (review_report approved.review_report))
  :returns ImplementationSummary)
```

Use direct `command-result :adapter` only for non-resource, non-resume
certified adapters with declared typed fields. Queue or ledger movement still
belongs in `resource-transition`, and reusable-state gating still belongs in
`resume-or-start`.

## 9A. Pure Computation And Typed Projection

If the logic is a comparison, a count, a boolean combination, a default, a
reason string, or typed record/union construction over values you already
have, write it in the language. Do not shell out.

The operator surface is closed and shared by compile-time folding and the
runtime evaluator (normative table:
[Workflow Lisp Frontend Specification](design/workflow_lisp_frontend_specification.md),
Section 10.2):

| Group | Operators |
| --- | --- |
| Equality | `=`, `!=` over `String`, `Int`, `Bool`, `Symbol`, same-type enums |
| Ordering | `<`, `<=`, `>`, `>=` over `Int` pairs or `Float` pairs |
| Boolean | `and`, `or`, `not` |
| Arithmetic | `+`, `-`, `*`, `min`, `max` over `Int`, fail-closed on 64-bit overflow |
| String | `string/concat`, `string/empty?`, `symbol/name` |
| Option | `some?`, `or-else` |
| Record | `record-update` |

There is deliberately no division, float equality, path-string concatenation,
collection operators, regex, time, randomness, or IO. If a workflow seems to
need one of those, that is a design question for the adapter-retirement
target
(`docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`),
not a reason to fall back to a command step or grow the surface informally.

Typed projection example — compare, default, and construct without Python:

```lisp
(defworkflow orchestrate
  ((approved Bool)
   (status String))
  -> SelectorSummary
  (record-update
    (record SelectorSummary
      :status status
      :ready false)
    :ready (or approved (= status "READY"))))
```

Choosing the surface:

| Behavior | Use |
| --- | --- |
| Compare, count, combine, default, build a reason string or typed value | Pure expressions / `defun` |
| Produce a typed record/union from existing typed values for routing or publication | Pure typed projection (same operators; visible generated step) |
| External tool, process spawn, network, git, real shell work | `command-result` with a certified adapter |
| Durable state mutation: queue, ledger, run-state | `resource-transition` (Section 13.4), never a bare command step |

What lowering generates: maximal pure regions become one compiler-generated
`pure_projection` step with a validated payload, payload digest, and a
private managed result bundle (`PURE_PROJECTION_BUNDLE`, resume-safe at step
scope). The step is visibility, not authority transfer: the expression body
stays effect-free, the generated bundle path is private, and
`pure_projection` is not an authored surface. Literal-only expressions may
fold away at compile time; the runtime evaluator owns the semantics either
way.

Failures are typed and fail-closed — expect `pure_expr_overflow`,
`pure_expr_float_equality_forbidden`, `pure_expr_union_equality_forbidden`,
`pure_expr_path_string_concat_forbidden`, or
`pure_expr_operator_unsupported`, never silent coercion.

Copy-safe fixtures:
`tests/fixtures/workflow_lisp/valid/pure_expr_loop_counter.orc` and
`tests/fixtures/workflow_lisp/valid/pure_expr_selector_action_projection.orc`.

Routing is not proof. `(if (= status "READY") ...)` may choose a branch; it
never makes union variant fields readable. See Section 10.

## 10. Pattern Matching And Variant Proof

Use `match` to consume union results.

```lisp
(match implementation
  ((COMPLETED c)
    (record-completed
      :execution-report c.execution-report))

  ((BLOCKED b)
    (record-blocked
      :progress b.progress-report
      :class b.blocker-class
      :reason b.blocker-reason)))
```

Inside the `COMPLETED` arm, `c.execution-report` is available. Inside the
`BLOCKED` arm, `b.progress-report`, `b.blocker-class`, and `b.blocker-reason`
are available. Outside `match`, variant-specific fields are unavailable.

Prefer exhaustive matches. Avoid partial matches unless the type or form
explicitly permits them.

Use `variant` to build a union value; use `match` to prove which variant you
have before reading variant-specific fields.

Computed scalar predicates may route; they never prove.

Routing on a genuine scalar is fine:

```lisp
(if (>= state.count max-iterations)
  (done ...)
  (continue ...))
```

Simulating `match` with a comparison to reach variant fields is not:

```lisp
;; Bad: routes on a status mirror, then reads an unproved variant field
(if (= implementation.status "COMPLETED")
    implementation.execution-report
    ...)

;; Better: proof comes from match
(match implementation
  ((COMPLETED c)
    c.execution-report)

  ((BLOCKED b)
    ...))
```

If the value is a union, use `match`. If a record carries a status enum that
mirrors a union's discriminant, the record is probably a fake outcome type
(Section 28).

## 11. Contexts And Derived State

High-level Lisp should derive state paths from private context and typed
resources, not from public path plumbing. Public workflow inputs are for caller
intent; runtime context is for allocation, checkpointing, idempotency, resume,
and provenance.

Common library/internal context records:

```lisp
(defrecord RunCtx
  (run-id RunId)
  (state-root Path.state-root)
  (artifact-root Path.artifact-root))

(defrecord PhaseCtx
  (run RunCtx)
  (phase-name Symbol)
  (state-root Path.state-root)
  (artifact-root Path.artifact-root))

(defrecord ItemCtx
  (run RunCtx)
  (item-id String)
  (state-root Path.state-root)
  (artifact-root Path.artifact-root)
  (ledger Path.state-existing))

(defrecord DrainCtx
  (run RunCtx)
  (state-root Path.state-root)
  (manifest Path.state-existing)
  (ledger Path.state-existing))
```

These records may appear in stdlib modules, reusable helper internals, low-level
fixtures, executable contracts, source maps, and Semantic IR. They should not
be exposed as ordinary public inputs for a promoted high-level workflow unless
the workflow is explicitly a low-level fixture or compatibility bridge.

When a promoted entry workflow omits one of these context parameters for an
internal reusable call, Workflow Lisp records that omission as private
executable-context metadata. Public authored inputs stay public; runtime-owned
context bindings, managed write roots, and YAML-compatibility bridge values
stay off the public boundary.

### 11.1 Boundary Authority Classes

Classify every path-like boundary value of a parent-callable candidate by
authority before exposing it:

| Class | Meaning | Treatment |
| --- | --- | --- |
| `public_authored` | The caller genuinely chooses the value: steering doc, target design, explicit output root | Keep public |
| `compatibility_bridge` | YAML-era state/artifact path kept for parity or existing consumers | Keep temporarily, labeled, with a retirement route |
| `runtime_derived` | Derivable from run context, resource identity, or `StateLayout` | Bind internally; not a public input |
| `generated_internal` | Compiler/runtime-owned bundle, write root, temp, or sidecar | Allocate privately |
| `materialized_view` | Deterministic rendering of a typed value | Allocate as a view; never semantic authority |

If most of a workflow's inputs are bookkeeping paths, the boundary is
YAML-shaped: derive or hide the internals and keep only authored inputs plus
labeled bridges public. The classification taxonomy, census evidence, and
promotion gates are owned by
`docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`.

Use helpers:

```lisp
(phase-ctx ctx 'implementation)
(phase-target ctx "execution-report.md")
```

Use those helpers inside library or lower-level procedures that already receive
private context. At higher-level call sites, prefer domain calls that allow the
compiler/runtime to provide the context privately:

```lisp
(run-work-item item)
```

Avoid:

```text
"${inputs.state_root}/implementation_state.json"
"${inputs.state_root}/execution_report_path.txt"
"${inputs.state_root}/implementation_outcome_before"
```

Those paths may exist after lowering, but they should not be ordinary high-level
authoring concerns.

### 11.2 Path Management

Before adding a path field, decide who semantically owns that path:

| Path class | Examples | Authoring rule |
| --- | --- | --- |
| Public authored input | target design doc, baseline design doc, steering doc, explicit output root | Keep as a typed public input when the caller genuinely chooses it. |
| Source or context document | prompt context doc, design reference doc, check-command spec | Model as a typed path value or typed request field. |
| Provider/command result bundle | structured `provider-result` or `command-result` bundle | Let the runtime bind the output target and validate the declared bundle. |
| Generated internal path | write root, checkpoint path, temp path, result-bundle sidecar | Allocate through `StateLayout`; never expose as ordinary public input. |
| Public report or summary | drain summary, review report, operator-facing artifact | Prefer boundary publication policy or observability rendering over body plumbing. |
| Prompt rendering | provider prompt input text | Pass a typed value/request record; prompt composition renders it. |
| Compatibility file | YAML-era pointer, selection bundle, legacy ledger view | Declare a labeled bridge with owner, source value, renderer/schema, and retirement condition. |
| Durable workflow state | backlog item state, drain state, recovery state | Use `Resource<TState>` and `Transition<TRequest, TResult>`, not arbitrary file writes. |

Litmus test: if deleting the path field would not change the workflow's
semantic domain input or output, the path is probably private, generated,
runtime-derived, a materialized view, or a compatibility bridge. It should not
be ordinary authored data.

If the only way to compute a path is string concatenation such as
`"${inputs.state_root}/..."`, stop and classify the value first. The fix is
usually one of:

- move the value into a typed request record;
- derive it from private context through `StateLayout`;
- make it a provider/command structured-output target;
- publish it at the boundary;
- declare it as a compatibility bridge; or
- keep it behind a certified adapter if it is truly legacy protocol work.

## 12. Transitions Instead Of Gates

A gate asks: may I continue?

A transition says: given state `S` and event/output `E`, validate `E`, produce
`S'`, expose typed outputs, and route by explicit outcome.

Do not fix brittle gates by adding more gates. Replace gate-shaped logic with
typed outcomes and transitions.

Avoid:

- `(file-exists? path)`
- `(status-string-equals? path "APPROVED")`
- `(parse-report-line report "Review Decision:")`
- `(pointer-file-points-to? path)`
- `(mtime-newer-than? output phase-start)`
- `(recovery-gate ...)`

Prefer:

- `(match result ...)`
- `(resume-or-start ...)`
- `(resource-transition ...)`
- `(review-revise-loop ...)`
- `(provider-result ...)`
- `(command-result ...)`
- `(backlog-drain ...)`

## 13. Standard High-Level Forms

This section describes high-level forms. Availability depends on current
frontend support and on the form having a reviewed lowering contract. A
standard-library form is safe authoring guidance only when it lowers through
visible generated statements, effects, state layout, proof behavior, and source
maps.

Treat these forms as stdlib authoring conveniences backed by generic `.orc`
composition, not opaque language builtins. The stdlib owns concrete helper
schemas and loop policy; the language/compiler owns generic typed dataflow,
effect visibility, source maps, and generated path handling.

Do not replace a missing or unsupported standard-library lowering with ad hoc
inline command text, report parsing, pointer choreography, or macro-generated
hidden effects. Either use the supported form, add a reviewed lowering
contract, or stay in lower-level YAML/Core fixtures.

### 13.1 `run-provider-phase`

Use for a provider-driven phase that returns typed structured state.

```lisp
(run-provider-phase implementation
  :ctx ctx
  :inputs inputs
  :provider providers.execute
  :prompt prompts.implementation.execute
  :returns ImplementationAttempt)
```

Expected lowering derives phase state paths, canonical result bundles, provider
output contracts, typed artifact refs, and validated commits. Authors should not
provide manual state paths.

### 13.2 `review-revise-loop`

Use for bounded review/fix loops where the form's lowering contract is
supported for the workflow's target.

The current authoring surface supports review/fix loop examples and fixtures,
and the current checkout lowers the form through the ordinary imported stdlib
route over compile-time review/fix `ProcRef` hooks. Primary YAML-to-`.orc`
migration is stricter: promotion still requires the parity evidence described
by `docs/design/workflow_lisp_key_migration_parity_architecture.md`.

The exact first-tranche `ReviewFindings`, `ReviewDecision`, and
`ReviewLoopResult` schemas are owned by
`docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`.
This guide should summarize that contract rather than restating alternate enum
or field-name variants.

```lisp
(review-revise-loop implementation-review
  :ctx ctx
  :completed completed
  :inputs inputs
  :review (proc-ref review-implementation)
  :fix (proc-ref fix-implementation)
  :max 40)
```

A review loop should return a typed result, such as `APPROVED`, `BLOCKED`, or
`EXHAUSTED`. Do not parse markdown review prose to recover the decision.

### 13.3 `resume-or-start`

Use to reuse canonical prior state or run fresh.

```lisp
(resume-or-start plan-gate
  :ctx ctx
  :resume-from selected.final-plan-gate-state
  :valid-when APPROVED
  :start
    (call plan/run
      :ctx (phase-ctx ctx 'plan)
      :selected selected
      :roadmap roadmap
      :providers providers.plan)
  :returns PlanGateResult)
```

Meaning:

- validate prior canonical state;
- if reusable, return typed resumed value;
- otherwise run fresh workflow/procedure;
- normalize both branches to the same return type.

This replaces brittle recovery gates. Do not call it a recovery gate.

### 13.4 `resource-transition`

Use for queue/resource movement plus ledger/state update.

```lisp
(resource-transition backlog-item
  :ctx ctx
  :resource selected.item
  :from Queue.active
  :to Queue.in-progress
  :ledger ctx.ledger
  :event SELECTED)
```

Valid lowerings:

- certified command adapter plus typed result validation;
- runtime-native `ResourceTransition` effect;
- transaction-capable state operation.

The form must not pretend to be more atomic than the substrate supports.

### 13.5 `finalize-selected-item`

Use to normalize terminal selected-item outcomes.

```lisp
(finalize-selected-item
  :ctx ctx
  :selected selected
  :plan plan
  :implementation implementation)
```

Meaning:

- match typed phase results;
- record completed or blocked item result;
- move resources if needed;
- write structured selected-item outcome;
- publish summary artifact;
- return `SelectedItemResult`.

This replaces fan-in through multiple handwritten blocked/completed scripts.

### 13.6 `backlog-drain`

Use for select/run/gap/repeat orchestration.

```lisp
(backlog-drain neurips
  :ctx ctx
  :selector selector/run
  :run-item selected-item/run
  :gap-drafter gap/draft
  :max-iterations max-iterations)
```

Expected lowering:

- bounded loop;
- selector workflow call;
- selected-item workflow call;
- gap-drafter workflow call;
- typed state accumulator;
- terminal typed result.

This is the high-level construct that should materially shrink top-level
backlog-drain authoring.

## 14. Provider Prompt Guidance

Prompts should focus on the provider's task.

Include:

- objective;
- scope boundaries;
- domain-specific completion criteria;
- required structured result shape;
- required human-facing report, if any;
- forbidden shortcuts;
- evidence expectations from the agent's point of view.

Usually avoid:

- orchestrator internals;
- pointer file theory;
- snapshot mechanics;
- variant proof mechanics;
- runtime state path explanations;
- duplicated generated output contracts;
- broad ambient doc globs;
- instructions to echo session IDs or pointer paths.

### Result Guidance

Use plain return types when the type and field names are sufficient. Add
guidance at the narrowest authored return occurrence when the producer needs
semantic help:

```lisp
:returns
  (result Bool
    :description "True only when no blocking findings remain."
    :format-hint "Write a JSON boolean."
    :example true)
```

Payload fields accept the same keys after the field type. `:example` is a
typed pure constant; for path types it is checked for path safety but the
target need not exist during compilation. Schema inclusion, imports, and
generic specialization preserve field guidance without changing type identity.

Provider/command occurrence guidance reaches the generated effect contract and
provider prompt. A `defworkflow` or effectful `defproc` return annotation is
overall callable guidance: it becomes top-level `result_guidance`, survives
shared IR, and is deliberately not injected into a provider prompt. Neither
form changes runtime validation, artifacts, routing, checkpoints, or resume.

For nontrivial provider calls, build a typed prompt-input record and pass that
record to `:inputs`. This keeps provider inputs named, typed, and separate from
runtime bookkeeping:

```lisp
(defrecord ImplementationRequest
  (target-design TargetDesignDoc)
  (baseline-design BaselineDesignDoc)
  (approved-plan PlanDoc)
  (checks CheckSpec)
  (output-targets ImplementationOutputTargets))

(provider-result providers.execute
  :prompt prompts.implementation.execute
  :inputs request
  :returns ImplementationAttempt)
```

The runtime renders `request` at the provider prompt seam. The provider output
still comes from the declared structured result contract.

Flat input lists are fine for small calls:

```lisp
(provider-result providers.execute
  :prompt prompts.implementation.execute
  :inputs (inputs.design inputs.plan)
  :returns ImplementationAttempt)
```

then the provider must produce `ImplementationAttempt`. The report explains the
work; the union value controls routing.

Do not put generated report targets, state roots, checkpoint paths, or
compatibility pointer paths in provider inputs merely so a prompt can tell the
provider where runtime-owned files live. Output targets belong in typed target
records, provider structured-output bindings, publication policy, bridge
metadata, or lower-level compatibility adapters according to their authority
class.

## 15. Operational Notes

The Lisp guide should not become a catalog of every provider/runtime feature.
Put detailed operational mechanics in provider/runtime docs. Keep these rules
visible:

- Provider aliases are typed values. Pass provider roles through typed inputs or
  provider records.
- Sessions are runtime-owned. Do not ask providers to echo, store, or restate
  session IDs in prompt content.
- Managed jobs remain runtime-managed. Do not hand-author guard wrappers,
  ad hoc audit paths, manual recovery steps, shell counters, or job
  resurrection scripts unless they are compatibility adapters with declared
  contracts and fixtures.
- Use adjudicated providers where comparing provider candidates is part of the
  workflow design. The selected structured result is what downstream state sees.
  Do not expose candidate/evaluator internal logs as semantic state unless the
  result type declares them.

## 16. Reuse And Modularity

Prefer narrow public workflows over reusable procedures and pure helpers rather
than one-off monoliths.

Before drafting a new unit, check the workflow and procedure libraries for:

- existing public phase boundary or internal phase procedure;
- existing design/plan/implementation stack;
- existing review loop;
- existing selected-item runner;
- existing adapter;
- existing result type.

Caller-visible outputs should come only through the declared return type.

Pass narrow cross-boundary data:

- typed inputs;
- typed context;
- typed provider roles;
- typed result records/unions.

Avoid:

- ambient globals;
- workspace-wide file globs;
- prompt-text routing;
- caller/callee provider-template merging;
- out-of-band pointer files.

Use typed `WorkflowRef[...]` parameters only for static orchestration strategies
that abstract over whole public workflow boundaries whose independent identity
matters. Workflow refs resolve at compile/module-link time, not by runtime
dynamic loading. Compile-time formal WorkflowRef/ProcRef parameters are
supported and erased. References cannot become runtime-bound public workflow
input contracts or cross outputs, records, artifacts, provider or command
results, or state. Prefer `ProcRef[...]` for internal behavior.

Use `ProcRef[...]` for compile-time procedure composition: typed procedure
parameters, explicit `(proc-ref name)` literals, keyword-only `bind-proc`
partial application, forwarding through `ProcRef[...]` parameters, and lexical
call-through after residual specialization. Keep ProcRef values on the
compile-time side of the boundary: do not route them through workflow outputs,
records, unions, artifacts, provider results, command results, ledgers, or
loop-carried runtime state, and do not model provider-selected, command-
produced, or dynamically dispatched procedures.

## 17. Loops

Use high-level loop forms when the pattern is known.

Prefer `review-revise-loop` for review/fix loops only when its current lowering
contract is supported for the workflow's promotion target. For primary
migrations, keep the characterized YAML primary or use an explicitly marked
compatibility surface until the required workflow-family parity evidence is
proven. Prefer `backlog-drain` for select/run/gap/repeat. Use direct
`loop/recur` only when the loop shape is genuinely novel.

Every loop must have:

- bounded iteration or explicit termination proof;
- typed loop state;
- typed terminal result;
- clear exhaustion behavior;
- no shell-managed counters;
- no raw back-edge hidden in command text.

Exhaustion should be a typed result when it is part of workflow semantics.

Loop state carries typed values, not file-path authority. Counters are `Int`
fields updated in-language; statuses and reasons are typed values; durable
state is a typed result or resource reference, not a `state/...` path
threaded through every iteration and re-read from disk. The pure-expression
surface makes the value-carrying shape direct:

```lisp
(loop/recur
  :max 6
  :state (record CounterState
           :count 0
           :label "seed")
  (fn (state)
    (if (< state.count 3)
      (continue
        (record-update state
          :count (+ state.count 1)
          :label "tick"))
      (done
        (record CounterResult
          :count state.count
          :label state.label)))))
```

### 17.1 `loop-state`

Use `loop-state` when `loop/recur` needs a typed local carrier but the carrier
does not deserve a top-level reusable `defrecord`.

```lisp
(loop/recur
  :max 2
  :state (loop-state
           (report ReviewReportPath report_path)
           (done Bool false))
  (fn (current)
    (if current.done
      (done current.report)
      (continue (loop-state :like current :done true)))))
```

`loop-state` rules:

- carriers are local and compile-time-only; the generated carrier name is not a
  public runtime contract;
- seed fields use `(field-name TypeName value)` and updates use
  `(loop-state :like existing :field replacement ...)`;
- use `loop-state` as the author-facing way to keep typed loop-frame state
  without introducing a generic top-level record just for one loop;
- runtime-forbidden values cannot be carried across the loop boundary,
  including `ProcRef[...]`, `WorkflowRef[...]`, provider refs, prompt refs, and
  `Json`.

## 18. Effects

Procedural abstraction must not hide effects.

```lisp
(defworkflow implementation/run
  ((ctx PhaseCtx)
   (inputs ImplementationInputs)
   (providers ImplementationProviders))
  -> ImplementationResult

  :effects
    ((reads inputs.design inputs.plan inputs.check-commands)
     (uses-provider providers.execute providers.review providers.fix)
     (writes Path.execution-report)
     (writes Path.checks-report)
     (writes Path.review-report)
     (updates-state ctx))

  ...)
```

Effect kinds include:

- `reads`
- `writes`
- `moves`
- `updates-ledger`
- `updates-state`
- `uses-provider`
- `executes-command`
- `calls-workflow`
- `captures-snapshot`
- `commits-bundle`
- `publishes`
- `materializes-artifact`

If a procedure's effects are hard to explain, the procedure is probably too
broad.

Semantic IR also promotes a small set of generated visibility effects
(`snapshot_capture`, `pointer_materialization`, `pure_projection`) so
generated runtime structure stays inspectable. A `pure_projection` entry is
observational metadata for one generated projection boundary; it does not
mean the authored expression gained provider, command, IO, or state effects.

Rendering is also an effect boundary. Prefer the consumer-owned lane:

| Consumer | Preferred authoring surface |
| --- | --- |
| typed workflow step | pass the typed value; no rendering |
| provider prompt | typed value or request record in `provider-result :inputs` |
| public workflow output | entry publication policy / boundary view |
| observability | typed terminal result rendered by report/dashboard surfaces |
| legacy reader | labeled compatibility bridge |
| timed mid-run artifact | explicit `materialize-view` |

If a body-level `materialize-view` only exists so a later prompt, summary,
public output, or legacy reader can see bytes, prefer moving that rendering to
the consumer seam. Keep explicit `materialize-view` when the file must exist at
that exact point in the workflow or when a low-level compatibility fixture is
being preserved deliberately.

## 19. Source Maps And Debugging

Debug high-level `.orc` in this order.

First, look at the `.orc` source diagnostic:

```text
variant_ref_unproved
at workflows/neurips/implementation.orc:42:9

field: attempt.execution-report
reason: field is available only for ImplementationAttempt.COMPLETED
hint: access it inside match
```

For generated nodes, diagnostics should show:

- source file;
- line/column;
- source form;
- macro/procedure expansion stack;
- generated Core AST node id;
- semantic IR node id;
- executable step id.

Useful build artifacts may include:

```text
.orchestrate/build/<workflow>/frontend_ast.json
.orchestrate/build/<workflow>/expanded_frontend_ast.json
.orchestrate/build/<workflow>/typed_frontend_ast.json
.orchestrate/build/<workflow>/core_workflow_ast.json
.orchestrate/build/<workflow>/semantic_ir.json
.orchestrate/build/<workflow>/executable_ir.json
.orchestrate/build/<workflow>/source_map.json
.orchestrate/build/<workflow>/expanded.debug.yaml
```

The debug YAML is optional and non-authoritative.

After compile/lowering succeeds, use ordinary runtime artifacts:

- `.orchestrate/runs/<run>/state.json`
- `.orchestrate/runs/<run>/logs/`
- composed prompts
- stdout/stderr
- artifact registry
- provider result bundles
- command result bundles
- generated `pure_projection` result bundles (private managed paths)

When a runtime failure references a generated executable step, the diagnostic
should also reference the high-level `.orc` source form.

## 20. Lints

The frontend and lint tools should warn on brittle authoring patterns.

| Code smell | Bad pattern | Preferred pattern |
| --- | --- | --- |
| `semantic_field_extracted_from_report` | Parse a markdown line for a decision or blocker | Structured provider/command result |
| `pointer_used_as_semantic_authority` | Publish a pointer file path as the value | Publish the typed artifact value |
| `variant_output_without_variant_specific_fields` | Union variants with no fields | Record plus enum |
| `recovery_gate_without_canonical_state` | File-existence recovery gate | `resume-or-start` |
| `resource_move_without_transition` | Shell move plus hidden ledger update | `resource-transition` or certified adapter |
| `manual_when_requires_variant_pair` | Manual condition/proof pairing | `match` |
| `manual_state_path` | Hand-built state path | Context helper such as `with-phase` |
| `command_step_for_pure_computation` | Python/`jq` step that only compares, counts, defaults, or formats | Closed pure-expression surface / typed projection (Section 9A) |
| `loop_state_carries_path_authority` | Loop state threading state-file paths between iterations | Typed value state plus `record-update` (Section 17) |
| `low_level_state_path_in_high_level_module` | `state/...` path types on a high-level public boundary | Derived context, private bindings, or a labeled compatibility bridge (Section 11.1) |

## 21. YAML Compatibility Surfaces

This section is for migration and debugging. New high-level `.orc` authors
should not usually start here.

| YAML/Core surface | Lisp-oriented replacement |
| --- | --- |
| `expected_outputs` | `defrecord`, `command-result`, simple typed artifact result |
| `output_bundle` | `defrecord` plus `provider-result` or `command-result` |
| `variant_output` | `defunion` plus `provider-result` |
| `pre_snapshot` + `select_variant_output` | `run-provider-phase` or another structured producer result |
| `materialize_artifacts` | Context-derived materialization or internal lowering |
| `requires_variant` | Usually generated from `match` |
| `match` | Same concept, used directly over unions |
| `repeat_until` | `review-revise-loop`, `backlog-drain`, or `loop/recur` |
| Raw `goto` | Avoid; use structured control |
| Shell gate | Assert, typed result, transition, or certified adapter |
| Pointer sidecar | Optional representation, not semantic source |

Do not write YAML-shaped Lisp:

```lisp
;; Bad direct translation
(step SelectImplementationOutcome
  (select-variant-output
    :path "${inputs.state_root}/implementation_state.json"
    :snapshot root.steps.Execute.snapshots.before
    :variants ...))
```

Prefer high-level authoring:

```lisp
(let* ((attempt
         (provider-result providers.execute
           :prompt prompts.implementation.execute
           :inputs (inputs.design inputs.plan)
           :returns ImplementationAttempt)))

  (match attempt
    ((COMPLETED c) ...)
    ((BLOCKED b) ...)))
```

If Lisp code is only YAML with parentheses, stop and revise the abstraction.

## 22. Migration From YAML To `.orc`

Use this process for converting an existing workflow.

1. Inventory behavior, not syntax.
2. Translate types first: path contracts, enums, records, unions, context
   records, provider records, and workflow signatures.
3. Translate one phase before the whole stack.
4. Measure authoring improvement.

Behavior inventory:

| Current pattern | Target |
| --- | --- |
| Pointer/path setup | Context-derived materialization or certified adapter |
| Fixed JSON bundle | `defrecord` plus `command-result`/`provider-result` |
| Completed/blocked output | `defunion` plus `match` |
| mtime/custom freshness selector | Structured producer result |
| Recovery gate | `resume-or-start` |
| Queue move + ledger update | `resource-transition` |
| Review/fix loop | `review-revise-loop` |
| Selected-item fan-in scripts | `finalize-selected-item` |
| Top-level select/run/gap/repeat | `backlog-drain` |
| Markdown line extraction | Structured result; legacy adapter only if necessary |
| Compare/count/default/format helper script | Closed pure-expression surface or typed projection |

For each migrated workflow, measure:

- authored LOC;
- semantic LOC;
- manual state-path count;
- pointer-file count;
- manual variant-check count;
- markdown/text extractor count;
- shell/Python glue count;
- gate-pattern count;
- behavioral equivalence.

The migration is not successful merely because the `.orc` parses. If the `.orc`
version remains YAML-shaped or requires more boilerplate than v2.14 YAML, stop
and revise the frontend design before migrating more workflows.

## 23. Example: Implementation Phase

Types:

```lisp
(defrecord ImplementationInputs
  (design Path.design)
  (plan Path.plan)
  (check-commands Path.check-commands)
  (execution-report-target Path.execution-report-target)
  (checks-report-target Path.checks-report-target)
  (review-report-target Path.review-report-target))

(defrecord ImplementationProviders
  (execute Provider)
  (review Provider)
  (fix Provider))

(defunion ImplementationAttempt
  (COMPLETED
    (execution-report Path.execution-report))

  (BLOCKED
    (progress-report Path.progress-report)
    (blocker-class BlockerClass)
    (blocker-reason String)))

(defunion ImplementationResult
  (APPROVED
    (execution-report Path.execution-report)
    (review_report Path.review-report)
    (findings ReviewFindings))

  (EXECUTION_BLOCKED
    (progress-report Path.progress-report)
    (blocker-class BlockerClass)
    (blocker-reason String))

  (REVIEW_BLOCKED
    (execution-report Path.execution-report)
    (review_report Path.review-report)
    (blocker_class BlockerClass)
    (findings ReviewFindings))

  (EXHAUSTED
    (execution-report Path.execution-report)
    (last_review_report Path.review-report)
    (findings ReviewFindings)
    (reason String)))
```

Workflow:

```lisp
(defworkflow implementation/run
  ((ctx PhaseCtx)
   (inputs ImplementationInputs)
   (providers ImplementationProviders))
  -> ImplementationResult

  :effects
    ((reads inputs.design inputs.plan inputs.check-commands)
     (uses-provider providers.execute providers.review providers.fix)
     (writes Path.execution-report)
     (writes Path.checks-report)
     (writes Path.review-report)
     (updates-state ctx))

  (with-phase ctx implementation
    (let* ((attempt
             (provider-result providers.execute
               :prompt prompts.implementation.execute
               :inputs
                 (inputs.design
                  inputs.plan)
               :targets
                 ((execution-report inputs.execution-report-target)
                  (progress-report (phase-target ctx "progress-report.md")))
               :returns ImplementationAttempt)))

      (match attempt
        ((COMPLETED completed)
          (match
            (review-revise-loop implementation-review
              :ctx ctx
              :completed completed
              :inputs inputs
              :review (proc-ref review-implementation)
              :fix (proc-ref fix-implementation)
              :max 40)

            ((APPROVED approved)
              (ImplementationResult.APPROVED
                :execution-report completed.execution-report
                :review_report approved.review_report
                :findings approved.findings))

            ((BLOCKED blocked)
              (ImplementationResult.REVIEW_BLOCKED
                :execution-report completed.execution-report
                :review_report blocked.review_report
                :blocker_class blocked.blocker_class
                :findings blocked.findings))

            ((EXHAUSTED exhausted)
              (ImplementationResult.EXHAUSTED
                :execution-report completed.execution-report
                :last_review_report exhausted.last_review_report
                :findings exhausted.findings
                :reason exhausted.reason))))

        ((BLOCKED blocked)
          (ImplementationResult.EXECUTION_BLOCKED
            :progress-report blocked.progress-report
            :blocker-class blocked.blocker-class
            :blocker-reason blocked.blocker-reason))))))
```

The stdlib loop returns the exact stdlib-owned `ReviewLoopResult`; the
workflow-specific `ImplementationResult` above is a caller-side projection over
that terminal protocol, not a replacement for it.

The author does not hand-manage `implementation_state.json`, snapshot names,
candidate paths, variant selector files, pointer sidecars, `requires_variant`,
or markdown line extraction.

## 24. Example: Selected Backlog Item

```lisp
(defworkflow selected-item/run
  ((selection SelectionInput)
   (providers NeuripsProviders))
  -> SelectedItemResult

  (let* ((selected
           (resolve-selected-item selection))

         (queued
           (resource-transition selected-backlog-item
             :resource selected.item
             :from Queue.active
             :to Queue.in-progress
             :event SELECTED))

         (roadmap
           (call roadmap/run-sync
             :selected selected
             :providers providers.roadmap))

         (plan
           (resume-or-start plan-gate
             :resume-from selected.final-plan-gate-state
             :valid-when APPROVED
             :start
               (call plan/run
                 :selected selected
                 :roadmap roadmap
                 :providers providers.plan)
             :returns PlanGateResult))

         (implementation
           (call implementation/run
             :inputs
               (make-implementation-inputs
                 :selected selected
                 :plan plan)
             :providers providers.implementation)))

    (finalize-selected-item
      :selected selected
      :queued queued
      :roadmap roadmap
      :plan plan
      :implementation implementation)))
```

This is the target shape for procedural composability. The workflow reads like a
typed program, not like a list of gates. Lowering/runtime may bind `ItemCtx`,
phase contexts, generated paths, idempotency keys, and transition audit state
behind this surface; those bindings should not become public workflow inputs.

## 25. Example: Top-Level Backlog Drain

```lisp
(defworkflow neurips/run-backlog-drain
  ((providers NeuripsProviders)
   (max-iterations Int))
  -> DrainResult

  (backlog-drain neurips
    :selector selector/run
    :run-item selected-item/run
    :gap-drafter gap/draft
    :providers providers
    :max-iterations max-iterations))
```

The `backlog-drain` form should own select, run selected item, handle empty,
handle gap, handle blocked item, record terminal drain state, and bounded
repetition.

Do not hand-author this pattern repeatedly, and do not expose `DrainCtx`,
run-state roots, summary targets, or generated bundle paths as ordinary public
inputs just to make the drain work. Library internals may still receive private
context after lowering.

## 26. Prompt Examples

Good implementation prompt framing:

```text
Implement the plan using the current checkout.

Inputs:
- design
- plan

You must return one structured outcome:

COMPLETED:
  - execution_report: path to the implementation execution report

BLOCKED:
  - progress_report: path to the progress/blocker report
  - blocker_class: one of the declared blocker classes
  - blocker_reason: concise reason

Write any human-facing report to the path provided by the structured output
contract. The structured result controls workflow routing.
```

Bad implementation prompt framing:

```text
Write a report. Somewhere in the report include:

Blocker Class:
Review Decision:
Execution Report Path:

The workflow will parse these lines later.
```

This makes prose the semantic state. Avoid it.

## 27. Drafting Checklist

Before running a new `.orc` workflow, confirm:

| Area | Check |
| --- | --- |
| Frontend choice | This belongs in `.orc`; YAML is needed only for compatibility or fixtures. |
| Types | All boundary values are typed. In public DSL v2.15, every currently transportable type is valid in function, procedure, provider-result, command-result, workflow-call, and public-workflow return positions; direct roots use compiler-owned `__result__` carriage and no authored wrapper. Optional `(result T ...)` and payload-field guidance is typed, prompt-only metadata and never changes runtime validity. |
| Paths | Path contracts are reusable `defpath` definitions. |
| Authority | Structured bundles/artifacts are authority; reports are views. |
| Providers | Provider decisions return structured state through `provider-result`. |
| Commands | Command semantics use `command-result` or certified adapters. |
| Reports | No markdown report is parsed for semantic state in new high-level code. |
| Pointers | Pointer files are not treated as artifact values. |
| Variants | Variant-specific fields are used only inside `match`. |
| State | State paths are derived from contexts. |
| Effects | Provider, command, write, move, ledger, state, and call effects are visible. |
| Reuse | Durable public run/resume/invocation/publication identity is a `defworkflow`; repeated internal effectful behavior is a `defproc`; pure behavior is a `defun`. |
| Gates | Gates have been replaced by typed outcomes or transitions where possible. |
| Prompts | Prompts describe domain work, not runtime mechanics. |
| Lowering | Generated Core AST uses real shared statement families; Semantic IR derives from validated shared bundle data; Executable IR validates before runtime-facing use; source maps preserve authored/generated provenance. |
| Diagnostics | Errors map back to useful `.orc` source forms. |
| Metrics | Authored size and brittle-pattern count improve over the YAML baseline. |

## 28. Review Checklist

When reviewing a `.orc` workflow, look for these failure modes.

### YAML-Shaped Lisp

Could this code be mechanically converted back to YAML without losing anything?
If yes, the Lisp frontend is probably not being used well.

### Hidden Command Semantics

Look for inline Python, inline Bash, subprocess chains, `jq` gates, report
parsers, pointer writers, and ledger updates hidden inside command text. Require
`command-result`, a certified adapter, or a runtime-native effect.

### Manual State Choreography

Look for manual state file paths, snapshot names, candidate paths, commit
bundles, and temporary paths. Require contexts or standard-library forms.

### Fake Outcome Types

Look for unions whose variants do not have variant-specific fields. Require a
record with an enum field instead.

### Report-As-State

Look for line-prefix extraction from markdown. Require structured
provider/command results.

### Pointer-As-Authority

Look for pointer file paths being published or passed as semantic values.
Require artifact values.

### Unproved Variant Access

Look for variant-specific fields outside `match`. Require `match` or a frontend
construct that lowers to an equivalent proof context.

## 29. Legacy And Compatibility Policy

Legacy workflows may retain YAML, shell glue, report parsing, and pointer
conventions temporarily. New high-level workflows should not introduce them.

A legacy adapter should declare:

- why it exists;
- what behavior it preserves;
- what structured result it returns;
- what effects it has;
- which fixtures prove it;
- when it can be retired.

Compatibility does not imply authority. A legacy script may still need pointer
files or markdown reports. That does not make those files semantic authority.
The `.orc` boundary should expose typed values.

## 30. Low-Level Core/YAML Surfaces

These surfaces still exist after lowering and remain useful for debugging,
compatibility, and runtime tests.

| Surface | Purpose |
| --- | --- |
| `expected_outputs` | File-per-artifact validation |
| `output_bundle` | Fixed-shape JSON bundle validation |
| `variant_output` | Tagged-union JSON bundle validation |
| `pre_snapshot` | Durable before-state evidence |
| `select_variant_output` | Exactly-one changed candidate selection and atomic bundle commit |
| `materialize_artifacts` | Runtime-owned materialization and pointer representation |
| `requires_variant` | Explicit variant proof for low-level steps |
| `match` | Structured branch/proof context |
| `repeat_until` | Bounded post-test loop |
| `call` | Reusable workflow call |

Do not duplicate this low-level substrate in high-level `.orc` unless you are
writing a compatibility fixture, runtime test, or standard-library lowering.

## 31. Quick Translation Table

| Old authoring thought | New authoring thought |
| --- | --- |
| "I need a gate." | "What typed outcome or transition proves this?" |
| "I need to parse the report." | "The provider/command should return structured state." |
| "I need a pointer file." | "What artifact value does the downstream step need?" |
| "I need when status == X." | "This is probably a match over a union." |
| "I need a recovery step." | "This is `resume-or-start` from canonical state." |
| "I need to move a file and update the ledger." | "This is a `resource-transition`." |
| "I need a custom review loop." | "Can this be `review-revise-loop`?" |
| "I need to select/run/gap/repeat." | "This is `backlog-drain`." |
| "I need a tiny Python helper to compare, count, or format." | "This is pure computation; use the operator surface and typed projection." |
| "I need to write a lot of target paths." | "These should derive from context or typed target schemas." |
| "The generated YAML is weird." | "Inspect the Core AST, executable IR, Semantic IR, and source map; YAML is only a projection." |

## 32. Minimal Safe Subset

For conservative examples, tutorials, and compatibility fixtures, prefer this
small subset before introducing modules, procedures, macros, loops, or library
forms:

- `defenum`
- `defpath`
- `defrecord`
- `defunion`
- `defworkflow`
- `let*`
- `match`
- `call`
- `provider-result`
- `command-result`
- `with-phase`
- `phase-target`

Minimal example:

```lisp
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")

  (defenum BlockerClass
    missing_resource
    unavailable_hardware
    roadmap_conflict
    external_dependency_outside_authority
    user_decision_required
    unrecoverable_after_fix_attempt)

  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)

  (defunion ImplementationAttempt
    (COMPLETED
      (execution-report WorkReport))
    (BLOCKED
      (progress-report WorkReport)
      (blocker-class BlockerClass)))

  (defworkflow implementation-execute
    ((provider Provider)
     (prompt Prompt)
     (design WorkReport)
     (plan WorkReport))
    -> ImplementationAttempt

    (let* ((attempt
             (provider-result provider
               :prompt prompt
               :inputs (design plan)
               :returns ImplementationAttempt)))

      (match attempt
        ((COMPLETED c)
          c)

        ((BLOCKED b)
          b)))))
```

Do not use forms from an active design tranche in ordinary authoring examples
until the implementation and fixtures have landed.

## 33. Final Rule

The frontend is successful only if authors can write workflows as typed
procedural compositions:

```lisp
(defworkflow run-selected-backlog-item (...) -> SelectedItemResult
  (let* ((selected (resolve-selected-item ...))
         (plan (ensure-approved-plan ...))
         (implementation (call implementation/run ...)))
    (finalize-selected-item ...)))
```

It is not successful if authors mostly write:

```lisp
(step ...)
(command ...)
(pre-snapshot ...)
(select-variant-output ...)
(write-pointer ...)
(parse-report ...)
```

The purpose of Workflow Lisp is not to make YAML prettier. The purpose is to
make deterministic workflow authoring typed, structured, composable,
state-safe, variant-safe, effect-visible, source-mapped, and less brittle while
still lowering into the same validated runtime substrate.
