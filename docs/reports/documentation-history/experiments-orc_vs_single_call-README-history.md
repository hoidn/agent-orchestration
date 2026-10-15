# experiments/orc_vs_single_call/README.md: Historical Sections

Status: **Historical.** Original tense, versioned acceptance language, receipts
and commands are preserved as evidence, not current execution or work selection.
Current owner: [README.md](../../../experiments/orc_vs_single_call/README.md).

## September experiment inventory

Material of the experiment of 2026-09-28.

- Report: [`docs/reports/2026-09-28-orc-versus-single-call.md`](../2026-09-28-orc-versus-single-call.md)
- Guidance: [`docs/orc_workflow_design_lessons.md`](../../orc_workflow_design_lessons.md)
- Rerun of both workflows on the evaluated route (2026-10-14), unchanged, through the comparison harness:
  [`docs/reports/2026-10-14-orc-versus-single-call-evaluated.md`](../2026-10-14-orc-versus-single-call-evaluated.md)

| Path | Contents |
| --- | --- |
| `workflows/best_of_n.orc` | four implementers, one selector; Sonnet implements, `gpt-6-sol` selects |
| `workflows/reviewed_change.orc` | implement, review, revise; Sonnet implements, `gpt-6-sol` reviews |
| `workflows/*.providers.json` | provider bindings for each workflow |
| `task/` | the instructions given to the agents and the bug report package |
| `evaluation/rubric.md` | the four criteria the blind judges applied |
| `evaluation/results.json` | every rated patch, per judge and per criterion, and what each workflow selected |
| `evaluation/judge_ratings/` | the judges' ratings with their reasons, and the key from random id to patch |
| `harness/` | the agent CLI wrapper and the trial runners, with the paths of the machine the experiment ran on |

The patches themselves, the prompts and the agents' outputs are not tracked.
