# Workflow Lisp REPL Introspection

## Metadata

- **Status:** accepted bounded contract for typed 2.35/2.36 and qualified native 3.0.
- **Kind:** additive REPL design; no new execution or persistence profile.
- **Authorities:** [CLI](../../specs/cli.md#workflow-lisp-repl),
  [versioning](../../specs/versioning.md), [REPL baseline](workflow_lisp_repl.md),
  [native architecture](workflow_lisp_dynamic_core_proposal.md#9-complete-consumer-production-candidate).
- **Evidence owners:** `tests/test_workflow_lisp_repl_introspection.py`,
  `tests/test_workflow_lisp_repl_type_query.py`,
  `tests/test_workflow_evaluated_repl_introspection.py`,
  `tests/test_workflow_dynamic_repl_introspection.py`.

## Decision and scope

Project declarations from the loaded module's actual compiler context and source
snapshot; project captured values through the existing checked attachment.
Reuse the ordinary reader/resolvers/typechecker or native metadata as applicable.
Inspection never evaluates an expression or launches a command/provider. Entered
pure expressions remain a separate existing operation; explicit `:run` retains
ordinary public execution authority.

This keeps profile-specific adapters and their retained compiler dependency.
Future compiler retirement requires a deliberate metadata migration; the new
shared checked-artifact owners do not make the complete CLI or runtime
frontend-free. No native lineage wrappers, equality-based provenance, evaluator
replacement, recovery, hot reload or static whole-program inference is added.

## Command contract by profile

| Command | Prerequisite | Typed 2.35/2.36 | Native 3.0 |
| --- | --- | --- | --- |
| `:browse` | Loaded module | Visible declarations, aliases and loaded snapshot identity | Actual visible lowerer declarations and namespaces; inference limits stated |
| `:info NAME` | Loaded module | Matching declaration contracts, types and available effect summaries | `define` parameter names with unavailable parameter/return/effect inference; explicit workflow/prompt/type schemas |
| `:source NAME` | Loaded module | Checked authored declaration from immutable loaded snapshot | Same source check using real native declaration spans |
| `:type EXPR` | Loaded module; optional attachment | Ordinary static type/effect analysis, including effectful expressions, without evaluation | Literals, visible function names and captured names only; kinds with explicit basis; compound expressions refuse |
| `:where [NAME]` | Attached run | Checked committed-result locator for performed binding or completed entry | No retained value-to-file provenance; refuses rather than guessing |
| `:run [run flags]` | Loaded module | Ordinary public run followed by attachment | Ordinary fresh-only public run; can repeat previous external work |

Existing `:load`, `:attach`, `:bindings`, `:result`, `:help`, `:quit` and pure
expression behavior remain governed by the [baseline](workflow_lisp_repl.md).
Declaration commands and module-only type queries need no run. Captured lexical
bindings shadow module names in type queries; a name absent from that environment
is not recovered by comparing values or walking report output.

## Declaration identity and source snapshots

Typed projections use the retained compilation context. Native projections use
the real lowerer graph, scopes, type environments, members and prompts. Resolve
imports/aliases, qualified names and visibility through their ordinary namespace
owners. A source graph can contain old executable declarations that are not
admissible native imports; their presence does not make them visible native
callables. Preserve ambiguity diagnostics; `:info` can display matches from
separate namespaces. Unknown declaration names report `repl_name_unknown`.

Extern projections expose only kind and available contract metadata, not manifest
secrets, prompt text or command argv. Unavailable contracts/inference are labeled
unavailable. Builtins, externs, compiled-only or generated declarations without
an exact authored form cannot acquire source text through display rendering.

`:source` reads only retained bytes from the successful load. Check the snapshot
hash and form span/name against the declaration, normalizing CRLF/CR for span
positions. Native `define` names occur in the declaration's parameter-list head.
A later disk edit/deletion changes neither inspection text nor snapshot identity;
there is no filesystem fallback. Missing/mismatched bytes, expanded or unavailable
forms refuse `repl_source_unavailable`. Loading the module again is an explicit
new compilation, not automatic source refresh.

## Type analysis and observed kinds

Typed `:type` uses ordinary analysis and prints a type plus inferred transitive
effects. It can analyze an effectful call or division by zero without evaluating
it; this does not grant permission to execute either expression interactively.
Typed expression evaluation still rejects effects under the baseline guards.

Native has no ordinary static type/effect inference for internal functions.
A literal reports its literal kind; a visible declared function reports `Function`
with unavailable return/effect inference. A captured value reports **observed
runtime kind**, including `Function` for a closure. Explicit workflow/prompt/type
schemas belong to declarations shown by `:info`; observed kinds are not boundary
schemas or proof of future evaluation. A native compound expression, including
an arithmetic or effectful call, refuses `repl_type_unavailable` without evaluating
any operands. Unknown value/function names use `name_unknown`.

## Result-file lookup and read-only guarantees

Typed captured values may carry a checked `committed_result_path`. `:where NAME`
returns that result's physical path beneath the attached authority root, checking
the retained root prefix and rejecting absolute/traversing/malformed locators.
`:where` without a name uses the completed entry value's retained locator.
It locates a result file, not a declaration's source location. Pure/computed
values without that locator report `repl_no_result_file`; coincidentally equal
values do not supply provenance.

Native physical result files are used during checked reconstruction, but the
captured plain values retain no file provenance. Every otherwise valid native
`:where` therefore reports `repl_no_result_file`. Both profiles use `name_unknown`
for an unknown captured name and `repl_no_result` for an absent completed entry
result; no native result-file claim is inferred from equality or effect order.

All inspection commands preserve run-tree bytes and perform zero external calls.
Read-only does not mean source-independent: loaded declarations/source/type
queries need retained compiler context, and native attachment requires a matching
loaded module. Native `:run` still writes a new run with no recovery/reuse.
