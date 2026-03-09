take the role of a principal engineer doing a repo hygiene and maintainability review

Review the repository for structural hygiene issues that are likely to create bugs, slow change, or make verification misleading.

Prioritize:
- oversized files or classes with too many responsibilities
- repeated bug-prone control-flow or state-management patterns
- generated/runtime files polluting the repo or git index
- brittle tests that lock in wording instead of behavior
- duplicated prompt or workflow patterns that should be consolidated

Treat a very large module or class as a likely finding unless there is a strong architectural reason for it to stay that way.
Do not spend time on style nits or low-value formatting feedback.

Write findings first, ordered by severity, with concrete file references and short explanations of:
- why the current shape is risky
- what a principled fix would look like

If no serious hygiene issues exist, say so explicitly and name any residual monitoring risks.
