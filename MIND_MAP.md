# Mind Map

A short map of where things live. For doc routing, start at
[`docs/index.md`](docs/index.md); for normative behavior, [`specs/index.md`](specs/index.md).

## Source To Run

```text
.orc source
  -> orchestrator/workflow_lisp/          parse, typecheck, admit for the target
       lowering/   typed through 2.34  -> Core AST, Semantic IR, Executable IR
       closed/     typed 2.35/2.36     -> checked closed program
       dynamic/    native 3.0          -> checked dynamic program
  -> orchestrator/workflow/               execute
       executor.py, executable_ir.py      flat step runtime
       evaluated/                         closed-program evaluator, memo, resume
       dynamic/                           native evaluator, fresh-only state
  -> .orchestrate/runs/<run_id>/          state, effects, logs, reports
```

## Code

| Path | What it holds |
| --- | --- |
| [`orchestrator/cli/`](orchestrator/cli/) | `main.py` and one module per subcommand under `commands/` (`run`, `compile`, `resume`, `invalidate`, `repl`, `trial`, `report`, `dashboard`, `monitor`, ...) |
| [`orchestrator/workflow_lisp/`](orchestrator/workflow_lisp/) | The compiler: reader, type checker, modules, macros, prompts, lowering, closed and dynamic program builders, REPL support, and the builtin `stdlib_modules/`. Its [code map](orchestrator/workflow_lisp/README.md) lists the modules |
| [`orchestrator/workflow/`](orchestrator/workflow/) | Runtimes for the three program forms, plus provider attempts, adjudication, peer groups, supervision, phased delivery and resume planning |
| [`orchestrator/state.py`](orchestrator/state.py) | Run state persistence, atomic writes and persisted-profile selection |
| [`orchestrator/providers/`](orchestrator/providers/), [`orchestrator/exec/`](orchestrator/exec/) | Provider templates and invocation; command execution and output capture |
| [`orchestrator/dashboard/`](orchestrator/dashboard/), [`orchestrator/monitor/`](orchestrator/monitor/), [`orchestrator/observability/`](orchestrator/observability/) | Read-only dashboard, email monitor, reports and step summaries |
| [`orchestrator/lsp/`](orchestrator/lsp/) | `.orc` language server |
| [`orchestrator/security/`](orchestrator/security/) | Secrets handling and masking |

## Everything Else

| Path | What it holds |
| --- | --- |
| [`specs/`](specs/) | Normative contracts: DSL, IO, state, providers, CLI, versioning, observability, security |
| [`docs/`](docs/) | Guides, design docs, runbooks; `docs/plans/` and `docs/reports/` are historical records |
| [`workflows/examples/`](workflows/examples/) | Runnable `.orc` examples and their inputs; catalog in [`workflows/README.md`](workflows/README.md) |
| [`workflows/library/`](workflows/library/) | Reusable imported workflows and their prompts |
| [`prompts/`](prompts/) | Shared prompt catalog |
| [`experiments/`](experiments/) | Comparison experiments and their materials |
| [`tests/`](tests/) | Unit, frontend, runtime and workflow tests; see [`tests/README.md`](tests/README.md) |

## Where To Start A Change

- Language form or type rule: `orchestrator/workflow_lisp/`, then the matching
  design under [`docs/design/`](docs/design/README.md) and `tests/test_workflow_lisp_*.py`.
- Runtime behavior: the runtime for the affected profile under
  `orchestrator/workflow/`, the owning spec, and its tests.
- CLI option: `orchestrator/cli/commands/` and [`specs/cli.md`](specs/cli.md).
