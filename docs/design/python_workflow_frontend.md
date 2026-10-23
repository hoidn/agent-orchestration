# Python Workflow Frontend

## Metadata

- **Kind:** frontend architecture and authoring contract
- **Status:** accepted; serial subset implemented
- **Implementation target:** Python 3.11+, generated Workflow Lisp targets
  2.35–2.40; default 2.39
- **Authority:** this document owns Python authoring and generation only. The
  contracts below continue to own compilation, execution and recovery.

## Purpose And Decision

Authors write typed workflow definitions in Python, build inspectable ordinary
`.orc` source, and execute it through the existing compiler and evaluated
runtime. Python is a source generator, never a second workflow interpreter.
The public import is `orchestrator.py`; commands are `orchestrator py build`,
`orchestrator py check`, and `orchestrator py run`. `orchestrator` is the actual
installed executable in `pyproject.toml`.

Use registration followed by symbolic tracing at build time. This admits
forward references, ordinary module reuse, typed effects and explicit bounded
control without parsing or translating Python function bodies. The alternatives
are a Python AST compiler, which duplicates language semantics, and immediate
execution, which bypasses durable runtime authority. Neither is selected.

This choice makes native Python control flow over runtime values unavailable,
requires source-backed definitions for reproducible builds, and gives static
Python checkers less knowledge than the `.orc` compiler. It does not promise a
Pyright plugin or ordinary-Python execution of a decorated workflow.

## Governing Contracts And Existing Owners

Read [the documentation hub](../index.md) and
[capability matrix](../capability_status_matrix.md) before extending admission.

| Concern | Existing authority and implementation |
| --- | --- |
| One semantic compiler | [Language principles](workflow_language_design_principles.md), [frontend baseline](workflow_lisp_frontend_specification.md) |
| Types, imports and concrete specialization | `workflow_lisp/compiler.py`, `modules.py`, `type_env.py`; `compile_stage3_entrypoint` and its linked catalogs |
| Target 2.39 procedure inference | [Procedure contracts](../lisp_workflow_drafting_guide.md#procedure-contracts-at-target-239), [effect contract](workflow_lisp_effect_ledger_simplification.md) |
| Closed compilation and configuration | `FrontendBuildRequest`, `workflow_lisp/closed/artifact.py:build_closed_program_bundle` |
| Typed prompt assembly | [Prompt fragments](../lisp_workflow_drafting_guide.md#authoring-prompt-fragments), `workflow_lisp/prompts.py` |
| Typed host questions and replies | [Durable host input](workflow_lisp_durable_host_input.md), [DSL](../../specs/dsl.md#evaluated-durable-host-input-target-240) |
| Effect identity, memo, replay | [Evaluated execution](workflow_lisp_evaluated_execution.md), [state](../../specs/state.md) |
| Run, locks and recovery | [CLI contract](../../specs/cli.md), `cli/commands/run.py:run_workflow`, `cli/commands/resume.py` |
| Diagnostic locations | `LispFrontendDiagnostic.span`, `form_path`, `notes`, and existing renderer |

The new frontend cannot widen evaluated admission. In particular it cannot
restore retired effects, make unqualified provider/parallel features qualified,
or admit imported source below 2.35. A Python module's `TARGET` constant selects
its admitted target, defaulting to `"2.39"`; imported modules retain their own
target and effect rules. The existing compiler validates import direction and
target-specific syntax. Selecting 2.35 does not acquire 2.39 inference.

## Public Authoring Surface

### Types And Values

```python
from enum import Enum
from orchestrator.py import (
    record, variant, RelPath, Text, Doc, PathOf, Value, Out,
    Prompt, prompt, Provider, Command,
    workflow, proc, pure, match, when, loop, cont, done,
    build, check, run, import_orc, ask, HostReply, host_input,
)

class Verdict(Enum):
    ACCEPT = "accept"
    REVISE = "revise"

class ReportPath(RelPath, under="reports", must_exist=True):
    pass

@record
class Draft:
    text: str

@variant
class Completed:
    report: ReportPath

@variant
class Blocked:
    reason: str

Attempt = Completed | Blocked
```

`@record` registers ordered annotated fields and provides a constructor.
`@variant` registers a named case, including an empty case; a union of these
classes is the closed union type. Named module-level aliases such as `Attempt`
provide the emitted union name. Resolve aliases after module import, choose a
single defining owner, and reject ambiguous competing declarations rather than
depending on dictionary traversal order. Re-exporting the same owned type does
not declare a new type. Different modules may declare the same short name.

Type mapping is direct: `str`, `int`, `float`, `bool`; declared enums, records,
paths and variant unions; supported `list[T]` and `T | None`
map to their existing `.orc` types. Recursive, `Any`, arbitrary object and
unsupported Python annotations fail at the author location. There is no new
coercion or schema validator. Callable parameter and return annotations are
required, with `returns=T` as an explicit return annotation alternative;
conflicting alternatives are errors.

Optional annotations cover inputs and produced values. Authored `None` literals
are refused because the current source language has no null constructor; the
frontend does not synthesize a helper to manufacture one.

Enum **values**, not Python member names or `str(member)`, are emitted wire
tokens. Values must be unique strings admitted as `.orc` enum identifiers;
aliases, integer values and invalid tokens are rejected. `Verdict.ACCEPT`
therefore emits `Verdict.accept`. `RelPath` uses existing path validation and
does not turn a Python filesystem path into an unvalidated string.

Cases retain the ordinary flat `.orc` union shape, for example
`{"variant": "Completed", "report": "reports/result.md"}`. A bare case such
as `Completed` is **not** a callable parameter or return type: the existing
compiler does not admit a union case name as a standalone type. Such annotations
produce `python_variant_signature_unsupported`. Use `Attempt` and match inside
the helper, or accept the case's individual fields. No hidden payload records
or implicit case-to-record conversion are introduced.

Symbolic protocol methods and private trace metadata names are reserved fields;
ordinary domain names such as `kind`, `args`, `annotation`, and `site` remain
available. Constructors accept concrete and symbolic field values. Union construction is
resolved against its expected annotated/branch type; unresolved or conflicting
union ownership is an error. Record fields are readable on symbolic values;
union-case fields are readable only on the corresponding `match` binder.
The `.orc` compiler remains responsible for nominal compatibility and proof.

### Prompts And Effects

```python
draft_prompt = Prompt(
    file="prompts/draft.md",
    fills={"task": Text},
    returns=Draft,
)

@prompt(returns=Draft)
def inline_draft(task: Text) -> str:
    return "Draft the design for {task}."

author = Provider("codex", model="chosen-model", effort="low")
checks = Command("checks", returns=bool)

@workflow
def draft(task: str) -> Draft:
    return author(draft_prompt(task=task))
```

`Prompt` requires exactly one of `file` and `text`, explicit fill declarations
and a return type. A file is UTF-8 authoring input relative to its defining
Python module; build captures its exact bytes and emits an inline `defprompt`.
It is not a runtime workspace input file. `Text` maps to `:text`; explicit
`Value[T]`, `Doc[PathType]`, `PathOf[PathType]`, and `Out[PathType]` fill
descriptors map to existing `:value`, `:doc`, `:path`, and `:path :out` kinds.
Unsupported renderer/type pairs remain compiler
errors. Prompt application yields a compile-time fragment, only consumed by a
provider call or, at target 2.40, a host question; it is never stored in
transported runtime values.

`@prompt` registers the function and its fill signature. At build it calls the
function to obtain one literal template string; arguments are declaration
markers, not runtime strings. The function must return a template without
interpolating its markers. This is the same `Prompt` definition path, not a
second template language. Template placeholders, escaping and completeness are
checked by the existing prompt compiler.

`Prompt.extern("prompts.review", returns=Review)` references the supplied
prompt-externs manifest instead of declaring a body. A provider call emits the
existing extern prompt, supplied `:inputs`, and declared `:returns` form, which
the compiler checks. The manifest owns the prompt source; it does not declare
the result type. Python cannot replace that source or silently supply a default
binding.

`Provider(name, model=None, effort=None, timeout_sec=None)` references an existing
provider extern: `Provider("codex")` emits `providers.codex`, whose value must
come from the supplied provider-externs manifest. There are no default extern
bindings. It does not register an executable or expose credentials.
Calling it records `provider-result`. A call may override these existing policy
fields with admitted values. The prompt owns fills and return type; there is no
second `returns` or `inputs` on the fragment-backed call.

`Command(name, *, returns)` references a boundary in the supplied command
manifest; it cannot create or replace that boundary. Calling
`checks("python", "tools/checks.py", *arguments)` supplies the complete argv
and records `command-result`. The existing compiler validates that argv against
the manifest's stable command prefix; the frontend does not synthesize a prefix.
`inputs={name: value}` supplies the
existing typed document input lane when needed. Missing bindings fail through
existing compiler validation. Closure, repeat policy and executable authority
remain in the existing manifest. The existing performer validates structured
output at its provided result path; stdout is not parsed as semantic state.
Paths and numeric argv use native command transport, not Python `str`.

Provider/command calls outside a trace fail. Tracing records every effectful
call in source evaluation order, even when its Python return value is ignored.
An effect reused twice is one bound result, not two invocations.

### Durable Host Decisions At Target 2.40

Set the defining module's `TARGET = "2.40"` to use
`ask(question, *, returns, timeout_sec=None, show=())`. It emits ordinary
`request-input` and binds a symbolic `HostReply[returns]` result in source
order. The default target remains 2.39. Importing the public names, including a
star import, does not import `std/host` into an older-target module.
`HostReply[A]` applies the existing generic `std/host` type through the ordinary
`.orc` bridge; it does not declare another nominal union or value codec.
At 2.40 the compiler skeleton prepares this standard type even when only the
function body uses `ask`, without a HostReply return annotation.

A question is a string, symbolic string or fully applied typed prompt. Local
`Prompt`, decorated `@prompt` and imported prompt declarations use ordinary
named fills, including `Text`, `Value` and runtime `Doc`. The prompt's return
contract must agree with `returns`. `Prompt.extern` questions refuse: the
provider extern `:inputs` form is not a Lisp question. Prompt-file bytes are
captured authoring inputs; runtime document bytes remain semantic replay
inputs. `show` contains typed file paths, whose bytes are frozen presentation
evidence under the host-input contract. Omitted/None timeout has no deadline;
a supplied timeout must be an exact positive integer when reached.

`host_input` is the subject-free effect descriptor for an explicit procedure
restriction, such as `@proc(effects=(host_input,))`. Omitted effects infer at
2.39 and later; explicit empty restrictions still refuse reachable asks.
Descriptors take declaration objects for subject-bearing effects, for example
`uses_provider(author)` and `uses_command(checks)`.

```python
from enum import Enum
from orchestrator.py import workflow, ask, match, when

TARGET = "2.40"

class Approval(Enum):
    APPROVED = "APPROVED"
    DENIED = "DENIED"

@workflow
def approval() -> str:
    reply = ask("Approve this operation?", returns=Approval, timeout_sec=3600)
    return match(
        reply,
        ANSWERED=lambda answer: when(
            answer.value == Approval.APPROVED,
            then=lambda: "approved",
            else_=lambda: "denied",
        ),
        CANCELLED=lambda _: "cancelled",
        EXPIRED=lambda _: "expired",
    )
```

Outer matching uses the ordinary HostReply union; enum answers use supported
equality and `when`. The [complete approval example](../../workflows/examples/durable_host_input/README.md)
adds a local provider diagnosis, typed verification/evidence and conditional
command actions with complete supplied manifests.

Execution suspends the evaluated run and releases its writer; no Python process
waits for the person. The external host API/CLI settles the exact request;
ordinary resume consumes the typed reply and continues. Serial Python loops
and imported asking procedures use the same dynamic activation/request identity
as emitted Lisp. One request is pending per run; transitive parallel-worker or
child-run asks refuse. The [host design](workflow_lisp_durable_host_input.md),
[state](../../specs/state.md#evaluated-durable-host-input-target-240),
[IO](../../specs/io.md#evaluated-host-input-io-target-240) and
[CLI](../../specs/cli.md#evaluated-host-input-target-240) own answer admission,
settlement, expiration, safe presentation override, invalidation and recovery.
There is no `py resume`, Python continuation store or host mutation during trace.

### Definitions And Symbolic Expressions

Decorators register metadata and the function without running its body.
After import, build resolves annotations with the defining module namespace,
discovers reachable registered definitions, and traces each definition once
using symbolic parameters. Calling a registered definition records a call;
it does not inline or recursively execute its Python function during tracing.
Cycles are diagnosed by the existing compiler. Reachable ignored effectful
calls still make their definitions reachable.

`@workflow` emits `defworkflow`; nested calls emit ordinary workflow `call`.
At 2.39 and later, `@proc` emits `defproc` with omitted `:effects`, using inference.
`@pure` emits `defun`; its body must be pure according to the compiler. Do not
emit `:lowering` at 2.39 or later. `@proc(effects=())` deliberately imposes the existing
empty restriction. Explicit `uses_command(command)` and
`uses_provider(provider)` and `calls_workflow(workflow)` descriptors map to
existing effect clauses with compiler-resolved subjects; at
2.35–2.38 these declarations remain mandatory and exact under their source
target. Emit explicit `:lowering inline` for Python procedures at those older
targets; the compiler's ordinary default is `auto`, not inline. Imported `.orc`
procedures retain their own lowering declaration.

Supported operator overloads map only to existing operators: numeric arithmetic
and ordering, supported equality, and field projections admitted by the
compiler. Generic list indexing is refused because it has no existing source
operator. Explicit helpers cover boolean combination, list length and string
construction: `all_of`, `any_of`, `not_`, `length`, and `concat`. Boolean helpers
with potentially effectful operands take thunks to preserve short-circuiting.
No float equality, implicit mixed-number conversion or new pure operator is
created.

`bool`, `if`, `while`, `and`, `or`, `not`, iteration, `len`, `str`, formatting,
membership and Python collection mutation over symbolic values fail early.
Python protocols cannot overload these into arbitrary symbolic values safely.
Provide a diagnostic naming the corresponding helper. Ordinary Python can
factor **concrete build-time** values; this cannot express runtime branching.

### Branches, Matching And Loops

```python
@record
class Counter:
    count: int

@proc
def describe(attempt: Attempt) -> str:
    return match(
        attempt,
        Completed=lambda c: "completed",
        Blocked=lambda b: b.reason,
    )

@workflow
def bounded(limit: int) -> int:
    return loop(
        state=Counter(count=0),
        max=limit,
        body=lambda s: when(
            s.count >= 2,
            then=lambda: done(s.count),
            else_=lambda: cont(Counter(count=s.count + 1)),
        ),
        on_exhausted=lambda s: s.count,
    )
```

`when(condition, *, then, else_)` requires zero-argument thunks. Each thunk
is traced into its own lexical region; its effects stay in that branch.
Passing eager branch values is an error, including already-recorded effect
results. Both Python thunks run while building, but only the selected generated
branch executes at runtime. Build-time Python IO in either thunk remains author
code and is not made safe by symbolic tracing.

`match(value, Case=lambda payload: ..., ...)` requires exactly the closed case
set; it lowers to `match`, with an arm-local typed payload binder. An arm cannot
leak that binder to another arm or outer scope. Join result types and
exhaustiveness are ultimately checked by the compiler.

`loop(state=..., max=..., body=..., on_exhausted=...)` lowers to bounded
`loop/recur`. Body and exhaustion receive distinct symbolic state binders.
Every body path ends in `cont(next_state)` or `done(result)`; exhaustion returns
the same result type as `done` and is mandatory, including when the bound is
zero. `cont` preserves the declared state type. These controls are only legal
inside the corresponding loop region; nesting preserves ownership. Python
`for`, `while`, and `cont(...) | done(...)` are not control syntax.

The trace representation contains declarations, expression references and
ordered lexical regions. Its job is hygienic source emission, not typechecking,
effect inference, scheduling or execution. Give generated bindings deterministic
local names; never use object addresses, line numbers or global counters as
semantic names. Emit ordered `let*` bindings so reuse and discarded effects have
ordinary `.orc` meaning.

## Modules And The `.orc` Bridge

Each defining Python module owns its declarations. Generated module identities
are `py/<qualified/module/name>`, independent of absolute checkout and output
directory. A file selected relative to a source root uses that same logical
module path; `__main__` and ephemeral import names never become identities.
Emit `<generated-source-root>/py/<qualified/module/name>.orc`, matching the
compiler's module resolver. Imports/re-exports preserve original ownership;
`__all__` selects Python module exports when present, otherwise public registered
definitions are exported. Reject duplicate logical modules and conflicting
provider/command binding names before publication.

```python
library = import_orc("library/review", source_root="workflows")

@workflow
def apply_review(text: str) -> str:
    return library.revise(text)
```

A relative `import_orc(source_root=...)` resolves from the Python file that
declares it. CLI `--source-root` and build/run `source_roots` paths resolve from
the current working directory.

`import_orc` registers a lazy module reference. At build, discover exports and
checked signatures using `compile_stage3_entrypoint` and its
`ModuleExportSurface`, procedure/workflow catalogs and type environment. Do not
parse `.orc` independently or recreate its type/effect inference. Calls emit
ordinary module imports and existing call forms. Imported types and prompts
retain compiler-owned descriptors and owners. Missing/private names fail at
their Python access site. Standard-library modules use the same bridge.

Concrete imported procedures, workflows, types and prompts must work. Existing
generic type application is expressed by subscripting a type handle, e.g.
`library.Decision[Notes, Blocker]`, and emits the existing applied type syntax;
the `.orc` compiler resolves its constraints. Imported callable specialization
is admitted only through a concrete signature that the existing compiler can
resolve; runtime Python callbacks or arbitrary generic Python functions do not
become ProcRefs. Do not advertise automatic support for every stdlib combinator.

## Build, Check, Run And Frozen Inputs

```python
artifact = build(
    "workflows/review.py", entry_workflow="draft",
    provider_externs_file="providers.json",
)
result = run(
    "workflows/review.py", entry_workflow="draft",
    provider_externs_file="providers.json",
    inputs={"task": "Describe the migration"},
)
```

```sh
orchestrator py build workflows/review.py --entry-workflow draft --provider-externs-file providers.json
orchestrator py check workflows/review.py --entry-workflow draft --provider-externs-file providers.json
orchestrator py run workflows/review.py --entry-workflow draft --provider-externs-file providers.json --input task="Describe the migration"
orchestrator py run workflows/review.py --entry-workflow draft --provider-externs-file providers.json --frozen
orchestrator resume RUN_ID
```

The source file and `entry_workflow` select the definition using existing entry
selection rules; one exported workflow may be selected implicitly. There is no
additional `file:member` locator or live-object build API. Existing source-root,
provider-externs, prompt-externs and command-boundaries file options remain the
binding authority, with corresponding underscore-spelled Python keywords.
Source-backed local modules are required. A fresh isolated worker imports and
traces the source; the
loader compiles the exact bytes it records, without using stale `sys.modules`
or timestamp-based `.pyc` caches. All project-local Python imports read through
this source-byte loader. Installed dependencies retain normal import behavior.
Import or tracing
exceptions become named frontend errors retaining their Python traceback and
source location. The worker returns only generated paths, source-map and
capture metadata; it does not serialize `TypedProgram` or use pickle. The parent
process performs existing closed compilation. Build is not a
hermetic Python environment; environmental IO and hidden dynamic inputs are
unsupported reproducibility inputs, not a sandbox guarantee.

The Python API uses `source_roots=(...)` for ordered additional roots and
`workspace_root=...` for build/check publication. Public run executes in the
current working directory, following the ordinary run owner's workspace rule.

Generation captures Python inputs and prompt files, emits source, preserves
copies of supplied binding manifests, and calls `build_closed_program_bundle` with an
ordinary `FrontendBuildRequest`. `build` returns the entry `.orc` path, generated
source root, source-map path, manifest paths, ordinary closed artifact path,
`build_key` and `program_digest`. No second runtime artifact schema is created.
Manifest snapshots preserve their existing binding meaning and cannot invent
defaults or broaden command/provider authority.
`check` performs the same trace and compiler validation without effects or
updating the frozen pin. CLI exit 2 denotes authoring/compile/frozen refusal;
`run` retains existing exit 0/1/2 semantics and `RunWorkflowResult`.
Python API calls propagate named frontend/compile exceptions for build failures;
`run` returns `RunWorkflowResult` after delegation to the ordinary runtime.

Keep each successful generated source/configuration snapshot in an immutable
directory under `.orchestrate/python/`, keyed by a digest of captured inputs
and emitted content. Do not overwrite files used by an existing run. A small
entry-specific pin records the ordinary closed `build_key`, generated snapshot
and frontend format version. Normal `build`/`run` may atomically update that pin
after successful compilation; `--frozen` requires a pin, rebuilds current source
without replacing it, and refuses a changed or missing input/configuration.
There is no implicit success when no prior build exists.

Frozen comparison covers the captured local Python sources, prompt bytes,
transitive `.orc` sources and manifests, in addition to the existing closed
build key; Python edits that emit identical `.orc` are still source changes.
It does not freeze runtime command closures or workspace inputs: their existing
runtime freshness and replay rules remain binding. The immutable snapshot also
contains imported project-local `.orc` source and source-owned prompt assets
needed to rebuild the ordinary entry, with logical module paths and
asset-relative layout preserved. Packaged stdlib remains in the compiler's
installed root: copying it into another source root creates ambiguous imports.
Record its consumed source hashes for frozen comparison and retain normal
compiler/package drift checks on resume; do not claim the installation is
immutable. Runtime `input_file` prompts remain workspace-relative. Retain the
ordered source roots in the run recipe, reject duplicates, and never resolve an
import against the generator's incidental current directory. Use compiler read
traces and resolved asset bindings to capture this dependency graph; copying
arbitrary directories is not the contract.

`run` forwards the generated entry, roots, manifests and user inputs to existing
`run_workflow`, retaining workspace locks, validation and output contracts.
The saved ordinary run recipe references the retained snapshot. Resume does
not import Python or reconstruct a workflow from Python state. It uses the
existing recompile/digest, closure-evidence and memo contract. There is no promise
that editing a workflow preserves old effect identities or allows old runs to
resume; formatting-only provenance changes and exact checked-program identity
follow the compiler's existing rules.

## Source Maps And Diagnostics

Every emitted declaration, call and expression range maps to its Python
file/line/column and owning function; synthetic wrappers map to their owning
declaration. Missing fine-grained positions may use the function's declaration
span, but must not invent a location. Include captured source hashes and emitted
`.orc` ranges in a versioned `source-map.json` sidecar.

The sidecar belongs to the Python frontend. Evaluated `compile --emit-source-map`
is currently refused; this design does not reopen that historical emitter.
Compose compiler diagnostic `.orc` spans with this sidecar to show a Python
primary location and retain the original diagnostic code, generated location,
notes and import context. Unmapped imported `.orc` errors keep their real source
location. Generated source remains directly inspectable and compilable.
Runtime memo/site authority is unchanged; a Python source location may be an
additional display note, never a replacement identity.

## Implementation Boundaries And Acceptance

Keep the public exports in `orchestrator/py/__init__.py`, with only the modules
needed for declarations/tracing, emission and build/import/diagnostic handling.
The CLI group lives under `orchestrator/cli/commands/` and delegates to this API.
Reuse existing string escaping, diagnostics, manifest readers and run defaults
where available. Do not introduce dependencies, a new scheduling layer,
provider adapters or a second semantic type checker. No arbitrary line-count
ceiling substitutes for completing the contracts.

The implementation handoff has four substantive boundaries, all required:

1. Typed declarations, prompts, provider calls, straight-line tracing and
   compiler-checked source emission, including forward references.
2. Reusable procedures/pure functions, commands, branch regions, matching,
   bounded loops and explicit exhaustion.
3. Stable module ownership, `.orc` bridge, durable generation, diagnostics,
   frozen comparison, Python API and public CLI through the existing runtime.
4. Independent review and public command-only integration/recovery evidence,
   authoring guide/examples and documentation routing updates.

Required checks are behavioral and contractual, never literal prompt text:

- Compile valid/invalid declarations, mismatched results, invalid enum values,
  duplicate ownership, unsupported signatures and symbolic Python coercions.
- Build twice after a source edit with unchanged size/mtime and after module
  caching; compile captured current bytes. Exercise cross-module forward
  references and imported types with identical short names.
- Run a real local command workflow with a branch and bounded loop through
  `orchestrator py run`; verify result values, command counts and ordering.
  An unselected arm must produce no command attempt, and ignored calls in the
  selected arm must still execute. Include zero-budget exhaustion.
- Interrupt after a committed command, resume with ordinary `orchestrator
  resume`, and verify no repeated committed call. Repeated completed resume is
  read-only under the existing authority contract. Change or remove the
  original Python sources before resume to prove the retained `.orc` recipe
  never reimports Python.
- Build/import a real source library with a concrete procedure, workflow and
  nominal type; include an applied generic type where used. Relocate the source
  tree and repeat with stable logical module identity. Missing/private exports
  and old targets must fail normally.
- Frozen runs reject edits to Python, inline/file prompts, transitive `.orc`
  sources or bindings; missing pin refuses, failure does not replace the pin,
  and ordinary runs still retain their original generated files.
- A generated `.orc` program and a hand-authored mirror with the same declared
  module/definition/type names and configuration have identical compiler
  `program_digest` and effect sites. Use the existing digest and provenance
  handling; never recursively strip arbitrary `@` fields or semantic names.
  Separate behavioral parity tests may compare differently named programs.
- At explicit target 2.40, run a provider diagnosis, command verification, ask
  and conditional action through the real public lifecycle. Cover String,
  enum and closed-union answers; inferred and explicit-empty effects; typed
  Value/Doc/show inputs; prompt-file freeze versus runtime Doc divergence;
  source deletion before settlement/resume; original/generated attribution;
  serial loop visits and imported asking procedures. Test body-only ask,
  old-target refusal, and a default-2.39 star import. Exercise all four host
  outcomes, crash/reply race boundaries and exact dispatch counts using local
  stand-ins. Source maps remain diagnostic evidence, never memo/site authority.
- Diagnostics name the Python call/declaration and preserve the original `.orc`
  location and compiler code. An imported `.orc` failure remains attributable.

Compilation and command-only evidence do not qualify live providers. No paid
provider invocation is required for this frontend's implementation checks.

## Implementation Evidence And Limits

The serial implementation is exercised by the declaration, control, procedure,
import, build and public CLI/recovery checks named in the
[implementation plan](../plans/2026-10-22-python-workflow-frontend-plan.md).
That plan owns the serial frontend evidence; the [host-input delivery
plan](../plans/2026-10-22-durable-host-input-plan.md) owns the additional
target-2.40 host integration evidence and acceptance checks. The [authoring guide](../python_workflow_drafting_guide.md)
provides the maintained local command recipe. Evidence is limited to compilation
and local deterministic commands, without live-provider or editor qualification.

### Original Feasibility Probes

The existing compiler was exercised directly with temporary ordinary source,
without production implementation or provider calls:

- Target-2.39 inferred and explicitly pure procedures, record loop state,
  `continue`/`done`, explicit exhaustion and union `match` compiled to a closed
  program successfully.
- A library-only module with an exported procedure compiled through
  `compile_stage3_entrypoint`; its exported canonical binding and resolved
  parameter/return signature are available without requiring an entry workflow.
- A `defprompt` owning its return type and a `provider-result` application
  compiled to one ordinary provider site with an existing provider extern.

These preimplementation probes established target-lowering and catalog
feasibility only; they were not implementation evidence for the Python tracer,
source map or freeze mechanism. Existing owner tests include
`test_workflow_evaluated_loops.py`, `test_workflow_evaluated_providers.py`,
`test_workflow_lisp_closed_program_names.py`, and the public CLI/resume suites.
The implementation plan tracks the public cross-boundary checks above.

`parallel_map` is deferred because the runtime's bounded parallel admission and
qualification do not justify a broad Python parallel API. `Agent` is deferred
because session lifetime, capability and recovery need their own faithful API;
it must not masquerade as ordinary `Provider`. Neither omission limits the
serial workflow, procedure, branch or loop contracts in this design.

Python imports and tracing execute trusted local code with the caller's
permissions, including during `check` and `--frozen`. These commands do not
sandbox code or certify the absence of build-time side effects. Durable
effects belong in `Provider`/`Command` so the existing runtime can own them.

The documentation hub, design index, capability matrix and
[CLI contract](../../specs/cli.md#python-authoring-frontend) route to the
implemented subset. Preserve ordinary `.orc` entrypoints and existing run data;
there is no migration or deletion of the Lisp frontend.
