# Workflow Lisp Core Calculus And Compiler Middle-End

Status: accepted architecture; the flat route (defunctionalization into flat
steps and the step runtime that executed them, targets through 2.34) was
retired on 2026-10-13 and executable entries through 2.34 are refused; the
retained middle-end (WCC elaboration, ANF normalization, scope/effect/proof
analysis) feeds the closed program that the evaluated runtime executes at
2.35/2.36 (§§10.1, 11.4, 13.5, 15)
Kind: architecture decision / compiler architecture
Created: 2026-06-09
Updated: 2026-10-15 (flat route retired; evaluated execution is the only route)
Execution scope: the [executor retirement design](workflow_lisp_executor_retirement.md)
and `specs/cli.md` govern executable admission; the
[retirement retrospective](../reports/2026-10-13-flat-route-retirement-retrospective.md)
records which modules were deleted and which were kept. Sections 11.3, the
flat-identity part of 11.4, 12, 13.4, 14.4-14.6 and 17-21 describe the
retired flat route and are kept as history.
Scope: retained typed WCC elaboration, ANF normalization, second-class
join-point control and scope/effect/proof analysis feeding checked closed-program
construction. Defunctionalization into flat steps is retired architecture, not
a current constraint or compatibility backend.

Authority:

- `docs/design/workflow_lisp_frontend_specification.md` remains the umbrella
  Workflow Lisp frontend contract; this document refines its compilation
  pipeline, not its language surface or authority rule.
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
  records completed migration history; it is not a current tranche selector.
- Normative DSL/runtime behavior remains in `specs/`.
- Shared typed checking and checked-program validation preserve semantic
  authority; the evaluated runtime/memo owns execution and persistence.
- This document does not by itself promote any `.orc` workflow to primary
  surface.
- A behavior described here is implementation-complete only when the listed
  verification evidence passes.

Related docs:

- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
- `docs/design/workflow_lisp_runtime_migration_foundation.md`
- `docs/design/workflow_lisp_unified_frontend_design.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_lisp_semantic_workflow_ir.md`
- `docs/design/workflow_lisp_executable_ir.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_proc_refs_partial_application.md`
- `docs/design/workflow_lisp_compile_time_parametric_specialization.md`
- `docs/design/workflow_lisp_runtime_closures_boundary.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/design/workflow_lisp_executor_retirement.md`
- `docs/reports/2026-06-09-design-delta-drain-orc-migration-frontend-runtime-findings.md`
- `docs/reports/2026-10-13-flat-route-retirement-retrospective.md`
- `specs/dsl.md`
- `specs/io.md`
- `specs/state.md`

<a id="1-purpose"></a>
<a id="2-executive-decision"></a>
<a id="3-relationship-to-the-post-foundation-target"></a>

The original problem, flattening decision and post-foundation delivery ownership are historical. Retained calculus/analysis feeds the checked program; no schema-1/2 flat runtime or resume path remains. See the [preserved record](../reports/documentation-history/workflow_lisp_core_calculus_middle_end-history.md#1-purpose).

<a id="4-authority-and-dependency-direction"></a>
<a id="41-this-document-consumes"></a>
<a id="42-this-document-owns"></a>
<a id="43-this-document-does-not-own"></a>
<a id="5-target-and-prohibited-dependency-directions"></a>
<a id="6-problem"></a>
<a id="7-goals"></a>
<a id="8-non-goals"></a>
<a id="9-architecture-invariants"></a>
<a id="103-elaboration-of-surface-forms"></a>
<a id="113-defunctionalization"></a>
<a id="132-environment-to-state-mapping"></a>
<a id="134-dual-compile-equivalence-policy"></a>
<a id="135-what-the-runtime-sees"></a>
<a id="14-contracts-and-interfaces"></a>
<a id="141-typechecker"></a>
<a id="142-elaborator"></a>
<a id="143-normalizer-and-analyzer"></a>
<a id="144-defunctionalizer"></a>
<a id="145-shared-validation"></a>
<a id="146-projections"></a>
<a id="15-alternatives-considered"></a>
<a id="16-deferred-work"></a>
<a id="17-work-blocked-and-not-blocked"></a>
<a id="18-evidence-and-implementation-boundaries"></a>
<a id="181-required-evidence"></a>
<a id="182-prohibited-evidence"></a>
<a id="19-compatibility-and-migration"></a>
<a id="20-verification-strategy"></a>
<a id="21-declarative-acceptance-scenarios"></a>
<a id="211-nesting-by-construction"></a>
<a id="212-typecheck-owns-the-boundary"></a>
<a id="213-equivalence-gated-route-flip"></a>
<a id="214-resume-schema-safety"></a>
<a id="22-success-criteria"></a>
<a id="23-summary-recommendation"></a>
<a id="12-incremental-migration-tranches"></a>
<a id="121-tranche-m0-characterization-oracle"></a>
<a id="122-tranche-m1-calculus-and-pure-subset"></a>
<a id="123-tranche-m2-straight-line-effects"></a>
<a id="124-tranche-m3-case-and-join-points"></a>
<a id="125-tranche-m4-loops-and-the-full-fixture"></a>
<a id="126-tranche-m5-route-flip-and-lowerer-deletion"></a>

The remaining flat dependency architecture, environment-to-state mapping, rollout/equivalence policy and acceptance inventory are historical. Current calculus/typed analysis/identity/diagnostic rules follow below. See the [preserved record](../reports/documentation-history/workflow_lisp_core_calculus_middle_end-history.md#4-authority-and-dependency-direction).

## Current Ownership And Invariants

The frontend baseline owns language/type/import rules. This component owns
retained WCC elaboration, lexical scope, normalization and proof/effect analysis;
`workflow_lisp/closed/` constructs the checked program and the evaluated runtime
owns execution/memo persistence. Shared catalogs and exact source provenance
remain available to typed imports, diagnostics and LSP. No migration design,
representation carrier or old header selects a flat executor.

- Join points remain second-class, never stored, returned or transported.
- `inject` determines output variant identity; `case` supplies field proof only.
- Binding visibility follows defining scope/dominance and lexical owner identity.
- Effect rows retain their closed vocabulary; normalization cannot invent effects.
- Loop budgets/exhaustion retain their accepted typed contracts.
- Semantic identity is independent of source position; source frames remain exact provenance.
- Checked artifacts/site identity and memo validation own admitted resume;
  schema-1/schema-2 flat identities are retained typed/history metadata only.
- Unsupported executable effects refuse at the owning checked admission boundary;
  no claim of universal totality follows from the old flattening design.

## 10. The Workflow Core Calculus

### 10.1 Constructs

At target 2.35 the implemented compiler converts WCC to a closed program
that retains control and callee bodies instead of flattening them as at
targets through 2.34. The closed body uses `let`, `perform`, `call`, `if`, `case`,
`join`, `jump`, `loop`, `continue`, `done` and `halt`; closed values retain
literals/references, operators, records, variants, projections, lists/maps,
pure conditionals/selections, `block`, runtime `context`/`result_path` and
`list_map`. Callee definitions, concrete types, canonical configuration and
perform sites are retained in the artifact.
The exact variants and typed fields are owned by the
[Phase 2 schema](../plans/2026-09-29-workflow-lisp-evaluated-execution-phase-2-plan.md#the-closed-programs-form).
Evidence: `orchestrator/workflow_lisp/closed/build.py`, `closed/values.py`,
`orchestrator/contracts/closed_program/check.py` and
`tests/test_workflow_lisp_closed_program_corpus.py`.
The integrated Phase 3 runtime (`orchestrator/workflow/evaluated/`) evaluates
that closed program through the public entries, as owned by
[evaluated execution §8](workflow_lisp_evaluated_execution.md#8-evaluation-and-resume);
a 2.35 entry never enters the flat lowering below. Evidence:
`tests/test_workflow_evaluated_totality.py` and
`tests/test_workflow_evaluated_cli.py`.

WCC is deliberately small. Target construct count is ten; additions require
amending this document. The implemented model
(`orchestrator/workflow_lisp/wcc/model.py`) carries more node kinds than this
table: `if`, `select`, loop `continue`/`done`, `parallel-map`, and payload
carriers for run references, trials and provider groups.

| Construct | Shape | Role |
| --- | --- | --- |
| `atom` | literals, variable refs, record construction, field projection | pure values; never lowered to steps |
| `inject` | `inject Union.Variant {field: atom, ...}` | variant introduction; sole source of output variant identity |
| `let` | `let x : T = <op> in body` | sequencing; in ANF, `<op>` is a single operation or atom |
| `perform` | `perform class.op(atoms) : T ! row` | effectful operation: provider call, command call, adapter call, workflow call, resource transition, projection, view materialization |
| `case` | `case x of Union.V1(binds) -> body1 \| ...` | variant elimination; opens a proof scope per arm; arms must be exhaustive or carry a typed default |
| `join` | `join k(params: T...) = body in scope` | second-class labeled continuation (join point) |
| `jump` | `jump k(atoms)` | transfer to a join point in scope |
| `rec-join` | `join rec k(params, budget: Bound) = body in scope` | bounded recursive join point; the only loop construct |
| `call` | `call f[spec](atoms) : T ! row` | compile-time-resolved procedure call; `f[spec]` is a specialized `defproc`/ProcRef body, inlined or cloned during elaboration |
| `halt` | `halt atom` | terminal workflow/procedure result |

The table names calculus representation, not executable effect admission.
Historical trial/provider-group/transition/view payload carriers do not admit
those effects to evaluated execution. Only checked admitted sites may execute.

Notes:

- There is no lambda, no first-class function, no store. The only "function
  space" is compile-time-resolved `call` plus second-class `join`. This is
  the smallest extension of straight-line code that expresses arbitrary
  branching and bounded iteration while preserving the no-runtime-closures boundary.
- `rec-join` budgets lower to the same exhaustion semantics the DSL's
  `repeat_until` already defines: budget exhaustion produces a typed
  `EXHAUSTED`-class variant routed like any other case, never a crash.
- `perform` operation classes are the closed effect vocabulary. Adding a
  class is a design change here and in the post-foundation effect summaries
  together.

### 10.2 Typing, effects, and proofs

- Every construct carries a type and an effect row. `atom` and `inject` are
  pure. `perform` and `call` carry rows from their declarations. `let`,
  `case`, `join`, and `jump` propagate rows by union.
- `case` arm bodies typecheck with refined arm bindings plus the arm's variant
  proof in metadata. In surface terms, `((BLOCKED blocked) ...)` binds
  `blocked` as the `BLOCKED` payload; field access on the scrutinee outside a
  proving arm remains a type error.
- A branch returning union type `T` must end in `inject T.V {...}`, a `jump`
  to a join point whose parameters carry `T`, a `call` returning `T`, or
  `halt`. The returned `inject` (or the called procedure's returns) decides
  the variant — eliminating F3 by construction.
- `jump` arity and types must match the join point's parameters; join-point
  parameters are how values flow out of branches and around loop iterations,
  replacing ad hoc "branch projection" rules with ordinary binding.
- Effect rows are checked against declared procedure signatures before
  elaboration; elaboration and normalization may reorganize control but may
  not change a program's row.

## 11. The Middle-End Pipeline

### 11.1 ANF normalization

Normalization brings elaborated programs to administrative normal form:

- every `perform` and `call` result is bound by a `let` to a fresh or
  authored name;
- compound arguments are atomized (bound first, then referenced);
- `case` scrutinees are atoms;
- non-tail `case`/`rec-join` results flow through join points rather than
  implicit expression results; and
- normalization preserves types, rows, proofs, and source frames node by
  node.

After ANF, control structure is fully explicit: a program is a tree of
scopes whose leaves are straight-line `let` sequences ending in `jump`,
`inject`-then-`jump`, or `halt`.

### 11.2 Scope, effect, and proof analysis

Over the normalized program the middle-end computes, per scope:

- binding table (name, type, defining construct, source frame);
- dominance: which bindings each reference may legally see;
- live-out sets per join point (which bindings cross into which jumps);
- effect summary (union of rows, per the closed vocabulary);
- active variant proofs; and
- allocation requests (write roots, bundle paths, view paths) attributed to
  the requesting scope and frame.

This analysis is the artifact the post-foundation target calls the
"composition-normalized structured control graph": `scope_id`, parent scope,
entering control node, active proof, loop/call-frame identity, produced and
projected values, declared effects, and requested allocations all fall out of
ANF structure plus this pass.

### 11.4 Identity and resume

At target 2.35 the compiler assigns local perform sites separately from
call frames; source spans remain provenance. Effect identity in the evaluated
runtime is `(site, activation path)`, as owned by
[evaluated execution §6](workflow_lisp_evaluated_execution.md#6-effect-identity).
The closed artifact uses its own checked schema; no flat lowering schema
identifies its effects. A 2.35 run carries no `lowering_schema_version`: its
header selects the evaluated profile (`specs/state.md`), and resume evaluates
the program again from its entry against the memo instead of restoring a
position in the scopes below. Evidence: `orchestrator/contracts/closed_program/sites.py`,
`tests/test_workflow_lisp_closed_program_sites.py` and, for the runtime,
`tests/test_workflow_evaluated_public_identity.py`.

## 13. Design Details

### 13.1 WCC node contract

Every node carries:

```text
node_id
construct kind
type
effect_row
scope_id
source_frame_stack          ; authored form, macro frames, import frames,
                            ; specialization frames
proof_context               ; active variant proofs
allocation_requests         ; StateLayout semantic requests, if any
```

Join points additionally carry:

```text
join_name (hygienic, owner-chain qualified)
parameters (name, type)
recursive? and budget, for rec-join
live_in / live_out binding sets (filled by analysis)
```

### 13.3 Diagnostics contract

All language-boundary rejection happens at or before typecheck:

- a feature the calculus cannot express is a surface/typecheck diagnostic
  naming the restriction (there are intentionally few: first-class
  procedure values, unbounded recursion, effects outside the closed
  vocabulary);
- elaboration, normalization and checked-program construction failures on
  typechecked programs are compiler defects by definition and must say so in
  their error text, with node provenance; and
- shared-validation failures on generic-route output are likewise compiler
  defects unless the workflow violates a contract the typechecker does not
  own (path safety against the live filesystem, for example).

In the current checkout an internal exception raised after typecheck by
elaboration, normalization or closed-program construction is reported as one
`compiler_defect` diagnostic (exit 2). It says that the program passed
typecheck, names the stage, and points at the authored form being handled; the
diagnostic keeps the exception as its `cause` (no CLI flag prints the
traceback). An `AssertionError` raised outside the orchestrator package is not
converted (`compiler_defect_boundary` in `orchestrator/workflow_lisp/diagnostics.py`,
applied in `orchestrator/workflow_lisp/closed/build.py`). Two internal checks
have codes of their own: `compiler_defect_hoisted_binding_rename` and
`compiler_defect_constructor_type_dropped`; `compiler_defect_loop_control_value`
and the replay-index code `pure_result_replay_unavailable` were retired with
the flat route. Located diagnostics raised under other codes, such as
`workflow_return_not_exportable`, `wcc_lowering_route_unsupported` and
`workflow_signature_mismatch`, keep their codes and do not say so.


## Current Integration And Verification Boundary

Typed elaboration, normalization, scope/effect/proof summaries and source lineage
must agree with the checked artifact consumed by the runtime. Internal failures
after typecheck use the compiler-defect boundary described above; public admission
refusals retain their specific diagnostics. Test current composition through the
public checked compile/run/resume and totality owners named by
[evaluated execution](workflow_lisp_evaluated_execution.md). Historical dual-flat
oracles and old-schema continuation tests preserve evidence for their original
claim; they are not current route prerequisites or a legacy recovery floor.
