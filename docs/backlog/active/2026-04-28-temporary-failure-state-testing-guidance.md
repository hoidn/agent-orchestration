# Backlog Item: Temporary Failure-State Testing Guidance

- Status: active
- Created on: 2026-04-28
- Plan: none yet

## Problem

Implementation and fix agents can make a test suite green by changing tests to
expect the current blocked, failing, unsupported, or candidate-only behavior.
That can be useful when the test is explicitly checking report honesty, but it
is poor development practice when it replaces the target behavior that the
approved task still requires.

The result is subtle: the project appears to have a passing gate, while the
real blocker has only been reclassified as expected behavior. Later agents then
have to fight the test suite to finish the actual feature.

## Desired Outcome

Generic implementation, review, and testing guidance should make this rule
explicit:

> Do not make an acceptance test pass by changing it to expect a temporary
> failure state unless the approved scope has changed. If a blocked or failing
> state must be tested, keep that check separate from target-behavior
> acceptance and document the exit condition.

This should be handled through prompt and skill hygiene, not a new DSL feature
or project-specific convention.

## Scope

- Generic implementation/fix prompts that tell providers how to respond to
  review findings and failing tests.
- Generic review prompts that should flag tests which encode unfinished behavior
  as success.
- Development skills or guidance related to test-driven development,
  systematic debugging, executing plans, and receiving review feedback.
- Documentation or examples that explain the difference between target-behavior
  tests and blocker-honesty checks.

## Required Guidance

- Preserve or add a target-state test for the behavior the task actually wants.
- If current behavior is blocked, add a separate blocker-honesty check only for
  reports, ledgers, routing, or temporary diagnostic surfaces.
- Do not delete, invert, weaken, or skip a target acceptance check just to make
  a revision pass.
- If a temporary failure-state check is necessary, name it and document the
  exit condition in the test, report, or nearby task artifact.
- Reviewers should treat "tests pass because they now expect failure" as a
  testing smell unless the design, plan, or roadmap explicitly reduced scope.

## Non-Goals

- Do not add DSL fields, workflow routing semantics, or new artifact schemas for
  this item.
- Do not forbid tests that verify honest blocked-state reports or explicit
  unsupported contracts.
- Do not require every project to use the same marker, filename, or test layout.
- Do not turn this into project-specific policy for one downstream repository.

## Success Criteria

- Generic prompts and skills warn against converting target acceptance tests
  into temporary failure-state tests.
- Review guidance asks reviewers to flag this pattern.
- Existing workflows benefit through clearer provider instructions without
  schema changes.
- A future implementation that needs an interim blocked-state check keeps the
  target behavior visible and records how the interim check is supposed to be
  removed or flipped.
