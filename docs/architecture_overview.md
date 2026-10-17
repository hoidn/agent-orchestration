# Architecture Overview

`agent-orchestration` is a compiler and runtime for agent-driven work written
in Workflow Lisp (`.orc`). Workflows are contracts over state, artifacts,
provider calls, command calls and control flow. For the fuller model and
glossary, read [Orchestration Start Here](orchestration_start_here.md).

## One-Screen Model

```text
authored Workflow Lisp source (.orc)
        |
        v
compiler: parse, check, admit for the declared target
        |
        v
flat Core + IR (typed through 2.34) | closed program (typed 2.35/2.36) | dynamic program (native 3.0)
        |
        v
runtime execution
        |
        v
run state, logs, artifacts, reports, and resume evidence (typed profiles)
```

The `(:target-dsl ...)` declaration selects the profile:

- **Typed flat, through 2.34**: lowers through shared validation, Semantic IR,
  Executable IR and source maps to the step runtime. Checked state; resume.
- **Typed evaluated, 2.35/2.36**: compiles a checked closed program and
  evaluates it with lexical values and a memo of committed effects. Resume and
  suffix invalidation; forms outside the admitted subset refuse at build.
- **Native, 3.0**: ordinary functions, closures and real imports inside one
  sequential run, with strict schemas at workflow, prompt and command
  boundaries. Runs are fresh-only: no resume, retries or result reuse.

[Versioning](../specs/versioning.md) defines each profile; the
[capability matrix](capability_status_matrix.md) shows what each one admits.

## What Is Authoritative?

Normative behavior lives in `specs/`, especially:

- [DSL](../specs/dsl.md)
- [Step IO](../specs/io.md)
- [Providers](../specs/providers.md)
- [State](../specs/state.md)
- [Versioning](../specs/versioning.md)

Within a run, structured state, validated result bundles, typed variants,
validated artifacts and source-mapped program nodes decide routing, resume,
publication and terminal status.

## What Is A View?

Reports, markdown summaries, stdout, prompt audits, pointer files and
dashboards are views unless a specific contract makes one of them the artifact
value. `expanded.debug.yaml` is a JSON-rendered debug projection despite its
name; it is also a view and is never parsed as source. A view can explain a
decision, but control flow comes from validated state and contracts.

## Why Files?

The runtime exposes durable filesystem artifacts so that:

- runs can be inspected after process death, and typed runs resumed;
- provider and command outputs have stable evidence paths;
- workflow steps can consume validated artifacts instead of transient process
  memory;
- downstream tools can inspect the same state the runtime uses.

Files are storage and evidence. They must not become unvalidated hidden state
or ad hoc pointers that replace structured workflow values.

## Why Types?

Typed results, variants and contracts prevent common workflow mistakes:

- a review decision is distinct from a report;
- a tagged outcome must prove its variant before variant-specific values are
  used;
- command and provider outputs are validated before they become canonical
  state.

Typed profiles check these before execution. Native 3.0 validates declared
boundaries and checks internal operations when they run.

## Why Workflow Lisp?

Workflow Lisp is the only authoring frontend. It makes high-level, reusable
composition easy to write without moving authority out of the runtime's
validated state. If a needed form is not available for your target, record the
gap rather than writing a lower-level or YAML workaround. Retired YAML/YML
sources cannot run.

## Next Reading

- [Documentation Index](index.md): find the right spec, guide or design doc.
- [Capability Status Matrix](capability_status_matrix.md): check whether a
  surface is implemented, partial, library-provided, designed, future or legacy.
- [Workflow Lisp Drafting Guide](lisp_workflow_drafting_guide.md): author `.orc`
  workflows.
- [Design Documentation Index](design/README.md): find architecture and
  feature designs.
- [Documentation Conventions](documentation_conventions.md): rules for
  maintained docs.
