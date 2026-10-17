# Documentation Index

`agent-orchestration` is a compiler and runtime for LLM-agent workflows written
in Workflow Lisp (`.orc`). Programs compose provider calls, commands and
ordinary computation behind declared contracts; the runtime validates results
and records run state under `.orchestrate/runs/<run_id>/`.

`specs/` defines normative behavior. `docs/` explains it. When they disagree,
the spec wins and the doc gets fixed.

## Start Here

| You want to | Read |
| --- | --- |
| Install, run a first compile check, see the main example | [README](../README.md) |
| A one-screen picture of the system | [Architecture Overview](architecture_overview.md) |
| Terms and the authoring/runtime split | [Orchestration Start Here](orchestration_start_here.md) |
| What the engine does during `run` and `resume` | [Runtime Execution Lifecycle](runtime_execution_lifecycle.md) |
| Whether a surface is implemented, partial or legacy | [Capability Status Matrix](capability_status_matrix.md) |
| A short map of the source tree | [Mind Map](../MIND_MAP.md) |

## Choose A Profile

The `(:target-dsl ...)` declaration in the source selects the profile. Typed
and native profiles are peers; pick the one whose trade-off fits the work.

| Profile | Targets | Choose it for | Limits | Read |
| --- | --- | --- | --- | --- |
| Typed flat | through 2.34 | Checked types, flat Core lowering, resume | No runtime closures; each target admits its own forms | [Versioning](../specs/versioning.md), [program shapes that run](lisp_workflow_drafting_guide.md#2a-program-shapes-what-runs-today) |
| Typed evaluated | 2.35, 2.36 | Checked closed programs, committed-result replay, resume and suffix invalidation; 2.36 adds local hooks with inferred captures | Portable providers only (no sessions, context capture, managed jobs or secrets); trials, supervision, peer groups, phased providers, adjudication, human input, resource transitions, views and parallel map refuse at build with `closed_program_gap` | [Evaluated execution](design/workflow_lisp_evaluated_execution.md), [local hooks](design/workflow_lisp_write_once.md) |
| Native | 3.0 | Ordinary `define`/`fn`, closures and real imports, with strict boundary schemas | Fresh runs only: no resume, retries, invalidation or result reuse; no parallel, child, trial, resource, view, host-input or provider session/context/phased/live surfaces | [Native target 3.0](../specs/versioning.md#native-target-30), [native authoring](lisp_workflow_drafting_guide.md#2b-native-30-dynamic-composition) |

## Author Workflows

| You want to | Read |
| --- | --- |
| Write a `.orc` workflow | [Workflow Lisp Drafting Guide](lisp_workflow_drafting_guide.md) |
| Check before writing whether a program shape runs | [Drafting guide §2A](lisp_workflow_drafting_guide.md#2a-program-shapes-what-runs-today) |
| Pick an example to start from | [Which Example Should I Copy?](../workflows/README.md#which-example-should-i-copy) |
| Reuse generation/selection, review/revise, evaluation or search procedures | [Library reference](lisp_library_reference.md#choose-by-task) |
| Decide between review, revise and select, and avoid known mistakes | [Designing `.orc` Workflows That Beat A Single Call](orc_workflow_design_lessons.md) |
| Write or reuse provider prompts | [Prompt Index](../prompts/README.md) |
| Call external tools from a workflow | [Command Adapter Contract](design/workflow_command_adapter_contract.md) |
| Inspect a run's bindings or try pure expressions | [REPL guide](lisp_workflow_drafting_guide.md#inspect-a-run-with-the-workflow-lisp-repl), [CLI](../specs/cli.md#workflow-lisp-repl) |
| Inspect loaded declarations, source, types or result files | [REPL introspection](design/workflow_lisp_repl_introspection.md), [CLI](../specs/cli.md#module-and-result-inspection) |
| Run pinned child runs and trials (target 2.25) | [Drafting guide](lisp_workflow_drafting_guide.md#pinned-child-runs-and-trials), [CLI](../specs/cli.md#workflow-lisp-trials-target-225) |
| Coordinate a live worker/supervisor or peer group (targets 2.16, 2.17) | [Live binding](design/workflow_lisp_provider_live_binding.md), [peer messaging](design/workflow_lisp_provider_peer_messaging.md) |
| See `.orc` next to the YAML it replaced | [Workflow Lisp MVP Comparison](workflow_lisp_mvp_comparison.md) |
| Decide whether content belongs in a spec, design, work item or workflow | [Work Definition Model](work_definition_model.md) |

## Reference

| You want to | Read |
| --- | --- |
| Normative contracts | [Master Spec](../specs/index.md): [DSL](../specs/dsl.md), [Step IO](../specs/io.md), [State](../specs/state.md), [Providers](../specs/providers.md), [CLI](../specs/cli.md), [Versioning](../specs/versioning.md), [Observability](../specs/observability.md), [Security](../specs/security.md), [Variables](../specs/variables.md), [Dependencies](../specs/dependencies.md), [Queues](../specs/queue.md) |
| Acceptance criteria | [Acceptance index](../specs/acceptance/index.md) |
| The Workflow Lisp language contract | [Frontend Specification](design/workflow_lisp_frontend_specification.md) |
| A design doc for a feature | [Design Documentation Index](design/README.md) |
| Principles for new language surfaces | [Workflow Language Design Principles](design/workflow_language_design_principles.md) |
| Implementation status of a surface | [Capability Status Matrix](capability_status_matrix.md) |
| Standard library procedures | [Library reference](lisp_library_reference.md) |
| Copy-role labels for examples | [Route/readiness labels](../workflows/README.md#workflow-lisp-routereadiness-labels) and the [registry](workflow_lisp_route_readiness_registry.json) |
| Test commands and markers | [Testing guide](../tests/README.md) |

## Operations

| You want to | Read |
| --- | --- |
| Email alerts for finished, failed or stalled runs | [Workflow Monitoring](workflow_monitoring.md), [Gmail app password setup](gmail_app_password_headless_monitor.md) |
| Launch the generic run watchdog | [Watchdog launch](../workflows/README.md#generic-run-watchdog-launch) |
| Launch the verified-iteration drain | [Drain launch](../workflows/README.md#verified-iteration-drain-launch) |
| Set up the `.orc` language server in an editor | [Language Server Setup](workflow_lisp_language_server_setup.md) |
| Upgrade the pinned OMP version | [OMP Upgrade Runbook](omp_upgrade_runbook.md) |
| Read run reports, dashboards and status JSON | [Observability](../specs/observability.md), [CLI](../specs/cli.md) |

## Examples And Experiments

| You want to | Read |
| --- | --- |
| Runnable `.orc` examples and launch commands | [Workflow Index](../workflows/README.md) |
| `.orc` workflows compared with a single agent call | [Experiment materials](../experiments/orc_vs_single_call/README.md) |
| The same contracts written in ORC and in Python | [ORC/Python showcase](../experiments/orc_vs_python_showcase/README.md) |
| A paired sequential search in ORC and Python | [MLEvolve-inspired pair](../experiments/mlevolve_pair/README.md) |

## Writing Docs

| You want to | Read |
| --- | --- |
| Rules for maintained docs | [Documentation Conventions](documentation_conventions.md) |
| A design doc skeleton | [Design Template](templates/design_template.md) |
| The gap-design skeleton the design-gap drain prompts fill in | [Design Gap Template](templates/design_gap_implementation_architecture_template.md) |

## Common Confusions

| Confusion | Correct model | Reference |
| --- | --- | --- |
| "Any docs page is authoritative." | `specs/` are normative; `docs/` explain. | [Master Spec](../specs/index.md) |
| "Reports, pointer files and debug YAML can decide workflow meaning." | Structured state, artifact values and contracts decide routing and resume. Reports, pointer files, rendered plans and `expanded.debug.yaml` are views. | [Design Principles](design/workflow_language_design_principles.md) |
| "JSON printed to stdout counts as a structured result." | Results travel only as validated bundles at runtime-bound output locations; wrong-path writes fail closed. stdout and stderr are observability, never a result channel. | [Step IO](../specs/io.md), [Runtime Migration Foundation](design/workflow_lisp_runtime_migration_foundation.md) |
| "Inline Python or shell is either banned or fine." | Command steps are for external tools and certified adapters. Workflow semantics hidden in inline glue, ad hoc JSON rewrites or report parsing belong in typed procedures, adapters or runtime-native effects. | [Command Adapter Contract](design/workflow_command_adapter_contract.md) |
| "The orchestrator moves queue items." | Queue item movement is authored by the workflow; the runtime does not move task files. | [Queues and Wait-For](../specs/queue.md) |
| "Typed 2.36 local hooks are native closures." | Typed 2.36 hooks are compile-time composition. Native 3.0 closures are runtime values. Neither profile's features carry over to the other. | [Versioning](../specs/versioning.md) |

## History

These are records of how the project got here. They do not describe current
behavior or select work; use the routes above for that.

- [`plans/`](plans/): implementation plans, roadmaps and work instructions.
- [`reports/`](reports/): experiment results, audits and decision briefs.
- [`superpowers/`](superpowers/): earlier design and plan drafts.
- [`backlog/`](backlog/): backlog items and generated queues.
- [Historical YAML drafting guide](workflow_drafting_guide.md): reference for
  translating retired YAML/YML workflows into `.orc`. YAML cannot be run or
  resumed.
- [YAML workflow estate triage](workflow_yaml_estate_triage.md) and
  [YAML-to-Workflow-Lisp gap list](workflow_yaml_orc_gap_list.md): records of
  the YAML retirement.
- YAML-era spec examples: [patterns](../specs/examples/patterns.md),
  [file dependencies](../specs/examples/file-dependencies.md),
  [injection modes](../specs/examples/injection-modes.md),
  [multi-agent inbox](../specs/examples/multi-agent-inbox.md) and
  [debugging](../specs/examples/debugging.md).
- [YAML semantics slide deck](slides/README.md): teaching deck for the retired
  YAML frontend.
- [Dynamic-core evaluation spike](../experiments/dynamic_core_evaluation/README.md):
  an earlier experiment that preceded the native 3.0 runtime.
- Git history holds everything else.
