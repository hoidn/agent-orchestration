# Workflow Lisp REPL Introspection

## Metadata

- **Status:** implemented current introspection contract at admitted evaluated targets 2.35–2.40
- **Kind:** feature
- **Owner:** Workflow Lisp frontend and CLI maintainers
- **Reviewers:** Independent design and implementation reviewers
- **Created / last material update:** 2026-10-12
- **Implementation target:** admitted evaluated REPL targets 2.35–2.40; 2.39 restriction/inference inspection follows the definition-origin contract
- **Related:** [REPL design](workflow_lisp_repl.md), [execution plan](../plans/2026-10-12-workflow-lisp-repl-introspection-plan.md)

## Summary And Scope

Make a loaded REPL module discoverable before running it: list its visible
names, inspect a type or callable contract, read an authored prompt definition,
and ask the frontend for an expression's type without evaluating it. Add four
commands over the compiler context the REPL already retains: `:browse`,
`:info NAME`, `:source NAME`, and `:type EXPR`.

The scope is introspection; execution and evidence are tracked in the linked plan.
Completion/history, multiline input, prompt rendering or editing, interactive
effects, execution changes, and a
general reflection API are excluded. `:bindings` continues to mean captured
lexical values; module declarations are a distinct namespace. This choice
makes future completion and inspecting unloaded libraries require their own
design; it does not provision an extensible command framework for them.

## Context And Authority

[CLI](../../specs/cli.md#workflow-lisp-repl-targets-235-and-236) owns existing
commands, diagnostics and output compatibility. The [capability matrix](../capability_status_matrix.md)
and [design index](README.md) record implemented availability; this accepted
design owns the bounded introspection contract. The [frontend baseline](workflow_lisp_frontend_specification.md)
owns names, imports, types, effects and prompt contracts; the [source-map design](workflow_lisp_source_map.md)
owns provenance, not a complete symbol catalog or historical source archive.
The [language principles](workflow_language_design_principles.md) require views
to follow compiler authority and avoid a second semantic implementation.

Current owners and introspection seams:

| Owner | Existing fact / bounded change |
| --- | --- |
| `cli/commands/repl.py::ReplSession` | Holds one `LoadedModule` and optional captured run; dispatch preserves the raw `:type` remainder, reads name-query symbols and retains shell parsing for load/run. |
| `workflow_lisp/repl_expr.py::LoadedModule` | Holds typed program, entry Stage-3 result, builder, type environment and immutable accepted source snapshots/revisions with loaded/reconstructed origin. |
| `repl_expr.py::typecheck_repl_expression`, `evaluate_repl_expression` | Share reading, elaboration, normalization and typechecking; evaluation continues through its purity, lowering and evaluator guards. |
| `workflows.py::ExpressionCompileContext`, `compiler.py` | Retain function catalog, name resolvers, linked module graph and final entry import scope as transient compiler context. |
| `type_env.py`, procedure/workflow/function catalogs, `prompts.py::PromptCatalog` | Own resolved definitions, aliases, signature/type facts and prompt slots/output. Type environment exposes `resolve_declared_type`, `declaring_module`, `declaring_name` and `retained_type_ref`. |
| `reader.py::SourceReadTrace` | Retains immutable `raw_bytes_by_path` and revision identities; both REPL build paths transfer them into the loaded context. |
| `closed/frontend.py::compile_typed_program_with_result` | Returns the typed program and entry Stage-3 result with transient expression context; the public result shape is unchanged. |
| `authored_symbols.py`, `lsp/navigation.py` | Existing authored-span cross-check and editor projection; their closed kinds omit `defun` and `defprompt`, so they are not a complete REPL catalog. |

The motivating failure is concrete: `Plan` and `revise-plan` are declarations,
so entering either as a value is not a way to discover its fields or template.
`:bindings` cannot supply those facts, even after a successful run.

## Decision And Alternatives

| Alternative | Benefit | Cost / decision |
| --- | --- | --- |
| Improve help and tell users to inspect `.orc` files externally | No compiler changes | Does not explain imported names or inferred expression types in the session. Insufficient. |
| Four compiler-backed inspection commands | Direct discovery, contract, source and type queries | Small transient retention and one shared typechecking seam. Selected. |
| One extensible `:inspect` command or reuse the whole LSP service/index | One command head; possible future editor reuse | Still needs four modes, adds service/framework coupling, and the LSP matrix lacks required definitions. Rejected. |

Four commands serve four distinct questions; no options, aliases, plugins or
mode configuration are introduced. `:info` stays compact while `:source`
explicitly requests potentially large prompt text. `:type` accepts an
expression rather than a declaration name and cannot be folded into name
lookup without inventing precedence between syntax and symbols.

## Public Contract

```text
:browse
:info Plan
:info revise-plan
:source revise-plan
:type (list/length (list "first step" "second step"))
# After attachment:
:bindings
:type revised.steps
```

The comments above explain session state; they are not REPL commands. The
loaded source must still compile using ordinary entry selection and extern
flags. This feature does not load an otherwise unrunnable library by itself.

| Command | Behavior |
| --- | --- |
| `:browse` | Print module name, source snapshot identity, target, selected entry, imports and aliases; then visible names grouped by kind. Coverage is explicitly labelled: named types, functions, procedures, workflows, prompts and externs. |
| `:info NAME` | Print every matching module declaration's kind, accepted name(s), declaring module and source location, followed by its contract as below. No value evaluation or prompt rendering. |
| `:source NAME` | Print a labelled source section for each match: kind, declaring module, path/location and snapshot revision, then the full original declaration form. A `defprompt` includes its authored template. |
| `:type EXPR` | Print two lines using existing frontend renderers: `type: <rendered type>`, then `effects: <rendered inferred effect set>` when complete. At 2.39 unresolved generic calls print `effects: incomplete (<unresolved names>); known <rendered known effect set>`. Read exactly one expression and stop after ordinary typechecking; do not display authored restrictions. |

`:info` contracts are: record fields; union variants and their fields; enum
members; path constraints; primitive type identity; function/procedure/workflow
parameter and return types plus available inferred effects; prompt fills in
declaration order with slot kind, refinement and output role, then output type.
At 2.39, procedure inspection separates the authored restriction (or its
omission) from inferred effects, and labels unresolved generic dependencies
incomplete; `:type` reports expression inference only. The
[CLI contract](../../specs/cli.md#workflow-lisp-repl-targets-235-and-236) owns
the exact text format.
Externs show kind, name and known declared contract, never manifest payload,
provider argv, credentials or the contents of an external prompt file. Unknown
facts are labelled unavailable; they are not inferred from runtime values.

Output uses deterministic plain text: kinds and names sort lexicographically;
declaration fields, variants, parameters and slots keep declaration order.
Aliases of one canonical identity collapse into one row/section, with accepted
spellings listed. The four commands add no JSON interface. Existing expression
and `:result` two-line JSON/type output remains byte-compatible.

### Session State, Names And Effects

| State / input | Required meaning |
| --- | --- |
| No loaded module and no attachment | All four commands fail `repl_module_required`. |
| Loaded module, no run | All four work. `:type` has module/extern context but no lexical values; a run-local name produces ordinary `name_unknown`. |
| Attached run | Inspection uses the compatible loaded/reconstructed module. `:type` additionally receives the same supported lexical type refs as ordinary expressions. |
| `:info revised` where only a lexical value exists | Unknown module name; diagnostic directs value inspection to `:type revised` / `:bindings`. |
| Lexical value shadows a module spelling | `:type` follows ordinary expression resolution. `:info` / `:source` ignore lexical values. |
| One spelling in several compiler namespaces | Show all distinct matches, each explicitly labelled by kind. Never guess precedence or add a namespace-selector syntax. Same-namespace ambiguity retains compiler refusal. |
| Imported/alias-qualified name | Use the compiler's actual accepted spellings and canonical resolution, including qualified spellings available despite an unqualified `:only` restriction. Never infer visibility from `:only` text alone. |
| Private member of another module / unloaded module | Not discoverable through this entry module unless ordinary compiler resolution exposes it. No project-wide search or implicit load. |
| Effectful `:type` expression | Allowed as static analysis: report type and inferred effects without lowering, evaluation, provider dispatch, run creation or attempt directories. |

`:browse` must enumerate the same accepted names that `:info` resolves, not
every entry reachable in a transitive typed-program catalog. Local declarations
are visible regardless of export. Imported definitions follow the entry
module's actual visibility. Source/module-qualified forms are shown as the
compiler accepts them; internal canonical keys are not automatically new
user aliases. Do not implement resolver semantics by splitting names on `/`.

The first release excludes macro, schema, resource and transition catalogs,
operator documentation, applied generic type syntax as `NAME`, and generated
local procedures/specializations. Help and `:browse` state that coverage.
Prelude named types are inspectable and labelled builtin; generic type
applications remain available through ordinary `:type` expressions. Generated
names are not made public. A visible macro-generated definition may expose its
resolved contract, but source is unavailable unless it has one exact original
declaration; an expansion site is never presented as that declaration.

`:type` preserves the ordinary target-dependent syntax and type/effect
diagnostics. It shares supported lexical type recovery, including existing
variant-case proof limitations; it invents no type from a similar descriptor.
Analysis of `(provider-result ...)` does not execute it. Entering the same
effectful expression normally still fails `repl_effect_refused` through all
existing frontend, lowered-body and evaluator safeguards.

### Parsing, Source And Errors

Dispatch splits the command head from its untouched remainder before choosing
a parser. `:type` passes that remainder directly to the existing S-expression
reader; `shlex` must not remove quotes, escapes or spaces inside string values.
`:info` / `:source` require exactly one reader symbol, and `:browse` no argument.
Existing `:load` / `:run` shell-style option parsing is preserved. Multiline
commands and several expressions on one line remain unsupported.

`:source` slices the accepted compiler read snapshot, never a fresh filesystem
read. Decode exact captured bytes as the reader does and normalize CRLF/CR to
LF before applying its closed-open character offsets; spans are neither byte
offsets nor offsets into unnormalized text. Preserve source inside the form,
including escaped template text and internal comments. Surrounding comments
outside its span are not part of the definition. Validate file identity, span
bounds and definition identity before displaying anything.

Every source section says it is the loaded snapshot and shows its revision.
Editing or deleting source after loading cannot change inspection; there is no
disk watcher or implicit reload. A later successful `:load` replaces the entire
context and source snapshot together. Failed loads keep the last good module,
its snapshots and any compatible attachment. Attach digest mismatch continues
to clear attachment under the existing contract.

Recipe-only attachment reconstructs a fresh module snapshot and verifies the
existing program digest. Its source is labelled reconstructed module source,
not the historical text that originally ran: comments/formatting may differ
despite equal program semantics. Historical text recovery and persistent source
archives are outside scope. Inspection commands perform no extra disk reads.

| Condition | Response |
| --- | --- |
| Malformed command arguments | Existing `repl_command_invalid`; `:type` uses ordinary reader errors / `repl_expression_arity`. |
| No matching supported declaration | `repl_name_unknown`, naming the query and supported coverage; no fallback to evaluation. |
| Builtin, extern, synthetic definition, missing snapshot or unprovable exact authored span | `repl_source_unavailable` with the reason; never read a manifest or current disk as fallback. |
| Invalid retained span/identity | `repl_source_unavailable`; fail closed rather than slicing a nearby form. |
| Missing retained compiler facts | Existing `repl_module_context_missing`; never silently return a partial catalog. |

Resolve and validate all `:source` matches before printing them; if any match
has unavailable source, print one refusal naming all unavailable matches and no
partial source. All expected errors use existing stderr handling and preserve
the usable session. Existing startup and EOF/quit exit semantics are unchanged.

## Internal Ownership And Feasibility Prerequisite

```text
ordinary successful compile -> LoadedModule (catalogs + accepted read snapshot)
                                  |-> module inspection projection -> text
entered expression -> shared frontend typecheck -> :type text
                                  `-> existing purity/lowering/evaluation
```

Retain the already-created `SourceReadTrace.raw_bytes_by_path` and revision
vector in `LoadedModule` on both explicit-load and recipe-attachment paths.
Retain the existing linked module graph and the final entry import scope on
`ExpressionCompileContext` through optional transient fields (`compare=False`,
`repr=False`, default `None`). The graph supplies original parsed source without
retaining a cyclic linked compile result; the final scope preserves imports
after compiler export/expansion processing. Do not rebuild that scope from
pre-expansion graph exports. Existing catalogs, resolvers and the compiler's
`build_import_scope` result remain authority. Snapshots, graph and scope are
never serialized, digested or installed in run authority.

Use one small `workflow_lisp/repl_inspect.py` projection for browse/name/source
queries, consumed by CLI dispatch. It derives rows from existing facts rather
than maintaining a symbol registry. Use type environment ownership APIs and
catalog declarations for facts/spans; when a type such as an enum has no
definition on its resolved ref, cross-check its compiler-owned module/name
against the retained original module syntax. Do not reparse current files,
scan text with regexes, add operator semantics or import the LSP service.
The LSP index and persisted source map are useful precedents, not fallbacks.

Extract one frontend-only function in `repl_expr.py`, accepting optional
capture and returning the typed expression plus the existing lowering inputs.
`:type` consumes its type/effect facts; `evaluate_repl_expression` consumes the
same result and retains its current purity/lowering/evaluation tail. Do not
copy the elaboration/typechecking pipeline or make type inspection call the
evaluator and discard its result. No runtime capture change is required.

Before selecting the exact retention patch, a bounded executable feasibility
check must demonstrate: local/imported `Plan` and an enum; aliases, canonical
and `:only` spellings; unused function and prompt definitions; whole-form source
for each from captured normalized text; and effectful typechecking stopping
before lowering. Use real compiler products with no providers or run writes.
The check must establish that the graph/canonical catalogs suffice and expose
any missing ownership fact explicitly. Reading code alone is not that proof.

Stop and revise if correctness needs an independent visibility resolver,
invented spans, an LSP process, a new persisted artifact, or broadly retaining
every compiler intermediate. Missing provenance produces a deliberate source
refusal, but cannot excuse missing directly authored supported declarations
from the successfully loaded source graph.
This prerequisite blocks implementation acceptance; the linked plan owns its
execution and evidence, not this durable contract.

## Compatibility, Cost And Security

No workflow syntax, run artifact, memo/header/schema, build digest, target
selection, dependency or public compile result tuple changes. Transient fields
remain optional for non-REPL callers. Both new inspection and existing pure
queries leave run evidence byte-identical; explicit `:run` and normal `:load`
retain their existing write contracts. Source text adds session memory bounded
by the loaded graph's bytes; replacement releases the previous snapshot.

Source inspection displays local authored text to the terminal, including any
secrets an author put directly in it. It adds no network or provider authority,
and does not read prompt extern payloads, configuration files or arbitrary paths.
`:browse` / `:info` avoid dumping templates by default. There is no rollout,
backfill or migration; existing commands remain usable without the new ones.

## Verification And Declarative Integration Scenarios

| Public scenario | Required observation and boundary |
| --- | --- |
| Load `plan_review_execute.orc` with its ordinary provider extern manifest, without running; issue `:browse`, `:info Plan`, `:info revise-plan`, `:source revise-plan` | See module identity, `Plan.steps : List[String]`, prompt fills/output and whole authored template; no run root, attempts or provider invocation. Real public CLI/compiler. |
| Load a small imported fixture with aliases, `:only`, private names, an enum, unused function/prompt and a shared spelling across namespaces | Catalog and direct queries agree with real compiler acceptance; aliases deduplicate; qualified visibility is preserved; namespaces are labelled; private/unloaded names refuse. |
| Query `:type` with a quoted multiword/escaped string, pure module call, an invalid expression, and a valid effectful call | Ordinary type/effect results or frontend diagnostics; no lowering/evaluator/provider invocation and no builder or artifact change. Real frontend, with boundary spies only as supplemental evidence. |
| Attach a real completed or stopped run; query a lexical value and a shadowed name | `:type` follows captured lexical typing; `:info` stays module-scoped; existing expression, `:bindings`, `:result` and effect-refusal behavior stays compatible. Hash authority/memo/views/attempt evidence before and after. |
| After loading Unicode and CRLF source, change/delete the file, query source, then attempt a broken reload | Exact normalized loaded form remains available and correctly labelled; failed load preserves prior source/context. Successful reload replaces both together. |
| Attach by recipe to a semantically matching source with changed comments; separately try a changed program | Source is labelled reconstructed, without historical claims; changed program retains `resume_program_changed` and detached-state behavior. |
| Query builtin, extern, generated/no-span and malformed/unknown names | Explicit supported contract or refusal; no current-file/manifest fallback, partial source dump, state mutation or session termination. |

Use `tests/test_workflow_evaluated_repl_introspection.py` for public subprocess
coverage, `tests/test_workflow_evaluated_repl.py` for existing behavior and the
maintained execution smoke, and small fixture-created modules for
source/namespace edge cases. Test prompt
metadata, template boundaries and fixture-controlled markers, never literal
production prompt wording. Collect changed test modules before execution.
Run narrow REPL/build regressions, then required affected suites with
`pytest -q -n 16 --dist=worksteal` in tmux; use the repo's broader campaign when
shared compiler retention changes warrant it. Include one public orchestrator
smoke with a disposable workspace and deterministic provider stand-in followed
by attached inspection; this proves integration, not live-provider quality.

Acceptance requires these public scenarios, unchanged execution/build evidence,
the feasibility prerequisite, and independent review of the actual diff and
compiler boundaries. No completion claim rests solely on private helper tests.

## Affected Surfaces And Handoff

| Surface | Implementation / consumer obligation |
| --- | --- |
| `orchestrator/cli/commands/repl.py` | Retain traces in both load paths, dispatch/help/parsing, errors and atomic session replacement. |
| `orchestrator/workflow_lisp/repl_expr.py` | Loaded snapshots and shared typecheck prefix; preserve the evaluation caller. |
| `orchestrator/workflow_lisp/repl_inspect.py` (new) | Bounded compiler-derived projection and source slicing; no independent registry. |
| `orchestrator/workflow_lisp/{compiler,workflows}.py` | Retain existing graph and final import scope in optional expression context; preserve compile callers. |
| `orchestrator/workflow_lisp/closed/{frontend,artifact}.py` | Existing transient result consumers: verify tuple/artifact/digest compatibility; no planned persistence edits. |
| `orchestrator/workflow_lisp/{reader,type_env,modules,prompts,authored_symbols}.py`, `orchestrator/lsp/navigation.py` | Reuse/inspect ownership contracts; no planned LSP matrix or language-surface change. Any shared helper edit requires its direct consumer regressions. |
| `tests/test_workflow_evaluated_repl_introspection.py`, `tests/test_workflow_evaluated_repl.py`, `tests/test_workflow_lisp_repl_introspection.py`, `tests/test_workflow_lisp_repl_type_query.py`, `tests/test_workflow_lisp_build_artifacts.py`, `tests/test_workflow_lisp_source_read_trace.py` | Public new behavior, focused catalog/type boundaries, maintained execution smoke, existing build outputs and snapshot compatibility; fixture-local source additions only. |
| `specs/cli.md`, `docs/lisp_workflow_drafting_guide.md`, `docs/design/workflow_lisp_repl.md` | Add verified commands, namespaces, static effects and source-snapshot limits at implementation time. |
| `docs/index.md`, `docs/design/README.md`, `docs/capability_status_matrix.md` | Route the accepted design and verified availability separately from execution evidence in the plan. |

No workflow/prompt production edits, CLI registration changes, package exports,
configuration keys or installed dependencies are needed. The [bounded plan](../plans/2026-10-12-workflow-lisp-repl-introspection-plan.md)
owns task ordering, feasibility evidence and verification records. Its first
step resolves the retention proof; implementation and independent review then
follow the repository's subagent policy.
