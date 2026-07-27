# Blinded Repository-Task Review Rubric

Review only the supplied package. Do not infer how a candidate was produced and
do not use information from another session.

## Review order

1. Inspect the task, candidate diff, selected final files, and permitted check
   evidence.
2. Assess each candidate and record path-specific evidence citations.
3. Seal the pairwise quality judgment and its citations.
4. Only after the quality judgment is sealed, record one production-method
   guess for each opaque candidate. `UNKNOWN` is a valid guess. Guesses never
   change the quality judgment.

## Quality dimensions

Assess each candidate on:

- task completeness: whether the requested behavior and acceptance boundaries
  are fully addressed;
- behavioral correctness: whether the implementation and supplied checks
  support the claimed behavior, including important edge cases;
- maintainability: whether the result is clear, direct, and reasonably easy to
  modify without avoidable coupling;
- scope control: whether changes remain focused on the task and avoid
  speculative or unrelated work; and
- evidence quality: whether claims are supported by the supplied diff, final
  files, and check evidence.

Every material claim must cite one or more paths inside the package. Treat a
missing or ambiguous artifact as missing evidence; do not invent its contents.

## Pairwise outcome

Return exactly one:

- `A` when candidate A is better supported under the quality dimensions;
- `B` when candidate B is better supported;
- `TIE` when the candidates are materially equivalent; or
- `INDETERMINATE` when the supplied evidence cannot support a reliable
  distinction.

Do not force a winner. Keep hard behavioral findings separate from softer
maintainability judgments, and explain how the cited evidence supports the
outcome.

## Post-judgment guesses

After sealing the cited judgment, record exactly one guess for each opaque
candidate from the allowed choices supplied with the review record. Use
`UNKNOWN` whenever the package does not support a responsible guess. Guess
confidence, correctness, or symmetry must not alter the already sealed
judgment.
