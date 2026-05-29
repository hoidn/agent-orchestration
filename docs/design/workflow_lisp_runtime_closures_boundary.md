# Workflow Lisp Runtime Closures Boundary

Status: deferred runtime-semantics design boundary
Extends: [Workflow Lisp ProcRef And Partial Application Delta](workflow_lisp_proc_refs_partial_application.md), [Workflow Lisp Local ProcRef Bindings Delta](workflow_lisp_let_proc_local_proc_refs.md)
Parent contract: [Workflow Lisp Frontend Specification](workflow_lisp_frontend_specification.md)
Non-goal: changing `ProcRef`, making `let-proc` imply runtime closures, or bypassing executable IR validation

This document is not an implementation target. It defines the boundary that a
future runtime-closure feature must satisfy so near-term compile-time procedure
features do not accidentally grow into unsafe runtime callable values.

The intended split is:

```text
ProcRef / bind-proc  = compile-time procedure references and specialization
let-proc             = lexical syntax over generated defproc + ProcRef
runtime closures     = runtime-owned callable values with full runtime semantics
```

`ProcRef` and `let-proc` must remain compile-time features. Runtime closures are
a separate semantic tier because they affect identity, storage, effects,
capabilities, source maps, executable IR validation, replay, and resume.

## 1. Decision

Runtime closures, if added later, are typed runtime-owned callable values. They
are not `ProcRef`, not `let-proc`, and not ordinary serialized user data.

A runtime closure must include:

- nominal sealed closure family;
- call signature;
- effect bound;
- capability bound;
- typed capture schema;
- executable-bundle code identity;
- source-map identity;
- replay/resume compatibility metadata.

Example type shape:

```lisp
Closure[
  family RunImplementation,
  (SelectedItem) -> ImplementationResult,
  :effects (uses_provider writes_artifact updates_ledger),
  :capabilities (implementation_provider)
]
```

The closure family, not the structural signature alone, is the unit that makes
the callable universe closed.

## 2. Closure Families

A closure type must include a nominal sealed family identity. A structural
signature such as:

```lisp
Closure[(SelectedItem) -> ImplementationResult
  :effects (uses_provider)]
```

is insufficient because unrelated closures may share the same signature and
effect bound while belonging to different semantic families.

An executable bundle owns a closure-family registry:

```yaml
closure_families:
  RunImplementation:
    accepted_code_ids:
      - closure/run-impl-a/abc123
      - closure/run-impl-b/def456
    signature: SelectedItem -> ImplementationResult
    effect_bound:
      - uses_provider
      - writes_artifact
    capability_bound:
      - implementation_provider
```

A runtime closure is valid only if its code identity appears in the executable
bundle's registry for its declared family.

Two closures with the same signature and effect bound are not interchangeable
unless the invocation site accepts their closure family.

## 3. Executable IR Invocation

Runtime closures require an explicit checked executable IR invocation node. They
do not weaken executable IR validation; they require extending it.

Conceptual node:

```text
InvokeClosure {
  accepted_families: [RunImplementation],
  closure_value_ref: ...,
  args: ...,
  result_type: ImplementationResult,
  accepted_effect_bound: ...,
  accepted_capability_bound: ...,
  write_root_policy: ...,
  invocation_site_id: ...
}
```

The node is valid only if every possible target accepted at that site satisfies:

- closure-family membership;
- signature compatibility;
- effect bound;
- capability bound;
- deterministic write-root and resource-scope rules;
- source-map obligations;
- replay/resume compatibility rules.

A call site may accept a narrower target set than the closure family globally
permits. The invocation site is the place where accepted families, effects,
capabilities, write roots, and source-map obligations are checked together.

Executable IR must reject any dynamic closure call whose callable universe is
not closed and validated.

## 4. Capture Modes

The closure design must distinguish capture modes.

Capture by value means an immutable serialized snapshot is stored with the
closure. Capture by reference means a stable runtime reference is re-resolved on
resume. Capture by capability means the closure carries authority that must be
accepted by the invocation site.

The first runtime-closure implementation should prefer immutable by-value
captures only:

- typed scalar values;
- typed records and unions with stable schemas;
- workflow input values represented as immutable data;
- pure path or context descriptors only if replay behavior is defined.

The first implementation should reject or defer:

- provider role captures;
- closure captures;
- mutable state references;
- live context objects;
- arbitrary runtime handles;
- provider/model/command-produced closure identities.

Any by-reference or capability capture requires explicit replay/resume rules
and explicit authority rules.

A captured value must not silently observe changed mutable state after resume.

## 5. Capabilities

Provider roles and similar authority-bearing references are capability captures,
not ordinary data.

The first runtime-closure implementation should reject provider-role captures
unless the runtime can prove:

- the closure was created with that capability;
- the invocation site explicitly accepts that capability;
- replay/resume preserves the same authority semantics;
- the closure cannot smuggle authority into a context that did not declare it.

Invocation requires the intersection of:

```text
captured closure capabilities
AND invocation-site accepted capabilities
AND executable-bundle capability policy
```

A closure must not carry provider, command, filesystem, artifact, or workflow
authority into a dynamic invocation site that did not explicitly accept that
authority.

## 6. Closure Value Model

A runtime closure value contains runtime-owned metadata and typed captures:

```yaml
closure:
  family: RunImplementation
  code_id: closure/run-impl-a/abc123
  executable_bundle_id: bundle/2026-05-29/example/789abc
  type:
    params:
      - SelectedItem
    return: ImplementationResult
    effects:
      - uses_provider
      - writes_artifact
    capabilities:
      - implementation_provider
  capture_schema_id: capture-schema/run-impl-a/456def
  captures:
    design:
      mode: value
      type: DesignDoc
      value: ...
    plan:
      mode: value
      type: ImplementationPlan
      value: ...
  source_map_ref: ...
  effect_summary_ref: ...
```

This value is not an opaque blob. Every field that affects invocation,
validation, replay, source mapping, or authority must be typed and inspectable.

## 7. Replay And Resume

Closure code identity resolves against the executable bundle that created the
closure, not against the current source module by name.

On resume, the runtime validates:

- executable bundle identity;
- closure family registry entry;
- closure code hash;
- capture schema hash;
- serialized capture compatibility;
- effect summary identity;
- capability policy;
- source-map identity.

If a newer executable bundle is used, resume requires an explicit migration
mapping.

No runtime may silently rebind a closure to changed source merely because a
module name or local procedure name matches.

Example diagnostic:

```text
closure_resume_code_mismatch:
  runtime closure `run-impl` was created by executable bundle
  bundle/2026-05-29/example/789abc with closure code hash abc123.

  resume attempted with bundle bundle/2026-06-02/example/012def,
  where the corresponding closure code hash is def456.

  closure created at:
    workflows/drain.orc:41

  dynamic invocation site:
    workflows/drain.orc:88

  action:
    resume with the original executable bundle or provide an explicit migration
    from abc123 to def456.
```

## 8. Effects And Write Roots

Constructing a closure value is pure if all captured values already exist.

Persisting a closure into workflow state is an ordinary state write.

Invoking a closure has the effects of the selected closure body.

Dynamic invocation must also prove deterministic write-root behavior for every
possible target. If artifact paths, ledgers, generated roots, resource scopes,
or reusable workflow boundaries cannot be made deterministic, the program must
be rejected.

For every accepted closure family and invocation site, the compiler/runtime must
know:

- what write roots may be touched;
- whether roots are derived from the invocation site, closure creation site, or
  an explicit runtime allocation policy;
- how repeated invocations are disambiguated;
- how reusable workflow boundaries receive generated write roots;
- how resume reconstructs the same root allocation.

Runtime closure invocation must not hide provider calls, command calls, state
mutation, resource movement, artifact publication, or ledger updates.

## 9. Provider And Model Selection

Provider or model output may influence ordinary validated dataflow branches that
select among statically known closures.

Allowed in principle:

```lisp
(match model-choice
  (:fast   fast-closure)
  (:robust robust-closure))
```

This is allowed only if the branch itself is compiled executable IR and each
possible closure value is already in the accepted closure-family registry.

Rejected:

- provider output directly producing a closure value;
- provider output producing closure code identity;
- provider output producing procedure names;
- provider output producing serialized callable payloads;
- provider output producing executable behavior.

The provider may produce data. It must not produce runtime code identity.

## 10. Storage And Transport

The first useful runtime-closure implementation may store closures only in
runtime-managed workflow state. This is still a full runtime-semantics feature,
not a small extension, because it immediately requires serialization, resume,
state schema compatibility, source maps, effect identity, and migration policy.

Rejected in the first implementation:

- publishing closures as artifacts;
- writing closures into external records intended for humans or tools;
- embedding closures in result bundles crossing exported workflow boundaries;
- serializing closures into provider prompts;
- accepting closures from provider, model, or command output;
- capturing other closures.

Expression-local runtime closures that cannot survive suspension are a possible
experimental subset, but they are not sufficient for general workflow semantics.

Closure captures may be allowed later only when closure graphs are acyclic,
effect-bounded, capability-bounded, serializable, source-mapped, and
version-compatible.

## 11. Source Maps

Runtime closure diagnostics must map:

- closure creation source;
- captured value source;
- closure body source;
- dynamic invocation source;
- selected closure code identity;
- executable bundle identity;
- generated executable IR nodes.

Diagnostics from closure invocation must explain both the dynamic invocation
site and the selected closure body.

Diagnostics from resume must explain both the stored closure value and the
bundle/version compatibility failure.

## 12. Relationship To ProcRef And let-proc

`ProcRef` remains compile-time only:

```text
named defproc
-> compile-time ProcRef
-> specialization before lowering
-> no runtime procedure value
```

`let-proc` remains lexical syntax over generated `defproc` plus existing
`ProcRef` specialization:

```text
local syntax
-> generated private defproc-equivalent
-> ProcRef specialization
-> ordinary defproc lowering
-> shared validation
-> no runtime procedure value
```

Runtime closures are separate:

```text
runtime callable value
-> sealed closure family
-> serialized capture environment
-> checked InvokeClosure node
-> replay/resume/version semantics
```

Nothing in `let-proc` should become partial runtime closure support.

## 13. Non-Implemented Design Fixtures

Before implementing runtime closures, add non-implemented design fixtures that
exercise the boundary without making the feature available:

- closure family registry fixture;
- rejected provider-produced closure fixture;
- rejected opaque serialized closure fixture;
- resume code mismatch fixture;
- effect-bound dynamic invocation fixture;
- capability-smuggling rejection fixture;
- deterministic write-root rejection fixture;
- closure-capture rejection fixture.

These fixtures are pressure tests for the design. They should not require
runtime closure execution.

## 14. Staging

Recommended order:

1. Finish `ProcRef` + `bind-proc`.
2. Add minimal compile-time `let-proc`.
3. Define and enforce ordinary effectful-composition lowering boundaries.
4. Fix effectful-composition lowering.
5. Add non-implemented closure design fixtures.
6. Design closure family registry.
7. Design `InvokeClosure` executable IR validation.
8. Design capture serialization and capture modes.
9. Design capability-bounded invocation.
10. Design deterministic write-root allocation.
11. Design resume/migration policy.
12. Only then consider runtime-managed closure state.
13. Only after that consider workflow-boundary transport.

Runtime-managed closure state is deliberately late in the sequence because state
storage is where serialization, replay, source maps, effect identity, and
version compatibility become unavoidable.

## 15. Acceptance Gate

Do not implement runtime closures until the design can prove:

- sealed closure-family correctness;
- explicit checked dynamic invocation;
- replay/resume correctness;
- executable-bundle-based code identity;
- deterministic version compatibility;
- typed capture serialization;
- capture-mode semantics;
- capability safety;
- static effect visibility;
- deterministic write-root allocation;
- source-map explainability;
- no opaque closure blobs;
- no provider/model-produced closure identity;
- no bypass around executable IR validation.

This keeps the boundary clean: `let-proc` is an authoring convenience; runtime
closures are a full runtime semantics feature.
