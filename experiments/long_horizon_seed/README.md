# Long-Horizon Seeds

**Status: experiment seeds, not frozen and not guidance.** Four compact `.orc` programs that stage a long task, as
starting points for the search of roadmap Phase 6. The
[long-horizon plan](../../docs/plans/2026-11-13-long-horizon-task-family-and-seed-plan.md) (step 8) owns their
requirements, the freeze and the ledger. Nothing here calls a provider: every run in this directory and in its test
uses a scripted `claude`.

| Program | What it stages | Lines |
| --- | --- | ---: |
| `milestones.orc` (lead) | Setup, spec; rounds of plan, a work-check-review loop per milestone, check, acceptance | 54 |
| `staged.orc` | Setup, spec, plan; rounds of work, check, acceptance | 34 |
| `designed.orc` | `staged` with a design between spec and plan, reviewed at most twice | 62 |
| `roles.orc` | `milestones` with Agent Sessions | 56 |

`common.orc` holds their result types. Each takes two inputs, the task text and the intent; models, efforts and loop
bounds are literals in the program. `providers.json` and `commands.json` bind the three roles and the `dev-check`
command.

Every loop and map has a literal bound, so each program has a worst case in provider calls:

| Program | Bounds | Worst case |
| --- | --- | ---: |
| `staged` | 4 rounds | 11 |
| `designed` | 2 design reviews, 4 rounds | 15 (6 when the design is refused twice) |
| `milestones`, `roles` | 2 rounds, the first 8 milestones of a plan, 2 attempts a milestone | 6 + 8 × 8 = 70 |

A plan of more than eight milestones is cut to its first eight (`(list/take plan.milestones 8)` with `:max 8`) and
the run goes on; the planner is still told "at most eight". The milestones after the eighth are not built in that
round; the next round's plan is written after the round's check and acceptance and can take them up.

## How a run ends

`staged` and `designed` end with `Outcome`: `DONE`, or `BLOCKED` with a reason and the notes the exhausted loop ended
on. `milestones` and `roles` end with `Ending`, which is `Outcome` with two more fields:

- `cut`, in both variants: one row `{planned, built}` for each plan that had more milestones than were built; empty
  when no plan was cut.
- `built`, in `BLOCKED`: how each milestone built in the round ended, `{met, notes}`, when the run ended because a
  milestone was refused in both attempts (reason "milestone refused twice"); empty otherwise.

A refused milestone ends the run after the map: the plan's other milestones, up to eight in all, are still built,
because a serial map runs every item; then the run ends without the round's check and acceptance. `built` holds every
milestone's result, since the language has no operator that selects one element of a list.

## Run

```bash
PYTHONPATH=$PWD python experiments/long_horizon_seed/demo.py /tmp/lhs-demo [program [scenario]]
pytest -q -n 8 tests/experiments/test_long_horizon_seed.py
```

`demo.py` compiles each program, prints its digest and site keys, and runs its scenarios; a scenario declares the
result, the committed steps and the scripted answers, and the run must match.

## Site keys, and how the seeds compare

A step is named by its full site key (`demo.py` prints them from the closed program). Every last label is an authored
name. The one generated ordinal is `loop:#1[*]`, the loop a `list/map-effect` lowers to, in `milestones` and `roles`.

| Step | Last label | Key in `staged` | Key in `designed` |
| --- | --- | --- | --- |
| Setup, spec | `ready`, `spec` | `run / ready`, `run / spec` | the same |
| Design draft, review, revision | `draft`, `opinion`, `revised` | none | `run / draft`; `run / design=workflow:designed::review-design / loop:state[*] / opinion` and `… / design / body / else / revised` |
| Plan | `plan` | `run / plan` | `run / ACCEPTED / built=workflow:designed::build / plan` |
| A round's work, check, acceptance | `change`, `report`, `acceptance` | `run / loop:state[*] / change`, `… / report`, `… / else / acceptance` | the same three under `run / ACCEPTED / built=workflow:designed::build / loop:state[*]` |

**The seeds compare by last label, not by key.** `designed`'s plan and round steps sit under
`ACCEPTED / built=workflow:designed::build` and do not share `staged`'s key prefix; the labels and the role of each
step are the same in all four seeds. In `milestones` and `roles` the plan is inside the round
(`run / loop:state[*] / plan`), and a milestone's `change`, `report` and `verdict` are under
`… / built / body / loop:#1[*] / else / each=workflow:<program>::milestone / loop:state[*]`. The round's check and
acceptance come after the test of the milestones' results and are `run / loop:state[*] / else / report` and
`… / else / else / acceptance`. Two keys there end in `report`: the round's check and each milestone's check. In `roles` opening a conversation is a step of its own
(`planning` and `accepting` in `run`, `coding` and `reviewing` in each milestone).

## The check

`dev_check.py` is this kit's copy of the seed catalog's script
(`experiments/orc_structural_search/seeds/dev_check.py`, left unchanged because that kit's candidate ids and recorded
runs pin its bytes). The difference: a failed check's output begins with the reason (the command and its exit status,
its timeout, or the missing `dev-check.json`). The seeds pass that output to the next round.

## Known gaps

- After a milestone is refused twice, the plan's later milestones are still built before the run ends (`milestones`,
  `roles`): a map cannot stop early. A loop over the plan would stop at once, at an estimated seven more lines a seed
  (not built).
- The check is protected by prompt wording only, its command inherits the orchestrator's environment, and its output
  goes into the next prompt unfiltered: for step 9's design.
- The guide path the setup step reports may be any existing path under the workspace, a directory included: the
  language has no path kind for a regular file.
