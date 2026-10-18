# Workflow Lisp Source-Site Inspection

- **Status:** proposed, unselected and not copy-safe. Implemented (manifest
  module `orchestrator/workflow_lisp/source_sites.py`, not admitted as a
  public surface).
- **Kind:** read-only, compiler-derived inspection contract over admitted
  2.35–2.39 source. It adds no language form, no runtime behavior, no edit
  operation and no optimizer concept.
- **Authority:** the [frontend baseline](workflow_lisp_frontend_specification.md)
  and [evaluated execution](workflow_lisp_evaluated_execution.md) own
  checking, lowering and the closed program; [effect ledger
  simplification](workflow_lisp_effect_ledger_simplification.md) owns inferred
  effects and restrictions; [REPL introspection](workflow_lisp_repl_introspection.md)
  owns interactive module inspection; the [program-search boundary
  invariants](workflow_lisp_program_search_boundaries.md) constrain every
  consumer (§8).
- **Compatibility:** no new target, no spec change, no new `compile` flag and
  no published artifact in the first version. The Python API is internal to
  the repository until a consumer stabilizes its fields.
- **Selection:** [ORC structural search roadmap](../plans/2026-10-18-orc-structural-search-roadmap.md).
  The consumer is the [structural search driver](orc_structural_search_driver.md).
- **Use today:** REPL `:info`, `:type` and `:source` for per-definition facts
  ([CLI](../../specs/cli.md#workflow-lisp-repl-targets-235-and-236)), and the
  `@` provenance on closed-program AST nodes (`Builder.provenance` in
  `orchestrator/workflow_lisp/closed/build.py`) for site start positions.
  There is no per-site type or binding query.
- **Copy safety:** record shapes and code paths below are conceptual.

## 1. Purpose And Scope

An external tool that proposes a replacement for one authored expression needs
four facts the compiler computes but does not expose together: where the
expression is, what it produces, what it may reference and what it depends on.
This design exposes those facts as a read-only **source-site manifest** over
one ordinary successful compilation.

Scope is the manifest only. The [driver design](orc_structural_search_driver.md)
owns edit receipts, scope validation, child snapshots and `candidate_id`
(its sections "Edit Validation And Transactions" and "Candidate Snapshots And
Identities"); the roadmap owns selection. The manifest describes authored
source; it does not make operation kinds interchangeable, does not reify
fragments as values and does not infer types from text.

## 2. What Exists And What Is Missing

Source references name paths and symbols; see the
[durable-reference rule](../documentation_conventions.md#durable-references).

| Fact | Existing carrier | Verdict |
| --- | --- | --- |
| In-memory build keeping `typed_program`, `stage3` and `builder` | `prepare_closed_program_bundle` in `orchestrator/workflow_lisp/closed/artifact.py`; `build_closed_program_bundle` is the written form | reuse as is |
| Per-node type, scope, span, form path | `WccNodeMetadata` in `orchestrator/workflow_lisp/wcc/model.py` is attached to every WCC node while a body is elaborated. Callee bodies are retained on `CallableRequest.prepared_body` (read through `Builder.prepared_by_key`) in `orchestrator/workflow_lisp/closed/build.py`; the entry body is not retained and needs one hook-free re-elaboration through `_command_wcc_body` (P-1, §7) | reuse as is; entry re-elaborated |
| Per-expression inferred effects | none: WCC nodes carry the owner's whole `EffectSummary` (`orchestrator/workflow_lisp/wcc/elaborate.py` passes `typed_body.effect_summary` down to every node), not the expression's | missing; a per-node summary would need a second effect analysis |
| Per-subexpression type in the typed AST | none: typecheck dispatch rebuilds parents from `typed_child.expr` and keeps one root `TypedExpr` (`orchestrator/workflow_lisp/typecheck_context.py`) per definition | missing; WCC metadata is the only per-node carrier |
| Binding names in scope | root `TypedExpr.binding_environment` is name → `BindingIdentity` (`orchestrator/workflow_lisp/typecheck_proofs.py`); `LetStarExpr.binding_identities` holds identities, not types | needs adapter for types (P-1) |
| Canonical type identity | `canonical_type_identity` and `canonical_type_descriptor` in `orchestrator/workflow_lisp/closed/names.py`; `render_type_ref` in `type_env.py` for display | reuse as is |
| Authored procedure and workflow call sites after inline normalization | `AuthoredDirectCall(owner_kind, owner_name, callee_kind, callee_name, authored_callee_span)` on `Stage3CompileResult.authored_direct_calls` (`orchestrator/workflow_lisp/workflows.py`); `callee_kind` is `procedure` or `workflow` only | reuse as is |
| Operation kind | expression node classes in `orchestrator/workflow_lisp/expressions.py` (`ProviderResultExpr`, `ProcedureCallExpr`, `CallExpr`, `RunRefExpr`, `AgentExpr`, `RunProviderPhaseExpr`, composition forms); perform node `class` in the closed program (`orchestrator/contracts/closed_program/check.py`) | reuse as is |
| Inferred effects and authored restriction per definition | `procedure_effect_inspection` in `orchestrator/workflow_lisp/procedures.py`; `EffectSummary` and `unresolved_effect_calls` in `effects.py` | reuse as is |
| Resolved prompt/provider/command/import configuration | `closed_program.json` `configuration`; perform nodes carry `provider`, `prompt`, `inputs`, `dependencies` | reuse as is |
| Executable site identity | `assign_sites` rows `(owner definition, label path)` in `orchestrator/contracts/closed_program/sites.py`; `@` start position and form path on AST nodes; `program_digest` strips `@` (`program.py`) | reuse as is; join needed |
| Exact source bytes read | `SourceReadRecord.revision` in `orchestrator/workflow_lisp/reader.py` (sha256 over the raw bytes read) and `_source_file_digests_from_trace` in `orchestrator/workflow_lisp/build_artifacts.py` | reuse as is |
| Free names of an expression | `free_expr_names` in `orchestrator/workflow_lisp/expression_traversal.py`, as W3 uses for `LetProcBinding.capture_names` | reuse as is |
| Structured "every fact at this span" query | none: the REPL returns text (`repl_inspect.py`), the LSP has no hover and no span → type table ([language server](workflow_lisp_language_server.md)) | missing: this design |

## 3. Source-Site Manifest

### 3.1 Eligible Sites

The caller names the source files to index. Within each authored
`defworkflow` and `defproc` of those files the manifest indexes:

- provider calls (`ProviderResultExpr`), phased provider calls
  (`RunProviderPhaseExpr`) and agent turns (`AgentExpr`);
- procedure and workflow calls (`ProcedureCallExpr`, `CallExpr`) and run
  references (`RunRefExpr`);
- the composition forms that enclose them: `let*` bodies and bindings, `if`,
  `cond`, `match` and bounded `loop`/`list` forms.

Pure-helper calls (`FunctionCallExpr`) are located but not eligible:
inline normalization removes them from typed bodies and `AuthoredDirectCall`
does not record them, so the manifest finds each through the
`HelperExpansionFrame.call_span` that normalization adds to the inlined
node's expansion stack (`orchestrator/workflow_lisp/syntax.py`) and reports
it with kind `function-call` and exclusion `pure-call-unretained`; its facts
are the call site's. Known gap: an inlined call produced by a macro is
currently dropped without a `macro-generated` record.
Literals, arithmetic and prompt templates are not indexed. Definitions in
files the caller did not name, imported library modules among them, appear
only as `dependencies` of indexed sites.

### 3.2 Site Record

One record per eligible authored expression. Fields marked **derived** come
from the carriers in §2; fields marked **adapter** depend on §7.

| Field | Content | Source |
| --- | --- | --- |
| `site_id` | owner definition canonical name plus `@` start position `path:line:col`. Macro-generated sites are excluded (§3.4) and two authored forms cannot share a start position, so no ordinal is needed | derived |
| `span` | start and end `SourcePosition(path, line, column, offset)` from the frontend `SourceSpan` (`orchestrator/workflow_lisp/spans.py`); closed-open character offsets into LF-normalized snapshot text, as `:source` slices; never byte offsets into the raw file (CRLF and multi-byte UTF-8 misalign them), so a consumer locates forms by re-reading, not by splicing | derived |
| `file_digest` | `SourceReadRecord.revision` of the file the compiler read | derived |
| `owner` | enclosing definition kind and canonical name; `form_path` | derived |
| `kind` | one of `provider-call`, `provider-phased-call`, `agent-turn`, `procedure-call`, `workflow-call`, `function-call`, `run-ref`, `let*`, `if`, `cond`, `match`, `loop`, `list-map`; never a common "callable" | derived |
| `result_type` | `canonical_type_identity` plus the rendered form; a loop-control position reports its `LoopControlTypeRef` and is ineligible | adapter (WCC `type_ref`) |
| `bindings` | names visible at the site with `BindingIdentity` and canonical type, in scope order; a shadowed name shows the innermost identity only. Authored parameter names come first, with a lowering type only when every lowering agrees; loop-state binders come from `WccRecJoin`; a generic definition with a single lowering reports that lowering's concrete types; a loop with several state parameters reports `facts-unavailable` (a join carries one binding identity) | adapter (WCC `binding_identity`, enclosing binders) |
| `dependencies` | resolved prompt, provider, command boundary, imported module and callee canonical names the expression uses; providers are `{extern, binding}` rows with the resolved closed perform binding; from closed `configuration` and perform node fields | derived |
| `effects` | `inferred: "unavailable"` (WCC nodes carry the owner's whole summary, §2) and the owner's authored restriction or `omitted` | owner-level facts derived |
| `executable_sites` | zero or more closed-program site rows `(owner, label path)` whose perform node `@` start equals this span start; zero for pure compositions; one static row per lowering of the owner, so a shared definition called from two workflows keeps one owner and fans out only at runtime through distinct activation paths, while a generic definition specialized per caller yields one row per specialization | adapter (join) |
| `authored_calls` | `AuthoredDirectCall` rows whose `authored_callee_span` lies inside the span | derived |
| `eligibility` | `eligible`, or an exclusion reason (§3.4) | derived |

The manifest is a JSON-serializable mapping keyed by `site_id`, headed by the
build's `build_key`, `program_digest`, target, entry and per-file digests. It
is produced by one module, `orchestrator/workflow_lisp/source_sites.py`,
called in-process with the result of `prepare_closed_program_bundle`. No CLI
flag, published file or REPL command is added; the REPL's four inspection
commands add no JSON interface, and this design does not change that.

### 3.3 Construction Path

1. Compile the candidate exactly as `run` would, through
   `prepare_closed_program_bundle`, with the same entry, source roots, extern
   files and command boundaries. A rejected compile yields no manifest; the
   ordinary diagnostics are the output.
2. Walk the retained typed definitions of the named files for authored
   expression nodes and their spans; record `kind` from the node class.
3. Obtain a normalized WCC body per owner (P-1, §7): callee bodies are the
   builder's retained `CallableRequest.prepared_body` rows from
   `Builder.prepared_by_key`; only the entry is re-elaborated once, without a
   call preparator, with the same type and value environments.
   Index `WccNodeMetadata` by `source_span.start`; attach `type_ref`,
   `scope_id` and `effect_summary` to the authored node with the same start.
   A node with no WCC counterpart reports `result_type: unavailable` and is
   ineligible.
4. Recover binding types by walking the WCC let-chain of the site's
   `scope_id` and resolving each `binding_identity` to its node `type_ref`.
5. Join `executable_sites` by walking the closed tree and pairing each
   perform node's `@` start with the authored span start.
6. Attach `AuthoredDirectCall` rows by span containment.

Step 3 reads what the compiler produced, or reproduces it with the compiler's
own elaboration; it never infers types from strings and never reads another
build's artifact. Measured cost (single-run in-process timings in the P-1 probe report: re-elaborating the entry costs 29% of a warm compile on `plan_review_execute` and 7.5% on `improve_experiment_proposal`; re-elaborating every owner of the latter would cost about 21%).

### 3.4 Exclusions

| Condition | Eligibility |
| --- | --- |
| Expression produced by macro expansion with no exact authored span | excluded: `macro-generated` |
| Expression in a file the caller did not name | not indexed; visible as a dependency |
| Loop-control position (`recur`, `continue`, `break` carriers) | excluded: `loop-control` |
| Owner is a specialization or generated local procedure | excluded: `generated-definition` |
| Pure-helper call | excluded: `pure-call-unretained` (§3.1) |
| `result_type` or `span` unavailable from retained facts | excluded: `facts-unavailable` |

Unknown facts are labelled unavailable, as the REPL does; they are not
guessed.

## 4. Identities The Manifest Reports

| Identity | Owner | Meaning here |
| --- | --- | --- |
| `build_key` | `closed_build_key` in `closed/artifact.py` | the build the manifest describes |
| `program_digest` | `program_digest` in `orchestrator/contracts/closed_program/program.py`, provenance stripped | the checked program; two source texts can share one digest |
| `site_id` | this design | local to one build; never an identity across edits or candidates |
| executable site and runtime identity | `assign_sites` rows; activation path with loop ordinals in `orchestrator/workflow/evaluated/machine.py` | joined through `executable_sites`; execution evidence, not a source identity |

`candidate_id`, lineage and any cross-candidate relation belong to the
[driver](orc_structural_search_driver.md). Source coordinates, matching types
or matching text do not establish that two sites in different builds are the
same thing.

Verified at `90ae778c` (2026-10-18) on `workflows/examples/plan_review_execute.orc`:
a comment-only change leaves `program_digest` unchanged and changes
`build_key`; a `let*` rename and a literal change each change
`program_digest`.

## 5. What This Approach Makes Harder

- Facts come from one in-process build. A consumer that compiles through the
  CLI or in another checkout gets no manifest and must compile again in
  process.
- Pure-helper calls are reported as `function-call` records excluded by
  policy (`pure-call-unretained`); a proposer cannot be pointed at one.
- A shared definition keeps one static site; the manifest reports callers
  and specializations as fan-out and never invents a second owner.
- Definitions the builder never lowers for the selected entry have no WCC
  facts and are excluded; dead definitions are not inspectable sites.
- Every manifest costs one entry re-elaboration on top of the compile.

## 6. Rejected Alternatives

| Alternative | Why not |
| --- | --- |
| Regex or string matching over `.orc` text to find calls and infer types | a second, wrong type system; the REPL and LSP designs reject it for the same reason |
| Reverse-engineering lowered closed-program nodes only | spans are start-only, bindings and scope are gone, inlined calls are invisible; lexical context cannot be reconstructed |
| A second typechecker inside the consumer | duplicates the frontend and drifts from it |
| Publishing a new `compile --emit-source-sites` artifact | every `--emit-*` flag is refused on evaluated builds (`orchestrator/cli/commands/compile.py`); a published file invites use as run authority; stabilize the schema after a consumer exists |
| CLI-first or REPL-command-first design | text output cannot carry the record; the four REPL commands add no JSON interface; an in-process consumer needs objects |
| Retaining every compiler intermediate on the builder | REPL introspection deliberately retains only what its commands need; P-1 is bounded to the WCC body per owner for one build |

## 7. Feasibility Prerequisites

Each item is an unproven capability. The minimal fixture that proves it is the
first deliverable of any selected implementation; failure is a recorded gap.

| Id | Claim | Minimal fixture |
| --- | --- | --- |
| P-1 | per-node WCC metadata is obtainable for every owner of one build at bounded cost: either `Builder` retains the normalized WCC body per owner (a bounded builder change, in tension with REPL introspection's rule against broadly retaining intermediates) or the manifest re-elaborates once per owner via `elaborate_command_scopes` with the build's environments | compile one maintained example both ways; assert identical `WccNodeMetadata` per node; record elaboration time and memory against the compile alone |
| F-a | WCC metadata yields span, type and scope per node and joins to closed-program site rows for both owner kinds; workflows and procedures both lower through `_prepare_command_owner` → `_command_wcc_body`, while `_workflow_wcc_body` serves only `_context_routes` | compile `workflows/examples/plan_review_execute.orc` (workflow owner) and `workflows/examples/improve_experiment_proposal.orc` (it declares a `defproc`); assert every perform node's `@` start matches exactly one `WccNodeMetadata.source_span.start` and one `assign_sites` row |
| F-b | binding types at a site are recoverable from the WCC let-chain | at the `review` site, assert `bindings` lists `draft` with its canonical type |
| F-c | an authored procedure call survives inline normalization as a site | a workflow calling an effect-free procedure that the compiler inlines: assert the call is a `procedure-call` site with `authored_calls` populated although `typed_body` holds the inlined form |
| F-d | the join distinguishes static sites from invocations | a non-generic procedure called from two workflows: assert one static site with one owner, with the two callers visible as distinct runtime activation paths and never as a second owner; a generic procedure specialized for two callers: assert one `executable_sites` row per specialization |
| F-e | shadowing resolves to the innermost identity | nested `let*` rebinding `x`: assert the inner site's `bindings["x"]` identity differs from the outer |

Results: P-1 and F-a passed (`tests/test_workflow_lisp_source_sites_probe.py`):
retained callee bodies and the entry re-elaboration reproduce the compiled
`WccNodeMetadata` node for node and leave the builder and artifact unchanged;
cost as in §3.3. F-b to F-e are covered by
`tests/test_workflow_lisp_source_sites.py`, with F-d as revised: one static
owner for a shared procedure, and one `executable_sites` row per
specialization.

## 8. Boundary Compliance

Against [the program-search boundary invariants](workflow_lisp_program_search_boundaries.md):

| Invariant | This design |
| --- | --- |
| 1 — immutable generations; full pipeline; no eval; child runs | **Amendment required** for the consumer's execution model; this design itself executes nothing and edits nothing |
| 2 — provider output is untrusted data | Satisfied: the manifest is read-only output; proposals are the consumer's data |
| 3 — neutral substrate versus feature | Satisfied: the record carries sites, kinds, types, bindings, dependencies, effects and diagnostics; no selection, score or archive vocabulary |
| 4 — whole-candidate evidence | Not implicated: `executable_sites` is a join for diagnosis, never a score carrier |
| 5 — evidence separation | Not implicated; consumer-owned |
| 6 — honest security boundary | **Amendment required**; the manifest adds no isolation and no execution |
| 7 — typed-operation parity without kind erasure | Satisfied: `kind` is mandatory and distinct per operation; equal `result_type` never implies substitutability across kinds; no runtime callable or closure |
| 8 — role-separated prompt identity | Inherited unchanged: prompts appear as resolved dependencies, never as an ambient hash |

The boundaries document carries a dated
[pending amendment block](workflow_lisp_program_search_boundaries.md#proposed-amendment-2026-10-17)
covering invariant 1 (ordinary registered runs launched by an external
controller and owned by an experiment record), invariant 6 (ordinary
configured agent sessions under experiment hygiene) and the
[typed program gates](workflow_lisp_typed_program_gates.md#boundary-compliance)
rule "generational child runs only" (scoped to candidate execution started
from inside a workflow); the [driver design](orc_structural_search_driver.md)
carries its rationale. Until the owner accepts that amendment, a consumer is
limited to what invariant 6 allows today: text-only/no-tool, mock, replay or
genuinely sandboxed provider calls.

## 9. Verification

Manifest-side behavioral checks, not snapshot tests of rendered text:

- A site inside shadowing `let*` forms resolves to the innermost binding
  identity; a shared or specialized definition does not map to the wrong
  owner (F-d, F-e).
- Every eligible site reports a canonical `result_type` equal to the
  build's own canonical type for that node; for a closed expression (no
  parameters or `let*` names) it also equals the REPL `:type` result for
  the same text, since `:type` without an attached run has no lexical
  values.
- `executable_sites` of a provider call equals the set of `assign_sites`
  rows whose perform node carries that start position; a pure composition
  reports none.
- A macro-generated expression, a pure-helper call and a loop-control
  position are reported with their exclusion reasons, not omitted silently.
- A file the caller did not name contributes no sites and its definitions
  appear only as dependencies.
- P-1's two routes produce identical metadata; the recorded cost is reported
  with the fixture, not asserted in prose.

Run the frontend and closed-program selectors that cover the touched modules
first, then one public `compile`/`run` integration check on a maintained
example; the repository's broad suite follows for any `orchestrator/` change.

## 10. Affected Surfaces And Handoff

- New: `orchestrator/workflow_lisp/source_sites.py` (manifest only), with
  its tests. P-1 needed no `Builder` change; no change to the typechecker,
  REPL, LSP or specs is expected.
- Consumer: the [structural search driver](orc_structural_search_driver.md)
  owns receipts, scope validation, snapshots, `candidate_id`, proposal
  sessions, evaluation, records and selection.
- Routing: the design index, capability matrix and the roadmap list this
  document as proposed; the §7 fixtures pass, but nothing here is admitted
  or copy-safe until the owner records the boundary amendment.
