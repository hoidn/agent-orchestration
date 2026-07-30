# Workflow Lisp Prompt Identity And Diagnostics

- **Status:** accepted
- **Kind:** target design
- **Owner:** Workflow Lisp prompt-calculus Q3
- **Target:** DSL 2.22
- **Depends on:** implemented Q1 prompt core and Q2 output positions
- **Design reviews:** `Q3_DESIGN_SPEC_APPROVED`, then
  `Q3_DESIGN_QUALITY_APPROVED`, over immutable reviewed snapshot
  `fdf16f362f93eae89c05600e6954a118270fe7b7`
- **Does not select:** Q4 judgment views, prompt search/evolution, P1–P5,
  runtime debugging, or any parked roadmap

## Summary

Q3 adds a content-free, attempt-scoped identity for the exact invocation
context and prompt bytes prepared for attempted delivery by a fragment-backed
provider call. It retains the existing
Q1/Q2 compiled fragment digest as the **fragment-program** role and adds four
separate runtime roles:

1. resolved slot bindings;
2. injected dependency content selected into the prepared prompt;
3. runtime-owned prompt contributions; and
4. the effective provider invocation policy.

The runtime publishes those five roles, the exact prepared final-prompt
digest, and one composition digest before provider launch. This proves
preparation and selection for attempted delivery only—not dispatch, process
receipt, remote receipt, or model read/attention. A pure comparator classifies
drift by role, and the existing report surface exposes those classifications for
completed, failed, or still-running attempts. The record is provenance and
diagnostic evidence only. It is not a workflow value, result, checkpoint,
resume guard, or search/fitness input.

Q3 applies only to the direct fragment-backed `provider-result` surface that
exists at target 2.22. Live-supervision and peer-group forms do not currently
accept a `defprompt` application and do not become Q3 consumers by implication.
A future fragment-backed provider operation must define its exact
runtime-contribution rows before it can opt into this schema.

The later ML-2 allocator simplification changes only the persistence substrate:
current allocation state is counter-only, and the immutable deterministic
scope-and-ordinal file is the persisted publication source. Historical
lifecycle-event state remains readable for compatibility but is never emitted
or consulted by current Q3 reporting. The identity, comparison, and
non-authority contracts in this design are unchanged.

## Decision

Adopt:

- target DSL `2.22`;
- optional compiler/runtime carrier
  `prompt_attempt_identity_version`;
- exact carrier value `workflow_prompt_attempt_identity.v1`;
- companion compiler-owned binding plan
  `compiler_prompt_attempt_binding_plan.v1`;
- attempt evidence schema
  `workflow_prompt_fragment_snapshot.functional.v2`;
- five closed identity roles with independent canonical digests;
- one exact final-prompt digest and one composition digest;
- ordered comparison classifications on the existing report surface; and
- byte- and behavior-compatible target-2.20/2.21 compiler, runtime,
  checkpoint, provider, and evidence paths, with the intentional additive
  report-API effect defined below.

Do not change:

- `compiled_prompt_fragment_identity.v1`;
- `compiled_prompt_fragment_identity.v2`;
- `compiler_prompt_fragment_contract.v1` or `.v2`;
- Q1/Q2 result, output-position, checkpoint, or completed-boundary semantics;
- the provider-attempt allocation/event shape as it existed when Q3 was
  introduced (later superseded by ML-2's counter-only substrate); or
- state schema `2.1`.

## Problem

The current compiled fragment identity deliberately identifies only referenced
prompt declarations and normalized fill expressions. It excludes resolved
runtime values, dependency bytes, runtime-owned suffixes/preludes, provider
policy, and cross-attempt comparison. That is correct for program identity,
but insufficient when an operator needs to answer:

- Did instructions change, or only inputs?
- Did an injected document change?
- Did output/result guidance or another runtime-owned contribution change?
- Did the provider/model/effort/timeout/input policy change?
- Is a hanging attempt using the same prompt context as its predecessor?

A single "prompt changed" hash cannot answer those questions. Expanding the
compiled fragment digest would also conflate program and attempt identity,
break Q1/Q2 compatibility, and tempt runtime evidence into resume authority.
Q3 therefore adds a separate attempt-scoped role model.

## Existing Authority Boundaries

Q3 builds on existing owners:

- the compiler owns `CompilerPromptFragmentContract` and
  `compiled_prompt_fragment_identity`, and at target 2.22 owns the companion
  declaration-ordered binding plan;
- the prompt renderer owns resolved fragment slots, exact rendered bytes, and
  the target-2.22 one-render trace;
- the prompt-dependency snapshot/render owner knows exact shown dependency
  bytes and the final injected block;
- the ordinary prompt composer owns consumed-artifact, output-position, and
  structured-result contributions;
- `ProviderExecutor.prepare_invocation` owns the resolved invocation used for
  launch; and
- the root provider-attempt allocator owns attempt scope and ordinal, while
  immutable publication owns the deterministic, content-sealed evidence file.

Q3 must consume those owners. It must not parse the final prompt, reopen a
dependency, reconstruct policy from argv, or copy prompt semantics into a
second renderer.

## Target And Carrier

At target 2.22, every fragment-backed `provider-result` carries:

```text
prompt_attempt_identity_version =
  "workflow_prompt_attempt_identity.v1"
```

The optional field is retained through:

- the typed provider application;
- Semantic IR;
- Executable IR;
- persisted provider configuration;
- lexical checkpoint configuration; and
- `RuntimeStep`.

Targets 2.20 and 2.21 omit the field byte-for-byte. At target 2.22, an absent,
malformed, unknown, dropped, or unequal carrier fails before provider launch.
The carrier is part of program/configuration compatibility, but the
attempt-identity record itself is not read by runtime or resume.

The same target also carries one separate compiler-owned plan:

```json
{
  "schema_version": "compiler_prompt_attempt_binding_plan.v1",
  "rows": [
    {
      "declaration_ordinal": 0,
      "slot_name": "review_doc",
      "slot_kind": "doc",
      "refinement": null,
      "output_role": "none",
      "delivery": "dependency",
      "runtime_source": {
        "kind": "required_dependency",
        "ordinal": 0
      },
      "renderer": null
    }
  ],
  "plan_sha256": "sha256:..."
}
```

The rows are exact declaration order, with contiguous zero-based
`declaration_ordinal` values and unique slot names. `slot_kind` is the closed
Q1 kind; `refinement` is the declaration's normalized optional refinement,
not the fill's inferred static type; `output_role` is `none` or
`required_string_file`; and `delivery` is `dependency` for `doc` or
`template` for every rendered kind.

`runtime_source` is an exact locator into an already-owned runtime input:

- a document row uses `required_dependency` plus its ordinal in the existing
  fragment dependency contract; and
- a rendered row uses `rendered_slot` plus its ordinal in the existing
  `CompilerPromptFragmentContract.rendered_slots`.

Document rows have `renderer=null`: `required-document` is a dependency
selector, not a prompt renderer, and Q3 does not invent a renderer version for
it. Rendered rows carry exactly
`{"renderer_id":S,"renderer_version":1}`. `renderer_id` is the existing
fragment-contract renderer: `raw-utf8-string` for `text`, or the compiler's
selected `canonical-json`/`posix-path-line` renderer for `value`/`path`.
Target 2.22 makes the existing raw-string algorithm explicitly version 1; it
does not route text through the typed-input registry. The plan digest covers
the closed object without `plan_sha256`.

The compiler constructs this plan from the resolved declaration and the same
selected dependency/rendered/output-position rows that build the existing
Q1/Q2 contracts. Validation requires exact coverage and agreement:

- `required_dependency` locators are unique, contiguous, and equal the
  existing required dependency rows in their authored order;
- `rendered_slot` locators are unique, contiguous, and agree on name, kind,
  and renderer ID with the existing rendered-slot carrier, which has no
  renderer-version field; Q3 fixes the plan's renderer version to 1;
  `value`/`path` additionally agree on renderer ID and version with their
  selected typed-input carrier, while `text` is governed by Q3's exact
  `raw-utf8-string` version-1 rule and does not acquire typed-input evidence;
- `required_string_file` rows equal the existing v2 output-position rows by
  name and order, while a v1 fragment has only `none`; and
- no row, locator, output role, refinement, renderer, or digest may be
  reconstructed from source text or inferred at runtime.

The optional plan and its digest are retained through the typed provider
application, Semantic IR, Executable IR, persisted provider configuration,
lexical checkpoint, and `RuntimeStep`. Target 2.22 requires the identity
version and binding plan as a pair and requires every boundary copy and digest
to agree before provider preparation. Targets 2.20 and 2.21 omit both
byte-for-byte. The plan participates in ordinary program/configuration and
resume compatibility; runtime does not read persisted prompt evidence to
reconstruct it.

The compiled fragment identity remains whichever Q1/Q2 identity the
application already requires:

- a fragment with no output-position slot retains
  `compiled_prompt_fragment_identity.v1`; and
- a fragment with at least one `:path :out` slot retains
  `compiled_prompt_fragment_identity.v2`.

Compiling under target 2.22 does not upgrade or recalculate either digest.

## Canonical Digest Rule

Every Q3 digest is:

```text
sha256:<lowercase-hex>(
  UTF-8 canonical JSON of the closed payload
)
```

Canonical JSON uses sorted object keys, compact separators, JSON literals
only, no non-finite numbers, and no trailing newline. Arrays retain the order
defined below. No role projection contains prompt text, resolved values,
dependency content, stdout/stderr, Python representations, object addresses,
absolute workspace paths, full command argv, environment variables, or
ambient repository hashes.

Each role has this wrapper:

```json
{
  "schema_version": "workflow_prompt_attempt_fragment_program.v1",
  "payload": {},
  "sha256": "sha256:..."
}
```

The digest is over the closed `payload`, not over the wrapper. Validators
recompute it. The wrapper schema tokens are exact:

| Role key | `schema_version` |
| --- | --- |
| `fragment_program` | `workflow_prompt_attempt_fragment_program.v1` |
| `resolved_bindings` | `workflow_prompt_attempt_resolved_bindings.v1` |
| `injected_dependencies` | `workflow_prompt_attempt_injected_dependencies.v1` |
| `runtime_contributions` | `workflow_prompt_attempt_runtime_contributions.v1` |
| `provider_policy` | `workflow_prompt_attempt_provider_policy.v1` |

No alias, omitted token, role/token mismatch, or unknown version is admitted.

## Attempt Identity Schema

`workflow_prompt_attempt_identity.v1` is:

```json
{
  "schema_version": "workflow_prompt_attempt_identity.v1",
  "roles": {
    "fragment_program": {},
    "resolved_bindings": {},
    "injected_dependencies": {},
    "runtime_contributions": {},
    "provider_policy": {}
  },
  "final_prompt": {
    "bytes": 0,
    "sha256": "sha256:..."
  },
  "composition_sha256": "sha256:..."
}
```

The five role keys are exact. The composition digest is over:

```json
{
  "schema_version": "workflow_prompt_attempt_composition.v1",
  "role_sha256": {
    "fragment_program": "...",
    "resolved_bindings": "...",
    "injected_dependencies": "...",
    "runtime_contributions": "...",
    "provider_policy": "..."
  },
  "final_prompt": {
    "bytes": 0,
    "sha256": "..."
  }
}
```

The final-prompt digest is computed from the exact bytes supplied to
`ProviderExecutor.prepare_invocation`. The prepared invocation must carry the
same prompt bytes for stdin delivery or the same prompt substitution bytes for
argv delivery. A disagreement fails before launch.

## Role 1: Fragment Program

The fragment-program payload is:

```json
{
  "identity_schema_version": "compiled_prompt_fragment_identity.v1",
  "compiled_prompt_fragment_identity": "sha256:..."
}
```

`identity_schema_version` is exactly v1 or v2 and must agree with the paired
compiler fragment contract and output-position shape. The digest is the
existing compiled identity; Q3 does not copy declarations or calculate a new
program hash.

A change in this role classifies as `instruction_drift`.

### Runtime Fragment Render Trace

At target 2.22 the existing `render_prompt_fragment_base` owner returns the
rendered base plus one immutable in-memory trace row for every non-document
slot. It still renders each slot exactly once. A trace row is:

```json
{
  "rendered_slot_ordinal": 0,
  "slot_name": "review_focus",
  "renderer": {
    "renderer_id": "raw-utf8-string",
    "renderer_version": 1
  },
  "value_sha256": "sha256:...",
  "raw_renderer_bytes_sha256": "sha256:...",
  "substitution_bytes": 0,
  "substitution_bytes_sha256": "sha256:..."
}
```

The trace validates against the companion binding plan and existing fragment
contract. `value_sha256` is the canonical transport-value digest of the exact
resolved slot value. For `raw-utf8-string` version 1, raw renderer bytes and
substitution bytes are the exact strict UTF-8 encoding of the string. For
`canonical-json` and `posix-path-line` version 1, raw renderer bytes are the
single existing `render_view` result and substitution bytes are its strict
UTF-8 bytes after removing exactly one trailing LF when present—the existing
fragment-substitution rule. The trace hashes both forms so it can agree with
existing raw typed-input evidence while Role 2 identifies the bytes actually
selected into the prepared fragment.

At target 2.22, fragment-owned typed-input evidence for `value` and `path`
must be derived from this same trace, never by calling `render_view` again.
The typed-input evidence owner consumes the trace's `value_sha256` and
`raw_renderer_bytes_sha256` and validates exact binding name, slot kind,
renderer ID, renderer version 1, and value-digest correspondence against its
selected typed-input carrier before constructing the existing evidence key.
It preserves the existing typed-input evidence schema and raw-renderer digest
meaning. A missing, extra, duplicate, reordered, or disagreeing trace/evidence
correspondence fails as `prompt_attempt_binding_plan_invalid` before either
record is published. Text has a trace row but no typed-input evidence row.
Targets 2.20 and 2.21 retain the existing typed-input rendering path
byte-for-byte.

No trace row stores or publishes the resolved value or rendered bytes. The
render owner uses the in-memory substitution text to build the fragment and
returns only immutable metadata/digests beside it. A missing, extra,
reordered, duplicate, renderer-mismatched, value-mismatched, or
substitution-mismatched trace fails before prompt composition or v2
publication. Targets 2.20 and 2.21 retain the existing string-only return and
rendering behavior byte-for-byte.

## Role 2: Resolved Bindings

The resolved-bindings payload is:

```json
{
  "binding_plan_sha256": "sha256:...",
  "rows": [
    {
      "slot_name": "review_doc",
      "slot_kind": "doc",
      "refinement": null,
      "output_role": "none",
      "delivery": "dependency",
      "renderer": null,
      "value_sha256": "sha256:...",
      "rendered_bytes_sha256": null
    }
  ]
}
```

The payload contains the validated companion binding-plan digest. Rows use
fragment declaration order and contain exactly:

- slot name and closed Q1 kind;
- normalized refinement or null;
- Q2 output role (`none` or `required_string_file`);
- delivery (`dependency` for `doc`, `template` for `text`, `value`, and
  `path`);
- the exact selected renderer ID/version, or null for `doc`;
- the digest of the normalized transportable resolved value; and
- the digest of exact rendered bytes, or null for `doc`, whose content is
  owned by the dependency role.

One row is required per declared slot, including a slot whose resolved value
equals its default. Unused lexical bindings, imported constants not referenced
by the fragment, and call context outside those rows are excluded.

The runtime walks the validated binding plan; it does not merge declarations
from the existing contracts. A `rendered_slot` locator consumes the exact
fragment-render trace row: `value_sha256` is copied from the trace and
`rendered_bytes_sha256` is its `substitution_bytes_sha256`, never the raw
renderer-output digest. A `required_dependency` locator
consumes the existing dependency authored row for that exact ordinal:
`value_sha256` is the canonical transport-value digest of its snapshotted
`evaluated_relpath`, while file content remains exclusively in the dependency
role. Missing, duplicate, reordered, name-mismatched, or locator-mismatched
runtime evidence fails before v2 publication.

The input role deliberately does not digest the fully rendered fragment.
Template bytes belong only to `fragment_program`; rendered fill bytes belong
only to their declaration-ordered binding rows. A template-only edit therefore
classifies only as instruction drift. If equal program and binding roles
nevertheless produce different fragment-composition bytes, the final-prompt
check detects the unaccounted composer change as
`prompt_identity_composition_mismatch` instead of double-classifying it.

A change in this role classifies as `input_drift`.

## Role 3: Injected Dependencies

The injected-dependencies payload is derived only from bytes selected into the
prepared final prompt:

```json
{
  "shown_groups": [
    {
      "order": 0,
      "authored_row_ids": ["sha256:..."],
      "render_status": "complete",
      "shown_bytes": 0,
      "shown_sha256": "sha256:..."
    }
  ],
  "injection": {
    "position": "prepend",
    "block_bytes": 0,
    "block_sha256": "sha256:..."
  }
}
```

`shown_groups` retains existing canonical group order but includes only
`complete` or `truncated` groups with non-null `shown_sha256`. It excludes:

- `retained_sha256`;
- normalized bytes beyond the shown prefix;
- omitted group content;
- unused imports and unreferenced paths; and
- current file bytes reopened after snapshot.

The injection block digest includes exact prepared framing, instruction, and
truncation summary bytes. Therefore a change to an omitted file matters only
when it changes selected prompt material, such as the prepared truncation
summary. The builder projects these fields from the existing one-render
fragment snapshot; it never reads dependency content again.

A change in this role classifies as `dependency_content_drift`.

## Role 4: Runtime Contributions

The runtime-contributions payload is:

```json
{
  "rows": [
    {
      "composition_ordinal": 0,
      "kind": "structured_result",
      "position": "append",
      "bytes": 0,
      "sha256": "sha256:..."
    }
  ]
}
```

Rows include only non-empty bytes actually inserted outside the rendered
fragment and dependency block. The closed `kind` set is:

- `consumed_artifacts`;
- `output_positions`;
- `structured_result`.

`composition_ordinal` is the contiguous zero-based order of runtime
contribution segments in the final prompt. `position` is `prepend` or `append`
and must agree with the existing owner. When present, the existing
consumed-artifact owner contributes exactly one row for the complete inserted
delta, including the separators it selected around its already rendered
block; the row hashes no artifact value or policy object separately. Its
declared prepend/append position is preserved, and it precedes the generated
output-position and structured-result suffix rows because the existing
composition pipeline applies consumed injection before the output contract.
Output-position then structured-result order remains fixed. A disabled,
empty, unresolved-to-no-shown-value, or otherwise byte-empty contribution has
no row.

The ordinary composition pipeline must expose these exact byte segments as an
immutable in-memory trace while it builds the final prompt. Q3 consumes that
trace; it does not render another block or split/reparse the final prompt.
For consumed artifacts, the existing `apply_consumes_prompt_injection` owner
returns its composed prompt plus the one exact target-2.22 trace segment from
the same render/insertion operation; it is not called a second time. The
target-2.22 composer validates that every non-empty runtime contribution has
one trace row, every row corresponds to one inserted segment, row ordering and
positions match the actual composition operations, and the traced segment
bytes plus the fragment/dependency owners' bytes cover the prepared final
prompt without a gap or overlap. Only lengths and digests enter the persisted
role.
Targets 2.20 and 2.21 keep the existing string-only composer returns and
consumed-artifact behavior byte-for-byte.

Coordinated-provider additions are not admitted because coordinated
fragment-backed operations do not exist in this tranche.

A change in this role classifies as `runtime_prelude_drift`.

## Role 5: Provider Policy

The provider-policy payload comes from the same resolved
`ProviderInvocation` that is about to execute:

```json
{
  "provider_name": "codex",
  "model": "gpt-5",
  "effort": "high",
  "timeout_sec": 1800,
  "input_mode": "stdin"
}
```

Fields are exact:

- logical provider registry name;
- effective canonical `model` and `effort` strings, or null when the provider
  has no declared canonical binding/value;
- positive timeout seconds or null;
- `argv` or `stdin`.

`ProviderExecutor.prepare_invocation` derives this closed projection from its
already merged/substituted parameters, declared call-policy bindings, ordinary
command template, and input mode. Runtime must not infer it from the resolved
command. Full argv, environment, secret values, executable filesystem
identity, provider registry contents not selected for the call, and
unobservable remote-provider state are excluded. Session command variants and
session modes are absent because direct fragment-backed `provider-result` has
no session authoring route; a future fragment-backed operation must version
this role before adding them.

A change in this role classifies as `provider_policy_drift`.

## Evidence Record And Publication

Target 2.22 publishes
`workflow_prompt_fragment_snapshot.functional.v2`. It retains every v1 field
and semantic validation rule, changes only the schema token, and adds required
`prompt_attempt_identity`.

The retained fields and the added identity are one closed record, not
independent claims. V2 validation first validates the exact v1 projection and
then requires these cross-field equalities before accepting the record seal:

- `prompt_attempt_identity.final_prompt` equals the retained top-level
  `final_prompt` object exactly;
- the fragment-program role's
  `compiled_prompt_fragment_identity` equals the retained top-level
  `compiled_prompt_fragment_identity`, and its identity-schema token equals
  the already validated paired compiler fragment contract; and
- the resolved-bindings role's document-row subsequence has exactly the same
  count and order as the retained fragment `authored_rows`; each document
  row's `value_sha256` equals the canonical transport-value digest of that
  corresponding retained row's exact `evaluated_relpath`, while its
  `renderer` and `rendered_bytes_sha256` remain null; and
- the injected-dependencies role equals the deterministic projection of the
  retained `canonical_groups` and `injection` fields exactly: exact retained
  canonical-group order, with each group's `authored_row_ids` retaining
  authored-row order, complete/truncated status, shown byte count and digest
  for every admitted shown group, followed by the retained injection position,
  block byte count, and block digest.

No alternate projection, omitted admitted group, extra role group, reordered
group, or independently resealed disagreement is valid. These cross-field
checks happen before immutable publication and again when a report or
comparison validates persisted v2 evidence.

Targets 2.20 and 2.21 continue to publish
`workflow_prompt_fragment_snapshot.functional.v1` byte-for-byte. Extern-backed
prompt dependency evidence remains unchanged and never acquires a fragment or
attempt identity.

For target 2.22 the sequence is:

1. validate compiler fragment contract, compiled identity, and Q3 carrier;
2. allocate the next ordinary counter-owned attempt ordinal;
3. resolve slots and take the existing one-shot dependency snapshot;
4. compose the exact prompt while retaining the in-memory segment trace;
5. prepare the exact provider invocation and its closed policy projection;
6. build and validate the v2 snapshot;
7. publish it immutably at the deterministic scope-and-ordinal path; and
8. launch the provider.

Publication failure stops before launch and leaves an ordinary allocation-only
gap, classified as `current_record_missing`. Invocation-preparation failure
has no resolved policy and does not invent a v2 identity. Instead it publishes
one closed Q3 preparation-failure record:

```json
{
  "schema": "workflow_prompt_fragment_preparation_failure.functional.v1",
  "record_kind": "failure",
  "run": {},
  "attempt": {},
  "fragment": {
    "identity_schema_version": "compiled_prompt_fragment_identity.v1",
    "compiled_prompt_fragment_identity": "sha256:...",
    "prompt_attempt_identity_version": "workflow_prompt_attempt_identity.v1",
    "binding_plan_sha256": "sha256:..."
  },
  "failure": {
    "category": "provider_policy_unresolved",
    "phase": "invocation_preparation"
  },
  "provider_calls": {
    "preparation": true,
    "execution": false
  },
  "record_sha256": "sha256:..."
}
```

`run`, `attempt`, canonical sealing, deterministic scope-and-ordinal path,
publication, and counter consistency reuse the existing functional evidence
owners.
`fragment.identity_schema_version` is exactly v1 or v2 and must agree with the
validated compiler fragment contract and compiled identity.
`compiled_prompt_fragment_identity` and
`prompt_attempt_identity_version` must equal the receiving runtime carriers,
and `binding_plan_sha256` must equal the validated companion plan.
The remaining nested objects and literals are exact. Provider error messages,
parameters, command material, and unresolved guessed policy are not copied.
Failure-record publication failure leaves the same ordinary allocation-only
gap and never launches the provider.

Dependency resolution/read/decode/render failures retain their existing
closed `record_kind=failure` evidence and publication. They do not acquire a
fabricated Q3 identity. Q3 carrier, role, composition, or publication
validation failures use the existing provider-step failure envelope with
their exact Q3 diagnostic and produce either a published existing dependency
failure (when that owner already has one) or an allocation-only gap. Q3 adds
only the preparation-failure schema above; it does not widen the existing
dependency-failure schema.

The file path, root allocation scope, ordinal, immutable-write rule,
command-lifetime single-writer locking, and offline terminal index remain
unchanged. Allocation state carries no current lifecycle-event list. No full
prompt or role bytes are persisted.

## Comparison Contract

The Q3 comparator accepts two validated functional-v2/identity-v1 records with
the same `ProviderAttemptScope`, where
`current.ordinal > previous.ordinal`.
Report selection first chooses the greatest earlier published
`record_kind=prompt_snapshot` ordinal in that scope without skipping a newer
legacy or invalid candidate. That exact candidate must then validate as
functional-v2. A valid functional-v1 candidate yields `legacy_snapshot_only`;
an invalid candidate yields `previous_record_invalid`, even when an older
valid functional-v2 record exists.
Selection does not use filesystem order or mapping order.

For comparable records, it emits an ordered array using this fixed order:

1. `instruction_drift`;
2. `input_drift`;
3. `dependency_content_drift`;
4. `runtime_prelude_drift`; and
5. `provider_policy_drift`.

It includes one classification for every unequal role digest. If all five
role digests and the final-prompt digest are equal, the sole classification is
`prompt_context_unchanged`.

If all five role digests are equal but the final-prompt digest differs, the
records prove that the role model failed to account for prepared prompt bytes.
The comparator fails closed with diagnostic
`prompt_identity_composition_mismatch`; it must not report context unchanged
or mint a sixth drift role. This rule compares two independently validated
records only.

A record whose claimed `composition_sha256` does not equal the canonical
composition projection is simply invalid. Prepublication validation fails
with `prompt_attempt_identity_composition_invalid`. Report validation maps an
invalid current record to `current_record_invalid` and an invalid selected
predecessor to `previous_record_invalid`; it never reclassifies digest tamper
as a cross-record composition mismatch.

Every comparison uses one closed shape:

```json
{
  "status": "available",
  "previous_attempt_ordinal": 1,
  "classifications": ["input_drift"],
  "reason": null
}
```

For `status=available`, `previous_attempt_ordinal` is a positive integer,
`classifications` is the non-empty ordered classification array, and `reason`
is null. For `status=unavailable`, `previous_attempt_ordinal` is null,
`classifications` is empty, and `reason` is exactly one of:

- `no_predecessor`;
- `current_record_missing`;
- `current_record_invalid`;
- `previous_record_invalid`;
- `legacy_snapshot_only`;
- `provider_policy_unresolved`; and
- `prompt_identity_composition_mismatch`.

Missing/invalid records never fall back to v1 hashes, raw prompt audits,
stdout, or current provider configuration.

## Report Surface

Existing `orchestrator report` JSON retains its `run`, `progress`, and `steps`
members and adds one exact top-level sibling. Q3 originally emitted report v1;
the implemented target-2.23 phased-delivery amendment now emits the additive
report v2 shape for every DSL target:

```json
{
  "run": {},
  "progress": {},
  "steps": [],
  "prompt_context": {
    "schema_version": "workflow_prompt_context_report.v2",
    "attempts": []
  }
}
```

This is an intentional additive report/API change for reports of every DSL
target, including 2.20 and 2.21: report JSON bytes and consumers that require
an exact top-level key set must update. It is not an execution, provider,
checkpoint, resume, or evidence-format change for those targets. A report
with no qualified fragment-backed attempt still emits the exact
`prompt_context` object above with `attempts=[]`; the field is not target
gated, so one run containing multiple target versions has one stable report
shape.

The report qualifies a provider-attempt scope as fragment-backed only from:

- at least one strictly validated functional-v1/v2/v3 fragment snapshot in
  that scope;
- at least one strictly validated existing failure record whose compiler
  contract origin is `workflow_lisp_prompt_fragment`; or
- at least one strictly validated Q3 preparation-failure record in that scope.

It does not infer operation kind from a runtime-step name, path spelling,
record kind alone, or an unvalidated schema claim. `prompt_context.attempts`
then has exactly one row for every allocated ordinal in each qualified scope.
An entirely unqualified allocation scope is omitted fail-closed rather than
misreported as a fragment attempt. Rows use the terminal prompt-index order
already defined by `(runtime_step_id UTF-8 bytes, visit_key,
attempt_ordinal)`. A running report derives the same ordered projection
read-only from persisted allocator state and run-owned evidence; it does not
persist or require a terminal index.

Every attempt row has this one closed shape:

```json
{
  "runtime_step_id": "step",
  "visit_key": "0123456789abcdef01234567",
  "attempt_ordinal": 2,
  "record_status": "snapshot",
  "record_sha256": "sha256:...",
  "identity": {
    "identity_version": "workflow_prompt_attempt_identity.v1",
    "composition_sha256": "sha256:...",
    "legacy_final_prompt_sha256": "sha256:...",
    "canonical_composed": null,
    "actual_deliveries": null,
    "role_sha256": {
      "fragment_program": "sha256:...",
      "resolved_bindings": "sha256:...",
      "injected_dependencies": "sha256:...",
      "runtime_contributions": "sha256:...",
      "provider_policy": "sha256:..."
    }
  },
  "comparison": {
    "status": "available",
    "previous_attempt_ordinal": 1,
    "classifications": ["input_drift"],
    "reason": null
  }
}
```

The exact `record_status` cases are:

| `record_status` | `record_sha256` | `identity` | `comparison` |
| --- | --- | --- | --- |
| `snapshot` | validated functional-v2/identity-v1 or functional-v3/identity-v2 record digest | exact validated versioned digest projection | available against the selected same-version predecessor, or unavailable with a closed reason |
| `legacy_snapshot` | validated functional-v1 record digest | null | unavailable / `legacy_snapshot_only` |
| `failure` | validated failure-record digest | null | unavailable / `provider_policy_unresolved` for the exact Q3 preparation-failure schema; otherwise `current_record_missing` |
| `allocation_only` | null | null | unavailable / `current_record_missing` |
| `invalid` | null | null | unavailable / `current_record_invalid` |

The row keys never vary. `record_sha256` and `identity` use JSON null exactly
where the table says null. An invalid publication may retain its validated
scope and ordinal for ordering, but the report does not repeat an
unvalidated claimed record digest. If a current valid functional-v2/v3
snapshot has a greatest earlier prompt-snapshot publication in the same scope,
that exact candidate must validate under its claimed schema before comparison.
An invalid candidate yields `previous_record_invalid`; a valid functional-v1
candidate yields `legacy_snapshot_only`; and an identity-v1/identity-v2 pair
uses the amendment's `identity_version_mismatch`. Failure publications and
allocation-only gaps are not prompt-snapshot predecessor candidates and are
skipped when selecting the greatest earlier prompt snapshot.

The Markdown view renders a `Prompt context` section after the ordinary steps,
with the same attempt order, record-status labels, role labels, and comparison
classifications. It does not render prompt text, values, dependency content,
commands, or environment.

Because publication occurs before launch, report may expose this object for a
running/hanging attempt. The report also shows the attempt's existing runtime
status; prompt evidence does not infer that the provider is alive, hung,
successful, or correct. It also does not infer dispatch, receipt, or that a
provider/model read any prepared byte.

The report path performs strict projection and record validation. A missing,
invalid, legacy, failed, or allocation-only current record uses the same
closed unavailable comparison shape while preserving the rest of the run
report. Runtime and resume do not import or call the report comparator.

## Diagnostics

The closed Q3 refusal set is:

| Code | Refusal | Owner |
| --- | --- | --- |
| `prompt_attempt_identity_version_missing` | target-2.22 fragment-backed call lacks the carrier in typed/semantic/executable/persisted/runtime configuration | dropped carrier |
| `prompt_attempt_identity_version_invalid` | carrier is not the exact v1 token | malformed carrier |
| `prompt_attempt_identity_version_mismatch` | compiler/IR/runtime carriers differ | disagreeing carrier boundary |
| `prompt_attempt_binding_plan_missing` | target-2.22 fragment-backed call lacks the companion plan or digest | dropped carrier |
| `prompt_attempt_binding_plan_invalid` | plan schema, row, locator, agreement, or digest validation fails | offending plan row/contract boundary |
| `prompt_attempt_binding_plan_mismatch` | compiler/IR/persisted/checkpoint/runtime plans or digests differ | disagreeing carrier boundary |
| `prompt_attempt_identity_role_invalid` | a role is open, malformed, misordered, or has a digest mismatch | offending role/row |
| `prompt_attempt_identity_policy_invalid` | prepared invocation lacks a closed effective policy projection | provider application |
| `prompt_attempt_identity_final_prompt_mismatch` | composed bytes and prepared invocation prompt bytes disagree | provider application/composition boundary |
| `prompt_attempt_identity_composition_invalid` | one record's claimed composition digest does not match its canonical composition projection | record construction/validation |
| `prompt_identity_composition_mismatch` | two independently valid records have equal role digests but different final-prompt digests | comparison |

Compiler carrier failures use the existing source-map provider-application
owner. Runtime evidence failures use the existing provider-step failure
envelope and stop before launch. Report-only comparison unavailability does
not mutate run state.

## Resume And Compatibility

Q3 does not make evidence authoritative:

- compatible completed-result reuse applies the existing source, root,
  call-frame, bound-input, checkpoint, result-contract, and completed-boundary
  guards and returns the committed result without preparing a provider or
  reading prompt evidence;
- a pending or failed boundary allocates a fresh attempt and creates fresh
  version-appropriate identity evidence before provider launch;
- a missing or damaged evidence file does not invalidate an otherwise
  compatible completed result;
- the optional identity carrier and binding plan participate in ordinary
  target-2.22 program/checkpoint compatibility, but role digests do not; and
- the comparator/report never settles, cancels, resumes, or retries an
  attempt.

Targets below 2.22 preserve their existing artifact, runtime, checkpoint,
state, and evidence bytes. A target-2.22 runtime must not silently emit v1
evidence for a fragment-backed attempt.

## Implemented Target-2.23 Phased-Delivery Amendment

Target 2.23 preserves the complete Q3 role model and binding-plan authority
while adding one versioned distinction for explicit phased delivery:

- omitted and explicit composed calls retain
  `workflow_prompt_attempt_identity.v1` inside
  `workflow_prompt_fragment_snapshot.functional.v2`;
- explicit phased calls require `workflow_prompt_attempt_identity.v2` inside
  `workflow_prompt_fragment_snapshot.functional.v3`;
- identity v2 replaces the v1 delivered-final-prompt claim with separate
  `canonical_composed {bytes, sha256}` and ordered `actual_deliveries`; a
  requested or offered turn is not actual delivery until its durable receipt;
- functional-v3 validates every delivery row and the v2 composition seal
  without persisting prompt or candidate content; and
- a composed/phased identity-evidence mismatch fails before provider start.

The current report projection is
`workflow_prompt_context_report.v2`. Every non-null identity has the fixed
keys `identity_version`, `composition_sha256`,
`legacy_final_prompt_sha256`, `canonical_composed`, `actual_deliveries`, and
`role_sha256`. V1 rows populate only the legacy final-prompt field; v2 rows
populate only canonical composition and actual deliveries. There is no
`final_prompt_sha256` field that could misdescribe canonical `C` as one
delivered turn.

Predecessor selection retains Q3 scope/ordinal rules but comparison is
version-strict. A v1/v2 pair is unavailable with
`identity_version_mismatch`. V2 adds only
`actual_delivery_drift` after the five existing role classifications and
canonical composition agree. Report v2 remains provenance only and does not
change execution, result, checkpoint, retry, or resume authority. The exact
v2 record and projection schemas are owned by
`workflow_lisp_phased_contract_delivery.md`.

## Principle 29 And Type Parsimony

Q3 adds no Workflow Lisp type, nominal prompt brand, outcome union, or authored
taxonomy. Identity roles are closed persisted evidence records because exact
field names are load-bearing for cross-attempt comparison. They do not become
source-language values.

Comparison outcomes use the existing report failure/data channel, not a new
DSL result union. Q4 may consume validated provenance through its separately
reviewed inspection design, but Q3 does not pre-design a judgment value.

## Non-Goals

Q3 does not add:

- search, mutation, fitness, candidate selection, or prompt optimization;
- an experiment registry or revival of the parked evolution roadmap;
- prompt values, partial fragment application, nested fragments, or dynamic
  fragment collections;
- coordinated-provider fragment applications;
- arbitrary non-fragment provider-call identity;
- prompt-body persistence or display;
- runtime breakpoints, live steering, or failure streaming;
- semantic prompt checking;
- new result, checkpoint, or resume authority;
- nominal types or mandatory type annotations; or
- Q4 judgment views.

## Implementation Ownership

The likely implementation surface is:

- new `orchestrator/workflow/prompt_identity.py` for closed roles, canonical
  digests, v2 validation, and pure comparison;
- `orchestrator/workflow/prompt_fragment_contract.py` plus the existing
  prompt-fragment carrier types for the companion declaration-ordered binding
  plan and its Core/Semantic/Executable IR, persisted-surface, checkpoint,
  runtime-step, classic, and WCC carriage;
- `orchestrator/workflow/prompting.py` for the target-gated one-render
  fragment trace covering text, value, and path slots;
- the fragment typed-input evidence owner for target-2.22 derivation from the
  same trace without a second renderer call, while preserving the existing
  typed-input evidence schema;
- `orchestrator/workflow/prompt_dependency_evidence.py` for v2 snapshot
  construction/publication through the current attempt allocator;
- the existing prompt composer for an immutable segment trace;
- `orchestrator/providers/types.py` and
  `orchestrator/providers/executor.py` for the closed prepared-policy
  projection;
- `orchestrator/workflow/executor.py` for target-2.22 preparation ordering and
  prelaunch publication; and
- existing CLI/report projection modules for read-only diagnostics.

Q3 must not modify LSP state, driver, navigation, or server paths owned by the
concurrent L2 plan.

## Verification

Acceptance requires both-direction evidence for:

- target 2.22 admission and below-target rejection;
- exact optional identity carrier and binding plan through classic and WCC
  IR/persistence/checkpoint paths, including missing/invalid/mismatch
  failures;
- binding-plan declaration order, doc/non-doc interleaving, refinement,
  output role, renderer/null renderer, source-locator coverage, plan digest,
  and exact agreement with Q1/Q2 contracts in both lowering routes;
- one-render trace coverage for text/value/path, including strict UTF-8 text,
  raw renderer digest, exact one-LF removal for value/path substitution,
  repeated placeholders without re-render, and every trace mismatch;
- a renderer call counter proving each target-2.22 value/path slot is rendered
  exactly once even when typed-input evidence is emitted; exact reuse of the
  trace value/raw-renderer digests; both trace-to-evidence and
  evidence-to-trace missing/extra/reordered/mismatch failures; and text trace
  coverage without typed-input evidence;
- byte-identical target-2.20/2.21 compiled identities, fragment contracts,
  snapshots, checkpoints, and completed-boundary reuse;
- closed-schema rejection for every extra/missing/malformed role field;
- exact v2 cross-field equality between the identity and retained v1
  final-prompt, compiled-fragment, document-authored-row,
  canonical-group-order/membership, and injection projections, with a
  separately resealed mismatch for every relation rejected both during
  publication and persisted-record report validation;
- role digest tampering and composition digest tampering;
- declaration-order resolved bindings and no unused lexical/import inputs;
- every slot kind, refinement, renderer, output role, and per-slot rendered
  byte digest;
- document rows proving `renderer=null`, canonical evaluated-relpath value
  identity, and content identity only in the dependency role;
- a template-only change proving instruction drift without input drift, and a
  binding-only change proving input drift without instruction drift;
- dependency complete/truncated/omitted cases proving only prepared prompt
  bytes and summaries affect identity;
- each runtime contribution independently present/absent/changed and exact
  consumed-artifact-before-output-position-before-structured-result order;
- consumed-artifact injection disabled/empty/no-shown-value negative cases,
  prepend and append positive cases, exact separator-inclusive segment
  bytes/digest from one composer call, value/policy/position changes producing
  only `runtime_prelude_drift`, and missing/extra/reordered/position/digest
trace rows failing before publication;
- no provider-session positive case in the direct fragment-backed v1 surface;
- provider/model/effort/timeout/input-mode changes, derived from the exact
  prepared invocation rather than argv parsing;
- publication after successful invocation preparation and before launch;
- preparation/publication failure with zero provider launches, including the
  exact closed Q3 preparation-failure record for unresolved policy, tampering
  of every field in that record, and an allocation-gap negative control that
  remains `current_record_missing`;
- every single-role and multi-role comparison in fixed order;
- equal-role/final-prompt mismatch failing as
  `prompt_identity_composition_mismatch`;
- composition-digest tamper producing an invalid current/predecessor record,
  never cross-record mismatch;
- no-predecessor, missing, invalid, legacy-only, and unresolved-policy
  comparison unavailability;
- a newer legacy or invalid predecessor proving report selection does not skip
  backward to an older valid v2 snapshot;
- exact top-level report projection and closed snapshot, legacy, failure,
  allocation-only, invalid, available, and unavailable rows for running,
  failed, and completed runs, with no bodies/values;
- runtime/resume independence from evidence/comparison;
- the intentional additive `prompt_context` report key for target-2.20,
  target-2.21, target-2.22, mixed-target, and no-qualified-attempt runs while
  all below-target compiler/runtime/checkpoint/provider/evidence bytes remain
  unchanged;
- one deterministic retry E2E with independently changed roles; and
- the roadmap's broad non-security gate plus ordered specification then quality
  review.

## Rejected Alternatives

### Expand `compiled_prompt_fragment_identity`

Rejected because program identity and resolved attempt context have different
lifetimes and compatibility obligations. It would also perturb Q1/Q2 bytes.

### One flat final-prompt hash

Rejected because it cannot distinguish instruction, input, dependency,
runtime-prelude, and provider-policy drift.

### Parse the final prompt into roles

Rejected because the runtime already owns composition segments and parsing
would create a second, brittle prompt grammar.

### Hash full dependency files

Rejected because truncated-away or omitted content not selected into the
prepared prompt must not create dependency-content drift.

### Hash argv or environment

Rejected because the resolved invocation already has the required closed
policy fields and command parsing is provider-specific and unstable.

### Use evidence as resume or result authority

Rejected because prompt snapshots are non-authoritative provenance; completed
result reuse and provider retry already have separate runtime contracts.

### Include all provider operations immediately

Rejected because only direct `provider-result :prompt` accepts a fragment
application today. Capability must follow a real consumer, not imply uniformity
over operations with different prompt composition.
