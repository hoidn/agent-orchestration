# Roadmap Runtime Capability Boundary Prompt Simulation

## Purpose

Test whether a small roadmap-prompt improvement would have made the EasySpin PyTorch-port roadmap identify public CUDA/device execution as an explicit tranche, acceptance gate, blocker, or non-goal instead of burying it inside performance-readiness language.

This is a simulation-only experiment. Do not edit prompts while running it.

## Candidate Prompt Change

Proposed draft-roadmap insertion, placed after the completion-boundary paragraph and before `The roadmap must:`:

```text
For technology-port roadmaps, identify material runtime capability dimensions implied by the brief, such as backend, device, dtype, precision, batching, public execution path, and performance claims. Each material dimension must be assigned to an implementation tranche, an acceptance gate, an explicit blocker, or an explicit non-goal.
```

Proposed review-roadmap rejection bullet, placed near the completion-boundary and omitted-in-scope-work checks:

```text
- a technology-port roadmap leaves a material runtime capability dimension implied by the brief, such as backend, device, dtype, precision, batching, public execution path, or performance claim, unassigned to a tranche, acceptance gate, explicit blocker, or explicit non-goal
```

The change is intentionally generic. It must not say "CUDA" except as an example in scenario analysis, and it must not require every technology-port project to implement GPU support.

## Prompt Surfaces

Primary prompt files:

- `workflows/library/prompts/major_project_stack/draft_project_roadmap.md`
- `workflows/library/prompts/major_project_stack/review_project_roadmap.md`

Relevant logged historical prompts from the EasySpin run:

- `/home/ollie/Documents/EasySpin/.orchestrate/runs/20260414T231811Z-ifx443/call_frames/root.run_roadmap_phase__visit__1/logs/DraftProjectRoadmap.prompt.txt`
- `/home/ollie/Documents/EasySpin/.orchestrate/runs/20260414T231811Z-ifx443/call_frames/root.run_roadmap_phase__visit__1/logs/ReviewProjectRoadmap.prompt.txt`

Important historical output:

- `/home/ollie/Documents/EasySpin/artifacts/review/pytorch-port/project-roadmap-review.json`

## Scope And Blast Radius

These prompts are used by the reusable major-project roadmap phase. The experiment should evaluate major-project roadmap behavior, not tranche design, plan, implementation, or implementation-review behavior.

The prompt change affects broad roadmap decomposition only. It should not:

- force CUDA or GPU work into projects that do not imply it
- turn every performance concern into a separate tranche
- require implementation details in the roadmap
- weaken existing completion-boundary, prerequisite, cross-tranche reuse, or manifest checks

## Simulation Arms

Run each target scenario against these three arms:

1. **Original EasySpin Prompts**
   Use the logged EasySpin roadmap prompt bodies from run `20260414T231811Z-ifx443`.
   For non-EasySpin scenarios, substitute only the consumed artifact paths needed for the scenario while preserving the logged prompt wording.

2. **Current Prompts**
   Use the current prompt files exactly as written, without the candidate prompt change.

3. **Improved Current Prompts**
   Use the current prompt files plus only the candidate draft and review lines above.

For arm 3, do not rewrite surrounding prompt language. The point is to isolate the marginal effect of the candidate lines on top of the current prompt set.

## Scenario A: EasySpin PyTorch Port Target Case

Goal: determine whether the current prompts already fix the original miss, and whether the improved current prompts are more likely to make public CUDA/device execution visible as an explicit roadmap item or explicit deferral.

Use these artifacts:

- Brief: `git -C /home/ollie/Documents/EasySpin show 2d25bd6f:docs/backlog/pytorch-port.md`
- Pre-correction roadmap: `git -C /home/ollie/Documents/EasySpin show 2d25bd6f:docs/plans/pytorch-port-roadmap.md`
- Historical review report: `/home/ollie/Documents/EasySpin/artifacts/review/pytorch-port/project-roadmap-review.json`
- Historical logged prompts listed above

Do not inspect current T32 roadmap/tranche files until after writing the scenario judgment.

Pass condition for the current or improved current prompts:

- The simulated roadmap or review must treat device/dtype/public execution semantics as a material capability dimension implied by a PyTorch port.
- It must create or demand a tranche, gate, blocker, or explicit non-goal for public device execution after relevant parity and performance evidence exists.
- A generic phrase like "benchmark GPU where available" or "record GPU readiness notes" is not enough.
- It must avoid premature broad GPU claims before parity, oracle, shape, and functional implementation evidence exists.

Record whether the likely result is:

- `PASS_STRONG`: public CUDA/device execution would likely become an explicit tranche or acceptance gate.
- `PASS_WEAK`: the issue would likely be noticed, but only as a deferral or review finding needing another iteration.
- `NO_CHANGE`: the roadmap would probably still bury CUDA/device semantics under performance readiness.
- `REGRESSION`: the prompt would likely cause premature or overbroad GPU work.

## Scenario B: Generic Backend-Port Hard Case

Goal: check that current and improved current prompts improve backend-port roadmaps without hardcoding CUDA.

Use:

- `/home/ollie/Documents/agent-orchestration/workflows/examples/inputs/major_project_brief.md`

This fixture says "port a small analysis subsystem to a new backend" but does not mention GPU/CUDA. The improved prompt should make the roadmap identify backend/runtime capability dimensions that are actually implied by the brief, without hallucinating CUDA.

Pass condition:

- The proposed arm may ask for backend selection, public execution path, batching/numerical behavior, and performance acceptance if relevant.
- It should not require CUDA, FP32, or GPU benchmarks unless the brief or repository context supports them.
- It should not materially increase the number or size of tranches compared with the current prompt unless the added tranche closes a real completion-boundary gap.

## Scenario C: Non-Port Workflow Dashboard Regression Case

Goal: check that the improved current prompt remains inert for broad projects that are not technology ports.

Use:

- `/home/ollie/Documents/agent-orchestration/docs/backlog/active/2026-04-13-workflow-dashboard-observability.md`

Pass condition:

- The candidate lines should not introduce device/dtype/backend noise.
- The roadmap should still focus on read-only dashboard architecture, state projection, path safety, routes, tests, and observability surfaces.
- Any additional finding must be tied to a real completion-boundary gap, not to the runtime-capability wording.

## Simulation Procedure

For each scenario and arm:

1. Read the brief and the relevant prompt text.
2. Predict the roadmap decomposition the prompt would likely induce.
3. Predict the review decision and the most important high/medium findings.
4. Compare the predicted output against the pass conditions.
5. Note expected artifact size/complexity, iteration count, and process-noise risk.

Do not run the full workflow. This is an in-head simulation using real prompt surfaces and real artifacts.

## Report Template

Write the completed report to:

`docs/plans/2026-04-18-roadmap-runtime-capability-boundary-simulation-report.md`

Use this structure:

```markdown
# Roadmap Runtime Capability Boundary Simulation Report

## Decision

Recommendation: ADOPT_AS_WRITTEN | ADOPT_NARROWLY | REVISE_AND_RESIMULATE | REJECT | BROADEN_WITH_SEPARATE_PROPOSAL

One-paragraph rationale.

## Scenario Results

| Scenario | Arm | Expected behavior | Important findings | Regression risk | Outcome |
| --- | --- | --- | --- | --- | --- |
| A EasySpin PyTorch port | Original EasySpin Prompts | ... | ... | ... | ... |
| A EasySpin PyTorch port | Current Prompts | ... | ... | ... | ... |
| A EasySpin PyTorch port | Improved Current Prompts | ... | ... | ... | ... |
| B Generic backend port | Original EasySpin Prompts | ... | ... | ... | ... |
| B Generic backend port | Current Prompts | ... | ... | ... | ... |
| B Generic backend port | Improved Current Prompts | ... | ... | ... | ... |
| C Dashboard non-port | Original EasySpin Prompts | ... | ... | ... | ... |
| C Dashboard non-port | Current Prompts | ... | ... | ... | ... |
| C Dashboard non-port | Improved Current Prompts | ... | ... | ... | ... |

## Analysis

- Did the candidate move the desired issue earlier into roadmap review?
- Did the current prompt set already solve the issue compared with the original EasySpin prompt set?
- Did it avoid turning GPU/CUDA into a universal requirement?
- Did it create checklist gravity or unnecessary tranche splitting?
- Did it interact cleanly with current completion-boundary wording?

## Recommended Edit

Quote the exact final wording recommended for each prompt, or explain why no edit should be applied.
```

## Adoption Bar

Adopt only if:

- Scenario A improves over both original EasySpin prompts and current prompts, or the report explains why current prompts are already sufficient and no edit is needed.
- Scenarios B and C do not show material regression.
- The candidate improves roadmap-level judgment without requiring downstream design, plan, or implementation prompts to compensate.

Use `ADOPT_NARROWLY` if the change should apply only to major-project roadmap prompts. Use `BROADEN_WITH_SEPARATE_PROPOSAL` if the simulation shows matching design/plan prompt edits are also needed.
