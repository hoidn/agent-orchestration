# Workflow Lisp Prompt Calculus

- **Status:** accepted and implemented Q1 and Q2 designs
- **Kind:** language design — typed, compositional provider prompts
- **Owner:** Workflow Lisp frontend plus the existing provider prompt pipeline
- **Selected tranches:** Q1 prompt core and Q2 output positions are implemented;
  Q3 role-separated identity/diagnostics is next at its design-review gate
- **Minimum targets:** Q1 `(:target-dsl "2.20")`; Q2 additive syntax
  `(:target-dsl "2.21")`
- **Q2 design reviews:** independent specification rereview
  `Q2_DESIGN_SPEC_REAPPROVED`, then independent quality review
  `Q2_DESIGN_QUALITY_APPROVED` (2026-07-26)
- **Q2 implementation plan:** accepted after independent
  `Q2_PLAN_SPEC_APPROVED` then `Q2_PLAN_QUALITY_APPROVED`;
  `docs/plans/2026-07-26-workflow-lisp-prompt-output-positions-implementation-plan.md`
- **Related docs:**
  - `docs/design/workflow_lisp_frontend_specification.md`
  - `docs/design/workflow_lisp_transportable_value_type.md`
  - `docs/design/workflow_lisp_native_transportable_returns.md`
  - `docs/plans/2026-07-17-workflow-lisp-provider-prompt-dependencies-design.md`
  - `docs/design/workflow_lisp_program_search_boundaries.md`
  - `docs/design/workflow_language_design_principles.md`, especially
    principle 29
  - `docs/plans/2026-07-26-workflow-lisp-language-quality-domain-semantics-roadmap.md`

## Decision

Q1 adds importable `defprompt` declarations with a closed delivery-kind
surface, fully applied named fills, prompt-owned result contracts, and one
minimum compiled-fragment identity. A `defprompt` is compile-time prompt
structure accepted only in `provider-result :prompt`. It is not a value,
`ProcRef`, procedure body, provider implementation, runtime prompt reference,
or general callable.

The compiler checks declared slot coverage, delivery compatibility,
placeholder correspondence, and result-contract coherence. It does not judge
whether prose is relevant, persuasive, sufficient for the task, or likely to
make a model comply.

The first consumer is the review half of
`workflows/examples/review_revise_design_docs.orc`. Q1 migrates only
`review-design-docs` and its current `prompts.design-docs.review` extern.
The fix prompt, review/revise loop, provider policy, result authority,
retry/resume behavior, and terminal routing remain unchanged.

`defprompt`, a fragment application in `provider-result :prompt`, and every
Q1-specific slot keyword require target DSL 2.20 or later. At target 2.19 and
earlier they fail with `prompt_calculus_requires_dsl_2_20`; lower targets do
not reserve `defprompt` as a general expression or change any extern-backed
provider call.

## Why This Surface Exists

Provider results already have typed, fail-closed contracts. Provider prompts
are still external files plus independently declared inputs, dependencies,
and returns. That split permits drift:

- an external prompt can omit an input the call believes it supplies;
- a rendered placeholder can have no declared source;
- a result type can be duplicated between prompt intent and call syntax; and
- two compiled calls can use different prompt programs without a stable
  fragment-program identity.

Q1 closes only those structural gaps. It reuses the existing prompt
dependency, typed-input, output-contract, prompt snapshot, and provider
transport owners rather than adding another prompt renderer, snapshot store,
result channel, or runtime authority.

## Q1 Surface

### `defprompt`

A prompt declaration belongs to a distinct compile-time module namespace. It
uses ordinary import/export visibility, ambiguity, and source-location rules.

```lisp
(defprompt review-design-doc
  (:fills
    (target_doc :doc DesignDocPath)
    (context_docs :value List[DesignDocPath])
    (review_focus :text)
    (checks_report :path WorkReportPath)
    (review_report_target_path :path ReviewReportTargetPath))
  -> ReviewDecision
  "Take the role of a principal engineer.

   Review the injected target document using {review_focus}.
   Read the context paths in {context_docs}.
   Read the checks report at {checks_report}.
   Write the review to {review_report_target_path}.")
```

The declaration contains:

- one module-local name;
- slots in authored declaration order;
- one optional `ReturnSpec`, defaulting to exact target-2.19 `Value`; and
- one template string.

`ReturnSpec` is the existing type plus optional description/format-hint/example
guidance structure. All existing target gates and type-specific guidance rules
continue to apply, including the prohibition on a `Value` example.

### Fully Applied Named Use

Q1 accepts exactly one direct, fully applied named application in a provider
prompt position:

```lisp
(provider-result providers.design-docs.review
  :prompt
    (review-design-doc
      :target_doc completed.target_doc
      :context_docs completed.context_docs
      :review_focus inputs.review_focus
      :checks_report inputs.checks_report
      :review_report_target_path inputs.review_report_target_path)
  :model inputs.review_model
  :effort inputs.review_effort
  :timeout-sec 3600)
```

All declared slots must appear exactly once as named fills. Fill order in the
application is not semantic: normalization reorders bindings into declaration
order. Unknown, duplicate, missing, or incompatible fills are compile errors.
An incomplete application never yields a residual fragment.

A fragment-backed `provider-result` must not author `:returns`. Its result
type and guidance derive from the declaration's sole `ReturnSpec`. The
enclosing procedure or workflow still checks that derived result through
ordinary type compatibility. Existing extern-backed provider calls retain
their current explicit `:returns` syntax.

A fragment-backed call also must not author `:inputs` or
`:prompt-dependencies`. Every provider-visible typed value or injected
document belongs to one declared slot. Existing extern-backed calls retain
both forms unchanged. Coexistence and merge policy are deferred until a real
consumer needs prompt material outside the fragment declaration.

## Closed Slot Contract

Kinds classify delivery. They are not nominal brands, source subtypes, or
implicit conversion rules. In particular, `:value` is not the Workflow Lisp
type `Value`; it creates neither `T -> Value` nor `Value -> T` conversion.

| Kind | Admissible fill | Optional refinement | Delivery owner | Placeholder rule |
| --- | --- | --- | --- | --- |
| `:doc` | one `PathTypeRef` whose contract is workspace-relative `relpath` and `must_exist=true` | any admissible `PathTypeRef` | existing immutable required-content snapshot and injection block | forbidden |
| `:text` | exact `String` | none in Q1 | raw UTF-8 inline rendering | required at least once; repetition allowed |
| `:value` | a type for which the target-2.20 typed-input registry selects exactly one canonical-JSON renderer | any admissible `:value` type | existing typed prompt-input renderer and evidence path | required at least once; repetition allowed |
| `:path` | any `PathTypeRef` for which the existing registry selects the path-line renderer | any admissible `PathTypeRef` | existing POSIX path reference renderer | required at least once; repetition allowed |

Transportability alone does not install a renderer. Unsupported or ambiguous
renderer selection remains fail-closed. Target 2.20 adds exactly one
Q1-required registry rule: `List[T]` selects canonical JSON when `T` is a
scalar, enum, path, record, or exact `Value` type already representable by
that renderer; the rule applies recursively to nested lists and adds no new
renderer implementation. This rule is required for the selected consumer's
`List[DesignDocPath]`. Q1 does not add implicit renderers for `Optional`,
`Map`, union, variant-case, reference, resource, schema, or other collection
types.

When a slot has a refinement, the fill's resolved static type must satisfy
the existing `type_refs_compatible(refinement, fill_type)` predicate. With no
refinement, membership in the kind's admissible set is sufficient. A
refinement must itself belong to that set. Thus refinement only narrows and
never creates a renderer, path contract, conversion, or subtype rule.

### Delivery Order

Lowering first renders the fragment template's `:text`, `:value`, and `:path`
placeholders as the in-memory base prompt. It lowers `:doc` fills into the
existing required prompt-dependency lane, with `position=prepend`, and records
their declaration order as provenance. The existing dependency owner retains
its canonical resolved-target ordering and alias de-duplication rules; Q1 does
not substitute fragment declaration order for that final block order. The
block uses the existing default dependency instruction; Q1 exposes no
fragment-level instruction or position override.

The final prompt then follows the existing composition contract:

1. start from the rendered fragment base prompt;
2. prepend the fragment's one canonical required `:doc` dependency block;
3. apply consumed-artifact injection at its declared position;
4. append the one generated output-contract suffix; and
5. deliver through the existing provider argv/stdin transport.

Q1 creates no prompt file at runtime. The fragment renderer hands its in-memory
base text and lowered contribution rows to the existing composition path.
The existing attempt snapshot remains the sole record of the prompt delivered
to that attempt.

The migrated generic-reviewer consumer must preserve its current five inputs:

| Slot | Fill | Required preservation |
| --- | --- | --- |
| `target_doc :doc DesignDocPath` | `completed.target_doc` | frozen required content in the prepend lane |
| `context_docs :value List[DesignDocPath]` | `completed.context_docs` | target-2.20 canonical JSON list rendering through the explicit registry rule above |
| `review_focus :text` | `inputs.review_focus` | task-specific lens text |
| `checks_report :path WorkReportPath` | `inputs.checks_report` | referenced path |
| `review_report_target_path :path ReviewReportTargetPath` | `inputs.review_report_target_path` | referenced path only; not an output-position declaration |

The prompt owns `-> ReviewDecision`. The existing `ReturnSpec` pipeline still
produces the generated variant contract, output-contract prompt suffix, and
runtime bundle validation. Provider prose remains a view; the validated
bundle remains result authority.

## Placeholder Grammar

The template scanner is deterministic and left-to-right.

- A placeholder is `{slot-name}`.
- `slot-name` must match `[A-Za-z_][A-Za-z0-9_-]*`.
- `{{` renders a literal `{`; `}}` renders a literal `}`.
- A lone or mismatched brace is invalid.
- Placeholder whitespace, format operators, attribute access, indexing, and
  nested expressions are invalid.
- A placeholder must name one declared `:text`, `:value`, or `:path` slot.
- Every declared rendered slot must appear at least once.
- Repeating a rendered placeholder is allowed and reuses the same rendered
  bytes.
- A `:doc` placeholder is invalid because document content is injected through
  the dependency lane, not inline.

This syntax is independent of provider command `${...}` substitution and
never enters that substitution engine.

## Return Ownership

One `defprompt` declaration owns one `ReturnSpec`. An omitted return means
exact `Value`, not an inferred type and not a wildcard. A fragment-backed
call:

- derives its provider result type from that declaration;
- lowers through the same direct-root/record/union contract machinery as any
  other declared result;
- renders the output contract exactly once; and
- rejects a second authored `:returns`.

Prompts and procedures remain different operation kinds. A procedure cannot
stand in for a prompt, a prompt cannot be referenced by `proc-ref`, and
matching parameter/result shapes do not make them interchangeable.

## Minimum Fragment Identity

Q1 adds `compiled_prompt_fragment_identity.v1`, a canonical SHA-256 digest of
compiled fragment structure:

```text
sha256(canonical_json({
  "schema_version": "compiled_prompt_fragment_identity.v1",
  "referenced_declarations": [
    {
      "qualified_name": ...,
      "template_utf8": ...,
      "slots": [
        {
          "name": ...,
          "kind": ...,
          "refinement": ...,
          "placeholder_policy": ...
        }
      ],
      "return_spec": ...
    }
  ],
  "fully_applied_bindings": [
    {
      "slot": ...,
      "typed_expression_identity": ...
    }
  ]
}))
```

Canonical JSON means UTF-8, sorted object keys, compact separators, JSON
literals only, and no trailing newline. The stored identity is
`sha256:<lowercase-hex>`. Declaration, slot, and binding rows use authored
declaration order; object-key sorting does not reorder those arrays.

Type identity is the existing normalized compiler type descriptor. A
`typed_expression_identity` is a closed JSON projection of the elaborated,
typechecked fill expression:

- a literal is
  `{"kind":"literal","literal_kind":K,"static_type":T,"value":V}`;
- a lexical name is
  `{"binding_path":[N],"kind":"binding_path","static_type":T}`;
- a field access rooted at a lexical name is
  `{"binding_path":[N,F1,...,Fn],"kind":"binding_path","static_type":T}`.

`K` is the existing normalized literal-kind token, `T` is the normalized
static type descriptor, `V` is the already validated JSON literal, `N` is the
authored lexical binding name, and each `F` is one resolved field name.
Imported module constants are not an admitted Q1 fill form. Authors can bind
the result of another pure expression with ordinary `let`/`let*` and fill the
slot from that lexical name.

No other expression node is admitted in Q1. The projection therefore excludes
spans, form paths, expansion stacks, comments, whitespace, runtime values,
Python `repr`, object addresses, absolute paths, and fallback source spelling.
Any other fill form is rejected with `prompt_fill_identity_unsupported`; the
compiler may not fall back to a source location or host-language
representation.

The remaining declaration projections are exact:

- `refinement` is the normalized compiler type descriptor or JSON `null`;
- `placeholder_policy` is `forbidden` for `:doc` and
  `required_repetition_allowed` for every rendered kind; and
- `return_spec` is
  `{"type":T,"guidance":G}`, where `T` is the normalized result type
  descriptor and `G` is the existing
  `normalized_result_guidance_payload` object or JSON `null`.

Q1 has no nested fragment references, so `referenced_declarations` contains
exactly one row: the directly applied declaration. Its `qualified_name` is the
resolved module name plus declaration name, `template_utf8` is the exact
decoded template string, and its slot rows have exactly the four keys shown
above. `fully_applied_bindings` contains exactly one `slot` plus
`typed_expression_identity` row per declared slot. All illustrated `...`
values in the envelope above are replaced only by these closed projections.

The digest includes exactly referenced declarations and normalized fully
applied binding expressions. It excludes:

- unused imports;
- resolved runtime values;
- injected file bytes or digests;
- provider/model/effort policy;
- runtime-owned prompt contributions and preludes;
- consumed-artifact values;
- output bytes;
- ambient repository state; and
- cross-attempt comparison state.

The same digest is required in Semantic IR, Executable IR, and the receiving
attempt's existing immutable prompt snapshot before delivery. Missing or
different carriage fails before provider launch. Q1 makes no claim that this
digest identifies everything the agent saw. Q3 owns role-separated binding,
dependency-content, runtime-contribution, and provider-policy identities,
comparison, and diagnostic presentation.

The exact carrier field is `compiled_prompt_fragment_identity` in:

- the Semantic IR provider application;
- the lowered Executable IR provider step; and
- the top level of the receiving attempt's existing immutable
  `record_kind=prompt_snapshot` evidence.

The attempt carrier is
`workflow_prompt_fragment_snapshot.functional.v1`: a closed,
fragment-specific sibling schema owned by the existing schema-2.1 functional
prompt-snapshot builder, publisher, allocator projection, and terminal
validator. It retains the existing attempt, run, compiler-contract,
dependency-row/group, injection, and final-prompt digest fields, and adds the
required compiled-fragment identity.

The compiler contract uses the new closed origin
`workflow_lisp_prompt_fragment`. It permits zero or more required `:doc`
binding refs, forbids optional refs and authored instruction/position
overrides, and fixes `position=prepend`. With zero document slots, the same
owner publishes empty authored/group/injection rows with instruction source
`none`; this is an explicit fragment snapshot, not an implicit-empty
provider-dependency contract.

Extern-backed calls and existing dependency-bearing calls continue to publish
`workflow_prompt_dependency_evidence.functional.v1` byte-for-byte and carry
no fragment identity. Q1 uses the current public schema-2.1 attempt allocator
and state lifecycle and does not depend on schema-2.2 or provider-isolation
work. The three fragment identity strings must be byte-equal before provider
preparation; missing, malformed, or unequal carriage fails before launch.

## Diagnostics And Source Ownership

The Q1 refusal set is closed:

| Code | Refusal | Primary source owner |
| --- | --- | --- |
| `prompt_slot_kind_unknown` | kind is not `doc`, `text`, `value`, or `path` | kind token |
| `prompt_slot_duplicate` | slot name is declared more than once | duplicate declaration |
| `prompt_slot_refinement_invalid` | refinement is incompatible with the kind/renderer lane | refinement occurrence |
| `prompt_placeholder_syntax_invalid` | malformed name, escape, or brace | template occurrence |
| `prompt_placeholder_undeclared` | placeholder names no slot | placeholder occurrence |
| `prompt_placeholder_missing` | rendered slot has no placeholder | slot declaration; template is related |
| `prompt_doc_placeholder_forbidden` | document slot appears inline | placeholder; slot declaration is related |
| `prompt_fill_duplicate` | named fill appears more than once | duplicate fill keyword |
| `prompt_fill_unknown` | fill names no slot | fill keyword |
| `prompt_slot_undischarged` | one or more declared fills are absent | application; missing declarations are related |
| `prompt_slot_type_mismatch` | fill fails kind/refinement compatibility | fill expression; slot declaration is related |
| `prompt_fill_renderer_unsupported` | selected kind has no unique existing renderer | fill expression |
| `prompt_fill_identity_unsupported` | fill expression is outside the closed literal/name/field-path identity grammar | fill expression |
| `prompt_partial_application_unsupported` | incomplete application is used as structure | application |
| `prompt_return_redeclaration_forbidden` | fragment-backed call also authors `:returns` | call-site `:returns`; declaration return is related |
| `prompt_inputs_redeclaration_forbidden` | fragment-backed call also authors `:inputs` | call-site `:inputs`; declaration slots are related |
| `prompt_dependency_redeclaration_forbidden` | fragment-backed call also authors `:prompt-dependencies` | call-site dependency form; declaration document slots are related |
| `prompt_calculus_requires_dsl_2_20` | a Q1 declaration, application, or slot keyword is authored below target 2.20 | first Q1-specific form or keyword |
| `compiled_prompt_fragment_identity_missing` | Semantic IR, Executable IR, or attempt snapshot lacks the digest | provider application/source-map owner |
| `compiled_prompt_fragment_identity_invalid` | a carried identity is not `sha256:` plus 64 lowercase hex digits or its bound canonical projection is malformed | malformed carrier or bound application |
| `compiled_prompt_fragment_identity_mismatch` | carried digests disagree | provider application/source-map owner |

Existing module visibility, type resolution, prompt-dependency, path,
renderer-runtime, output-contract, and provider-transport failures retain
their existing codes. They may relate the fill occurrence to their existing
source owner; Q1 does not mint duplicate runtime errors.

Diagnostic precedence is:

1. declaration syntax, duplicate slots, kinds, refinements, and placeholders;
2. module/import/export resolution;
3. application fill names and completeness;
4. fill type and renderer compatibility;
5. return redeclaration and enclosing result compatibility;
6. identity carriage validation; and
7. existing runtime prompt/output/provider failures.

## Real Consumer And Equivalence Gate

Q1 migrates:

- workflow: `workflows/examples/review_revise_design_docs.orc`;
- procedure: `review-design-docs`;
- provider: `providers.design-docs.review`;
- extern key: `prompts.design-docs.review`;
- prompt asset:
  `prompts/workflows/review_revise_design_docs/review.md`; and
- result: imported `std/phase::ReviewDecision`.

The declaration may live in the consumer module or one importable companion
module selected by the implementation plan. The extern key and review prompt
asset are retired only for this call. `prompts.design-docs.fix` remains an
extern.

Acceptance must prove:

- the consumer remains WCC/schema-2 and preferred current guidance;
- all five fills follow the existing delivery lanes and order;
- the composed base/dependency/input/contract bytes are intentionally
  equivalent to the prior consumer, apart from the reviewed placeholder
  normalization needed to make the fragment explicit;
- provider selection, model, effort, timeout, result contract, bundle
  authority, retry/resume, and review-loop behavior are unchanged; and
- no family/module/provider name appears in generic compiler or runtime
  machinery.

## Principle 29 And Parsimony

Slot kinds are structural delivery constraints, not mandatory type
taxonomies. Refinements are optional and may only narrow. Q1 introduces no
nominal wrapper type, implicit `Value` coercion, structural record coercion,
new outcome union, or failure-as-data carrier. Existing declared types remain
exact and fail-closed.

An author can begin with `:text`, unrefined `:value`, generic path families,
and an omitted return (`Value`), then narrow where consumers need stronger
guarantees. Names remain mandatory only where they already carry a
load-bearing contract, such as rooted paths, routed variants, and persisted
identities.

## Explicitly Outside Q1

Q1 does not add:

- residual or partial application;
- fragment-valued fills or nested fragment composition;
- prompt values, `PromptRef`, prompt collections, or dynamic selection;
- `:out` output-position slots or post-attempt existence checks;
- judgment values, judgment lists, provenance views, or reviewer matrices;
- role-separated attempt identity, cross-attempt comparison, or prompt-drift
  diagnostics;
- type-parameterized fragments;
- semantic prompt-quality checking;
- optimization, search, or fitness;
- a new runtime prompt/result/snapshot store;
- procedure/provider signature interchangeability; or
- security/provider-isolation behavior.

Q2 exclusively owns `:path :out`. Q3 exclusively owns role-separated prompt
identity and diagnostics. Q4 exclusively owns judgment inspection values and
views. Residual fragments require a later consumer-triggered design amendment
and are not implicitly selected by any of those stages.

## Q1 Verification Boundary

The implementation plan must include TDD coverage for:

- declaration/import/export and distinct namespace behavior;
- all kind/refinement/placeholder rules and diagnostic precedence;
- fully applied named fills, including missing/unknown/duplicate/wrong-type
  failures;
- explicit rejection of residuals, nested fragments, `:out`, `proc-ref`, and
  call-site `:returns`;
- default exact `Value` and an explicit structured `ReturnSpec`;
- classic/WCC parity where both routes support the surrounding provider call;
- Semantic IR, Executable IR, attempt-snapshot identity carriage, and
  missing/mismatch failure before launch;
- unchanged existing extern-backed calls;
- one clean and one resumed deterministic migrated-consumer execution without
  duplicate provider work;
- the existing prompt dependency, typed-input, output-contract, state, and
  resume adjacency; and
- the repository broad non-security comparison.

Q1 and Q2 are implemented through their reviewed plans recorded in the active
roadmap. The design below is durable contract authority; factual execution
evidence remains in the Q2 implementation plan.

## Implemented Q2 Amendment: Output-Position Slots

**Status:** accepted after independent specification rereview
`Q2_DESIGN_SPEC_REAPPROVED` and independent quality review
`Q2_DESIGN_QUALITY_APPROVED`, then implemented under the reviewed Q2 plan.
Q2 is an additive target-2.21 surface.
Target-2.20 parsing, compilation, identity bytes, runtime behavior, and resume
compatibility remain exactly the implemented Q1 behavior above.

Q2 adds only an output role to a rendered path slot:

```lisp
(defprompt review-design-doc
  (:fills
    (target_doc :doc DesignDocPath)
    (review_report_target_path :path :out ReviewReportTargetPath))
  -> ReviewDecision
  "Review the injected document.
   Write the review to {review_report_target_path}.")
```

The closed slot grammar becomes:

```text
(slot-name :doc [PathType])
(slot-name :text)
(slot-name :value [Type])
(slot-name :path [PathType])
(slot-name :path :out [PathType])  ; target 2.21+
```

`:out` is a role modifier, not a fifth kind, a type, a renderer, or a
caller-side keyword. It may occur exactly once, immediately after `:path`, and
nowhere else. A target-2.20 module or application using it fails with
`prompt_output_positions_require_dsl_2_21`. The modifier does not make a fill
optional: every output-position slot remains subject to the ordinary exact
named-fill discharge rule and placeholder rule.

An output-position refinement, when present, and the resolved static type of
its fill must each be a workspace-relative `relpath` contract with
`must_exist=false`. This is the existing target-path shape: the file need not
exist before provider launch, but the runtime can resolve its path inside the
workspace before launch and require it after the attempt. Refinements continue
to narrow only. `:out` does not create a nominal path type, convert `String` to
a path, weaken an existing-path contract, or install a renderer. An unrefined
`:path :out` admits only a fill already carrying that same workspace-relative,
non-existing-target path structure.

### One Authored Path Contract

The declaration slot and its one fill are the sole authoring authority for all
of these:

1. the placeholder name and POSIX path-line rendering in the fragment;
2. the runtime path template resolved from the fill;
3. one compiler-projected required file postcondition; and
4. source ownership for compile-time and runtime diagnostics.

Neither `provider-result` nor the caller may redeclare or override the output
name, path, type, requiredness, delivery mode, or postcondition. A fragment
application with an output-position slot projects exactly this ordinary
`expected_outputs` row onto the provider step:

```json
{
  "name": "<slot-name>",
  "path": "<resolved-fill-template>",
  "type": "string",
  "required": true
}
```

The row is compiler-owned. Its `name` comes from the slot, and its `path` comes
from the same normalized Q1 runtime binding source that supplies the
placeholder. One compiler helper derives both consumers: an exact frozen
`{"ref": R}` binding becomes the runtime template `${R}`, while an admitted
string-literal binding becomes that exact validated literal value. No source
spelling, AST `repr`, or second path reconstruction is permitted. Before
provider launch, the typed value resolved for POSIX path-line rendering and the
resolved `expected_outputs.path` must be the same canonical workspace-relative
POSIX path; disagreement is contract mismatch. The implementation may carry
source-map metadata beside or within the internal row, but no second authored
path or output declaration exists. The primary runtime source owner is the fill
expression that selected the concrete path; the slot declaration and its
`:out` token are related origins.

`type: string` means Q2 verifies one required UTF-8 file at that exact path and
records its content under the slot name. The path slot's static contract owns
workspace-relative resolution and containment; the generated expected-output
row owns post-attempt existence and string-file validation. Q2 does not infer a
content schema from prose or from the prompt result type.

The first consumer is the implemented review half of
`workflows/examples/review_revise_design_docs.orc`.
`review-design-doc.review_report_target_path` changes from
`:path ReviewReportTargetPath` to
`:path :out ReviewReportTargetPath`. Its fill remains
`inputs.review_report_target_path`; the generated output name is
`review_report_target_path`; and the existing `ReviewDecision` remains the sole
structured result contract. The consumer E2E must prove that the provider
writes the required report at the filled path and returns the intended same
path in `ReviewDecision.review_report`. Q2 does not infer a general mapping
between output slots and arbitrary path-valued result fields.

### Required Generic Output-Contract Composition

The current generic owners assume one output-contract surface:

- `orchestrator/workflow/validation.py`, in the declared-output-contract
  exclusivity check and `_validate_expected_outputs`, validates authored step
  combinations and expected-output rows;
- `orchestrator/workflow/prompting.py`,
  `PromptComposer.apply_output_contract_prompt_suffix`, currently selects only
  one of `expected_outputs`, `output_bundle`, or `variant_output`;
- `orchestrator/workflow/executor.py`,
  `WorkflowExecutor._resolve_output_contract_paths` and
  `_apply_expected_outputs_contract`, resolves and validates only one selected
  contract and then attaches its artifacts;
- `orchestrator/contracts/output_contract.py`,
  `validate_expected_outputs`, `validate_output_bundle`, and
  `validate_variant_output_bundle`, owns the actual file and structured-bundle
  checks; and
- `orchestrator/workflow/surface_ast.py`,
  `orchestrator/workflow/semantic_ir.py`,
  `orchestrator/workflow/executable_ir.py`,
  `orchestrator/workflow/lowering.py`,
  `orchestrator/workflow/elaboration.py`, and
  `orchestrator/workflow/runtime_step.py` carry the existing
  `expected_outputs` and structured-result contracts into runtime.

Q2 requires a generic correction in those owners. It is not a
review-consumer special case:

1. shared validation admits `expected_outputs` together with exactly one of
   `output_bundle` or `variant_output`;
2. `output_bundle` plus `variant_output`, either structured contract plus
   `select_variant_output`, `expected_outputs` plus `select_variant_output`, or
   any other multi-contract combination remains rejected;
3. provider prompt completion renders both generated contract blocks exactly
   once, in fixed output-position-then-structured-result order;
4. after a successful provider process, the runtime resolves the paths and
   validates both contracts in that same deterministic order before exposing
   either artifact mapping;
5. failure of either contract produces one failed step and commits no artifacts
   from either contract to state; this atomicity does not roll back files the
   provider already wrote;
6. on joint success, the runtime merges the two artifact mappings only when
   their names are disjoint; and
7. a collision between an expected-output name and any possible structured
   bundle field name fails before provider launch, with both source owners; and
8. after path resolution but before provider launch, output-position
   destinations must be pairwise distinct and disjoint from the resolved
   structured-result bundle path. Aliasing fails with the colliding fill
   origins and the structured-result/provider-application origin as
   appropriate, even when artifact names differ.

The compiler projects output-position rows through
`orchestrator/workflow_lisp/prompts.py` (`PromptSlot`, `_parse_slots`, prompt
typechecking, and `_compiled_identity_projection`) and
`orchestrator/workflow_lisp/lowering/phase_scope.py`
(`_build_compiler_prompt_fragment_contract`), then installs them on the provider
step in
`orchestrator/workflow_lisp/lowering/effects.py`
(`_lower_provider_result_operation`). Classic and WCC lowering must produce the
same declaration-ordered rows, identities, source-map subjects, and executable
contracts. Generic IR validators must reject missing, extra, reordered,
unpaired, or caller-authored substitutes.

### Identity, Checkpoint, And Resume

A fragment application with no output-position slot continues to use
`compiled_prompt_fragment_identity.v1` with byte-identical canonical input and
digest at targets 2.20 and 2.21. Merely compiling Q1 source under target 2.21
does not upgrade its identity.

An application containing one or more output-position slots uses
`compiled_prompt_fragment_identity.v2`. Its canonical projection is the Q1
projection with:

- `schema_version` set to `compiled_prompt_fragment_identity.v2`; and
- an `output_role` on every declaration slot, exactly `required_string_file`
  for `:path :out` and `none` otherwise.

The existing slot name, kind, refinement, placeholder policy, fill-expression
identity, return contract, and array ordering remain unchanged. The v2 digest
therefore distinguishes a render-only `:path` from the same slot with a
post-attempt obligation without perturbing Q1-only identities.

Q2 also introduces `compiler_prompt_fragment_contract.v2` as the inspectable
runtime carrier for a v2 identity. The v1 carrier type and canonical
serialization remain byte-for-byte unchanged and admit no output-position
rows. The v2 carrier retains the v1 template and rendered-slot fields and adds
one closed, declaration-ordered `output_positions` array. Each row is the exact
slot-role binding plus its exact compiler-projected `expected_outputs` object:

```json
{
  "slot_name": "<slot-name>",
  "output_role": "required_string_file",
  "expected_output": {
    "name": "<slot-name>",
    "path": "<resolved-fill-template>",
    "type": "string",
    "required": true
  }
}
```

The v2 carrier validator requires at least one row, unique names, exact keys,
the sole `required_string_file` role, nested `type=string`,
nested `required=true`, and a unique declaration-relative-order correspondence
with the subset of rendered `kind=path` slots whose normalized role is
`required_string_file`. Ordinary rendered path slots with `output_role=none`
have no row. Compiler construction must feed both the v2 identity slot
projection and the carrier row from one normalized slot-role record, prove
every normalized output-role slot has exactly one row, and never reconstruct
either copy independently. A v2 contract is invalid if a projected row names no
rendered path slot or if an output-role slot has no row. At every Core,
Semantic IR, Executable IR, persisted configuration, checkpoint, and runtime
boundary, a dedicated pair validator compares the carrier's nested
`expected_output` objects exactly, in order, with the provider configuration's
`expected_outputs`; missing, extra, reordered, or unequal rows fail before
provider preparation. Runtime therefore reads an explicit validated role
carrier and does not infer output role from the opaque digest.

The v1-or-v2 identity, its matching v1-or-v2 compiler contract,
compiler-projected expected-output rows, and their source-map subjects must
agree through Core, Semantic IR, Executable IR, persisted provider
configuration, checkpoint program identity, and the receiving attempt. Missing
or mismatched Q2 carriage fails before provider preparation. A compatible
completed checkpoint may be reused only after the original boundary committed
both the required file postcondition and the structured result. Resume must
not re-execute that boundary; incompatible output-role identity, carrier, or
contract drift is ordinary program drift.

### Closed Q2 Diagnostics And Precedence

Q2 adds this closed diagnostic set:

| Code | Refusal | Primary source owner |
| --- | --- | --- |
| `prompt_output_positions_require_dsl_2_21` | `:out` appears below target 2.21 | `:out` token |
| `prompt_output_position_syntax_invalid` | `:out` is duplicated, misplaced, or followed by an invalid slot tail | offending token or slot declaration |
| `prompt_output_position_kind_invalid` | `:out` is used with a kind other than `:path` | `:out` token; kind token is related |
| `prompt_output_position_refinement_invalid` | an explicit refinement is not a workspace `relpath` with `must_exist=false` | refinement; `:out` token is related |
| `prompt_output_position_fill_invalid` | the resolved fill type is not a workspace `relpath` with `must_exist=false` | fill expression; slot declaration is related |
| `prompt_output_position_contract_collision` | projected output name collides with a structured-result artifact name | output slot; result field origin is related |
| `prompt_output_position_destination_collision` | two resolved output destinations alias, or one aliases the structured-result bundle path | colliding fills, or fill plus structured-result/provider-application origin |
| `prompt_output_position_contract_mismatch` | IR/runtime carriage is missing, extra, reordered, or disagrees with the fragment identity | provider application/source-map owner |

`prompt_output_position_destination_collision` is a preparation-time,
pre-provider diagnostic when any destination depends on runtime substitution.
The compiler may emit the same code earlier only for a collision proven from
static literal destinations. Contract mismatch remains a boundary-validation
diagnostic rather than a promise that every carrier defect is visible during
source typechecking.

At runtime, existing expected-output violation types remain authoritative,
including `invalid_output_path`, `missing_output_file`, and string-file
validation failures. Their subject references must resolve to the Q2 fill and
slot origins; Q2 does not mint duplicate runtime error names.

Precedence extends Q1's order without making Q2 diagnostics unreachable:

1. slot-tail token recognition identifies the presence of `:out`; when it is
   present below target 2.21, the Q2 target gate wins over legacy Q1
   tail/refinement rejection;
2. at target 2.21 or later, Q2 validates modifier multiplicity and placement,
   then the `:path` kind requirement;
3. ordinary Q1 duplicate-slot, kind, refinement, and placeholder checks run on
   the normalized slot, followed by Q2 output-refinement validation;
4. module/import/export resolution;
5. Q1 application fill names and completeness;
6. Q1 fill type/renderer compatibility, then Q2 output-fill compatibility;
7. return ownership and enclosing result compatibility;
8. projected-output/structured-result name collision;
9. v1/v2 identity, compiler-contract, and expected-output pair validation;
10. resolved rendered-path equality and destination-alias validation before
    launch; and
11. existing runtime path, expected-output, structured-output, and provider
   failures.

Slots whose tails contain no `:out` retain byte-for-byte Q1 precedence and
diagnostics.

### Q2 Verification Boundary

The implementation plan must require:

- target-2.20 rejection and target-2.21 positive parsing for the exact grammar,
  plus duplicate, misplaced, non-path, existing-path refinement, wrong-fill,
  missing-fill, and caller-override negatives;
- exact Q1 v1 identity bytes at both targets and v2 identity sensitivity to
  `output_role`, plus byte-identical v1 compiler-contract serialization and
  both-direction v2 carrier/`expected_outputs` pair validation;
- classic/WCC parity for the projected expected-output row, source-map subjects,
  prompt fragment contract, result contract, Semantic IR, Executable IR,
  persisted configuration, and checkpoint identity;
- generic validation tests that admit only
  `expected_outputs + output_bundle` and
  `expected_outputs + variant_output`, reject every other multi-contract
  combination, and reject artifact-name overlap;
- exact derivation tests for binding refs and path literals, plus both-direction
  proof that the path rendered into the prompt equals the resolved
  `expected_outputs.path`;
- pre-launch rejection of pairwise output-position destination aliasing and of
  aliasing with either structured-result bundle shape, even under distinct
  artifact names;
- prompt-composition tests proving one output-position block followed by one
  structured-result block;
- both-direction runtime tests: required file plus valid bundle succeeds;
  missing required file plus valid bundle fails; required file plus invalid or
  missing bundle fails; and neither failure publishes a partial artifact map;
- first-consumer E2E proving the one authored report-target fill drives prompt
  rendering and the required-file postcondition, the `ReviewDecision` remains
  authoritative, and the clean/resumed provider boundary executes once;
- checkpoint/resume tests proving compatible reuse and rejecting Q1/Q2 identity
  or projected-contract drift;
- genericity scans excluding consumer/module/provider names from compiler and
  runtime machinery; and
- the repository's broad non-security comparison followed by ordered
  specification and quality review.

### Explicit Q2 Non-Goals

Q2 adds no:

- arbitrary file content type or content schema beyond required UTF-8 string;
- optional output, directory output, glob, dynamic output name, or output set;
- call-site output declaration, override, weakening, or delivery-mode switch;
- implicit mapping from output slots to result fields;
- new result, artifact, snapshot, checkpoint, or runtime channel;
- change to Q1-only rendering, identity bytes, evidence schema, or resume; or
- security/provider-isolation behavior.

The implemented amendment routes next to Q3's separate role-separated
identity/diagnostics design-review gate. It does not pre-accept or expose Q3 or
Q4 behavior.
