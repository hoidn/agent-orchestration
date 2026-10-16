# Provider JSON Contract Rendering Implementation Plan

> **For agentic workers:** Use `superpowers:subagent-driven-development` and
> `superpowers:verification-before-completion`. The coordinator integrates and
> verifies; a reviewer distinct from the author reviews the resulting change.

**Goal:** ordinary evaluated provider calls show the selected file action and
one nested, typed JSON shape, without compiler aliases or displayed JSON
pointers. Each call renders its own return contract.
**Architecture:** add rendering `file/2` to the existing delivery selection and
replay mechanism. Render the checked result descriptor through the existing
transport-schema converter, attaching the validated contract's guidance and
constraints at their actual fields. Leave existing renderers byte-identical.
**Tech stack:** existing Python, `json`, pytest and deterministic CLI fixtures;
no dependency, DSL version, transport, persistent field or configuration option.
**Status:** Implemented and independently reviewed. The
[execution report](../reports/2026-10-13-provider-json-rendering.md) records
403 affected tests, 53 additional consumer tests, public run/resume and frozen
historical hashes. The native CLI campaign proceeded independently.
**Tradeoff:** complete union alternatives repeat common fields. All three
rendering versions remain replay obligations; subsequent presentation changes
need another version. A new transportable type will need a shape-rendering case.

## Decisions and authority

Read `docs/index.md`, `docs/capability_status_matrix.md`,
`docs/design/README.md`, then `specs/providers.md` (delivery, guidance as data,
direct-root `Value`), `specs/state.md` (provider input parts/replay),
`docs/design/provider_result_delivery.md`, and
`docs/design/workflow_lisp_native_transportable_returns.md` (root and guidance
wire contracts). These own the behavior; this plan selects a presentation.

The user authorized the presentation improvement independently of the native
session experiment. That experiment uses hand-authored CLI prompts and native
JSON Schema; neither completing it nor interpreting its results depends on
this renderer. Session identity, queues, agent scheduling and transport changes
are outside this plan. OMP keeps `legacy` and its existing parent-materialized
text transport. Coordinate edits to `evaluated/providers.py` and its delivery
tests with the separate OMP correction; do not overwrite that work.

**Chosen representation:** a single JSON-shaped **type notation**, explicitly
labelled as a shape, not an example or copyable JSON document. Unlike a JSON
example populated with guessed values, type markers explicitly distinguish
placeholders from authored data. Unlike a JSON Schema dump, it exposes the result's real nesting
without `properties`/`required`/extension machinery. No generic JSON Schema
converter exists in the relevant contract/provider owners; adding one would
also require nonstandard path/existence annotations.

Illustrative rendered block; wording is not a test oracle:

```text
## Output Contract
Write the JSON result to the file on the path line using a file-writing or shell
tool before finishing. ORCHESTRATOR_OUTPUT_BUNDLE_PATH names that same target.
- path: .orchestrate/runs/<run>/effects/<effect>/attempt-1/result.json
JSON shape, not an example: <...> denotes a type; | chooses one alternative;
... denotes zero or more entries. Comments are contract annotations, not output.
{
  "evidence": {
    "notes": <string>
  },
  "report": <relpath> // {"under":"artifacts/review","must_exist_target":true}
                     // workspace-relative; include the declared under prefix
}
```

The actual result path appears once, on the existing R3 `- path:` line. Keep
the file action first and the warning that assistant text does not deliver the
ordinary result. JSON-encode all authored keys, tags and annotation values;
never interpolate authored multiline guidance into instruction prose.

| Contract | Shape rule |
| --- | --- |
| `bool`, `integer`, `float`, `string` | `<boolean>`, `<integer>`, `<finite number>`, `<string>`; root scalars stay roots, without an object wrapper. These request the declared types; existing coercion/normalization is unchanged. |
| `enum` | JSON-quoted allowed values separated by `|`, preserving allowed order. |
| `relpath` | `<relpath>` with its own `under`, `must_exist_target` and workspace-relative/prefix note. No global path note; no note for an unrelated string. |
| `optional` | `null | <item shape>`; do not conflate nullable with omittable. At an extracted contract field, preserve existing missing-optional behavior explicitly; `required: false` remains an omission annotation. A nullable field inside a direct structural record still requires its key. |
| `list`, `map` | `[<item shape>, ...]`, `{<string key>: <value shape>, ...}`. The legend defines zero or more; no invented sample key, cardinality or value. Recurse through every container. |
| `record` | JSON-quoted actual field keys and nested objects, including empty `{}` records. Never split generated names on `__`. |
| `union` | Parenthesized complete object alternatives separated by `|`, in discriminant order. Each includes its literal tag and shared plus active-variant fields. Nested unions use the same notation. Repeating common fields avoids a second merging language or misleading envelope. |
| `Value` | `<strict JSON value>` at the actual position/root. No narrowing, invented fields, envelope, `__result__`, or example. |

Attach description, format hint and **only authored** example data as JSON
comment annotations at the corresponding node. Preserve null/false examples.
Bundle guidance remains root guidance, separately from root-field guidance;
never import overall workflow `result_guidance`. Decode RFC 6901 internally
(`~1` then `~0`); guidance contexts attach to ancestor objects. Deduplicate
identical ancestor payloads in first-seen order, but retain distinct payloads
without overwriting. For a shared field, select its `guidance_by_variant`
payload for each displayed alternative; missing variant guidance stays absent.
Preserve shallow-to-deep context order and discriminant order. Authored strings
may themselves contain pointer-like text; only generated pointer metadata and
compiler aliases disappear. Keep nominal type names suppressed on this ordinary
evaluated route, as today. Preserve all guidance present in the checked payload;
do not invent guidance that existing compiler flattening omitted for empty
records or change that compiler behavior in this presentation task.

A read-only feasibility check on 2026-10-13 confirmed that the existing
transport-schema converter preserves nested records, empty records and `Value`
(Python exit 0); `commands.py::_restore_record_containers` already uses the
same checked result descriptor to restore the otherwise missing containers.

## Bounded implementation

### 1. Freeze compatibility and prove the projection

**Files:** `tests/fixtures/provider_delivery_file1/` (new frozen run and README),
`tests/test_workflow_evaluated_resume_replay.py`,
`tests/test_prompt_contract_json_shape.py` (new).

- [x] Before renderer edits, capture an interrupted ordinary public CLI run
  committed under `file/1`, using the existing pre-change fixture's shim and
  kill helper. Retain actual memo/program/header and committed attempt bytes;
  record hashes and capture command. Do not manufacture a memo or refresh the
  historical `tests/fixtures/provider_delivery_pre_change/` fixture.
- [x] Freeze root/record/union `legacy` and `file` prompt bytes for fixed
  representative payloads. Byte comparisons here prove replay identity, not
  preferred wording.
- [x] Add focused behavioral cases covering the table, nested/empty records,
  literal names containing `__`, `/`, `~`, quotes and newlines, all guidance
  scopes, differing shared guidance, nullable versus omittable, and no input
  mutation. Use compiled checked nodes for the ordinary route.

### 2. Render the shape on the new branch

**Files:** `orchestrator/contracts/prompt_json_shape.py` (new private helper;
the historical `prompt_contract.py` remains untouched),
`orchestrator/contracts/prompt_delivery.py`,
`orchestrator/workflow/evaluated/prompts.py`;
tests: the new shape module and `tests/test_workflow_evaluated_prompts.py`.

- [x] In `_output_contract_prompt`, branch on the new selector `file/2` and
  call one bounded structured-result renderer with the checked contract,
  `node["result"]` and the concrete result path. Existing branches and default
  `legacy` remain untouched. Keep `expected_outputs` insertion/order unchanged.
- [x] Reuse `transport_schema_for_descriptor(...,
  allow_nested_structures=True)` from `orchestrator/workflow/type_descriptor.py`.
  It supplies all nested structure, including empty records absent from the
  flattened payload. Overlay the validated payload's field constraints and
  guidance by decoded paths, recursively through nested schema nodes, then
  emit the notation above. Keep this projection private to the renderer; no
  new public schema model, parser, validator or compiler output.
- [x] Add a separate `file/2` opening, without altering `_LEGACY`, `_FILE`,
  `RELPATH_GUIDANCE`, their walk, or any old rendering helper. Test structural
  projection, encoded annotation data, root kind, actual keys, variant data and
  single path/block placement; do not assert literal instructional prose.
- [x] Verify rendered representative values through the existing validator,
  including enum/variant rejection, path bounds/existence and nonfinite numbers.
  Do not parse the type notation back into values or create another validator.

### 3. Select, replay and keep the census readable

**Files:** `orchestrator/workflow/evaluated/providers.py` (selector table and
docstring only), `orchestrator/workflow/evaluated/effect_inputs.py`,
`scripts/provider_delivery_census.py`; tests:
`tests/test_workflow_evaluated_provider_delivery.py`,
`tests/test_workflow_evaluated_providers.py`,
`tests/test_workflow_evaluated_resume_replay.py`,
`tests/test_provider_delivery_census.py`,
`tests/workflow_evaluated_consumer_sources.py` (stale commentary).
The shared consumer comparison also reconstructs and checks the selected
contract before normalizing it to the historical presentation. Its callers
are verified in `test_workflow_evaluated_consumers.py`,
`test_workflow_evaluated_phase6a_pilot.py` and
`test_workflow_evaluated_artifact_freshness.py`.

- [x] Register `"file/2": "file/2"` beside `legacy` and `file/1`; choose it
  for new ordinary attempts, leaving OMP on `legacy`. Existing absent-part,
  known-digest and unknown-digest replay rules do not change. New `prompt` and
  `delivery` digests change; declarations, result paths and memo wire do not.
- [x] Resume both frozen legacy and file/1 runs: reuse old commits without
  dispatch or byte drift; the pending ordinary effect records `file/2`.
  Resume a completed file/2 run twice with unchanged memo and request bytes.
  Preserve unknown-digest refusal before launch and OMP's legacy digest.
- [x] Update default-version assertions and request parity helpers to compare
  only the appropriately selected contract blocks; preserve explicit tests
  of historical versions. Add `file/2` to the census's existing name list and
  test the digest/name mapping without changing aggregation behavior.

### 4. Document and verify the complete route

**Files:** `specs/providers.md`, `specs/state.md`,
`docs/design/provider_result_delivery.md`, and their existing routing rows in
`docs/index.md` / `docs/design/README.md` only if wording becomes stale.
Integration found two additional claims to update: `specs/versioning.md`
names `file/1` as current, and three parity rows in
`docs/design/workflow_lisp_evaluated_execution.md` limit differences to opening
lines. Update those exact passages and the capability matrix's rendering row;
preserve unrelated edits in these shared documents.

- [x] State the current nested presentation, direct-root exception, guidance
  placement and versioned replay. Qualify existing pointer-oriented prompt
  descriptions as historical rendering; keep wire-schema and validator
  contracts intact. Explain future byte changes require another selector.
- [x] Run collection on added/renamed tests, then focused new cases and frozen
  replay cases before broader checks. Required public smoke: compile/run a
  fake-provider program returning a guided nested record and tagged union,
  inspect actual `prompt.txt`/result/memo, then resume with zero extra dispatch.
  Use each call's own contract; no real provider or session experiment needed.
- [x] Run the affected suites below in tmux with the `tmux` skill; inspect
  exits and diff yourself, and obtain independent code/contract review.

```bash
pytest --collect-only -q tests/test_prompt_contract_json_shape.py tests/test_workflow_evaluated_prompts.py tests/test_workflow_evaluated_resume_replay.py tests/test_workflow_evaluated_provider_delivery.py tests/test_workflow_evaluated_providers.py tests/test_provider_delivery_census.py
pytest -q tests/test_prompt_contract_json_shape.py
pytest -q tests/test_workflow_evaluated_resume_replay.py -k 'provider_commit or delivery or pre_change or file1'
pytest -q tests/test_workflow_evaluated_provider_delivery.py -k 'public'
pytest -q -n 16 --dist=worksteal tests/test_prompt_contract.py tests/test_prompt_contract_json_shape.py tests/test_prompt_contract_recursive_schema.py tests/test_prompt_contract_injection.py tests/test_workflow_evaluated_prompts.py tests/test_workflow_evaluated_providers.py tests/test_workflow_evaluated_provider_delivery.py tests/test_workflow_evaluated_resume_replay.py tests/test_workflow_evaluated_public_identity.py tests/test_workflow_lisp_result_guidance_e2e.py tests/test_workflow_lisp_native_returns_e2e.py tests/test_provider_delivery_census.py
git diff --check
```

Completion requires fresh command results, unchanged historical prompt/run
hashes, successful public run/resume, and inspection of the new prompt for a
nested record, union, path and root `Value`. Human readability and provider
success-rate improvement remain observational claims; deterministic checks
establish contract fidelity and replay, not model compliance.
