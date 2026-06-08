# Workflow Lisp Runtime Migration Foundation

Status: draft design
Kind: architecture decision / migration target design
Created: 2026-06-08
Scope: command structured-output authority, machine-readable migration
promotion gates, and generated state/path layout.

Related docs:

- `specs/io.md`
- `specs/dsl.md`
- `specs/state.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_semantic_workflow_ir.md`
- `docs/design/workflow_lisp_source_map.md`
- `docs/lisp_workflow_drafting_guide.md`

## Summary

This document defines the next runtime/migration foundation for Workflow Lisp
promotion work. It narrows three high-priority directions into one target:

1. finalize command structured-output behavior;
2. harden the machine-readable migration promotion gate; and
3. centralize compiler/runtime generated state and path allocation through
   `StateLayout` / `PathAllocator`.

The common theme is authority. Command bundles must be the authority for command
structured outputs, migration promotion must be computed from evidence rather
than asserted, and compiler-generated paths must be owned by one layout contract
rather than scattered helper conventions.

## Context And Authority

Normative command IO behavior lives in `specs/io.md`. It already states that
command steps with `output_bundle.path` receive
`ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, that the runtime-owned value wins over any
caller-provided value, that the runtime creates or validates the parent
directory before command launch, and that the bundle file is semantic authority.

Migration promotion policy is governed by
`docs/design/workflow_lisp_key_migration_parity_architecture.md` and
`docs/lisp_workflow_drafting_guide.md`: compile, validation, and dry-run are
necessary evidence, not promotion. A `.orc` candidate may replace a YAML primary
only when machine-readable parity evidence computes `non_regressive`.

Generated state/path ownership is governed by
`docs/design/workflow_lisp_state_layout.md`: high-level frontend code should
request semantic targets, while layout derives concrete bundle paths, state
paths, temp paths, write roots, and source-map identities.

Current implementation is partially ahead of the design prose:

- `output_bundle` and `variant_output` validation exist, and command-result
  lowering can produce structured bundle contracts.
- `migration-parity` exists and computes `non_regressive` from a target
  manifest and generated evidence reports.
- Source maps, semantic IR state-layout entries, generated paths, and generated
  internal-input projections exist.

The remaining gap is coherence: these surfaces are implemented in several
places, but not yet hardened as one promotion-grade foundation.

## Problem

Workflow Lisp migration confidence is limited by three related failure modes.

First, command structured-output authority can drift. If authored environment
variables can override the runtime-owned `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, a
command can write semantic state somewhere other than the contract path. If the
runtime does not create or validate the bundle parent before launch, adapters
must carry path setup logic that should belong to the runtime contract.

Second, the migration promotion gate is currently stronger than a report but
not yet always a hard release valve. It computes `non_regressive`, but a caller
can still treat a generated report as advisory unless there is an explicit
gate mode, strict report validation, and clear distinction between
`non_regressive` and `eligible_for_primary_surface`.

Third, generated path allocation is scattered across lowering helpers, managed
write-root inputs, source-map generation, semantic IR projection, call binding,
and executor entry binding. This makes it easy to fix one path family while
leaving another family with stale resume identity, public hidden inputs, or
parallel-run collisions.

## Goals

- Make command `output_bundle` / `variant_output` files the only semantic
  authority for command structured outputs.
- Ensure the runtime, not command adapters, owns structured bundle target
  injection and parent-directory readiness.
- Make migration promotion fail closed when required evidence is missing,
  stale, malformed, regressive, or ineligible.
- Keep `non_regressive` computed only by tooling.
- Make `primary_surface` derivation depend on computed non-regression and
  promotion eligibility.
- Introduce a single path/layout allocation boundary for compiler-generated
  write roots, bundle paths, state paths, and generated path provenance.
- Preserve existing public API behavior while hiding compiler-owned
  `__write_root__...` inputs from public entrypoints.
- Preserve source-map and Semantic IR evidence for generated paths.

## Non-Goals

- Do not redesign review/revise-loop, `resume-or-start`, generic effectful
  composition, or adapter lint policy in this document.
- Do not ban command steps.
- Do not replace YAML primaries based on this design alone.
- Do not introduce a generic semantic diff engine for migration parity.
- Do not rewrite all existing generated paths in one change.
- Do not make reports, stdout, pointer files, or debug YAML semantic authority.

## Decision

Implement the foundation in three ordered tranches.

### Tranche 1: Command Structured-Output Authority

For command steps with `output_bundle.path` or `variant_output.path`, the runtime
must:

1. resolve the path through the existing output-contract path-safety logic;
2. set `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` unconditionally to that resolved
   workspace-relative target;
3. override any authored `env.ORCHESTRATOR_OUTPUT_BUNDLE_PATH`;
4. create or validate the bundle parent directory before command launch;
5. validate the bundle file after successful command exit; and
6. fail the step as an output-contract failure if exit is `0` but the bundle is
   missing or invalid.

Stdout JSON remains debug/captured output unless the step explicitly uses
`output_capture: json`. It must not become structured command state when an
`output_bundle` or `variant_output` contract is present.

### Tranche 2: Migration Promotion Gate Hardening

Keep the existing manifest-driven `migration-parity` model, but harden it into
a release gate.

The promotion command must support a strict mode, such as
`--require-non-regressive`, that exits nonzero when any selected target that is
eligible for promotion is regressive or lacks required evidence.

The command must validate both freshly generated reports and reused existing
reports against the same schema/version contract before including them in an
aggregate index. Existing reports are not authority merely because they are
JSON objects.

`non_regressive` remains computed from evidence. Target manifests and hand
authored reports must not provide it. `primary_surface` is derived from:

```text
computed non_regressive
AND promotion_eligibility.eligible_for_primary_surface
```

When `non_regressive=true` but `eligible_for_primary_surface=false`, reports
must make the distinction explicit: the candidate may be non-regressive against
recorded evidence but still not promotable.

### Tranche 3: StateLayout / PathAllocator Foundation

Introduce a concrete `StateLayout` / `PathAllocator` boundary without forcing a
large path migration in the first patch.

The first implementation should centralize allocation and provenance for:

- generated command/provider result bundle write roots;
- generated internal inputs such as `__write_root__...`;
- reusable call write-root bindings;
- entrypoint runtime-owned managed write roots;
- generated source-map path entries; and
- Semantic IR state-layout entries.

The initial allocator may preserve current concrete path shapes where changing
them would create unnecessary churn. The important first step is that every
generated path family goes through one allocation interface and one provenance
interface.

After that interface is stable, path families can move toward the
`workflow_lisp_state_layout.md` target: private generated write paths are
run-isolated by default, resume reconstructs the same private path for the
same run/call-frame/loop identity, and authored stable workspace artifacts
remain explicit.

## Design Details

### Command Bundle Contract

The command execution path has three phases:

```text
resolve contract path
  -> prepare runtime-owned environment and parent directory
  -> run command
  -> validate declared bundle
  -> publish typed artifacts
```

The path passed through `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` is the same path used
for post-exit validation. A command cannot select a different semantic target
by writing a different env value or by printing JSON to stdout.

Required failure behavior:

| Case | Result |
| --- | --- |
| Authored env sets `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` | Runtime value wins |
| Bundle path unsafe | Step fails before command launch |
| Parent cannot be created/validated | Step fails before command launch |
| Command exits nonzero | Command failure remains primary |
| Command exits `0`, bundle missing | Output-contract failure |
| Command exits `0`, bundle invalid | Output-contract failure |
| Stdout contains valid JSON, bundle missing | Output-contract failure |

### Promotion Gate Contract

The parity report is a machine-readable evidence object, not a checklist
summary. A report has these authority layers:

```text
target manifest
  -> evidence commands and accepted waivers
  -> generated report
  -> computed non_regressive
  -> derived aggregate index
  -> optional primary-surface decision
```

Required evidence roles remain those already represented by the migration
parity implementation and architecture:

- compile;
- shared validation;
- dry-run or smoke/integration;
- baseline characterization;
- output contract parity;
- terminal state parity;
- artifact parity;
- resume/reuse parity;
- generated-source provenance; and
- deprecated-mechanic replacement or accepted waiver.

The gate must distinguish:

- `report_valid`: the report shape is valid;
- `evidence_complete`: required evidence exists and is current enough;
- `non_regressive`: evidence proves no required parity regression;
- `eligible_for_primary_surface`: policy allows promotion; and
- `primary_surface`: generated surface selected by the gate.

### StateLayout / PathAllocator Contract

`StateLayout` owns semantic allocation requests. `PathAllocator` owns concrete
path names for those requests.

Illustrative request shape:

```text
layout.allocate(
  owner="workflow_lisp",
  workflow_id="design-plan-stack::review-plan",
  source_span=...,
  semantic_role="command_result_bundle",
  stable_identity="review-plan/run-review/result",
  privacy="private_generated",
  resume_scope="run_call_frame",
)
```

The returned allocation contains:

```text
generated_input_name, when needed
concrete_path_template
semantic_identity
source_map_entry
semantic_ir_layout_entry
path_safety_policy
resume_identity
```

`StateLayout` does not decide semantic workflow outcomes. It decides where
compiler/runtime-owned state and generated bundle files live, how they are
hidden from public inputs, and how they are explained.

## Contracts And Interfaces

### Runtime

- `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` is runtime-owned for structured command
  bundle steps.
- Runtime creates or validates the bundle parent before command launch.
- Runtime validates output bundles after successful command exit.
- Runtime entry binding for compiler-managed write roots remains hidden from
  public workflow inputs.

### CLI

- `migration-parity` remains the machine-readable promotion evidence command.
- A strict gate mode exits nonzero for regressive promotable targets.
- CLI docs/specs must describe the command once it is relied on as a release
  gate.

### Generated Artifacts

- `source_map.json` records generated paths and generated internal inputs.
- Semantic IR records corresponding state-layout entries.
- Parity JSON reports are authority for migration evidence.
- Markdown parity reports and indexes are views.

## Dependencies And Sequencing

Tranche 1 should land first because it fixes a small runtime authority bug and
strengthens every command-result migration.

Tranche 2 can land next because the command exists; hardening it does not
require StateLayout to be complete. It should include any spec/CLI doc updates
needed to treat the command as a gate.

Tranche 3 should follow as a staged refactor. It has broader blast radius and
should start by routing existing allocation families through a shared boundary
without changing all concrete paths at once.

Work that can proceed in parallel:

- report-schema validation for existing parity reports;
- CLI spec/doc alignment for `migration-parity`;
- focused tests for command bundle env precedence; and
- inventory of generated path families that currently bypass a shared layout
  interface.

Work that should wait for this foundation:

- treating additional `.orc` candidates as primary YAML replacements;
- broad strict adapter-lint enforcement; and
- large-scale generated path shape changes.

## Invariants And Failure Modes

- Structured command bundle files are semantic authority; stdout is not.
- Authored environment values cannot redirect structured command output.
- Missing bundle parent setup is a runtime/setup failure, not adapter-specific
  hidden logic.
- `non_regressive` is computed, never authored.
- A regressive or malformed parity report cannot promote a candidate.
- Hidden `__write_root__...` inputs remain unavailable at public entrypoints.
- Generated private paths are source-mapped and represented in Semantic IR.
- Path allocation failures are explicit diagnostics, not silent fallback to
  handwritten strings.
- New path allocation interfaces must not break resume identity for existing
  runs unless an explicit compatibility boundary says so.

## Evidence And Implementation Boundaries

Implementation follows this design only if the default runtime command path
sets structured bundle env values, creates/validates parents, and validates the
declared bundle. Adapter-side `mkdir` calls and tests that manually write bundle
files are not sufficient evidence.

Migration promotion follows this design only if the CLI can fail as a gate.
Generated reports that compute `non_regressive` but never affect exit behavior
are useful evidence, but not a release valve.

State layout follows this design only if generated path families route through
one allocation/provenance boundary. Existing helpers that merely keep producing
`__write_root__...` names are compatibility mechanics, not the target
architecture.

## Compatibility And Migration

Existing YAML and `.orc` workflows remain valid.

Command steps that already honor `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` continue to
work. Command steps that intentionally override that variable become invalid
for structured bundle contracts because the runtime-owned value wins.

Existing parity reports remain readable, but strict gate mode may reject old
reports that lack schema/version fields or required evidence. That is expected:
old evidence can remain historical, but it should not be promotion authority.

StateLayout migration is incremental. The first implementation should preserve
current concrete paths where practical and move ownership behind an allocator
facade before changing path shapes.

## Verification Strategy

Command structured-output tests:

- command env override cannot redirect `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`;
- runtime creates the bundle parent before command launch;
- stdout JSON without bundle fails as missing bundle;
- nonzero command exit remains primary over bundle validation;
- `variant_output.path` follows the same env and validation contract.

Migration gate tests:

- target manifest rejects authored `non_regressive`;
- strict gate exits nonzero for regressive eligible targets;
- strict gate exits zero for non-regressive eligible targets;
- reused existing reports are schema/version validated;
- expired waivers, missing required evidence, missing required artifacts, and
  hidden managed write-root inputs force non-regression false;
- aggregate index derives `primary_surface` from computed non-regression and
  promotion eligibility.

StateLayout tests:

- generated result bundle paths route through the allocator;
- generated internal inputs remain hidden from public inputs and present in
  runtime contracts;
- source maps and Semantic IR contain matching generated path/layout entries;
- repeated calls, loop iterations, and match arms produce collision-proof
  allocations;
- resume reconstructs the same allocation identity for the same run and
  call-frame/loop identity;
- absolute paths and `..` escapes are rejected.

## Declarative Acceptance Scenarios

### Command Bundle Authority

Initial state: a workflow has a command step with an `output_bundle.path` and an
authored env value for `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`.

Entrypoint: `python -m orchestrator run ...`

Expected result: runtime overrides the authored env value, the command sees the
contract path, the bundle validates, and the step artifacts come from the
bundle file.

Forbidden result: stdout JSON or the authored env path becomes semantic state.

### Promotion Gate

Initial state: a parity target has compile and dry-run evidence but missing
resume parity.

Entrypoint:

```bash
python -m orchestrator migration-parity \
  workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json \
  --require-non-regressive
```

Expected result: the report is generated, `non_regressive=false`, and the CLI
exits nonzero for an eligible promotion target.

Forbidden result: the target appears as primary `.orc` because it compiled.

### Generated Path Allocation

Initial state: a `.orc` workflow calls the same reusable procedure twice inside
a loop, and each call lowers to a command-result bundle.

Entrypoint: compile, shared validation, and dry-run/run.

Expected result: each generated bundle path has one allocator identity, one
hidden runtime input when needed, matching source-map and Semantic IR entries,
and no collision across calls or loop iterations.

Forbidden result: generated path strings are synthesized independently by
lowering helpers with no common provenance.

## Success Criteria

- Command structured-output tests pass for env precedence, parent creation, and
  missing-bundle fail-closed behavior.
- `migration-parity` has a strict gate mode with focused CLI tests.
- Existing parity reports and indexes are still generated, but reused reports
  are schema/version checked.
- A `StateLayout` / `PathAllocator` implementation boundary exists and at
  least command-result and reusable-call write-root allocation route through it.
- Source-map and Semantic IR tests prove generated path provenance survives.
- No public workflow entrypoint exposes compiler-owned `__write_root__...`
  inputs.
- `git diff --check` passes.
