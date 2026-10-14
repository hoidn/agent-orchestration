# E-B: Design-Review-Execute Against One Call On A Feature One Call Does Not Finish

Status: pre-registered; runs not started. This skeleton was committed before any E-B run, including
the qualification runs, and the results sections below are filled in afterwards.

## Question And Criterion

The question is whether `workflows/examples/design_review_execute.orc` delivers more of the hidden
acceptance tests than one `gpt-6.1-sol` call with the same task text and time limit. The task is
the Workflow Lisp REPL: base `47e85a9c`, with 16 hidden node ids from `fe49c1c4`. In the treatment,
`claude-fable-5-1` plans and revises, and `gpt-6.1-sol` reviews and executes.

- Criterion: [`experiments/compare/criteria/eb.json`](../../experiments/compare/criteria/eb.json).
- SHA-256: `de57fba1e200eb52ec3a946eb793293a280b014dbc8de25abf5a8e02a9d6ef0a`.
- It was frozen before any run, and every scoring run binds it.
- Runs use the frozen runtime at `aac25b7d`.
- Pooling and summarizing happen at the commit the criterion describes.
- Package SHA-256 at that commit: `585e057e3828b7eb7a9208ccb5188925949357737c03e156013096ceabcb5f61`.

## Qualification

(pending)

## Runs

(pending)

## Hidden Acceptance, Scores And Anchors

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
