# E-A: Maintained Workflows Against Single Calls On The Evaluated Route

Status: pre-registered; runs not started. This skeleton was committed before any E-A run, and the
results sections below are filled in afterwards.

## Question And Criterion

The question is whether, on the evaluated route, `best_of_n` and `reviewed_change` beat single calls
on the September task (`468e7908`, `bugs/loop_result_paths`), as they did on the flat route.

- Criterion: [`experiments/compare/criteria/ea.json`](../../experiments/compare/criteria/ea.json).
- SHA-256: `0030e44a3b765de43dafff280f00600f52e7698afb9e002dec4a543da512f7c9` (amendment 2; earlier versions are cited in its `amends` and `amends_2` fields).
- It was frozen before any run, and every scoring run binds it.
- Harness, runtime and task package: the frozen runtime at commit `197e35ed` for `best_of_n` and at `1a77e0af` for the
  other arms. The difference touches only `best_of_n`'s state directory (R37). The runs made at `aac25b7d`
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
