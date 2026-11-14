A run root written before a `list/map-effect` body became any expression and a serial `:max` any `Int`
expression (surface coherence, I1). **Never regenerate it**: it exists to prove that a run recorded under
the old compiler still resumes to the same outcome.

Recorded on 2026-11-13 with the package at `ae36901d`, in `/tmp/i1-tmp/rec/ws`, by
`python -m orchestrator run main.orc --command-boundaries-file commands.json`; no provider. `main.orc`
maps three items under `:max 2`: the run committed items 1 and 2 and ended `list_map_effect_cap_exceeded`.

`runs/<run id>/` is copied to `.orchestrate/runs/`; the lock, the build cache and the call log are not
kept. `tests/test_workflow_lisp_map_effect_general_body.py` resumes it.
