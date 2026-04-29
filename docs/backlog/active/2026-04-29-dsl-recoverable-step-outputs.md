# Backlog Item: DSL Recoverable Step Outputs

- Status: active
- Created on: 2026-04-29
- Plan: none yet

## Scope
Design and implement a first-class DSL/runtime recovery surface for steps whose declared outputs can be safely reconstructed from durable evidence after a resume or relaunch.

The immediate trigger was the NeurIPS backlog drain: an item had already passed the plan gate, then failed downstream during implementation. A fresh workflow run recovered the in-progress item but reran planning because the selected-item workflow had no general way to hydrate the already-approved plan outputs. The local workflow fix added explicit plan-gate recovery, but the same pattern will recur for other workflows and gates.

The broader problem is not "plan recovery." The problem is that a workflow step's output contract is the thing downstream steps need, and today authors must hand-code recovery steps to reconstruct that contract from queue files, run state, or stable pointer files.

## Desired Outcome
Add a principled DSL/runtime mechanism for recoverable step outputs.

The likely shape is an authored, opt-in step surface such as `recover_outputs`, where the runtime can:

- check durable recovery evidence before executing a step
- validate reconstructed values against the step's normal `expected_outputs` or `output_bundle` contracts
- hydrate `steps.<Step>.artifacts.*` with recovered values
- mark the step as recovered in run state and observability
- let downstream references work exactly as if the step had executed successfully

This should make recovery behavior the runtime's deterministic responsibility once the workflow author declares where valid evidence comes from.

## Required Design Questions
- Should recovery attach to individual steps, imported `call` steps, output contracts, or artifact registry entries?
- What evidence sources are allowed in the first version: prior run state, existing pointer files, JSON files, frontmatter, consumed artifacts, or only explicit command-produced recovery bundles?
- How does the runtime prove the recovered outputs are still valid for the current inputs?
- Does recovery require an explicit approval marker, or is existence plus output-contract validation sufficient for some contracts?
- How should recovered steps appear in `state.json`, reports, monitor output, and resume behavior?
- How does this interact with `consumes` freshness, `publishes`, provider sessions, `repeat_until`, structured branches, and imported workflows?
- What is the compatibility story for existing workflows and run states?

## Likely Design Direction
Prefer declarative opt-in over implicit global skipping.

Good:

- The workflow author declares the evidence source and validation requirements.
- The runtime validates recovered outputs using the same type/path rules as normal outputs.
- Recovery is visible as a distinct successful step status or debug field.
- If evidence is absent or invalid, the step executes normally unless the author explicitly chooses a blocking policy.

Avoid:

- blindly skipping any step whose output files happen to exist
- making provider prompts decide whether to reuse old outputs
- encoding workflow lifecycle states such as `IMPLEMENTATION_READY`
- making NeurIPS-specific queue/frontmatter assumptions part of the generic DSL

## Motivating Example
The NeurIPS plan-gate workflow should eventually be expressible without a custom `RecoverPlanGateOutputs` plus `ResolvePlanGateOutputs` pair.

Conceptually, the authored step should say:

- this plan step may recover `plan_path`, `plan_review_decision`, and `plan_review_report_path`
- valid evidence can come from the recovered in-progress backlog item's approved plan authority
- recovered `plan_path` must be under `docs/plans` and exist
- recovered review evidence must be present or a deterministic recovery report must be produced
- if recovery fails, run the fresh plan step

Downstream implementation should keep consuming `RunPlanPhase.artifacts.plan_path` and should not know whether that artifact was executed or recovered.

## Non-Goals
- Do not make every step implicitly recoverable by default.
- Do not treat stale output files as proof of semantic validity.
- Do not add NeurIPS-only queue semantics to the core runtime.
- Do not replace explicit workflow routing, review gates, or artifact freshness semantics.
- Do not weaken output contract validation to make recovery easier.

## Success Criteria
- A design document defines a minimal DSL surface for recoverable outputs, including validation, state representation, observability, and compatibility rules.
- A focused implementation supports at least one representative non-NeurIPS example and can replace the NeurIPS plan-gate hand-coded recovery pattern.
- Regression tests prove that valid recovery hydrates normal step artifacts and skips execution, while missing or invalid evidence executes the step normally or blocks according to authored policy.
- Runtime status/reporting makes recovered steps distinguishable from freshly executed steps.
- Documentation explains when to use recoverable outputs versus ordinary `consumes`, `expected_outputs`, `output_bundle`, or workflow-authored recovery commands.
