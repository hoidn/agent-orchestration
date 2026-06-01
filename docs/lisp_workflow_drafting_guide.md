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

- [Workflow Lisp Frontend Specification](design/workflow_lisp_frontend_specification.md)
- [Workflow Lisp Frontend MVP Specification](design/workflow_lisp_frontend_mvp_specification.md)
- [Workflow Lisp Core Statement Taxonomy](design/workflow_lisp_core_stmt_taxonomy.md)
- [Workflow Lisp Semantic Workflow IR](design/workflow_lisp_semantic_workflow_ir.md)
- [Workflow Lisp Executable IR](design/workflow_lisp_executable_ir.md)
- [Workflow Lisp Macro Surface Contract](design/workflow_lisp_macro_surface_contract.md)
- [Workflow Lisp Frontend Standard Library Lowering](design/workflow_lisp_stdlib_lowering.md)
- [Workflow Lisp Runtime Closures Boundary](design/workflow_lisp_runtime_closures_boundary.md)
- [Workflow Language Design Principles](design/workflow_language_design_principles.md)
- [Workflow Command Adapter Contract](design/workflow_command_adapter_contract.md)

Use this guide for authoring judgment. Use the component-contract docs for
current-checkout behavior. Use the unified design for future or deferred
surfaces. Use `specs/` for normative runtime and DSL behavior.

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

If you want the smallest concrete Workflow Lisp starting point, read
`workflows/examples/kiss_backlog_item.orc` before studying the autonomous drain
examples. It shows a single backlog item flowing through typed plan and
implementation provider results plus bounded review/fix loops. Treat it as a
single-item shared-validation example, not as a production queue drain: it can
compile and dry-run through the `.orc` runtime bridge, but it does not include
the selector, queue movement, recovery, and parity evidence required to replace
the mature YAML backlog drains.

## Core Rule

Author typed workflow procedures and structured results.

Do not author brittle gates, pointer plumbing, report parsers, candidate-path
selectors, or manual state-file choreography.

Good high-level workflow code should look like typed composition:

```lisp
(defworkflow run-selected-backlog-item
  ((ctx ItemCtx)
   (selection SelectionInput)
   (providers NeuripsProviders))
  -> SelectedItemResult

  (let* ((selected
           (resolve-selected-item ctx selection))

         (plan
           (ensure-approved-plan
             :ctx (phase-ctx ctx 'plan)
             :selected selected
             :providers providers.plan))

         (implementation
           (call implementation/run
             :ctx (phase-ctx ctx 'implementation)
             :inputs (make-implementation-inputs selected plan)
             :providers providers.implementation)))

    (finalize-selected-item
      :ctx ctx
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

## 1. Mental Model

Think in five layers.

| Layer | Author concern | Typical `.orc` forms | Runtime/lowering concern |
| --- | --- | --- | --- |
| Types and contracts | What values exist? | `defpath`, `defenum`, `defrecord`, `defunion`, `defschema` | Contracts, path safety, artifact shapes |
| Procedures and workflows | What behavior is reusable? | `defworkflow`, `defproc`, `defun`, `call`, `let*` | Graph structure, workflow calls, sequencing |
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
- Is this reusable as a workflow, a procedure, or a pure helper?
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
- `if`
- `match`
- `loop/recur`
- `call`
- `WorkflowRef[...]` and `(workflow-ref ...)`
- `provider-result`
- `command-result`
- `with-phase`
- `phase-target`
- `run-provider-phase`
- `resume-or-start`
- `review-revise-loop` as an implemented authoring surface; primary-migration
  parity for this form is pending the ordinary stdlib/generic composition
  lowering described in
  `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `resource-transition` through the current library/certified-adapter path
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

Deferred or future:

- runtime first-class procedures or closures
- provider-selected or command-produced procedure values
- procedure values stored in workflow outputs, records, unions, artifacts,
  provider results, command results, state, ledgers, or loop-carried runtime
  state
- dynamic runtime procedure dispatch
- runtime-native atomic resource transitions beyond current certified adapters

Runtime closures remain future runtime-owned callable values. Current work only
proves disabled-profile rejection and source-map diagnostics. Do not author
runtime closure values, dynamic procedure dispatch, or procedure-valued runtime
state.

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

A general `if` or string predicate is not proof unless the frontend/compiler
explicitly supports that proof form.

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
| Exported callable workflow | `defworkflow` | Giant monolith |
| Reusable effectful graph behavior | `defproc` | Copy-pasted steps |
| Pure path/record/schema helper | `defun` | Command step |
| Compile-time syntax abbreviation | `defmacro` | Effectful macro |
| Provider returns structured state | `provider-result` | Markdown parsing |
| Command returns structured state | `command-result` | Stdout scraping |
| Outcome-shaped result | `defunion` + `match` | Stringly gates |
| Fixed-shape result | `defrecord` | Fake tagged union |
| Queue/ledger movement | `resource-transition` or certified adapter | Shell move + hidden ledger update |
| Resume prior state or run fresh | `resume-or-start` | Recovery gate |
| Review/fix loop | `review-revise-loop` | Raw back-edge or shell counter |
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
(defenum ReviewDecision
  APPROVE
  REVISE)

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

Enums support contract validation, exhaustive `match`, stable branch shape,
prompt-contract generation, and typed diagnostics.

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

Use `defworkflow` for exported callable workflow boundaries.

```lisp
(defworkflow implementation/run
  ((ctx PhaseCtx)
   (inputs ImplementationInputs)
   (providers ImplementationProviders))
  -> ImplementationResult

  ...)
```

Use `defworkflow` when:

- another workflow should call this unit;
- the unit has a stable public input/output contract;
- the unit should appear as a separate workflow boundary in run state;
- the unit belongs in a reusable workflow library.

Keep workflow boundaries narrow. Pass typed inputs in and typed outputs out.

### 6.2 `defproc`

Use `defproc` for reusable effectful graph behavior that need not be a public
workflow boundary.

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

A macro rewrites syntax. A procedure represents reusable workflow behavior. If
the abstraction has effects, prefer `defproc` or a compiler-owned
standard-library form over `defmacro`.

Current implementation boundary: `defproc` is usable for provider-only helpers
and reviewed-phase helpers that rely on `with-phase`,
`review-revise-loop`, `match` fan-in, and the compiler-owned prompt or
write-root transport those forms generate. Prefer `:lowering private-workflow`
when a reviewed-phase helper should stay reusable across workflow boundaries;
`:lowering auto` remains conservative and may still inline single-call-site
helpers. Keep a `defworkflow` boundary when you want a public entrypoint or the
workflow call shape itself is the authored API surface.

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
combine strings, compute constants, and build type-level descriptors.

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

```lisp
(let* ((attempt
         (provider-result providers.execute
           :prompt prompts.implementation.execute
           :inputs (inputs.design inputs.plan)
           :returns ImplementationAttempt)))

  ...)
```

The provider must produce structured output matching the return type.

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
(command-result move-backlog-item
  :adapter adapters.backlog.move-item
  :inputs
    ((item selected.active-path)
     (to Queue.in-progress)
     (ledger ctx.ledger))
  :returns ResourceTransitionResult)
```

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

Do not use general predicates as proof:

```lisp
;; Bad
(if (= implementation.status COMPLETED)
    implementation.execution-report
    ...)

;; Better
(match implementation
  ((COMPLETED c)
    c.execution-report)

  ((BLOCKED b)
    ...))
```

## 11. Contexts And Derived State

High-level Lisp should derive state paths from contexts.

Common context records:

```lisp
(defrecord WorkflowCtx
  (state-root Path.state-root)
  (artifact-root Path.artifact-root)
  (run-id RunId))

(defrecord PhaseCtx
  (state-root Path.state-root)
  (artifact-root Path.artifact-root)
  (run-id RunId)
  (phase-name Symbol))

(defrecord ItemCtx
  (state-root Path.state-root)
  (artifact-root Path.artifact-root)
  (run-id RunId)
  (ledger Path.state-existing)
  (design Path.design))

(defrecord DrainCtx
  (state-root Path.state-root)
  (artifact-root Path.artifact-root)
  (run-id RunId)
  (manifest Path.state-existing)
  (ledger Path.state-existing))
```

Use helpers:

```lisp
(phase-ctx ctx 'implementation)
(phase-target ctx "execution-report.md")
```

Avoid:

```text
"${inputs.state_root}/implementation_state.json"
"${inputs.state_root}/execution_report_path.txt"
"${inputs.state_root}/implementation_outcome_before"
```

Those paths may exist after lowering, but they should not be ordinary high-level
authoring concerns.

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

Use for bounded review/fix loops.

```lisp
(review-revise-loop implementation-review
  :ctx ctx
  :completed completed
  :inputs inputs
  :review-provider providers.review
  :fix-provider providers.fix
  :review-prompt prompts.implementation.review
  :fix-prompt prompts.implementation.fix
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

If a provider is declared as:

```lisp
(provider-result providers.execute
  :prompt prompts.implementation.execute
  :inputs (inputs.design inputs.plan)
  :returns ImplementationAttempt)
```

then the provider must produce `ImplementationAttempt`. The report explains the
work; the union value controls routing.

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

Prefer reusable workflow/procedure structure over one-off monoliths.

Before drafting a new workflow, check the workflow library for:

- existing phase workflow;
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

Use typed `WorkflowRef[...]` parameters for reusable orchestration strategies
that abstract over whole workflows. Workflow refs resolve at compile/module-link
time, not by runtime dynamic loading.

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

Prefer `review-revise-loop` for review/fix loops and `backlog-drain` for
select/run/gap/repeat. Use direct `loop/recur` only when the loop shape is
genuinely novel.

Every loop must have:

- bounded iteration or explicit termination proof;
- typed loop state;
- typed terminal result;
- clear exhaustion behavior;
- no shell-managed counters;
- no raw back-edge hidden in command text.

Exhaustion should be a typed result when it is part of workflow semantics.

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
  (COMPLETED
    (execution-report Path.execution-report)
    (checks-report Path.checks-report)
    (review-report Path.review-report)
    (review-decision ReviewDecision))

  (BLOCKED
    (progress-report Path.progress-report)
    (blocker-class BlockerClass)
    (blocker-reason String))

  (EXHAUSTED
    (last-review-report Path.review-report)
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
          (review-revise-loop implementation-review
            :ctx ctx
            :completed completed
            :inputs inputs
            :review-provider providers.review
            :fix-provider providers.fix
            :review-prompt prompts.implementation.review
            :fix-prompt prompts.implementation.fix
            :max 40))

        ((BLOCKED blocked)
          (ImplementationResult.BLOCKED
            :progress-report blocked.progress-report
            :blocker-class blocked.blocker-class
            :blocker-reason blocked.blocker-reason))))))
```

The author does not hand-manage `implementation_state.json`, snapshot names,
candidate paths, variant selector files, pointer sidecars, `requires_variant`,
or markdown line extraction.

## 24. Example: Selected Backlog Item

```lisp
(defworkflow selected-item/run
  ((ctx ItemCtx)
   (selection SelectionInput)
   (providers NeuripsProviders))
  -> SelectedItemResult

  (let* ((selected
           (resolve-selected-item
             :ctx ctx
             :selection selection))

         (queued
           (resource-transition selected-backlog-item
             :ctx ctx
             :resource selected.item
             :from Queue.active
             :to Queue.in-progress
             :ledger ctx.ledger
             :event SELECTED))

         (roadmap
           (call roadmap/run-sync
             :ctx (phase-ctx ctx 'roadmap-sync)
             :selected selected
             :providers providers.roadmap))

         (plan
           (resume-or-start plan-gate
             :ctx (phase-ctx ctx 'plan)
             :resume-from selected.final-plan-gate-state
             :valid-when APPROVED
             :start
               (call plan/run
                 :ctx (phase-ctx ctx 'plan)
                 :selected selected
                 :roadmap roadmap
                 :providers providers.plan)
             :returns PlanGateResult))

         (implementation
           (call implementation/run
             :ctx (phase-ctx ctx 'implementation)
             :inputs
               (make-implementation-inputs
                 :selected selected
                 :plan plan)
             :providers providers.implementation)))

    (finalize-selected-item
      :ctx ctx
      :selected selected
      :queued queued
      :roadmap roadmap
      :plan plan
      :implementation implementation)))
```

This is the target shape for procedural composability. The workflow reads like a
typed program, not like a list of gates.

## 25. Example: Top-Level Backlog Drain

```lisp
(defworkflow neurips/run-backlog-drain
  ((ctx DrainCtx)
   (providers NeuripsProviders)
   (max-iterations Int))
  -> DrainResult

  (backlog-drain neurips
    :ctx ctx
    :selector selector/run
    :run-item selected-item/run
    :gap-drafter gap/draft
    :providers providers
    :max-iterations max-iterations))
```

The `backlog-drain` form should own select, run selected item, handle empty,
handle gap, handle blocked item, record terminal drain state, and bounded
repetition.

Do not hand-author this pattern repeatedly.

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
| Types | Inputs, outputs, provider results, and command results have record/union types. |
| Paths | Path contracts are reusable `defpath` definitions. |
| Authority | Structured bundles/artifacts are authority; reports are views. |
| Providers | Provider decisions return structured state through `provider-result`. |
| Commands | Command semantics use `command-result` or certified adapters. |
| Reports | No markdown report is parsed for semantic state in new high-level code. |
| Pointers | Pointer files are not treated as artifact values. |
| Variants | Variant-specific fields are used only inside `match`. |
| State | State paths are derived from contexts. |
| Effects | Provider, command, write, move, ledger, state, and call effects are visible. |
| Reuse | Repeated behavior is a `defworkflow`, `defproc`, or standard-library form. |
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
