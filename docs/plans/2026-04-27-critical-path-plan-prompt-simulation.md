# Critical-Path Plan Prompt Simulation

Date: 2026-04-27

## Inputs And Exclusions

Inputs inspected:

- `workflows/library/prompts/major_project_stack/draft_plan.md`
- `workflows/library/prompts/major_project_stack/review_plan.md`
- EasySpin approved T26 design:
  `/home/ollie/Documents/EasySpin/docs/plans/pytorch-port-roadmap/T26-full-chili-slow-motion-solver-expansion-design.md`
- EasySpin approved T26 plan:
  `/home/ollie/Documents/EasySpin/docs/plans/pytorch-port-roadmap/T26-full-chili-slow-motion-solver-expansion-plan.md`
- EasySpin T26 plan review:
  `/home/ollie/Documents/EasySpin/artifacts/review/pytorch-port-roadmap/T26-full-chili-slow-motion-solver-expansion-plan-review.json`
- EasySpin T26 implementation review/report evidence visible during the live run.

Excluded:

- No provider was actually re-run with the proposed prompt text.
- No prompt edits were applied for this simulation.
- The simulation does not judge whether the T26 implementation is scientifically complete; it tests whether the proposed prompt edit would likely have changed planning/review behavior.

## Compared Versions

Current prompt behavior:

- Draft prompt requires scope accounting, implementation units, dependency direction, and sequencing constraints.
- Review prompt rejects underscope, overbroad collapsed work, weak verification, and missing executable boundaries.
- Neither prompt explicitly requires a named critical-path gate before the task list.
- Neither prompt explicitly rejects plans that schedule downstream contracts/reports/docs before the behavior/API gate they describe.

Proposed draft prompt addition:

```md
Before the task list, name the critical path gates for the tranche's central claim. Order tasks so downstream contract, report, docs, and cleanup work cannot precede the behavior/API gate they describe. If a critical gate cannot be satisfied, the plan must stop there and escalate rather than continue with downstream work.
```

Proposed review prompt addition:

```md
Reject plans that list all required work but do not enforce the critical path. Downstream contracts, reports, docs, ledgers, or generated evidence must not be scheduled before the behavior/API gate they describe has passed.
```

## Scenario Setup

Scenario A, target failure:

- T26 `chili` implementation where the central claim is public CPU `torch.float64` closure.
- The approved plan listed exact solver replacement, catalog/report migration, T18 workflow acceptance, docs, and broad verification as sibling tasks.
- Implementation initially fixed narrower issues while the core preview-path/parity blockers remained open.

Scenario B, hard case:

- Same as T26, but assume selected `outputs.spec` parity cannot be made to pass with the approved solver design.
- Desired behavior is early escalation rather than report/catalog churn.

Scenario C, small case:

- A tranche with one local behavior change and one docs note, no generated contract bundle.
- Desired behavior is minimal overhead and no artificial ceremony.

## Evidence Ledger

- Observed: current draft prompt says every material design requirement must be accounted for, and tasks should put prerequisites before dependent work.
- Observed: current review prompt checks executable work, scope accountability, component boundaries, and verification gates.
- Observed: approved T26 plan goal is full CPU `torch.float64` closure and says current scope is the whole approved T26 design.
- Observed: approved T26 plan includes Unit 4 for replacing preview numerics with the exact solver path.
- Observed: approved T26 plan also puts contract surfaces, runtime policy, preflight gating, exact solver, report migration, docs, T18, T29, and verification in one broad task list.
- Observed: T26 plan review approved with no findings.
- Observed: implementation review found the tranche still on interim evidence-only contract and public `chili` still routed through preview numerics.
- Observed later in the live run: a subsequent implementation report claims the preview-path and selected-anchor parity issues were eventually addressed.
- Inferred: the current plan was not missing the central work; it was missing a hard gate that made that work dominate earlier implementation/review attention.

## Deterministic Workflow Delta

No deterministic workflow delta.

The proposed change alters provider judgment only. It does not change:

- workflow YAML
- DSL routing
- plan phase inputs/outputs
- review decision enum
- loop bounds
- implementation-phase behavior

## Simulated Event Log

### Scenario A: T26 Current Prompt

1. Draft plan consumes approved design and inactive escalation context.
   Output: broad plan with five implementation units and seven tasks.
   Rationale: current prompt rewards accounting for every material design requirement.
   Confidence: high, because this is the observed plan.

2. Review plan consumes design, plan, and open findings.
   Output: `APPROVE`.
   Rationale: the plan carries all design requirements, has units, and names verification commands.
   Confidence: high, because this is the observed review.

3. Implementation starts.
   Output: local fixes land around runtime-policy/support-envelope/report issues.
   Rationale: the plan allows many valid work surfaces to be attacked before the exact solver/parity gate is proven.
   Confidence: medium-high, based on observed implementation review findings.

4. Review finds core blockers remain.
   Output: `REVISE`; findings focus on interim contract and preview numerics.
   Rationale: the central claim was not made a blocking milestone before downstream surfaces.
   Confidence: high, based on observed review text.

### Scenario A: Proposed Prompt

1. Draft plan consumes same design.
   Output: plan includes a `Critical Path Gates` section before tasks.
   Likely gates:
   - public CPU `chili` rows do not use preview numerics
   - selected `outputs.spec` parity passes
   - catalogs/reports promote closure only after parity
   - T18 workflow passes only after public runtime closure
   - docs/examples/ledgers update last
   Confidence: medium-high; the proposed text directly asks for this.

2. Review plan checks critical path.
   Output: current observed plan would likely be `REVISE`.
   Rationale: it lists all work but does not enforce the exact-solver/parity gate before contract/report/docs work.
   Confidence: medium. A reviewer could still approve if it interprets existing sequencing lines generously, but the proposed rejection sentence gives a concrete reason to reject.

3. Revised plan makes exact solver/parity the central gate.
   Output: implementation starts with a red/green runtime-parity milestone.
   Rationale: downstream report/catalog/doc tasks are explicitly blocked until the core behavior/API gate passes.
   Confidence: medium.

4. Implementation review sees either core gate pass or fail before downstream churn.
   Output: fewer iterations spent on peripheral fixes before H-1/H-2 become central.
   Confidence: medium; provider still has to implement hard numerical work.

### Scenario B: Hard Case Current Prompt

1. Plan is broad and approved.
2. Implementation tries partial fixes.
3. Review repeatedly finds remaining parity or report closure gaps.
4. Likely terminal behavior: late escalation or many revise cycles.
   Confidence: medium.

### Scenario B: Hard Case Proposed Prompt

1. Plan names solver/parity as a hard gate.
2. Implementation attempts the gate first.
3. If selected parity cannot pass, report stops at that gate and asks for replan/redesign/roadmap recharter.
4. Downstream catalog/report/docs work is not used to mask the failure.
   Confidence: medium-high.

### Scenario C: Small Case Current Prompt

1. Draft plan creates one implementation unit or small task list.
2. Review approves if verification is adequate.
3. Implementation proceeds.
   Confidence: medium-high.

### Scenario C: Small Case Proposed Prompt

1. Draft plan names one critical gate in one sentence.
   Example: "Gate: API returns the new value and regression test passes."
2. Task list remains small.
3. Review does not add material burden because there are no downstream contracts/reports/docs.
   Confidence: medium. Some providers may add a small extra heading, but the wording is short enough to limit ceremony.

## Decision Rationale

The proposed edit targets the observed failure mode directly: the plan had the right work but allowed surrounding artifact/report/docs work to be treated as peer progress before the central runtime/parity gate was proven.

It does not ask for a table, exhaustive fields, or new artifacts. That reduces the risk of creating another process-heavy checklist.

## Comparison

Expected improvements:

- Earlier rejection of plans that flatten critical behavior and downstream evidence into sibling tasks.
- Less implementation review churn around report/catalog/docs work while core behavior remains absent.
- Clearer basis for escalation when the behavior/API gate cannot pass.

Expected costs:

- One extra sentence or short section in plans.
- Some chance of providers adding a verbose "critical path" heading even for simple work.

Iteration impact:

- T26-like hard tranches: likely fewer peripheral fix iterations before core blockers are addressed or escalated.
- Simple tranches: likely no meaningful change, unless the provider over-formalizes.

## Assumptions And Falsifiers

Assumptions:

- Plan drafters will interpret "central claim" as the main user-facing behavior/API claim, not every report field.
- Reviewers will use the new review sentence as a reason to reject complete-looking but ungated plans.
- Implementation agents follow the approved plan order enough for critical gates to matter.

Falsifiers:

- A new plan still lists downstream reports/docs before proving the core behavior.
- A review still approves such a plan.
- A simple tranche gains long critical-path boilerplate unrelated to risk.
- Implementation ignores a clearly gated plan and continues artifact-first work.

## Regression Risks

- The phrase "critical path gates" could become a new ceremonial heading if providers overdo it.
- For exploratory tranches, "behavior/API gate" might be too narrow; the central claim may be architectural discovery, reference-data quality, or migration readiness.
- The review prompt could become too rigid if it rejects legitimate early contract edits needed to write the red test or define the gate.

Mitigation:

- Keep the edit short.
- Use "behavior/API gate they describe" only for downstream contracts/reports/docs/ledgers/generated evidence, not for all contract authoring.
- Do not require a specific table or field list.

## Recommendation

`ADOPT_NARROWLY`

Apply the two minimal prompt edits to the major-project plan draft and review prompts only. Do not change workflow YAML or implementation prompts yet.

If a later run still churns, the next simulation should evaluate whether implementation review should explicitly downgrade artifact/report fixes when the current critical behavior gate remains red.
