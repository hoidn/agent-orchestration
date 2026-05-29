# Workflow Lisp Frontend MVP Specification

Status: draft MVP
Parent architecture: `docs/design/workflow_lisp_frontend_specification.md`
Target substrate: v2.14+ Core Workflow AST and existing runtime
Primary purpose: prove that a non-YAML frontend can reduce brittle workflow
authoring without building the full language at once

## 1. Scope

This MVP is the smallest useful implementation of the Workflow Lisp frontend.
It intentionally does less than the full frontend specification.

The MVP must prove four things:

1. A Lisp source file can compile to the same Core Workflow AST used by YAML.
2. Typed records and unions can express workflow inputs, outputs, and provider
   results without manual pointer/state-path boilerplate.
3. `match` can provide variant-proof contexts for variant-specific fields.
4. One real workflow phase can be translated with less brittle authoring
   surface than the equivalent v2.14 YAML.

The MVP is successful only if it improves semantic authoring quality, not merely
if it parses S-expressions.

## 2. Relationship To The Full Specification

The full Lisp frontend specification remains the north-star architecture.
This MVP narrows it into an implementation tranche.

Keep from the full spec:

- direct lowering to Core Workflow AST, not YAML text;
- structured state as semantic authority;
- reports as views;
- artifact values as authority;
- typed variants and proof by `match`;
- source spans for diagnostics;
- shared v2.14 validation after lowering.

Defer from the full spec:

- user-defined `defmacro`;
- hygienic macro system;
- general effect graph;
- higher-order workflow refs;
- full module/import/export system;
- generic `defproc` lowering choices;
- runtime-native resource transitions;
- full Semantic IR and Executable IR serialization;
- debug YAML renderer;
- legacy adapter framework.

These deferred pieces are not rejected. They become eligible after the MVP
proves the frontend is worth extending.

## 3. Non-Goals

The MVP must not:

- replace the runtime;
- create a second execution engine;
- emit YAML as the authoritative target;
- parse markdown reports to recover semantic fields;
- hide provider, command, state, or filesystem effects;
- support arbitrary Lisp evaluation;
- support runtime code loading;
- support user-defined macros;
- support dynamic workflow references;
- migrate the full NeurIPS backlog drain stack.

## 4. MVP Language Surface

### 4.1 File Form

MVP source files use `.orc`.

Every file has one workflow module header:

```lisp
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  ...)
```

The MVP does not implement general modules. The file is one compilation unit.
Names are local to that file plus the fixed MVP prelude.

### 4.2 Definitions

Supported definitions:

```lisp
(defenum Name value ...)
(defpath Name :kind relpath :under "..." :must-exist true|false)
(defrecord Name (field Type) ...)
(defunion Name (VARIANT (field Type) ...) ...)
(defworkflow name ((arg Type) ...) -> ReturnType body)
```

Unsupported in MVP:

```lisp
defmacro
defproc
defun
import
export
WorkflowRef
loop/recur
resource-transition
backlog-drain
```

Pure helper logic is deliberately small in the MVP. If a translation needs
complex computation, keep that computation in an existing command/helper and
call it through `command-result`.

### 4.3 Expressions

Supported expressions:

```lisp
(let* ((name expr) ...) body)
(match union-value ((VARIANT binding) body) ...)
(call workflow-name :arg value ...)
(provider-result provider-ref :prompt prompt-ref :inputs (...) :returns UnionType)
(command-result name :argv (...) :returns RecordOrUnionType)
(record Type :field value ...)
field.access
string/int/bool literals
```

The MVP may omit general arithmetic, string concatenation, and arbitrary
conditionals. Authoring should stay declarative and typed.

### 4.4 Built-In Forms

The MVP may include compiler-owned built-ins, but they are not user macros.

Allowed built-ins:

- `with-phase`
- `phase-target`
- `provider-result`
- `command-result`

These forms must lower through fixed, reviewed compiler code. They may not be
implemented as user-extensible macros in the MVP.

## 5. Type Model

### 5.1 Primitive Types

Required primitive types:

```text
String
Int
Bool
Json
Provider
Prompt
```

### 5.2 Path Types

`defpath` defines a reusable relpath contract.

Example:

```lisp
(defpath WorkReport
  :kind relpath
  :under "artifacts/work"
  :must-exist true)
```

Path values are artifact/path values, not pointer-file paths.

MVP path validation reuses the existing path-safety and contract-refinement
checks after lowering.

### 5.3 Records

Records are product types used for workflow inputs, command results, and fixed
output bundles.

Example:

```lisp
(defrecord ChecksResult
  (checks-report CheckReport)
  (status String))
```

### 5.4 Unions

Unions are tagged outcome types.

Example:

```lisp
(defunion ImplementationAttempt
  (COMPLETED
    (execution-report WorkReport))
  (BLOCKED
    (progress-report WorkReport)
    (blocker-class BlockerClass)))
```

Variant-specific fields are available only inside a `match` arm for that
variant.

## 6. Lowering Contract

The MVP compiler lowers:

```text
.orc source
  -> parsed S-expression tree with source spans
  -> typed frontend AST
  -> Core Workflow AST
  -> existing shared validation
  -> existing runtime execution path
```

YAML is not part of the authoritative pipeline.

An optional debug rendering may be added later, but the MVP should not spend
implementation time on a debug YAML renderer.

## 7. Provider And Command Results

### 7.1 `provider-result`

`provider-result` is the MVP's primary proof point.

Example:

```lisp
(provider-result providers.execute
  :prompt prompts.implementation.execute
  :inputs (inputs.design inputs.plan)
  :returns ImplementationAttempt)
```

Lowering requirements:

- generate a provider step;
- inject a structured output contract derived from the return type;
- validate the provider's structured bundle with `variant_output` when the
  return type is a union;
- validate with `output_bundle` when the return type is a record;
- expose typed artifacts only after validation succeeds.

MVP providers must produce structured JSON state. Markdown reports may be
referenced by fields in that JSON, but markdown is not parsed for semantic
state.

### 7.2 `command-result`

`command-result` wraps existing deterministic scripts.

Example:

```lisp
(command-result run-checks
  :argv ("python" "scripts/run_checks.py" "--out" inputs.checks-report-target)
  :returns ChecksResult)
```

Lowering requirements:

- generate a command step;
- require structured output validation;
- expose the record/union typed result only after validation succeeds.

No arbitrary stdout parsing is allowed unless the command's output contract is
already structured.

## 8. Variant Proof

`match` is required for variant-specific access.

Valid:

```lisp
(match attempt
  ((COMPLETED c)
    c.execution-report)
  ((BLOCKED b)
    b.progress-report))
```

Invalid:

```lisp
attempt.execution-report
```

Lowering must preserve the proof in the Core Workflow AST using existing
variant availability rules, such as `match` or `requires_variant`.

## 9. Source Spans And Diagnostics

The MVP does not need full source-map artifacts.

It must preserve enough source information for diagnostics:

- file path;
- line;
- column;
- enclosing form name;
- generated Core AST node id.

Minimum diagnostic example:

```text
variant_ref_unproved at workflows/foo.orc:42:9
  field: attempt.execution-report
  reason: field is available only for ImplementationAttempt.COMPLETED
  hint: access it inside (match attempt ((COMPLETED c) ...))
```

Full expansion stacks and macro hygiene frames are deferred.

### 9.1 Linter And LSP Compatibility

The MVP does not implement a language server or a full lint CLI.

It must, however, shape its parser, compiler, and diagnostics so those tools can
be added without rewriting the frontend core:

- diagnostics are structured records with stable codes, not prose-only strings;
- every diagnostic has a source span when the failure is tied to authored
  source;
- parse, syntax, definition, type, variant-proof, provider-result, and
  command-result failures use the same diagnostic channel;
- typed definitions, variants, fields, and path contracts remain discoverable
  after compilation;
- generated Core AST nodes preserve enough origin metadata to support future
  source-map and hover/go-to-definition behavior.

Deferred tooling includes:

- `orchestrate lint workflow.orc`;
- LSP diagnostics-on-save;
- hover for type, contract, effect, and proof information;
- go-to-definition and completion;
- formatting and code actions.

The first tranche should test the structured diagnostics API directly. It
should not add editor integration before the `.orc` to Core Workflow AST path is
proven on one real phase.

## 10. Validation

The MVP compiler must validate:

- unknown names;
- duplicate definitions;
- invalid type references;
- invalid record fields;
- invalid union variants;
- non-exhaustive `match` unless explicitly marked partial;
- provider result return type is record or union;
- command result return type is record or union;
- variant-specific field access outside proof context;
- path contract shape before lowering;
- target DSL version is supported.

After lowering, the existing shared workflow validation remains authoritative
for:

- path safety;
- contract refinement;
- output bundle validation;
- variant output validation;
- provider prompt-contract injection;
- workflow call compatibility;
- runtime state behavior.

The frontend must not duplicate shared validation in a divergent way.

## 11. MVP Standard Prelude

The MVP prelude is fixed and small.

Required names:

```text
String
Int
Bool
Json
Provider
Prompt
PathRel
```

Required built-ins:

```text
provider-result
command-result
match
let*
call
with-phase
phase-target
```

Do not add a broad standard library until one translated workflow proves which
forms are genuinely needed.

## 12. First Migration Target

The first migration target should be one workflow phase, not the whole backlog
drain.

Recommended target:

```text
workflows/library/neurips_backlog_implementation_phase.v214.yaml
```

Reason:

- it has real provider execution;
- it has review/fix behavior;
- it has typed completed/blocked outcomes;
- it historically suffered from brittle status/report handling;
- success is measurable through boilerplate reduction.

The MVP translation may cover only the execute/result-selection portion first
if the full review/fix loop is still too large.

## 13. Success Metrics

For the first translated phase, measure:

- authored lines versus equivalent v2.14 YAML;
- number of manual state paths;
- number of pointer files;
- number of manually paired variant checks;
- number of markdown/text extractors;
- number of shell/Python glue commands kept;
- behavioral equivalence on existing oracle tests.

Minimum success bar:

- authored `.orc` is shorter than the equivalent v2.14 YAML phase;
- manual state-path count decreases;
- variant-only field access is statically rejected outside `match`;
- provider output contract is generated from a typed record/union;
- existing v2.14 behavior tests still pass.

If the translated workflow remains YAML-shaped or requires more boilerplate
than v2.14 YAML, stop and revise the frontend before adding more features.

## 14. Implementation Stages

### Stage 1: Parser And Definitions

Implement:

- S-expression parser with source spans;
- one-file compilation unit;
- `defenum`, `defpath`, `defrecord`, `defunion`;
- duplicate/unknown-name validation.

No runtime execution yet.

### Stage 2: Typed Expressions

Implement:

- `let*`;
- field access;
- record construction;
- `match`;
- basic type checking;
- variant-proof checking.

### Stage 3: Core AST Lowering

Implement:

- `defworkflow`;
- `call`;
- `provider-result`;
- `command-result`;
- lowering to Core Workflow AST;
- handoff to existing shared validation.

### Stage 4: One Phase Translation

Translate the first selected v2.14 phase.

Run:

- compiler unit tests;
- lowering tests;
- shared workflow validation;
- one end-to-end `.orc` usage scenario, such as writing or updating a small
  workflow, compiling it, and running a dry-run when runtime support exists;
- existing behavior/equivalence oracle for that phase.

### Stage 5: Decision Point

Decide whether to continue.

Continue only if metrics show a real reduction in brittle authoring surface.
Otherwise, keep improving YAML ergonomics instead of building more frontend
language.

## 15. Deferred Features

The MVP explicitly defers:

- user `defmacro`;
- user `defproc`;
- module imports/exports;
- higher-order workflow refs;
- resource-transition language form;
- backlog-drain language form;
- loop/recur;
- full effect graph;
- full proof graph artifact;
- full semantic IR artifact;
- debug YAML renderer;
- legacy adapter framework;
- runtime-native queue/resource transaction effects.

`defmacro` remains important for the eventual language. It is deferred so that
user macros cannot become an escape hatch before typed lowering and validation
are proven.

## 16. Acceptance Criteria

The MVP is complete when:

1. A `.orc` file using records, unions, `provider-result`, and `match` compiles
   to Core Workflow AST.
2. Invalid variant field access fails at compile time with a source-span
   diagnostic.
3. Provider output contracts are generated from typed records/unions.
4. At least one real v2.14 workflow phase has an `.orc` translation.
5. The translated phase passes shared workflow validation.
6. A small end-to-end `.orc` usage scenario proves the MVP path beyond isolated
   form tests.
7. Existing oracle/equivalence tests pass for the translated behavior.
8. A metrics report shows whether authoring surface improved.
9. The implementation report explicitly recommends one of:
   - continue toward `defmacro` and procedural library work;
   - revise the MVP;
   - stop and invest in YAML ergonomics instead.

## 17. Recommended Next Spec After MVP

If the MVP succeeds, the next spec should cover user-defined `defmacro`.

That spec should require:

- hygienic expansion;
- source-span preservation;
- no filesystem/network/provider/command effects during expansion;
- no direct Semantic IR emission;
- expanded output must typecheck through the same frontend pipeline;
- macro-introduced provider/command/state effects must be visible after
  expansion.

This keeps `defmacro` on the path without making it the first proof burden.
