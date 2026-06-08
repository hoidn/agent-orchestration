# Generic Review/Revise `.orc` Runtime Gap Report

Status: investigation report
Created: 2026-06-08
Scope: gaps exposed while launching `workflows/examples/review_revise_design_docs.orc`
Target run: `20260608T225644Z-pcxb4n`
Target design doc: `docs/design/workflow_lisp_runtime_migration_foundation.md`

## Summary

The generic review/revise design-doc workflow exposed real runtime contract
gaps, not just Workflow Lisp frontend bugs.

The largest issue is that the frontend now lowers richer typed Workflow Lisp
values into ordinary executable workflow surfaces, but the runtime contract for
some of those surfaces still assumes the older authored-YAML model:

- artifact registry values are mostly `relpath` or scalar;
- `materialize_artifacts.pointer` is only a relpath pointer;
- `consumes` accepts only `relpath` or scalar artifacts;
- collection schemas appear only inside private frontend-lowered output
contracts, not as first-class internal dataflow values.

Those assumptions are too narrow for generic `.orc` workflows that pass lists,
records, and typed prompt-input bundles through stdlib review loops. Fixing this
only in the Lisp frontend would hide the problem by generating around runtime
limitations. The principled fix is to make the runtime and specs explicitly
support the internal lowered value shapes that Workflow Lisp is allowed to
produce, while keeping authored YAML compatibility restrictions where intended.

There are also two provider/authoring gaps. First, prompt externs used by
`.orc` provider forms currently lower to `asset_file`, so extern values must be
workflow-source-relative bundled assets. That is valid under the current
`asset_file` contract, but it is surprising for generic workflows whose prompt
extern manifest names workspace-root prompt files. The frontend should either
document and enforce bundled prompt externs or expose a way to choose
workspace-relative `input_file` prompt externs.

Second, provider structured-output bundle paths are still prompt-owned in
practice. The review provider was shown the correct `variant_output.path`, but
it wrote a valid bundle to a directory-style sibling path. Runtime validation
correctly rejected the run, but the failure shows that provider structured
output lacks the out-of-band path authority that command structured output
already has through `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`.

## Evidence

The generic workflow was launched with:

```text
workflows/examples/review_revise_design_docs.orc
target_doc = docs/design/workflow_lisp_runtime_migration_foundation.md
context_docs =
  docs/design/workflow_lisp_key_migration_parity_architecture.md
  docs/design/workflow_command_adapter_contract.md
  docs/design/workflow_lisp_state_layout.md
```

Early dry-runs passed, but live execution exposed failures before the provider
step could run. The failures were runtime/executable-contract failures, not
parse or typecheck failures.

Focused regression checks added during investigation:

```bash
pytest tests/test_output_contract.py::test_validate_contract_value_accepts_json_string_list_contracts -q
pytest tests/test_v214_runtime_semantics.py::test_materialize_artifacts_writes_pointer_for_string_input -q
pytest tests/test_dataflow.py::test_enforce_consumes_contract_accepts_collection_artifacts -q
```

The live run eventually reached provider execution after the runtime gaps were
patched locally and prompt assets were moved onto the valid workflow-source
asset surface. The provider then returned `REVISE` and wrote the review report
and findings, but the run failed post-execution because the structured result
bundle was written to the wrong file path.

## Gap 1: Collection Contract Values Cross Runtime Boundaries

### Failure

The generated stdlib review loop materialized `context_docs` as a
`List[DesignDocPath]`. Runtime validation then hit collection contract shapes
that were valid in frontend-lowered executable IR but not accepted consistently
by runtime validators.

Two concrete problems appeared:

- executable IR freezes nested contract definitions as mapping-proxy objects,
  while output-contract validation accepted only plain `dict` nested schemas;
- structured joins can carry list/map values as JSON strings, while
  `validate_contract_value` treated non-string collection values differently
  from string collection payloads.

### Layer Ownership

This is a runtime contract/design gap.

Workflow Lisp should be allowed to lower typed collections into private
executable contracts. Once the executable workflow is accepted by shared
validation, runtime validators must accept the same schema family. The frontend
should not have to flatten lists into ad hoc relpath pointer files or encode
lists as report prose.

### Required Design Clarification

`specs/dsl.md` currently keeps `kind: collection` unavailable to ordinary
authored YAML boundaries except where frontend-lowered workflows are explicitly
allowed. That split is fine, but the runtime design should say:

- collection contracts are valid internal/private executable contracts for
  frontend-lowered workflows;
- runtime validators must treat immutable mapping schemas and plain mapping
  schemas equivalently;
- list/map values may arrive as native JSON values or JSON string payloads at
  join/materialization boundaries;
- validation must normalize nested relpaths through the same output-contract
  logic used by structured bundles.

## Gap 2: `materialize_artifacts.pointer` Is Too Narrow

### Failure

The generic `.orc` workflow lowers prompt-input materialization into
`materialize_artifacts` entries with pointer files for values such as:

- `target_doc` relpath;
- `context_docs` list;
- `review_focus` string;
- `checks_report` relpath;
- `review_report_target_path` relpath.

The runtime rejected non-relpath pointer materialization with:

```text
pointer_not_allowed_for_scalar
Pointers are only allowed for relpath materialization
```

### Layer Ownership

This is primarily a runtime design/spec gap.

The broader repo authority model already treats pointer files as views or
representations unless a contract says otherwise. A materialization pointer for
a string or collection value is a useful prompt/input view; it is not semantic
authority. Rejecting such pointer views forces the frontend either to avoid
materializing prompt inputs uniformly or to encode special cases by value kind.

### Required Design Clarification

The current `specs/dsl.md` v2.14 text says `pointer.path` is allowed only for
relpath materializations. That is too narrow for frontend-lowered internal
materialization.

Recommended split:

- authored YAML `materialize_artifacts.pointer` may remain conservative if that
  is desired for public surface stability;
- frontend-lowered/private materialization may write pointer views for
  validated scalar and collection values;
- pointer content for strings should be the string plus newline;
- pointer content for lists/maps should be stable JSON plus newline;
- pointer files remain views and must not become artifact authority.

This should be aligned with `docs/design/workflow_lisp_state_layout.md`: the
layout layer should own semantic allocation and pointer-view classification,
not scattered frontend/runtime helper conventions.

## Gap 3: `consumes` Rejects Collection Artifacts

### Failure

After prompt-input materialization published `context_docs`, the provider step
failed before execution:

```text
contract_violation: Consume contract failed
reason: unsupported_artifact_kind
artifact: context_docs
artifact_kind: collection
```

The shared consume manager accepted `relpath` and scalar artifacts but rejected
collection artifacts. This blocked the provider prompt step from consuming the
already-materialized list.

### Layer Ownership

This is a runtime dataflow design gap.

If frontend-lowered executable workflows can publish collection artifacts, then
runtime dataflow must be able to consume them. Otherwise generic `.orc` can
typecheck, lower, and validate, but fail at the provider boundary.

### Required Design Clarification

Runtime artifact dataflow should support collection artifacts at least for
frontend-lowered/private executable workflows:

- publish may record collection values in `artifact_versions`;
- consume must validate selected collection values against their embedded
  contract;
- `_resolved_consumes` may contain native lists/maps;
- prompt consume rendering should render collection values deterministically;
- collection consume failures should be ordinary contract violations with the
  nested validation details preserved.

This does not require making collection artifacts a normal authored YAML
surface immediately. It does require executable/runtime parity for the lowered
contract family that Workflow Lisp already emits.

## Gap 4: Prompt Externs Lower To `asset_file`

### Failure

The prompt extern manifest initially used workspace-root prompt paths:

```json
{
  "prompts.design-docs.review": "prompts/workflows/review_revise_design_docs/review.md",
  "prompts.design-docs.fix": "prompts/workflows/review_revise_design_docs/fix.md"
}
```

Live execution resolved these as workflow-source-relative `asset_file` paths
under `workflows/examples/`, producing:

```text
workflows/examples/prompts/workflows/review_revise_design_docs/review.md
```

Trying to use `../../prompts/...` failed validation because `asset_file` is not
allowed to escape the workflow source tree.

The workflow became runnable only after the generic prompt assets were placed
under:

```text
workflows/examples/prompts/workflows/review_revise_design_docs/
```

### Layer Ownership

This is mainly a Workflow Lisp frontend and authoring-model gap, not a runtime
bug.

The runtime is following the normative `asset_file` contract: asset files are
workflow-source-relative and cannot traverse outside the workflow source tree.
The gap is that `.orc` prompt externs do not make the source class obvious to
authors or launch manifests.

### Required Design Clarification

The frontend should choose and document one of these models:

1. Prompt externs are bundled assets.
   - `:prompt prompts.foo` always lowers to `asset_file`.
   - Extern manifest values must be workflow-source-relative.
   - Checked-in examples must bundle prompt files beside the workflow.

2. Prompt externs declare their source surface.
   - Manifest entries can say `asset_file` or `input_file`.
   - Workspace-root prompt files can be used through `input_file`.
   - Bundled reusable workflow prompts use `asset_file`.

3. The frontend provides separate namespaces/forms.
   - Example: `prompt-asset` versus `prompt-input`.
   - The lowering target is explicit at the `.orc` level.

The current behavior is valid but under-documented and easy to mislaunch.

## Gap 5: Provider Structured-Output Bundle Path Is Prompt-Owned

Status: fixed in the provider invocation boundary; pending fresh end-to-end
workflow evidence.

### Failure

The review provider returned a valid-looking `REVISE` result and wrote:

```text
artifacts/review/LISP-MIGRATION-PARITY-DRAIN/review-revise-design-docs-runtime-foundation-review.md
artifacts/work/LISP-MIGRATION-PARITY-DRAIN/review-revise-design-docs-runtime-foundation-findings.json
```

It also wrote a JSON result bundle, but not to the declared
`variant_output.path`.

Runtime expected:

```text
.orchestrate/workflow_lisp/entry/20260608T225644Z-pcxb4n/review_revise_design_docs::review-revise-design-docs/__write_root__review_revise_design_docs_review_revise_design_docs__review___proc_ref_call_parametric_call_std_phase_review_revise_loop_proc_d15c114978f5_d5df4f219296_1__body__review_decision__review_1__result__result_bundle.json
```

The provider wrote:

```text
.orchestrate/workflow_lisp/entry/20260608T225644Z-pcxb4n/review_revise_design_docs::review-revise-design-docs/__write_root__review_revise_design_docs_review_revise_design_docs__review___proc_ref_call_parametric_call_std_phase_review_revise_loop_proc_d15c114978f5_d5df4f219296_1__body__review_decision__review_1__result__result_bundle/result_bundle.json
```

Runtime then failed the step with:

```text
missing_bundle_file
Variant output bundle file was not created
```

This happened after the provider made a useful review decision, so the loop did
not route `REVISE` to the fix ProcRef.

### Layer Ownership

This is primarily a runtime/spec design gap, with Workflow Lisp lowering as a
secondary consumer.

The prompt contract included the correct path, but prompt text is not a strong
authority boundary. For command steps, `specs/io.md` already says the runtime
resolves `output_bundle.path` and sets `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`; the
runtime-owned value wins over caller-provided values. Provider structured output
should have the same path-authority property.

### Required Design Clarification

Provider steps with `output_bundle.path` or `variant_output.path` now need to
receive the resolved bundle target out of band:

- runtime resolves the declared path before provider invocation;
- runtime exposes it as `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, or an accepted
  provider-equivalent reserved binding;
- runtime-owned binding wins over authored/provider-template env values;
- prompt text still describes the schema and may repeat the path, but it is not
  the only authority for the write location;
- post-execution validation remains authoritative and rejects wrong-path files.

Do not fix this by copying
`.../__result_bundle/result_bundle.json` to `.../__result_bundle.json`. That
would recover one run but preserve the weak provider-output authority boundary.

### Implemented Boundary

The provider executor call site now passes a runtime-owned
`ORCHESTRATOR_OUTPUT_BUNDLE_PATH` value for provider `output_bundle` and
`variant_output` steps. Authored provider env values with the same name are
overridden by the resolved contract path before invocation preparation.

Prompt contract text also names `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` as the
runtime-owned authoritative write target, while post-execution bundle
validation remains the semantic gate.

## Design-Level Answer

The runtime gap should be fixed at the runtime design/spec level, with a
matching frontend contract.

The split should be:

| Gap | Primary owner | Secondary owner |
| --- | --- | --- |
| collection contract validation across executable runtime boundaries | runtime/spec | Workflow Lisp lowering fixtures |
| non-relpath materialization pointer views | runtime/spec + StateLayout | Workflow Lisp lowering fixtures |
| collection artifacts in publish/consume dataflow | runtime/spec | Workflow Lisp lowering fixtures |
| prompt extern path/source semantics | Workflow Lisp frontend authoring contract | workflow examples / prompt catalog |
| provider structured-output bundle path authority | runtime/spec | provider prompt contract and Workflow Lisp lowering fixtures |

The anti-pattern to avoid is making the Lisp frontend generate increasingly
strange YAML to fit an older runtime subset. That would defeat the point of the
frontend: typed `.orc` should lower to ordinary executable surfaces, but those
surfaces must be rich enough to carry the typed values that the frontend is
allowed to express.

## Recommended Follow-Up

1. Update `docs/design/workflow_lisp_runtime_migration_foundation.md` to add a
   fourth foundation subsection for frontend-lowered typed value transport, or
   explicitly fold it into the StateLayout/runtime contract tranche.
2. Add a normative or semi-normative spec note that collection contracts are
   valid inside frontend-lowered executable workflows even if authored YAML
   boundaries keep rejecting them.
3. Decide whether non-relpath `materialize_artifacts.pointer` is allowed only
   for frontend-lowered/private workflows or for authored YAML too.
4. Add acceptance tests for:
   - collection values in output-contract validation;
   - collection artifacts in publish/consume dataflow;
   - string/list/map pointer-view materialization;
   - prompt extern values as bundled `asset_file` paths;
   - negative prompt extern traversal outside workflow source tree;
   - provider `output_bundle` and `variant_output` steps receiving runtime-owned
     structured bundle paths;
   - provider wrong-path bundle writes failing with a clear diagnostic.
5. Clarify the `.orc` prompt extern model in
   `docs/lisp_workflow_drafting_guide.md` and `workflows/README.md`.

## Acceptance Criterion For Closing This Gap

The generic design-doc review/revise workflow should be runnable with:

```bash
python -m orchestrator run workflows/examples/review_revise_design_docs.orc \
  --entry-workflow review-revise-design-docs \
  --provider-externs-file <providers.json> \
  --prompt-externs-file <prompts.json> \
  --input-file <inputs.json> \
  --stream-output
```

without frontend-specific runtime crashes, hidden prompt-path assumptions,
collection-artifact contract failures, or provider structured-output bundle
placement failures. Provider output may still request ordinary design
revisions, but the runtime should no longer fail before the review provider is
able to make a typed review decision or before the stdlib loop can route that
decision into `APPROVE`, `REVISE -> fix`, or `BLOCKED`.
