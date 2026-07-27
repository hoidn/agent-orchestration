# Workflow Lisp Prompt Calculus

- **Status:** accepted Q1 design (independent specification and quality review
  approved 2026-07-26)
- **Kind:** language design — typed, compositional provider prompts
- **Owner:** Workflow Lisp frontend plus the existing provider prompt pipeline
- **Selected tranche:** Q1 prompt core only
- **Minimum target:** `(:target-dsl "2.20")`
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
- the top level of the receiving attempt's existing immutable prompt-snapshot
  record.

A fragment-backed call always uses that existing attempt snapshot publication
owner, including when it has no `:doc` fill and no separately authored prompt
dependency. In that case the snapshot has an empty dependency contribution
set but still binds the compiled identity and final prompt digest. A snapshot
for an extern-backed call remains unchanged. The three identity strings must
be byte-equal before provider preparation; missing, malformed, or unequal
carriage fails before launch.

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

Q1 design acceptance does not select implementation. A reviewed implementation
plan remains the next gate.
