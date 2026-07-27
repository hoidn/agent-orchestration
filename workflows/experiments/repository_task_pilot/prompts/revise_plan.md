# Plan revision

Act as the plan reviser for the supplied repository task.

Use the task, discovery record, current plan, and accepted review findings. Resolve each blocking finding directly while preserving the task's original scope and repository constraints. Recheck cited paths or symbols before changing a technical claim.

Return a revised structured plan whose ordered steps contain:

- concrete implementation actions;
- preserved invariants and scope boundaries; and
- any genuine unresolved assumption or blocker.

Return acceptance checks that retain the supplied visible-check definition.

Keep sound parts of the current plan. Do not introduce fixture-specific answers, candidate-derived oracle values, weakened tests, or test-only substitutes for the requested public behavior.

Do not edit the product or claim that checks have run.
