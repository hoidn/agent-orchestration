# Authoring revisions: the probe table

The "today" table that the tasks of the
[staged-workflow authoring plan](../../docs/plans/2026-11-13-staged-workflow-authoring-revisions-plan.md)
flip rows of. No provider or model is called: commands are the stand-in `emit.py`, and a probe that
names a provider is compiled only. The identity invariants are `scripts/invariants/`.

| File | What it is |
| --- | --- |
| `probe.py <spec> <dir> [prefix]` | Compiles (and runs, when the probe gives inputs) each probe of a spec through the command line, in `<dir>` outside the repository; one row per probe |
| `step1_spec.py` | The six findings of the design's §2, each as the smallest program at target 2.40 |
| `step1_today.txt` | Its output on `main` at `9bb55dda` (the resume command of the one failed run is cut) |

```bash
PATH=$PWD/experiments/thread_m/no_provider:$PATH PYTHONPATH=$PWD \
  python experiments/authoring_revisions/probe.py experiments/authoring_revisions/step1_spec.py /tmp/<dir>
```
