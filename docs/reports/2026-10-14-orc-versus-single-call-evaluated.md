# E-A: Maintained Workflows Against Single Calls On The Evaluated Route

Status: pre-registered; runs not started. This skeleton was committed before any E-A run, and the
results sections below are filled in afterwards.

## Question And Criterion

The question is whether, on the evaluated route, `best_of_n` and `reviewed_change` beat single calls
on the September task (`468e7908`, `bugs/loop_result_paths`), as they did on the flat route.

- Criterion: [`experiments/compare/criteria/ea.json`](../../experiments/compare/criteria/ea.json).
- SHA-256: `6d1c4090a1b8d600e69360b2895f3e709a889bf0adb8dd9cd3c98c2c5c6bf989` (amendment 1; the first version, `a495900a…`, is cited in its `amends` field).
- It was frozen before any run, and every scoring run binds it.
- Harness, runtime and task package: the frozen runtime at commit `1a77e0af`. The runs made at `aac25b7d`
  were discarded before pooling, for two harness defects (R34 and R35). The criterion's `amends` field lists them.
- Package SHA-256: `5bb1487dadf33982af56170f351edad76bbfd3e31b35c85b67ab87d5d91302a3`.
- Design: [`docs/design/orc_effectiveness_comparison_harness.md`](../design/orc_effectiveness_comparison_harness.md).

## Runs

(pending)

## Scores, Anchors And Agreement

(pending)

## Contamination Scan

(pending)

## Cost

(pending)

## Verdict

(pending)

## Limits

(pending)

## Reproduce

(pending)
