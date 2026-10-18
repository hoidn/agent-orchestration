# Workflow Lisp Source-Site Inspection

## Metadata

- **Status:** proposed (2026-10-17); unimplemented; not copy-safe
- **Kind:** feature (frontend component contract)
- **Owner:** Workflow Lisp frontend and CLI maintainers
- **Reviewers:** independent design and implementation reviewers
- **Created / last material update:** 2026-10-17
- **Implementation target:** admitted evaluated modules at targets 2.35–2.39; no new target, header field, artifact, memo field or spec change
- **Related:** [REPL introspection](workflow_lisp_repl_introspection.md) (the retained compiler context this builds on);
  [language server](workflow_lisp_language_server.md) (prerequisite P3 and the navigation precedents);
  [frontend specification](workflow_lisp_frontend_specification.md) (names, types, effects, spans);
  [program-search boundaries §3 and §7](workflow_lisp_program_search_boundaries.md) (neutral substrate; kinds are not erased);
  consumer: [structural-search experiment](orc_structural_search_experiment.md)

## Summary And Scope

A read-only projection of a successfully compiled module that lists its
editable source expressions with the facts the compiler already holds about
each (span, enclosing definition, operation kind, inferred type, visible
bindings, resolved dependencies, inferred effects and restrictions, executable
sites, eligibility); a way to typecheck a proposed replacement for one such
expression in that expression's lexical environment without lowering or
running; and an edit transaction that applies one replacement to the accepted
source snapshot and validates that nothing else changed before the ordinary
full compile. The consumer is any tool that proposes a replacement for one
expression and needs to know what it may reference and what it must preserve.

Out of scope: a second typechecker, a printer for reader trees or expression
nodes, a persisted artifact or schema, a new CLI command beyond what the REPL
already exposes, any notion of a proposal's worth, and anything that changes
compilation or execution.

## Context And Authority

| Owner | Existing fact this design uses |
| --- | --- |
| `workflow_lisp/repl_expr.py::LoadedModule` | Retains the typed program, entry Stage-3 result, builder, type environment and the immutable accepted source snapshots (`source_snapshots`, `source_revisions`, `source_origin`) |
| `workflow_lisp/closed/frontend.py::TypedProgram` | `workflows`, `procedures`, `workflow_type_env(name)`, `procedure_type_env(procedure)`, `module_type_envs`, `externs`, `command_boundaries`, `source_file_digests`, `imported_programs` |
| `workflow_lisp/typecheck_context.py::TypedExpr` | `expr`, `type_ref`, `span`, `form_path`, `effect_summary`, `binding_environment`. The environment is attached only at the root of each typechecked body (`typecheck_dispatch.py`, the `replace(... binding_environment=dict(active_binding_env))` after `_typecheck`; `procedure_typecheck.py::_typecheck_owner`); intermediate `TypedExpr`s are discarded during dispatch |
| `workflow_lisp/repl_expr.py::typecheck_repl_expression` | Typechecks an entered expression in module context and reports type and inferred effects without lowering; lexical bindings are available only after a run is attached |
| `workflow_lisp/repl_inspect.py` | `visible_declarations`, `inspect_name`, `source_name`: declaration rows with kinds, spans, contracts and inferred effects; whole-form source sliced from the accepted snapshot with CRLF normalization; refusals `repl_name_unknown`, `repl_source_unavailable`, `repl_module_context_missing` |
| `workflow_lisp/reader.py` | `read_sexpr_text` returns spanned reader trees (per atom and list, start and end); `SourceReadTrace.raw_bytes_by_path` and `revision_vector`; comments are skipped by `_Reader._skip_ignored` and never retained |
| `workflow_lisp/expression_traversal.py` | `walk_expr`, `map_expr`, `free_expr_names(expr, bound=..., include_callees=...)` over frontend `ExprNode`s |
| `contracts/closed_program/program.py` | `program_digest` strips `@` provenance (`strip_provenance`); sites are `(owner, "#n")` rows (`_sites_from_nodes`); `perform` nodes carry `class`, `contract`, `policy`; provenance `@` is `{"span": "<path>:<line>:<col>", "form": [...]}`, a start position and form path, plus `source_map_subject` on some `perform` nodes |
| `closed/artifact.py::closed_build_key` | `build_key` hashes `source_file_digests`; `manifest.json` carries `schema_version`, `build_key`, `program_digest`, `representation`, `target`, `entry_workflow`, `sites`, `source_path`, `source_roots`, `artifact_paths` and no source digests |
| `cli/commands/compile.py` | `--diagnostics-json`: accepted `{"build_key","program_digest","status":"accepted"}`; rejected `workflow_lisp_compile_diagnostics.v1` |
| `lsp/navigation.py`, `authored_symbols.py` | Definition edges for direct procedure/workflow call heads and authored spans for a closed kind set; precedents, not a manifest |

Verified facts (2026-10-17, main `90ae778c`): adding a comment line leaves
`program_digest` unchanged and changes `build_key`; renaming a `let*` binding
changes `program_digest` (the closed program keeps `let name: t`); a literal
change changes `program_digest`. The REPL creates no run for `:browse`,
`:info` or `:type`.

## Problem

A consumer that wants to replace one expression must know its span, its
enclosing definition, what the expression's result type is, which names are in
scope at that point and with what types, which externs and prompts it resolves,
what effects it has and what its context permits, and which executable sites it
reaches. The checked frontend computes every one of these facts during a
compile, but retains the lexical environment only at definition roots, and the
published closed artifact carries start positions and form paths, not extents
or environments. Reading the artifact or re-inferring from text would be a
second typechecker, which the language principles and the LSP contract forbid.
Applying an edit has no component either: there is no printer, so the only
comment-preserving path is the REPL's own, slicing and splicing the accepted
snapshot by span.

## Goals And Non-Goals

Goals: every manifest field comes from a retained compiler fact or a bounded
walk of a retained typed body; eligibility is explicit with a reason for every
exclusion; a replacement is typechecked in its site's environment before any
compile; a transaction either produces a new source snapshot whose only
structural difference from the parent is within the selected span and declared
helper spans, or refuses with the first difference it found; the ordinary full
compile is the only certification.

Non-goals: any optimizer concept (the worth of a proposal, choosing among proposals, keeping a store of them or of their history);
a second typechecker or any type inference from strings or lowered nodes; a
persisted manifest artifact or schema; a printer or reformatter; editing
imports, type or protocol declarations, prompt bodies (unless the consumer's
scope says so) or the entry signature; interior environments through
re-running typecheck per site in the MVP.

## Decision

Derive the manifest from `LoadedModule`'s retained facts the way
`repl_inspect.py` derives declaration rows: no registry, no reparse, no regex,
no LSP process. For a site's lexical environment, accept for the MVP the
REPL-style fallback: start from the definition's root `binding_environment`
and its type environment, and walk the retained typed body's `let*`/binding
chain to the site to collect the bindings in scope. Typecheck a replacement
with the existing `typecheck_repl_expression` path given that environment and
an expected type equal to the site's inferred type. Apply an edit as a span
splice on the raw snapshot, re-read, and compare reader trees. Certify with the
ordinary compiler.

Alternatives: a span→type and span→environment sidecar collected during
typecheck dispatch (LSP P3) gives interior facts directly and is the
feasibility prerequisite's first option; retained only if the probe shows the
walk is insufficient or P3 is cheap. Reading the closed artifact alone was
rejected: it cannot reconstruct lexical context. A printer was rejected: not
needed for a splice-and-re-read transaction.

## Public Contract

### Source-Site Manifest

A read-only projection, computed on demand from one `LoadedModule`, never
serialized into run or build authority. Rows for provider calls, named
workflow/procedure calls, and enclosing `let*`/conditional compositions;
literals and arithmetic are not indexed.

| Field | Source | Limit |
| --- | --- | --- |
| Snapshot identity: file path, sha256 of the accepted snapshot bytes, revision | `LoadedModule.source_snapshots`, `source_revisions`, `source_origin` | A reconstructed snapshot is labelled as such; comments and formatting may differ from what ran |
| Site locator: span (start and end), form path | `TypedExpr.span`, `form_path` of the typed body; `ExprNode.span` of the walked node | Spans are character offsets into CRLF-normalized text, per the REPL's slicing rule |
| Enclosing definition: kind, name, module, target | `TypedProgram.workflows` / `procedures`; `repl_inspect.visible_declarations` | Generated local definitions and specializations are excluded, as the REPL catalog excludes them |
| Operation kind: provider call, procedure call, workflow call, composition | The `ExprNode` class of the walked node | Kinds are never interchangeable (boundaries §7) |
| Inferred result type and canonical type identity | `TypedExpr.type_ref` at the root; the walked node's type in the MVP comes from re-typechecking the node in the site environment (the fallback) or from the P3 sidecar | Polymorphic schemes and contextual expected types beyond equality are deferred |
| Visible lexical bindings and their types | Root `binding_environment` plus the `let*` chain walk; `workflow_type_env` / `procedure_type_env` for declared names | Branch-local variant proofs and loop-state carriage follow the frontend's rules; a binding introduced by an unsupported form makes the site ineligible |
| Resolved prompt / provider / module dependencies | `TypedProgram.externs`, `module_externs`, prompt catalog, import scope | Unused imports are not dependencies (boundaries §8) |
| Inferred effects and applicable restrictions | `TypedExpr.effect_summary`; at 2.39 the definition's authored restriction, as `:info` separates them | Effects describe operation kinds, not counts or cost |
| Executable sites | `closed_program.json` `sites` rows `(owner, "#n")` joined by owner and `@` form path; `source_map_subject` where present | See the join limits below |
| Eligibility and exclusion reason | Computed | Every excluded site carries one reason from the table below |

### Eligibility And Exclusion Reasons

| Reason | When |
| --- | --- |
| `generated_definition` | Specializations, WCC-generated owners, macro-expanded or hygiene-renamed forms with no authored provenance |
| `expansion_site` | The node lies inside a macro expansion; only the authored call site is addressable |
| `entry_signature` | The exported entry's parameters and return type |
| `declaration` | Imports, type/union/record declarations, prompt bodies, extern declarations |
| `unsupported_binding_form` | A binding in scope was introduced by a form the walk does not model |
| `source_unavailable` | No exact authored span can be proved (the REPL's `repl_source_unavailable` conditions) |
| `imported_module` | The expression lives in an imported module; editing it affects every importer and is outside one module's transaction |

### Join To Closed-Program Sites

A source site joins to executable sites by owner (`workflow:` or `procedure:`
name) and the `@` form path, which is a start position and form path, not an
extent. The join is one-to-many: lowering, imports and specialization create
several executable instances of one authored expression, and an edit in a
shared definition reaches every caller. The join is not available for compiler
temporaries without authored provenance. A consumer must rebuild and evaluate
the whole program; it never reads a site's runtime identity as a persistent
identity across edits.

### Replacement Typecheck In Site Context

Input: a site row and one replacement expression as text. The component reads
the text with the ordinary reader, elaborates and typechecks it through the
`typecheck_repl_expression` path with the site's lexical environment and the
site's inferred type as the expected type, and stops before lowering. Output:
the replacement's type and inferred effects, or the ordinary frontend
diagnostic. This is a preflight; the full compile of the whole module
remains mandatory and is the only acceptance.

### Edit Transaction And Scope Validation

```text
precondition: sha256(parent snapshot bytes) == expected digest
splice:       replace bytes of the selected span (and declared helper spans or
              a declared helper insertion point) in the raw snapshot
re-read:      read_sexpr_text on the new bytes -> reader tree
structural    compare original and edited reader trees modulo spans; every
diff:         difference must lie within the selected span or a declared helper
              span, otherwise refuse with the first out-of-scope difference
compile:      ordinary full compile of the edited module (--diagnostics-json)
```

Scope rules: the selected expression may be replaced; declared fresh helpers
may be added; prompt bodies and provider/model options change only when the
consumer's declared scope allows; imports, type/protocol declarations and the
entry signature are frozen; a helper receives explicit capture parameters and
must not rebind an existing name (checked by `free_expr_names` on the
replacement against the site's visible bindings). The parent snapshot is never
modified; the edited module is a new snapshot with its own digest.

Digest facts the consumer relies on: a comment-only change leaves
`program_digest` unchanged and changes `build_key`; a rename or a literal change
changes `program_digest`. So `program_digest` proves semantic identity for
formatting changes and detects renames; it does not distinguish a rename from a
structural change, which is a consumer concern. No printer exists and none is
needed: the transaction never re-serializes a tree.

## Feasibility Prerequisite

Before an implementation plan is accepted, a bounded executable probe on real
compiler products, with no providers and no run writes, must show:

1. For a module with a `let*` chain inside a workflow and inside a procedure,
   the walk from the root `binding_environment` reaches a provider-call site
   and reports the same bindings and types as the frontend assigns (checked
   against a deliberately shadowed name and against a branch-local variant
   proof).
2. A replacement that references an out-of-scope name is refused by the
   site-context typecheck with `name_unknown`; a type-incompatible replacement
   is refused with the ordinary diagnostic; a compatible one reports the site's
   type and its inferred effects.
3. A span splice followed by re-read produces a reader tree whose only
   difference from the parent is the spliced span; a second edit elsewhere in
   the file is refused by the structural diff.
4. The join from the edited site to `sites` rows is stable across a
   comment-only change and changes as expected after the edit.

If the walk cannot reproduce interior environments for admitted forms, the
alternative is the P3 sidecar (optional collection of per-subexpression type
and environment during typecheck dispatch, keyed by span and form path), which
then becomes this design's prerequisite exactly as P3 is the LSP hover's. Stop
and revise if correctness needs an independent visibility resolver, invented
spans, a persisted artifact, a printer, or retaining every compiler
intermediate.

## Relation To The REPL And The Language Server

The REPL already exposes the declaration-level view (`:browse`, `:info`,
`:source`, `:type`) and the slicing rule; this component extends the same
retained context one level down, to expressions, and adds the transaction. It
adds no REPL command in the MVP; a consumer drives it as a library over
`LoadedModule`. The language server's navigation index and authored symbols
are precedents for span-keyed projections; neither is reused as a dependency,
and the server's hover (L6a) remains limited to declaration names until P3
exists. If P3 is implemented for this component, the LSP hover may consume it;
that is a separate selection.

## Compatibility, Cost And Security

No syntax, artifact, memo, header, schema, digest, target or public compile
result changes. The projection and the typecheck leave run evidence
byte-identical; the transaction writes only a new source file in the consumer's
own root. Memory is bounded by the loaded graph's bytes and one typed-body walk
per site. The manifest shows local authored text, including any secret an
author wrote into it; it reads no prompt extern payloads, configuration files or
arbitrary paths, and adds no provider or network authority.

## Verification And Declarative Integration Scenarios

| Scenario | Expected |
| --- | --- |
| Shadowed binding | The manifest resolves the innermost binding at the site; a replacement referencing the outer one by the same name typechecks against the inner type |
| Shared definition | A site in a procedure called from two workflows lists both executable site owners; the manifest does not silently map it to one |
| Incompatible replacement | Refused at site-context typecheck and, if forced through, at full compile with `workflow_lisp_compile_diagnostics.v1`; never reaches execution |
| Two valid replacements | Both compile; their `program_digest`s differ |
| Out-of-scope edit | A change outside the selected span in the same file is refused by the structural diff with its location |
| Frozen boundary | A transaction that alters the entry signature or an import is refused |
| Helper capture | A helper that would capture a site binding without a parameter is refused by the capture check |
| Comment-only edit | `program_digest` unchanged, `build_key` changed, structural diff empty |

Narrow selectors for the new module first, then the broad suite.

## Open Questions

| Question | Impact | May implementation proceed? |
| --- | --- | --- |
| Walk versus P3 sidecar for interior environments | Shape of the environment code | No; the probe decides |
| Whether `form_path` plus owner suffices to join every authored provider call to its `sites` rows under specialization | Join completeness | Yes, with unjoined sites marked `source_unavailable` |
| Whether the consumer's declared scope may include prompt bodies by default | Scope rule default | Yes; default frozen |
