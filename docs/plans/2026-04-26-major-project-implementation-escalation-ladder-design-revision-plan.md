# Revision Plan: Major-Project Implementation Escalation Ladder Design

## Goal

Revise `2026-04-26-major-project-implementation-escalation-ladder-design.md` to address the first five gaps identified by the T26 simulation report.

## Required Revisions

1. Localize the workflow and prompt blast radius so the escalation ladder stays major-project-only.
2. Define a concrete roadmap-revision entry workflow and its caller/callee contract.
3. Tighten `BLOCK` versus escalation semantics for plan and big-design review.
4. Specify deterministic reset and archive rules for escalation context and implementation iteration ledgers.
5. Add explicit early-phase escalation expectations so initial design and plan review can escalate oversized tranches before implementation churn begins.

## Planned Edits

- Update the design scope and workflow inventory to introduce major-project-specific plan and implementation phase variants.
- Add a new roadmap-revision phase section with typed inputs, outputs, and drain routing.
- Add a dedicated decision-boundary section for `BLOCK`, `ESCALATE_REDESIGN`, and `ESCALATE_ROADMAP_REVISION`.
- Add lifecycle sections for initialization, activation, archival, reset, and tranche-terminal cleanup of escalation artifacts.
- Revise the prompt-edit section so the early executability checks and escalation duties are explicit in major-project-local prompts.
