# Workflow Lisp Provider-Call Policy Design

- **Status:** Reviewed implementation candidate; completion conditional on two final approvals and byte-identical commit
- **Kind:** feature / architecture decision
- **Owner:** Workflow Lisp frontend and shared workflow runtime maintainers
- **Reviewers:** specification reviewer; implementation-quality reviewer
- **Created:** 2026-07-17
- **Last material update:** 2026-07-17
- **Related authority:**
  [`provider-call-policy-parity`](../workflow_yaml_orc_gap_list.md#provider-call-policy-parity),
  [Workflow Lisp Frontend Specification](../design/workflow_lisp_frontend_specification.md),
  [Workflow Language Design Principles](../design/workflow_language_design_principles.md),
  [Providers](../../specs/providers.md), [DSL](../../specs/dsl.md), and
  [State](../../specs/state.md)
- **Implementation target:** the ordinary Workflow Lisp `provider-result`
  pipeline through frontend AST, typing, WCC, Surface/Core/Executable provider
  configuration, shared validation, the existing provider runtime, and resume

## Summary

Extend `provider-result` with three optional inline call-policy operands:

```lisp
(provider-result providers.execute
  :prompt prompts.execute
  :inputs (request)
  :model inputs.worker-model
  :effort inputs.worker-effort
  :timeout-sec 7200
  :returns WorkResult)
```

`model` and `effort` are typed, effect-free, inline-lowerable `String`
expressions. `timeout-sec` is a positive integer literal. The compiler lowers
authored model and effort values to a first-class internal provider-step
`provider_call_policy` mapping and lowers an authored timeout to the existing
`timeout_sec` field. The resolved `ProviderTemplate` declaratively maps present
canonical options to its native parameter or argv shape. Unsupported authored
options fail before invocation; they are never silently ignored. An absent
keyword emits no canonical entry, and complete policy absence preserves current
extern/provider-template defaults and runtime behavior.

This is a generic language feature. Provider identity remains a
compiler-known extern, provider execution remains on the existing shared
executor path, and no workflow-family or module name participates in parsing,
typing, lowering, validation, or runtime behavior.

## Context And Authority

At design acceptance, the Stage-6 gap contract identified
`provider-call-policy-parity` as the one generic language-surface blocker shared
by the two retained `.orc` port queues.
Their YAML sources carry runtime model and effort inputs plus per-call
timeouts. The gap contract permits either a generic implementation or an
explicit owner waiver; no waiver exists, so this design selects the generic
implementation.

Current contracts already provide the lower layers this design must reuse:

- `provider-result` produces an ordinary provider step and a validated typed
  result bundle;
- provider steps already merge provider-template defaults with
  `provider_params`, perform runtime substitution, and enforce `timeout_sec`;
- validated executable IR is execution authority, Semantic IR is the durable
  typed semantic projection, and source maps retain authored provenance;
- root and callee checksums plus checkpoint/program-identity guards already
  reject incompatible resume state.

The missing capability at design acceptance was the `.orc` authoring and
preservation route from a typed policy operand to those existing step fields.
The implemented closure candidate follows this design without making
provider-result a second provider executor.

Interactive design questions were intentionally skipped. The user directed
autonomous roadmap execution, and the reviewed gap contract already chose
generic implementation versus waiver. The design therefore resolves only the
implementation shape needed by that accepted decision.

## Problem

Before implementation, `provider-result` fixed the provider extern, prompt,
inputs, and return contract but exposed no call-local model, effort, or timeout.
A `.orc` port could therefore compile while silently replacing
runtime-configurable YAML inputs with extern defaults or losing the YAML call
deadline. Compile success alone still does not establish behavioral parity.

Putting the values only in provider extern manifests is insufficient. Extern
defaults are compile-time configuration and cannot preserve workflow/procedure
values selected for an individual runtime invocation. Freezing or removing the
controls without a waiver would weaken the accepted migration contract.

## Goals

- Express call-local model, effort, and timeout policy on ordinary
  `provider-result` forms.
- Accept the existing inline-lowerable String scalar subset for model and
  effort without introducing pure projection or runtime provider references.
- Preserve authored policy through frontend AST, WCC,
  Surface/Core/Executable step configuration, `RuntimeStep`, build, and resume
  boundaries.
- Reuse existing provider parameter substitution, invocation preparation,
  timeout enforcement, state, and resume paths.
- Resolve canonical model/effort through declarative provider-template
  capabilities, failing closed when the selected provider does not support an
  authored option.
- Fail closed on type errors, literal nonpositive timeouts, unresolved provider
  parameters, and resume drift.
- Preserve the current lowered and runtime behavior when all three keywords are
  absent.

## Non-Goals And V1 Scope

V1 does not add:

- an arbitrary provider-parameter map;
- a first-class `ProviderCallPolicy` record;
- runtime provider references, dynamic provider loading, or provider identity
  passed as a value;
- provider-specific model or effort enumerations;
- provider/model compatibility inference;
- a second provider invocation, substitution, timeout, checkpoint, or resume
  path;
- policy keywords on `command-result`, adjudicated providers, provider
  sessions, or other effect forms;
- family-, workflow-, module-, extern-, provider-, or basename-specific
  compiler branches;
- a waiver or frozen replacement values.

Provider templates declaratively state whether and how canonical `model` and
`effort` affect their command. Authored canonical options may not fall through
to the existing unused-parameter behavior. Ordinary YAML/provider
`provider_params` remain a separate mapping and keep their current
arbitrary-map compatibility and unused-parameter behavior.

The internal `provider_call_policy` mapping is compiler/runtime step
configuration, not a Workflow Lisp value, record, arbitrary map, or YAML
authoring surface.

## Decision

### Source form

The grammar adds exactly three optional keyword/value pairs to
`provider-result`:

```text
(provider-result <compiler-known Provider extern>
  :prompt <compiler-known Prompt extern>
  :inputs (<expr> ...)
  [:model <String expr>]
  [:effort <String expr>]
  [:timeout-sec <positive Int literal>]
  :returns <return-spec>)
```

Keyword order follows the existing keyword-section behavior. Each keyword may
occur at most once. Existing required operands and return-spec behavior do not
change. After `_keyword_sections`, elaboration checks an explicit allowed-key
set containing only `:prompt`, `:inputs`, `:returns`, `:model`, `:effort`, and
`:timeout-sec`; every unknown keyword is rejected rather than ignored.

Model and effort operands use only the existing inline-lowerable String scalar
subset supported by `_resolve_inline_expr_value` plus the scalar template
renderer: String literals, workflow/procedure inputs or parameters, names,
references, and projections that resolve to those values. Computed `if`, pure
operator, function/procedure/workflow call, record-construction, and other
computed expressions are rejected even when effect-free. V1 does not introduce
a `pure_projection` step merely to compute call policy.

The timeout operand is deliberately narrower: v1 accepts only a positive
integer literal. The current shared runtime substitution and elaboration path
does not provide a typed whole-field dynamic timeout route, and the two port
gates need fixed per-call deadlines rather than runtime timeout inputs. A
future dynamic-timeout surface requires a separate reviewed design.

### Absence semantics

Absence is meaningful and must survive lowering:

| Authored keyword | Lowered provider-step field |
| --- | --- |
| no `:model` | no `provider_call_policy.model` entry |
| no `:effort` | no `provider_call_policy.effort` entry |
| no `:timeout-sec` | no `timeout_sec` field |
| `:model value` | `provider_call_policy.model = <resolved value/template>` |
| `:effort value` | `provider_call_policy.effort = <resolved value/template>` |
| `:timeout-sec 7200` | `timeout_sec = 7200` |

The compiler emits the first-class internal mapping only when at least one
canonical option is authored:

```json
{"provider_call_policy": {"model": "${inputs.model}", "effort": "${inputs.effort}"}}
```

The mapping contains only present model/effort keywords. Mapping insertion
order is not semantic; serializers emit present entries in canonical order
(`model`, then `effort`) for deterministic artifacts. Timeout remains the
ordinary `timeout_sec` field and is not part of provider-template mapping.
Authoring only one option emits only that entry.

The compiler must not synthesize defaults, copy values out of the provider
extern, or emit empty `provider_call_policy`/`provider_params` mappings solely
because the new surface exists. At the lowered mapping surface absent keys are
omitted. New typed policy fields in Surface/Core/Executable configuration may
use `None` internally, but serializers must omit the newly introduced
`provider_call_policy` key when absent rather than add `null`; keyword-free
compiled artifacts must remain byte-identical. Existing unrelated typed fields
and serializers retain their current representations. Provider-template
defaults retain their present precedence when a keyword is absent.

### Type and value rules

- `:model` must typecheck as exactly `String`.
- `:effort` must typecheck as exactly `String`.
- `:timeout-sec` must be a literal whose language type is exactly `Int`;
  `Bool`, `Float`, numeric strings, names, projections, procedure parameters,
  workflow inputs, and computed expressions are rejected in v1.
- The timeout literal must be greater than zero at compile time.
- Once compiled, timeout execution and an elapsed deadline use the existing
  provider timeout path and exit-`124` contract unchanged.

Empty model or effort strings retain the current provider-parameter contract:
the shared provider layer/provider template decides whether they are usable.
This language feature establishes the `String` type, not provider-specific
value vocabularies.

If a dynamic model or effort template cannot be resolved, the existing
provider-parameter `substitution_error` contract applies. This design does not
relabel that failure.

An otherwise well-typed model or effort expression outside the v1
inline-lowerable subset fails with stable diagnostic
`provider_result_policy_operand_not_inline_lowerable` at its authored value
span. It is not automatically materialized through `pure_projection`.

### Canonical provider-template capability contract

`ProviderTemplate` gains a declarative `call_policy_bindings` map. Its keys are
the closed v1 canonical options `model` and `effort`. Each binding declares:

- `target_param`: the provider-template parameter that receives the canonical
  value; and
- optional `argv_fragment`: an ordered list of provider command-template
  tokens appended only when that canonical option is present in the internal
  call policy.

Conceptually:

```python
call_policy_bindings = {
    "model": {"target_param": "model"},
    "effort": {
        "target_param": "effort",
        "argv_fragment": ["--effort", "${effort}"],
    },
}
```

Binding declarations are provider data, not compiler logic. Registration
validates them structurally:

- canonical keys are unique and drawn from the closed call-policy contract;
- `target_param` is the bare identifier portion of an existing ordinary
  provider-parameter placeholder, not a `${...}` token. It must be accepted by
  the same shared identifier grammar that recognizes ordinary
  `${<provider_param>}` command placeholders; registration must reuse that
  grammar rather than define a looser second parser. It is not `PROMPT`,
  `SESSION_ID`, or any other name in the provider runtime's reserved
  context-placeholder namespace;
- target parameters are unique across the declaration, but need not appear in
  provider defaults; a valid no-default provider can consume a call-policy
  value directly;
- fragments are ordered string-token lists and placeholder counting applies
  after the existing command-template escape processing, so escaped literal
  text is not consumption;
- without `argv_fragment`, every applicable `command`, `fresh_command`, and
  `resume_command` variant contains exactly one unescaped placeholder formed
  from that binding's target, `${<target_param>}`; and
- with `argv_fragment`, every applicable base/session variant contains zero
  `${<target_param>}` placeholders, while the fragment contains exactly one
  unescaped placeholder total and that placeholder is the binding's exact
  `${<target_param>}`. It may contain no other dynamic placeholder, including
  `${PROMPT}`, `${SESSION_ID}`, or a context/provider parameter.

Thus whichever actual command variant is selected consumes each present
canonical value exactly once. A zero, duplicate, mismatched, extra, or reserved
placeholder rejects provider registration. These consumption rules constrain
declared bindings only: a provider with no call-policy declaration, or an
invocation with no call policy, retains its current validation and argv
behavior.

`ProviderRegistry` applies the same declaration validation when it initializes
built-in templates and when it accepts a programmatic registration. Invalid
built-in declarations therefore fail registry initialization rather than
bypassing the public registration check.

Built-in declarations are:

- Codex: canonical `model -> model`; canonical
  `effort -> reasoning_effort`. Existing base, fresh-session, and
  resume-session command placeholders/defaults remain native
  `reasoning_effort`.
- Claude and Claude summary templates: canonical `model -> model`; canonical
  `effort -> effort` with the optional `--effort ${effort}` fragment. The
  fragment appears only for a present authored effort, so keyword-free legacy
  Claude argv remains unchanged.
- A built-in or programmatic custom provider that does not declare a canonical
  option does not support it. In particular, a provider without an effort
  binding rejects an authored effort before invocation.

Custom programmatic `ProviderTemplate` instances may declare equivalent
mappings without compiler changes. V1 does not add call-policy binding syntax
to YAML provider-template configuration. Provider-specific value vocabularies
remain outside v1.

### Generic runtime mapping

`RuntimeStep` passes the internal `provider_call_policy` mapping separately
from ordinary `ProviderParams`. Runtime preparation resolves the selected
provider template normally. When the mapping is present, it:

1. validates every present canonical key against the closed contract and the
   template's declared binding;
2. translates each canonical value, without substitution, to its binding's
   native `target_param` and retains any optional-fragment declaration;
3. merges provider defaults, ordinary native step parameters, and translated
   canonical overrides in that precedence order;
4. calls the existing `_substitute_params` exactly once on the one merged
   native-parameter mapping;
5. selects and augments the actual base, fresh-session, or resume-session
   command variant with fragments belonging to present canonical options,
   appending them in canonical `model`, then `effort` order independent of
   authored, mapping-insertion, or declaration order; and
6. passes that command and the once-substituted native parameters to the
   existing `_build_command` path.

Canonical overrides win if a translated `target_param` collides with an
ordinary native step parameter. This collision rule is deterministic and
applies at the one merge; values are not independently or repeatedly
substituted. The one existing `_substitute_params` call remains the sole owner
of `substitution_error`. A same-name target such as `model -> model` requires
no rename. Legacy native parameters such as `reasoning_effort` continue through
ordinary `ProviderParams`. No v1 source form can author both an arbitrary
native parameter and canonical call policy on the same provider-result.

When `provider_call_policy` is absent, runtime skips the canonical resolver and
optional-fragment path entirely. This is what preserves YAML-local provider
parameters and keyword-free built-in invocations exactly.

The mapping is keyed only by canonical option and the resolved template's
declaration. It must not branch on provider name, workflow name, module, source
path, or family.

## End-To-End Representation

### Frontend AST, traversal, and typing

`ProviderResultExpr` gains optional `model`, `effort`, and `timeout_sec` fields;
the timeout field retains its accepted literal node/value rather than a
runtime-resolved expression. Elaboration records each present authored value
under the existing provider-result form provenance. All expression walkers,
cloning/rewrite helpers, macro/procedure inspections, effect discovery,
workflow-reference traversal,
and public serialization must visit or preserve these fields.

The normal typechecker owns model and effort types. Those expressions
contribute their ordinary value-expression effects and references to the
enclosing expression; because this surface requires effect-free operands, a
hidden/effectful operand is rejected instead of being reordered around the
provider call. Elaboration/typechecking jointly enforce the literal-only,
positive timeout rule.

After String typechecking, model/effort validation also proves that each
operand is in the closed inline-lowerable subset. A computed but effect-free
String is still rejected with
`provider_result_policy_operand_not_inline_lowerable`.

### Procedure specialization and WCC

Procedure specialization, type substitution, ProcRef specialization, and
ordinary AST replacement must preserve all three optional expressions.
Specialization may substitute or project an accepted inline value, but it may
not widen the operand into general computation or erase whether the author
supplied a keyword. Timeout remains the authored positive literal.

WCC elaboration includes the three optional operands in the provider-result
operation payload or an equivalently typed WCC field set. WCC traversal,
defunctionalization, loop-binding reconstruction, and both direct and nested
provider-result lowering routes must reproduce the same policy expressions.
Schema-2/WCC is the primary route; any supported compatibility route must
produce the same Core provider-step result.

### Core lowering and shared validation

The one owner-level provider-result lowering payload carries the optional
policy expressions so direct frontend lowering and WCC defunctionalization
cannot diverge. Existing typed value/template rendering resolves each present
operand:

- compile-time values become ordinary string or integer literals;
- runtime model/effort values become the existing resolved binding/template
  representation;
- authored model and effort populate only the canonical
  `provider_call_policy.model` and `provider_call_policy.effort` entries;
- authored timeout populates only `timeout_sec` as a positive integer literal.

The output contract, typed prompt inputs, generated bundle allocation, step
identity, and provider extern lookup remain on the existing provider-result
path. `provider_call_policy` is represented explicitly by `SurfaceStep`,
`CoreProviderStep`, and `ProviderStepConfig`, serialized in the content-addressed
Core/executable compiled build artifacts, and exposed by `RuntimeStep` to
ordinary provider execution. `timeout_sec` remains on the existing common-step path
(`SurfaceStepCommonConfig` / `StepCommonConfig`). Shared validation requires a
closed mapping with String literal/template values, rejects unknown keys and
empty policy maps, and rejects timeout inside policy. Serializers use canonical
`model`, then `effort` key order. Ordinary
`provider_params` remain a separate compatibility surface. There is no
provider-policy adapter step.

Authored YAML/YML may not supply `provider_call_policy`. The YAML frontend and
shared frontend-kind validation reserve/reject that key; only
compiler-generated Workflow Lisp provider steps may introduce the internal
mapping. Shared validation owns mapping shape, not selected-provider
capability, because compilation may not have the runtime registry. The resolved
`ProviderTemplate` performs the capability check defensively at runtime before
process/session creation.

### Core/executable IR, runtime plan, provenance, and build artifacts

The resolved call policy is execution input. Accordingly:

- the Core provider step retains present fields;
- executable IR retains the resolved literal or dynamic model/effort template,
  first-class internal call-policy mapping, and literal timeout needed by the
  ordinary provider step;
- the existing `runtime_plan` remains unchanged as a topology/checkpoint
  projection; it does not carry provider configuration or become execution
  authority;
- content-addressed Core/executable compiled build artifacts serialize the same
  provider-step fields produced by the build;
- the dashboard-oriented persisted surface/graph remains unchanged and omits
  provider configuration, including call policy;
- existing provider-result step/form provenance and procedure/specialization
  expansion lineage continue to identify the authored effect.

V1 adds the required provider-step policy field to `SurfaceStep`,
`CoreProviderStep`, `ProviderStepConfig`, and `RuntimeStep`, but does not add
policy fields to `SemanticPromptSurface`,
field-level source-map validation subjects, the runtime-plan schema, or any
other Semantic IR/source-map schema.
The ordinary provider call remains visible through existing semantic and
source-map projections. If implementation evidence proves that an existing
owning IR or source-map schema must expose additional policy data to preserve
an established contract, the implementation plan must be amended and reviewed
before adding that schema surface.

Debug YAML, reports, and source maps remain views. They must not become the
runtime source of policy.

### Runtime ownership

The ordinary runtime-step view exposes `provider_call_policy` alongside the
existing `provider_params` and `timeout_sec` fields. The existing provider
executor continues to own:

1. generic canonical-option validation and unsubstituted native-target
   translation;
2. the single defaults, ordinary-native-params, canonical-overrides merge;
3. the single existing `_substitute_params` call over that merged mapping;
4. actual command-variant selection and conditional fragment augmentation;
5. the existing `_build_command` and invocation/session preparation;
6. timeout enforcement and exit-124 state;
7. provider result-bundle validation and commit through existing owners.

The workflow executor passes the internal policy as a separate optional
argument to `ProviderExecutor.prepare_invocation`; it is not folded into
`ProviderParams` before that boundary. Absence passes `None` and takes the
unchanged legacy preparation route.

No new timeout normalization or execution branch is required. The compiler
supplies a positive integer literal to the existing provider timeout field.

### Identity and resume

Provider-call policy changes execution and therefore participates in existing
execution identity:

- authored policy syntax and its lowered provider-step content participate in
  the existing authored-source, build, program, and workflow-checksum identity
  surfaces;
- a changed literal, changed binding expression, added keyword, or removed
  keyword is authored-source/program drift, not source-map-only drift;
- runtime workflow inputs used by model/effort policy remain ordinary bound
  inputs and are subject to existing bound-input and checkpoint validation;
- public `.orc` resume rebuilds the candidate through
  `build_frontend_bundle`, then applies the normal source/build/program,
  workflow-checksum, bound-input, checkpoint, and provider-step guards;
- resume may not ignore policy differences, patch old state, or reuse a
  completed provider boundary under a different policy unless an existing
  general compatibility contract independently proves that reuse valid.

No new checksum exception, identity alias, or migration upgrader is authorized.
Provider-registry/template drift remains existing operational configuration and
is not newly checksum-bound by this design.

## Diagnostics And Failure Contract

Compile-time policy diagnostics must point to the authored policy value span
and preserve expansion lineage. Runtime failures cannot promise a field-level
span because v1 adds no field-level source-map subject. V1 uses these stable
categories/codes:

| Phase | Code / state type | Required meaning |
| --- | --- | --- |
| parse/elaboration | `frontend_parse_error` | missing keyword value or duplicate keyword; no AST is accepted |
| elaboration | `provider_result_keyword_invalid` | a keyword is outside the explicit provider-result allowed-key set |
| typecheck | `provider_result_model_type_invalid` | `:model` is not `String` |
| typecheck | `provider_result_effort_type_invalid` | `:effort` is not `String` |
| typecheck | `provider_result_policy_operand_not_inline_lowerable` | a typed String model/effort operand is outside the closed inline-lowerable subset |
| elaboration/typecheck | `provider_result_timeout_literal_required` | `:timeout-sec` is not an integer literal |
| typecheck | `provider_result_timeout_type_invalid` | the timeout literal is not `Int` |
| typecheck | `provider_result_timeout_nonpositive` | a compile-time timeout is zero or negative |
| shared validation | `provider_call_policy_invalid` | the internal mapping is malformed, empty, or contains an unknown/non-String option |
| provider registration | existing provider-template validation error | a declarative call-policy binding is structurally invalid |
| runtime preparation | `provider_call_policy_unsupported` | the resolved provider template does not support a present canonical option |

Unresolved dynamic model/effort parameters retain the existing
provider-parameter `substitution_error` failure. Ordinary provider-template
errors and elapsed-timeout exit `124` also retain their existing diagnostics.
`provider_call_policy_unsupported` uses exit `2`, includes only the resolved
provider identifier and canonical option in bounded context, and uses existing
enclosing provider-result step/form provenance when available. It occurs before
provider process/session creation and must not claim an authored-value span or
echo the policy value, prompt, or secrets.

## Alternatives Considered

### Structured `ProviderCallPolicy` record

Rejected for v1. A record would provide a natural future home for more policy
fields, but the accepted requirement contains only three scalar options and no
runtime policy value is otherwise needed. Introducing a record now would add a
new construction/optional-field/serialization contract and invite arbitrary
provider parameters before their semantics are designed. The inline keywords
can later be desugared into a reviewed record surface if the policy vocabulary
grows.

### Extern-only defaults or owner waiver

Rejected. Extern defaults cannot preserve runtime workflow/procedure inputs at
an individual call site, and they cannot express distinct per-call deadlines.
No owner waiver exists. Freezing the values would therefore hide a migration
delta rather than close the generic parity gate.

### Arbitrary `:provider-params` map

Rejected. It would weaken typechecking, expose provider-template internals as
an unbounded language surface, and make semantic identity and diagnostics less
precise. V1 admits only the reviewed cross-provider keys.

### Pass canonical `effort` through without a declared binding

Rejected. Current built-ins do not share a native effort key or argv shape:
Codex consumes `reasoning_effort`, while Claude needs an `--effort` fragment.
Blind pass-through would silently ignore a promotion-relevant control. A
compiler branch for particular provider names would solve the immediate case
but violate the generic boundary; declarative template bindings keep that
knowledge with its owner.

## Invariants And Failure Modes

- Provider identity is always compiler-known.
- An absent policy remains `None` on new typed fields and is omitted from
  serialized compiled artifacts.
- A present policy field cannot disappear during specialization, WCC, lowering,
  serialization, or resume.
- `provider_call_policy` contains exactly the canonical model/effort values
  introduced by `provider-result`; it never contains arbitrary YAML parameters
  or timeout.
- Direct and WCC lowering produce equivalent ordinary provider-step policy.
- A present canonical option is either mapped through a structurally valid
  provider-template declaration or rejected before invocation; it is never
  ignored as an unused parameter.
- Optional argv fragments appear only for their present authored option and on
  the actually selected base/session command variant.
- Policy values never come from reports, stdout, debug YAML, or source-map
  parsing.
- Invalid or nonpositive timeout source fails compilation; no dynamic timeout
  reaches runtime in v1.
- Existing checksum, checkpoint, call-frame, and resume validation is not
  weakened.
- Provider templates and the shared executor remain the only execution path.
- No behavior is selected by workflow family, module, path, provider name, or
  extern name.

If implementation cannot preserve typed dynamic model/effort values through
the existing template/runtime boundary without adding a second executor, the
design must be revised before implementation continues.

## Compatibility

Existing `.orc` programs require no source change. With all three keywords
absent, their frontend AST meaning, lowered provider step, extern-default
behavior, execution, and resume behavior remain unchanged. Parser acceptance is
additive.

Compatibility is behavioral and representation-aware at each existing layer.
For this additive field specifically, a keyword-free source must produce the
same serialized compiled artifacts byte-for-byte: internal `None` is not
permission to add a new JSON `null`. Tests bind that narrow byte-equality claim;
they do not impose a universal equality rule on unrelated future changes.

Existing provider extern manifests remain valid. An authored call override
uses the one native-parameter merge with precedence provider defaults <
ordinary native step parameters < translated canonical overrides. Thus a
canonical override deterministically wins a target-key collision without a
second merge or substitution pass.

Existing YAML workflow-local providers have no internal call-policy mapping, so
their arbitrary `provider_params` retain current merge, substitution,
unused-key, and command behavior. Existing callers of built-in Codex using the native
`reasoning_effort` parameter remain valid and behaviorally unchanged. New
canonical `effort` maps to that same native slot. Keyword-free
built-in Claude invocations retain their current argv; `--effort` is appended
only for a present authored effort.

The feature does not change YAML syntax or behavior. It supplies a `.orc`
route to semantics YAML already supports.

## Feasibility Basis

This design depends on a new preservation path but not a new provider execution
or dynamic-timeout capability. The current checkout already demonstrates:

- `ProviderResultExpr` parse/type/lower ownership in
  `orchestrator/workflow_lisp/expressions.py`, `typecheck_effects.py`, and
  `lowering/effects.py`;
- provider-result WCC elaboration/reconstruction/defunctionalization in
  `orchestrator/workflow_lisp/wcc/`;
- ordinary Core provider steps carrying `provider_params` and literal
  `timeout_sec` through executable IR and `RuntimeStep`;
- one centralized `ProviderTemplate`/`ProviderRegistry`/`ProviderExecutor`
  preparation path that already owns defaults, substitution, base/session
  command selection, and argv construction;
- provider parameter substitution and timeout enforcement in
  `orchestrator/providers/executor.py` and the workflow executor;
- public `.orc` resume rebuilding through `build_frontend_bundle` before the
  existing build/program/checksum/bound-input/checkpoint guards.

Implementation must add a minimal executable fixture proving a dynamic
workflow/procedure model and effort value plus a literal timeout reach the
existing executor path, with actual built-in Codex and Claude argv capture.
The new declarative binding is feasible only if it remains inside this
centralized preparation path and requires no provider-name branch. Inspection
of these owners alone is not acceptance evidence.

## Verification Strategy

Implementation follows TDD and must include both positive and negative
coverage.

### Parser, AST, traversal, and typing

- parse each keyword alone and all three together, independent of keyword
  order;
- preserve absent versus present fields and exact source spans;
- reject missing values, duplicate keywords, and unknown keywords;
- prove every shared expression traversal/rewrite retains the operands;
- accept literal, workflow-input, procedure-parameter, and lexical typed values
  for model and effort;
- reject non-`String` model/effort and effectful model/effort operands;
- reject computed `if`, operator, call, record, and other non-inline-lowerable
  String operands with
  `provider_result_policy_operand_not_inline_lowerable`;
- accept positive integer literal timeout and reject `Bool`, `Float`, numeric
  string, name/reference, computed, zero, and negative timeout forms.

### Specialization and WCC

- prove procedure specialization/substitution retains dynamic model/effort and
  the authored timeout literal;
- prove WCC elaboration, traversal, reconstruction, and defunctionalization
  retain present fields and absence;
- compare direct/compatibility and primary WCC Core provider-step policy where
  both routes remain supported;
- include nested procedure and loop/control-flow coverage so preservation is
  not fixture-specific to a top-level call.

### Lowering and IR

- literal policy lowers to `provider_call_policy.model`,
  `provider_call_policy.effort`, and `timeout_sec` exactly;
- dynamic typed model/effort values lower to the existing resolved
  template/binding form; timeout lowers as a positive integer literal;
- `provider_call_policy` contains exactly the present canonical model/effort
  values, with one-key and two-key cases covered;
- absent keywords emit none of those entries and do not emit an empty policy
  container at the lowered mapping layer; serializers omit the new key when
  typed policy fields are `None`, and a keyword-free compiled artifact remains
  byte-identical;
- typed frontend AST, Surface/Core/Executable provider-step configuration,
  `RuntimeStep`, content-addressed Core/executable artifacts, and compiled
  bundle agree on the provider-step fields and internal policy mapping;
- shared validation rejects unknown keys, an empty mapping, non-String
  literal/template values, and timeout inside policy;
- authored YAML/YML rejects the reserved internal `provider_call_policy` key;
- runtime plan remains unchanged as a topology/checkpoint projection and gains
  no provider configuration;
- dashboard persisted surface/graph remains unchanged and omits provider
  configuration;
- existing provider-result form/step provenance remains present without a new
  Semantic IR or field-level source-map schema;
- changing one authored policy value changes the applicable authored-source,
  build, program, and workflow-checksum identity.

### Provider-template and runtime capture

- a capturing provider executor receives the resolved model and effort in the
  normal mapped/merged provider parameters and the literal timeout in the normal
  invocation timeout field;
- extern defaults apply when keywords are absent, and authored values override
  defaults when present;
- a canonical override wins a collision with an ordinary native step parameter
  at its translated target key, while a no-collision ordinary parameter is
  retained;
- an instrumented preparation path proves `_substitute_params` is called
  exactly once on the fully merged native mapping, and unresolved values emit
  the single existing `substitution_error` contract;
- provider-template binding declarations reject unknown canonical keys, invalid
  or reserved target parameters, malformed fragments, and every mismatched,
  zero, duplicate, or extra placeholder case in direct and fragment-backed
  bindings;
- direct bindings prove every applicable base/fresh/resume command consumes one
  unescaped target placeholder; fragment-backed bindings prove every applicable
  command consumes zero and the fragment consumes exactly its one target;
- both no-default unrestricted profiles validate positively as their existing
  direct-placeholder profiles: Codex consumes `model` and
  `reasoning_effort`, while Claude consumes `model` and `effort`;
- a separate programmatic custom `ProviderTemplate` fixture positively covers
  a fragment-backed binding across its applicable base/fresh/resume variants;
- registry initialization rejects an invalid built-in binding declaration just
  as programmatic registration rejects an invalid custom declaration;
- built-in Codex maps canonical effort to `reasoning_effort` and produces actual
  base, fresh-session, and resume-session argv with call-authored model/effort;
- built-in Claude produces actual argv with call-authored model/effort, while
  the same invocation without authored effort has no `--effort` fragment;
- Claude summary templates obey the same conditional-fragment rule;
- two present optional fragments append in canonical model-then-effort order
  regardless of authored, input-mapping, or binding-declaration order;
- a provider without an effort binding rejects present effort with
  `provider_call_policy_unsupported`, exit `2`, and zero provider launches;
- unsupported-policy failure exposes only bounded provider/option context plus
  available enclosing step/form provenance, and does not claim field-level
  authored-value provenance;
- a declaratively mapped programmatic custom `ProviderTemplate` works without
  compiler changes;
- YAML provider-template configuration retains its current schema and cannot
  author `call_policy_bindings` in v1;
- YAML workflow-local `provider_params` without internal policy retain their
  current behavior;
- legacy built-in Codex `reasoning_effort` input remains behaviorally
  compatible, including its default and explicit override cases;
- unresolved dynamic model/effort values retain the existing
  `substitution_error` contract;
- a positive literal timeout reaches the ordinary provider invocation;
- a real elapsed deadline retains existing exit-`124` behavior;
- tests prove the ordinary provider executor path was used, not a helper-only
  or mock policy executor.

### Resume both directions

- unchanged authored source/lowered policy and persisted root inputs
  resume/reuse through the normal checkpoint path;
- changed literal policy is rejected by normal source/checksum/program guards;
- root resume reuses persisted root inputs rather than accepting a replacement
  input set; nested bound-input mismatch rejects where the existing nested
  contract applies;
- removing or adding a keyword is rejected as drift;
- public `.orc` resume rebuilds through `build_frontend_bundle` before normal
  guards and does not read debug projections as authority;
- provider-registry/template drift is not asserted to change workflow checksum
  or program identity;
- no test bypasses checksum validation to manufacture a passing resume.

### Regression and integration

- existing structured-result, provider, executable-IR, build-artifact, WCC,
  procedure, runtime, and resume suites remain green;
- one declarative `.orc` integration fixture uses workflow inputs for model and
  effort plus a literal timeout and captures the real invocation contract;
- one procedure fixture passes model/effort through parameters while retaining
  a literal per-call timeout;
- the broad parallel suite runs after focused selectors;
- both an independent specification review and an independent implementation-
  quality review approve the exact implementation tree before port evidence is
  assembled.

Tests must assert contracts, dataflow, identities, and diagnostics rather than
literal provider prompt wording.

## Declarative Acceptance Scenario

Given a `.orc` workflow with `String` inputs `model` and `effort`, a
compiler-known built-in Codex extern, and a `provider-result` that binds those
inputs plus `:timeout-sec 7200`, compiling and running through the public
entrypoint must produce one ordinary provider invocation whose actual argv
contains the bound model and native `reasoning_effort=<bound effort>`, and whose
timeout is integer `7200`. The internal canonical options are mapped by
the Codex template declaration, not a compiler/provider-name branch. The
structured result bundle is validated and committed through the existing
provider-result path. Public resume rebuilds the candidate bundle and, with
unchanged source and bound inputs, uses the normal valid checkpoint route.

A paired built-in Claude scenario maps the same canonical inputs to model plus
`--effort <bound effort>`. Removing only `:effort` removes its internal policy
entry and argv fragment while leaving keyword-free legacy Claude argv
unchanged.

The paired negative compile scenarios use `:timeout-sec 0`, a negative integer,
and a workflow-input reference, plus a computed String policy expression. Each
is rejected before an executable workflow or provider launch. A runtime
negative selects a provider template without effort capability while effort is
present; preparation fails with `provider_call_policy_unsupported` before any
process/session creation. Changing an authored valid policy value before resume
is rejected by the normal identity guards. An unresolved model/effort value
uses the existing provider-parameter `substitution_error`; a provider that
exceeds the valid literal deadline uses the existing exit-`124` contract.

These scenarios must use the public compile/run/resume pipeline. Calling a
policy renderer or provider-executor helper directly is insufficient.

## Security, Operations, And Performance

The design adds no provider authority, credentials, filesystem access, network
path, or secret channel. Model and effort values enter the existing provider
command-construction path after declarative canonical-to-native mapping;
existing masking and logging rules continue to apply. Diagnostics must not echo
unbounded resolved values.

Compile and runtime cost is bounded to two optional expressions plus one
optional literal. No additional process, checkpoint, artifact, or provider call
is introduced.

## Documentation And Specification Impact

After acceptance and implementation:

- update the Workflow Lisp frontend specification with the normative syntax,
  typing, lowering, identity, and diagnostic rules;
- update provider/DSL specs with declarative canonical call-policy bindings,
  internal policy mapping, unsupported-option failure, and policy-absent YAML
  compatibility;
- update the `.orc` drafting guide with a small generic example;
- update the capability matrix from missing to implemented only after tests and
  reviews pass;
- update `provider-call-policy-parity` status/routing without claiming either
  workflow family has passed its promotion gate;
- update normative DSL/provider/state specs only where the shared boundary
  needs a new explicit rule rather than duplicating this design in indexes.

## Implementation Handoff

Implement in this order:

1. parser/AST fields and red syntax/type tests;
2. typing, inline-lowerable-subset validation, explicit keyword validation,
   literal positivity, and traversal preservation;
3. procedure specialization and WCC payload/reconstruction preservation;
4. one shared lowerable provider-result payload plus first-class canonical
   `provider_call_policy` emission;
5. Surface/Core/Executable/`RuntimeStep` representation, serialization, shared
   validation, existing provenance, runtime-plan non-expansion, and identity
   tests;
6. `ProviderTemplate` binding schema, structural validation, built-in mappings,
   and generic executor translation;
7. actual built-in/custom/YAML-compatibility runtime capture plus resume
   both-direction integration tests;
8. focused, broad, and two independent reviews;
9. specification, guide, matrix, and roadmap routing updates.

Likely implementation owners include
`orchestrator/workflow_lisp/expressions.py`, `typecheck_effects.py`, shared
expression traversal/specialization modules, `orchestrator/workflow_lisp/wcc/`,
`lowering/effects.py`, Surface/Core/Executable/runtime-step serialization and
validation owners, `orchestrator/providers/types.py`,
`orchestrator/providers/registry.py`, and the existing provider executor/runtime
boundary. Semantic IR, field-level source-map schema, and runtime-plan schema
are not expected to change. The implementation plan must enumerate exact files
after a fresh code-path audit rather than treating this list as exhaustive.

## Success And Claim Boundary

The design is successfully implemented only when the generic source form,
typing, preservation, lowering, IR/build identity, ordinary runtime capture,
declarative built-in/programmatic-custom provider mapping,
unsupported-provider failure, YAML/native-parameter compatibility,
literal-timeout validation, and resume both-direction tests all pass and both
independent reviews approve the exact tree.

That result closes only the generic `provider-call-policy-parity`
implementation gate. It does **not** promote, establish parity for, or authorize
deletion of either retained workflow family. Each port still owes its own
prompt-dependency, artifact-lineage or watchdog behavior, parity, run/resume,
promotion, reference-scan, and deletion gates under the YAML retirement
program.

## Stop / Revise Criteria

Revise this design before continuing if implementation would require:

- runtime provider references or a family/provider-name special case;
- a second provider execution or timeout path;
- an arbitrary provider-parameter map;
- ignoring policy in authored-source/build/program/workflow-checksum identity;
- bypassing or weakening normal resume guards;
- accepting a dynamic, noninteger, zero, or negative timeout in v1;
- parsing reports, debug YAML, or source maps as runtime policy authority; or
- representing typed dynamic model/effort values only through a fixture/helper
  path that the public compile/run/resume pipeline does not use.

## Open Questions

None block implementation after design review. Additional provider-call policy
fields require a separate design decision; their possibility does not widen the
three-keyword v1 surface.
