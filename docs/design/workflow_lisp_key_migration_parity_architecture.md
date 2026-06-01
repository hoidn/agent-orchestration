# Workflow Lisp Key Migration Parity Architecture

Status: draft
Kind: architecture decision / migration design
Created: 2026-06-01
Last material update: 2026-06-01
Scope:

- Workflow Lisp lowering requirements for key-workflow parity.
- Runtime/spec deltas required before `.orc` promotion.
- Migration evidence and promotion policy.

Authority:

- Normative DSL/runtime behavior remains in `specs/`.
- This document is authoritative as a migration architecture, not as a runtime
  spec, until the required spec deltas and promotion-report schema are accepted.
- A `.orc` workflow must not replace a YAML primary solely because this document
  describes a target behavior.

Related docs:

- `docs/lisp_workflow_drafting_guide.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/lisp_frontend_review_fix_loops.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-summary.md`
- Generated run evidence:
  `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/index.json`

Implementation target: staged changes to the Workflow Lisp frontend,
remaining effectful composition gaps, shared validation, and runtime
command/output handling needed before promoting key `.orc` workflow
replacements over YAML primaries.

## Summary

The first key-workflow migration pass proved that Workflow Lisp can compile and
dry-run meaningful `.orc` replacements, but it did not establish primary
workflow parity. The remaining gaps are not mostly syntax gaps. They are
contract gaps between high-level Lisp forms, generated Core DSL, runtime output
materialization, repeat/revise state, and migration evidence.

This design chooses a language-foundation-first migration architecture. The
YAML DSL already has most required runtime primitives: `output_bundle`,
`variant_output`, `repeat_until`, `on_exhausted`, workflow input defaults,
structured refs, call frames, and runtime state. Workflow Lisp also already has
important composition substrate: pure `defun`, effectful `defproc`,
`WorkflowRef`, `ProcRef`, `bind-proc`, `let-proc`, and `loop/recur`. The main
work is to complete and generalize that substrate enough that recurring
patterns such as `review-revise-loop` can be defined as ordinary library
workflows/procedures, not compiler-special forms. After that, the remaining
work is to specify the few runtime behaviors that are currently implementation
details and add a machine-checked promotion gate that prevents `.orc` workflows
from replacing YAML while parity remains regressive. The main runtime/spec
exceptions are command bundle-path injection, command-produced union bundle
handling, generated write-root policy, review-loop exhaustion projection, and
machine-checked promotion evidence.

No runtime closures or runtime-transported procedure values are required for
this migration tranche.

## Intention And Goal

The intention is to make `.orc` a credible primary authoring surface for key
workflow families, not merely an alternate syntax that can compile toy or
single-pass examples. A promoted `.orc` workflow must preserve the operational
behavior authors rely on in YAML: structured outputs, review/revise loops,
carried review context, resume safety, input defaults, and observable migration
evidence.

The goal of this design is to identify the smallest principled set of
DSL/compiler/runtime and stdlib changes needed to reach that parity without
recreating YAML-era glue. In particular, recurring orchestration patterns should
be expressible as ordinary `.orc` stdlib workflows/procedures over generic
effectful composition, while the runtime continues to enforce validated
artifacts and state rather than learning workflow-specific concepts.

## Context And Authority

Normative DSL behavior lives in `specs/`. Existing relevant contracts include:

- `specs/dsl.md`: workflow inputs/defaults, `output_bundle`, `variant_output`,
  `repeat_until`, `on_exhausted`, structured `match`, and `materialize_artifacts`.
- `specs/state.md`: authoritative `state.json`, call frames, `repeat_until`
  bookkeeping, artifact lineage, and resume state.
- `specs/io.md`: step output capture and output contract validation.

Workflow Lisp design authority is split across:

- `docs/design/workflow_lisp_stdlib_lowering.md`, which defines the current
  standard-library lowering inventory that this design narrows away from
  compiler-special review-loop behavior;
- `docs/design/lisp_frontend_review_fix_loops.md`, which sketches review/fix
  loop behavior;
- `docs/design/workflow_lisp_state_layout.md`, which defines generated state
  path ownership;
- `docs/design/workflow_command_adapter_contract.md`, which separates
  certified command adapters from hidden semantic glue.

The migration evidence currently shows two non-primary `.orc` targets:

- `cycle_guard_demo.orc` compiles and dry-runs, but the real run failed because
  the managed output bundle was not materialized at the expected path.
- `design_plan_impl_review_stack_v2_call.orc` preserves phase order and typed
  outputs, but does not preserve full YAML review/revise loops, carried
  findings, YAML input defaults, or real smoke parity.

## Problem

Key `.orc` replacements cannot become primary while the compiler and runtime
leave important behavior implicit:

- A `command-result` can lower to `output_bundle`, but the runtime/compiler
  contract for the bundle path, environment injection, and validation authority
  is not fully documented as a promotion requirement.
- `review-revise-loop` exists as a high-level authoring concept, but it cannot
  yet be defined as ordinary `.orc` library code. The blocker is not the
  absence of procedures, references, or loops; it is that provider/prompt refs,
  compiler-owned result paths, typed review findings, and source-map-preserving
  stdlib expansion are not yet general enough for a review loop to live outside
  a compiler-specific branch.
- Review findings are still entangled with report/pointer extraction in legacy
  YAML patterns instead of being typed state that revise/fix steps consume.
- Generated state paths and reusable phase state are not yet stable enough for
  primary `.orc` replacements of long-running workflows.
- `.orc` entrypoints cannot yet claim parity with YAML entrypoints that expose
  defaults unless defaults are represented at the Workflow Lisp boundary.
- Migration evidence lacks a hard promotion gate that distinguishes "parses and
  dry-runs" from "can replace the YAML primary."

Without a design-level boundary, these gaps invite local patches: hidden Python
adapters, pointer-as-state compatibility, prompt-side loop instructions, or
test-only fixtures. Those would reproduce the YAML migration debt that Workflow
Lisp is intended to remove.

## Goals

- Define which changes belong to DSL/spec, Workflow Lisp compiler, runtime, and
  migration policy.
- Close the parity gaps required to promote key workflows to `.orc`.
- Preserve existing runtime primitives where they are already sufficient.
- Keep structured state and validated artifacts as authority.
- Make generated state paths, bundle paths, and source maps deterministic.
- Support real review/revise/fix loops with typed terminal outcomes.
- Make review/revise/fix loops ordinary `.orc` stdlib code rather than
  compiler-special language forms.
- Support carried review findings without markdown report parsing as semantic
  authority.
- Require compile, shared validation, dry-run, real smoke where safe, and
  parity evidence before YAML deprecation.

## Non-Goals

- Do not add runtime closures or runtime-transported procedure values.
- Do not recreate YAML pointer choreography in high-level `.orc`.
- Do not make generated/debug YAML semantic authority.
- Do not promote the low-level cycle-guard demo itself as a high-level key
  workflow replacement unless native bounded-loop parity is intentionally
  designed later.
- Do not preserve inline shell/Python findings extraction as a permanent
  semantic path.
- Do not introduce a new DSL version solely to rename existing v2.14 surfaces.
- Do not add or preserve a compiler-special `review-revise-loop` implementation
  as the migration path.

## Decision

Use a language-foundation-first architecture with narrow runtime/spec contract
deltas.

The recommended approach is:

1. Treat existing YAML DSL primitives as the executable substrate.
2. Complete the existing generic `.orc` support needed to define effectful
   library abstractions over provider calls, command calls, typed loops,
   matches, generated result paths, source maps, and compile-time
   provider/prompt/workflow/procedure references.
3. Define `review-revise-loop` as ordinary `.orc` stdlib code on top of those
   generic capabilities.
4. Finalize Workflow Lisp contracts for `command-result`, `resume-or-start`,
   state layout, and workflow input defaults.
5. Specify and implement normative command structured-output behavior:
   `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` is the command's authoritative bundle
   target for command steps with deterministic structured bundle contracts.
6. Introduce generic structured dataflow guidance for stdlib review-result and
   finding records.
7. Add a machine-validated migration promotion gate that keeps YAML primary
   until parity evidence is non-regressive. `non_regressive` is computed by the
   promotion command from evidence; authors must not assert it by hand.

### Minimum Migration Slice

This design deliberately does not require completing every future `.orc`
composition feature before migration can continue. A key workflow may attempt
`.orc` promotion after this narrower slice is implemented and tested:

1. `command-result` lowers to authoritative generated bundle contracts with
   compiler-owned paths and runtime bundle-path injection.
2. Imported `.orc` stdlib definitions can generate provider steps, command
   steps, `match`, and one resume-safe typed loop form with stable source maps.
3. Provider, prompt, workflow, and procedure refs are compile-time-only and
   fully specialized before executable runtime state is produced.
4. `review-revise-loop` is implemented in `.orc` stdlib using only that subset.
5. Parity evidence proves the generated executable shape matches the YAML
   baseline.

Generic macros, broader stdlib packaging, and arbitrary nested effectful
composition remain follow-on work unless this review-loop implementation
requires them.

Alternatives considered:

- **DSL-first new primitives.** Add new YAML DSL constructs for review loops,
  findings, phase state, and command results. This would make the substrate
  larger even though v2.7-v2.14 already have the needed execution primitives.
  Reject for this tranche.
- **Compiler-special stdlib lowering.** Recognize `review-revise-loop` directly
  in the compiler and lower it to generated `repeat_until`/`match`/provider
  steps. This may be expedient, but it bakes one workflow idiom into the
  compiler and delays the more important `.orc` composition model. Reject as the
  migration path.
- **Legacy adapter migration.** Wrap missing behavior in certified adapters and
  preserve YAML-era pointer/report conventions. Useful only for explicitly
  allowlisted compatibility. Reject as the primary architecture.
- **Language-foundation-first stdlib.** Complete generic effectful composition
  and source-map-preserving library expansion first, then implement review loops
  as ordinary `.orc` stdlib code. This is the selected approach.

## Required Changes By Gap

| Gap | Required extension | Primary owner | DSL/spec impact | Promotion evidence |
| --- | --- | --- | --- | --- |
| Command-result structured return materialization | Final `command-result` lowering contract and runtime bundle-path contract | Workflow Lisp lowering + runtime executor | Normative command bundle-path behavior in `specs/dsl.md` and `specs/io.md` | Real command smoke proves env injection, bundle validation, and missing-bundle failure |
| Review/revise loop parity | Complete generic effectful `.orc` library composition, then implement `review-revise-loop` in stdlib `.orc` | Workflow Lisp language/compiler + stdlib | No new YAML DSL construct if v2.7/v2.12 semantics plus final projection suffice | REVISE/fix/APPROVE and exhaustion tests |
| Carried findings/review state | Generic structured output/dataflow support, with concrete review-result and findings schemas owned by the `.orc` stdlib loop | `.orc` stdlib + Workflow Lisp generic validation | No new YAML DSL construct; use declared structured bundles | Findings schema validation and revise/fix consumption |
| Resume/state semantics | State layout and `resume-or-start` reusable-state validation contract | Workflow Lisp state layout + runtime/adapters | Clarify reusable state shape and failure taxonomy | Reusable, stale, missing artifact, failed, and schema-mismatch cases |
| Default input parity | `.orc` boundary syntax and lowering for workflow input defaults | Workflow Lisp parser/typecheck/lowering | Existing DSL input default support | Compile/lower/default override tests |
| Real smoke coverage | Migration promotion checklist and parity report schema | Migration policy/tests | New machine-readable migration report schema | Computed `non_regressive`, not manually asserted |

Implementation owner matrix:

| Concern | Owner / file area |
| --- | --- |
| Input defaults | `orchestrator/workflow_lisp/workflows.py`, `specs/dsl.md` |
| Record, union, and findings contracts | `orchestrator/workflow_lisp/contracts.py`, `.orc` stdlib schemas |
| Managed bundle paths | `orchestrator/workflow_lisp/lowering.py`, runtime command executor bridge |
| `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` injection | runtime command execution, `specs/io.md`, `specs/dsl.md` |
| `review-revise-loop` lowering | `.orc` stdlib/generic effectful composition and Workflow Lisp lowering |
| State/reuse validation | Workflow Lisp state layout, shared validation, certified validators |
| Parity report | migration tooling, parity tests, generated report schema |

## Architecture

The architecture has four layers.

```text
.orc authoring
  -> Workflow Lisp parser/typecheck/effectful library composition
  -> .orc stdlib workflows/procedures
  -> Core Workflow AST / Semantic IR / Executable IR
  -> existing DSL runtime primitives
  -> migration parity evidence
```

## Normative Spec Status

Before any `.orc` candidate can replace a YAML primary, required behavior must
live in normative specs or a machine-readable schema, not only in this
architecture doc.

- `specs/dsl.md`: command steps with deterministic structured bundle contracts
  receive a runtime-resolved bundle target.
- `specs/io.md`: define `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, parent-directory
  creation, stdout-vs-bundle authority, and missing/invalid bundle behavior.
- `specs/state.md`: define the output-contract failure shape for missing or
  invalid command bundles after process exit `0`.

Remaining normative/schema work before acceptance:

- Path-safety spec surface: define workspace-relative normalization, rejection
  of absolute paths and `..` escapes, and symlink policy for generated bundle
  and state paths.
- Migration evidence schema: define the parity report fields and require
  `non_regressive` to be computed from evidence, not manually asserted.

Command-produced union results must lower to a variant-proof surface and must
not depend on an implicit `variant_output` path. Until `variant_output.path` is
normative, primary-promotion candidates may use one of two explicit strategies:

1. Add normative `variant_output.path` support and lower `command-result`
   unions directly to `variant_output`.
2. Lower the command to an `output_bundle` containing the raw discriminant and
   payload, then generate a compiler-owned validator/projection step that emits
   a variant-proof-compatible result.

The compiler must not expose output-bundle variant fields directly as if they
had selected-variant proof. Downstream variant-specific fields are available
only through `variant_output` proof or the compiler-owned projection's
equivalent discriminant proof.

## Related Doc Updates Required

Before this design is accepted rather than draft, align the dependent authoring
and lowering docs:

- `docs/lisp_workflow_drafting_guide.md`: label `review-revise-loop` as
  stdlib-pending for primary migrations unless the ordinary stdlib
  implementation exists.
- `docs/design/workflow_lisp_stdlib_lowering.md`: record that
  review-loop-specific compiler lowering is rejected for this tranche.
- `docs/design/lisp_frontend_review_fix_loops.md`: map YAML terminal statuses
  to `ReviewDecision` and `ReviewLoopResult`.

### 1. Workflow Lisp Authoring Layer

The authoring layer exposes primitive effectful forms and ordinary library
abstractions.

Primitive effectful forms include:

- `command-result`
- `provider-result`
- `run-provider-phase`
- `resume-or-start`
- `resource-transition`

Library abstractions include:

- `review-revise-loop`
- `finalize-selected-item`
- `backlog-drain`

Authors should express typed workflow behavior. They should not write hidden
bundle paths, pointer files, markdown extraction, or loop routing glue.

`review-revise-loop` must be authored in `.orc` stdlib, imported like any other
library workflow/procedure, and compiled through the same generic machinery as
project-authored code. The compiler may know about the primitive forms it uses,
but it must not contain a review-loop-specific lowering branch.

### Required Generic `.orc` Support

The following support is required before `review-revise-loop` can be a normal
library definition. This is completion work on the current language model, not
a restart. Current support already includes pure `defun`, effectful `defproc`,
`WorkflowRef`, `ProcRef`, `bind-proc`, `let-proc`, and `loop/recur`.

1. **Effectful library procedures or workflows.** A reusable `.orc` definition
   can already be represented with `defproc` and workflow/procedure refs. The
   remaining requirement is to make that path sufficient for stdlib control
   combinators: imported library definitions must preserve sequencing,
   artifacts, output refs, validation, source maps, and effect graph entries
   across nested provider calls, command calls, `match`, typed loops, and calls
   to other workflows/procedures.

2. **Compile-time references for providers, prompts, workflows, and
   procedures.** Workflow and procedure refs already have a static authoring
   model. Provider and prompt refs need equivalent compile-time parameter
   support so stdlib code can accept review/fix providers and prompts without
   runtime-transported values or hard-coded extern names. All refs must
   specialize before executable runtime state is produced.

3. **Composable typed loops.** `loop/recur` already provides typed iterative
   control. The remaining requirement is to prove and, where needed, complete
   its use inside imported stdlib procedures/workflows, with typed loop
   outputs, a typed terminal result, explicit exhaustion, source maps, and
   resume-safe lowering.

4. **Generic result-bundle and path allocation.** Library code must request
   semantic targets such as "review decision bundle" or "phase result bundle"
   without exposing `__write_root__...` inputs or hard-coded paths. The compiler
   owns deterministic allocation, validation, source maps, and path-safety
   checks.

5. **Hygienic source-map-preserving expansion.** Existing macro hygiene must
   either be kept out of effectful stdlib control flow or extended with explicit
   effect introduction. If macros are used to make the library ergonomic,
   expansion must preserve authored origin, library origin, generated step
   origin, generated hidden-input origin, and generated path origin.
   Macro-introduced effects must remain visible to validation and the effect
   graph.

6. **Structured dataflow for stdlib review results.** The language does not
   need built-in findings semantics. It needs generic records, unions,
   structured provider outputs, typed procedure parameters, and loop-carried
   values sufficient for the `.orc` stdlib `review-revise-loop` to define
   review decisions, findings, reports, blocker classes, and exhaustion reasons.
   Until list types are available, findings may be carried as a schema-validated
   JSON artifact path, but the semantic value must be validated before
   publication and revise/fix consumption rather than extracted from markdown.

7. **Module visibility and stdlib packaging.** Stdlib workflows/procedures must
   import, export, specialize, and source-map like project modules. A consumer
   should be able to inspect which stdlib definition generated each executable
   node.

8. **Negative validation for abstraction leaks.** The compiler must reject
   library definitions that leak hidden write-root inputs, treat pointer files
   as state authority, hide effects in macros, or route on report prose.

Readiness before acceptance:

| Capability | Required for review loop? | Acceptance fixture | Acceptance status |
| --- | --- | --- | --- |
| Imported effectful stdlib `defproc` or workflow | Yes | Import stdlib loop and emit DSL-visible provider, command, loop, and match nodes | Must be proven by implementation audit |
| ProviderRef specialization | Yes | Pass review/fix providers into stdlib with no runtime provider value | Must be proven by implementation audit |
| PromptRef specialization | Yes | Pass prompts into stdlib with no hard-coded extern or runtime prompt value | Must be proven by implementation audit |
| `loop/recur` to resume-safe DSL loop | Yes | `REVISE -> fix -> APPROVE` with a persisted loop checkpoint | Must be proven by implementation audit |
| Generated bundle/path allocation | Yes | Compile stdlib loop without public hidden write-root inputs | Must be proven by implementation audit |
| Effect graph and source maps across stdlib expansion | Yes | Generated nodes record call site, stdlib definition, and generated-node provenance | Must be proven by implementation audit |
| Negative validation for abstraction leaks | Yes | Reject stdlib definitions that route on report prose, leak hidden roots, or hide effects | Must be proven by implementation audit |

New or completed authoring syntax:

```lisp
(defrecord ReviewFinding
  (id String)
  (severity FindingSeverity)
  (summary String)
  (evidence String))

(defpath ReviewFindingsJsonPath
  :kind relpath
  :under "artifacts/work"
  :must-exist true)

(defrecord ReviewFindings
  (schema_version String)
  (items_path ReviewFindingsJsonPath))

(defunion ReviewDecision
  (APPROVE
    (review_report ReviewReportPath)
    (findings ReviewFindings))
  (REVISE
    (review_report ReviewReportPath)
    (findings ReviewFindings))
  (BLOCKED
    (review_report ReviewReportPath)
    (blocker_class BlockerClass)
    (findings ReviewFindings)))

(defunion ReviewLoopResult
  (APPROVED
    (review_report ReviewReportPath)
    (findings ReviewFindings))
  (BLOCKED
    (review_report ReviewReportPath)
    (blocker_class BlockerClass)
    (findings ReviewFindings))
  (EXHAUSTED
    (last_review_report ReviewReportPath)
    (findings ReviewFindings)
    (reason String)))
```

`ReviewDecision` is the per-iteration review result. `ReviewLoopResult` is the
terminal loop result. `APPROVE` maps to terminal `APPROVED`; `REVISE` invokes
revise/fix and repeats; `BLOCKED` maps to terminal `BLOCKED`; max-iteration
exhaustion maps to terminal `EXHAUSTED`. Raw unconstrained `Json` findings do
not satisfy primary-promotion parity. Until first-class list types exist,
`items_path` must point to JSON that validates against `ReviewFindings.v1`
before publication and before revise/fix receives it.

`ReviewFindings.v1` is validated by a Workflow Lisp `defschema` validator if
available in this tranche, or by a certified `review-findings-v1` validation
adapter generated by the stdlib loop. `schema_version` must equal
`ReviewFindings.v1`; a plain string value is not sufficient without that
validation rule. Validation runs before the `ReviewFindings` record is
published to loop state and again before revise/fix receives it after resume.
Malformed findings fail as an output-contract failure, not as a review
decision.

Workflow input defaults should be expressible at the boundary:

```lisp
(defworkflow design-plan-impl-review-stack
  ((brief_path BriefPath :default "workflows/examples/inputs/design_brief.md")
   (design_target_path DesignDocTarget :default "docs/plans/example-design.md"))
  -> StackOutput
  ...)
```

Syntax status: proposed. Semantic contract: accepted target after spec and test
gates. Defaults belong to the workflow boundary, obey the same path/type
validation as explicit inputs, and are overridden by CLI/caller-provided inputs.

### 2. Compiler And Lowering Layer

The compiler owns all generated paths and hidden wiring. Generated write-root
inputs are not public workflow API.

Generated write roots may be hidden from the user-facing `.orc` API only if the
compiler lowers them to deterministic DSL-visible bindings that satisfy the
reusable-call write-root contract. Each generated root needs a stable semantic
identity derived from workflow id, call-site id, phase id, loop iteration where
applicable, and compiler/language version; source-map provenance; collision
checks across repeated calls and branch/loop expansions; resume reconstruction
rules; and a debug/explain projection.

Compiler-generated bundle and temporary paths must be run-isolated unless the
authored contract explicitly requests a stable workspace artifact. Stable
semantic identity is source-map/debug identity; the concrete write path must
include the runtime run root or another collision-proof generated namespace.
Resume must reconstruct the same concrete path for the same run.

V1 managed bundle path model:

- The compiler may emit internal managed write-root inputs for generated bundle
  paths because the current lowering path already represents managed write roots
  that way.
- Loader/runtime binding owns those values before validation/execution. CLI
  users and workflow callers must not be required to provide or override them.
- Public compiled workflow documentation and promoted entrypoint help must hide
  these inputs. Debug projections may show them only with generated-origin
  metadata and source-map provenance.
- Shared validation must distinguish public required inputs from internal
  managed inputs. A promoted entrypoint fails parity if tests or users must pass
  `__write_root__...` inputs manually.
- The runtime reconstructs the same managed value for the same run on resume and
  rejects caller-provided conflicting values for runtime-owned command bundle
  targets.

The compiler owns generic primitives and generic library expansion. It must not
own workflow-specific control idioms such as `review-revise-loop`.

`command-result` lowering must:

- map record return types to deterministic JSON-bundle contracts;
- map union return types to a variant-proof surface: either normative
  `variant_output.path`, or an authoritative `output_bundle.path` followed by a
  compiler-owned validator/projection step with equivalent discriminant proof;
- generate a deterministic result-bundle path;
- record source-map origins for the high-level form, generated step, and
  generated path;
- ensure the command receives the resolved bundle path through the runtime
  command environment;
- expose only validated bundle fields as typed refs;
- ignore stdout JSON for semantic success;
- reject command boundaries without certified command metadata when the command
  carries workflow semantics.

Generic effectful composition must:

- extend the existing static ref model so provider and prompt refs specialize
  like workflow and procedure refs before runtime artifacts are produced;
- allow imported reusable library definitions to generate provider steps,
  command steps, `match`, typed loops, and materialization through ordinary
  composition;
- preserve source maps across authored call site, stdlib definition, macro
  expansion if any, generated Core statements, hidden inputs, and generated
  paths;
- keep generated effects visible in Semantic IR and the effect graph;
- reject runtime transport of procedure/provider/prompt refs.

Stdlib control forms lower by specializing imported stdlib definitions before
Core DSL lowering. For this migration slice, `review-revise-loop` should compile
as an imported stdlib workflow/procedure boundary or equivalent specialized
private workflow, producing DSL-visible steps, call-frame state, loop state,
source maps, and outputs. It must not rely on macro-generated hidden effects or
a review-loop-specific compiler branch.

The stdlib `review-revise-loop` definition must compile through those generic
capabilities to the same executable families a hand-authored workflow would use:
`repeat_until`, provider steps, structured output bundles, `match`, and
materialization.

Canonical generated executable shape for this migration slice:

```text
caller workflow
  call generated/private workflow stdlib__review_revise_loop__<call_site_id>
    inputs:
      draft artifact refs, review provider ref, revise/fix provider ref,
      prompt refs, loop budget, generated bundle roots
    outputs:
      ReviewLoopResult bundle, terminal status, review report, findings

generated/private workflow
  repeat_until review_loop:
    loop-frame outputs:
      review_status, latest_review_report, latest_findings,
      latest_review_decision_bundle
    steps:
      provider step writes ReviewDecision bundle
      match ReviewDecision:
        APPROVE -> materialize latest outputs and stop
        REVISE  -> run revise/fix, carry findings, recur
        BLOCKED -> materialize blocker outputs and stop
    on_exhausted.outputs:
      review_status = "EXHAUSTED"
  final projection:
    build ReviewLoopResult from review_status and loop-frame outputs
```

The caller observes a normal call-frame boundary and typed outputs. The private
workflow owns the `repeat_until` frame, generated bundle roots, and terminal
projection. This generated/private workflow is produced by generic stdlib
specialization, not by a review-loop-specific compiler primitive. If
implementation proves that inlining is required instead, this design must be
revised to spell out equivalent call-frame, source-map, and resume guarantees
before promotion.

Exhaustion lowering must respect current `repeat_until` behavior:

- The loop body materializes scalar review status and structured review result
  outputs on each completed iteration.
- `on_exhausted.outputs` overrides only scalar terminal markers, such as
  `review_status = "EXHAUSTED"`.
- The last review report and findings are loop-frame outputs from the final
  completed iteration, not values invented by exhaustion handling.
- A generated final projection step constructs `ReviewLoopResult.EXHAUSTED`
  from the scalar exhausted marker plus the last materialized review outputs.
- If the final iteration fails before those outputs exist, the loop fails as an
  ordinary execution or contract failure, not as `EXHAUSTED`.

`resume-or-start` lowering must:

- validate prior reusable state through a certified adapter or future
  runtime-native validator;
- normalize resumed and fresh branches to the same return type;
- require referenced artifacts to still exist;
- reject stale, failed, partial, or schema-incompatible state;
- never treat pointer-file existence as reusable-state authority.

Default lowering must:

- attach defaults to generated Core workflow input contracts;
- preserve caller override precedence;
- reject defaults that violate path roots, type contracts, or `must-exist`;
- keep compiler-owned hidden inputs out of public documentation unless a debug
  surface explicitly requests them.

### 3. Runtime Layer

The runtime should not learn Lisp-specific behavior. It should execute the
generated Core DSL and enforce contracts.

Runtime/spec deltas required:

- For every command step declaring `output_bundle.path` or a future
  `variant_output.path`, the runtime resolves the workspace-relative contract
  path before command launch and exposes it as
  `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`. This environment variable is only the
  command's discoverable handle for the declared output target.
- If the command declares or receives a conflicting
  `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, the runtime-owned value wins.
- The runtime creates or validates the bundle parent directory according to the
  output contract before launch, then validates the bundle after exit `0`.
- The bundle file is authoritative for structured command results. Stdout may
  be captured for logs/debug, but stdout JSON is not semantic authority for
  promoted `.orc` workflows.
- If the command exits `0` and the bundle file is missing or invalid, the step
  fails as an output-contract failure.
- If the command exits non-zero, structured output validation does not mask the
  command failure.
- Resolved bundle paths must remain workspace-relative and path-safe.
- Repeat-until resume state remains the existing runtime authority for loop
  continuation; generated Lisp source maps are observability and debugging
  evidence, not runtime routing input.

These are general command-step contracts, not Lisp-specific runtime behavior.

### 4. Migration Evidence Layer

A `.orc` replacement can become primary only when a parity report says it is
non-regressive.

Intended YAML primary behavior is characterized from the current YAML primary at
the promotion baseline commit, its accepted tests, and a baseline run when one is
safe. Normative DSL specs win over accidental YAML behavior; explicit accepted
differences must be listed in the parity report.

Required evidence per promoted workflow family:

- compile always emits source `.orc`, a lowered workflow dictionary accepted by
  shared validation, source map, debug projection, compiler version, target DSL
  version, and generated-name manifest;
- optional compiler artifacts such as Core AST, Semantic IR, Executable IR,
  effect graph, proof graph, and reference catalog are emitted when implemented
  and accepted; otherwise the parity report records them as `not_implemented`;
- shared validation passes;
- dry-run passes;
- at least one real smoke or targeted integration run passes when safe;
- YAML baseline behavior is characterized;
- `.orc` output contracts, terminal states, artifacts, and resume behavior match
  the intended YAML primary behavior;
- deprecated YAML-era mechanics are explicitly listed and justified.

Real smoke is unsafe only when it would mutate external systems, spend
unbounded provider budget, require unavailable credentials, or alter user data
outside the workspace. In that case, the parity report must record
`smoke_or_integration.waived = true` with an owner, expiry, and justification,
and include targeted integration evidence for the skipped runtime behavior.

`cycle_guard_demo` should not block key high-level migration unless the project
chooses to support native `.orc` cycle-guard conformance. Its current fake
`terminal_status`/`guard_cycles` surface is useful as a command-result bridge
test, not as true parity with YAML cycle-guard semantics.

## Contracts And Interfaces

### Command Structured Output Contract

Old behavior:

- A command step with `output_bundle` validates a JSON file after successful
  command execution.
- Runtime implementation may expose a bundle path to commands, but migration
  docs did not treat this as a promotion contract.

New behavior:

- For command steps with declared structured bundle paths, the resolved bundle
  path is provided to the process as
  `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`.
- The command must write the structured bundle to that path.
- The runtime validates the bundle before exposing typed artifacts.
- The compiler must not require callers to pass compiler-owned hidden bundle
  inputs for promoted entrypoints.
- Command-produced union results use `variant_output.path` when that is
  normative. Until then, they use a generated `output_bundle.path` only for the
  raw discriminant and payload, followed by a compiler-owned
  validator/projection step that establishes variant proof.

Compatibility:

- Existing YAML command steps continue to work.
- Existing scripts that already honor `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` remain
  compatible.
- Stdout JSON may remain useful for manual debugging or legacy compatibility,
  but it is not the promoted semantic path.

### Review Loop Contract

Old behavior:

- YAML review loops use `repeat_until`, shell glue, report pointers, and
  sometimes inline findings extraction.
- Current `.orc` migrations can perform one draft/review pass without full loop
  parity.

New behavior:

- `review-revise-loop` is a standard `.orc` stdlib workflow/procedure for
  bounded review/fix loops, not a compiler-special language form.
- It has two typed layers: `ReviewDecision` for one review iteration and
  `ReviewLoopResult` for the terminal loop result.
- `APPROVE` exits with `APPROVED`; `REVISE` deterministically invokes
  revise/fix and repeats; `BLOCKED` exits with `BLOCKED`.
- Exhaustion exits with `EXHAUSTED` only after the last completed iteration has
  produced the outputs required by the final projection.
- Reports are views; typed review decisions, terminal results, and validated
  findings are authority.

Transition table:

| Event | Loop action | `ReviewLoopResult` | YAML-compatible projection |
| --- | --- | --- | --- |
| `ReviewDecision.APPROVE` | Exit | `APPROVED` | Phase approved |
| `ReviewDecision.REVISE` with budget remaining | Run revise/fix and recur | None yet | Not completion |
| `ReviewDecision.REVISE` with budget exhausted | Exit through final projection | `EXHAUSTED` | Blocked / revise-exhausted |
| Provider-authored `ReviewDecision.BLOCKED` | Exit | `BLOCKED` | Blocked with blocker class |
| Invalid provider output | Fail contract | No semantic result | Provider output contract failure |

Compatibility:

- Existing YAML workflows remain primary until parity is proven.
- Legacy report extraction can remain behind allowlisted certified adapters only
  for migration, with replacement metadata.

### Reusable State Contract

Old behavior:

- YAML workflows frequently use file-existence gates, state-root conventions,
  and pointer files to decide whether work can be reused.

New behavior:

- `resume-or-start` validates a canonical prior state object and returns the
  same type as a fresh run.
- Reuse requires schema compatibility, approved terminal state, and existing
  referenced artifacts.
- Invalid prior state routes to fresh execution or a typed non-reusable result,
  depending on the authored form.
- `ReusablePhaseState.v1` is a derived, validated summary of canonical runtime
  state, not an alternative authority.

Minimum reusable-state shape:

```json
{
  "schema": "ReusablePhaseState.v1",
  "source_run_id": "",
  "source_step_id": "",
  "source_call_frame_id": "",
  "workflow_checksum": "",
  "phase_id": "implementation",
  "producer_workflow": "",
  "producer_compiler": "",
  "terminal": "APPROVED",
  "source_inputs_hash": "sha256:...",
  "producer_fingerprint": "sha256:...",
  "result_type": "ImplementationResult",
  "artifact_refs": {
    "plan_path": {
      "type": "relpath",
      "value": "docs/plans/example.md",
      "sha256": "..."
    }
  },
  "created_at": "",
  "compatibility": {
    "dsl_version": "2.14",
    "state_schema_version": ""
  }
}
```

Validation outcomes are `REUSABLE`, `STALE`, `MISSING_ARTIFACT`,
`FAILED_PRIOR_STATE`, `SCHEMA_MISMATCH`, and `UNSUPPORTED_VERSION`.
`STALE` means the prior state has a supported schema and terminal, but its input
hash, producer fingerprint, dependency hash, or artifact checksum no longer
matches the current reusable-state policy.

Hash and fingerprint derivation:

- `source_inputs_hash` is computed from canonical JSON for public workflow
  inputs after defaults and caller overrides are resolved. Relative paths are
  normalized workspace-relative. Inputs declared content-sensitive include the
  referenced file digest; ordinary path-valued inputs include the normalized path
  string. Generated hidden roots, run ids, timestamps, and absolute workspace
  prefixes are excluded.
- `producer_fingerprint` is computed from the `.orc` source digest, imported
  stdlib definition digests, compiler version, target DSL version, lowering
  options that affect executable shape, and specialized provider/prompt/workflow
  refs. It excludes transient runtime state.
- Artifact checksums are computed over the referenced artifact content after
  path-safety validation. A missing artifact is `MISSING_ARTIFACT`, not `STALE`.
- Schema or version incompatibility wins over staleness: unsupported schema or
  compatibility metadata returns `SCHEMA_MISMATCH` or `UNSUPPORTED_VERSION`
  before hash comparison.
- The producer records the source run id, source step id or call-frame id,
  workflow checksum, input hash basis, artifact lineage basis, and artifact
  content hashes used to validate reuse. On resume, the validator compares this
  summary against current policy and referenced artifact contents; it must not
  trust the summary alone.

Compatibility:

- Adapter-backed validators are acceptable initially.
- Pointer files remain compatibility representations only.

### Workflow Input Defaults

Old behavior:

- YAML workflow inputs support defaults.
- `.orc` promoted entrypoints may require explicit inputs even when the YAML
  primary did not.

New behavior:

- Workflow Lisp supports input defaults at the `defworkflow` boundary and
  lowers them to Core workflow input defaults.
- Literal defaults are type-checked at compile time, workspace/path constraints
  are checked during shared validation, and runtime checks are reserved for
  dynamic inputs whose existence cannot be proven earlier.

## Dependencies And Sequencing

Recommended sequencing:

1. Accept normative spec deltas for command structured-output bundle path
   injection, command-produced union bundle handling, output-contract failure
   shape, and path safety.
2. Document and test the command structured-output runtime contract.
3. Complete generic `.orc` effectful composition support for reusable library
   definitions: provider/prompt refs, stdlib-owned use of existing
   workflow/procedure refs and `loop/recur`, generated path allocation, and
   source-map-preserving expansion.
4. Finalize `command-result` lowering so hidden bundle paths are compiler-owned
   and not public entrypoint inputs.
5. Implement `review-revise-loop` as ordinary `.orc` stdlib code, including
   stdlib-owned findings propagation over generic structured dataflow.
6. Implement or complete `.orc` input defaults.
7. Finalize `StateLayout` and `resume-or-start` reusable-state validation for
   phase outputs.
8. Define and enforce the machine-readable parity report schema.
9. Re-run the existing migrated workflow family and update parity reports.
10. Only then migrate additional key workflow families.

Independent work:

- Migration promotion checklist and parity report schema can proceed in
  parallel with compiler/runtime work.
- Certified legacy adapter inventory can proceed in parallel.

Blocked work:

- Deprecating YAML primaries is blocked until the relevant `.orc` parity report
  is non-regressive.

## Invariants And Failure Modes

Invariants:

- Structured bundles and typed artifacts are authority.
- Reports, debug YAML, stdout, pointer files, and source maps are views unless a
  specific contract says otherwise.
- Generated hidden inputs are compiler/runtime implementation details, not user
  workflow API.
- A successful command process does not imply a successful workflow step until
  output contracts validate.
- `REVISE` is not completion.
- Exhausted review loops are explicit non-completion, not failed hidden control
  flow.
- Resume/reuse cannot be based on file existence alone.
- Source maps must preserve authored-to-generated provenance for generated
  steps and paths.

Failure modes:

- Missing command bundle after exit `0`: output contract failure.
- Invalid bundle JSON: output contract failure.
- Missing required artifact target: output contract failure.
- Review provider returns invalid decision: provider output contract failure.
- Review loop exhausts: typed `EXHAUSTED` result.
- Reusable state is stale or incomplete: typed non-reusable result or fresh
  branch, according to `resume-or-start` contract.
- Default input violates path/type contract: compile or validation failure.

## Security, Operations, And Performance

Security:

- Bundle paths and generated state paths must remain workspace-relative.
- Runtime must reject absolute paths and `..` escapes before command launch or
  output validation.
- Certified adapters carrying workflow semantics must declare effects.

Operations:

- Promoted `.orc` workflows should be easier to resume and inspect because
  loop, phase, and review state are typed and source-mapped.
- Operators should not have to pass `__write_root__...` hidden inputs for
  normal runs.

Performance:

- Review/revise parity may add generated materialization and projection steps,
  but this cost is negligible next to provider execution.
- Runtime validation cost is bounded by existing JSON bundle and artifact
  validation behavior.

## Evidence And Implementation Boundaries

Implementation evidence must exercise the default path, not a fixture-only
shortcut.

For `command-result`:

- a real command process must receive `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`;
- the command must write the bundle;
- runtime must validate the file and expose typed artifacts;
- tests must fail if stdout JSON is present but the bundle file is missing.

For `review-revise-loop`:

- tests must prove the loop is defined in `.orc` stdlib and reaches runtime
  through generic library composition, not a compiler-special lowering branch;
- tests must drive `REVISE -> fix/revise -> APPROVE`;
- tests must drive exhaustion;
- final outputs must come from the loop frame or terminal projection, not the
  first review step;
- findings must be consumed by revise/fix in structured form.

For `resume-or-start`:

- tests must cover reusable approved state, stale state, missing artifact state,
  failed state, and schema mismatch.

For migration promotion:

- the promotion command computes `non_regressive`; authors do not set it by
  hand.
- parity reports must contain the computed `non_regressive` value and the
  evidence used to derive it.

Minimum parity-report shape:

```json
{
  "workflow_family": "design_plan_impl_stack",
  "candidate": "workflows/example.orc",
  "yaml_primary": "workflows/example.yaml",
  "compiler_version": "",
  "dsl_version": "2.14",
  "evidence": {
    "compile": {"status": "pass", "artifacts": []},
    "shared_validation": {"status": "pass"},
    "dry_run": {"status": "pass"},
    "smoke_or_integration": {
      "required": true,
      "passed": true,
      "waived": false,
      "waiver_reason": null,
      "owner": null,
      "expires": null
    },
    "baseline_characterization": {
      "inputs": "",
      "outputs": "",
      "terminal_states": "",
      "artifacts": "",
      "resume_behavior": ""
    },
    "output_contract_parity": "pass",
    "terminal_state_parity": "pass",
    "artifact_parity": "pass",
    "resume_parity": "pass"
  },
  "deprecated_yaml_mechanics": [
    {"mechanic": "pointer-file gate", "replacement": "typed state"}
  ],
  "non_regressive": false
}
```

`non_regressive` is computed as true only when:

- `compile.status`, `shared_validation.status`, and `dry_run.status` are
  `"pass"`;
- smoke or targeted integration evidence passed, or the waiver is present,
  owned, unexpired, justified, and accompanied by targeted evidence for the
  skipped runtime behavior;
- baseline characterization records inputs, outputs, terminal states, artifacts,
  and resume behavior;
- output contract parity, terminal state parity, artifact parity, and resume
  parity are all `"pass"`;
- every deprecated YAML mechanic has either a concrete replacement or an
  accepted-risk waiver owned by the promotion policy;
- optional compiler artifacts recorded as `not_implemented` are not required by
  that workflow family's promotion policy.

Any missing required field, expired waiver, manually asserted
`non_regressive=true`, or required artifact recorded as `not_implemented`
forces `non_regressive=false`.

## Compatibility And Migration

Existing YAML workflows remain valid and primary.

Migration is additive:

1. Add or update `.orc` replacement.
2. Compile and validate.
3. Run dry-run and required smoke/integration, or record an explicit waiver with
   targeted integration evidence.
4. Generate parity report.
5. Let the promotion command compute `non_regressive` from required evidence.
6. Update docs/catalog to identify `.orc` as primary.
7. Keep YAML as compatibility or fixture until an explicit deprecation decision.

Deprecated behavior:

- inline report parsing for decisions or findings;
- pointer-file existence gates;
- user-authored hidden bundle paths;
- prompts that manage workflow loops;
- treating dry-run success as replacement parity.

## Verification Strategy

Unit tests:

- `command-result` lowering emits authoritative bundle contracts, discriminant
  handling for unions, source maps, and no public hidden input requirement for
  promoted entrypoints.
- input defaults parse, type-check, lower, and reject invalid defaults.
- stdlib review-result and findings records validate through generic
  structured type checks and reject malformed findings.

Runtime integration tests:

- command structured output path is injected and validated.
- missing bundle after command success fails visibly.
- invalid bundle after command success fails visibly.
- repeat-until resume still works for stdlib-defined review loops.

Workflow Lisp integration tests:

- stdlib `review-revise-loop` imports and compiles through generic effectful
  composition.
- stdlib `review-revise-loop` approves first pass.
- stdlib `review-revise-loop` revises once then approves.
- stdlib `review-revise-loop` exhausts and returns `EXHAUSTED`.
- exhaustion projection fails as an ordinary contract failure if the final
  completed iteration did not materialize required review outputs.
- revise/fix receives findings from the previous review.
- `resume-or-start` reuses approved state and rejects stale/failed state.

Migration tests:

- existing key migration tests continue to compile and dry-run.
- promoted stack workflow has a real smoke or targeted integration run.
- parity report generation rejects `non_regressive=true` when any required
  evidence is missing.
- parity report records optional IR artifacts as `not_implemented` rather than
  silently omitting them.

## Declarative Acceptance Scenarios

### Command Result Bundle Authority

Initial state: a `.orc` workflow calls a certified command adapter returning a
typed record. The command writes JSON only to the path from
`ORCHESTRATOR_OUTPUT_BUNDLE_PATH`.

Entrypoint: `python -m orchestrator run workflow.orc --entry-workflow ...`

Expected result: the run completes, `state.json` exposes typed artifacts from
the bundle, and no caller-provided hidden write-root input is required.

Forbidden behavior: the run must not pass by parsing stdout if the bundle file
is absent.

### Review Revise Loop

Initial state: fake providers return `REVISE` with findings, then the fix
provider writes an updated artifact, then review returns `APPROVE`.

Entrypoint: a `.orc` phase importing the stdlib `review-revise-loop`.

Expected result: the fix step runs exactly once, receives structured findings,
the loop exits approved, and the final phase output reflects the approved
iteration.

Forbidden behavior: the workflow must not record completion after the first
`REVISE`.

### Reusable State

Initial state: a prior phase state says `APPROVED` and references existing
artifacts.

Entrypoint: a `.orc` workflow using `resume-or-start`.

Expected result: reusable state validates and normalizes to the same return type
as a fresh phase execution.

Negative case: if the referenced artifact is missing, reuse is rejected and the
workflow follows the documented fresh or non-reusable branch.

### Migration Promotion

Initial state: a YAML primary and `.orc` candidate both exist.

Entrypoint: migration parity command or workflow.

Expected result: the promotion command computes `non_regressive=true` only when
compile, shared-validation, dry-run, required smoke/integration or explicit
waiver, and behavioral parity checks all pass.

Forbidden behavior: a candidate that only parses or dry-runs must remain
non-primary.

## Success Criteria

- Runtime command structured-output behavior is documented and tested.
- Required command bundle-path, output failure, and path-safety spec deltas are
  accepted in the relevant normative surfaces.
- `command-result` no longer requires users to pass compiler-owned hidden
  bundle inputs for promoted workflows.
- Generic effectful library composition supports provider calls, command calls,
  typed loops, matches, generated result paths, and compile-time
  provider/prompt/workflow/procedure refs without runtime-transported procedure
  values, reusing the existing `defproc`, `WorkflowRef`, `ProcRef`, `bind-proc`,
  `let-proc`, and `loop/recur` substrate where it already satisfies the
  contract.
- `review-revise-loop` is implemented as ordinary `.orc` stdlib code and is
  accepted as the canonical high-level replacement for YAML review/fix
  `repeat_until` loops.
- Review findings are validated structured state and can be consumed by
  revise/fix steps.
- Workflow Lisp input defaults lower to existing DSL input defaults.
- `resume-or-start` has a reusable-state validation contract with negative
  tests.
- Parity reports are machine-validatable and compute `non_regressive` from
  required evidence.
- The existing design/plan/impl `.orc` migration can be rerun with
  non-regressive parity, or the report explicitly names any remaining blocker.

## Stop / Revise Criteria

Revise this design if:

- implementation requires a new YAML DSL primitive rather than lowering onto
  existing v2.14 surfaces;
- implementation requires a compiler-special `review-revise-loop` path rather
  than generic `.orc` composition;
- runtime command bundle injection cannot be made reliable without exposing
  hidden inputs as public API;
- command-produced union results require implicit `variant_output` paths instead
  of an explicit generated bundle contract;
- the stdlib findings schema requires unsupported collection types that would
  broaden the type-system work beyond this migration tranche;
- `repeat_until` cannot express the required review/fix behavior without
  weakening resume semantics;
- parity evidence cannot distinguish real runtime behavior from fixture-only
  helper behavior.
