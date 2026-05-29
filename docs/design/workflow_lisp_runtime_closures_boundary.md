# Workflow Lisp Runtime Closures Boundary

Status: deferred acceptance contract
Extends: [Workflow Lisp ProcRef And Partial Application Delta](workflow_lisp_proc_refs_partial_application.md), [Workflow Lisp Local ProcRef Bindings Delta](workflow_lisp_let_proc_local_proc_refs.md)
Parent contract: [Workflow Lisp Frontend Specification](workflow_lisp_frontend_specification.md)
Implementation status: not an implementation target until the acceptance gate in this document is satisfied

This document defines the acceptance boundary for a future runtime-closure
feature in Workflow Lisp. It is a spec-level guardrail, not an implementation
plan. It exists so near-term compile-time procedure features do not accidentally
grow into unsafe runtime callable values.

The intended split is:

```text
ProcRef / bind-proc  = compile-time procedure references and specialization
let-proc             = lexical syntax over generated defproc + ProcRef
runtime closures     = runtime-owned callable values with full runtime semantics
```

`ProcRef` and `let-proc` remain compile-time features. Runtime closures are a
separate semantic tier because they affect identity, storage, effects,
capabilities, source maps, executable IR validation, replay, and resume.

## 1. Purpose And Authority

Runtime closures are not ready to implement today.

This document is the authority for deciding whether a proposed runtime-closure
implementation is allowed to start. It does not override the parent Workflow
Lisp contract. It adds a stricter boundary for runtime callable values.

Near-term `ProcRef`, `bind-proc`, and `let-proc` work MUST continue to compile
away before executable IR. A change that leaves unresolved procedure values in
executable/runtime artifacts is outside this document's accepted surface.

The closure feature is implementation-ready only when a candidate design can
meet the conformance profile and acceptance gate below with no fallback to
dynamic Python objects, procedure-name strings, serialized code,
provider-produced procedures, or unchecked executable IR.

## 2. Conformance Profiles

Runtime closure support has three profiles.

### 2.1 Disabled Profile

This is the current required behavior.

The compiler/runtime MUST reject authored or runtime closure values with
`runtime_closure_not_enabled`.

Design fixtures MAY describe closure syntax or metadata, but they MUST NOT
execute closures or serialize runtime closure values as ordinary data.

### 2.2 Design-Fixture Profile

This profile is allowed before execution support.

The compiler/runtime MAY validate rejected examples, registry shapes,
diagnostics, and source-map metadata. It MUST still reject closure execution.

This profile exists to prove that the forbidden cases are understood before any
runtime behavior is added.

### 2.3 Minimum Executable Profile

This is the first profile that may execute runtime closures.

Before implementation starts, the repo MUST have:

- completed or explicitly bounded `ProcRef` and `bind-proc` semantics;
- completed or explicitly bounded `let-proc` semantics, if `let-proc` examples
  are used as closure motivation;
- a concrete executable IR extension point for checked dynamic invocation;
- a closure-family registry design owned by executable bundles;
- a source-map format that can describe both closure creation and invocation;
- an effect/capability model strong enough to reject authority smuggling;
- a deterministic write-root allocation model for repeated dynamic invocation;
- a replay/resume compatibility policy based on executable bundle identity;
- non-implemented fixtures proving forbidden shapes are rejected.

Without those prerequisites, runtime closures remain deferred.

The minimum executable profile MUST also satisfy the acceptance gate in
Section 20.

## 3. Runtime Closure Contract

Runtime closures, if added later, are typed runtime-owned callable values. They
are not `ProcRef`, not `let-proc`, and not ordinary serialized user data.

A runtime closure value MUST carry:

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

## 4. Forbidden Semantics

Do not implement any of the following as a "small closure feature":

- runtime `ProcRef`;
- runtime `let-proc`;
- provider-produced procedure values;
- command-produced procedure values;
- procedure-name strings interpreted as callable values;
- opaque serialized callable payloads;
- Python function objects or host-language closures in state;
- dynamic imports or runtime code loading;
- executable IR nodes that dispatch without a closed target universe;
- closures stored in artifacts, ledgers, provider results, command results, or
  workflow outputs in the first tranche;
- closures that bypass effect, capability, source-map, or write-root checking;
- closures that silently rebind to changed source on resume.

The key non-goal is:

```text
Runtime closures MUST NOT be introduced as a workaround for unresolved ProcRef,
let-proc, effectful-composition, or workflow-lowering gaps.
```

## 5. Relationship To ProcRef And let-proc

`ProcRef` remains compile-time only:

```text
named defproc
-> compile-time ProcRef
-> specialization before Core AST / Semantic IR lowering
-> executable IR contains no procedure value
```

`let-proc` remains lexical syntax over generated `defproc` plus existing
`ProcRef` specialization:

```text
local syntax
-> generated private defproc-equivalent
-> ProcRef specialization
-> ordinary defproc lowering
-> shared validation
-> executable IR contains no procedure value
```

Runtime closures are separate:

```text
runtime callable value
-> sealed closure family
-> typed capture environment
-> checked InvokeClosure executable IR node
-> replay/resume/version semantics
```

`let-proc` MUST NOT become partial runtime-closure support.

## 6. Minimum Executable Surface

The first runtime-closure tranche, if accepted later, MUST be intentionally
narrow.

Allowed:

- closure values created only by authored workflow/frontend forms;
- closure families declared statically in the compiled executable bundle;
- by-value captures of immutable, typed data only;
- dynamic invocation only through a checked executable IR node;
- closure values stored only in runtime-managed state, if storage is needed;
- source-mapped diagnostics for creation, capture, invocation, and resume.

Rejected:

- provider/model/command-produced closures;
- provider/model/command-produced closure family or code ids;
- closure captures;
- provider role captures;
- mutable state captures;
- live context object captures;
- artifact publication of closures;
- workflow-output transport of closures;
- cross-bundle resume without explicit migration metadata.

This tranche is useful only if it proves the full safety model on a small
callable universe. A purely expression-local closure subset may be considered
for experimentation, but it is not sufficient as the semantic model.

## 7. Closure Family Contract

A closure type MUST include a nominal sealed family identity. A structural
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
    signature:
      params:
        - SelectedItem
      return: ImplementationResult
    effect_bound:
      - uses_provider
      - writes_artifact
    capability_bound:
      - implementation_provider
    capture_schema_ids:
      - capture-schema/run-impl-a/456def
      - capture-schema/run-impl-b/789abc
```

A runtime closure is valid only if its code identity appears in the executable
bundle's registry for its declared family.

Two closures with the same signature and effect bound are not interchangeable
unless the invocation site accepts their closure family.

## 8. Closure Value Contract

A runtime closure value contains runtime-owned metadata and typed captures:

```yaml
closure:
  schema: workflow_lisp_runtime_closure/v1
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
      value: {}
    plan:
      mode: value
      type: ImplementationPlan
      value: {}
  source_map_ref: source-map/closure/run-impl-a
  effect_summary_ref: effect/run-impl-a
```

This value is not an opaque blob. Every field that affects invocation,
validation, replay, source mapping, or authority MUST be typed and inspectable.

## 9. Capture Contract

The closure design MUST distinguish capture modes.

Capture by value means an immutable serialized snapshot is stored with the
closure. Capture by reference means a stable runtime reference is re-resolved on
resume. Capture by capability means the closure carries authority that MUST be
accepted by the invocation site.

The first runtime-closure implementation MUST allow only immutable by-value
captures:

- typed scalar values;
- typed records and unions with stable schemas;
- workflow input values represented as immutable data;
- pure path or context descriptors only if replay behavior is defined.

The first tranche MUST reject:

- provider role captures;
- closure captures;
- mutable state references;
- live context objects;
- arbitrary runtime handles;
- provider/model/command-produced closure identities.

Any later by-reference or capability capture MUST define explicit replay/resume
rules and explicit authority rules.

A captured value MUST NOT silently observe changed mutable state after resume.

### 9.1 Capability Captures

Provider roles and similar authority-bearing references are capability captures,
not ordinary data.

The first runtime-closure implementation MUST reject provider-role captures
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

A closure MUST NOT carry provider, command, filesystem, artifact, workflow, or
ledger authority into a dynamic invocation site that did not explicitly accept
that authority.

## 10. Invocation Contract

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
  invocation_site_id: ...,
  source_map_ref: ...
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
permits. The invocation site is where accepted families, effects, capabilities,
write roots, and source-map obligations are checked together.

Executable IR MUST reject any dynamic closure call whose callable universe is
not closed and validated.

## 11. Effect And Write-Root Contract

Constructing a closure value is pure if all captured values already exist and
no state is written.

Persisting a closure into workflow state is a state write.

Invoking a closure has the effects of the selected closure body.

Dynamic invocation MUST also prove deterministic write-root behavior for every
possible target. If artifact paths, ledgers, generated roots, resource scopes,
or reusable workflow boundaries cannot be made deterministic, the program MUST
be rejected.

For every accepted closure family and invocation site, the compiler/runtime MUST
know:

- what write roots may be touched;
- whether roots are derived from the invocation site, closure creation site, or
  an explicit runtime allocation policy;
- how repeated invocations are disambiguated;
- how reusable workflow boundaries receive generated write roots;
- how resume reconstructs the same root allocation.

Runtime closure invocation MUST NOT hide provider calls, command calls, state
mutation, resource movement, artifact publication, or ledger updates.

## 12. Provider And Model Selection Contract

Provider or model output may influence ordinary validated dataflow branches that
select among statically known closures.

Allowed in principle:

```lisp
(match model-choice
  ((FAST choice) fast-closure)
  ((ROBUST choice) robust-closure))
```

This is allowed only if the branch itself is compiled executable IR and each
possible closure value is already in the accepted closure-family registry.

Rejected:

- provider output directly producing a closure value;
- provider output producing closure code identity;
- provider output producing procedure names;
- provider output producing serialized callable payloads;
- provider output producing executable behavior.

The provider may produce data. It MUST NOT produce runtime code identity.

## 13. Storage And Transport Contract

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

## 14. Replay And Resume Contract

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

A runtime MUST NOT silently rebind a closure to changed source merely because a
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

## 15. Source Map Contract

Runtime closure diagnostics MUST map:

- closure creation source;
- captured value source;
- closure body source;
- dynamic invocation source;
- selected closure code identity;
- executable bundle identity;
- generated executable IR nodes.

Diagnostics from closure invocation MUST explain both the dynamic invocation
site and the selected closure body.

Diagnostics from resume MUST explain both the stored closure value and the
bundle/version compatibility failure.

## 16. Diagnostic Contract

Runtime closure work MUST introduce stable diagnostics before execution is
enabled.

Required diagnostics:

- `runtime_closure_not_enabled`
- `closure_family_unknown`
- `closure_family_not_accepted`
- `closure_signature_mismatch`
- `closure_effect_bound_exceeded`
- `closure_capability_not_accepted`
- `closure_capture_mode_unsupported`
- `closure_capture_type_mismatch`
- `closure_capture_schema_mismatch`
- `closure_provider_produced_identity_forbidden`
- `closure_command_produced_identity_forbidden`
- `closure_opaque_payload_forbidden`
- `closure_write_root_policy_invalid`
- `closure_resume_bundle_mismatch`
- `closure_resume_code_mismatch`
- `closure_resume_capture_schema_mismatch`
- `closure_source_map_missing`
- `closure_runtime_value_in_artifact_forbidden`
- `closure_runtime_value_in_workflow_output_forbidden`

Diagnostics MUST preserve the original source-map origin and distinguish:

- invalid closure creation;
- invalid capture;
- invalid dynamic invocation;
- invalid storage/transport;
- invalid resume/migration.

## 17. Validation Rules

The compiler/runtime MUST reject:

- any runtime closure when the feature gate is disabled;
- closure values whose family is not declared in the executable bundle;
- invocation sites whose accepted family set is empty or open-ended;
- closure values whose code id is absent from the accepted family registry;
- structural closure dispatch without nominal family identity;
- capture modes unsupported by the active tranche;
- captures whose serialized value fails the declared type schema;
- provider/model/command-produced closure values or code identities;
- closures stored in artifacts, ledgers, provider results, command results, or
  workflow outputs in the first tranche;
- capability captures not accepted by the invocation site;
- effect summaries that exceed the invocation site's accepted effect bound;
- write-root policies that cannot be replayed deterministically;
- missing source maps for closure creation, capture, body, or invocation;
- resume against a changed executable bundle without explicit migration.

## 18. Acceptance Fixtures

Before runtime closure execution is implemented, add fixtures that exercise the
boundary without making the feature available:

- closure family registry fixture;
- rejected provider-produced closure fixture;
- rejected command-produced closure fixture;
- rejected opaque serialized closure fixture;
- resume code mismatch fixture;
- resume capture-schema mismatch fixture;
- effect-bound dynamic invocation fixture;
- capability-smuggling rejection fixture;
- deterministic write-root rejection fixture;
- closure-capture rejection fixture;
- workflow-output transport rejection fixture;
- artifact publication rejection fixture;
- missing source-map rejection fixture.

These fixtures are acceptance tests for the boundary. They MUST NOT require
runtime closure execution.

## 19. Non-Normative Staging Notes

This order is advisory. The acceptance gate in Section 20 is the normative
implementation boundary.

Recommended order:

1. Finish or explicitly bound `ProcRef` + `bind-proc`.
2. Finish or explicitly bound compile-time `let-proc`.
3. Define and enforce ordinary effectful-composition lowering boundaries.
4. Fix effectful-composition lowering for the forms runtime closures would
   reuse.
5. Add non-implemented closure design fixtures and disabled-feature diagnostics.
6. Define closure-family registry records in executable-bundle metadata.
7. Define `InvokeClosure` executable IR validation without execution support.
8. Define capture serialization and capture-mode validation.
9. Define capability-bounded invocation.
10. Define deterministic write-root allocation.
11. Define resume/migration policy.
12. Add runtime-managed closure state only after serialization, source maps,
    effects, and resume validation are in place.
13. Add execution support for one narrow by-value capture tranche.
14. Consider workflow-boundary transport only after runtime-managed state is
    proven.

Runtime-managed closure state is deliberately late in the sequence because
state storage is where serialization, replay, source maps, effect identity, and
version compatibility become unavoidable.

## 20. Acceptance Gate

Do not implement runtime closure execution until a concrete design and fixture
set demonstrate all of these conditions:

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
- no provider/model/command-produced closure identity;
- no runtime closure values in artifacts or workflow outputs in the first
  tranche;
- no bypass around executable IR validation.

This keeps the boundary clean: `let-proc` is an authoring convenience; runtime
closures are a full runtime semantics feature.

## 21. Open Questions

These questions are not blockers for keeping runtime closures deferred, but they
MUST be answered before implementation:

1. Should closure values be allowed in runtime-managed state in the first
   execution tranche, or should the first tranche be expression-local only?
2. Should executable bundle identity be one global bundle id, or should closure
   code ids be namespaced by workflow entrypoint?
3. What is the smallest useful capture schema that still permits real
   workflows?
4. Are capability captures ever necessary in V1, or should all authority be
   supplied by the invocation site?
5. Should migration mappings be authored manually, generated by compiler diff,
   or prohibited in the first execution tranche?
6. How should dashboards and debug YAML display closure values without making
   them look like ordinary artifacts or user data?
