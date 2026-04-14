# Backlog Item: Run EasySpin Major Project Tranche Workflow

- Status: active
- Created on: 2026-04-14
- Plan: none yet

## Scope
Run the major-project tranche workflow against the EasySpin PyTorch port backlog item after the workflow family has been committed and is ready to copy or invoke from the EasySpin checkout.

The EasySpin backlog item is intentionally broader than one ordinary design-plan-implementation stack. It should enter the major-project workflow as a project brief, produce a roadmap and tranche manifest, then run one selected tranche through big design, plan, and implementation.

## Required Work
- Run from `/home/ollie/Documents/EasySpin`, not from this repository.
- Activate `ptycho311` before launching the orchestrator.
- Invoke `python -m orchestrator` directly so tmux streams output; do not use plain `conda run` without `--no-capture-output`.
- Use `/home/ollie/Documents/EasySpin/docs/backlog/pytorch-port.md` as the project brief.
- Preserve any prior ordinary EasySpin stack output as exploratory context, not as the canonical project decomposition.
- Let the roadmap phase decide the tranche sequence and prerequisites before executing a tranche.

## Success Criteria
- The workflow produces an EasySpin project roadmap and tranche manifest.
- Exactly one ready tranche is selected for the first run.
- The selected tranche completes or records a clear blocked outcome through the big-design, plan, and implementation phases.
- The run artifacts identify the roadmap, manifest, selected tranche brief, design, plan, execution report, and review reports.
