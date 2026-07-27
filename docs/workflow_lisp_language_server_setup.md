# Workflow Lisp Language Server Setup

Status: implemented optional editor tooling

The Workflow Lisp language server provides compiler-owned diagnostics and
closed navigation for saved `.orc` files. It is a read-only stdio server: it
does not execute workflows, create run state, or write build artifacts into the
workspace.

## Install And Launch

Install the optional dependency set from this checkout:

```bash
python -m pip install -e '.[lsp]'
```

Then configure an LSP client to launch:

```bash
python -m orchestrator.lsp
```

The default install remains free of the LSP transport dependency. There is no
bundled editor extension or syntax-highlighting grammar; adapt the command and
initialization fields below to the generic-LSP configuration shape used by
your editor.

## Workspace And Initialization

Each server process owns exactly one canonical workspace root. The client's
`rootUri` and `workspaceFolders`, after canonicalization and deduplication,
must identify exactly one local directory. Opening an entry outside that root
is rejected. The compiler-owned builtin standard-library root is the only
additional source location the server admits automatically; it is not a
second workspace root and is not client-configurable.

The optional `initializationOptions` object accepts only these fields:

| Field | Value | Purpose |
| --- | --- | --- |
| `source_roots` | ordered list of paths contained by the workspace | The same explicit caller roots that an equivalent CLI compile would receive. The workspace root is not added implicitly. |
| `entry_workflow` | non-empty string or `null` | Select an exported workflow; leave `null` for a library-only Stage-3 compile. |
| `provider_externs_path` | path or `null` | Production provider-extern bundle. |
| `prompt_externs_path` | path or `null` | Production prompt-extern bundle. |
| `command_boundaries_path` | path or `null` | Production command-boundary bundle. |
| `imported_workflow_bundles_path` | path or `null` | Production imported-workflow manifest, including its recursive source and configuration closure. |

Relative paths resolve from the canonical workspace root. A client
configuration is conceptually:

```json
{
  "command": ["python", "-m", "orchestrator.lsp"],
  "workspaceRoot": "/absolute/path/to/workspace",
  "initializationOptions": {
    "source_roots": ["workflows"],
    "entry_workflow": null
  }
}
```

`command` and `workspaceRoot` are illustrative client-side keys; the protocol
values sent to the server are the launch command, one local-file root URI, and
the `initializationOptions` object. Do not add lint, lowering, validation, or
completion-type options. V1 fixes validation to the production shared-callable
policy and lint/lowering to the unchanged production defaults; unsupported
options fail initialization.

## Editing Model

The server performs one serialized, full Stage-3 compile on a clean open and
after a clean save. "Clean" means the editor text is exactly equal to the
strictly decoded bytes currently on disk. An unsaved `didChange` marks the
document dirty and does not compile an in-memory overlay. Save the file to disk
before expecting refreshed diagnostics or navigation.

The implemented v1 surface is:

- compiler diagnostics on clean open/save, usually one blocking diagnostic
  because the production reader and typechecker remain fail-fast;
- reverse invalidation of clean importers when a saved, open dependency
  changed on disk, even when the client sends no watched-file notification;
- intentional invalid-params initialization responses for structured compiler
  failures, carrying ordered diagnostic code/path rows without synthesizing a
  document diagnostic;
- visible ordered compiler notes and structured macro/helper expansion labels
  without changing diagnostic identity or aggregation;
- go-to-definition only when the cursor is inside an exact
  compiler-provenanced direct procedure or workflow call head, including
  visible imported and standard-library calls;
- document symbols for directly authored `defmodule`, `defproc`,
  `defworkflow`, `defenum`, `defpath`, `defrecord`, `defunion`, `defschema`,
  `defresource`, and `deftransition` definitions, with full-form ranges and
  exact name-token selection ranges; and
- deterministic, namespace-preserving completion for compiler-visible
  local/imported procedure and workflow names plus registered form heads.
  Procedure/workflow rows remain distinct even at the same label and show
  compiler-rendered parameter/return details; procedure details also show
  declared effects.

Navigation is deliberately closed. It returns null/no items for dirty,
compile-pending, dependency-invalidated, language-failed, server-failed,
configuration-stale, superseded, closed, or unassociated documents. It also
returns null for generated or ambiguous calls, arguments outside the exact
callee span, and unsupported definition kinds. Completion uses visibility and
registry membership only; it does not impose or infer a nominal type taxonomy.
Generated, expanded, specialized, or span-ambiguous definitions do not become
best-effort symbols.

## Freshness And Restart Rules

Every accepted result is bound to exact raw-byte SHA-256 revisions for the
complete compiler-read `.orc` closure, including builtin standard-library
files. Source changes invalidate affected open entries and schedule serialized
recompilation. File watchers improve responsiveness, but every navigation
request rechecks the bound source and configuration state even when no watcher
notification arrived. A save performs one disk probe and selects either the
changed-revision observer or the unchanged local-save transition, never both.
The pure-projection export helper likewise keys untraced reuse by canonical
path and exact content; traced compiler reads continue to bypass that cache.

Initialization configuration is immutable for the server lifetime. Changes to
configured extern or imported-workflow inputs, their recursively imported
source/configuration closure, the compiler-owned builtin-root identity, or the
workspace-root set latch a restart-required state. Reverting the bytes does not
unlatch it; restart the language server.

## Current Limits

The implemented v1/L0/L1 surface intentionally has no unsaved-buffer analysis,
recovery-safe incomplete completion,
multi-diagnostic recovery,
hover/type sidecar, compile cache or incrementality, rename, formatting, code
actions, semantic tokens, multi-root workspace support, or non-default compile
policy. These are not partial server features. L2's design-amendment/review
gate is next; no L2 design is accepted. The frontend prerequisites P1–P5 and
any other successor work remain separately designed and scheduled.

For the owning contract and rationale, see
[Workflow Lisp Language Server](design/workflow_lisp_language_server.md) and
frontend specification
[§76.1 Editor And Lint Tooling Compatibility](design/workflow_lisp_frontend_specification.md#761-editor-and-lint-tooling-compatibility).
