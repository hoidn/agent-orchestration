# Workflow Lisp REPL

## Metadata

- **Title:** Workflow Lisp REPL
- **Status:** contract; delivery and evidence are tracked in the execution plan
- **Kind:** feature
- **Owner:** Workflow Lisp frontend and evaluated-runtime maintainers
- **Reviewers:** Independent code and design reviewers
- **Created:** 2026-10-12
- **Last material update:** 2026-10-12
- **Related docs / issues / plans:** [Execution plan](../plans/2026-10-12-workflow-lisp-dynamic-repl-port-plan.md), [evaluated execution](workflow_lisp_evaluated_execution.md), [frontend baseline](workflow_lisp_frontend_specification.md)
- **Implementation target:** Evaluated entries at DSL 2.35 and 2.36, plus branch-qualified native target 3.0

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

The sections below retain the typed upstream contract from commit
`a761b1c62bb2e492eb30e9f03bbe416468ce31b0`. The final section specifies
the native target-3.0 extension and its explicit profile differences.

## Context And Authority

Read [the documentation hub](../index.md), [capability matrix](../capability_status_matrix.md)
and [design routing](README.md) before selecting contracts. Normative CLI and
persistence behavior remain owned by [CLI](../../specs/cli.md) and
[State](../../specs/state.md). This design supplies their bounded REPL delta;
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
and entry return type; otherwise it fails `repl_no_result`.

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
[execution checklist](../plans/2026-10-12-workflow-lisp-dynamic-repl-port-plan.md) owns work
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
Persistence specs require no new wire contract. The execution plan owns delivery
status and independent acceptance evidence.

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

## Native Target 3.0 Extension

### Contract and retained boundaries

One `orchestrator repl` supports the existing typed 2.35/2.36 contract and the
branch-qualified [dynamic profile](../../specs/versioning.md#branch-qualified-target-30).
Its native source, values and state remain governed by
[dynamic architecture §9](workflow_lisp_dynamic_core_proposal.md#9-complete-consumer-production-candidate),
[CLI](../../specs/cli.md#dynamic-execution) and
[state](../../specs/state.md#dynamic-fresh-run-authority). This extension authorizes
explicit, read-only lexical reconstruction for the REPL; it does not alter the
source-free, nonreplaying contract of ordinary dynamic report/status readers.
The execution plan owns implementation ordering, prerequisites and evidence.

Retaining 2.36 includes its actual W3 compiler prerequisites, not merely admitting
a version string. Importing those prerequisites does not select the dynamic
profile as the default or authorize application migrations. Flat profiles,
interactive effects, resume, new persistent definitions and multiline input
remain outside this REPL.

Choose one shared command loop and the ordinary compiler/evaluator for each
existing execution profile. Native inspection adds no durable field, runtime
value codec, effect ledger, replay cache or recovery authority. The cost is
explicit module loading for native attachment, weaker historical integrity
evidence than typed memo, and inspection that depends on the existing strict
path/result contracts. Those limitations are preferable to inventing a second
persistence model for an inspection command.

### Session, attachment and output

`:load` uses the existing target selector and native build owner for 3.0. It
retains transient compiler context without publishing additional files. Typed
loading and attachment continue through their original owners. Loaded modules
are replaced only after a successful build; changing target or semantic digest
clears an incompatible captured environment.

Native `:attach` requires a loaded native module and the exact state routing pair
`3.1` / `dynamic_execution.v1`. Missing context gives `repl_module_required` with
instructions to use `:load`. There is no native `resume_request`, and the
program's source hashes and paths do not contain recoverable source text.
Do not invent a durable recipe or synthesize imports from qualified code names.
The loaded module's semantic digest must equal the saved program digest before
capture. A mismatch clears attachment and uses the shared existing
`resume_program_changed` diagnostic with a neutral program-mismatch message.
Unknown/mixed profiles refuse; they never fall through to typed memo loading.

`:run` alone executes a workflow: reuse the public parser and `run_workflow`,
including native option validation, then attach the returned run root. Neither
attachment nor expression evaluation may call a command/provider performer,
create an attempt, acquire a writer lock, publish a result, repair a state file,
or invoke resume. Failed ordinary session commands preserve a compatible prior
capture. Inspection changes no run files, source files, manifests or saved
program bytes/digests.

Native `:bindings` lists visible names and runtime kinds, including `Function`
for a closure; it does not invent typed signatures or infer boundary schemas.
Data expressions print ordinary canonical JSON followed by their runtime kind.
A bare closure prints `<function>` and `: Function`. Records/lists containing
closures remain usable internally: fields/elements can be selected and their
functions called. Printing such a container refuses with
`repl_value_not_printable`; it does not encode functions into JSON or hide them
behind transportable substitutes. Native `:result` prints the declared result
schema and completed entry value only when the saved state is `completed` and
the checked reconstruction agrees. A null result is a result, not absence;
represent availability explicitly rather than testing `value is None`.

For example, save this pure module as `scratch.orc` in a disposable workspace:

```scheme
(workflow-lisp
  (:language "0.1") (:target-dsl "3.0") (:budget 100)
  (defmodule scratch) (export run)
  (defworkflow run ((n Int :default 7)) -> Int
    (let* ((add (fn (x) (+ n x))))
      (add 0))))
```

Then `:load scratch.orc`, `:run`, `(add 5)` and `:result` produce `12` and `7`
respectively. `:bindings` includes `n : Int` and `add : Function`. A later
session uses `:load scratch.orc` followed by `:attach RUN_ID`; its entered
expressions reuse the reconstructed closure without another workflow launch.

### One evaluator with an internal expression entry

In `workflow/dynamic/evaluator.py`, extract the current iterative reduction loop
into one internal function accepting the checked program, starting body,
environment, definition/pointer and activation. Public `evaluate` retains input
binding, default handling and the root `boundary_return`; both entry paths use
the same loop, operators, call handling, closure objects and budget checks.
The internal expression entry accepts already-native immutable values. It must
not pass them through `bind_inputs`, `Value`, JSON, or a synthesized workflow
boundary. Calls made by an expression to actual declared workflows still apply
those workflows' real input/result boundaries.

Add an optional in-memory observation seam to the loop. Each pending reduction
continuation owns its lexical environment, definition, source pointer and
activation; observation follows that owner when the continuation runs. In
particular, an operator or `perform_done` restores its caller's environment
after evaluating operands, and a helper-return continuation restores the caller
after the helper finishes. A boundary-return check observes the completed
body's exit scope. It must not reset capture to the entry parameters. A failed
argument/body operation preserves the innermost failing scope; no later outer
catch overwrites it.

The final entry scope includes the `let*` bindings in the selected exit body,
with ordinary shadowing. It excludes locals belonging only to an operand or a
returned helper. Capture the actual post-boundary root result, not an incidental
operand/helper return. Copying the last `enter` event, retaining one global
latest environment, or unioning all visited bindings cannot satisfy this rule.
Observer/return bookkeeping consumes no language node budget and changes no
evaluation order, call trace, error activation or existing return value.

### Checked reconstruction of existing native state

`workflow/dynamic/capture.py` owns the session-only reconstruction. First call
`load_dynamic_run` with a pinned `WorkspaceFiles` run owner; do not change that
loader or derive authority from logs. Read the atomic state snapshot once.
Evaluate its checked program and bound inputs with capture enabled and two
read-only effect callbacks. Those callbacks consume the snapshot's ordered rows
by ordinal, comparing each reached definition, expression location and effect
class. They never delegate to `workflow/dynamic/runtime.py`.

For each reached `completed` row, read its prescribed physical `result.json`
through the run file owner and use the shared `validate_effect_result` with
`native_result=True`. Reuse the result's declared contract and the saved
workspace owner; do not substitute state output, stdout or a fabricated value.
The same strict boundary/path validation applies during reduction. An absent
required workspace asset or invalid result can therefore refuse attachment;
inspection does not weaken validation to recover a historical value.

A reached `running` or `failed` row stops at that effect's true caller scope.
So does the first reached effect without a recorded row. Partial or orphan
bundles never become completed results. For a stored failed terminal without
a failed row, require either a reproducible pure error at the same code,
location and step count, or the recorded pre-dispatch failure at the next
reached effect boundary. Such a pre-dispatch failure may depend on external
files/executables, so retain its recorded diagnostic instead of reenacting
preflight. Its location and recorded steps must match the reached boundary.

For completed state, reconstruction must consume every completed row, halt,
and reproduce both canonical terminal value and exact `steps_used`. Unreached
or reordered rows, malformed/missing completed results, a contradictory error,
or disagreement with a completed terminal refuses `dynamic_state_invalid`.
Reconstruction must also account for every snapshot row when it stops: a pure
failure cannot silently leave later recorded effects unused. When a final
failed row exists, its diagnostic and any failed terminal must agree.

Track the evaluator step count at each reached recorded effect boundary: both
its start and settlement persist that same count. For a stored `running`
snapshot, `steps_used` must equal the last recorded effect's boundary count,
whether that final row is completed, running or failed; with no rows it must
be zero. For a final failed effect, its error's step metadata must also equal
that reached boundary count, as must `steps_used` in a failed terminal. A pure
failed terminal instead retains the exact reproduced error count described
above. Any disagreement refuses `dynamic_state_invalid`. These are capture
checks, not changes to the loader or state schema.

Stored `running` is not a terminal assertion. An otherwise consistent replay
may reach the next effect, a pure failure, or an unpublished pure halt after the
last state transition. Retain the corresponding inspectable scope; use position
`halt-unpublished` for the last case and make `:result` return `repl_no_result`.
The later reconstructed count is not the saved progress count: neither an
unrecorded next effect nor a pure halt/failure advances a running snapshot's
last durable transition. Do not compare `steps_used` with that speculative
frontier or reject a legitimate unfinished pure prefix for the difference.
Do not infer physical interruption at a particular pure instruction: the state
records effect progress, not every reduction. Existing liveness semantics and
`resumable: false` remain authoritative.

This checks result shape, reached row identity/order and terminal consistency.
Native state does not record historical result digests or operand fingerprints,
so this contract cannot detect every schema-valid alteration of historical
result files. No guarantee from typed memo is implied, and no new state fields
are added to manufacture that guarantee.

### Ordinary native compilation for entered expressions

Retain the existing `_Lowerer` compilation context transiently in
`DynamicSourceCompilation` and `DynamicProgramBuildResult`, excluded from
comparison, repr and serialization. `workflow_lisp/dynamic/repl_expr.py` reads
exactly one datum with the existing reader and lowers it with the ordinary
dynamic lowerer. Lexical names come from the captured environment and shadow
module names normally. Module resolution uses the captured definition's owning
module, including its actual source import scope.

Separate the lowerer's lexical-resolution module from the emitted ownership
and source of the entered datum. This permits one ephemeral internal helper
and any inline `fn` definitions under a collision-free virtual REPL module,
while references to module functions retain their original code identities.
Reuse the lowerer's source-map/artifact assembly and `DynamicProgram.from_artifact`
to admit an in-memory copy containing the original checked definitions plus
the expression helper. Its parameters are the captured lexical names; its
boundary is null. Preserve the original program entry and its declared boundary.
The virtual source records the entered text's own hash and spans. Never
attribute it to old file bytes or manufacture source by concatenating a module.

The temporary copy has its own computed identity; the loaded and attached
programs, their original definition/source entries and saved digests remain
unchanged. It is never published, assigned a build key, or reused as run
authority. Start the common internal evaluator directly at the expression
helper body with the captured native environment. Existing closure code IDs
continue to resolve to the preserved definitions, including imported closures
and closures held inside lists/records. A failed or successful expression leaves
the attached environment and retained compiler context unchanged.

Reject any directly lowered `perform` in the entered expression or its newly
created inline functions with `repl_effect_refused`. For calls through existing
functions or captured closures, evaluation installs no effect performers;
reaching `perform` maps `dynamic_effect_unsupported` to `repl_effect_refused`
before its operands or dispatch. This also blocks transitive effects without
adding global function-effect inference. Native purity is an execution guard:
an untaken branch can mention an effectful existing function. Typed 2.35/2.36
keep their existing stricter compile-time transitive-effect checks. Each entered
expression receives the loaded program's normal finite budget afresh; it cannot
consume or reset the attached run's recorded budget.

### File ownership and required evidence

| Owner | Change |
| --- | --- |
| `workflow_lisp/dynamic/{source,build}.py` | Transient context, reuse of ordinary lowering/admission for an ephemeral expression helper; no new build artifact |
| `workflow_lisp/dynamic/repl_expr.py` | Single-datum expression bridge and direct-effect refusal |
| `workflow/dynamic/evaluator.py` | One loop shared by public and internal entries, exact continuation-owned capture, absent-performer guard |
| `workflow/dynamic/capture.py` | Checked read-only reconstruction, lexical result and native presentation data |
| `cli/commands/repl.py` | Shared session/commands with exact native versus typed dispatch |
| `tests/test_workflow_dynamic_repl.py` | Public native CLI acceptance and regression cases |
| `specs/{cli,state}.md`, docs routing and drafting guide | Exact per-profile behavior and inspection limits |

Before implementation is accepted, demonstrate the following through the real
compiler, state loader and evaluator; public checks may use controlled local
command/provider transport but no paid providers:

- Pure and completed command/provider runs attach through the public CLI;
  field/list expressions, ordinary local/imported functions, captured closures,
  shadowing, defaults and null results work. Hash the whole run tree before and
  after inspection and verify that no launch occurs.
- A final helper call and nested compound operand restore caller scope; a root
  `let*`/selected branch retains its own exit bindings. Interrupted/failed
  effects and late pure failures expose their actual lexical scope and no
  completed result. Cover a failure after an operand returns from a helper.
- Direct effects, an effectful imported helper and an effectful captured closure
  refuse without launch. A pure captured closure still works. Container-held
  closures remain usable without crossing a public `Value` boundary.
- Corrupt results, wrong row identity/order, an unreachable completed row,
  contradictory terminal output/error/steps and mismatched module digests
  refuse. A running row with an orphan successful bundle remains unfinished;
  a pure halt without terminal publication remains `halt-unpublished`.
- Tampering `steps_used` to another in-range value on a running snapshot or
  failed effect refuses, including a final running row changed to zero. Valid
  running snapshots with no rows or a completed prefix still attach when pure
  reconstruction reaches a later unrecorded effect or unpublished halt.
- Repeated successful/failed queries do not mutate base artifacts, compiler
  state, captured values or budgets; entered-source diagnostics have genuine
  virtual-source ownership. Existing evaluator call traces/budget errors and
  strict boundary rejection of closures remain unchanged.
- Native missing-module/profile refusals and all retained typed public tests
  pass. Existing ordinary dynamic readers remain source-free and nonreplaying.

An executable architecture check can already construct an admitted internal
helper taking a closure that captures `7`, invoke it with `5`, and obtain `12`
from the ordinary evaluator. Moving that closure through a workflow `Value`
parameter must still produce `dynamic_boundary_invalid`. This proves the value
route, not the new capture or standalone compilation seams; the acceptance
cases above are required evidence for those seams.
