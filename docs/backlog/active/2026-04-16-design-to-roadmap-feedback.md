# Backlog Item: Add Design-To-Roadmap Feedback For Major-Project Workflows

- Status: active
- Created on: 2026-04-16
- Plan: none yet

## Scope
Add an explicit feedback path for cases where a tranche design or design review exposes a roadmap-level problem that cannot be handled inside the selected tranche.

Today, major-project roadmap prompts own global outcome coverage and tranche decomposition, while tranche design prompts own local implementation shape. That boundary is correct. The missing capability is a structured way for a later design/review phase to say: "this tranche can proceed only after the roadmap or manifest is amended" or "the selected tranche is valid, but the roadmap is missing follow-on work."

Do not add roadmap-gap prose to design prompts unless the workflow can route the signal into a later roadmap revision step.

## Desired Outcome
Major-project workflows can carry design-stage roadmap feedback back to the roadmap phase without relying on ignored prose or manual intervention.

The intended handoff is:

1. Design or design review identifies a roadmap-level issue.
2. The workflow captures a structured roadmap amendment request.
3. A roadmap revision step consumes the request together with the current roadmap, manifest, tranche briefs, and original project brief.
4. The manifest and generated tranche briefs are revalidated.
5. Tranche selection resumes from the amended roadmap.

## Required Work
- Define a structured `roadmap_amendment_request` artifact or equivalent field in the design-review output contract.
- Include at least these decisions: `NONE`, `REQUEST_ROADMAP_REVISION`, and `BLOCK_SELECTED_TRANCHE`.
- Record evidence, affected tranche IDs, recommended amendment type, and required roadmap or manifest changes.
- Add a roadmap revision prompt that consumes the amendment request and updates the roadmap, manifest, and affected tranche briefs without redoing unrelated approved work.
- Add workflow routing so `NONE` continues to plan, `REQUEST_ROADMAP_REVISION` returns to roadmap revision/validation/selection, and `BLOCK_SELECTED_TRANCHE` stops or returns to tranche selection with a clear reason.
- Keep deterministic validation responsible for manifest schema, tranche references, path safety, and prerequisite consistency after amendment.
- Add a mocked-provider smoke test that exercises the feedback route end to end.

## Non-Goals
- Do not make every tranche design re-review the full roadmap.
- Do not add advisory roadmap-gap sections to design docs that no later step consumes.
- Do not make roadmap amendment a free-form prompt convention without a workflow contract.
- Do not add prompt snapshot tests or literal prompt-phrasing assertions.
- Do not change existing major-project prompt wording until the feedback path has an artifact and route.

## Success Criteria
- A design-review step can request a roadmap amendment in structured form.
- The workflow can revise and revalidate the roadmap and manifest before selecting or continuing a tranche.
- A smoke test demonstrates that a roadmap gap found during design review is not silently ignored by later plan or implementation phases.
- Prompt responsibilities remain clean: roadmap prompts own project decomposition, design prompts own tranche design, and the workflow owns routing between them.
