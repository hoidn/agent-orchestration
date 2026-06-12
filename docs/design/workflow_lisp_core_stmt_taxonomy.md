# Workflow Lisp Core Statement Taxonomy

Status: draft internal design  
Depends on: `docs/design/workflow_lisp_core_workflow_ast.md`,
`docs/design/workflow_command_adapter_contract.md`

## Purpose

This document is an internal, implementation-aligned inventory of the current
shared Core statement substrate. It is not a public DSL contract and it does
not redefine runtime behavior. Base statement-family identity comes from the
actual shared dataclasses in `orchestrator/workflow/core_ast.py`; attached
semantics come from existing `common` payloads, executable configs, runtime-plan
projections, Semantic IR promotions, and source-map lineage.

`docs/design/workflow_command_adapter_contract.md` remains the authority for
what a command or certified adapter is allowed to mean. This taxonomy only
records how those already-implemented semantics attach to the shared statement
families.

## Current Shared Base Statement Families

The current checkout defines these validation-relevant base families:

- `CoreCommandStep`
- `CoreProviderStep`
- `CoreAdjudicatedProviderStep`
- `CorePureProjectionStep`
- `CoreWaitForStep`
- `CoreAssertStep`
- `CoreSetScalarStep`
- `CoreResourceTransitionStep`
- `CoreIncrementScalarStep`
- `CoreMaterializeArtifactsStep`
- `CoreSelectVariantOutputStep`
- `CoreCallStep`
- `CoreIf`
- `CoreMatch`
- `CoreForEach`
- `CoreRepeatUntil`

These are the only statement families that shared Core AST validation accepts
today. Frontends may elaborate into them, but may not bypass them.

## Structural Nested Blocks

The taxonomy also includes nested structural blocks that carry lineage and
output contracts without becoming standalone runtime node kinds:

- `CoreBranchBlock`
  Used by `CoreIf` for `then` and `else` bodies plus branch-local outputs.
- `CoreMatchCaseBlock`
  Used by `CoreMatch` for case bodies plus case-local outputs.
- `CoreFinally`
  Used for top-level finalization ordering and lineage.

These blocks are part of the contract because shared validation, Semantic IR,
and source maps must preserve their nested statement identity and output scope.

## Attached Semantic Facets

The current implementation carries several important semantics as attached
facets instead of standalone `CoreStmt` dataclasses:

- Command-boundary classification on `CoreCommandStep`
  `boundary_kind` and `boundary_name` remain explicit and are projected into
  Semantic IR, runtime-plan observability, and compiled source maps.
- Publication facets
  `publishes`, `expected_outputs`, `output_bundle`, and `variant_output`
  remain statement-local surfaces that project into runtime artifact plans and
  Semantic IR publication refs.
- Snapshot and selection facets
  `pre_snapshot` stays on step `common`; `select_variant_output` stays its own
  base statement family; both project into runtime snapshot plans.
- Prompt and provider facets
  Provider prompt surfaces, asset dependencies, output-contract injection, and
  adjudicated-provider metadata remain attached provider semantics.
- Proof facets
  `requires_variant` and `variant_output` create Semantic IR proof entries;
  match-case proof narrowing remains shared-validation behavior, not a new
  statement family.
- Promoted semantic effects
  `resource_transition` now exists in two shared forms: compiler-generated
  `CoreResourceTransitionStep` for declared runtime-native transitions, and
  promoted certified-adapter effects for compatibility routes that still lower
  through `CoreCommandStep`. `ledger_update` remains adapter-promoted for those
  compatibility routes; `snapshot_capture`, `pointer_materialization`, and
  `pure_projection` come from lowering-generated semantics. `pure_projection`
  is also represented by a shared generated statement family with attached
  payload and private-bundle lineage.
- State and write-root facets
  Resume checkpoints, presentation keys, and managed write-root inputs remain
  derived state-layout entries keyed to validated workflow identity.
- Source-map facets
  Generated internal inputs, generated semantic effects, command boundaries,
  executable nodes, and core-node lineage remain derived source-map sections.

None of these derived projections become semantic authority. Structured state,
artifact/path values, and validated shared artifacts remain authoritative; build
artifacts, reports, source maps, and observability summaries remain views over
that authority.

## Validation And Runtime Ownership

Ownership remains split across existing shared layers:

- `orchestrator/workflow/core_ast.py`
  Base family identity, structural blocks, metadata, and Core AST validation.
- `orchestrator/workflow/semantic_ir.py`
  Statement rows, command boundaries, prompt surfaces, call edges, promoted
  effects, proofs, publication refs, and state-layout projections.
- `orchestrator/workflow/runtime_plan.py`
  Publication plans, snapshot plans, runtime ordering, checkpoints, and
  observability-facing command hints.
- `orchestrator/workflow_lisp/source_map.py`
  Core-node lineage, executable-node lineage, generated internal inputs,
  command-boundary lineage, and generated semantic-effect lineage.
- Runtime/executor modules
  Execution semantics, persistence, resume, and observability rendering.

## Statement-Family Contract Matrix

| Family | Inputs | Outputs or projections | Effects | Proof or scope behavior | State or write-root behavior | Source-map fields | Ownership |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `CoreCommandStep` | `command`, shared `common`, command-boundary metadata | command boundary row, publication refs, snapshot plans when attached | `command_call`; promoted `resource_transition` / `ledger_update` for certified adapters | no new proof family; ordinary lexical scope | resume checkpoints and presentation keys; managed write-root inputs only when inherited from workflow provenance | step origin, core node, executable nodes, command-boundary lineage, generated semantic effects | Core AST + Semantic IR + runtime plan + source map |
| `CoreProviderStep` | provider binding, prompt surfaces, `common` | prompt surface row, publication refs | `provider_call`; promoted `snapshot_capture` / `pointer_materialization` when lowering generates them | `variant_output` / `requires_variant` proof rows when attached | resume checkpoints and presentation keys | step origin, core node, executable nodes, generated semantic effects | Core AST + Semantic IR + source map |
| `CoreAdjudicatedProviderStep` | adjudicated provider config, evaluator metadata, `common` | publication refs and prompt-delivery projections from adjudication surfaces | provider-family execution effect surface | no separate proof family beyond attached variant facets | ordinary state/projection ownership | step origin, core node, executable nodes | Core AST + shared adjudication + Semantic IR |
| `CorePureProjectionStep` | validated pure-expression payload, typed binding refs, `common.output_bundle` | generated result-bundle projection plus flattened output contracts | promoted `pure_projection` semantic effect with payload digest/schema lineage | no proof creation; remains effect-free pure computation | private generated `pure_projection_bundle` plus managed write-root bridge for the concrete bundle path | step origin, core node, executable nodes, generated semantic effects, generated-path lineage | Core AST + Semantic IR + runtime plan + source map |
| `CoreWaitForStep` | `wait_for` config | statement row and runtime node only | none beyond wait/runtime control | no proof context | resume checkpoints and presentation keys | step origin, core node, executable nodes | Core AST + runtime plan |
| `CoreAssertStep` | typed predicate | statement row and runtime node only | none | no proof context | resume checkpoints and presentation keys | step origin, core node, executable nodes | Core AST + runtime plan |
| `CoreSetScalarStep` | scalar artifact target and literal/ref value | publication refs when attached | none | no proof context | ordinary scalar artifact state only | step origin, core node, executable nodes | Core AST + runtime plan |
| `CoreResourceTransitionStep` | validated declaration payload, resolved resource metadata, resolved request/expected-version bindings | generated transition result artifacts plus state-layout lineage for `resource_state` / `transition_audit` | explicit `resource_transition` effect; compatibility `ledger_update` stays command-boundary-owned | no separate proof family; runtime declaration governs preconditions and write set | runtime-owned resource-state documents, transition-audit ledgers, and resume replay identity | step origin, core node, executable nodes, generated semantic effects, generated-path lineage | Core AST + Semantic IR + executable IR + runtime plan + source map |
| `CoreIncrementScalarStep` | scalar artifact target and increment | publication refs when attached | none | no proof context | ordinary scalar artifact state only | step origin, core node, executable nodes | Core AST + runtime plan |
| `CoreMaterializeArtifactsStep` | materialization value list, pointer metadata | runtime snapshot/materialization plans, publication refs when attached | lowering may later promote `pointer_materialization` | no proof context by itself | ordinary artifact/path state plus pointer authority enforcement | step origin, core node, executable nodes, generated semantic effects when present | Core AST + runtime plan + source map |
| `CoreSelectVariantOutputStep` | selector config plus snapshot evidence | runtime snapshot plan for `select_variant_output` and selected artifact projections | none directly; consumes prior snapshot evidence | variant-specific reference validation happens in shared validation | ordinary checkpoint/presentation-key state | step origin, core node, executable nodes | Core AST + runtime plan + shared validation |
| `CoreCallStep` | import alias and call bindings | Semantic IR call edge, imported-workflow refs | `workflow_call` | reusable-boundary validation stays external to the statement family | managed write-root policy remains caller-owned shared behavior | step origin, core node, executable nodes | Core AST + Semantic IR + runtime plan |
| `CoreIf` | typed predicate, `then`/`else` blocks | statement row plus branch-local outputs | none directly | creates nested lexical scope through `CoreBranchBlock` | branch outputs remain derived contract surfaces | step origin for statement and nested branch statements | Core AST + shared validation |
| `CoreMatch` | enum ref plus case blocks | statement row plus case-local outputs | none directly | shared validation performs match-case proof narrowing | case outputs remain derived contract surfaces | step origin for statement and nested case statements | Core AST + shared validation |
| `CoreForEach` | items or `items_from`, loop body | statement row plus nested body nodes | none directly | creates nested lexical scope for body statements | runtime plan creates loop-frame checkpoints; write-root policy remains shared | step origin for statement and nested body statements | Core AST + runtime plan |
| `CoreRepeatUntil` | body steps, outputs, condition, max iterations | loop outputs, runtime checkpoints, nested body nodes | none directly | nested lexical scope plus validated loop-output contract | runtime plan creates repeat-frame checkpoints | step origin for statement and nested body statements | Core AST + runtime plan |

## Drift From Older Draft

The earlier one-row-per-family draft no longer matches the current checkout
literally. The current contract is:

- `CoreForEach` is a real shared base family and belongs in the inventory.
- `CorePureProjectionStep` is now a real shared generated base family used for
  runtime-visible pure computation and private projection-bundle transport.
- `publish`, `consume_bundle`, `variant_output`, and `pre_snapshot` are current
  attached facets, not standalone `CoreStmt` dataclasses.
- `CoreResourceTransitionStep` is now a real shared generated base family for
  declared runtime-native transitions, while certified-adapter
  `resource_transition` / `ledger_update` compatibility routes still travel
  through `CoreCommandStep`.
- `snapshot_capture` and `pointer_materialization` are still promoted generated
  effects with source-map lineage, not statement families.
- Source maps, runtime-plan summaries, build artifacts, and observability views
  remain derived projections. They must not become semantic authority.

The practical rule is: update this document only when the shared implementation
changes, and describe new behavior in terms of real shared dataclasses plus real
attached facets rather than reviving obsolete standalone-family names.
