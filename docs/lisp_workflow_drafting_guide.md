# Workflow Lisp Drafting Guide

Status: informative current-authoring guide
Authored workflow frontend: Workflow Lisp / `.orc`
Normative contracts: `specs/`
Primary audience: workflow authors, workflow-library maintainers, and
prompt/workflow reviewers
Compatibility audience: maintainers inspecting generated Core mappings,
historical migration fixtures, and persisted legacy state

This guide explains how to author deterministic workflows using the Workflow
Lisp frontend. It is about authoring choices, not runtime implementation.
Normative DSL and runtime contracts live under `specs/`.

Before choosing a review, revise, or select pattern, use the
[Workflow Lisp Library Reference](lisp_library_reference.md) for the task chooser,
complete examples and operating limits, and read
[Designing `.orc` Workflows That Beat A Single Call](orc_workflow_design_lessons.md)
for the design tradeoffs.

Current contract reading path:

- [Frontend baseline](design/workflow_lisp_frontend_specification.md): language,
  typed modules/imports, static procedures, proof and effect rules.
- [Evaluated execution](design/workflow_lisp_evaluated_execution.md) and
  [runtime lifecycle](runtime_execution_lifecycle.md): checked program, memo,
  public compile/run/resume/invalidation and read-only views.
- [Capability matrix](capability_status_matrix.md) and [Section 2A](#2a-program-shapes-what-runs-today):
  admitted shapes, bounded qualification and explicit refusals.
- [Prompt calculus](design/workflow_lisp_prompt_calculus.md),
  [typed result/delivery contract](design/provider_result_delivery.md),
  [parametric types](design/workflow_lisp_parametric_type_system.md) and
  [local procedures](design/workflow_lisp_let_proc_local_proc_refs.md): focused authoring rules.
- [Command adapter contract](design/workflow_command_adapter_contract.md):
  explicit external-tool/closure boundaries and validation.
- [Language server setup](workflow_lisp_language_server_setup.md): supported
  editor use; evaluated F2 remains **OPEN_NOT_WAIVED**.

Use this guide for authoring judgment. Use
[Capability Status Matrix](capability_status_matrix.md) for current
availability and copy-safety status. Use the component-contract docs for
current behavior. Future/deferred surfaces require their focused accepted
design and selection gate; the historical unified proposal selects no work.
Use `specs/` for normative runtime and DSL behavior.

The Design Delta family (`workflows/library/lisp_frontend_design_delta/`) is
deprecated, apart from its reusable library procedures. Do not start new work
from it, and read
[Workflow Lisp Runtime-Native Drain Authoring](design/workflow_lisp_runtime_native_drain_authoring.md)
as a historical checklist for that family's shape. Start current authoring from
[`improve_experiment_proposal.orc`](../workflows/examples/improve_experiment_proposal.orc)
at 2.39 for a `std/improve` review loop, or the
[complete 2.35 lifecycle recipe](#a-complete-235-recipe-compile-run-resume-report-invalidate).
[`best_of_n.orc`](../experiments/orc_vs_single_call/workflows/best_of_n.orc) and
[`reviewed_change.orc`](../experiments/orc_vs_single_call/workflows/reviewed_change.orc)
now target 2.35. Their [experiment recipe](../experiments/orc_vs_single_call/README.md)
provides the manifests and prerequisites for serial candidate selection and
the review/revise loop; historical comparison results keep their original scope.

Use the retired [Workflow Drafting Guide](workflow_drafting_guide.md) only to
translate or audit historical YAML/YML definitions and evidence. It is not an
authoring or runtime route.

Fresh workflow execution is ORC-only. `run` accepts a path whose suffix
compares case-insensitively as `.orc` and rejects every other source with
`.orc required` before creating state. The production YAML parser and PyYAML
runtime dependency are removed. Persisted legacy runs retain state-only
report/dashboard compatibility without source parsing. Old workflow profiles
refuse `resume`, force-restart and invalidation with
`workflow_execution_profile_retired` before changing retained run contents.
Native `prompt resume` remains separate. The
[executable support boundary](../specs/cli.md#executable-support-boundary)
owns the exact refusal and retained-release limits.

If new work needs a form that the current `.orc` frontend does not support, do
not create a lower-level or YAML workflow as a workaround. Record a capability
gap so the missing surface can be designed and implemented deliberately.

For historical migration review, preserve the captured YAML baseline and its
computed parity evidence. Do not attempt to rerun the retired source or infer
parity merely because an `.orc` version compiles.

## Editor Diagnostics And Navigation

Evaluated targets have source/helper selection parity only; evaluated LSP
snapshot/navigation and terminal diagnostic parity remain unqualified. The
features below describe the established full-Stage-3 editor lane, not a promise
of evaluated-run editor support. See the
[language-server owner](design/workflow_lisp_language_server.md) and
[capability matrix](capability_status_matrix.md) for exact scope.

The optional Workflow Lisp language server v1 is implemented for practical
`.orc` authoring feedback. Install the `[lsp]` extra, launch
`python -m orchestrator.lsp`, and configure exactly one canonical workspace
root as described in the
[setup guide](workflow_lisp_language_server_setup.md).

The server compiles only clean disk-equal opens and saves through the
production full-Stage-3 path. It provides compiler diagnostics, exact direct
procedure/workflow call definition, exact authored prompt-application-head
definition, and exact final unexpanded direct-retained `proc-ref` name
definition in authored non-generated, non-specialized owners. It also provides
document symbols for the ten directly authored module, procedure, workflow,
enum, path, record, union, schema, resource, and transition kinds. Completion
preserves separate
procedure/workflow/form namespaces and renders callable parameters, returns,
and procedure contracts from compiler signatures. At 2.39, detail separates
optional authored restrictions from inferred effects and marks unresolved
generic hooks incomplete. Save the buffer
before expecting refreshed results. Definition and document symbols remain
unavailable for dirty, pending, failed, invalidated, or configuration-stale
documents, and configuration or root drift requires a server restart. L0
additionally provides content-keyed
reuse of pure-projection exports, one-probe saves with reverse-dependency
invalidation, structured compiler-initialization failures, and visible ordered
note/expansion roles. The server writes no workspace files.

Navigation is authored-to-authored and exact-token only. Macro heads remain
null shape-wide, and macro-consumed, erased, expanded, generated-owner, or
specialized-owner proc-refs remain null. Existing direct-call behavior is
unchanged and WCC/generated calls stay excluded. Do not infer broader support
from a same-spelled token: the server never parses or resolves source text to
fill a missing compiler join.

Implemented L2 adds a recovery-only, **process-frozen form registry**. A valid
dirty, current-pending, language-failed, or server-failed open entry receives
those form heads with `isIncomplete=true` and **no stale callable** names or
signatures.
Configuration-stale, unavailable, closed, unassociated, malformed, and
index-failed entries remain empty, while definition and document symbols
remain available only from current success. This does not validate a form at
the cursor or compile the unsaved buffer; treat the incomplete list as
syntax-head recovery help and save before relying on semantic navigation.
Unsaved-buffer analysis, multi-diagnostic recovery, hover, broader
incrementality, type-directed completion, and the other P1–P5 prerequisites
remain deferred rather than approximated.

Before copying a checked-in `.orc` example or fixture, check
`docs/workflow_lisp_route_readiness_registry.json`. Registry labels provide
the copy-safety and route/readiness classification: `wcc_default` records
historical WCC/schema-2 evidence, `legacy_schema1_compat` is historical compatibility evidence,
`evaluated_execution` is checked closed-program evidence for a registered
evaluated entry target, `migration_candidate` is not a promotion claim, and
`stale_needs_update` is not current guidance. Old flat entries are now `historical_negative` with no executable readiness
or flat metadata; preserved route labels do not permit launch. Evaluated evidence uses the
public CLI and checked closed artifact, with both flat lowering fields unset.
The registry remains v1. Its label does not select runtime behavior or certify
editor support; `copy_safety` and direct owner evidence still govern guidance. Leaf compile/runtime
labels are useful progress evidence, but they are not promotable
workflow-family evidence.

Migration promotion checklist:

- Treat compile, typecheck, lower, shared validation, and dry-run as necessary
  evidence, not as promotion approval.
- Require output contract parity, terminal-state parity, artifact parity, and
  resume/reuse parity against the characterized historical baseline.
- Treat `non_regressive` values in preserved reports as frozen historical
  evidence; do not edit or regenerate them.
- Keep structured bundles, typed artifacts, runtime state, and variant proof as
  authority. Do not route migration behavior through reports, stdout, pointer
  files, or `expanded.debug.yaml`.
- Do not expose compiler-generated write roots or result-bundle paths as public
  entrypoint inputs. Debug projections may show generated bindings only with
  origin metadata.
- Do not treat `output_bundle` fields as variant-specific proof. Use
  `variant_output`, `match` proof, `requires_variant`, or a compiler-owned
  validator/projection that establishes equivalent proof.
- Keep review decisions and terminal loop results separate. `REVISE` must run a
  revise/fix path or exhaust explicitly; it is not completion.
- Validate schema-backed JSON, such as carried review findings, before it is
  published to loop state and again before it is consumed after resume.
- Evidence paths are produced by workflow, checks, or materializer steps.
  Review providers inspect and judge evidence, but they should not author
  evidence identity. Do not put consumed evidence paths such as `checks_report`
  in provider output contracts unless the provider actually produces that
  artifact; carry them from state or inputs when terminal results need them.
- When a provider already owns a validated structured-output bundle path, use
  `provider-bundle-path` to expose a typed relpath view such as
  `selection_bundle_path`; do not add a helper script or pointer file that only
  echoes the same bundle identity.

The manifest-driven parity generator is retired. Preserved per-target JSON and
Markdown reports remain immutable historical evidence, not current route
authority. For current claims, validate
`docs/workflow_lisp_route_readiness_registry.json` and run the direct owner
compile/runtime/resume tests cited by the selected registry entry.

Choose new examples from the workflow
catalog's [copy-safety table](../workflows/README.md#which-example-should-i-copy).
The earlier examples that targeted DSL 2.14 or 2.23, such as
`review_revise_design_docs.orc` and `kiss_backlog_item.orc`, are now test
fixtures under `tests/fixtures/workflow_lisp/retired_examples/`; release
`v0.1.0` runs them.

## Core Rule

Author narrow public workflow boundaries over typed procedures and structured
results. Workflows own public run/resume/invocation/publication identity;
procedures are the normal internal reuse unit.

Do not author brittle gates, pointer plumbing, report parsers, candidate-path
selectors, or manual state-file choreography.

Good high-level workflow code composes typed provider/command results, pure
helpers and bounded control. See [Section 13.7](#137-improve) for the exercised
review/revise composition. Low-level state-file choreography, report parsing
and pointer plumbing should not dominate authored Lisp.

## Runtime-Native Authoring Direction

For new high-level Workflow Lisp, pass typed domain values by default and let
lowering/runtime own execution mechanics.

Preferred authoring shape:

- provider calls render supported scalar, record, relpath, exact
  `Value`, and recursively renderer-admitted `List[T]` values from `:inputs`
  at the prompt consumer seam; other composite shapes require an implemented
  checked route;
- private runtime context, generated paths, checkpoint identity, and write roots
  are hidden from public entrypoints and ordinary user-facing calls;
- deterministic local reshaping uses pure typed projection instead of Python;
- durable resource changes require an admitted, reviewed effect;
  `resource-transition` remains unavailable at evaluated targets;
- prompt text, public summaries, observability, and compatibility files are
  renderings at consumer seams; and
- body-level `materialize-view` remains unavailable at evaluated targets.

For example, the high-level call should usually be:

```lisp
(run-work-item item)
```

not:

```lisp
(run-work-item item item-ctx state-root artifact-root summary-path)
```

The checked builder may supply an admitted private helper context without
exposing runtime bookkeeping as a public authored input. Its typed ownership
and exact source provenance remain inspectable; historical flat IR projection
is not part of current execution.

## Prompt Externs

Prompt externs are compile-time build bindings, not workflow-boundary inputs.
They tell the Workflow Lisp frontend which shared provider prompt source field
to emit when a workflow refers to a named prompt extern.

- String shorthand means `asset_file`.
- Use `asset_file` for reusable library prompts and other workflow-source-owned
  prompt assets.
- Use explicit `input_file` object bindings for workspace-owned or
  runtime-generated prompt material.
- Runtime prompt existence checks, path-root enforcement, and prompt-read
  diagnostics still belong to the shared provider/runtime layer.

Examples:

```json
{
  "prompts.implementation.execute": "prompts/implementation/execute.md",
  "prompts.project.review": {
    "input_file": "prompts/workspace/project-review.md"
  }
}
```

## 1. Mental Model

Think in five layers.

| Layer | Author concern | Typical `.orc` forms | Runtime/lowering concern |
| --- | --- | --- | --- |
| Types and contracts | What values exist? | `defpath`, `defenum`, `defrecord`, `defunion`, `defschema` | Contracts, path safety, artifact shapes |
| Procedures and workflows | Which boundary is public, and what behavior is internally reusable? | `defworkflow`, `defproc`, `defun`, `call`, `let*` | Public run/resume identity, graph structure, procedure lowering, workflow calls |
| Structured results | What did a provider or command produce? | `provider-result`, `command-result`, `match` | Output validation, prompt contract, variant proof |
| Effects | What work occurs? | Admitted `provider-result`, `command-result`, calls and path-mode `run-ref` | Effect identity, validated results, memo commits |
| Runtime substrate | How is it executed? | Usually not hand-authored | Core AST, semantic IR, snapshots, bundles, artifacts |

For evaluated targets 2.35–2.39, within their admitted feature scope,
the compiler elaborates and checks `.orc` source into a
closed program; the evaluator computes its values and memoizes its effects.
The checked `closed_program.json` is execution authority. The memo is effect
result authority, and `state.json` is a derived view. The
[evaluated-execution design](design/workflow_lisp_evaluated_execution.md)
owns the full model.

Ask these first:

- What typed input does this workflow receive?
- What typed result does it return?
- Does this need durable public run/resume/invocation/publication identity, or
  is it an internal procedure or pure helper?
- Which provider, command, filesystem, state, or ledger effects occur?
- Which result is fixed-shape state and which result is an outcome union?
- Where should variant proof be established?
- Which state transition is being performed?

If the answer starts with "I need a step that checks whether a file exists,"
step back. You probably need a typed result, a transition, or a certified
adapter.

## 2. Availability Model

Use the [Capability Status Matrix](capability_status_matrix.md) to distinguish
implemented, library-provided, designed, future and legacy surfaces. Compiler
acceptance at an older target does not establish evaluated runtime admission.
Use 2.39 for inference-default [procedure contracts](#procedure-contracts-at-target-239).
The explicitly versioned 2.35/2.36 recipes retain their original procedure rules;
2.38 introduces bounded [Agent Sessions](#agent-sessions-target-238) and
[command-only confined children](#confined-workflow-children-target-238-command-only).
[Section 2A](#2a-program-shapes-what-runs-today) owns the current shape limits.

The shared authoring surface includes declarations (`defenum`, `defpath`,
`defrecord`, `defunion`, `defschema`), modules/imports/exports, `defworkflow`,
`defproc`, `defun`, bounded deterministic macros, `let*`, strict-`Bool` `if`
and `cond`, `match`, `loop/recur`, the closed pure operator and list surfaces,
`call`, `provider-result`, `command-result`, and fully applied `defprompt`
fragments. Prompt output slots may own one required UTF-8 file alongside the
structured result. See the effect admission limits in Section 2A before using
any library helper.

At target 2.38 the surface also includes `agent`, which allocates a run-local
`Agent`, and `provider-result` on an `Agent`, which takes one turn in that
agent's native conversation. Both compile and run; acceptance comparison
remains pending. See
[Agent sessions](#agent-sessions-target-238).

Native transportable results need no one-field record wrapper: use the actual
scalar, enum, path, optional, list, map, record, union or exact opaque `Value`
contract. Optional typed guidance uses
`(result T :description ... :format-hint ... :example ...)`; examples are
typed pure constants and safe path examples need not exist at compile time.
Exact `Value` permits description/format guidance, but not an example.

Procedure composition remains compile-time-only: `ProcRef[...]`,
`(proc-ref ...)`, `bind-proc`, and `WorkflowRef[...]` are specialized before
execution. They cannot cross transport seams, become provider-produced values,
or survive in runtime state. Generic `defproc` is supported; generic
`defworkflow`, dynamic runtime dispatch and runtime closures remain outside
current authoring.

At target 2.35, bounded V1 `let-proc` has one typed local procedure and
explicit identifier captures. At 2.36,
[W3](design/workflow_lisp_write_once.md#63-language-changes-to-let-proc)
adds several bindings, inferred lexical captures and incomplete signatures
inferred from exactly one authored direct consumer site. Complete signatures
retain reuse. Nested local definitions and recursion remain excluded. See
[Section 13.7](#137-improve) for the maintained proposal recipe.

The [macro contract](design/workflow_lisp_macro_surface_contract.md),
[parametric type contract](design/workflow_lisp_parametric_type_system.md), and
[local-binding contract](design/workflow_lisp_let_proc_local_proc_refs.md)
own their detailed language limits. Historical YAML migration records preserve
captured baselines and parity evidence; they do not select a current runtime
route.

## 2A. Program Shapes: What Runs Today

Use target **2.39** for the [current procedure authoring contract](#procedure-contracts-at-target-239).
The **2.35/2.36** recipes below remain valid at their stated targets; **2.38**
introduces bounded [Agent Sessions](#agent-sessions-target-238) and
[command-only confined children](#confined-workflow-children-target-238-command-only). These select evaluated
execution; 2.36 adds the W3 local-hook and graph-selected `std/improve` API
shown in [Section 13.7](#137-improve). Every source dependency must declare
target 2.35 or newer, including dependencies supplied as typed programs or
compiled bundles. Pre-2.35 entry execution is retired; source imports, REPL
loads and LSP analysis below that floor also refuse. Historical source is
preserved as evidence; no header or run conversion is performed. The
[Phase 5 plan](plans/2026-10-07-evaluated-execution-phase-5-plan.md)
owns bounded 2.37 parallel support and its remaining qualification; it is not
general copy-safe guidance. Target 2.38 separately admits the bounded
[Agent recipe](#agent-sessions-target-238) and
[command-only confined children](#confined-workflow-children-target-238-command-only);
the latter does not admit providers or Agent operations inside the child.

Values are evaluated in lexical scope; they are not stored as generated steps.
Effects execute in source order and are recorded in `memo.jsonl`. A committed
effect is reused on resume. The public shape evidence lives in
[`tests/test_workflow_evaluated_totality.py`](../tests/test_workflow_evaluated_totality.py)
and [`tests/test_workflow_evaluated_programs.py`](../tests/test_workflow_evaluated_programs.py),
not in the historical flat-route workaround catalogue.

| Shape | Current guidance |
| --- | --- |
| Branches, nested loops, and helpers in loops | Compose admitted forms directly; selected branches are lazy and lexical bindings retain their scope. |
| Records, unions, lists, and repeated pure bindings | Keep typed native values; no flattening or value-as-step wrapper is needed to reach a command. |
| Effectful arguments and conditions | Admitted effects run in structural evaluation order, once per activation; boolean operators short-circuit. |
| Pure contexts | Keep `:on-exhausted` and pure `list/map` bodies effect-free; union reads still require proof. |
| Serial `list/map-effect` | Supply an explicit traversal bound and one admitted effect per body; parallel map requires the bounded 2.37 extension owned by the Phase 5 plan above and is not general copy-safe guidance. |
| Decimal arithmetic | Use the closed numeric operator surface in Section 9A; mixed numeric types and non-finite results fail closed. |
| Path-mode `run-ref` | Admitted directly or through calls in effect-admitting branches, loops, budgets, seeds, `match` subjects and serial effect maps; retain pure-context restrictions. |

The admitted effects are commands (external tools and certified adapters),
portable composed providers, procedure/workflow calls and path-mode run
references. Portable providers admit extern `asset_file`/`input_file` prompts
and supported `defprompt` slots, including `:path :out`, but no session,
context binding/capture, managed job or secrets.

Selected `request-input`, `trial`, phased provider delivery,
`run-provider-phase`, `produce-one-of`, `resume-or-start`,
`finalize-selected-item`, `resource-transition`, `materialize-view`, live
provider supervision/peer groups and bundle-mode `run-ref` are unavailable
at both evaluated targets and refuse at build with `closed_program_gap`.
Provider session artifacts and materialization attempts are also excluded.
Recursive calls and runtime closures remain excluded. Frontend/typechecking
may reject a source before this admission check; retargeting an old workflow
is not an acceptance guarantee. Exact scope is owned by
[evaluated execution §1.1](design/workflow_lisp_evaluated_execution.md#11-the-first-release)
and the [located-gap tests](../tests/test_workflow_lisp_closed_program_effects.py).

Public `compile` writes `closed_program.json` and `manifest.json`; `run`
evaluates that checked program, `resume` rebuilds it from the recorded recipe
and reuses committed effects, and `invalidate RUN_ID IDENTITY` cancels a
commit and every later commit for the next resume. Reports, dashboard and
monitor consume derived views. Exact persistence, IO and command contracts
live in [State](../specs/state.md#evaluated-execution-persistence-profile-target-235),
[Step IO](../specs/io.md#evaluated-command-and-provider-io-target-235),
[CLI](../specs/cli.md#evaluated-execution-target-235) and
[Versioning](../specs/versioning.md#version-gating-summary).

Every supplied command manifest row, even unused, and every used injected
binding needs an explicit `closure` array, including `[]` when nothing is
declared. Compilation records logical paths without reading their contents;
execution binds the declared bytes and pins the interpreter for the run.
This declaration is not a sandbox. See the
[command closure contract](design/workflow_command_adapter_contract.md#command-closure-declaration)
and the complete lifecycle below.

### A complete 2.35 recipe: compile, run, resume, report, invalidate

Everything below is the public fixture of
[`tests/test_workflow_evaluated_invalidate_smoke.py`](../tests/test_workflow_evaluated_invalidate_smoke.py)
(`test_public_compile_run_resume_invalidate_resume_keeps_provider_command_evidence`),
as it ran under the Task 16A inventory: the files it writes, the commands it
issues and what it asserts. `$T` is the workspace, the current directory of
every command. Run the test to reproduce it.

**Source** (`$T/main.orc`, entry `main::run`): one command whose result feeds
one provider, with a typed `String` input.

```lisp
(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule main) (export run)
  (defrecord Result (ok Bool))
  (defworkflow run ((message String)) -> Result
    (let* ((built (command-result build :argv ("python" "command.py" message) :returns String))
           (review (provider-result providers.review :prompt prompts.base
             :inputs (message built) :model "chosen-model" :effort "low" :returns Result)))
      review)))
```

**Command** (`$T/command.py`): appends its argv to `command-requests.jsonl`
and writes its result, a JSON string, to the file named by
`ORCHESTRATOR_OUTPUT_BUNDLE_PATH` (workspace-relative for a command).

```python
import json
import os
import sys
from pathlib import Path

with Path("command-requests.jsonl").open("a", encoding="utf-8") as stream:
    stream.write(json.dumps({"argv": sys.argv[1:]}, ensure_ascii=False) + "\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(
    json.dumps("command artifact ñ", ensure_ascii=False), encoding="utf-8"
)
```

**Manifests**: the command boundary with its closure, the provider extern
and the prompt extern.

```json
// $T/commands.json
{"build": {"stable_command": ["python", "command.py"], "closure": ["command.py"]}}
// $T/providers.json
{"providers.review": "codex"}
// $T/prompts.json
{"prompts.base": {"asset_file": "prompt.md"}}
```

`$T/prompt.md` holds `ASSET SOURCE`. The provider is a stand-in: `_fixture()`
in [`tests/test_workflow_evaluated_providers.py`](../tests/test_workflow_evaluated_providers.py)
writes `$T/bin/codex` (its `SHIM` text behind a `#!<python>` line, mode
0700). It reads the prompt on stdin, appends the request to `requests.jsonl`
and writes `{"ok":true,"extra":7}` to the absolute
`ORCHESTRATOR_OUTPUT_BUNDLE_PATH` a 2.35 provider receives. The runtime
validates that file against `Result` and commits `{"ok": true}`; `extra` is
not part of the contract. `:model "chosen-model"` is the fixture's
placeholder; a real provider needs a real model alias, and Task 14D ran the
three maintained programs live with their own manifests, not with this one.
The environment of every command below is the fixture's: `PATH=$T/bin:$PATH`,
`PYTHONPATH=<repository root>` (this checkout's `orchestrator` must be the
one `python -m orchestrator` imports; another installed checkout refuses
target 2.35), `PYTHONDONTWRITEBYTECODE=1`, `PROVIDER_SHIM_MODE=success`,
`PROVIDER_SHIM_RESULT='{"ok":true,"extra":7}'`; `$T` is the current directory.

**1. Compile.** Writes `$T/.orchestrate/build/<key>/closed_program.json` and
`manifest.json`; stdout is JSON whose `artifact_paths.closed_program` names
the artifact. Exit 0.

```bash
python -B -m orchestrator compile $T/main.orc --entry-workflow main::run \
  --source-root $T --provider-externs-file $T/providers.json \
  --prompt-externs-file $T/prompts.json --command-boundaries-file $T/commands.json
```

**2. Run**, with the typed input. Exit 0. The run root
`$T/.orchestrate/runs/<run_id>/` holds `run.json` (header with the rebuild
recipe), `closed_program.json`, `memo.jsonl`, `state.json` (derived view),
`run.lock` and `effects/<sha256 of the identity>/attempt-1/` for each effect
(`result.json`, `stdout.txt`, `stderr.txt`; `prompt.txt` for the provider).
The last memo record is
`{"outcome":"completed","record":"terminal","value":{"ok":true}}` (keys
sorted, compact); `state.json` has that value under `workflow_outputs`. `command-requests.jsonl`
has one line, `{"argv": ["typed input"]}`; `requests.jsonl` has one provider
request whose argv names `chosen-model` and `model_reasoning_effort=low`. The
build directory is unchanged by the run.

```bash
python -B -m orchestrator run $T/main.orc --entry-workflow main::run \
  --source-root $T --provider-externs-file $T/providers.json \
  --prompt-externs-file $T/prompts.json --command-boundaries-file $T/commands.json \
  --input 'message=typed input'
```

`--dry-run` on the same arguments builds and binds the inputs, exits 0 and
creates no run root; an invalid input exits 2 the same way
([`tests/test_workflow_evaluated_cli.py`](../tests/test_workflow_evaluated_cli.py),
`python -m orchestrator run $T/evaluated/inputs.orc --dry-run --input score=0.75`
on its pure fixture).

**3. Resume a completed run.** Exit 0, and nothing under `.orchestrate`
changes: no new request, no new attempt, same `memo.jsonl` bytes.

```bash
python -B -m orchestrator resume <run_id>
```

**Stop and resume.** A run killed inside its command attempt resumes from
the memo: the interrupted effect gets `attempt-2`, and the pinned interpreter
is launched even after `PATH` changed (its changed bytes are logged as
`interpreter_changed`). The fixture is
[`tests/test_workflow_evaluated_resume_replay_boundary.py`](../tests/test_workflow_evaluated_resume_replay_boundary.py)
(`test_public_pending_retry_uses_pinned_path_after_path_and_bytes_change`):
`run $T/pinned.orc --command-boundaries-file $T/commands.json`, killed by the
test, then `resume <run_id>`, exit 0.

**4. Report.** Reads header, program and memo and reconstructs the view in
memory when `state.json` is missing, stale or unparseable; it writes nothing.
Exit 0 ([`tests/test_workflow_evaluated_readers.py`](../tests/test_workflow_evaluated_readers.py)).

```bash
python -m orchestrator report --run-id <run_id> --runs-root $T/.orchestrate/runs --format json
```

**5. Invalidate the command**, by its canonical identity, one shell argument.
Exit 0; stdout is the appended row,
`{"from_commit": <byte offset of the command's commit>, "record": "invalidated", "time": ...}`
(the memo stores it compact, keys sorted). The memo grows by that one row; `attempt-1` files, `run.json`,
`closed_program.json` and the build directory are unchanged. Repeating the
same command exits 2 with `invalidate_not_committed` and changes nothing.

```bash
python -B -m orchestrator invalidate <run_id> "workflow:main::run / built"
```

**6. Resume after invalidation.** Exit 0. The command and the provider run
once more, as `attempt-2` of the same identities (`command-requests.jsonl` and
`requests.jsonl` each gain one line); the terminal is `completed` with
`{"ok": true}` again; `attempt-1` evidence and the program digest are
unchanged.

```bash
python -B -m orchestrator resume <run_id>
```

What the recipe does not show: context capture, trials, phased providers
and the other classes of
[§1.1](design/workflow_lisp_evaluated_execution.md#11-the-first-release)
refuse at build with `closed_program_gap` (a parallel `list/map-effect` below
target 2.37 refuses earlier, in the frontend, with
`list_traversal_target_dsl_unsupported`); external kills at every window of
every effect of the three maintained programs are owned by
[`tests/test_workflow_evaluated_recovery.py`](../tests/test_workflow_evaluated_recovery.py)
(Phase 3 Task 15, integrated).

### Print a value during a run

At target 2.35, `(print value)` writes the value's compact JSON line to the
run's stdout and returns the value, so a `let*` binding such as
`(shown (print feedback.findings))` shows a committed result while the run goes
on. `print` is an operator, not an effect: it has no memo record, `resume`
prints again what it re-evaluates, and readers that replay the program (views,
`report`, the REPL) evaluate it as the identity.

### Inspect a run with the Workflow Lisp REPL

For admitted evaluated targets 2.35–2.39, `orchestrator repl` lets you discover a loaded
module's declarations, inspect their contracts/source, ask for expression types,
and inspect captured run bindings. From the repository root, use the maintained
[`plan_review_execute.orc`](../workflows/examples/plan_review_execute.orc) and
its required [provider extern manifest](../workflows/examples/inputs/plan_review_execute/providers.json).
Loading and the first queries below
compile the module and publish its ordinary build bundle; they do not run the
providers. No prompt extern manifest is required for this module:

```bash
python -m orchestrator repl workflows/examples/plan_review_execute.orc \
  --provider-externs-file workflows/examples/inputs/plan_review_execute/providers.json
```

Inside the session, before running or attaching anything:

```text
:browse
:info Plan
:info revise-plan
:source revise-plan
:type (list/length (list "first step" "second step"))
```

`:browse` lists module/entry/target, imports and available names. `:info Plan`
shows `steps: List[String]`; `:info revise-plan` shows the text slot `task`,
value slots `steps` and `findings`, their refinements/output roles and return
type `Plan`. `:source revise-plan` prints the complete authored prompt form
with its loaded snapshot revision. The type query prints `type: Int` and
`effects: ()` without evaluating the expression.

Coverage is named types, functions, procedures, workflows, prompts and externs.
Names use the compiler's accepted import/alias spellings; distinct namespace
matches are labelled, and aliases share one declaration. Macros, schemas,
resources, transitions, operator documentation, applied generic type syntax as
a name, and generated local definitions/specializations are excluded. Extern
inspection does not read external prompt files or display provider payloads.

To inspect an existing run, replace `RUN_ID` below with its actual run ID:

```text
:attach RUN_ID
:bindings
:type revised.steps
:type feedback.findings
feedback.findings
(list/length revised.steps)
(list/empty? feedback.findings)
:result
:where revised
:quit
```

For a completed run of this module, `revised.steps` and `feedback.findings` have
type `List[String]`. `:bindings`, ordinary expressions and `:result` inspect
the checked captured frame; `:info` and `:source` continue to query declarations.
Values print as compact sorted JSON on one line and `: <type>` on the next.
`:result` returns the entry result; a stopped/failed run instead reports
`repl_no_result`. `:where revised` prints the path of the `result.json` that
binding was read from (its directory also holds `prompt.txt`, `stdout.txt`
and `stderr.txt`); `:where` alone does the same for the entry result, and a
computed binding reports `repl_no_result_file`. REPL/runtime errors print `[code] detail`; frontend errors
retain localized compiler diagnostics with `kind`/`form` context. Expected
session errors leave the session available for the next line. `list/empty?`
tests list emptiness; `=` / `!=` keep the ordinary supported-scalar/same-enum
contract, without deep list equality. See
[frontend §10.2](design/workflow_lisp_frontend_specification.md#102-closed-pure-expression-surface).

You can also add `--run-id RUN_ID` to the launch command; add `--state-dir DIR` for a
custom run root. Without a loaded workflow, `repl --run-id RUN_ID` rebuilds
its persisted recipe in memory and requires the same program digest. Its source
is labelled `reconstructed module source`: it may differ in comments/formatting
from the historical run. Explicit loads say `loaded snapshot`; editing or
deleting files after loading cannot change that snapshot, and a failed load
keeps the previous one. No historical source archive is supplied.

No run files change during attachment or inspection. `:type` also accepts
effectful expressions as static analysis, preserving ordinary frontend errors
without lowering or evaluation. Entered effectful expressions,
including transitive procedure effects, refuse `repl_effect_refused`; only
explicit `:run` executes effects. To create a new run in a workspace intended
for execution, use `:run --input task="Inspect this workspace and summarize the planned changes"`;
this invokes the real providers selected by the manifest. Input is one expression per line, with no
session resume, new definitions, editing or multiline support.

The [CLI contract](../specs/cli.md#workflow-lisp-repl-targets-235-and-236)
owns flags and diagnostics; the [REPL design](design/workflow_lisp_repl.md)
owns the capture/expression boundary, and the
[introspection design](design/workflow_lisp_repl_introspection.md) owns module
queries and source provenance. Behavioral public integration coverage is
[`tests/test_workflow_evaluated_repl.py`](../tests/test_workflow_evaluated_repl.py)
and [`tests/test_workflow_evaluated_repl_introspection.py`](../tests/test_workflow_evaluated_repl_introspection.py);
provider stand-ins in tests prove integration rather than live provider quality.

## 3. Semantic Authority Rules

These rules apply across `.orc`, generated Core AST, the JSON-rendered
`expanded.debug.yaml` view, and runtime IR.

For evaluated execution, the checked closed program is execution authority and
the memo owns committed effect results. State, runtime plans, source maps,
summaries and reports are views. Semantic/Executable IR retain their component
contracts for older compiler routes; they do not replace evaluated authority.

### 3.1 Structured State Is Authority

Structured records, unions, bundles, and typed artifacts are semantic authority.

Reports, rendered plans, summaries, the JSON-rendered
`expanded.debug.yaml`, logs, and pointer files are views or materialized
representations.

Bad:

```lisp
(command-result extract-blocker
  :argv ("python" "scripts/extract_line.py" "--prefix" "Blocker Class:")
  :returns BlockerClass)
```

Better:

```lisp
(defunion ImplementationAttempt
  (COMPLETED
    (execution-report Path.execution-report))
  (BLOCKED
    (progress-report Path.progress-report)
    (blocker-class BlockerClass)
    (blocker-reason String)))

(provider-result providers.execute
  :prompt prompts.implementation.execute
  :inputs (inputs.design inputs.plan)
  :returns ImplementationAttempt)
```

The provider may write a markdown report, but the markdown report is not parsed
later to recover semantic state.

### 3.2 Reports Are Views

Use reports for human review, provenance, explanation, and diagnostics.

Do not use reports as the only source of:

- review decision;
- blocker class;
- phase status;
- selected item path;
- drain status;
- resource transition result.

If a report contains those values, the same values must also exist in structured
state.

### 3.3 Artifact Values Are Authority

A path artifact value is the semantic value. A pointer file may contain or
represent that value, but the pointer file path is not the value unless the
contract explicitly says so.

Bad:

```text
execution-report := "state/execution_report_path.txt"
```

Better:

```text
execution-report := implementation.execution-report
```

The runtime may materialize `state/execution_report_path.txt` for a legacy
command or prompt, but that file is a representation.

### 3.4 Freshness Requires Durable Evidence

Do not use mtime-only freshness for routing or semantic selection.

Use snapshot/hash evidence through the lowered runtime substrate. High-level
`.orc` should normally express `provider-result`, `command-result`, or another
structured producer result. The compiler/runtime may lower that to snapshots,
content hashes, validated bundle commits, and variant selection.

mtime may be recorded for debugging only.

### 3.5 Validate Before Committing State

Validate type, contract, path, variant and effect constraints before committing
an effect result. Evaluated execution appends and synchronizes the validated
memo record, then derives and atomically replaces `state.json` before the next
dispatch. The memo record remains authority if view replacement fails;
`view_write_failed` stops execution without revoking the commit or fabricating
a failure record. See the
[writer sequence](../specs/state.md#writer-sequence-and-durability).

### 3.6 Contracts May Only Narrow

If a value comes from an input, artifact, or reference, later declarations may
refine it only by narrowing. They may not weaken:

- type;
- path kind;
- `under` root;
- must-exist requirement;
- target-existence requirement;
- variant availability.

### 3.7 Variant-Specific Fields Need Proof

For unions, the discriminant is always available. Variant-specific fields are
available only inside a proof context.

Good:

```lisp
(match attempt
  ((COMPLETED c)
    c.execution-report)

  ((BLOCKED b)
    b.progress-report))
```

Bad:

```lisp
attempt.execution-report
```
A computed pure `Bool` condition, such as `(= status "READY")`, may route
control flow, but it is proof-neutral: it does not unlock variant-specific
fields, optional payloads, or union narrowing. Typed `.variant` equality and
inequality comparisons such as `(= attempt.variant COMPLETED)` establish
branch-local variant proof.

### 3.8 Do Not Hand-Manage Runtime State

Avoid hand-authoring:

- state bundle paths;
- snapshot names;
- candidate paths;
- temporary bundle paths;
- pointer files;
- report line-prefix extractors;
- manual variant selectors;
- manual gate outputs.

If high-level `.orc` contains many of those, it is probably written at the wrong
abstraction level.

## 4. Choosing The Right Authoring Unit

Use the smallest unit that represents the behavior truthfully.

| Need | Use | Avoid |
| --- | --- | --- |
| Durable public run/resume/invocation/publication boundary | `defworkflow` | Workflow solely for internal reuse |
| Reusable effectful graph behavior | `defproc` | Copy-pasted steps |
| Pure path/record/schema helper | `defun` | Command step |
| Compile-time syntax abbreviation | `defmacro` | Effectful macro |
| Provider returns structured state | `provider-result` | Markdown parsing |
| Command returns structured state | `command-result` | Stdout scraping |
| Outcome-shaped result | `defunion` + `match` | Stringly gates |
| Fixed-shape result | `defrecord` | Fake tagged union |
| Queue/ledger movement | Unavailable resource effect; see Section 13.4 | Shell move + hidden ledger update |
| Continue an interrupted run | Public memo-backed `resume` | File-existence recovery gate |
| Review/fix loop | Exercised `std/improve` composition in Section 13.7 | Raw back-edge or shell counter |
| Select/run/gap/repeat | Bounded admitted composition; resource drain recipe unavailable | Hidden state/resource effects |

## 5. Types First

Start every workflow family by defining the values it moves across boundaries.

Scope note (design principle 29, adopted 2026-07-25): "types first" describes
where a production workflow family should end up, not an admission price.
Exploratory authoring may begin with generic primitives (`String`, `Int`,
`List[...]`, general path families) and loose result contracts, then narrow
under "contracts may only narrow" as fields get consumed and outcomes get
routed on. Reserve specific nominal types for boundaries where the name
carries a real contract — rooted/existence path families, variants callers
route on with proof, persisted identities — and prefer structural
constraints (`is-record`, `has-field`, `has-union-variant`) over demanding
bespoke nominal types in reusable procedures.

### 5.1 Paths

Use `defpath` for reusable path contracts.

```lisp
(defpath Path.state-file
  :kind relpath
  :under "state"
  :must-exist false)

(defpath Path.state-existing
  :kind relpath
  :under "state"
  :must-exist true)

(defpath Path.execution-report
  :kind relpath
  :under "artifacts/work"
  :must-exist true)

(defpath Path.execution-report-target
  :kind relpath
  :under "artifacts/work"
  :must-exist-target false)

(defpath Path.progress-report
  :kind relpath
  :under "artifacts/work"
  :must-exist true)

(defpath Path.check-commands
  :kind relpath
  :under "state"
  :must-exist true)
```

A value of type `Path.execution-report` is the report path value. It is not the
pointer file path.

### 5.2 Enums

Use `defenum` for stable decision tokens.

```lisp
(defenum DrainStatus
  CONTINUE
  BLOCKED
  EMPTY)

(defenum BlockerClass
  missing_resource
  unavailable_hardware
  roadmap_conflict
  external_dependency_outside_authority
  user_decision_required
  unrecoverable_after_fix_attempt)
```

For the first-tranche parametric review/revise route, `ReviewDecision` is not a
two-value enum example. That route uses the stdlib-owned `ReviewDecision` union
defined in
`docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`.

Enums support contract validation, stable equality-based routing,
prompt-contract generation, and typed diagnostics. Workflow Lisp `match`
currently consumes unions, not enums; use `if` with same-type enum equality
when routing on an enum value.

### 5.3 Records

Use `defrecord` for fixed-shape state.

```lisp
(defrecord ImplementationInputs
  (design Path.design)
  (plan Path.plan)
  (check-commands Path.check-commands)
  (execution-report-target Path.execution-report-target)
  (checks-report-target Path.checks-report-target)
  (review-report-target Path.review-report-target))
```

Use a record when all fields are part of one fixed shape. Good candidates are
workflow inputs, provider settings, resolved selected-item inputs, target path
bundles, command result bundles, and context records.

### 5.4 Unions

Use `defunion` for outcome-shaped state.

```lisp
(defunion ImplementationAttempt
  (COMPLETED
    (execution-report Path.execution-report))

  (BLOCKED
      (progress-report Path.progress-report)
      (blocker-class BlockerClass)
      (blocker-reason String)))
```

Use a union when different outcomes have different valid fields. Do not use a
union when every variant has the same fields. That is a fixed-shape record with
an enum field.

Construct one declared union variant with the explicit `variant` form:

```lisp
(variant ImplementationAttempt COMPLETED
  :execution-report execution-report-path)
```

Keep the union type and variant name explicit. Use the same keyword/value field
shape as `record`. Constructing a union does not prove later field access;
variant-specific reads still need `match` or a branch proven
by a typed `.variant` equality or inequality comparison.

Bad:

```lisp
(defunion SelectedItemInputs
  (ACTIVE_SELECTION)
  (RECOVERED_IN_PROGRESS))
```

Better:

```lisp
(defrecord SelectedItemInputs
  (selection-mode SelectionMode)
  (selected-item-active-path Path.backlog-active)
  (selected-item-in-progress-path Path.backlog-in-progress)
  (selected-item-context-path Path.state-existing)
  (check-commands-path Path.state-existing))
```

### 5.5 Schemas

Use `defschema` when several records share a field group.

```lisp
(defschema ReportTargets
  (execution-report-target Path.execution-report-target)
  (checks-report-target Path.checks-report-target)
  (review-report-target Path.review-report-target))
```

A schema is not a workflow. It is reusable contract structure.

### 5.6 Loose Transport With `Value`

Use compiler-owned `Value` only when the useful contract is
"one transportable JSON value" and consumers do not yet need named fields,
variants, path constraints, or element guarantees. This example uses the
2.35–2.38 procedure syntax:

```lisp
(defproc pass-through ((payload Value)) -> Value
  :effects ()
  :lowering inline
  payload)
```

`Value` accepts `null`, booleans, integers, finite floats, strings, lists, and
string-keyed objects recursively. It is not `Json`: `Json` remains an internal,
non-transportable type. It is also not shorthand for a record or union.
Compatibility is exact, so neither a concrete value nor `Value` implicitly
converts to the other. Narrow the authored contract later when consumers need
more guarantees; do not expect an unchecked cast in the same program.

Exact `Value` is available in the usual transportable parameter, return,
provider/command result, workflow-call, and record/union payload positions.
`Optional[Value]`, `List[Value]`, and `Map[String, Value]` are supported where
their surrounding collection position is supported. `Value` does not make a
Bool condition, `match` subject, path operand, or otherwise ineligible form
valid.

The evaluated program and memo retain the declared opaque type and validated
payload; they never infer a narrower type from a previous run's JSON shape.

## 6. Workflows, Procedures, Pure Helpers, And Macros

### 6.1 `defworkflow`

Use `defworkflow` for durable public workflow boundaries.

```lisp
(defworkflow implementation/run
  ((ctx PhaseCtx)
   (inputs ImplementationInputs)
   (providers ImplementationProviders))
  -> ImplementationResult

  ...)
```

Current parameter forms are:

- `(name Type)`
- `(name Type :default <literal>)`

Use `:default` only on public workflow-boundary inputs that flatten to one
workflow input contract. Supported authored defaults in the current slice are:

- string literals for `String` and path / relpath boundary types
- integer literals for `Int`
- float literals for `Float`
- boolean literals for `Bool`
- enum-member symbols for enum boundary types

Do not use `:default` for record or union boundaries, collections, `nil`,
`WorkflowRef`, `ProcRef`, or computed expressions. Omitting a defaulted binding
uses the callee's compiled workflow-input default; passing a value still
overrides the default.

Use `defworkflow` when:

- operators or external callers run or resume the unit directly;
- the unit has an externally invocable CLI/API workflow-entry registration or
  export contract;
- the unit has an independently addressable child-workflow identity;
- the unit owns stable public inputs, defaults, outputs, or terminal lifecycle;
- the unit should appear as an operator-visible workflow boundary in run state;
- the unit owns public artifact names or publication policy; or
- callers depend on its independent checkpoint/state namespace.

Keep workflow boundaries narrow. Pass typed inputs in and typed outputs out.
Being called from another unit or belonging to a library does not by itself
justify `defworkflow`; ordinary module export of a reusable procedure is not a
workflow-entry export. Use `defproc` for internal reuse.

### 6.2 `defproc`

Use `defproc` for reusable internal effectful graph behavior.

#### Procedure contracts at target 2.39

At target **2.39**, omit `:effects` to infer a procedure's transitive effects
without an authored restriction. Use `:effects ()` when the procedure must
remain free of tracked effects, including after generic or ProcRef
specialization. A named clause is a checked upper bound: the inferred effects
must fit the resolved declared subjects, and unused allowed effects are valid.
For example, `:effects ((uses-provider providers.review))` permits that provider
and refuses a substitution with another provider. Omission never means purity.

```lisp
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.39")
  (defmodule procedure_contracts)
  (export run)

  (defproc inferred ((value Int)) -> Int
    (+ value 1))

  (defproc pure-wrapper ((value Int)) -> Int
    :effects ()
    (inferred value))

  (defworkflow run ((value Int)) -> Int
    (pure-wrapper value)))
```

Do not write `:lowering` on a 2.39 definition: procedures compose inline in
the caller. To express an intentional call/frame/checkpoint boundary, define
an ordinary `defworkflow` and invoke it with `call`. An unexported workflow
can still be selected locally as an entry; its inputs and result must satisfy
workflow transport rules. Compile-time ProcRef/WorkflowRef values and generic
parameters cannot be transported across that boundary. Moving an old private
procedure into a workflow changes definition identity and does not promise
old fingerprints or cross-version resume.

Imported definitions retain their defining target: 2.35–2.38 procedures keep
mandatory exact ordinary declarations, specialization exceptions and their
authored/default lowering policy. A 2.39 caller does not reinterpret those
contracts, and an older module cannot import a 2.39 definition. The packaged
stdlib remains at 2.35. Source below 2.35 is refused.

At 2.39, use genuine imported stdlib bindings for `with-phase` and
`finalize-selected-item`; their bare compatibility heads are refused. Private
expansion heads are admitted only when introduced by the actual packaged
`std/phase` or `std/drain` macro template. This preserves genuine imported
expansion without admitting hand-written private syntax; it does not admit
excluded state/resource effects to evaluated execution.

The [effect-ledger contract](design/workflow_lisp_effect_ledger_simplification.md)
and [frontend lowering/source admission](design/workflow_lisp_frontend_specification.md#106-procedure-lowering-policy-resolved)
own the full rules. REPL `:info` and LSP procedure-completion detail distinguish
authored restrictions from inferred effects. REPL `:type` reports the expression
type and inferred effects only; unresolved generic hooks are marked incomplete.
Evaluated LSP qualification F2 remains
OPEN_NOT_WAIVED. The [proposal recipe](lisp_library_reference.md#target-239-local-hooks)
shows an intentional empty restriction and command ceiling; the
[compact search](lisp_library_reference.md#iterative-search) omits its mirrored
command ledger.

Resolved effect-free helpers can compose in expressions, with eager once-only
arguments and lexical scope; admitted effectful calls still follow Section 2A.
The following illustrative declaration uses the older **2.35–2.38** contract:

```lisp
(defproc ensure-approved-plan
  ((ctx PhaseCtx)
   (selected SelectedItemInputs)
   (roadmap RoadmapState)
   (providers PlanProviders))
  -> PlanGateResult

  :effects
    ((reads selected.selected-item-context-path)
     (uses-provider providers.generate providers.review)
     (writes Path.plan-target)
     (writes Path.review-report)
     (updates-state ctx))

  ...)
```

A macro rewrites syntax. A procedure represents reusable internal workflow
behavior. If
the abstraction has effects, prefer `defproc` or a compiler-owned
standard-library form over `defmacro`.

The evaluated route retains typed callee bodies and lexical call activations.
Choose public workflow boundaries for actual public identity; internal reuse
does not require generated private workflow state.

Procedure effects have two useful views. The direct summary covers effects
introduced by the body. The caller-visible transitive summary also includes
called procedures, selected ProcRef hooks, and child workflows. The accepted
model requires generic specialization to recompute that transitive summary
after type and ProcRef resolution and before lowering. Provider, command,
transition, bridge,
publication, and child-workflow effects must remain explicit. Returning a
value or artifact from a procedure never publishes it implicitly; public
publication stays on the workflow boundary.

This is the current carrier shape. `TypedProcedureDef.direct_effect_summary`
retains body-local effect atoms plus procedure-call edges, and the compiler
recomputes `transitive_effect_summary` over the materialized monomorphic
procedure set after generic and ProcRef specialization. That implementation
does not make every private workflow an eligible procedure: public identity,
checkpoint, state, publication, and live-consumer compatibility gates still
decide each migration.

Current parametric boundary: generic `defproc` headers with `:forall` are
implemented for compile-time-only specialization. The compiler infers concrete
type bindings from call sites, materializes monomorphic specializations before
lowering, and erases those type parameters before runtime-visible artifacts
such as lowered workflows, source maps, Semantic IR, and Executable IR are
emitted. `:where` clauses for generic `defproc` use the fixed clause order
`:forall`, params, `:where`, `->`. The constraint vocabulary, subset
semantics, and specialization pipeline are owned by
[Workflow Lisp Parametric Type System](design/workflow_lisp_parametric_type_system.md);
the stable spellings, summarized:

- `(T is-record)`
- `(T is-union)`
- `(T has-field field Type)`
- `(T has-union-variant VARIANT)`
- `(T has-union-variant VARIANT (field Type) ...)`
- `(T has-shared-union-field field Type)`

The `Type` position in `has-field`, `has-union-variant`, and
`has-shared-union-field` may name another `:forall` parameter, which is how
cross-parameter contracts are expressed — for example, constraining a hook's
payload parameter to be the same type as the selector union's
`SELECTED.selection` field.

Constraint checks run against resolved concrete call-site types before the
specialization is accepted, and every clause carries subset semantics: it
proves a required capability; no clause forbids extra caller fields or
variants or proves exact shape. `has-shared-union-field` is intentionally
narrow: it allows branch-free projection only of the named field after the
constraint is validated; it does not prove which variant is present, and it
does not make variant-specific fields available outside a proof-bearing
`match` — and adding a caller variant that lacks the shared field breaks that
constraint. Variant and field names referenced by a stdlib definition's
`:where` clauses are frozen public vocabulary for callers. Generic
`defworkflow` remains out of scope in the current compiler surface.

### 6.3 `defun`

Use `defun` for pure helper logic.

```lisp
(defun phase-target
  ((ctx PhaseCtx)
   (name String))
  -> Path.state-file

  (path/join ctx.state-root name))
```

A `defun` may construct records, construct symbolic paths, select fields,
combine strings, compute constants, and build type-level descriptors. Pure
computation inside a `defun` uses the closed pure-expression operator surface
(Section 9A); the body either folds at compile time or lowers to the same
pure-expression payload the runtime evaluator executes.

A `defun` may not read files, write files, call providers, call workflows, run
commands, inspect wall-clock time, or generate random values.

If it has an effect, it is not a `defun`.

### 6.4 `defmacro`

Macros are for syntax, not hidden workflow behavior.

A macro may construct AST, introduce hygienic bindings, expand shorthand into
typed forms, and emit source-map frames.

A macro may not perform filesystem I/O, perform network I/O, depend on
wall-clock time, call providers, run commands, weaken contracts, emit executable
IR directly, or hide effects.

The current `defmacro` surface is a deterministic frontend-only syntax
expander. It supports top-level template macros, hygienic introduced names,
imported macro visibility, source-map provenance, and validation through the
ordinary frontend pipeline. It does not support compile-time I/O, runtime macro
values, intentional capture syntax, alternate validators, or direct Semantic IR
or Executable IR generation.

Macro-origin failures are owned by the same layer that would own the expanded
form without a macro. Macro provenance is additive; it does not create a second
validation stack. See the macro surface contract for the current diagnostic
ownership matrix.

Ordinary workflow authors should rarely need user-defined macros. Prefer
standard-library procedures and compiler-owned forms until there is evidence
that custom macros are needed.

## 7. Modules, Imports, And Exports

Use modules to make workflow libraries navigable.

```lisp
(defmodule neurips.implementation
  (import neurips.common :as common)
  (export
    ImplementationInputs
    ImplementationProviders
    ImplementationResult
    run)

  ...)
```

Prefer explicit imports:

```lisp
(import neurips.implementation :as impl)
(import neurips.plan :as plan)
```

Then call workflows clearly:

```lisp
(call impl/run
  :ctx implementation-ctx
  :inputs implementation-inputs
  :providers providers.implementation)
```

Reserve cross-module `call` for callees that own a durable public boundary
under the section 4 table and
`docs/design/workflow_lisp_procedure_first_reuse_contract.md`. Reuse that
does not need its own run/resume identity belongs in an exported `defproc`,
not a workflow call.

Rules:

- export only stable workflow/library surfaces;
- keep internal helpers private;
- avoid wildcard imports;
- avoid duplicate names that canonicalize to the same field name (the
  compiler rejects duplicate import aliases and duplicate exports outright).

## 8. Structured Provider Results

Use `provider-result` when a provider produces structured state.

`:returns` may name a record, a union, or any currently transportable
narrower type directly — `Bool`, `Int`, `Float`,
`String`, an enum, a declared path, `Optional[T]`, `List[T]`, or
`Map[String, T]`, including exact opaque `Value`. The provider writes the
plain JSON value to its runtime-bound result bundle; a `Value` object, boolean,
list or `null` is written directly, never inside `{"value": ...}`.

```lisp
(let* ((attempt
         (provider-result providers.execute
           :prompt prompts.implementation.execute
           :inputs (inputs.design inputs.plan)
           :returns ImplementationAttempt)))

  ...)
```

Supported scalar, record, relpath, exact `Value`, closed
union, and recursively renderer-admitted `List[T]` values in `:inputs` are
rendered at the provider prompt consumer seam without family-profile metadata.
Scalars, records, unions, `Value`, and admitted lists use the canonical-JSON default;
relpaths use the registered POSIX-path default. Selection follows static
structural type/kind recursively rather than nominal type names:
`List[ReviewReportPath]` is admitted, while `List[RunId]` is not. Typed state
remains authority and the rendered bytes are ephemeral provider input.

Pass a union result directly to the next call with
`:inputs (decision)`, or fill a prompt's `:value Decision` slot. The provider
receives canonical JSON containing the discriminant and only the active
payload, including nested records and lists. No `match`-and-repackage step is
needed. This does not grant source-level access to an unproven variant's fields.

Use `:prompt-dependencies` additionally when the provider needs a relpath
target's file contents. Rendering a relpath value supplies the path, not the
file body.

When one call needs authored model, effort, or deadline policy, use the bounded
generic surface rather than a provider-specific parameter map:

```lisp
(let* ((attempt
         (provider-result providers.execute
           :prompt prompts.implementation.execute
           :inputs (inputs.design inputs.plan)
           :model inputs.worker-model
           :effort inputs.worker-effort
           :timeout-sec 7200
           :returns ImplementationAttempt)))

  ...)
```

`:model` and `:effort` must be exact `String` expressions in the effect-free
inline-lowerable scalar/template subset. String literals, typed inputs or
procedure parameters, names, references, and supported projections are the
intended shape; computed calls, records, operators, and other general
expressions are not silently materialized. `:timeout-sec` is only a positive
exact-`Int` literal. Omit a keyword to preserve provider defaults; omission does
not synthesize policy, argv fragments, or `null` fields.

Provider externs remain compiler-known. Their declarative bindings decide how
canonical model/effort reach native argv; workflow authors do not construct
`provider_call_policy`, `call_policy_bindings`, or arbitrary provider params in
`.orc`. Unsupported canonical options fail before launch. Public evaluated
resume treats policy changes as ordinary source/program drift and preserves its
program, bound-input and memo integrity guards. Runtime plans, reports,
dashboard/debug projections, `expanded.debug.yaml`, and source maps are
inspection views, not call-policy or resume authority.

### Portable Provider Context

Provider context binding and capture are unavailable at targets 2.35/2.36 and
refuse with `closed_program_gap`. Use typed results or artifact handoffs within
the admitted provider subset. The
[provider-context contract](design/workflow_lisp_provider_context_values.md)
preserves the historical context/type contract and its coverage limits;
its executable route is retired, with no evaluated capture port selected.

### Agent sessions (target 2.38)

Status: allocation, turns, recovery, C8 guards and instance views are implemented
at target 2.38. The [qualification record](reports/2026-10-14-agent-sessions-pq1a-qualification.md)
contains deterministic proofs and bounded adapter smokes; the clean and failed/resumed
comparison (PQ-1c) has not run and requires separate owner authorization. The
[Agent Sessions design](design/workflow_lisp_agent_sessions.md) owns the contract.

Choose an agent when later calls should continue the same native conversation; use independent
calls and artifact handoffs when typed inputs suffice. The cost: invalidating a
suffix containing a committed agent turn is refused (C8); earlier work cannot
be rerun in place. An interrupted first turn may run more than once.

The opt-in [worked example](../workflows/examples/design_review_execute_agents.orc)
uses this complete four-turn body. Its `defworkflow` inputs, path/record types and
inline `defprompt` declarations are in that file:

```lisp
(let* ((designer (agent providers.claude :model planner_model :effort "high"))
       (reviewer (agent providers.codex :model reviewer_model :effort "high"))
       (draft (provider-result designer :timeout-sec 3600
                :prompt (draft-design :task task)))
       (feedback (provider-result reviewer :timeout-sec 3600
                   :prompt (review-design :task task :design draft.doc)))
       (revised (provider-result designer :timeout-sec 3600
                  :prompt (revise-design :task task :design draft.doc :draft_path draft.doc
                                         :blocking feedback.blocking :notes feedback.notes))))
  (provider-result reviewer :timeout-sec 14400
    :prompt (execute-design :task task :design revised.doc)))
```

`designer` and `reviewer` are separate conversations. The designer retains its
draft context for revision; the reviewer retains its review context for execution.
Each turn also returns its own checked value: `Draft` carries `doc`, `Feedback`
carries `blocking` and `notes`, `Design` carries the revised `doc`, and `Execution`
carries the final summary, commits, checks and unfinished work. The `:doc` fills
still deliver the current typed document; native history does not replace current
inputs or result contracts.

`(agent <provider-extern> [:model String] [:effort String])` allocates one
`Agent` without launching a provider. Its provider must be compiler-known;
model/effort are its only options and must be inline `String` operands.
`(provider-result <agent> :prompt ... [:timeout-sec N])` takes a turn and returns
its typed result. Turns run in source order; aliases, aggregates, branches and
same-run `defproc` arguments/returns reuse the same agent.

Constructor `:model`/`:effort` pin instance policy; prompts, inputs and timeouts
belong to turns. The example keeps the baseline's models (`claude-opus-5-5`,
`gpt-6.1-sol`), effort and timeouts. Override models initially with
`--input planner_model=...` / `--input reviewer_model=...`, never on a turn.

Use the existing manifests, from the repository root:

- [providers.json](../workflows/examples/inputs/design_review_execute_agents/providers.json)
  binds `providers.claude` to `claude_unrestricted_workspace` and `providers.codex`
  to `codex`.
- [inputs.json](../workflows/examples/inputs/design_review_execute_agents/inputs.json)
  supplies a sample `task` string. Select the intended task before a real run;
  your own input JSON can use the same fields.
- No prompt manifest is required: the four prompts are inline `defprompt` declarations.

Prerequisites: a repository/worktree containing `AGENTS.md`, `docs/index.md` and
`docs/templates/design_template.md`, and installed Python dependencies. Real work
requires authenticated `claude`/`codex` on `PATH`, using existing
`CODEX_HOME`/`CLAUDE_CONFIG_DIR` or default homes; no homes/credentials are provisioned.
The final turn modifies and commits the workspace. [Tmux views](../specs/observability.md) are read-only,
best-effort and optional.

Compile and dry-run validate the maintained example without invoking providers:

```bash
python -m orchestrator compile workflows/examples/design_review_execute_agents.orc \
  --provider-externs-file workflows/examples/inputs/design_review_execute_agents/providers.json

python -m orchestrator run workflows/examples/design_review_execute_agents.orc \
  --provider-externs-file workflows/examples/inputs/design_review_execute_agents/providers.json \
  --input-file workflows/examples/inputs/design_review_execute_agents/inputs.json \
  --dry-run
```

To opt into paid provider work after checking the task and workspace, run the
second command with `--dry-run` removed, using the intended input JSON. Use its
`RUN_ID` to continue or inspect the run from that same workspace:

```bash
python -m orchestrator resume RUN_ID
python -m orchestrator report --run-id RUN_ID --format json
```

Use `resume`, including admitted first-turn bootstrap; `--force-restart` is
unavailable. Native loss or external advancement can block new turns; completed
replay needs no native session. See the normative
[resume contract](../specs/cli.md#evaluated-execution-target-235) and
[Agent persistence/recovery limits](design/workflow_lisp_agent_sessions.md#persistence-recovery-and-invalidation)
for refusal/invalidation rules. This example remains opt-in with bounded evidence;
the recipe earns no further qualification or PQ-1c acceptance. REPL remains
2.35/2.36; use `report` here.

Refused at compile time:

| Code | When |
| --- | --- |
| `agent_target_dsl_unsupported` | `agent` in a module below target 2.38 |
| `agent_provider_invalid` | The first operand is not a compiler-known provider extern |
| `agent_keyword_invalid` | A keyword other than `:model` or `:effort`, such as `:timeout-sec`, on `agent` |
| `agent_model_type_invalid`, `agent_effort_type_invalid` | `:model` or `:effort` is not a `String` |
| `agent_policy_operand_not_inline_lowerable` | `:model` or `:effort` is a `String` expression the compiler cannot inline, such as an `if` |
| `frontend_parse_error` | A malformed `agent` form: an odd key/value list, an entry that is not a keyword, a duplicated keyword, or a keyword where the provider belongs |
| `agent_turn_policy_override_forbidden` | `:model` or `:effort` on a turn; change the constructor instead |
| `agent_turn_option_unsupported` | Context capture, `:session-artifact`, phased delivery or another option outside the bounded turn |
| `agent_transport_forbidden` | An `Agent` in provider or command data: `:inputs`, a prompt `:value` fill, `:argv` |
| `workflow_boundary_type_invalid`, `workflow_return_type_invalid` | An `Agent`, or a record or union carrying one, in a `defworkflow` parameter or return, a `call` argument, or a `run-ref` input or result |
| `provider_result_return_type_invalid`, `command_result_return_type_invalid` | A provider or command result type that carries an `Agent` |
| `loop_state_runtime_transport_forbidden` | An `Agent` in `loop/recur` state |
| `parallel_agent_boundary` | An `Agent` entering or leaving a parallel worker, or a worker reaching an allocation or turn through a helper, child workflow, macro or `ProcRef` |
| `let_proc_capture_agent_forbidden` | A `let-proc` or `bind-proc` capturing an `Agent` |
| `pure_expr_operand_type_mismatch` | Equality or printing of an `Agent` |
| `agent_origin_mismatch` | Closed-program check: a turn's provider origins omit a provider its `Agent` operand can reach, as in a hand-edited closed program |

The [state spec](../specs/state.md) owns allocation/turn records. Agent sessions
supersede `prompt-queue`, which is not implemented.

### Durable Host Input

`request-input` is unavailable at targets 2.35/2.36 and refuses with
`closed_program_gap`. The [human-input contract](../specs/dsl.md)
preserves the historical host-input lifecycle; old-profile answer/cancel
mutation is retired. No current executable host-input lane is available.

### Explicit OMP Session Publication

Provider session artifacts are unavailable at targets 2.35/2.36 and refuse
with `closed_program_gap`. The typed result bundle remains provider-result
authority. See the [session publication contract](../specs/providers.md)
and [OMP runbook](omp_upgrade_runbook.md) for historical session publication and retained verified native `prompt resume`
(including `--in-place`), without creating scaffolds or compiling old workflows.

### Provider Prompt Dependencies

When provider prompt semantics require workspace file contents, declare exact
typed prompt dependencies on the provider result:

```lisp
(provider-result providers.execute
  :prompt prompts.implementation.execute
  :inputs (request)
  :prompt-dependencies
    (:required (inputs.work-order inputs.target-design)
     :optional (inputs.prior-findings)
     :position prepend
     :instruction "Use these files as authoritative inputs:")
  :returns ImplementationAttempt)
```

Each operand must already have a declared workspace `relpath` type. Required
paths must exist; optional paths may be absent. Optional does not mean
`Optional[Path]`. `:position` defaults to `prepend`; use `append` only when the
provider contract needs the dependency block after the base prompt. An omitted
instruction uses the standard required/optional label; an authored instruction
must be literal text.

Do not substitute strings, globs, broad ambient documentation sets, dynamic
instructions, or commands that copy file contents into an intermediate bundle.
The runtime resolves and de-duplicates present targets, renders them in
deterministic canonical path order, and bounds the exact UTF-8 dependency block
to `262144` bytes with explicit truncation. One attempt uses one immutable
snapshot; a retry reads a fresh snapshot. Evaluated resume rereads prompt
sources and dependencies to compare their digests before reusing a committed
provider result. Changed, missing or unreadable committed inputs refuse with
`effect_input_diverged` before launch; compatible results are reused without
redispatch. See [evaluated provider IO](../specs/io.md#evaluated-command-and-provider-io-target-235).

The compiler-owned typed contract and per-attempt content-free evidence are not
authoring surfaces. `runtime_plan` remains topology-only, and evidence or its
offline index never controls execution or resume. Historical YAML
content-injection behavior may remain in parity evidence, but no fresh authored
YAML path reaches it.

The provider must produce structured output matching the return type. The
result travels through one channel: a validated bundle written at the
runtime-bound output location the provider receives with its injected
output contract. JSON printed to stdout is never the result — stdout and
stderr are observability evidence only, for providers and commands alike.
The bound-path bundle is the current sanctioned transport, not part of the
authored contract: `:returns` declares the contract, and any future result
channel must pass the same fail-closed validation.

Markdown reports may be written and referenced by fields in the structured
result, but the report is not parsed later for semantic state.

Good pattern: pass the validated typed provider result directly to `match`
and carry its actual report path as data. The complete evaluated recipe above
shows supported provider transport.

Bad pattern:

```lisp
(let* ((report
         (provider-result providers.execute
           :prompt prompts.implementation.execute
           :returns Path.execution-report))

       (blocker-class
         (command-result parse-blocker-class
           :argv ("python" "extract_line.py" report "Blocker Class:")
           :returns BlockerClass)))

  ...)
```

This turns a human-facing report into semantic state. That belongs only in a
marked legacy adapter.

### Prompt Obligations

The return type defines the structured result contract.

Prompts should describe:

- task objective;
- scope boundaries;
- required structured output;
- human-facing report expectations;
- forbidden shortcuts;
- domain-specific evidence requirements.

Prompts should usually avoid:

- runtime pointer internals;
- orchestrator state paths;
- snapshot selection mechanics;
- variant proof mechanics;
- workflow routing internals.

<a id="authoring-prompt-fragments---target-220"></a>

### Authoring Prompt Fragments

Use `defprompt` when one provider prompt should own its complete visible input
contract and result contract:

```lisp
(defprompt review-design-doc
  (:fills
    (target_doc :doc DesignDocPath)
    (context_docs :value List[DesignDocPath])
    (review_focus :text)
    (checks_report :path WorkReportPath))
  -> ReviewDecision
  "Review the injected target using this focus:
   {review_focus}
   Context document paths: {context_docs}
   Checks report path: {checks_report}")

(provider-result providers.review
  :prompt
    (review-design-doc
      :target_doc completed.target_doc
      :context_docs completed.context_docs
      :review_focus inputs.review_focus
      :checks_report inputs.checks_report)
  :model inputs.review_model
  :effort inputs.review_effort
  :timeout-sec 3600)
```

The application is named and fully applied. Each declared slot appears once;
the compiler normalizes fill order to declaration order. The prompt-owned
return replaces call-site `:returns`, and the declared fills replace call-site
`:inputs` and `:prompt-dependencies`. Do not author both representations.

Choose slot kinds by delivery:

| Kind | Use |
| --- | --- |
| `:doc PathType` | Inject one required existing workspace file through the fixed prepend dependency lane. Do not put `{slot}` in the template. |
| `:text` | Insert exact `String` bytes inline. |
| `:value T` | Insert canonical JSON for a uniquely supported static type. Includes recursively supported `List[T]`, such as `List[DesignDocPath]`. |
| `:path PathType` | Insert one POSIX path reference line, not file content. |

Every `:text`, `:value`, and `:path` slot needs at least one `{slot-name}`
placeholder. `{{` and `}}` produce literal braces. Placeholders do not support
format operators, indexing, attribute access, whitespace, or expressions.

Refinements are optional constraints, not nominal prompt brands. They may only
narrow an already supported kind/renderer pairing. In particular, `:value`
does not convert `T` to the Workflow Lisp `Value` type. Closed unions and
eligible lists of unions use canonical JSON; optional, map, reference,
resource and schema fragment rendering are not generally admitted.

Do not partially apply a prompt, store it in a record, return it, pass it as a
procedure reference, nest it in another fragment, or use it outside
`provider-result :prompt`. Keep an existing extern-backed call when it needs
independent `:inputs`, authored `:prompt-dependencies`, or an authored
`:returns`.

The compiler and runtime bind the fragment program with
`compiled_prompt_fragment_identity`; authors do not construct or persist that
field. A changed declaration, result contract, or fill expression changes
program identity and is ordinary resume drift. Runtime prompt snapshots are
evidence views, not an authoring or recovery surface.

### Authoring Prompt Output Positions

Use one `:path :out` slot when the prompt must tell the provider where to write
one required UTF-8 file and the runtime must validate that same path:

```lisp
(defprompt review-design-doc
  (:fills
    (target_doc :doc DesignDocPath)
    (review_report_target_path :path :out ReviewReportTargetPath))
  -> ReviewDecision
  "Review the injected target.
   Write the review to {review_report_target_path}.")

(provider-result providers.review
  :prompt
    (review-design-doc
      :target_doc completed.target_doc
      :review_report_target_path inputs.review_report_target_path)
  :model inputs.review_model
  :effort inputs.review_effort
  :timeout-sec 3600)
```

The slot's one named fill drives both the rendered POSIX path and one required
file postcondition. The prompt still owns one structured result:
`ReviewDecision` remains semantic authority for the decision and its declared
fields, while the generated file contract validates the human-facing report.
The historical first consumer, `review-design-docs` in
`tests/fixtures/workflow_lisp/retired_examples/review_revise_design_docs.orc`,
is not an evaluated copy target; the slot contract itself remains admitted.

Do not add a call-site output declaration, duplicate the path in another
contract, or infer a general relationship between an output slot and a result
field. Output-position names and resolved destinations must be disjoint from
the structured-result bundle before the provider starts. The prompt and
post-attempt validators process the output position first and the structured
result second; neither artifact mapping enters state unless both pass.

Output positions do not add optional files, directories, globs, dynamic
output sets, arbitrary file schemas or a second result channel. Diagnostic
prompt-identity and judgment-view contracts are scoped separately below.

### Inspecting Prompt-Attempt Identity

Prompt identity and drift evidence is diagnostic, never a workflow value or
resume decision. The [prompt-identity contract](design/workflow_lisp_prompt_identity_diagnostics.md)
owns Q3's versioned snapshot and report behavior; its older-route evidence does
not establish evaluated-profile availability. Use the evaluated lifecycle and
reader contracts for reports from a 2.35/2.36 run.

### Inspecting Judgment Views

Q4 judgment views are a bounded read-only diagnostic projection, not provider
results or workflow-readable state. See the
[judgment-view contract](design/workflow_lisp_judgment_views.md) and the
[capability matrix](capability_status_matrix.md) for the panel's exact scope;
older-profile snapshot evidence does not qualify evaluated readers.

### Authoring Phased Contract Delivery

Phased provider delivery and materialization attempts are unavailable at
2.35/2.36 and refuse with `closed_program_gap`. Use ordinary composed delivery
for admitted calls. The [prompt-calculus contract](design/workflow_lisp_prompt_calculus.md)
preserves the historical phased lifecycle; no current executable port is selected.

## 8A. Bounded Live Provider Supervision

`with-live-providers` is unavailable at targets 2.35/2.36 and refuses with
`closed_program_gap`. See the
[live-binding contract](design/workflow_lisp_provider_live_binding.md) for the
historical one-worker/one-supervisor surface; its execution is retired.

## 8B. Recorded Provider Peer Groups

`with-live-provider-peers` is unavailable at targets 2.35/2.36 and refuses with
`closed_program_gap`. See the
[peer-messaging contract](design/workflow_lisp_provider_peer_messaging.md) for
the historical cooperative-provider surface; its execution is retired.

## Pinned Child Runs And Trials

Path-mode `run-ref` is admitted at targets 2.35/2.36. Pin an exact literal
40-character lowercase Git commit, supply every child input, and preserve the
child's exact result contract and `:deterministic-effect-free` environment.
Relpath inputs are copied and rebound into the pinned child workspace after
validation; cloning and process boundaries are not an OS sandbox.

Use the exercised path-child fixtures in
[`tests/test_workflow_evaluated_run_ref.py`](../tests/test_workflow_evaluated_run_ref.py)
and the [path-child lifecycle](design/workflow_lisp_evaluated_execution.md#931-path-child-admission-authority-and-return)
for source, pin and root requirements. The public lifecycle recipe above
records the run-reference root used on resume.

Bundle-mode run references and `trial` are unavailable at both evaluated
targets and refuse with `closed_program_gap`. The `trial` CLI and old trial SDK
are retired; the CLI refuses with `workflow_execution_target_retired` before
source reads or publication. The [DSL contract](../specs/dsl.md) and
[CLI contract](../specs/cli.md#evaluated-execution-target-235) own those boundaries.

### Confined workflow children (target 2.38, command-only)

Use `:program (:workflow name)` when commands must execute in a runtime-owned
clone and OS confinement boundary. The child is a static workflow from the
parent's checked module graph; the candidate repository supplies project files,
not executing `.orc` source or configuration. Command-only `:network :none`,
recovery and typed exports are admitted. The
[design](design/workflow_lisp_run_ref_expression_environments.md) explains the
full target; the [plan/report](plans/2026-10-14-run-ref-expression-environments-plan.md)
records command acceptance and the separate provider blocker.

Prepare a Linux x86_64 host with root-owned `/usr/bin/bwrap` and
`/usr/bin/systemd-run`, unprivileged user/network namespaces, a reachable user
systemd manager with delegated cgroup v2 `cpu`, `memory` and `pids`, and Yama
`ptrace_scope >= 1`. Admission verifies scope limits, quota and release controls;
a missing prerequisite refuses rather than falling back to host execution.
Provide a trusted Linux/amd64 OCI image layout containing `/bin/sh`,
`/usr/bin/env`, `/usr/bin/setsid`, `python3` and the project's dependencies.
Use its repository plus manifest digest, not a tag or an illustrative digest.
No provider login or API key is needed for this command-only recipe.

Image preparation is an installation step outside the workflow. There is no
public image-import CLI: use the existing `import_oci_layout` API on a local OCI
layout. The runtime reads the sealed store at `<run-ref-root>/images`, with
`records/<digest-hex>.json` and `rootfs/<digest-hex>`; it rehashes the descriptor
before launch. Obtaining the OCI layout is operator provisioning, not a runtime
registry pull. From the repository root, set `IMAGE` to the real reference and
`OCI_LAYOUT` to its existing absolute layout directory, then:

```bash
export IMAGE='your-registry/your-image@sha256:YOUR_REAL_MANIFEST_DIGEST'
export OCI_LAYOUT='/absolute/path/to/your/oci-layout'
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
export DEMO_ROOT="$(mktemp -d /tmp/orc-confined-command.XXXXXX)"
export RUN_REF_ROOT="$DEMO_ROOT/run-ref"
python - <<'PY'
import os
from pathlib import Path
from orchestrator.workflow.run_ref.image_store import import_oci_layout
import_oci_layout(Path(os.environ["RUN_REF_ROOT"]) / "images",
                  os.environ["IMAGE"], Path(os.environ["OCI_LAYOUT"]))
PY
```

This minimal example has one confined producer and one ordinary host command
that consumes the exported file after child cleanup. The producer writes its
typed result through the runtime-selected bundle path. Create a pinned local
candidate repository and parent source; these setup commands are outside the
workflow, and the workflow itself contains no clone/setup shell step:

```bash
mkdir "$DEMO_ROOT/candidate" "$DEMO_ROOT/parent"
cat > "$DEMO_ROOT/candidate/produce.py" <<'PY'
import json, os
from pathlib import Path
path = Path("out/result.txt")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text("hello from the confined child\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(str(path)))
PY
git -C "$DEMO_ROOT/candidate" init --quiet
git -C "$DEMO_ROOT/candidate" add produce.py
git -C "$DEMO_ROOT/candidate" -c user.name=Demo -c user.email=demo@example.invalid commit --quiet -m candidate
export REVISION="$(git -C "$DEMO_ROOT/candidate" rev-parse HEAD)"
cat > "$DEMO_ROOT/parent/consume.py" <<'PY'
import json, os, sys
from pathlib import Path
text = Path(sys.argv[1]).read_text()
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(text))
PY
python - <<'PY'
import json, os
from pathlib import Path
root = Path(os.environ["DEMO_ROOT"])
parent = root / "parent"
source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.38")
  (defmodule run_ref_confined) (export main)
  (defpath Artifact :kind relpath :under "out" :must-exist true)
  (defworkflow candidate-body ((seed Int)) -> Artifact
    (command-result produce :argv ("python3" "produce.py") :returns Artifact))
  (defworkflow main ((seed Int) (revision String)) -> String
    (let* ((child (run-ref :source (:repo "REPOSITORY" :commit revision)
                    :program (:workflow candidate-body) :inputs (:seed seed)
                    :policy (:environment :confined :image "IMAGE" :network :none
                             :limits (:wall-seconds 300 :memory-mib 1024 :cpus 1 :pids 64
                                      :workspace-mib 32 :output-mib 8)))))
      (match child
        ((COMPLETED c)
          (command-result consume :argv ("python3" "consume.py" c.result.value) :returns String))
        ((FAILED f) f.code)))))'''
(parent / "run_ref_confined.orc").write_text(
    source.replace("REPOSITORY", (root / "candidate").as_uri()).replace("IMAGE", os.environ["IMAGE"]))
(parent / "commands.json").write_text(json.dumps({
    "produce": {"stable_command": ["python3", "produce.py"], "closure": []},
    "consume": {"stable_command": ["python3", "consume.py"], "closure": []}}))
(parent / "providers.json").write_text("{}")
(parent / "inputs.json").write_text(json.dumps({"seed": 1, "revision": os.environ["REVISION"]}))
PY
```

Run the public lifecycle from the parent workspace so its command paths and
resume recipe remain stable. `RUN_REF_ROOT` must retain its canonical absolute
spelling. Read `RUN_ID` from the new directory beneath `runs` (or its `run.json`):

```bash
cd "$DEMO_ROOT/parent"
python -m orchestrator compile run_ref_confined.orc --entry-workflow run_ref_confined::main --source-root . --command-boundaries-file commands.json --provider-externs-file providers.json
python -m orchestrator run run_ref_confined.orc --entry-workflow run_ref_confined::main --source-root . --command-boundaries-file commands.json --provider-externs-file providers.json --input-file inputs.json --state-dir "$DEMO_ROOT/runs" --run-ref-root "$RUN_REF_ROOT"
export RUN_ID='the-new-run-directory-name'
python -m orchestrator resume "$RUN_ID" --state-dir "$DEMO_ROOT/runs" --run-ref-root "$RUN_REF_ROOT"
python -m orchestrator report --run-id "$RUN_ID" --runs-root "$DEMO_ROOT/runs" --format json
```

Resume the **parent** run after interruption; the public CLI does not provide
an independent confined `CHILD_ID` resume entry. Its coordinator recovers the same
child once a child effect is committed, reuses that prefix and reruns only a
permitted pending attempt. A durable child terminal is reused even with zero
commits. This is at-least-once command execution before commit, so retain the
ordinary `must_not_repeat` boundary for work that cannot safely repeat. Completed
resume dispatches nothing; a recorded cleanup obligation is retried, with exit 2
and `run_ref_cleanup_pending` while still pending, then exit 0 after completion.
The public command integration test
[`test_increment_a_public_lifecycle_with_commands`](../tests/e2e/test_e2e_run_ref_confined.py)
adds a second child command, kills externally after the first commit, and checks
same-child recovery, parent consumption and repeated completed resumes/reports.

The call returns `COMPLETED` with `result.value`, `workspace_delta` and
`accounting`, or `FAILED` with `code`, `detail` and `accounting`; pre-release
structural/admission failures still abort the parent. Match the union before
reading its value. Output paths require a nonempty workspace-relative `:under`
and `:must-exist true`; runtime copies and rebases validated files under
`<under>/.run-ref-exports/<parent-run>/...` before clone cleanup. Exports survive
cleanup; manually retiring the parent means removing its run root and associated
export directories. The 32 MiB workspace requires at least 992 MiB memory under
the profile's `workspace + 960` rule; the example supplies 1024 MiB.

Confined children exclude nested run references, parallel effects, sessions/context,
Agent allocation/turns, dynamic evaluation, trials, human/resource effects and
`provider-bundle-path`. A confined site is also excluded from serial or parallel
`list/map-effect` frames. Image-pinned interpreters execute project scripts as
arguments; command `closure` entries cannot resolve into the mutable clone.
The independent 2.38 [Agent recipe](#agent-sessions-target-238) runs outside this
child profile and does not widen it.

Public confined provider sites still refuse with
`run_ref_provider_transport_unavailable` before state/holder creation. Private
per-leaf Holder transport and synthetic checks do not qualify native auth/TLS or
the public `:model-only` route. The selected native Codex transport uses existing
managed ChatGPT login (`authMethod=chatgpt`), with no API key; managed-policy
qualification remains blocked in the [plan/report](plans/2026-10-14-run-ref-expression-environments-plan.md#task-10-provider-transport).
Claude and other transports require separate qualification. The full provider
module in the design and the future best-of-N migration are not runnable templates.

## 9. Structured Command Results

Use `command-result` when a deterministic command or certified adapter returns
structured state.

`:returns` may name a record, a union, or any currently transportable type
directly. If current behavior genuinely
has a meaningful fixed result shape, model that shape as a record. Otherwise,
prefer a direct scalar/enum/path/optional/list/map return over inventing a
transport-only one-field wrapper.

```lisp
(defrecord ChecksResult
  (checks-report Path.checks-report)
  (status String))

(command-result run-checks
  :argv
    ("python"
     "workflows/library/scripts/run_checks.py"
     "--commands" inputs.check-commands
     "--report" inputs.checks-report-target)
  :returns ChecksResult)
```

`command-result` requirements:

- the command has declared inputs;
- the command has declared outputs;
- the command exposes structured result state;
- the command's effects are visible;
- the result is exposed only after validation succeeds;
- stdout parsing is not semantic authority.

### Certified Command Adapters

Use a certified adapter when the runtime does not yet have a native effect.

Examples:

- legacy queue move script;
- legacy ledger update script;
- legacy report normalizer;
- legacy path resolver;
- legacy external tool wrapper.

A certified adapter must have a registered adapter name, declared argv shape,
declared input/output contracts, declared effects, fixtures, source-map origin,
and a migration/deprecation note if it should become runtime-native later.

Bad:

```lisp
(command-result move-item
  :argv ("python" "-c" "... complex inline script ...")
  :returns Json)
```

Better:

```lisp
(command-result normalize-summary
  :adapter normalize_result
  :inputs
    ((execution_report completed.execution_report)
     (review_report approved.review_report))
  :returns ImplementationSummary)
```

Use direct `command-result :adapter` only for non-resource, non-resume
certified adapters with declared typed fields. Resource transitions and
reusable-state helpers remain unavailable at evaluated targets; do not hide
those semantics in an arbitrary command workaround.

## 9A. Pure Computation And Typed Projection

If the logic is a comparison, a count, a boolean combination, a default, a
reason string, or typed record/union construction over values you already
have, write it in the language. Do not shell out.

The operator surface is closed and shared by compile-time folding and the
runtime evaluator (normative table:
[Workflow Lisp Frontend Specification](design/workflow_lisp_frontend_specification.md),
Section 10.2):

| Group | Operators |
| --- | --- |
| Equality | `=`, `!=` over `String`, `Int`, `Bool`, `Symbol`, same-type enums |
| Ordering | `<`, `<=`, `>`, `>=` over `Int` pairs or `Float` pairs |
| Boolean | `and`, `or`, `not` |
| Arithmetic | `+`, `*`, `min`, `max` over two or more operands, all `Int` or all `Float`; `-` over two; `/` over two `Float`; `int/div` (rounds toward negative infinity) and `int/mod` (sign of the divisor) over two `Int`; `float/abs`, `float/sqrt`, `float/log` (natural) over one `Float` |
| Conversion | `int/to-float`; `float/floor` and `float/round` (halves to even) to `Int`, refused outside 64 bits |
| String | `string/concat`, `string/empty?`, `symbol/name` |
| Option | `some?`, `or-else` |
| Record | `record-update` |

A decimal literal (`1.5`, `-0.25`, `2e-3`) is admitted wherever an expression
is admitted. Mixed numeric operands refuse at compile time; conversion must
be explicit. Integer arithmetic fails closed on 64-bit overflow, and
non-finite floats at input/result/resume boundaries refuse with
`float_not_finite`. The [numeric contract](design/workflow_lisp_numeric_surface.md)
owns exact arities, rounding and domain rules.

There is no float equality, path-string concatenation, regex, time, randomness
or IO in pure expressions. Use the list surface in Section 17.2 for collection
operations; record a capability gap rather than inventing operators.

Typed projection example — compare, default, and construct without Python:

```lisp
(defworkflow orchestrate
  ((approved Bool)
   (status String))
  -> SelectorSummary
  (record-update
    (record SelectorSummary
      :status status
      :ready false)
    :ready (or approved (= status "READY"))))
```

Choosing the surface:

| Behavior | Use |
| --- | --- |
| Compare, count, combine, default, build a reason string or typed value | Pure expressions / `defun` |
| Produce a typed record/union from existing typed values | Pure typed projection in lexical scope |
| External tool, process spawn, network, git, real shell work | `command-result` with a certified adapter |
| Durable resource mutation | Outside current evaluated admission; see Section 13.4 |

Pure values stay in the lexical environment; they have no generated step,
private projection bundle or memo entry. Resume recomputes them while reusing
committed effect results. The historical flat-route `pure_projection` payload
limit and split-expression workarounds do not govern evaluated programs.

Pure evaluation fails closed on overflow, invalid operand types, division by
zero, float domain errors and non-finite results. See the numeric contract for
exact diagnostics and Section 2A for public evaluated evidence.

Routing is not generally proof. `(if (= status "READY") ...)` may choose a
branch, but it never makes union variant fields readable. Typed
`.variant` equality and inequality comparisons are the deliberate exception.

## 10. Pattern Matching And Variant Proof

Use `match` when directly deconstructing a union:

```lisp
(match implementation
  ((COMPLETED c)
    (record-completed
      :execution-report c.execution-report))

  ((BLOCKED b)
    (record-blocked
      :progress b.progress-report
      :class b.blocker-class
      :reason b.blocker-reason)))
```

Inside the `COMPLETED` arm, `c.execution-report` is available. Inside the
`BLOCKED` arm, `b.progress-report`, `b.blocker-class`, and
`b.blocker-reason` are available. The proof is arm-local.

Ordinary `if` and `cond` may establish the same branch-local
proof from a typed union discriminant:

```lisp
(if (= attempt.variant COMPLETED)
    (record-completed :execution-report attempt.execution-report)
    ...)

(cond
  ((= attempt.variant COMPLETED)
   (record-completed :execution-report attempt.execution-report))
  ((= attempt.variant BLOCKED)
   (record-blocked :progress attempt.progress-report)))
```

Each condition must resolve to exact `Bool`. Condition effects execute left to
right and at most once; `and` and `or` skip unselected operands. A `cond`
without `else` is accepted only when a pure statically true terminal or the
closed variant facts make its final false environment unreachable. The
compiler retains runtime `requires_variant` guards and resume-time proof
validation for narrowed field reads.

Ordinary scalar predicates and status mirrors remain proof-neutral:

```lisp
;; Bad: a status mirror does not prove the union discriminant
(if (= implementation.status "COMPLETED")
    implementation.execution-report
    ...)
```

Prefer `match` for exhaustive deconstruction; use typed discriminant `if` or
`cond` when branch control is clearer. Current evaluated composition evidence,
including nested native union values, is in
[`tests/test_workflow_evaluated_totality.py`](../tests/test_workflow_evaluated_totality.py).

### 10.1 A Step That May Be Unable To Answer

When a provider may be unable to do its task, give its result a variant that
says so, instead of leaving it to invent a value or fail the attempt:

```lisp
(defunion MoveOutcome
  (Moved (position String))
  (Blocked (reason String)))

(let* ((white (provider-result providers.white :prompt prompts.white
                :inputs (state.position) :returns MoveOutcome)))
  (match white
    ((Moved w) (continue (loop-state :like state :position w.position)))
    ((Blocked w)
      (done (variant GameOutcome Blocked :side "White" :reason w.reason)))))
```

`Blocked` is an ordinary committed result; the runtime does not retry it, and
`match` routes it to a typed outcome of the loop (here the workflow's own
`GameOutcome` union). Authored prompts carry no transport instructions, such as
result-file paths or environment variables: the runtime renders the delivery
contract for the transport it selects. The full example is
[`experiments/agent_chess/chess.orc`](../experiments/agent_chess/chess.orc).

## 11. Contexts And Derived State

These private context concepts remain useful for admitted helper composition.
They do not admit resource transitions, materialized views or reusable-state
helpers at 2.35/2.36; consult Section 2A before copying a library recipe.

High-level Lisp should derive state paths from private context and typed
resources, not from public path plumbing. Public workflow inputs are for caller
intent; runtime context is for allocation, checkpointing, idempotency, resume,
and provenance.

Common library/internal context records:

```lisp
(defrecord RunCtx
  (run-id RunId)
  (state-root Path.state-root)
  (artifact-root Path.artifact-root))

(defrecord PhaseCtx
  (run RunCtx)
  (phase-name Symbol)
  (state-root Path.state-root)
  (artifact-root Path.artifact-root))

(defrecord ItemCtx
  (run RunCtx)
  (item-id String)
  (state-root Path.state-root)
  (artifact-root Path.artifact-root)
  (ledger Path.state-existing))

(defrecord DrainCtx
  (run RunCtx)
  (state-root Path.state-root)
  (manifest Path.state-existing)
  (ledger Path.state-existing))
```

These records may appear in stdlib modules, reusable helper internals, low-level
fixtures, executable contracts, source maps, and Semantic IR. They should not
be exposed as ordinary public inputs for a promoted high-level workflow unless
the workflow is explicitly a low-level fixture or compatibility bridge.

When a promoted entry workflow omits one of these context parameters for an
internal reusable call, Workflow Lisp records that omission as private
executable-context metadata. Public authored inputs stay public; runtime-owned
context bindings, managed write roots, and historical compatibility-bridge values
stay off the public boundary.

### 11.1 Boundary Authority Classes

Classify every path-like boundary value of a parent-callable candidate by
authority before exposing it:

| Class | Meaning | Treatment |
| --- | --- | --- |
| `public_authored` | The caller genuinely chooses the value: steering doc, target design, explicit output root | Keep public |
| `compatibility_bridge` | Historical state/artifact path retained for a supported persisted consumer | Keep only while that consumer contract remains, labeled with a retirement route |
| `runtime_derived` | Derivable from run context, resource identity, or `StateLayout` | Bind internally; not a public input |
| `generated_internal` | Compiler/runtime-owned bundle, write root, temp, or sidecar | Allocate privately |
| `materialized_view` | Deterministic rendering of a typed value | Allocate as a view; never semantic authority |

If most of a workflow's inputs are bookkeeping paths, the boundary is
YAML-shaped: derive or hide the internals and keep only authored inputs plus
labeled bridges public. The classification taxonomy, census evidence, and
promotion gates are owned by
`docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`.

Use helpers:

```lisp
(phase-ctx ctx 'implementation)
(phase-target ctx "execution-report.md")
```

Use those helpers inside library or lower-level procedures that already receive
private context. At higher-level call sites, prefer domain calls that allow the
compiler/runtime to provide the context privately:

```lisp
(run-work-item item)
```

Avoid:

```text
"${inputs.state_root}/implementation_state.json"
"${inputs.state_root}/execution_report_path.txt"
"${inputs.state_root}/implementation_outcome_before"
```

Those paths may exist after lowering, but they should not be ordinary high-level
authoring concerns.

### 11.2 Path Management

Before adding a path field, decide who semantically owns that path:

| Path class | Examples | Authoring rule |
| --- | --- | --- |
| Public authored input | target design doc, baseline design doc, steering doc, explicit output root | Keep as a typed public input when the caller genuinely chooses it. |
| Source or context document | prompt context doc, design reference doc, check-command spec | Model as a typed path value or typed request field. |
| Provider/command result bundle | structured `provider-result` or `command-result` bundle | Let the runtime bind the output target and validate the declared bundle. |
| Generated internal path | write root, checkpoint path, temp path, result-bundle sidecar | Allocate through `StateLayout`; never expose as ordinary public input. |
| Public report or summary | drain summary, review report, operator-facing artifact | Prefer boundary publication policy or observability rendering over body plumbing. |
| Prompt rendering | provider prompt input text | Pass supported scalar, record, relpath, exact `Value`, closed union, or recursively renderer-admitted `List[T]` values in `:inputs`; use `:prompt-dependencies` when the provider also needs a relpath target's body. Other composite shapes require an implemented checked route. |
| Compatibility file | YAML-era pointer, selection bundle, legacy ledger view | Declare a labeled bridge with owner, source value, renderer/schema, and retirement condition. |
| Durable resource state | backlog item state, drain state, recovery state | Resource-transition semantics are outside evaluated admission; do not bypass that gap with arbitrary writes. |

Litmus test: if deleting the path field would not change the workflow's
semantic domain input or output, the path is probably private, generated,
runtime-derived, a materialized view, or a compatibility bridge. It should not
be ordinary authored data.

If the only way to compute a path is string concatenation such as
`"${inputs.state_root}/..."`, stop and classify the value first. The fix is
usually one of:

- move the value into a typed request record;
- derive it from private context through `StateLayout`;
- make it a provider/command structured-output target;
- publish it at the boundary;
- declare it as a compatibility bridge; or
- keep it behind a certified adapter if it is truly legacy protocol work.

## 12. Transitions Instead Of Gates

A gate asks: may I continue?

A transition says: given state `S` and event/output `E`, validate `E`, produce
`S'`, expose typed outputs, and route by explicit outcome.

Do not fix brittle gates by adding more gates. Replace gate-shaped logic with
typed outcomes and transitions.

Avoid:

- `(file-exists? path)`
- `(status-string-equals? path "APPROVED")`
- `(parse-report-line report "Review Decision:")`
- `(pointer-file-points-to? path)`
- `(mtime-newer-than? output phase-start)`
- `(recovery-gate ...)`

Prefer typed `match`, admitted provider/command results, and ordinary bounded
composition. State/resource effects remain governed by Section 2A; the
high-level helpers below have their own availability limits.

## 13. Standard High-Level Forms

This section describes high-level forms. Availability depends on current
frontend support and on the form having a reviewed lowering contract. A
standard-library form is safe authoring guidance only when it lowers through
visible generated statements, effects, state layout, proof behavior, and source
maps.

Treat these forms as stdlib authoring conveniences backed by generic `.orc`
composition, not opaque language builtins. The stdlib owns concrete helper
schemas and loop policy; the language/compiler owns generic typed dataflow,
effect visibility, source maps, and generated path handling.

Do not replace a missing or unsupported standard-library lowering with ad hoc
inline command text, report parsing, pointer choreography, or macro-generated
hidden effects. Either use the supported form, add a reviewed lowering
contract, or record a capability gap. The lower-level Core mapping remains a
compiler/runtime contract, not an alternate authored surface.

| Missing-form context | Required disposition |
| --- | --- |
| Historical migration evidence | `preserve_captured_baseline` |
| New authoring | `record_capability_gap` |
| New YAML/YML workaround | `prohibited` |

### 13.1 `run-provider-phase`

`run-provider-phase` is unavailable at targets 2.35/2.36 and refuses with
`closed_program_gap`. See the [phase helper contract](design/workflow_lisp_stdlib_lowering.md) for its
separate lowering and state semantics.

### 13.2 `review-revise-loop`

This ordinary stdlib composition is usable only when its selected hooks and
generated effects are admitted by the evaluated graph. Its context/publication
recipe is not a current copy target. The [frontend review-loop baseline](design/workflow_lisp_frontend_specification.md#27-review-revise-loop)
owns the promoted schemas; the original integration delta is historical; use [Section 13.7](#137-improve) for the
publicly exercised evaluated review/revise recipe.

### 13.3 `resume-or-start`

`resume-or-start` is unavailable at targets 2.35/2.36 and refuses with
`closed_program_gap`. See the [reusable-state helper contract](design/workflow_lisp_stdlib_lowering.md) for its
separate lowering and state semantics.

### 13.4 `resource-transition`

`resource-transition` is unavailable at targets 2.35/2.36 and refuses with
`closed_program_gap`. See the [resource transition contract](design/workflow_lisp_frontend_specification.md) for its
separate lowering and state semantics.

### 13.5 `finalize-selected-item`

`finalize-selected-item` is unavailable at targets 2.35/2.36 and refuses with
`closed_program_gap`. See the [selected-item finalizer contract](design/workflow_lisp_stdlib_lowering.md) for its
separate lowering and state semantics.

### 13.6 `backlog-drain`

The historical context/resource-based drain recipe is not an evaluated-target
copy target: resource transitions, reusable-state effects and materialized
views remain unavailable at 2.35/2.36. Ordinary bounded composition is governed
by Section 2A. The [drain-authoring design](design/workflow_lisp_runtime_native_drain_authoring.md) owns the separate
family's intended responsibilities and migration evidence.

### 13.7 `improve`

`std/improve` reviews and revises a typed record under a bounded round limit,
then returns the candidate with APPROVED, BLOCKED or EXHAUSTED. Use that returned
candidate downstream; EXHAUSTED may contain an unreviewed final revision.
The [library reference](lisp_library_reference.md#review-and-revise-with-stdimprove)
owns the target-specific APIs, complete examples, dependencies, operating route
and composition limits. Choose review/revise versus generating alternatives
using the [task chooser](lisp_library_reference.md#choose-by-task).

<a id="target-236-local-hooks"></a>

#### Target 2.39 local hooks

See the [complete local-hook example](lisp_library_reference.md#target-239-local-hooks)
and its inference/capture limits. The hooks use the W3 API introduced at 2.36;
the caller uses 2.39 procedure restrictions and imports retained 2.35 library
definitions.

#### Compile, run and resume the maintained proposal

See the [proposal operating route](lisp_library_reference.md#compile-run-and-resume-the-maintained-proposal),
including the workspace-owned launcher requirement.

#### Target 2.35 explicit inputs

See the [explicit-input API](lisp_library_reference.md#target-235-explicit-inputs).

#### `improve` rejections

See the [rejections and remaining composition limits](lisp_library_reference.md#improve-rejections).

## 14. Provider Prompt Guidance

Prompts should focus on the provider's task.

Include:

- objective;
- scope boundaries;
- domain-specific completion criteria;
- required structured result shape;
- required human-facing report, if any;
- forbidden shortcuts;
- evidence expectations from the agent's point of view.

Usually avoid:

- orchestrator internals;
- pointer file theory;
- snapshot mechanics;
- variant proof mechanics;
- runtime state path explanations;
- duplicated generated output contracts;
- result delivery instructions, such as result-file paths or
  `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`: the runtime renders the delivery contract
  for the transport it selected (§10.1);
- broad ambient doc globs;
- instructions to echo session IDs or pointer paths.

### Result Guidance

Use plain return types when the type and field names are sufficient. Add
guidance at the narrowest authored return occurrence when the producer needs
semantic help:

```lisp
:returns
  (result Bool
    :description "True only when no blocking findings remain."
    :format-hint "Write a JSON boolean."
    :example true)
```

Payload fields accept the same keys after the field type. `:example` is a
typed pure constant; for path types it is checked for path safety but the
target need not exist during compilation. Schema inclusion, imports, and
generic specialization preserve field guidance without changing type identity.

Exact `Value` is the opaque-type exception: it accepts `:description` and
`:format-hint`, but rejects `:example` because ordinary narrower literals are
not implicitly `Value`. The provider contract describes one JSON document
root; the text guidance never adds fields, an envelope, or narrower runtime
validation.

Provider/command occurrence guidance reaches the generated effect contract and
provider prompt. A `defworkflow` or effectful `defproc` return annotation is
overall callable guidance: it becomes top-level `result_guidance`, survives
shared IR, and is deliberately not injected into a provider prompt. Neither
form changes runtime validation, artifacts, routing, checkpoints, or resume.

Build a typed prompt-input record and pass that record to `:inputs`. This keeps
provider inputs named, typed, and separate from runtime bookkeeping:

```lisp
(defrecord ImplementationRequest
  (target-design TargetDesignDoc)
  (baseline-design BaselineDesignDoc)
  (approved-plan PlanDoc)
  (checks CheckSpec)
  (output-targets ImplementationOutputTargets))

(provider-result providers.execute
  :prompt prompts.implementation.execute
  :inputs request
  :returns ImplementationAttempt)
```

For supported scalar, record, relpath, exact `Value`,
closed union, and recursively renderer-admitted `List[T]` bindings, the runtime renders each
value at the provider prompt seam through the unique registered default.
Missing, unknown, shape-incompatible, or ambiguous renderer selection fails
before provider launch. The provider output still comes only from the
declared structured result contract.

Prompt rendering does not grant source-level variant proof. Use only the
renderer-admitted input shapes and keep unsupported composites behind a
separately implemented checked route; do not assume a historical phase
materialization fallback exists on the evaluated route.

Flat input lists are fine for small calls:

```lisp
(provider-result providers.execute
  :prompt prompts.implementation.execute
  :inputs (inputs.design inputs.plan)
  :returns ImplementationAttempt)
```

then the provider must produce `ImplementationAttempt`. The report explains the
work; the union value controls routing.

Do not put generated report targets, state roots, checkpoint paths, or
compatibility pointer paths in provider inputs merely so a prompt can tell the
provider where runtime-owned files live. Output targets belong in typed target
records, provider structured-output bindings, publication policy, bridge
metadata, or lower-level compatibility adapters according to their authority
class.

## 15. Operational Notes

The Lisp guide should not become a catalog of every provider/runtime feature.
Put detailed operational mechanics in provider/runtime docs. Keep these rules
visible:

- Provider aliases are typed values. Pass provider roles through typed inputs or
  provider records.
- Sessions are runtime-owned. Do not ask providers to echo, store, or restate
  session IDs in prompt content.
- Managed jobs remain runtime-managed. Do not hand-author guard wrappers,
  ad hoc audit paths, manual recovery steps, shell counters, or job
  resurrection scripts unless they are compatibility adapters with declared
  contracts and fixtures.
- Use explicit [candidate generation and selection](lisp_library_reference.md#generate-candidates-and-select)
  when comparing alternatives. The maintained example returns a typed selection;
  it requires separate clones and does not merge the winner. Declare evaluator
  evidence in domain result types when downstream policy needs it.

## 16. Reuse And Modularity

Prefer narrow public workflows over reusable procedures and pure helpers rather
than one-off monoliths.

Before drafting a new unit, check the workflow and procedure libraries for:

- existing public phase boundary or internal phase procedure;
- existing design/plan/implementation stack;
- existing review loop;
- existing selected-item runner;
- existing adapter;
- existing result type.

Caller-visible outputs should come only through the declared return type.

Pass narrow cross-boundary data:

- typed inputs;
- typed context;
- typed provider roles;
- typed result records/unions.

Avoid:

- ambient globals;
- workspace-wide file globs;
- prompt-text routing;
- caller/callee provider-template merging;
- out-of-band pointer files.

Use typed `WorkflowRef[...]` parameters only for static orchestration strategies
that abstract over whole public workflow boundaries whose independent identity
matters. Workflow refs resolve at compile/module-link time, not by runtime
dynamic loading. Compile-time formal WorkflowRef/ProcRef parameters are
supported and erased. References cannot become runtime-bound public workflow
input contracts or cross outputs, records, artifacts, provider or command
results, or state. Prefer `ProcRef[...]` for internal behavior.

Use `ProcRef[...]` for compile-time procedure composition: typed procedure
parameters, explicit `(proc-ref name)` literals, keyword-only `bind-proc`
partial application, forwarding through `ProcRef[...]` parameters, and lexical
call-through after residual specialization. Keep ProcRef values on the
compile-time side of the boundary: do not route them through workflow outputs,
records, unions, artifacts, provider results, command results, ledgers, or
loop-carried runtime state, and do not model provider-selected, command-
produced, or dynamically dispatched procedures.

## 17. Loops

Use `loop/recur` for bounded typed iteration and the exercised `std/improve`
recipe for review/revise loops. A stdlib helper must compose only effects
admitted by the selected evaluated target.

Every loop must have:

- bounded iteration or explicit termination proof;
- typed loop state;
- typed terminal result;
- clear exhaustion behavior;
- no shell-managed counters;
- no raw back-edge hidden in command text.

Exhaustion should be a typed result when it is part of workflow semantics.

Loop state carries typed values, not file-path authority. Counters are `Int`
fields updated in-language; statuses and reasons are typed values; durable
state is a typed result or resource reference, not a `state/...` path
threaded through every iteration and re-read from disk. The pure-expression
surface makes the value-carrying shape direct:

```lisp
(loop/recur
  :max 6
  :state (record CounterState
           :count 0
           :label "seed")
  (fn (state)
    (if (< state.count 3)
      (continue
        (record-update state
          :count (+ state.count 1)
          :label "tick"))
      (done
        (record CounterResult
          :count state.count
          :label state.label)))))
```

### 17.1 `loop-state`

Use `loop-state` when `loop/recur` needs a typed local carrier but the carrier
does not deserve a top-level reusable `defrecord`.

```lisp
(loop/recur
  :max 2
  :state (loop-state
           (report ReviewReportPath report_path)
           (done Bool false))
  (fn (current)
    (if current.done
      (done current.report)
      (continue (loop-state :like current :done true)))))
```

`loop-state` rules:

- carriers are local and compile-time-only; the generated carrier name is not a
  public runtime contract;
- seed fields use `(field-name TypeName value)` and updates use
  `(loop-state :like existing :field replacement ...)`;
- use `loop-state` as the author-facing way to keep typed loop-frame state
  without introducing a generic top-level record just for one loop;
- runtime-forbidden values cannot be carried across the loop boundary,
  including `ProcRef[...]`, `WorkflowRef[...]`, provider refs, prompt refs, and
  `Json`.

### 17.2 Bounded list traversal

The total list operators are `list/empty?`, `list/head`, `list/rest`,
`list/append` and `list/length`, with `(list ...)` construction, pure `list/map`
and bounded serial `list/map-effect`. Transportable records and unions may be
list elements; source-level variant field reads still require proof. Eligible
lists can also be loop state. `path/join-under` constructs safe paths below a
declared root.

`list/map-effect` requires an explicit `:max` and one admitted effect in its
body; its source and body arguments remain pure. Pure `list/map` bodies remain
effect-free. Indexing, filtering, folding, general ProcRef mapping and
unbounded traversal are outside the current surface; parallel `list/map-effect`
requires target 2.37 and remains bounded Phase 5 work, not copy-safe guidance
(Section 2A). Traversal does
not grant prompt visibility: a provider input still needs an admitted renderer.
See [evaluated totality evidence](../tests/test_workflow_evaluated_totality.py)
for record/union/list transport and pure-context refusals.

## 18. Effects

Procedural abstraction must not hide effects.

```lisp
(defworkflow implementation/run
  ((ctx PhaseCtx)
   (inputs ImplementationInputs)
   (providers ImplementationProviders))
  -> ImplementationResult

  :effects
    ((reads inputs.design inputs.plan inputs.check-commands)
     (uses-provider providers.execute providers.review providers.fix)
     (writes Path.execution-report)
     (writes Path.checks-report)
     (writes Path.review-report)
     (updates-state ctx))

  ...)
```

Effect kinds include:

- `reads`
- `writes`
- `moves`
- `updates-ledger`
- `updates-state`
- `uses-provider`
- `executes-command`
- `calls-workflow`
- `captures-snapshot`
- `commits-bundle`
- `publishes`
- `materializes-artifact`

If a procedure's effects are hard to explain, the procedure is probably too
broad.

The evaluated route records admitted effects and their typed results in the
memo. Pure computation is not an effect or a generated step. Provider prompts
render values at their consumer seam; reports and dashboard render derived
views. Explicit `materialize-view` and boundary publication machinery from
older resource recipes remain outside current evaluated admission.

## 19. Source Maps And Debugging

Debug high-level `.orc` in this order.

First, look at the `.orc` source diagnostic:

```text
variant_ref_unproved
at workflows/neurips/implementation.orc:42:9

field: attempt.execution-report
reason: field is available only for ImplementationAttempt.COMPLETED
hint: access it inside match
```

Located diagnostics retain authored source provenance, including file,
line/column and the refused form. For evaluated compilation inspect the
checked `closed_program.json` and `manifest.json`; at run time inspect
`run.json`, `memo.jsonl`, the derived `state.json`, attempt requests,
stdout/stderr and validated result bundles. The complete lifecycle recipe and
[State contract](../specs/state.md#evaluated-execution-persistence-profile-target-235)
own their exact layout and authority.

Older Core/Semantic/Executable IR and `expanded.debug.yaml` are retained
historical projections/read formats. Their emitters/executors are retired;
inspect current checked artifacts and memo evidence rather than requesting an
old flat build.

## 20. Lints

The frontend and lint tools should warn on brittle authoring patterns.

| Code smell | Bad pattern | Preferred pattern |
| --- | --- | --- |
| `semantic_field_extracted_from_report` | Parse a markdown line for a decision or blocker | Structured provider/command result |
| `pointer_used_as_semantic_authority` | Publish a pointer file path as the value | Publish the typed artifact value |
| `variant_output_without_variant_specific_fields` | Union variants with no fields | Record plus enum |
| `recovery_gate_without_canonical_state` | File-existence recovery gate | Public memo-backed resume; reusable-state helper unavailable |
| `resource_move_without_transition` | Shell move plus hidden ledger update | Record the resource-effect gap; Section 13.4 |
| `manual_when_requires_variant_pair` | Manual condition/proof pairing | `match`, or typed discriminant `if`/`cond` |
| `manual_state_path` | Hand-built state path | Context helper such as `with-phase` |
| `command_step_for_pure_computation` | Python/`jq` step that only compares, counts, defaults, or formats | Closed pure-expression surface / typed projection (Section 9A) |
| `loop_state_carries_path_authority` | Loop state threading state-file paths between iterations | Typed value state plus `record-update` (Section 17) |
| `low_level_state_path_in_high_level_module` | `state/...` path types on a high-level public boundary | Derived context, private bindings, or a labeled compatibility bridge (Section 11.1) |

<a id="21-historical-yaml-to-core-translation-surfaces"></a>
<a id="22-historical-migration-from-yaml-to-orc"></a>
<a id="23-example-implementation-phase"></a>
<a id="24-example-selected-backlog-item"></a>
<a id="25-example-top-level-backlog-drain"></a>

The original YAML/Core translation map, migration stages and resource/drain examples are historical. They do not supply admitted effects or new-work recipes; current typed composition and public examples are above. See the [preserved record](reports/documentation-history/docs-lisp_workflow_drafting_guide-history.md#historical-operational-record-2).

## 26. Prompt Examples

Good implementation prompt framing:

```text
Implement the plan using the current checkout.

Inputs:
- design
- plan

You must return one structured outcome:

COMPLETED:
  - execution_report: path to the implementation execution report

BLOCKED:
  - progress_report: path to the progress/blocker report
  - blocker_class: one of the declared blocker classes
  - blocker_reason: concise reason

Write any human-facing report to the path provided by the structured output
contract. The structured result controls workflow routing.
```

Bad implementation prompt framing:

```text
Write a report. Somewhere in the report include:

Blocker Class:
Review Decision:
Execution Report Path:

The workflow will parse these lines later.
```

This makes prose the semantic state. Avoid it.

## 27. Drafting Checklist

Before running a new `.orc` workflow, confirm:

| Area | Check |
| --- | --- |
| Frontend choice | This belongs in `.orc`; there is no alternate fresh authored frontend. |
| Types | Every boundary has its actual transportable type; no wrapper is required. Exact `Value` remains opaque. Typed result guidance does not alter validation. |
| Paths | Path contracts are reusable `defpath` definitions. |
| Authority | Structured bundles/artifacts are authority; reports are views. |
| Providers | Portable composed calls return validated structured state. Sessions, context capture, phased delivery, supervision and peer groups are unavailable at evaluated targets. |
| Commands | Command semantics use `command-result` or certified adapters. |
| Reports | No markdown report is parsed for semantic state in new high-level code. |
| Pointers | Pointer files are not treated as artifact values. |
| Variants | Variant-specific fields are used only inside a proof-bearing `match` arm or typed discriminant branch. |
| State | The memo owns committed effects; run state and reports are derived views. Resource/reusable-state helpers remain outside current admission. |
| Effects | Provider, command, write, move, ledger, state, and call effects are visible. |
| Reuse | Durable public run/resume/invocation/publication identity is a `defworkflow`; repeated internal effectful behavior is a `defproc`; pure behavior is a `defun`. |
| Gates | Gates have been replaced by typed outcomes or transitions where possible. |
| Prompts | Fully discharge `defprompt` slots without duplicating its input/dependency/result contract. `:path :out` may own one required UTF-8 file alongside the structured result. |
| Evaluation | Compile a checked closed program; declared command closures and typed input contracts match the intended execution. |
| Diagnostics | Errors map back to useful `.orc` source forms. |
| Metrics | Authored size and brittle-pattern count improve over the YAML baseline. |

## 28. Review Checklist

When reviewing a `.orc` workflow, look for these failure modes.

### YAML-Shaped Lisp

Could this code be mechanically converted back to YAML without losing anything?
If yes, the Lisp frontend is probably not being used well.

### Hidden Command Semantics

Look for inline Python, inline Bash, subprocess chains, `jq` gates, report
parsers, pointer writers, and ledger updates hidden inside command text. Require
`command-result`, a certified adapter, or a runtime-native effect.

### Manual State Choreography

Look for manual state file paths, snapshot names, candidate paths, commit
bundles, and temporary paths. Require contexts or standard-library forms.

### Fake Outcome Types

Look for unions whose variants do not have variant-specific fields. Require a
record with an enum field instead.

### Report-As-State

Look for line-prefix extraction from markdown. Require structured
provider/command results.

### Pointer-As-Authority

Look for pointer file paths being published or passed as semantic values.
Require artifact values.

### Unproved Variant Access

Look for variant-specific fields outside a proof-bearing context. Require
`match` or a typed `.variant` equality or inequality branch.

## 29. Persisted Legacy And Historical Compatibility Policy

Persisted legacy runs and historical evidence may retain YAML-era path names,
shell glue, report parsing, and pointer conventions. Fresh workflows cannot
retain authored YAML and should not introduce those mechanics through `.orc`.

A legacy adapter should declare:

- why it exists;
- what behavior it preserves;
- what structured result it returns;
- what effects it has;
- which fixtures prove it;
- when it can be retired.

Compatibility does not imply authority. A legacy script may still need pointer
files or markdown reports. That does not make those files semantic authority.
The `.orc` boundary should expose typed values.

<a id="30-low-level-core-surfaces"></a>

The low-level flat/Core inventory is historical format/debugging context, not an available emitter or alternate authoring route. See the [preserved record](reports/documentation-history/docs-lisp_workflow_drafting_guide-history.md#historical-operational-record-2).

## 31. Quick Translation Table

| Old authoring thought | New authoring thought |
| --- | --- |
| "I need a gate." | "What typed outcome or transition proves this?" |
| "I need to parse the report." | "The provider/command should return structured state." |
| "I need a pointer file." | "What artifact value does the downstream step need?" |
| "I need when status == X." | "This is probably a match over a union." |
| "I need a recovery step." | "Use public `resume` to reuse committed effects; reusable-state helpers are unavailable here." |
| "I need to move a file and update the ledger." | "Resource transitions are outside evaluated admission; record the gap." |
| "I need a custom review loop." | "Can the exercised `std/improve` composition express it?" |
| "I need to select/run/gap/repeat." | "Use bounded admitted composition; the historical resource drain recipe is unavailable." |
| "I need a tiny Python helper to compare, count, or format." | "This is pure computation; use the operator surface and typed projection." |
| "I need to write a lot of target paths." | "These should derive from context or typed target schemas." |
| "I need an external prompt plus separately repeated inputs, dependencies, and return guidance." | "Can one `defprompt` own the complete fill and result contract?" |
| "I need prompt text and runtime validation to agree on a required report path." | "Can one `:path :out` slot own both while the prompt keeps one structured result?" |
| "`expanded.debug.yaml` looks unusual." | "It is a historical projection. Inspect the checked artifact, run header, memo and authored diagnostic provenance for current runs." |

## 32. Minimal Safe Subset

For conservative examples, tutorials, and compatibility fixtures, prefer this
small subset before introducing procedures, macros, loops, or library forms
(the `defmodule`/`export` header is mandatory in every module):

- `defmodule` and `export`
- `defenum`
- `defpath`
- `defrecord`
- `defunion`
- `defworkflow`
- `let*`
- `match`
- `call`
- `provider-result`
- `command-result`

Context/library helpers have independent effect admission; they are not part
of this conservative runnable subset merely because their types import.

Minimal syntax example (provider/prompt extern bindings are supplied by the
caller; use the complete lifecycle recipe for an executable package):

```lisp
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.35")

  (defmodule minimal_subset)
  (export implementation-execute)

  (defenum BlockerClass
    missing_resource
    unavailable_hardware
    roadmap_conflict
    external_dependency_outside_authority
    user_decision_required
    unrecoverable_after_fix_attempt)

  (defpath WorkReport
    :kind relpath
    :under "artifacts/work"
    :must-exist true)

  (defunion ImplementationAttempt
    (COMPLETED
      (execution-report WorkReport))
    (BLOCKED
      (progress-report WorkReport)
      (blocker-class BlockerClass)))

  (defworkflow implementation-execute
    ((design WorkReport)
     (plan WorkReport))
    -> WorkReport

    (let* ((attempt
             (provider-result providers.execute
               :prompt prompts.implementation.execute
               :inputs (design plan)
               :returns ImplementationAttempt)))

      (match attempt
        ((COMPLETED c)
          c.execution-report)

        ((BLOCKED b)
          b.progress-report)))))
```

Do not use forms from an active design tranche in ordinary authoring examples
until the implementation and fixtures have landed.

The [previous broad design reading list](reports/documentation-history/docs-lisp_workflow_drafting_guide-history.md#historical-operational-record-1)
is historical routing provenance; use current focused owners at the start of this guide.

## 33. Final Rule

Author typed compositions over admitted effects, lexical values, explicit
outcomes and bounded control. Keep runtime bookkeeping and report parsing out
of domain code. A helper's existence at another target does not make its
resource, publication or session effects available on the evaluated route.
