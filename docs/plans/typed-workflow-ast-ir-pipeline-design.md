# ADR: Typed Workflow Surface AST and Executable IR Pipeline

**Status:** Proposed
**Date:** 2026-03-10
**Owners:** Orchestrator maintainers

## Context

The orchestrator already has real language semantics: strict version gating, stable internal step identities, scoped references, structured control lowering, reusable `call`, resume-sensitive loop behavior, and workflow-boundary signatures. But those semantics still flow through mutable `dict[str, Any]` workflow objects for most of the pipeline.

Today:

1. `WorkflowLoader` parses YAML into raw dictionaries, validates them, assigns step ids, lowers `repeat_until` bodies, lowers structured statements, lowers `finally`, and appends loader metadata such as `__workflow_path`, `__source_root`, `__imports`, and `__managed_write_root_inputs` onto the same mutable object.
2. `orchestrator/workflow/lowering.py` rewrites names and structured refs directly into copied dictionaries and encodes helper/runtime nodes through magic metadata keys such as `structured_if_branch`, `structured_if_join`, `structured_match_case`, and `workflow_finalization`.
3. `WorkflowExecutor`, `LoopExecutor`, `CallExecutor`, and `ResumePlanner` dispatch largely by key presence, list indices, and presentation-name lookup on those dictionaries and must understand a mix of authored shape, normalized shape, lowered executable shape, and persisted compatibility state.

This works, but the phase boundaries are weak. Validation, elaboration, lowering, and execution each depend on partially normalized dict shapes rather than explicit node contracts.

## Problem Statement

Introduce a typed in-memory language pipeline between authored YAML and runtime execution so that:

1. authored workflow structure has an explicit typed surface AST
2. lowered executable structure has an explicit typed IR
3. executor/runtime collaborators consume the lowered IR instead of raw workflow dictionaries
4. existing external DSL behavior and persisted run/state semantics remain unchanged in the first tranche

This is an internal architecture change, not a user-facing DSL redesign.

## Decision

Adopt a four-stage internal pipeline:

1. parse YAML into a raw mapping only long enough to report syntax/load errors
2. validate and elaborate that mapping into an immutable typed surface AST
3. lower the AST into an immutable typed executable IR
4. execute only against the IR

The steady-state runtime contract is:

- authored YAML is the only source language
- surface AST is the authored-shape truth
- executable IR is the execution-shape truth
- raw dicts do not escape parse/elaboration internals
- top-level loading returns a typed loaded-workflow bundle carrying surface AST, executable IR, compatibility projection, and typed provenance/import metadata

## Smallest Useful Cut

The first useful cut is not "type everything in the repo." It is:

1. a typed workflow root plus typed step union for every currently supported execution form
2. typed authored nodes for structured `if/else`, `match`, `repeat_until`, `finally`, `for_each`, and `call`
3. typed refs, predicates, artifact/input/output contracts, workflow provenance/import metadata, and stable-id metadata
4. typed executable helper nodes for branch markers/joins, case markers/joins, finalization steps, repeat-until frames, and call boundaries
5. an in-memory compatibility projection that preserves current state/report surfaces without making presentation names or indices the execution truth

The first cut does not need to redesign provider transport, prompt composition, output capture internals, or `state.json`.

## Core Contracts

### Surface AST

The surface AST should live under a dedicated module such as `orchestrator/workflow/surface_ast.py` and model authored structure directly:

- `SurfaceWorkflow`
- `SurfaceStep` tagged union for provider, command, wait, assert, scalar bookkeeping, `for_each`, `repeat_until`, `call`, and structured statements
- typed contract/value nodes for artifacts, workflow inputs/outputs, typed predicates, and structured refs
- typed provenance/import nodes for workflow path, source root, imported workflow bindings, and managed write-root requirements
- normalized block nodes for branch/case/finalization/repeat-until bodies

Surface AST responsibilities:

1. normalize author-friendly shapes into one canonical in-memory authored form
2. validate version-gated schema and typed contract rules
3. assign durable step ids before lowering
4. preserve lexical scope explicitly instead of reconstructing it later from rewritten names
5. carry authoritative provenance/import metadata instead of relying on raw-dict magic fields later in execution

The surface AST must not contain lowered helper nodes.

### Workflow Provenance and Imports

The typed pipeline must carry the runtime metadata that currently rides on raw workflow dictionaries:

- workflow file path and source root used for asset resolution and import-relative behavior
- imported workflow bindings keyed by alias
- reusable-call managed write-root input requirements and collision-validation metadata
- enough provenance to recompute workflow checksum and validate resume against the current file on disk

Both the surface AST and the loaded-workflow bundle should expose this through typed metadata records. `CallBoundary`, asset resolution, checksum validation, and nested call dispatch must consume those typed records rather than `__workflow_path`, `__source_root`, `__imports`, or `__managed_write_root_inputs`.

### Executable IR

The executable IR should live under a dedicated module such as `orchestrator/workflow/executable_ir.py` and model only runnable nodes:

- `ExecutableWorkflow`
- `ExecutableNode` tagged union for leaf execution nodes and helper nodes
- explicit helper node types for:
  - `IfBranchMarker`
  - `IfJoin`
  - `MatchCaseMarker`
  - `MatchJoin`
  - `FinalizationStep`
  - `RepeatUntilFrame`
  - `CallBoundary`

Each executable node should carry:

1. durable runtime identity (`step_id` or equivalent node id)
2. presentation name used in state/reporting
3. explicit node kind enum
4. typed guard/routing/output-materialization metadata
5. scope metadata required for structured ref resolution
6. a compatibility projection handle for persisted state/report surfaces

Lowering must be a pure AST-to-IR transform. It must not read runtime state, mutate global loader state, or depend on executor behavior.

### IR Topology and Routing

`ExecutableWorkflow` must define one concrete execution topology, not just a catalog of node kinds. The contract for the first tranche is:

- a `body_region` ordered tuple of top-level node ids in canonical execution order
- an optional `finalization_region` ordered tuple with its own entry node and local ordinal table
- lookup tables for `node_id -> node`, `node_id -> presentation key`, and `compatibility_index -> node_id`

Every executable node must expose:

1. a fallthrough successor (`node_id` or terminal sentinel)
2. explicit routed transfers keyed by reason, covering `goto`, branch/case routing, loop continue/exit, call return, and finalization entry
3. whether a routed transfer counts toward `transition_count`
4. region membership so body-vs-finalization sequencing never depends on list-slicing conventions in the executor

Lowering resolves all goto names and structured-control routes to target node ids. The executor advances only by IR edges; it does not scan step names to find a target. Normal fallthrough preserves ordered execution, while routed transfers preserve today's transition-count semantics by carrying an explicit `counts_as_transition` flag.

### Bound References

Surface elaboration parses structured refs and predicates into typed reference nodes, but lowering must go further and bind every executable reference to a durable target address. The relevant address kinds are:

- workflow-input addresses
- node-result addresses keyed by target `node_id` plus result slot/member
- block/join output addresses keyed by statement node id and output name
- loop-frame addresses keyed by loop node id, iteration scope, and output slot
- call-output addresses keyed by call-boundary node id and declared output name

After lowering, runtime reference resolution may consult current state values, but it may not reparse ref strings, scan presentation-key maps, or rewrite step names. Presentation names remain compatibility/reporting surfaces only.

### Compatibility Projection and Resume

Because `state.json` remains unchanged in the first tranche, lowering must emit an in-memory compatibility projection alongside the IR. That projection is the sole authority for mapping execution-shape node ids back to compatibility-oriented persisted state.

The projection must define:

- `node_id <-> compatibility_index` for `current_step.index` and ordered top-level restart surfaces
- `node_id -> presentation_key` and display name for `steps.<PresentationKey>`, `step_visits`, and reporting
- finalization local-index mappings for `finalization.current_index` and `completed_indices`
- loop-key templates for `steps.<LoopName>`, `steps.<LoopName>[i].<NestedStep>`, `for_each.<LoopName>`, and `repeat_until.<LoopName>`
- call-frame checkpoint mappings so nested execution stores callee-local node ids while preserving existing outer call-frame schema fields

Resume must use persisted durable identities first:

1. map `current_step.step_id` or the first unfinished projected entry to an IR `node_id`
2. cross-check any persisted compatibility index or presentation key against the projection and treat mismatches as state-integrity errors
3. restart from the resolved IR node id, using persisted indices and presentation keys only as compatibility surfaces

This projection layer is also responsible for preserving today's branch/join presentation keys, finalization bookkeeping, repeat-until frame keys, call-frame checkpoints, `step_visits`, and `transition_count` semantics without making those names or indices the execution truth.

## Invariants

1. YAML remains the sole authored source language. No custom parser and no serialized on-disk IR.
2. AST and IR are immutable after construction.
3. Stable ids are assigned once during AST elaboration. Lowering may derive child ids, but it must not reinterpret authored identity based on later mutations.
4. Structured refs and typed predicates are parsed and validated before lowering, and lowering binds them to durable target addresses keyed by node ids or output slots. The executor must not rewrite or reparse refs against presentation keys.
5. Lowered helper nodes are explicit IR node types, not ordinary step dictionaries with magic keys.
6. The first tranche preserves external behavior:
   - same DSL syntax
   - same version gates
   - same `state.json` schema/version
   - same presentation keys and `step_id` ancestry
   - same call-frame privacy and workflow-output behavior
7. Workflow provenance/import metadata are typed contracts on the loaded workflow bundle, not raw-dict magic fields.
8. Path safety, workflow signatures, import/version validation, and output contract validation remain pre-execution concerns owned by parse/elaboration/lowering, not ad hoc executor heuristics.
9. Callee-private lineage remains private. Only declared callee outputs cross the `call` boundary.
10. Resume semantics remain driven by persisted state, but restart planning uses `step_id -> node_id` projection. Persisted indices and presentation names remain compatibility surfaces and integrity cross-checks, not execution truth.
11. Once migrated, runtime dispatch may not determine node kind by arbitrary key presence or resolve control transfers by scanning step names.
12. The compatibility projection is the only allowed path from IR nodes to `steps.*`, `current_step.index`, `finalization.*`, `repeat_until.*`, `for_each.*`, and `call_frames.*` state surfaces.

## Required Debt Paydown Before Further Feature Work

Yes. A narrow internal refactor tranche is required before more language features should land on this pipeline.

Required debt paydown:

1. move normalization, stable-id assignment, provenance capture, and ref binding out of scattered dict mutation and into AST elaboration/lowering
2. replace executor key-presence and name-scan dispatch with explicit IR node-kind and node-id dispatch
3. stop representing lowered helper/runtime nodes as ordinary authored step dicts
4. introduce a first-class IR-to-state compatibility projection instead of ad hoc persistence keyed by the current step list layout
5. split tests by phase so authored-shape validation, lowering invariants, and runtime behavior can fail independently

Sequencing constraint:

- do not add new structured-control or reusable-execution features directly on top of the raw dict pipeline after this ADR, except for targeted bug fixes to already-shipped behavior

## Temporary Migration Contracts

During migration, some dict-shaped compatibility is acceptable, but only at narrow adapters.

Allowed temporary contracts:

1. a loader-owned compatibility wrapper such as `LoadedWorkflowBundle(surface, ir, projection, legacy_dict=None)` while callers are migrated
2. leaf-node adapters from IR configs into existing `StepExecutor` / `ProviderExecutor` call shapes
3. step-result/state payload dictionaries, because persisted runtime state is intentionally unchanged in this tranche
4. temporary shims that expose typed provenance/import data to unchanged asset or call helpers while those helpers are migrated

Not allowed as a steady state:

1. new runtime behavior keyed off lowered dict metadata like `structured_if_join`
2. executor paths that must interpret both authored dicts and IR nodes for the same concept
3. runtime paths that recover workflow provenance or imports from `__workflow_path`, `__source_root`, `__imports`, or `__managed_write_root_inputs` once the typed bundle exists
4. feature work that extends the legacy lowered-dict representation instead of the typed IR

## Module Ownership

Recommended ownership split:

- `orchestrator/loader.py`
  - parse orchestration and top-level typed load-bundle entrypoint
- `orchestrator/workflow/surface_ast.py`
  - authored node types
- `orchestrator/workflow/elaboration.py`
  - raw mapping -> validated/normalized AST
- `orchestrator/workflow/executable_ir.py`
  - executable node types and enums
- `orchestrator/workflow/lowering.py`
  - AST -> IR plus compatibility-projection generation
- `orchestrator/workflow/references.py`
  - parsed reference nodes plus IR binding helpers
- `orchestrator/workflow/state_projection.py`
  - IR node id <-> compatibility state/presentation mapping
- `orchestrator/workflow/executor.py`
- `orchestrator/workflow/loops.py`
- `orchestrator/workflow/calls.py`
- `orchestrator/workflow/resume_planner.py`
  - IR + projection consumers only

## Sequencing Plan

1. Add characterization coverage for current external behavior around structured lowering, scoped refs, `call`, `repeat_until`, finalization, resume, transition counting, and persisted state presentation.
2. Introduce surface AST types, typed provenance/import metadata, and parsed reference nodes while keeping a temporary compatibility path for unchanged callers.
3. Introduce executable IR topology, bound reference addresses, and compatibility-projection generation for all currently supported step kinds.
4. Migrate executor, loop, call, finalization, and resume collaborators to consume IR node kinds plus the compatibility projection only.
5. Remove legacy lowered-dict helper metadata, raw workflow magic metadata fields, and runtime string-based structured-ref lookup/rewrite paths.
6. Only after step 4 is complete should new language/runtime features build on the new pipeline.

If any step discovers a required external contract change, that change must be split into a separate ADR and, where appropriate, a version-gated DSL or state-schema change.

## Test Strategy

Add and organize tests around the phase boundaries:

1. AST tests
   - validation errors
   - normalization behavior
   - stable-id assignment
   - typed provenance/import metadata
   - typed ref/predicate parsing
2. Lowering tests
   - branch/case/finalization/repeat-until/call lowering invariants
   - identity preservation
   - topology edge tables and routed-transfer flags
   - bound-reference targets
   - compatibility-projection tables
   - structured output-materialization metadata
3. IR runtime tests
   - executor dispatch by node kind
   - goto routing and `transition_count` semantics
   - resume against lowered identities via projection
   - finalization restart from projected local indices
   - call-frame and loop-frame persistence
4. Compatibility tests
   - existing example workflows and state/report surfaces remain unchanged
   - `current_step.index`, `step_visits`, finalization bookkeeping, repeat-until keys, and call-frame checkpoint fields match current contracts

The first tranche is successful only if these layers can fail independently instead of every regression surfacing as a generic end-to-end dict-shape failure.

## Non-Goals

This ADR does not authorize:

1. a DSL syntax redesign
2. a `state.json` redesign
3. a serialized on-disk IR format
4. optimizer or normalization passes unrelated to correctness and maintainability
5. a general compiler framework or plugin system
6. performance work as the primary motivation
7. removing recent executor seam extractions that already help isolate runtime responsibilities

## Alternatives Considered

1. Keep the dict pipeline and add more helper functions.
   Rejected because the authored/lowered/runtime phases would remain mixed and new features would continue to accumulate magic-key branching.

2. Add only a typed IR and keep authored validation/elaboration dict-shaped.
   Rejected because the loader/lowering boundary would remain weak and structured semantics would still be normalized through mutable dict mutation.

3. Treat this as a full compiler rewrite with custom parsing and serialized IR.
   Rejected because it is far broader than the problem, would slow feature delivery, and is not required to get the runtime benefits this backlog item targets.

## Success Criteria

This ADR is satisfied only if the follow-on implementation:

1. introduces a typed surface AST for the targeted workflow area
2. introduces a typed executable IR for lowered runtime nodes
3. defines a concrete IR topology and IR-to-state compatibility projection that preserve current control-flow, resume, and reporting semantics
4. makes executor/runtime collaborators consume IR and projection instead of raw workflow dicts plus name/index lookup
5. materially reduces mixed-phase loader/lowering/executor logic
6. preserves current external workflow and persisted-state behavior unless a later ADR explicitly changes it
