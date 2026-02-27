# Workflow Drafting Guide

This guide explains how to author reliable workflows when prompts, runtime contracts, and control flow all interact.

## 1) Mental Model: Three Contracts

Treat each provider step as three separate contracts:

1. Prompt contract
- What the agent is asked to do.

2. Runtime contract
- What the orchestrator validates after step execution (`expected_outputs` or `output_bundle`).

3. Flow contract
- What decides whether execution continues, loops, or stops (`on.success/failure.goto`, gates, max cycles).

Most workflow bugs come from assuming one contract implies another. It does not.

## 2) What Is Injected Automatically

For provider steps, prompt text is composed in this order:

1. Base prompt from `input_file` (literal file contents).
2. Optional `Consumed Artifacts` block (when `consumes` is present and `inject_consumes != false`).
3. Optional `Output Contract` block (when `expected_outputs` is present and `inject_output_contract != false`).

Important:
- Producer/consumer declarations do not replace prompt instructions. They only resolve artifact lineage and preflight checks.
- Output-contract injection describes required artifacts and paths. It does not execute file writes; the agent still must write files.

## 3) Deterministic Handoff Patterns

## A. `expected_outputs` (v1.2, file-per-artifact)

Use when each artifact naturally maps to one file.

Pros:
- Simple.
- Strong `relpath` safety checks (`under`, `must_exist_target`).
- Easy to inspect by humans.

Cons:
- Many pointer files can accumulate.

## B. `output_bundle` (v1.3, single JSON file)

Use when a step emits many scalar artifacts.

Pros:
- One deterministic JSON artifact file.
- Typed extraction via `json_pointer`.

Cons:
- Requires stricter JSON discipline.
- Still file-based (not raw stdout handoff).

## 4) Avoid Weak Gates

Common anti-pattern:
- `FixIssues` is considered successful if it writes required output files, even if blockers remain.

If your intent is root-cause closure, add an explicit gate that checks closure criteria before moving forward.

Example closure checks:
- Required canonical command completed.
- Fallback profile not used for canonical requirement.
- Required artifact exists and matches expected profile/tag.
- Review decision is `APPROVE`.

Do not rely on review prose alone to enforce completion.

## 5) Prompt Authoring Guidance

Keep prompts focused on decision-quality instructions, not plumbing duplicated from DSL.

Prompt should include:
- Task objective.
- Completion criteria.
- Explicit forbidden shortcuts (if needed).
- Required evidence format.

Prompt should usually avoid:
- Repeating pointer paths already injected via `consumes`.
- Repeating output file contracts already injected via `expected_outputs`.

Exception:
- Keep explicit lines when you want extra redundancy for high-risk steps.

## 6) Recommended Loop Pattern

For execute/review/fix loops:

1. ExecutePlan
- Publish execution session log pointer.

2. Run deterministic checks
- Produce machine-checkable evidence log.

3. Assess completion
- Convert execution evidence into structured status (`COMPLETE/INCOMPLETE/BLOCKED`).

4. ReviewImplVsPlan
- Produce decision + review artifact pointer.

5. Gate
- Route on decision.

6. FixIssues
- Consume plan + execution assessment + review.

7. Cycle gate
- Hard cap via `max_review_cycles`.

Add at least one hard closure assertion step if fallback behavior is possible.

## 7) Drafting Checklist

Before running a new workflow, confirm:

- DSL version supports used fields (`version` gating).
- Every provider step has explicit `expected_outputs` or `output_bundle` where deterministic handoff is needed.
- `publishes.from` references real local artifact names.
- `consumes` reflects true runtime dependencies.
- Prompt text does not conflict with injected contracts.
- Gates encode real completion, not just artifact presence.
- Loop has bounded retries/cycles.
- `--debug` prompt audit is enabled for first runs.

## 8) Debugging Where Things Go Wrong

Use run artifacts under `.orchestrate/runs/<run_id>/`:

- `logs/<Step>.prompt.txt`
  - Shows fully composed prompt after injections.
- `state.json`
  - Shows step result, errors, and parsed artifacts.
- `logs/<Step>.stderr` and `<Step>.stdout`
  - Provider/command execution traces.

If behavior differs from prompt file content, inspect the composed `.prompt.txt` first.
