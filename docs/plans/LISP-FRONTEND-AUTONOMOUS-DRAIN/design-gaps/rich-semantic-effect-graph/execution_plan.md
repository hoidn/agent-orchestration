# Rich Semantic Effect Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the Workflow Lisp frontend and shared semantic IR so the selected semantic effect classes are explicit and queryable: resource transition, ledger update, snapshot capture, and pointer materialization.

**Architecture:** Keep frontend-owned effect inference and lowering lineage in `orchestrator/workflow_lisp/`, keep shared semantic meaning in `orchestrator/workflow/semantic_ir.py`, and reuse the existing lowered-surface -> shared validation -> semantic IR pipeline. Preserve the current generic `command_call`, `provider_call`, and `workflow_call` entries; promoted effects augment those records and must be justified only by certified-adapter metadata or validated lowered surfaces.

**Tech Stack:** Python 3, dataclasses, `orchestrator.workflow_lisp`, shared `SemanticWorkflowIR`, persisted `source_map.json`, pytest, and Workflow Lisp fixtures under `tests/fixtures/workflow_lisp/`.

---

## Fixed Inputs

Treat these as implementation authority:

- `docs/index.md`
- `docs/steering.md`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `16. Effect System`
  - `46. Validated Core Workflow AST`
  - `47. Semantic IR`
  - `59. Validation Sequence`
  - `61. Effect Validation`
  - `65. Pointer Authority Validation`
  - `74. Source Map Requirements`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `6. Lowering Contract`
  - `9. Source Spans And Diagnostics`
  - `10. Validation`
- `docs/design/workflow_lisp_effect_graph.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/rich-semantic-effect-graph/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-full-restart-20260523T081550Z/iterations/9/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-full-restart-20260523T081550Z/iterations/9/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

## Current Repo Baseline

Assume this exact starting point during execution:

- `docs/steering.md` is empty in this checkout and does not widen scope.
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json` has no events, so do not infer partial implementation from ledger state.
- `orchestrator/workflow_lisp/effects.py` currently defines only:
  `ReadEffect`,
  `WriteEffect`,
  `PublishEffect`,
  `UsesProviderEffect`,
  `UsesCommandEffect`,
  `CallsWorkflowEffect`,
  and `UpdatesStateEffect`.
- `orchestrator/workflow_lisp/typecheck.py` currently infers `resource-transition` as only `UsesCommandEffect(("apply_resource_transition",))`.
- `orchestrator/workflow_lisp/compiler.py` already registers the certified adapter `apply_resource_transition` with declared effects `("resource_transition", "ledger_update")`.
- `orchestrator/workflow_lisp/source_map.py` already persists command boundaries, core nodes, validation subjects, and executable nodes, but `CommandBoundaryLineage` does not carry declared effect names and there is no `GeneratedSemanticEffectLineage`.
- `orchestrator/workflow/semantic_ir.py` already exists, but `SemanticEffectEntry` has no `details` field and `derive_workflow_semantic_ir(...)` emits only generic `workflow_call`, `provider_call`, and `command_call` effects.
- `tests/test_workflow_lisp_effects.py` and `tests/test_workflow_lisp_source_map.py` do not exist yet.
- The proposed fixture files for this slice do not exist yet:
  - `tests/fixtures/workflow_lisp/valid/resource_transition_effects.orc`
  - `tests/fixtures/workflow_lisp/valid/phase_snapshot_effects.orc`
  - `tests/fixtures/workflow_lisp/valid/pointer_materialization_effects.orc`
  - `tests/fixtures/workflow_lisp/invalid/command_boundary_effect_promotion_invalid.orc`
  - `tests/fixtures/workflow_lisp/invalid/pointer_effect_lineage_invalid.orc`

## Hard Scope Limits

Implement only the bounded rich-effect slice selected by the work item:

- extend the frontend-local effect taxonomy with explicit promoted kinds for resource movement, ledger update, snapshot capture, and pointer materialization;
- infer promoted resource and ledger effects from authored `resource-transition`;
- persist promoted effect lineage for lowering-generated `pre_snapshot` and pointer-writing `materialize_artifacts`;
- project and validate the promoted effect entries in shared `SemanticWorkflowIR`.

Explicit non-goals:

- no runtime behavior changes for queues, snapshots, pointers, or ledgers;
- no new adapters, no new runtime-native effects, and no generic YAML effect rewrite;
- no new or renamed authored effect-clause spellings in this slice; snapshot promotion remains lowering-owned and existing authored snapshot declarations stay on `writes-snapshot(...)` until a governing design doc changes that surface;
- no pointer-authority rule changes, report parsing, shell-text inference, or pointer-as-state recovery;
- no redesign of shared Core AST, runtime plan, or source-map coverage outside the narrow promoted-effect additions.

## Non-Negotiable Contracts

Do not re-decide any of these during execution:

- keep frontend ownership in `orchestrator/workflow_lisp/` and shared semantic meaning in `orchestrator/workflow/`;
- promoted effects must augment, not replace, generic `command_call`, `provider_call`, and `workflow_call`;
- only `certified_adapter` boundaries may promote adapter-declared semantic effects in this slice;
- only allowlisted adapter effect strings become first-class shared semantic effects:
  - `resource_transition`
  - `ledger_update`
- lowering-generated promoted effects are limited to:
  - `snapshot_capture` from `pre_snapshot`
  - `pointer_materialization` from `materialize_artifacts.values[*].pointer.path`
- the plan must not add an authored `captures-snapshot` effect clause; snapshot capture remains an internal promoted effect derived from lowering, while authored snapshot declarations keep the existing `writes-snapshot(...)` spelling from the full frontend specification;
- pointer-related promoted effects remain representational metadata and never become semantic authority;
- all promoted effect ids and lineage keys must be deterministic and derived from stable workflow and step identifiers rather than list position alone.

## File Ownership

Create:

- `tests/test_workflow_lisp_effects.py`
- `tests/test_workflow_lisp_source_map.py`
- `tests/fixtures/workflow_lisp/valid/resource_transition_effects.orc`
- `tests/fixtures/workflow_lisp/valid/phase_snapshot_effects.orc`
- `tests/fixtures/workflow_lisp/valid/pointer_materialization_effects.orc`
- `tests/fixtures/workflow_lisp/invalid/command_boundary_effect_promotion_invalid.orc`
- `tests/fixtures/workflow_lisp/invalid/pointer_effect_lineage_invalid.orc`

Modify:

- `orchestrator/workflow_lisp/effects.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/source_map.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/build.py`
- `orchestrator/workflow/semantic_ir.py`
- `tests/test_workflow_lisp_resource_stdlib.py`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_semantic_ir.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_diagnostics.py`
- `tests/test_workflow_lisp_cli.py`

Modify only if a focused failing test proves the bridge is required:

- `orchestrator/workflow_lisp/__init__.py`
- `tests/workflow_bundle_helpers.py`

## Required Data Shape

Implement these contract additions exactly:

Treat these frontend-local dataclasses as internal promoted effect atoms for
effect summaries, diagnostics, lowering provenance, and shared Semantic IR
projection. They are not new authored effect-clause spellings in this tranche.

In `orchestrator/workflow_lisp/effects.py` add frontend-local atoms:

```python
@dataclass(frozen=True)
class MovesResourceEffect:
    subject: tuple[str, ...]
    from_queue: tuple[str, ...]
    to_queue: tuple[str, ...]


@dataclass(frozen=True)
class UpdatesLedgerEffect:
    subject: tuple[str, ...]
    event_name: tuple[str, ...]


@dataclass(frozen=True)
class CapturesSnapshotEffect:
    subject: tuple[str, ...]
    snapshot_kind: tuple[str, ...]
    candidate_names: tuple[str, ...]


@dataclass(frozen=True)
class MaterializesPointerEffect:
    subject: tuple[str, ...]
    pointer_path: tuple[str, ...]
    representation_role: tuple[str, ...]
```

In `orchestrator/workflow_lisp/source_map.py` extend the persisted lineage model:

```python
@dataclass(frozen=True)
class CommandBoundaryLineage:
    ...
    declared_effects: tuple[str, ...] = ()


@dataclass(frozen=True)
class GeneratedSemanticEffectLineage:
    effect_key: str
    step_id: str
    effect_kind: str
    origin_key: str
    details: Mapping[str, Any]
```

Persist `generated_semantic_effects` per workflow alongside the existing sections.

In `orchestrator/workflow/semantic_ir.py` extend `SemanticEffectEntry` additively:

```python
@dataclass(frozen=True)
class SemanticEffectEntry:
    ...
    details: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
```

Use `details` only for:

- `resource_transition`: `from_queue`, `to_queue`
- `ledger_update`: `event_name`
- `snapshot_capture`: `snapshot_kind`, `candidate_names`
- `pointer_materialization`: `pointer_path`, `representation_role`

## Task 1: Lock The Frontend Effect Taxonomy

**Files:**

- Create: `tests/test_workflow_lisp_effects.py`
- Create: `tests/fixtures/workflow_lisp/valid/resource_transition_effects.orc`
- Modify: `orchestrator/workflow_lisp/effects.py`
- Modify: `tests/test_workflow_lisp_resource_stdlib.py`

- [ ] **Step 1: Add failing tests for the internal promoted effect atoms and scope boundary**

Cover:

- direct construction/render coverage for internal
  `MovesResourceEffect`,
  `UpdatesLedgerEffect`,
  `CapturesSnapshotEffect`, and
  `MaterializesPointerEffect` atoms without widening the authored syntax;
- regression coverage that authored snapshot effect clauses still use `writes-snapshot(...)` while the internal `CapturesSnapshotEffect` atom remains lowering-owned in this tranche;
- regression coverage that authored `moves-resource`, `updates-ledger`,
  `materializes-pointer`, and `captures-snapshot` spellings remain rejected in
  this slice so the parser surface does not widen ahead of governing design
  approval;
- effect-summary merge behavior including the new atoms;
- deterministic diagnostic labels for the new effect classes;
- a typed `resource-transition` workflow fixture whose inferred effect summary includes both the generic `UsesCommandEffect` and the promoted resource and ledger atoms.

Recommended test names:

- `test_internal_promoted_effect_atoms_render_deterministically`
- `test_authored_promoted_effect_spellings_remain_invalid`
- `test_effect_summary_merge_preserves_promoted_atoms`
- `test_resource_transition_infers_promoted_effects`

- [ ] **Step 2: Run collection and the narrow selectors first**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_effects.py tests/test_workflow_lisp_resource_stdlib.py -q
python -m pytest tests/test_workflow_lisp_effects.py tests/test_workflow_lisp_resource_stdlib.py -k 'effect or resource_transition' -q
```

Expected: collection succeeds once the new module exists, and the test run
fails because the promoted effect atoms and deterministic internal renderers do
not exist yet.

- [ ] **Step 3: Implement the frontend effect atoms without widening authored syntax**

Update `orchestrator/workflow_lisp/effects.py` to:

- add the four new dataclasses to `EffectAtom`;
- keep the authored parser surface aligned with the governing spec:
  - continue rejecting `moves-resource`, `updates-ledger`, and
    `materializes-pointer` as authored clauses in this slice;
  - keep authored snapshot clauses on `writes-snapshot(...)`;
  - do not add an authored `captures-snapshot` spelling in this slice;
- render the new atoms deterministically in `render_effect_atom(...)` for
  diagnostics and internal summaries;
- keep the existing effect-summary APIs unchanged apart from supporting the new atom types.

- [ ] **Step 4: Re-run the focused selectors**

Run:

```bash
python -m pytest tests/test_workflow_lisp_effects.py tests/test_workflow_lisp_resource_stdlib.py -k 'effect or resource_transition' -q
```

Expected: PASS with the new effect taxonomy available.

## Task 2: Promote `resource-transition` During Typechecking

**Files:**

- Modify: `orchestrator/workflow_lisp/typecheck.py`
- Modify: `tests/test_workflow_lisp_resource_stdlib.py`
- Create: `tests/fixtures/workflow_lisp/invalid/command_boundary_effect_promotion_invalid.orc`
- Modify: `orchestrator/workflow_lisp/compiler.py`

- [ ] **Step 1: Add failing typecheck coverage for promoted resource and ledger effects**

Extend `tests/test_workflow_lisp_resource_stdlib.py` so `resource-transition` is required to infer:

- `UsesCommandEffect(("apply_resource_transition",))`
- `MovesResourceEffect(...)`
- `UpdatesLedgerEffect(...)`

Also add one negative case that proves only the certified adapter path may promote semantic effect names for this slice.

- [ ] **Step 2: Implement the narrow inference rule**

In `orchestrator/workflow_lisp/typecheck.py`, extend the `ResourceTransitionExpr` branch so the returned effect summary includes the promoted resource and ledger atoms alongside the existing command-boundary effect.

Use authored queue and event names directly from the already-validated transition spec. Do not infer snapshot or pointer effects here; they belong to lowering.

- [ ] **Step 3: Guard the adapter-declared effect surface**

In `orchestrator/workflow_lisp/compiler.py`, keep the compile-time allowlist narrow and explicit:

- accept `resource_transition` and `ledger_update` as promotable certified-adapter effect names for this slice;
- leave other adapter effect strings as metadata only;
- fail deterministically if this slice's tests construct a boundary that claims promoted lineage without a certified-adapter declaration.

- [ ] **Step 4: Re-run the resource stdlib selector**

Run:

```bash
python -m pytest tests/test_workflow_lisp_resource_stdlib.py -k 'resource_transition and effect' -q
```

Expected: PASS with promoted resource and ledger effects inferred only through the certified adapter path.

## Task 3: Persist Generated Semantic Effect Lineage

**Files:**

- Create: `tests/test_workflow_lisp_source_map.py`
- Create: `tests/fixtures/workflow_lisp/valid/phase_snapshot_effects.orc`
- Create: `tests/fixtures/workflow_lisp/valid/pointer_materialization_effects.orc`
- Create: `tests/fixtures/workflow_lisp/invalid/pointer_effect_lineage_invalid.orc`
- Modify: `orchestrator/workflow_lisp/lowering.py`
- Modify: `orchestrator/workflow_lisp/source_map.py`
- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `tests/test_workflow_lisp_phase_stdlib.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] **Step 1: Add failing lineage and source-map tests**

Cover these contracts before implementation:

- `CommandBoundaryLineage` persists certified-adapter `declared_effects`;
- `generated_semantic_effects` is emitted per workflow and survives JSON serialization;
- lowering records one `snapshot_capture` lineage entry for each generated `pre_snapshot`;
- lowering records one `pointer_materialization` lineage entry for each generated pointer write in `materialize_artifacts`;
- ordinary materialization without `pointer.path` does not emit promoted pointer lineage;
- invalid promoted lineage referencing an unknown step or origin key fails with a deterministic source-map diagnostic.
- keep the valid smoke fixture entry workflow name stable as `orchestrate` so Task 5's real orchestrator compile command is deterministic.

Recommended selectors:

- `tests/test_workflow_lisp_source_map.py`
- `tests/test_workflow_lisp_phase_stdlib.py -k 'pre_snapshot or materialize'`
- `tests/test_workflow_lisp_build_artifacts.py -k 'source_map'`

- [ ] **Step 2: Run collection and the narrow failing selectors**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_build_artifacts.py -q
python -m pytest tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_build_artifacts.py -k 'source_map or pre_snapshot or materialize' -q
```

Expected: FAIL because the current source-map model has no `declared_effects` or `generated_semantic_effects`.

- [ ] **Step 3: Extend lowering provenance and source-map serialization**

Implement the lineage plumbing in `orchestrator/workflow_lisp/lowering.py` and `orchestrator/workflow_lisp/source_map.py`:

- add `declared_effects` to command-boundary lineage from existing certified-adapter bindings;
- add `GeneratedSemanticEffectLineage` records for:
  - `pre_snapshot` -> `snapshot_capture`
  - `materialize_artifacts.values[*].pointer.path` -> `pointer_materialization`
- derive stable effect keys from `step_id` plus semantic surface, for example:
  - `snapshot:<step_id>:<name>`
  - `pointer:<step_id>:<value_name>`
- validate that every promoted lineage entry resolves to an existing step id and origin key inside the workflow source-map document.

- [ ] **Step 4: Keep build emission deterministic**

Update `orchestrator/workflow_lisp/build.py` only as needed to carry the richer source-map payload through artifact emission unchanged. Do not introduce a second effect artifact.

- [ ] **Step 5: Re-run the focused selectors**

Run:

```bash
python -m pytest tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_build_artifacts.py -k 'source_map or pre_snapshot or materialize' -q
```

Expected: PASS with promoted lineage serialized and validated.

## Task 4: Project Promoted Effects Into Shared `SemanticWorkflowIR`

**Files:**

- Modify: `orchestrator/workflow/semantic_ir.py`
- Modify: `tests/test_workflow_semantic_ir.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_workflow_lisp_diagnostics.py`

- [ ] **Step 1: Add failing shared semantic-IR tests**

Extend `tests/test_workflow_semantic_ir.py` so it locks down:

- promoted `resource_transition` and `ledger_update` entries appear only alongside a matching generic `command_call`;
- promoted `snapshot_capture` entries correspond to real validated `pre_snapshot` surfaces;
- promoted `pointer_materialization` entries correspond to real validated `materialize_artifacts.values[*].pointer.path` payloads;
- promoted entries carry stable ids and `details`;
- YAML workflows without frontend lineage stay on the existing coarse shared effect surface;
- invalid promoted lineage raises `semantic_ir_invalid`.

Also extend diagnostics coverage so a `semantic_ir_invalid` raised from promoted-effect validation still remaps through structured subject refs.

- [ ] **Step 2: Run the narrow failing selectors**

Run:

```bash
python -m pytest tests/test_workflow_semantic_ir.py tests/test_workflow_lisp_diagnostics.py -k 'semantic_ir and (effect or promoted or lineage)' -q
```

Expected: FAIL because `SemanticEffectEntry` does not yet carry `details` and the shared builder does not ingest promoted lineage.

- [ ] **Step 3: Extend the shared effect entry and builder**

Update `orchestrator/workflow/semantic_ir.py` to:

- add the `details` field to `SemanticEffectEntry`;
- ingest promoted adapter metadata from command-boundary lineage;
- ingest lowering-generated promoted effect lineage from the source map;
- preserve the existing generic `workflow_call`, `provider_call`, and `command_call` behavior unchanged.

Projection rules:

- `resource_transition` and `ledger_update` require:
  - a matching `command_call`
  - `boundary_kind == "certified_adapter"`
  - an allowlisted declared effect name
- `snapshot_capture` requires a real validated `pre_snapshot` surface;
- `pointer_materialization` requires a real validated `pointer.path` payload;
- append `:<effect_key>` to the effect id when one statement can own multiple promoted entries of the same kind.

- [ ] **Step 4: Tighten shared validation**

In `validate_workflow_semantic_ir(...)`, reject:

- promoted resource or ledger effects on non-certified or non-command statements;
- snapshot effects without a validated `pre_snapshot`;
- pointer effects without a validated pointer materialization payload;
- promoted effects that reference missing refs, unknown statements, or duplicate ids.

- [ ] **Step 5: Re-run the semantic-IR selectors**

Run:

```bash
python -m pytest tests/test_workflow_semantic_ir.py tests/test_workflow_lisp_diagnostics.py -k 'semantic_ir and (effect or promoted or lineage)' -q
```

Expected: PASS with promoted shared effect entries validated end to end.

## Task 5: Run Regression Coverage And One Real Orchestrator Artifact-Contract Smoke

**Files:**

- Modify only if a failing check proves the assertion surface needs refresh:
  - `tests/test_workflow_lisp_cli.py`

- [ ] **Step 1: Run `--collect-only` for all new test modules**

Run:

```bash
python -m pytest --collect-only \
  tests/test_workflow_lisp_effects.py \
  tests/test_workflow_lisp_source_map.py \
  tests/test_workflow_semantic_ir.py -q
```

Expected: PASS.

- [ ] **Step 2: Run the focused regression suite**

Run:

```bash
python -m pytest \
  tests/test_workflow_lisp_effects.py \
  tests/test_workflow_lisp_source_map.py \
  tests/test_workflow_lisp_resource_stdlib.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  tests/test_workflow_semantic_ir.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_lisp_diagnostics.py \
  -k 'effect or source_map or semantic_ir or resource_transition or pre_snapshot or materialize' -q
```

Expected: PASS.

- [ ] **Step 3: Run one real `python -m orchestrator` compile smoke for the changed artifact contracts**

Run:

```bash
python -m orchestrator compile tests/fixtures/workflow_lisp/valid/pointer_materialization_effects.orc \
  --entry-workflow orchestrate \
  --provider-externs-file tests/fixtures/workflow_lisp/cli/providers.json \
  --prompt-externs-file tests/fixtures/workflow_lisp/cli/prompts.json \
  --command-boundaries-file tests/fixtures/workflow_lisp/cli/commands.json \
  --emit-semantic-ir .orchestrate/tmp/rich-semantic-effect-graph-smoke/semantic_ir.json \
  --emit-source-map .orchestrate/tmp/rich-semantic-effect-graph-smoke/source_map.json
python -c "import json; ir=json.load(open('.orchestrate/tmp/rich-semantic-effect-graph-smoke/semantic_ir.json')); sm=json.load(open('.orchestrate/tmp/rich-semantic-effect-graph-smoke/source_map.json')); effects=[effect['kind'] for workflow in ir['workflows'] for effect in workflow['effects']]; generated=[effect['effect_kind'] for workflow in sm['workflows'] for effect in workflow.get('generated_semantic_effects', [])]; assert 'pointer_materialization' in effects; assert 'generated_semantic_effects' in sm['workflows'][0]; assert 'pointer_materialization' in generated"
```

Expected: PASS, proving that the real orchestrator compile path emits the changed `semantic_ir.json` and `source_map.json` contracts and that the emitted artifacts expose promoted pointer-materialization data through the actual build surface rather than only through pytest helpers.

- [ ] **Step 4: Re-run the focused CLI/build pytest smoke**

Run:

```bash
python -m pytest tests/test_workflow_lisp_cli.py -k 'emit_semantic_ir or emit_source_map or explain_workflow' -q
```

Expected: PASS, keeping the narrower CLI/build regression coverage alongside the real orchestrator smoke above.

- [ ] **Step 5: Record verification evidence before claiming completion**

Implementation is not complete until the execution report captures:

- the exact test commands run;
- the exact `python -m orchestrator compile ... --emit-semantic-ir ... --emit-source-map ...` smoke command and the artifact paths it wrote;
- whether any new fixture files were added;
- the source-map sections added or changed;
- the promoted shared effect kinds observed in the passing semantic-IR assertions;
- confirmation that no runtime behavior or pointer-authority rules were changed.
