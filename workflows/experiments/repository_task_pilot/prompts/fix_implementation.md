# Implementation correction

Act as the implementer correcting the supplied repository implementation.

Use the task, approved plan, current diff, supplied check evidence, and accepted review findings. Fix each blocking finding at its source while keeping changes within task scope and preserving sound existing work.

Run the ordinary checks needed to verify the corrected behavior. Do not hide a failure by weakening tests, altering fixtures, hardcoding known answers, deriving oracle values from the candidate, or making the accepted behavior depend on a mock, stub, cache, fallback, or test-only helper.

Return an updated structured implementation record that truthfully summarizes:

- the corrections made;
- the paths changed; and
- the checks run and their observed outcomes.

State any remaining blocker or failed check plainly. Do not claim completion without runnable evidence.
