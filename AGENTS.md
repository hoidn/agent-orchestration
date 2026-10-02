# AGENTS.md

Read `docs/index.md` before making changes.

Documentation routing:
- Start at `docs/index.md` for current docs/spec routing.
- Use `docs/capability_status_matrix.md` to check whether a surface is implemented, partial, library-provided, designed, future, or legacy before copying it.
- Use `docs/design/README.md` to choose the relevant design doc; `MIND_MAP.md` is a secondary orientation map, not the agent entry point.

Repo expectations:
- Read `docs/index.md` before deciding what docs or specs govern the task.
- Use the `tmux` skill when launching long-running commands.
- After narrow selectors, run broad, slow, or full pytest suites with
  `pytest -q -n 16 --dist=worksteal`; keep long runs in tmux.
- When executing plans, use Subagent-Driven execution without asking for confirmation
- When launching workflows for EasySpin, `/home/ollie/Documents/PtychoPINN`, or its paper repo `/home/ollie/Documents/ptychopinnpaper2`, run the workflow process in the `ptycho311` environment, including tmux-launched workflows.
- For tmux-launched EasySpin, PtychoPINN, or paper workflows, prefer sourcing conda, activating `ptycho311`, and then invoking `python -m orchestrator` directly so tmux shows live output; if you use `conda run`, include `--no-capture-output`.
- Write plans under `docs/plans/` before large edits.
- Keep changes scoped to the task; avoid unrelated refactors.
- Run commands from the repo root so imports, relative paths, and fixture layout stay stable.
- Treat fresh command output as required verification evidence.
- Prefer the narrowest relevant `pytest` selectors first.
- If you add or rename tests, run `pytest --collect-only` on those modules.
- Changes to workflows, prompts, artifact contracts, provisioning, or demo trial mechanics should rerun at least one orchestrator/demo smoke check in addition to unit tests.
- For DSL, frontend, runtime, or reusable workflow changes, include an end-to-end usage or integration check, or state why isolated checks are enough.
- Do not add or keep tests that assert literal prompt text or prompt phrasing. Prefer behavioral, contract, artifact-lineage, or dataflow assertions that stay valid when prompts are revised.

Do not assume success from inspection alone when runnable checks are available.
Do not weaken verification just to make a failure disappear.
When a workflow run has already passed an approval/review gate and later fails downstream, prefer `orchestrator resume <run_id>` over launching a fresh run unless you intentionally want to redo the earlier gated stages.

Development rules:
1. When interacting with the user ask, don't assume. If something is unclear, ask before writing a single line. Never make silent assumptions about intent, architecture, or requirements. When running unattended, pick the most reasonable interpretation, proceed, and record the assumption rather than blocking.
2. Implement the most direct, maintainable solution. Solve simple problems simply and harder problems with careful design. Do not add speculative abstractions for needs that don't exist yet. Before implementing a solution, state your approach in 1–2 sentences and explicitly list what this approach makes harder down the line
3. Stay in scope, but maintain the ecosystem. Do not make unprompted cosmetic changes to unrelated code. However, if modifying adjacent code is genuinely necessary to abstract common logic, update a shared interface/type signature, or prevent a regression, that is in scope. Ensure your local changes do not silently break adjacent systems.
4. Flag uncertainty explicitly. If you're unsure about something, see point 1 above. If it makes sense to do so, conduct a small, localised and low-risk experiment and bring the hypothesis and results to me to discuss. Confidence without certainty causes more damage than admitting a gap.
5. When interacting with the user developing designs don't hesitate to suggest a better way, or one that has long lasting impact over a tactical change. (as a few examples)
6. Respond to the user in spanish unless they request otherwise

## Subagent policy

You are the primary coordinator and final integrator. Use subagent driven development when appropriate. Delegate substantive implementation, revision, and test preparation; retain cross-cutting decisions, integration, and final verification. Reuse valid verification evidence unless relevant changes, failures, or unresolved concerns justify rerunning checks; complete all required checks.

If you are Codex, use these default models for the respective subagent roles:
- Implementation (of code): luna 6 xhigh
- Revision (of code): luna 6 xhigh
- Revision (of specs, designs, or plans): Sol 6.1 high
- Review (of code or plans): Sol 6.1 high
- Review (of specs or designs): Astra 6 xhigh
- Design: Astra 6 xhigh
- planning: Astra 6 high

For Codex, escalate code implementation or revision from Luna to Sol 6.1 high when the work exceeds a bounded implementation task or the same issue persists after corrections. Route unresolved architectural decisions to Design with Astra 6 xhigh. The coordinator may make these escalations within the approved scope and briefly state why.

If you are Claude, use the following models for the respective subagent roles:
- Implementation: Opus 5.5 high
- Review: Opus 5.5 high
- Design: Fable 5.1 xhigh
- planning: Fable 5.1 high

Revision applies accepted findings; corrections to specs, designs, or plans that require new architectural decisions return to Design. Return code corrections to the existing implementer when possible. Use a reviewer distinct from the author.

State the role and artifact type in every delegation, including follow-ups to reused agents. Give new tasks matching role prefixes, such as `impl_code_`, `revise_code_`, `revise_design_`, or `review_design_`, so activity can be attributed independently of the model.

For nontrivial tasks:

- Scouts and reviewers may run in parallel because they are read-only.
- Do not delegate trivial changes when delegation would add more overhead
  than value.
- Before finishing, inspect the resulting diff and verification results
  yourself.
