# Python Authoring For Evaluated Workflows

- **Kind:** frontend architecture and bounded authoring contract
- **Target:** DSL 2.40, emitted through the existing Workflow Lisp compiler
- **Runtime owner:** [evaluated execution](workflow_lisp_evaluated_execution.md)
- **Host input owner:** [durable host input](workflow_lisp_durable_host_input.md)

This design selects the Python authoring subset needed for typed
diagnose/approve/recover workflows. Implementation status and evidence belong
in the implementation plan. Python `ask` is native authoring in this subset;
it does not call the external `orchestrator.host_input.answer` API or block a
Python process waiting for a person.

## Decision And Owners

Add `orchestrator.py` as a Python package with public exports in
`orchestrator/py/__init__.py`. Its tracer records a small typed expression and
declaration graph, emits ordinary `.orc`, and submits that source plus supplied
ordinary extern manifests to `workflow_lisp/closed/artifact.py`'s
`build_closed_program_bundle(FrontendBuildRequest(...))`. That owner already
calls `closed/frontend.py:compile_typed_program_with_result` and produces the
checked closed program. Do not call a retired compiler route, generate YAML,
construct unchecked runtime nodes, or add a Python executor.

```text
Python declarations → trace once at build → immutable .orc + supplied manifests
  → existing frontend/type/effect checks → checked closed program
  → existing run/memo/host settlement/resume
```

Keep tracing/emission in `orchestrator/py/`, CLI argument adaptation in
`cli/commands/python.py`, and shared compilation/run behavior in its existing
owners. A separate generic graph library, frontend registry, plugin protocol,
Python checkpoint format or Python-specific provider adapter is unnecessary.
The Python declaration graph is build-time data, never execution authority.

The ordinary Lisp compiler is the final type/effect authority. Python validates
unsupported authoring constructs early and supplies useful source locations;
it does not duplicate all compiler validation. This choice makes arbitrary
Python control flow, dynamic imports during resume and Python object identity
unavailable as durable workflow semantics.

## Selected Public Surface

The package exports these functional surfaces, all backed by emitted Lisp:

| Python | Meaning |
| --- | --- |
| `@workflow(returns=T)` | Declares an exported workflow with annotated inputs and explicit result |
| `@proc(returns=T, effects=...)` | Declares a reusable typed procedure; omitted effects infer, explicit effects restrict |
| `@record` | Declares a closed record from annotated fields |
| Python `Enum` | Declares a closed enum from string-valued members |
| `@variant` and `A | B` / `typing.Union` | Decorated variant classes provide closed payloads; a named union alias declares their union |
| `RelPath` subclasses | Declare named typed path contracts; `PathOf[T]` is a prompt fill descriptor |
| `Prompt(text=... or file=..., fills=..., returns=...)` | Declares a typed prompt with named fill descriptors `Text`, `Doc`, `Value`, `PathOf`, `Out` |
| `Provider`, `Command` | Refer to extern names; manifests remain the only binding authority |
| `host_input`, `uses_provider(name)`, `uses_command(name)` | Build explicit effect restrictions for `@proc(..., effects=[...])` |
| `match` | Exhaustive variant/enum match using lazy branch callbacks |
| `when` | Lazy conditional with `then` and `otherwise` callbacks |
| `ask` | Emits target-2.40 `request-input`; returns symbolic `HostReply[A]` |
| `build` | Traces and compiles a selected workflow, returning the generated source and checked build result |

Return annotations may be accepted as shorthand for `returns=`, but conflicting
annotations/decorator arguments fail rather than silently choosing one. Effects
are omitted by default; `effects=[]` is a pure restriction and
`effects=[host_input]` admits the subject-free effect. Provider/command effect
constructors emit their ordinary subject-bearing restrictions.

Python `str`, `int`, `float`, `bool` and `list[T]` annotations map to the
corresponding supported Lisp descriptors. A concrete Python `None` is not an
implicit option value. There is no implicit conversion of symbolic values to
strings or paths. `HostReply` is an imported/reexported descriptor for
`std/host::HostReply`, not a second Python-named union definition.

`@proc`/`@workflow` decorators register declarations and retain their callable
bodies without running them. Trace begins only at explicit `build` or CLI check/build/run,
after the source module has finished importing. Forward references to helpers
declared later in the module therefore work. The build discovers reachable
procedure declarations, traces each once with typed symbolic parameters and
emits definitions plus call expressions. Recursive call graphs retain the
ordinary compiler's refusal; a Python recursion must not occur while tracing.

Ordinary undecorated helpers may compose expression builders during tracing.
They are executed as build-time Python and inlined into their caller's emitted
body; they have no durable call-frame identity. Authors use `@proc` when they
need a reusable emitted procedure and its ordinary call/site attribution.

## Concrete Approval Flow

The following is the selected call shape. Provider/command setup supplies the
same bindings that the Lisp example supplies in manifests.

```python
from enum import Enum
from orchestrator.py import workflow, proc, record, Prompt, Text, ask, match, HostReply

class Approval(Enum):
    APPROVED = "APPROVED"
    DENIED = "DENIED"

@record
class Diagnosis:
    summary: str

@record
class Outcome:
    status: str

approval_question = Prompt(
    text="Approve this recovery? {summary}",
    fills={"summary": Text},
    returns=Approval,
)

@proc(returns=HostReply[Approval])
def approval(diagnosis: Diagnosis):
    return ask(approval_question(summary=diagnosis.summary), returns=Approval,
               timeout_sec=86400)

@workflow(returns=Outcome)
def diagnose_recover(problem: str):
    diagnosis = diagnose(problem)
    reply = approval(diagnosis)
    return match(
        reply,
        ANSWERED=lambda answer: match(
            answer.value,
            APPROVED=lambda _: repair(diagnosis),
            DENIED=lambda _: escalate("denied"),
        ),
        CANCELLED=lambda _: escalate("cancelled"),
        EXPIRED=lambda _: escalate("expired"),
    )
```

`diagnose`, `repair` and `escalate` are ordinary annotated `@proc` declarations
in the complete example, backed by `Provider`/`Command` declarations. The
example above omits only those binding-specific definitions, not a second
runtime mechanism. The maintained runnable example must include them and its
recording stub provider/command fixtures.

Provider and command call shapes are:

```python
diagnoser = Provider("providers.diagnoser")
repair_command = Command("repair", returns=Outcome)

# In a traced procedure:
diagnosis = diagnoser(diagnose_prompt(problem=problem))
outcome = repair_command("python", "repair.py", diagnosis.summary)
```

These objects name existing externs; they do not emit source default bindings,
provider models or command closures. Build/CLI callers supply ordinary provider,
prompt and command manifests as required by the referenced externs. Command
calls emit the full authored argv; the command manifest declares its matching
stable command and mandatory explicit closure, including when empty. The
provider result type comes from the applied prompt's declared return contract.
Manifest validation, path safety,
closure hashing and dispatch belong to existing compiler/runtime owners.
Provider declarations do not make a live provider available or qualify it.
Provider calls accept the existing `model`, `effort` and `timeout_sec` keyword
arguments and emit their corresponding `provider-result` options. These are
per-call policy values, including typed symbolic operands where Lisp admits
them; they never supply an extern binding or a source-level provider default.

`ask(question, *, returns, timeout_sec=None, show=())` accepts a Python string,
symbolic string or fully applied typed prompt. Omitted/`None` timeout means no
deadline; a supplied timeout emits the same positive integer operand as Lisp.
`show` is a Python tuple/list of symbolic typed file paths emitted as the Lisp
`:show` operand list. It has exactly the host-input design's answer admission,
effect inference, validation, persistence and parallel/child restrictions.

## Symbols, Branches And Declarations

Declare paths with ordinary subclass keywords, for example
`class EvidencePath(RelPath, under="artifacts/daq", must_exist=True): ...`.
`under` is the authored relative path root and `must_exist` is a boolean;
the declaration emits the existing `defpath :kind relpath` contract and its
`:under`/`:must-exist` options. Path construction emits a typed path value;
it does not perform filesystem IO during tracing. The ordinary compiler and
runtime retain path validation and existence checks.

Symbolic record fields emit field access; constructing a decorated record emits
a typed record value. Enum wire tokens are their string `.value`, which must be
distinct, nonempty and valid enum tokens. Python member names select constants
and enum `match` keyword branches, then map explicitly to those wire tokens.
Thus `FaultClass.TIMEOUT = "timeout"` emits token `timeout`, not `TIMEOUT`.
Enum aliases are refused by checking all `__members__`, including aliases,
rather than silently dropping them during iteration. Declaring a union is
finite and explicit:

```python
@variant
class ACCEPT:
    reason: str

@variant
class REJECT:
    reason: str

Decision = ACCEPT | REJECT
```

`ACCEPT(reason="ok")` emits the corresponding constructor in its declared union.
Membership comes from the explicit named union alias (`A | B` or
`typing.Union[A, B]`), not class inheritance
or unrelated classes. Reject ambiguous membership in more than one emitted
union in this bounded subset; the author must use distinct variants.
Generic user-defined records/unions, inheritance and
arbitrary Python objects are outside this subset; imported `HostReply[A]` has
its existing ordinary first-order generic descriptor.

`match(value, TAG=callback, ...)` requires each admitted tag once, no unknown
tag and one callback parameter. For a union the parameter has only that tag's
payload fields; for an enum it is the symbolic selected member. Each callback
is invoked once during build into an isolated branch buffer. Effects in that
buffer become effects in only that emitted branch. Results must have a common
admitted type; the existing compiler checks exhaustiveness and refinement.

`when(condition, then=lambda: expr, otherwise=lambda: expr)` likewise traces
each zero-argument callback into its own branch. Eager expressions passed as
branches are refused. Python call evaluation would otherwise trace both effects
before the branch exists, changing the workflow. `match` also refuses noncallable
branch values rather than accepting previously emitted effects.

The trace records effect operations as ordered bindings, preserving Python
left-to-right evaluation within a procedure/branch. Calling a traced `@proc`
emits a call; it does not execute that procedure's body into the caller. Names
and site labels derive from deterministic declaration/operation order, never
Python `id()`, process hash order, clock time or filesystem traversal order.

Symbolic `__bool__`, `__iter__`, `__len__`, `__str__` and formatting fail with a
located authoring diagnostic. Unsupported equality, ordering, arithmetic and
other operators also fail explicitly: notably `__eq__`/`__ne__` must not fall
back to Python object-identity booleans. No symbolic operator is advertised by
this subset; typed enum/union selection uses `match`. Native `if`, `and`, `or`,
loops, comprehensions,
`len(symbol)`, `str(symbol)` and f-strings cannot silently inspect runtime data.
Do not claim every Python side effect is intercepted: ordinary Python executes
when importing and tracing trusted author code. File/network/process operations
there are ordinary build-time Python, outside workflow durability. Authors must
express runtime work through the declared effect builders. No sandbox or
arbitrary-Python replay promise is introduced.

## Prompts And Generated Source

`Prompt(text=template, fills={...}, returns=...)` emits a normal `defprompt`.
`Text` maps to `:text`; `Doc[PathType]` to `:doc`; `Value[Type]` to `:value`;
`PathOf[PathType]` to `:path`; `Out[PathType]` to the existing admitted
output-position contract. Exactly one of `text` and `file` is required. The declared fill names must match the fully applied
keyword arguments. Use existing compiler rendering/type rules, not Python
`format`, string interpolation or ad hoc file reads of symbolic values.

`Prompt(file=path, fills=..., returns=...)` reads a UTF-8 authoring template at
build time and embeds its exact template bytes in the emitted `defprompt`.
It is an authoring-file snapshot, unlike a runtime `Doc` fill. Rebuilding after
editing that template creates a new generated source identity; resuming an
existing run uses its frozen emitted template. Runtime `Doc` file contents
retain the ordinary content-bound input/replay semantics. No source file is
opened merely because a prompt argument happens to contain a path-like string.

`build` emits a content-addressed bundle beneath
`.orchestrate/generated/<module>/<digest>/`: entry `.orc` and a
Python-to-generated-source map. Explicit supplied extern manifests remain
ordinary build inputs and retain their existing mutation/resume semantics;
there is no generated provider/default binding manifest. The digest covers
emitted source, canonical source-map bytes, emitter schema/version and any
authoring template snapshots. Source-map filenames are workspace-relative, so
adding source lines changes this bundle identity without introducing absolute
paths or falsely colliding with an older map. It does not depend on timestamps
or absolute workspace paths. The supplied manifest paths are passed unchanged
through the normal build request.

Publish all files via a temporary sibling directory, fsync files and directory,
and atomically install the final digest directory. If that destination already
exists, verify its exact expected bytes before reuse; never overwrite divergent
content. Reject symlinks and paths outside the established workspace generation
root. A failed compiler check may leave a complete generated source bundle for
diagnosis, but no run authority or provider work. Partial bundles are never
selected. Generated source is an ordinary retained build input, not an opaque
cache that cleanup may remove while runs reference it.

The generated source module and workflow names are deterministic. Generated
bindings lower through normal typed source and are source-mapped by the existing
compiler. The supplementary source map associates generated ranges with the
Python filename, definition and source line captured during trace. Initial
diagnostics retain both locations when available; if exact expression columns
cannot be proven, report the enclosing Python line/definition rather than
inventing precision. Nested branch/procedure errors must remain attributable.
This map is diagnostic evidence, not a semantic authority used to resume.

## CLI And Resume

```sh
orchestrator py check workflow.py --entry-workflow diagnose_recover
orchestrator py build workflow.py --entry-workflow diagnose_recover
orchestrator py run workflow.py --entry-workflow diagnose_recover --input-file inputs.json
orchestrator input get RUN_ID
orchestrator resume RUN_ID
```

The file argument imports trusted Python once for that invocation, then
`--entry-workflow` selects its decorated workflow. Without a selector, exactly
one exported workflow is required. `build(workflow, *, workspace=None,
provider_externs_file=None, prompt_externs_file=None,
command_boundaries_file=None, source_roots=())` uses the same explicit manifest
inputs as the CLI; its default workspace is the current directory. `check`
traces/emits and invokes the ordinary compiler without starting a run; it may publish generated/build
artifacts. `build` also prints generated source paths, supplied manifest paths,
entry workflow and checked program/build digests. `run` adapts the completed build's
source/manifest paths into the ordinary evaluated run entrypoint. Existing
runtime input/state-directory/provider options retain their meanings; they are
not reimplemented as a second execution configuration layer.

The ordinary run header records the generated `.orc` and manifest paths as its
rebuild recipe. `resume RUN_ID` uses that recipe and the existing fresh compile
and digest comparison before loading memo. It never imports the original Python
module, invokes decorators, traces code, or chooses a new generated directory.
Editing or removing original Python source or an authoring `Prompt(file=...)`
template cannot change an existing run; editing generated source/manifests is
detected by the ordinary rebuild/program-identity checks. Missing retained
generated inputs fail closed. Runtime document or provider input files retain
their existing replay divergence rules; this design does not freeze arbitrary
workspace contents. Changing `.orc` source is `resume_program_changed` (or its
compile refusal), while changing a bound runtime document can be
`effect_input_diverged`.

There is no `py resume`, Python stack serialization or call to host answer from
inside tracing. Host settlement uses the public API/CLI in the companion design.

## Bounded Exclusions And Verification

The subset does not export placeholder names for Python-native loops, arbitrary
pure evaluation, generators/async workflows, exceptions as workflow control,
agents, resource transitions, child `run-ref`, parallel maps or direct IR APIs.
Those require their own authoring contracts. Existing Lisp workflows retain
their independently admitted features. Every name advertised above must work
through emitted source; an unsupported type/option fails clearly at build.

Before accepting the frontend, a small executable fixture must prove that a
traced `@proc` returning `HostReply[Approval]`, a lazy typed `match`, a provider
diagnosis and a command continuation compile through the real closed-program
builder. This is a required implementation feasibility check, not a claim that
the nonexistent Python frontend is already proven. If that shape requires new
semantics below the emitter beyond the accepted host-input effect, revise this
design before expanding the frontend.

Tests must cover declaration-before-helper ordering, deterministic repeated
builds, comment/line-only edits with correct source-map identity, exact
output-directory reuse/corruption refusal, typed fills, closed
union construction, source-located errors, symbolic truth/string/iteration/equality
refusal, and lazy branch isolation. Test both a handwritten `.orc` fixture and
native Python diagnose/recover through public run, pending, answer/cancel and
resume with scripted providers. Assert the same semantic outcomes and call
counts for APPROVED, DENIED, CANCELLED and EXPIRED; program digests need not be
identical because nominal/source identities differ. Delete/change the original
Python file before resume to prove it is not imported. Preserve declaration,
effect, request and original/generated source attribution in the test report.

No live provider spend is required. Document the selected API, trusted build-time
Python model, prompt snapshot distinction, retained generated inputs and native
approval example in a dedicated authoring guide and route it from the docs and
workflow indices. Do not advertise the deferred full Python language proposal.
