# Workflow Lisp Repl: Historical Sections

Status: **Historical.** Original sections retain their original tense, measurements
and acceptance language as evidence, not current authority or work selection.
Current owner: [workflow_lisp_repl.md](../../design/workflow_lisp_repl.md).

## Implementation Handoff

Likely files: `workflow_lisp/workflows.py`, `compiler.py`,
`closed/{frontend,artifact}.py` for transient context;
`workflow/evaluated/{views,capture}.py` for visible bindings and capture;
`workflow_lisp/repl_expr.py` for the ordinary expression bridge;
`cli/commands/{repl,__init__}.py`, `cli/main.py` and the installed CLI entry
in `pyproject.toml` for registration/session;
`tests/test_workflow_evaluated_repl.py` and the documentation surfaces above.

The safe first step is the transient compile-result seam, checked against
existing build callers and artifact bytes. Review capture/terminal parity and
recursive purity guards before integrating the CLI. Keep new modules below
500 lines, use current helpers, and retain error validation at every boundary.
Implementation and test preparation follow subagent-driven execution; the
coordinator owns integration, independent review and fresh final verification.
