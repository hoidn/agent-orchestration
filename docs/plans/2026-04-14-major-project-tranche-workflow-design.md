# ADR: Major Project Tranche Workflow

**Status:** Proposed
**Date:** 2026-04-14
**Owners:** Orchestrator maintainers

## Context

The existing generic design-plan-implementation stack works well for bounded backlog items. It assumes a single item can be turned into one design, one plan, and one implementation loop. That model is too flat for broad migration or architecture programs such as the EasySpin MATLAB-to-PyTorch port.

The EasySpin backlog item is a major project. It includes repo documentation bootstrapping, architecture discovery, performance and parallelization analysis, shared API decisions, MATLAB oracle generation, MATLAB coverage work, PyTorch package design, and implementation of many numerical slices. Running the ordinary stack directly against that backlog item can produce a useful prerequisite slice, but it does not explicitly represent the program structure or the sequential tranches needed to complete the project.

The workflow should separate project decomposition from tranche execution.

## Decision Summary

Add a generic major-project workflow family with two levels:

1. A project-roadmap phase that reads a broad backlog item and produces a reviewed roadmap plus an ordered tranche manifest.
2. A tranche stack that runs one selected tranche through big-design, normal plan, and normal implementation phases.

The architect/project-planning step only divides the project into sequential tranches and records the high-level architecture direction. It does not draft every tranche's detailed design. Detailed design belongs to the selected tranche's design phase.

## Non-Goals

- Do not create an EasySpin-only workflow when the shape is generally useful.
- Do not turn the roadmap phase into an implementation or design-all-tranches phase.
- Do not fork the existing plan and implementation prompts unless a concrete gap is found.
- Do not make the driver deterministically drain every tranche by default. Large projects should be able to stop after one approved tranche so humans can review, commit, and decide whether to continue.
- Do not require every tranche design to include every heavyweight section. Big-design sections are required only where relevant.

## Workflow Components

### `major_project_roadmap_phase.yaml`

Purpose: turn one broad project brief into an approved project roadmap and tranche manifest.

Inputs:

- `state_root`
- `project_brief_path`
- `project_roadmap_target_path`
- `tranche_manifest_target_path`
- `roadmap_review_report_target_path`

Outputs:

- `project_roadmap_path`
- `tranche_manifest_path`
- `roadmap_review_report_path`
- `roadmap_review_decision`

Prompt assets:

- `workflows/library/prompts/major_project_stack/draft_project_roadmap.md`
- `workflows/library/prompts/major_project_stack/review_project_roadmap.md`
- `workflows/library/prompts/major_project_stack/revise_project_roadmap.md`

The roadmap phase should use the same tracked-findings review loop pattern as `tracked_design_phase.yaml`, with a deterministic manifest validation step after draft and after revise before review or selection consumes the manifest.

### `tracked_big_design_phase.yaml`

Purpose: produce and review a detailed design document for one selected tranche.

The interface should stay close to `tracked_design_phase.yaml`:

- `state_root`
- `brief_path`
- `design_target_path`
- `design_review_report_target_path`

Additional inputs:

- `project_brief_path`
- `project_roadmap_path`
- `tranche_manifest_path`

Outputs should match `tracked_design_phase.yaml`:

- `design_path`
- `design_review_report_path`
- `design_review_decision`

Prompt assets:

- `workflows/library/prompts/major_project_stack/draft_big_design.md`
- `workflows/library/prompts/major_project_stack/review_big_design.md`
- `workflows/library/prompts/major_project_stack/revise_big_design.md`

The big-design prompts should ask for deeper design where relevant:

- ADR or architecture decision section
- type-driven interface contracts
- data flow and ownership
- module/package boundaries
- source-of-truth, oracle, and provenance contracts
- spec and documentation updates
- migration or compatibility strategy
- performance model and batching implications
- verification strategy
- sequencing constraints, pivots, non-goals, and deferred work

The approved big design must be self-contained for downstream phases. The existing generic plan phase consumes only the approved design, and the existing implementation phase consumes only the approved design and plan. Therefore the design must carry the selected tranche brief summary, relevant manifest fields, prerequisites, target artifacts, roadmap constraints, design depth, completion gate, and project-level decisions needed later.

### `major_project_tranche_design_plan_impl_stack.yaml`

Purpose: run a selected tranche through:

1. `tracked_big_design_phase.yaml`
2. existing `tracked_plan_phase.yaml`
3. existing `design_plan_impl_implementation_phase.yaml`

The stack should look like `backlog_item_design_plan_impl_stack.yaml`, but its design phase consumes project context and selected tranche context.

### Optional Driver

Add a runnable example driver only after the reusable library pieces exist:

- `workflows/examples/major_project_tranche_design_plan_impl_stack_v2_call.yaml`

This driver should call the roadmap phase from a project brief, select one ready tranche from the generated validated manifest, and call the tranche stack. A later drain driver may run multiple tranches, but one-tranche execution should be the first supported path.

## Artifact Model

Use explicit artifacts instead of implicit file conventions.

| Artifact | Owner | Purpose |
| --- | --- | --- |
| `project_brief` | roadmap phase | Original broad backlog item. |
| `project_roadmap` | roadmap phase | Approved project-level roadmap and sequencing rationale. |
| `tranche_manifest` | roadmap phase | Ordered JSON list of tranches and prerequisites. |
| `roadmap_open_findings` | roadmap review loop | Carried roadmap findings. |
| `tranche_ledger` | driver | Records completed, skipped, blocked, or selected tranches. |
| `selected_tranche_brief` | driver | Current tranche brief consumed by big design. |
| `tranche_design` | big-design phase | Approved design for the selected tranche. |
| `design_open_findings` | big-design review loop | Carried design findings. |
| `tranche_plan` | plan phase | Approved implementation plan for the selected tranche. |
| `plan_open_findings` | plan review loop | Carried plan findings. |
| `execution_report` | implementation phase | Current implementation report for the selected tranche. |
| `implementation_review_report` | implementation review loop | Review result for the selected tranche implementation. |

## Tranche Manifest Contract

The manifest should be JSON so deterministic driver steps can validate and select from it.

Minimal schema:

```json
{
  "project_id": "pytorch-port",
  "project_brief_path": "docs/backlog/pytorch-port.md",
  "project_roadmap_path": "docs/plans/pytorch-port-roadmap.md",
  "tranches": [
    {
      "tranche_id": "repo-docs-and-architecture-baseline",
      "title": "Repository documentation and architecture baseline",
      "brief_path": "docs/backlog/generated/pytorch-port/repo-docs-and-architecture-baseline.md",
      "design_target_path": "docs/plans/pytorch-port/repo-docs-and-architecture-baseline-design.md",
      "design_review_report_target_path": "artifacts/review/pytorch-port/repo-docs-and-architecture-baseline-design-review.json",
      "plan_target_path": "docs/plans/pytorch-port/repo-docs-and-architecture-baseline-implementation-plan.md",
      "plan_review_report_target_path": "artifacts/review/pytorch-port/repo-docs-and-architecture-baseline-plan-review.json",
      "execution_report_target_path": "artifacts/work/pytorch-port/repo-docs-and-architecture-baseline-execution-report.md",
      "implementation_review_report_target_path": "artifacts/review/pytorch-port/repo-docs-and-architecture-baseline-implementation-review.md",
      "item_summary_target_path": "artifacts/work/pytorch-port/repo-docs-and-architecture-baseline-summary.json",
      "prerequisites": [],
      "status": "pending",
      "design_depth": "big",
      "completion_gate": "implementation_approved"
    }
  ]
}
```

Required tranche fields:

- `tranche_id`
- `title`
- `brief_path`
- `design_target_path`
- `design_review_report_target_path`
- `plan_target_path`
- `plan_review_report_target_path`
- `execution_report_target_path`
- `implementation_review_report_target_path`
- `item_summary_target_path`
- `prerequisites`
- `status`
- `design_depth`
- `completion_gate`

The roadmap phase may include richer metadata, but the first driver should depend only on the required fields.

## Step Consumption Contract

| Step | Consumes | Produces |
| --- | --- | --- |
| `DraftProjectRoadmap` | `project_brief` plus repo docs selected by prompt | `project_roadmap`, `tranche_manifest` |
| `ValidateTrancheManifest` | `project_roadmap`, `tranche_manifest` pointer paths | validated `project_roadmap`, validated `tranche_manifest`, counts |
| `ReviewProjectRoadmap` | `project_brief`, validated `project_roadmap`, validated `tranche_manifest`, `roadmap_open_findings` | roadmap review report, decision, counts |
| `ReviseProjectRoadmap` | `project_brief`, `project_roadmap`, `tranche_manifest`, roadmap review report/findings | revised roadmap and manifest |
| `SelectNextTranche` | validated `tranche_manifest`, optional `tranche_ledger` | selection status, selected tranche brief path, and selected tranche paths |
| `DraftBigDesign` | `selected_tranche_brief`, `project_brief`, `project_roadmap`, `tranche_manifest` | `tranche_design` |
| `ReviewBigDesign` | `selected_tranche_brief`, `project_roadmap`, `tranche_design`, `design_open_findings` | design review report, decision, counts |
| `ReviseBigDesign` | `selected_tranche_brief`, `project_roadmap`, `tranche_design`, design review report/findings | revised `tranche_design` |
| `DraftPlan` | approved self-contained `tranche_design` | `tranche_plan` |
| `ReviewPlan` | approved `tranche_design`, `tranche_plan`, `plan_open_findings` | plan review report, decision, counts |
| `RevisePlan` | approved `tranche_design`, `tranche_plan`, plan review report/findings | revised `tranche_plan` |
| `ExecuteImplementation` | approved `tranche_design`, approved `tranche_plan` | source/docs edits and `execution_report` |
| `ReviewImplementation` | approved `tranche_design`, approved `tranche_plan`, `execution_report`, current checkout | implementation review report and decision |
| `FixImplementation` | approved `tranche_design`, approved `tranche_plan`, `execution_report`, implementation review findings | updated implementation and report |
| `FinalizeTranche` | implementation approval, selected tranche id, manifest, ledger | updated ledger and item summary |

## Prompt Responsibilities

Prompts own judgment. Workflows own deterministic control.

Roadmap prompts should decide:

- project-level architecture direction
- tranche boundaries
- ordering and prerequisites
- what each tranche is expected to produce
- which tranches are blocked by missing evidence or external prerequisites

Roadmap prompts should not:

- implement source changes
- write tranche implementation plans
- draft all tranche designs
- manage loop counters or selection ledgers

Big-design prompts should decide:

- detailed implementation shape for the selected tranche
- whether ADR sections, type/interface contracts, data-flow diagrams in prose, spec/docs updates, or architecture changes are required
- how the tranche preserves project-level roadmap decisions
- which choices are semantically material and require justification

Plan and implementation prompts should remain the existing generic stack unless review shows a concrete gap.

## EasySpin Mapping

The EasySpin backlog item should be treated as a major project brief:

`docs/backlog/pytorch-port.md`

Suggested project-level outputs:

- `docs/plans/pytorch-port-roadmap.md`
- `state/easyspin-pytorch-port/roadmap/tranche_manifest.json`
- `docs/backlog/generated/pytorch-port/<tranche-id>.md`

Suggested per-tranche outputs:

- `docs/plans/pytorch-port/<tranche-id>-design.md`
- `docs/plans/pytorch-port/<tranche-id>-implementation-plan.md`
- `artifacts/work/pytorch-port/<tranche-id>-execution-report.md`
- `artifacts/review/pytorch-port/<tranche-id>-design-review.json`
- `artifacts/review/pytorch-port/<tranche-id>-plan-review.json`
- `artifacts/review/pytorch-port/<tranche-id>-implementation-review.md`

The previously completed ordinary EasySpin stack should be treated as exploratory/prerequisite context, not as the canonical project decomposition.

## Review Gates

Roadmap review should reject when:

- the project is not decomposed into coherent sequential tranches
- tranche prerequisites are missing or circular
- a tranche is too broad to review or too small to verify
- the roadmap hides architecture, API, oracle, or data-flow decisions inside implementation
- generated tranche briefs cannot stand alone as inputs to a design phase

Big-design review should reject when:

- semantically material choices are unjustified
- data contracts, APIs, ownership, or provenance are ambiguous
- spec/doc changes needed by the tranche are omitted
- the design conflicts with the approved roadmap without explaining why
- the design proposes implementation before resolving blocking architecture decisions
- verification is too weak for the tranche's risk

Implementation review should keep its current standard: verify required plan tasks first, then correctness, then non-blocking cleanup.

## Open Decisions

1. Whether the first driver runs exactly one selected tranche or can optionally drain all ready tranches.
   Recommendation: start with one selected tranche per run.

2. Whether roadmap review should use JSON findings or markdown findings.
   Recommendation: use the same JSON findings contract as tracked design and plan review loops.

3. Whether to update `backlog_item_design_plan_impl_stack.yaml` to accept a design phase import alias or create a separate tranche stack.
   Recommendation: create a separate tranche stack first. Generalize only after the interface proves stable.

4. Whether selected tranche briefs are generated markdown files or JSON strings embedded in the manifest.
   Recommendation: generate markdown files and reference them from the manifest so provider steps consume ordinary files.
