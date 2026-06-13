# Workflow Lisp Macro Surface Contract

Status: accepted current-surface contract  
Scope: bounded `defmacro` behavior implemented in the current checkout  
Relationship to other docs: this narrows the macro surface from
`workflow_lisp_frontend_specification.md` to the implemented contract and does
not promote the future macro work in
`workflow_lisp_unified_frontend_design.md` into current behavior

## 1. Purpose And Scope Boundary

This document is the durable repo contract for the current Workflow Lisp
`defmacro` surface.

It exists to answer one bounded question:

```text
What macro behavior is implemented today, and which existing layer owns each
class of macro-origin failure?
```

This contract is intentionally narrower than the umbrella frontend design and
the future unified design. It documents the current checkout only.

In scope:

- top-level template-based `defmacro` expansion;
- hygienic introduced names for macro-generated identifiers;
- imported macro visibility and precedence;
- validator ownership for macro-origin failures;
- source-map and diagnostic provenance obligations.

Out of scope:

- compile-time evaluation or filesystem/network access;
- intentional capture syntax;
- runtime macro values, runtime closures, or dynamic dispatch;
- alternate lowering, alternate validators, or macro-owned runtime semantics.

## 2. Supported Current Macro Model

The current macro surface is a deterministic frontend-only syntax expander.

Current `defmacro` behavior:

- macros are declared only at module top level;
- the compiler collects local macros before expanding non-`defmacro` forms, so
  same-file forward references are supported;
- parameter lists support positional names plus final `&rest` or `&body`
  capture;
- macro expansion operates on syntax nodes, not strings;
- expansion is recursive and deterministic, with stable expansion ids such as
  `m0001`;
- imported macros participate in the same expansion pass as local macros;
- imported macros may emit helper-composed `let*` bindings whose initializer
  calls resolve through the ordinary imported `defproc` lookup/typecheck path;
- macro output must still elaborate, typecheck, lower, and pass shared
  validation through the ordinary frontend pipeline.

Allowed emitted top-level forms are the existing frontend definition forms:

- `defenum`
- `defpath`
- `defschema`
- `defrecord`
- `defunion`
- `defworkflow`
- `defun`
- `defproc`

Current macros do not support:

- emitting top-level `defmacro`;
- compile-time provider calls or command execution;
- alternate semantic IR or executable IR generation;
- runtime transport of macro values.

## 3. Hygiene And Capture Policy

The current surface is hygienic for macro-introduced names and does not support
intentional capture.

Current rules:

- identifiers introduced by the macro template receive hygienic resolved names
  tied to the expansion id;
- caller-authored identifiers passed through the macro keep their authored
  identity and provenance;
- when a macro introduces a helper-result binding and later references that
  binding or one of its fields, hygiene rewriting keeps those references tied
  to the same introduced local so downstream typing and lowering treat it as an
  ordinary lexical binding;
- unintentional capture is prevented by introduced-name rewriting rather than
  by a second runtime binding model;
- there is no syntax for intentional capture, rebinding caller locals on
  purpose, or creating runtime macro values.

Effect visibility follows authorship:

- caller-authored `provider-result` or `command-result` syntax spliced through
  a macro alias remains caller-authored and continues through the ordinary
  validator path;
- `provider-result`, `command-result`, or other effectful syntax introduced by
  the macro template itself is hidden macro surface and must be rejected by the
  existing effect validation pass.
- imported helper `defproc` calls introduced as explicit `let*` initializers
  are allowed because their effects stay visible through the ordinary procedure
  typing path; direct macro-owned variant proof is still not a supported macro
  capability.

## 4. Imported Visibility, Qualification, And Local Precedence

Imported macro visibility is owned by module import resolution first, then by
macro catalog construction.

Supported imported name surfaces:

- unqualified names imported through `:only`, such as `m`;
- alias-qualified names such as `helper.m`;
- module-qualified names such as `demo/helper/m`.

Current precedence rules:

- local macro definitions override imported unqualified `:only` names of the
  same spelling;
- qualified imported names remain explicit and continue to resolve through the
  import scope;
- ambiguous unqualified imported macro names are rejected by the module/import
  layer with `module_import_ambiguous` before macro expansion continues.

This means macro lookup is not a second authority for collision handling.
Import-scope resolution decides visibility and ambiguity; the macro catalog only
consumes the already-authorized visible bindings.

## 5. Validation Ownership Matrix

Macro expansion does not create a separate validation stack. Failures remain
owned by the existing layer that already validates that class of behavior.

| Failure class | Current owner | Representative codes |
| --- | --- | --- |
| Macro definition shape, arity, reserved names, expansion cycles, invalid emitted top-level form | frontend macro layer | `frontend_parse_error`, `macro_arity_error`, `macro_reserved_name`, `macro_expansion_cycle`, `macro_emits_invalid_ast` |
| Imported alias or `:only` ambiguity | module/import layer | `module_import_ambiguous`, `module_alias_duplicate`, `module_export_missing` |
| Macro-template-introduced hidden provider or command effect | frontend effect validation | `macro_hidden_effect` |
| Downstream expanded-form failures after expansion succeeds | existing downstream validator | for example `name_unknown`, `frontend_parse_error`, shared-validation codes |
| Source-map lineage omissions for generated nodes | source-map validator | `source_map_executable_node_unmapped`, `source_map_generated_effect_invalid` |

Ownership rule:

```text
Macro provenance is additive.
It does not replace the owner of the underlying failure.
```

## 6. Active Vs Reserved Or Deferred Macro Diagnostics

Active macro-specific diagnostics in the current checkout:

| Code | Status | Meaning |
| --- | --- | --- |
| `macro_arity_error` | active | macro invocation supplied too few or too many arguments for the declared parameter list |
| `macro_reserved_name` | active | reserved head binding or duplicate local macro definition |
| `macro_expansion_cycle` | active | recursive expansion cycle detected during macro expansion |
| `macro_emits_invalid_ast` | active | expansion emitted an invalid top-level form or invalid splice shape |
| `macro_hidden_effect` | active | macro template introduced a hidden provider or command effect |

Current non-macro codes that still apply to macro-origin output when they own
the real failure:

- `frontend_parse_error`
- `name_unknown`
- `module_import_ambiguous`
- `source_map_executable_node_unmapped`
- shared-validation, semantic-IR, and executable/source-map bridge codes when
  those layers detect the failure

Reserved or deferred macro surface in this checkout:

- intentional capture syntax;
- compile-time evaluation;
- runtime macro values;
- dynamic dispatch or runtime callable transport;
- any future paper-only macro diagnostic names not backed by code and tests.

No additional reserved macro diagnostic code is emitted today for those deferred
surfaces. They remain future-scope only.

## 7. Source-Map And Explain/Provenance Obligations

Macro-generated structure must preserve provenance through the existing
`ExpansionFrame` and `expansion_stack` channel.

Current obligations:

- macro-origin diagnostics must preserve the macro call site;
- when relevant, diagnostics must also preserve the macro definition site;
- nested expansion notes render in stable outer-to-inner order;
- source-map validation must map generated semantic and executable nodes back
  to authored origins instead of collapsing failures into generic macro errors;
- downstream validation failures may keep their original diagnostic code, but
  they must retain macro provenance notes when the failing structure came from
  expansion.

This provenance rule applies equally to:

- frontend diagnostics rendered directly from expanded forms;
- serialized diagnostics;
- source-map validation of executable nodes and generated semantic effects;
- explain/debug surfaces that reuse source-map and diagnostic lineage.

## 8. Relationship To Command-Adapter Policy And Future Macro Work

`docs/design/workflow_command_adapter_contract.md` remains authoritative for
command semantics.

This macro contract does not authorize:

- hidden command semantics;
- uncertified command adapters;
- inline Python or shell glue inside `command-result`;
- a macro-only loophole around command boundary validation.

Current boundary rules are:

- caller-authored `command-result` passed through a macro alias still must obey
  the command-adapter contract and normal command-boundary validation;
- macro-template-introduced `command-result` is rejected first as
  `macro_hidden_effect`;
- the macro surface may reference command-adapter policy, but it does not
  replace or weaken it.

Future macro work, including any fuller hygiene model or intentional capture
surface described in `workflow_lisp_unified_frontend_design.md`, requires a
separate accepted design delta. This document is not that delta.
