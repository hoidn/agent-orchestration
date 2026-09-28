# `.orc` Workflows Versus A Single Agent Call

Material of the experiment of 2026-09-28.

- Report: [`docs/reports/2026-09-28-orc-versus-single-call.md`](../../docs/reports/2026-09-28-orc-versus-single-call.md)
- Guidance: [`docs/orc_workflow_design_lessons.md`](../../docs/orc_workflow_design_lessons.md)

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
