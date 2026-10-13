# Workflow Lisp REPL

## Metadata

- **Title:** Workflow Lisp REPL
- **Status:** implemented
- **Kind:** feature
- **Owner:** Workflow Lisp frontend and evaluated-runtime maintainers
- **Reviewers:** Independent code and design reviewers
- **Created:** 2026-10-12
- **Last material update:** 2026-10-12
- **Related docs / issues / plans:** [Execution plan](../plans/2026-10-12-workflow-lisp-repl-plan.md), [evaluated execution](workflow_lisp_evaluated_execution.md), [frontend baseline](workflow_lisp_frontend_specification.md)
- **Implementation target:** Evaluated entries at DSL 2.35 and 2.36

## Summary

Add `orchestrator repl` to load a Workflow Lisp module, explicitly run it through
the ordinary public run service, attach to an evaluated run, inspect its lexical
bindings and result, and evaluate a pure expression against those bindings.
Attachment reconstructs a checked memo prefix without launching effects or
writing run evidence. Expression compilation and evaluation use the ordinary
frontend and closed evaluator, including pure module functions and procedures.

This is a new interactive CLI surface over existing compilation and run
contracts. It creates no persistence profile, expression language, operator
implementation, or alternate execution authority.

## Context And Authority

Read [the documentation hub](../index.md), [capability matrix](../capability_status_matrix.md)
and [design routing](README.md) before selecting contracts. Normative CLI and
persistence behavior remain owned by [CLI](../../specs/cli.md) and
[State](../../specs/state.md). This proposal supplies their bounded REPL delta;
it does not supersede the existing run or resume entrypoints.

The [evaluated-execution design](workflow_lisp_evaluated_execution.md) owns
lexical values (§5), authoritative header/program and rebuild recipe (§8.4),
checked read-only replay (§10), and diagnostics (§12). The frontend baseline,
[W3 contract](workflow_lisp_write_once.md) and existing target-aware compiler
own expression syntax, names, typechecking and inferred local hooks.

Implementation authorities are `cli/main.py::_add_frontend_flags`, the public
`run_workflow` service, `cli/commands/evaluated.py::_resume_build_request`,
`workflow_lisp/closed/{frontend,artifact,values}.py`,
`workflow/evaluated/{authority,memo,views,machine,values}.py` and
`workflow/workspace_files.py`. Existing read-only view replay already checks
commit reachability/order and completed-terminal consistency. Lexical capture
and standalone expression compilation are additive seams whose feasibility
must be demonstrated by the integration scenarios below before acceptance;
existing report evidence alone does not prove those capabilities.

## Problem

An operator can compile, run and report a workflow, but cannot inspect its
current lexical environment or try a typed pure expression in that environment.
Flat persisted steps are insufficient: values are computed in lexical frames,
and the position of an interrupted program requires checked replay. Adding a
second evaluator or reconstructing scope from report JSON would create a
competing semantic authority.

## Goals And Non-Goals

Goals are checked attachment to completed, interrupted and pure-failed runs;
correct lexical scope, shadowing and binding types; ordinary pure expression
and pure module-call semantics; explicit public execution; and byte-preserving
inspection with ordinary diagnostics.

Non-goals are effects in entered expressions, resume inside the session,
module editing or hot reload, LSP integration, flat targets through 2.34,
multiline input, new definitions, completion or persistent history, and changes
to workflow launching mechanics. New modules remain below 500 lines.

## Decision

Use a small CLI session, an in-memory compiler context, a capture subclass of
the existing frozen machine, and an ordinary frontend expression pipeline.
Replay uses the existing checked view replay and terminal checks. A loaded
module must match the attached run's program digest. Without a loaded module,
rebuild its persisted recipe in memory to recover the compiler context.

Reject Python `eval`, a second JSON operator evaluator, and `report --expr`:
each either bypasses language contracts or puts executable expression handling
inside an existing reporting surface. This choice couples capture to the
machine's private callbacks and makes multiline editing, effectful interactive
execution and source-independent module calls harder; those remain separate
features. No core design decision is left open.

## Design Details

### CLI session and commands

```text
orchestrator repl [WORKFLOW] [frontend flags] [--run-id RUN_ID] [--state-dir DIR]
:load PATH [frontend flags]
:run [--input NAME=VALUE ...] [--input-file JSON] [--state-dir DIR] [--run-ref-root DIR]
:attach RUN_ID
:bindings
:result
:where [NAME]
:help
:quit
```

Reuse `_add_frontend_flags` exactly as run/compile do for entry selection,
source roots and extern/boundary/import manifests. Startup loads the optional
workflow first, then attaches the optional run. Input is one expression or
command per `input()` line. A prompt and optional readline support are enabled
only for a TTY; piped input receives no prompt. EOF and `:quit` exit 0.

`:load` constructs `FrontendBuildRequest` and calls
`build_closed_program_bundle`, publishing only the ordinary build artifact.
Compile diagnostics use `render_diagnostic`. Failed loads retain the previously
loaded module. Failed ordinary commands retain compatible session state; a digest mismatch
clears attachment so no incompatible module/frame pairing remains usable.

`:run` requires a loaded module. Parse its options using the public run CLI
contract, pass the loaded module's frontend request to `run_workflow`, and
attach the returned `run_root` after the public service releases writer locks.
Forward the session's state directory unless `:run --state-dir` overrides it.
Inputs retain public run parsing, precedence and validation; there is no
second binding path. Effects and evidence writes occur only during this
explicit command, with ordinary public run authority.

### Checked read-only attachment

Locate the requested root using the session state directory, then retain
`WorkspaceFiles` while reading `run.json`, `closed_program.json` and
`memo.jsonl`. Use `load_run_authority_from_bytes` and
`reduce_memo(..., site_classes(program))`; a derived `state.json` is never
input authority. Attachment neither acquires the writer lock nor appends,
repairs, reconciles or publishes views. It captures one checked journal prefix,
not a live subscription or an atomic transaction against a concurrent writer.

Require the evaluated profile. A flat run fails `repl_profile_unsupported`;
a missing root fails `repl_run_not_found`; malformed authority or memo keeps
ordinary checked-loader diagnostics. When a module is loaded, compare its
program digest with the attached authority before accepting the session state;
a mismatch fails `resume_program_changed` and leaves the session detached.

When no module is loaded, use `_resume_build_request` and
`prepare_closed_program_bundle` to rebuild the header's durable recipe entirely
in memory. Require a present recipe (`resume_request_missing`) and matching
program digest (`resume_program_changed`). Preserve ordinary compile errors.
Do not read or publish build-cache artifacts, infer a recipe from bound inputs,
rebind fresh input files, or acquire resume writer authority. Replay binds the
stored authoritative inputs. A matching explicitly loaded module allows
inspection of a historical header without a recipe.

### Capture at the true execution position

Add `workflow/evaluated/capture.py` with a frozen `_CaptureMachine` subclass of
`_Machine`. Its mutable trace object survives `dataclasses.replace` when calls
construct callee machines. It adds observation only:

- `_halt` calls `super()` first, then appends its environment and already
  evaluated value to the shared `trace.completions`.
- `_done` calls `super()._done` and observes the existing `_ControlTransfer`
  after its operands have been evaluated. For `kind == "done"`, append the
  environment and already evaluated transfer value, then rethrow the same
  exception. Do not reevaluate operands or alter loop/control-transfer handling.
- `_perform` calls the ordinary implementation and catches `views._MissingCommit`
  after operand evaluation, recording the first stopped environment and effect
  identity. A stop overrides incidental successful halt/done exits.
- `_body` catches `EvaluatedValueError`, recording the first (innermost) failed
  lexical environment and position `failed:<code>`, then rethrows. A failure
  also overrides incidental successful completions.

For successful replay, the last halt/done event supplies the lexical exit
frame. A root loop can complete through `done` without a halt event; an
incidental seed-block halt of 3 must not replace the loop result 7. Capture the
actual return of `_Machine.evaluate` separately in `trace.result`, after
ordinary result coercion and dependency propagation, rather than using an
observed completion value. Completed capture still has position `halt`, naming
the terminal semantic outcome rather than requiring a particular body opcode.

An uncommitted effect inside a callee captures the callee's lexical frame,
not the caller's frame. The shared trace must retain that capture as exceptions
unwind. Ordinary evaluation order, calls, coercion and control transfers remain
unchanged.

`views._replay` gains a keyword evaluator parameter defaulting to
`evaluate_closed_program`. Its effect handler, consumed-commit checks and
error handling stay unchanged. Capture supplies its evaluator to `_replay`
and calls `_checked_terminal` afterward. An unreachable/out-of-order commit,
pending-start inconsistency or contradictory completed terminal therefore
fails `memo_inconsistent` exactly as reporting does. A normal pure failure
with no contradictory evidence remains inspectable and has no result.

### Binding types and transient compiler context

`capture.py::visible_bindings` walks innermost frames first, retains
the first occurrence of each name and hides compiler names beginning with
`%`. Display surviving bindings in outer-frame order, retaining inner-frame
shadowing, with name, rendered type, capture position and run identity.

Map runtime descriptors back to frontend type refs by canonical structural
descriptor identity with provenance removed. Collect the transitive closure
of signature types, refs in `builder.emitted_descriptors`, every `TypedExpr`
ref in entry/procedure bodies, and resolved record fields, list items, map
keys/values, optional items and union components. Do not restrict the map to
top-level named types: nested enum bindings must remain usable. Synthesized
runtime `variant_case` descriptors may be displayed but cannot enter the
expression type environment; descriptor similarity cannot invent frontend
variant proof.

Add frozen `ExpressionCompileContext` containing `function_catalog`,
`typed_functions_by_name`, and the function/procedure/workflow name resolvers.
Attach it to the entry module's `Stage3CompileResult` using the existing
compiler locals. The additive `expression_context` field defaults to `None`,
with `compare=False` and `repr=False`.

Add equally transient/defaulted `typed_program`, `stage3` and `builder` fields
to `ClosedProgramBuildResult`. Introduce
`compile_typed_program_with_result` returning the typed program and entry
Stage-3 result; preserve `compile_typed_program` as its existing-result wrapper.
These are in-memory products, excluded from artifacts, manifests, schema,
header and digests. Preserve existing callers and exports.

### Ordinary expression compilation and evaluation

Read with `read_sexpr_text` and require exactly one datum, producing a
`SyntaxNode`. Call `expressions.elaborate_expression` with captured type refs
and the loaded module's extern/type/procedure/function/workflow catalogs and
resolvers. Preserve the ordinary target-2.36 inferred-hook branching. Apply
`functions.normalize_function_calls` where the ordinary compiler supports it,
then `typecheck_expression`. Ordinary unresolved names remain `name_unknown`.
A missing context refuses module calls with `repl_module_context_missing`,
rather than silently using reduced catalogs or another evaluator.

Keep the ordinary frontend §10.2 equality contract: `=` / `!=` accept supported
scalars and same-type enums, with no added deep-list equality. `list/empty?`
is the ordinary list-emptiness predicate. This feature does not broaden
operators or their operand/result semantics.

Enforce purity at three boundaries:

1. Refuse a nonempty `typed.effect_summary.transitive_effects` with
   `repl_effect_refused`, including transitive procedure effects.
2. Lower through the normal prepared-owner pipeline. Build an ephemeral
   `TypedWorkflowDef` containing the actual `TypedExpr`, with a minimal signature
   of the captured typed parameters and expression return type, retaining the
   loaded entry's source owner. Create `builder.definition_context`, retain
   identity names, call `_prepare_command_owner`, `_install_prepared_requests`,
   the ordinary computed-capture preparation, then `builder.body` and the
   installed request verifier. Direct `frontend_value` alone lacks prepared
   call coordinates for closed-opaque pure calls. Recursively guard the lowered
   value, block bodies and reachable callee bodies against `perform`; allow pure
   calls. Never determine purity from the entered head alone.
3. Call `evaluate_closed_value` with ordinary `_Machine._body`/`_bound`
   callbacks and `effect_handler=None`, `provider_io=None`. Map an eventual
   `closed_effect_handler_missing` to `repl_effect_refused`.

Pure module `defun` and `defproc` calls use ordinary lowering and callee
execution. Lowering may add previously unreachable pure procedure definitions
into the retained builder. Evaluate such calls against an in-memory program
view carrying the builder definitions and nominal types; do not mutate
`authority.program`, the published closed artifact or its digest. The loaded
build result's `.program` is a JSON-readback snapshot, not an alias of the
retained builder, so this view requires no deep copy of the builder. There is
no Python evaluation or REPL-specific operator evaluator.
Entered expressions cannot mutate the captured lexical frame or run evidence.

## Contracts And Interfaces

This adds a CLI command and transient compiler/runtime helpers; existing run,
compile, resume and report contracts retain their behavior. An expression or
`:result` prints canonical UTF-8, compact, sorted-key JSON on one line followed by a second line exactly
`: <rendered type>` on stdout. `:result` returns only the halted entry value
and entry return type; otherwise it fails `repl_no_result`. `:where NAME`
prints the absolute result-file path of a performed binding under the attached
run root, `:where` alone that of the entry result; a computed value fails
`repl_no_result_file`.

REPL/runtime errors print `[code] detail` to stderr. Frontend errors keep
ordinary localized `render_diagnostic` output with `kind`/`form` context.
Session commands fail without ending the input loop; startup failures exit 2 and unexpected failures exit 1.
Diagnostics include `repl_effect_refused`, `repl_run_not_found`,
`repl_profile_unsupported`, `repl_not_attached`, `repl_module_required`,
`repl_expression_arity`, `repl_no_result`, `repl_module_context_missing`,
ordinary `name_unknown`, and the reused authority/compile/resume codes.
`:bindings`, `:result` and expressions require attachment; `:run` requires a
loaded module. `:help` describes these commands and the pure-expression limit.

## Dependencies And Sequencing

The evaluated 2.35/2.36 authority, public build/run services, closed evaluator
and W3 compiler are prerequisites. This proposal does not select broader
runtime roadmap work. Implement the transient compile products before the
expression bridge, and capture before CLI attachment. The bounded
[execution checklist](../plans/2026-10-12-workflow-lisp-repl-plan.md) owns work
ordering and verification records; this durable design owns the contracts.

## Invariants And Failure Modes

Run evidence is byte-identical before/after attach, bindings, result and any
pure/refused/failed expression. `:load` writes only ordinary build artifacts;
`:run` writes only through public execution. No new memo records, schema,
header keys, digest components or evaluator semantics are introduced.

Loaded source/context must match the attached program. Failed loads and ordinary command errors preserve compatible session state;
a digest-mismatched attach clears attachment and never retains an incompatible
module/frame pairing. Checked replay errors cannot be masked by
capture or replaced with a best-effort report. Stops/failures inside operand
blocks must expose the correct lexical environment. Completion through halt or
loop done preserves the actual machine result, never an incidental seed or
operand completion value.

## Security, Operations, And Performance

Attachment has existing local run-file read authority only. Binding/result
inspection exposes those local values to the operator's terminal; it adds no
credentials, network access or provider dispatch. Explicit `:run` retains the
ordinary command/provider permissions. Use descriptor-relative run loading
and existing path checks. Replay and in-memory reconstruction have the cost of
ordinary checked replay and frontend compilation; captured frames are session
memory, not durable state. No deployment or background process is required.

## Evidence And Implementation Boundaries

Public subprocess CLI tests must load actual `.orc` sources and attach to runs
created by the real public run service. Authority loaders, memo reduction,
frontend compilation and replay must be production paths. A deterministic
provider executable shim may stand in for an external provider solely to make
completion/interruption reproducible; it proves orchestration integration,
not live provider behavior. Never run provider smoke against the live checkout.

Hashes of retained authority, memo, state and attempt files establish the
read-only boundary. Test-only direct capture helpers supplement but do not
replace the public acceptance scenarios. Review must verify no parser,
operator evaluator or effect-launch route is duplicated.

## Compatibility And Migration

No existing source, artifact, memo, header, profile or schema migrates. Targets
through 2.34 retain their route and refuse REPL attachment. Existing compile
callers retain their result type; additive transient fields default to `None`
and do not affect equality, repr or serialization. Existing view replay callers
retain the ordinary evaluator by default. Stored artifacts remain the only
execution program authority; fresh module context must have the same digest.

## Verification Strategy

Add behavioral tests in `tests/test_workflow_evaluated_repl.py`, collecting
that module before execution. Cover completed field/list expressions, pure
module function/procedure calls, including an unused helper and a nested
`defun` → `defproc` call, and entry result; completed root loops with no halt
event and an incidental seed halt 3 followed by done 7; interrupted compound operands
and callee scope; transitive effect refusal with evidence hashes; digest mismatch;
recipe-only attachment; pure failures before/after a committed effect; custom
state-root forwarding through `:run`; and nested enum binding type recovery.

Run narrow build, view, provider and resume selectors, then the complete
non-E2E campaign with `pytest -q -n 16 --dist=worksteal` in tmux. Run the
maintained `plan_review_execute` workflow through public execution in a disposable workspace;
the provider shim is a bounded stand-in, never a live-checkout provider run.
Reuse valid evidence unless later changes or unresolved failures invalidate it.
Independent review checks artifacts/digests, checked replay parity and module
size. Tests assert behavior/dataflow, never literal prompt prose.

## Declarative Acceptance / Integration Scenarios

| Initial state and public entry | Required observation and invariant | Dependencies |
| --- | --- | --- |
| A real 2.35/2.36 module/run has record/list bindings; pipe `repl WORKFLOW --run-id ID` with field/list expressions, pure `defun`/`defproc`, and `:result` | Ordinary typed JSON values and halted entry result; evidence hashes unchanged | Real frontend, run service, reader loaders and evaluator; deterministic provider shim where needed |
| Complete a root loop through `done`, both without a halt event and with a seed-block halt of 3 before done 7; attach and use `:bindings` / `:result` | Capture the loop exit frame; position is `halt`, and result is the actual postcoercion/dependency-preserving machine return 7 rather than incidental 3 | Real closed evaluator, existing control transfer and checked replay |
| Attach a module whose pure helper is unused by its workflow and whose pure function calls a pure procedure; enter those calls | Ordinary prepared-owner lowering resolves call coordinates and returns typed values; stored program, build artifact/digest and run evidence remain unchanged | Real frontend catalogs, prepared command owner and ephemeral program view |
| Interrupt a run at the first uncommitted effect after a compound operand block or inside a callee; `:attach ID`, then inspect bindings | Correct stopped lexical scope, effect identity and shadowing; no operand halt published as result; no launches/writes | Real memo replay and captured machine; controlled provider interruption |
| Attach a completed run and enter a directly/transitively effectful procedure expression | `repl_effect_refused`; memo/state/attempt files byte-identical | Real frontend type/effect analysis, lowered guard and evaluator |
| Start recipe-only attachment, then attach with a semantically changed loaded module | First reconstructs only in memory; second refuses `resume_program_changed`; missing recipe without module refuses `resume_request_missing` | Real durable recipe, build request and digest checks |
| Attach pure failure before/after an effect, or journal with unreachable commit/contradictory completed terminal | Failure frame inspectable with no result when evidence is consistent; inconsistent evidence refuses `memo_inconsistent` identically to report | Real reduction, replay and terminal checks |
| Start with a custom session state directory, load and `:run`; inspect a nested enum binding | Public run writes the selected root and attaches after locks release; enum remains typeable in an expression | Real public run parser/service and structural type recovery |

## Success Criteria

All primary and negative scenarios pass through the intended production
boundaries, narrow regressions and required smoke are recorded, and the full
campaign has explicit outcomes/dispositions. Independent code and design
review must confirm byte-preserving inspection, exact replay consistency,
ordinary pure-call semantics, compatibility and the <500-line module bound.
CLI specs, capability routing and author guidance must describe only the
verified scope. No claim of live-provider qualification follows from a shim.

## Stop / Revise Criteria

Revise if capture changes evaluation order or memo validation, purity requires
a second evaluator, module calls require serialized new context, digest parity
cannot be preserved, or public scenarios work only through private test helpers.
Escalate rather than silently add effectful expression execution, hot reload,
new artifact/schema fields or a broad runtime/compiler refactor.

## Documentation Impact

Create this design and its execution plan; add routing in [design index](README.md).
Implementation updates [CLI](../../specs/cli.md), [capability matrix](../capability_status_matrix.md),
[documentation hub](../index.md) and [drafting guide](../lisp_workflow_drafting_guide.md).
Persistence specs require no new wire contract. Preserve proposed status until
independent acceptance evidence supports a deliberate status change.

## Implementation Handoff

Likely files: `workflow_lisp/workflows.py`, `compiler.py`,
`closed/{frontend,artifact}.py` for transient context;
`workflow/evaluated/{views,capture}.py` for visible bindings and capture;
`workflow_lisp/repl_expr.py` for the ordinary expression bridge;
`cli/commands/{repl,__init__}.py`, `cli/main.py` and the installed CLI entry
in `pyproject.toml` for registration/session;
`tests/test_workflow_evaluated_repl.py` and the documentation surfaces above.

The safe first step is the transient compile-result seam, checked against
existing build callers and artifact bytes. Review capture/terminal parity and
recursive purity guards before integrating the CLI. Keep new modules below
500 lines, use current helpers, and retain error validation at every boundary.
Implementation and test preparation follow subagent-driven execution; the
coordinator owns integration, independent review and fresh final verification.

## Open Questions

None in the selected design. Feasibility of the new seams is a verification
obligation, not permission to invent alternate semantics.

## Appendix

Illustrative session using the maintained `plan_review_execute` source and
its declared provider manifest (execute only in a disposable workspace):

```text
:load workflows/examples/plan_review_execute.orc --provider-externs-file workflows/examples/inputs/plan_review_execute/providers.json
:run --input task=inspect-this-disposable-workspace
:bindings
feedback.findings
(list/length revised.steps)
:result
:quit
```
