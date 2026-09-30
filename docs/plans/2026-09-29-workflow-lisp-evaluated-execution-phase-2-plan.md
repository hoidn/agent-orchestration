# Workflow Lisp Evaluated Execution, Phase 2: The Closed Program Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` to execute this plan task by
> task, with `superpowers:test-driven-development` for every behaviour change
> and `superpowers:verification-before-completion` before any completion
> claim. One worktree per task. Tasks of one group touch disjoint files and
> may run in parallel only after their listed prerequisites are merged. Use
> the repository role assignments: Implementation Luna 6 xhigh, Review Sol 6
> high, Design Astra 6 xhigh, Planning Astra 6 high. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The compiler produces, for a program at the evaluated execution
target, the closed program that Phase 3's evaluator will run: whole,
calculus-only, with complete effect nodes, a site table, a checked form,
provenance outside identity, and a digest that is the program's identity.

**Architecture:** An evaluated-entry compilation stops after typecheck
throughout its source graph, including older imports, and never lowers to
steps. A new package `orchestrator/workflow_lisp/closed/`
takes the typed program, elaborates every reachable definition once with the
compiler's own elaborator and normal-form pass (both changed at the new target
only), and translates the result into a table of plain JSON definitions. The
elaborator is changed where a property of the closed program cannot be
obtained after it (callee bodies, effectful arguments, `done` values,
`continue` targets, `phase-target`); everything else is translation. The
flat route and every target that exists today are untouched: byte-identical
build artifacts are the evidence.

**Tech Stack:** Python, the Workflow Lisp typechecker, the WCC elaborator
(`wcc/elaborate.py`) and normal form (`wcc/anf.py`), the pure expression
catalog (`orchestrator/workflow/pure_expr.py`), canonical JSON, pytest.

**Spec:** [evaluated execution](../design/workflow_lisp_evaluated_execution.md),
sections 1.1 (`closed_program_gap`), 4 (P1 to P7, the table of definitions,
the constructs, X1 to X4), 6 (I1 to I7), 7.3 (C1 for supplied and injected command bindings), 12
(codes) and 13 (targets). Facts: the
[execution facts](../reports/2026-09-29-workflow-lisp-execution-facts.md)
(A.1 to A.5). Evidence and measured sizes: the
[gate report](../reports/2026-09-29-evaluated-execution-spike.md), sections
4 and 7. The prototype of every task is the spike under
`experiments/evaluated_execution_spike/` (`closed.py`, `closed_effects.py`,
`sites.py`, `table.py`, `repairs.py`, `frontend.py`). Read it; do not import
it. The spike is not wired in and nothing of it is deleted by this plan.

---

## Status, Authorities And Scope

- Parent plan: [evaluated execution plan](2026-09-29-workflow-lisp-evaluated-execution-plan.md),
  Phase 2 (milestones P1 to P7). Entry condition: gate G1, decided
  2026-09-29. Governing revisions: design commits `181e4ed9` and
  `9fa10443`, reconciled with all twelve independent Phase 2 review findings
  and the follow-up builtin-closure/recovery contracts. The implementation baseline is the
  actual clean base recorded before Task 1; `613993ad` is historical Phase 0
  evidence, not this revision's comparison base.
- The owner selected **2.35** on 2026-09-30, closing parent-plan decision 6
  after reviewing this plan. `PHASE2_BASE` is
  `2e4c7a653d74c06e24c15c284662e5914abd5576`, the integrated Phase 0 head.
  Task 1 registers the target in one gate constant; every later task and
  every fixture reads the number from that constant, never as a literal.
- In scope: the compiler's output at the new target and the manifest field
  `closure`; both command boundary kinds; portable composed providers with
  `asset_file`, `input_file` and all admitted `defprompt` slots; procedure and
  workflow calls including value/reference bindings, `bind-proc` captures and
  bounded `let-proc`; path-mode run references. Out of scope, Phase 3 and later: the evaluator, the memo,
  performers, coordinators, views, `run` and `resume` at the new target,
  typed input documents, `par-map`.
- Phase 2 does not make the new target runnable. `orchestrator run` and
  `orchestrator resume` refuse a program at the new target with
  `evaluated_execution_unavailable` (Task 1) until Phase 3 replaces the
  refusal with the evaluator's entry. `orchestrator compile` at the new
  target writes the closed program (Task 9).
- Two experiments run beside this plan and are not tasks of it: the owner's
  coordinator experiment (parent plan, decision 5) and the equality of the
  compiler's `PhaseCtx` and `phase-target` values with the present route's
  (design §19, item 4; open item of this plan).

## Global Constraints

Every task's requirements include these lines.

- Targets that exist today (2.34 and older) accept and lower exactly what
  they do at the commit the task starts from. Evidence: build the named
  programs at the base and at the head, with the program and the orchestrator
  package each at one fixed path and `PYTHONHASHSEED=0`; compare every build
  artifact byte by byte (the method of Task 0 of Phase 0: `git archive` of
  the base into a scratch directory, `python -m orchestrator compile` with
  every `--emit-*` flag, `diff -r` on the emitted files and on
  `.orchestrate/build/<key>/`).
- No generated identity introduced by this plan contains a source-file path,
  source position or `repr` of a type. Authored semantic paths (prompt
  bindings, run-ref sources, closure declarations and type roots) remain
  program content; explicitly absolute declarations stay location-bound. `repr(TypeRef)` never enters a name or a digest of
  the closed program (execution facts A.5).
- Every refusal has a code and a source location, and prints the value it
  refused and the limit it applied.
- Tests assert through the public compile entry (`compile_typed_program`,
  `build_closed_program`, `build_closed_program_bundle`, or
  `python -m orchestrator compile`): the closed program's content, sites,
  digests, and refusals by code and location. No test asserts prose or prompt
  text.
- No broad or full-suite test run while other agents share the machine.
  Narrow selectors, one module at a time, serial, with
  `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$PWD python -m pytest -q -p no:cacheprovider --basetemp=<scratch>/pytest`.
  One full run at the phase closeout, alone, in tmux.
- Reuse the existing signature, effect-summary, catalog, source-read and
  descriptor owners. Add no generic signature abstraction, fake validated
  bundle or extra compatibility layer. Keep the existing small `closed/`
  file responsibilities below; split only when concrete code needs it, not
  to satisfy arbitrary line or complexity limits. An admitted form that
  cannot be closed is a compiler defect to repair, never an extra release gap.
- Reviews record every finding. Only Critical evidence of observed silent
  wrong results, data loss or writes outside the workspace blocks the owner's
  review/merge gate; other findings are handled and recorded. Failing checks
  are repaired, not relabeled acceptable. Scope changes still need an
  explicit owner/design decision.
- Commit by pathspec (`git commit -m "<message>" -- <paths>`), after staging
  the task's created/changed files. Commit messages carry no tool
  or assistant attribution.
- The spike under `experiments/evaluated_execution_spike/` is read as the
  prototype and never imported by production code or by this plan's tests.
  Test fixtures needed from `tests/experiments/fixtures/evaluated_execution_spike/`
  are copied under `tests/fixtures/workflow_lisp/closed_program/`.

## Review Focus

Five input classes most likely to bite, each pinned by a test in the task
that owns the code.

1. One procedure called from three arms of one `match` inside a loop has
   one local `perform` site in its definition and three call frames, each
   with `<binder>=<callee>` and `loop:<param>[*]`. Moving the loop into a
   called workflow preserves that separation; calls never add site rows. Task 5 tests `arms_in_loop.orc`; Task
   4 tests the table form gives one definition for the callee.
2. A program moved to another path, and the orchestrator package moved to
   another path, must give the same sites and the same program digest; the
   artifact's provenance may differ. Task 7 tests provenance and digest on
   hand-written trees; Task 9 tests both moves through public compilation,
   including package relocation in a subprocess, on a specialized imported callee
   (`if_in_hook.orc`), whose names digest `repr(TypeRef)` today.
3. A manifest without `closure` must be refused at the new target with
   `command_boundary_closure_missing` naming the boundary and the manifest
   path, before any elaboration; at 2.34 the same manifest must build the
   artifacts it builds today. Task 4 tests the refusal in process, Task 9 at
   the manifest path, Task 7 the unchanged build at 2.34.
4. A form outside the first release (`materialize-view`,
   `resource-transition`, `trial`, `request-input`, a phased or supervised
   provider, a provider with `:capture-context`, a bundle-mode `run-ref`)
   must be refused with `closed_program_gap` at the form's own location,
   with the form named, and never as `compiler_defect`. Task 8 tests each
   form; Task 10 shows it on the corpus.
5. Two builds of one source, at two paths, with different `@` provenance in
   every node, must give one digest; and a tampered operator payload in the
   artifact must be refused when the artifact is read back. Task 7 tests
   both.

---

## The Closed Program's Form

Every task from 4 on reads and writes this schema. Code excerpts below
omit repeated typed/provenance fields for readability; actual fixtures must
fill every field required here and pass `validate`. It is the contract between
tasks; a task that needs another key adds it here first.

### The program

```json
{
  "schema": "workflow-lisp/closed-program/1",
  "representation": "table/1",
  "target": "<OWNER_SELECTED_TARGET>",
  "entry": "grt/entry::run",
  "params": [["seed", {"kind": "primitive", "name": "Int"}]],
  "defaults": {"seed": 1},
  "result": {"kind": "record", "name": "grt/entry::Box", "fields": [...]},
  "body": <body>,
  "types": {"grt/entry::Box": <canonical nominal descriptor>},
  "configuration": {"commands": <all canonical command bindings>, "providers": <all resolved provider bindings>, "prompts": <all resolved prompt bindings>},
  "definitions": {"<canonical callee name>": {"key": <canonical definition tuple>, "params": [["n", <descriptor>]], "result": <descriptor>, "body": <body>}},
  "sites": [["grt/entry::fetch", "#1"]]
}
```

- `params` lists the entry's declared parameters, hidden context parameters
  excluded (they are bound in the body, X1). `defaults` holds each declared
  default as its normalized value. Type descriptors are the compiler's
  normalized descriptor shapes, recursively canonicalized by Task 6. The
  existing descriptor builder alone is insufficient: private nominals also
  require `module::Name`. `types` holds the canonical definitions of every
  reachable nominal, including private and generated result types; all uses
  must match it. No source path is included.
- `definitions` holds one entry per canonical callee name (§4.2), procedures
  and called workflows alike. A body is stored once.
- `sites` is the site table (P4): one `[definition, local path]` per
  `perform`, entry first then definitions in first-call order. Call frames
  stay on call nodes. `configuration` contains every parsed manifest binding
  (including unused entries) and compiler-injected bindings used by the
  program, normalized using the same rules as in-memory bindings; provenance and raw manifest bytes are excluded. Its semantic
  content enters `program_digest`, not just the build-cache key.

### Body nodes

| `k` | Keys | Rule |
| --- | --- | --- |
| `let` | `name`, `value` (a bound value), `body` | sequencing |
| `halt` | `value` | result of the definition, or of a `block` |
| `if` | `cond` (value), `then`, `else` (bodies) | strict `Bool` |
| `case` | `subject` (value), `arms`: `[{variant, bind, body}]` | variant elimination |
| `join` | `name`, `params` (`[[name, descriptor]]`), `result` (descriptor), `body`, `cont` | second-class continuation; a `halt` reached in `body` is the join's value (§4.3) |
| `jump` | `join`, `args` (values) | |
| `loop` | `name`, `param`, `state_type`, `result` (descriptors), `budget` (value), `init` (value), `body`, `exhausted` (body or `null`), `code` | bounded iteration; `code` is the exhaustion diagnostic code |
| `continue` | `loop`, `args` (values) | names the loop it is in |
| `done` | `value` | |

### Bound values (the `value` of a `let`)

| `k` | Keys | Rule |
| --- | --- | --- |
| `perform` | `class`, `result` (descriptor), `repeat` (`"rerun"` or `"never"`), `site` (set by the site walker), and the class's keys below | one effect |
| `call` | `callee` (canonical name), `args` (values), `type` (result descriptor), `frame` (set by the site walker when the callee performs an effect) | evaluation of a definition's body (§9.2) |
| a value | | |

Effect classes of the first release (§1.1, §9.2):

| `class` | Keys |
| --- | --- |
| `command` | `boundary`, `command` (stable tokens), `closure` (canonical `[{base, path}]` rows, C1; base is `workspace`, `absolute` or `package:orchestrator`), `contract` (`{kind, payload}` without a `path`), and either `argv` (values) or `document` (`[[transport_key, value]]` in signature order, for a certified adapter) |
| `provider` | `provider` (provider id), `prompt` (`{"source_kind": "asset_file" or "input_file", "path": "<exact bound path>", "asset_base": "<logical entry directory>"}`; `asset_base` only for asset lookup, or `{"template": "<text>", "fills": <ordered typed slot rows>}`), `inputs` (`[[name, renderer_id, value]]`, named as lowering names typed prompt inputs), `dependencies` (`{required: [values], optional: [values], position, instruction}` or `null`), `policy` (`{model, effort, delivery, materialization_attempts, timeout_sec}`, each present only when declared, as values), `contract` |
| `run_ref` | `config` (base64 of `encode_run_ref_static_config`, path mode only, inputs bound as the references `inputs.<name>`, K7), `inputs` (`[[name, value]]`) |

A workflow `call` is not a `perform`: it is a `call` node whose callee is the
workflow's canonical name (§9.2, "a call is evaluation").

### Values

| `k` | Keys | Rule |
| --- | --- | --- |
| `lit` | `v`, `type` (descriptor) | literal; a variant tag is a literal |
| `name` | `n` | |
| `field` | `base` (value), `path` (field names) | |
| `record` | `type` (descriptor), `fields` (`[[name, value]]`) | |
| `inject` | `type` (descriptor), `variant`, `fields` | |
| `op` | `payload` (a pure catalog payload, `pure_expr_schema_version` 2, bindings `a0..an`), `args` (values) | one catalog operator; `record_update`, `list_nonempty_head` and `path_join_under` are catalog node kinds |
| `select` | `cond`, `then`, `else`, each arm `{prefix: [{name, value}], value}` | conditional value |
| `list` | `items` (values), `type` (descriptor) | |
| `list_map` | `binder`, `source` (value), `body` (value), `type` (descriptor of the result list) | `list/map` with a pure body; the body reads `binder` as a name |
| `path_join` | `base` (value), `child` (`lit`), `type` (path descriptor) | X3 for a generic `PhaseCtx`: the base path joined with a literal child, under the descriptor's root |
| `block` | `body` | a body evaluated for its value (§4.3) |
| `context` | `field` (`"run-id"`) | a value the run supplies (X1) |
| `result_path` | `n` (the binder of a provider effect), `type` (path descriptor) | the committed attempt's result file (X4) |

### Type facts and prompt slot rows

Every value has one derivable type. Literal/list nodes carry `type` because
empty lists, numeric kinds, enums and refined paths cannot always be inferred
from JSON alone; `name` and `field` derive it from the typed environment.
Record/inject/path nodes already carry descriptors; `op` uses its catalog
result descriptor; `select`/`block` derive a common branch/body result;
`context.run-id` is `String`; `result_path` must reference a provider result
binding and its declared path type. Definition/entry, join and loop results,
all parameter types and effect result/contract types are persisted. Case
bind types derive from the subject union's selected variant. The validator
uses these facts without a frontend environment or authored files.

A prompt slot row is `{name, kind, type, value, renderer_id, output_role,
placeholder_ordinals}` in declaration order. For `doc`, `renderer_id` is
null and the row additionally retains required document-reference/content
injection semantics (prepend, declaration order); it is not a rendered text
placeholder. Other kinds retain their selected renderer, refinements, repeated
placeholder positions and any declared output role/path/expected-output
facts. Reuse the existing fragment/dependency owners' semantic projections;
keep step ids and source subjects under provenance. Explicit dependencies
retain ordered operands, role, position and instruction. Do not reduce these
to counts or discard output-slot semantics.

### Provenance

Every node that came from a source form carries `"@": {"span": "<path>:<line>:<column>", "form": [...]}`.
The path is the one the reader recorded, as the source map records it today.
`strip_provenance` removes every `@` key; the digest is taken over the
stripped tree (P6, P7).

### Names

- Generated binders (`__wcc_*`, `__spike_*`-style names from the elaborator)
  are renamed `%<n>` per definition, in order of binding. Authored names are
  kept.
- An unspecialized top-level name is `module::name`; a specialized/local
  name appends the full SHA-256 of the canonical definition tuple in design
  §4.2. Persist that tuple as `key`: declaring module, definition kind,
  declared/local key, type/procedure-reference/workflow-reference/value
  bindings, explicit capture schema, residual parameter/result types.
  Maps sort by formal name; ordered arguments/fields retain declaration
  order. Runtime captures are explicit typed parameters/arguments, never
  runtime proc-ref values. Local keys ignore spans, generated names, body
  digests and unrelated pure bindings. Run-ref generated types use their
  structural input/result signature in definition keys; their final name
  and config site digest use the containing canonical definition/site.
- Nominal type identities and descriptors recursively use the declaring
  module, exported or private. Applied arguments, list/optional members,
  fields and variants recurse; generated run-ref result names never reuse
  `RunRefResult$…` from typecheck.
- Site segments follow the full traversal table of design §6: `select`
  prefixes under binder/arm, `block` under binder/`block`, join body under
  result binder/`body` with its continuation at the enclosing prefix, loop
  body/exhaustion separately. Pure bindings consume no effect ordinal.
  Segments are tagged internally; presentation escapes `% / = # [ ]` in
  authored names using UTF-8 percent encoding. Calls get frames only.

---

## Task Map

| Task | What | Group | Files it owns |
| --- | --- | --- | --- |
| 1 | The new target exists and refuses to run | A (alone, first) | `syntax.py`, `workflow/validation.py`, `run_ref/config.py`, `run_ref/bundle_transport.py`, `closed/__init__.py`, `closed/target.py`, `cli/commands/run.py`, `cli/commands/resume.py`, `specs/versioning.md`, `specs/dsl.md`, `specs/index.md` line 1, `tests/test_workflow_lisp_target_234.py` |
| 2 | The public compile entry that stops after typecheck | B (alone) | `closed/frontend.py`, `compiler.py` (`_compile_stage3_graph`), `workflows.py` (`Stage3CompileResult`) |
| 3 | The elaborator at the new target | C | `wcc/model.py` (`WccIdentityFactory.closed_program`), `wcc/elaborate.py` |
| 5 | Sites and the checked form | C | `closed/sites.py`, `closed/check.py` |
| 6 | Names that hold no path | C | `closed/names.py`, `type_env.py` (declaring module index) |
| 7 | The program artifact, its digest, and the manifest field `closure` | C2 (after 5) | `closed/program.py`, `command_boundaries.py`, `build_manifest_io.py`, `stdlib_contracts.py`, `compiler.py` (injected binding origins), `closed/frontend.py` (carriage) |
| 4 | The builder: bodies, values, the table, X1 to X4, command nodes | D (alone) | `closed/build.py`, `closed/values.py`, `closed/context.py`, `closed/effects.py` (commands and the closure rule), `typecheck_effects.py` (one gated line), `tests/workflow_lisp_closed_program_helpers.py` |
| 8 | Effect nodes: providers, run references, the gaps | E | `closed/effects.py`, `closed/build.py` (run-ref finalization call) |
| 9 | `orchestrator compile` at the new target: the build key and the artifact on disk | E | `closed/artifact.py`, `cli/commands/compile.py` |
| 10 | The corpus check | F | `tests/workflow_lisp_closed_program_corpus.py`, `tests/test_workflow_lisp_closed_program_corpus.py` |
| 11 | Documents | F | `specs/versioning.md`, `specs/io.md`, `docs/design/workflow_command_adapter_contract.md`, `docs/design/workflow_lisp_core_calculus_middle_end.md`, `docs/design/workflow_lisp_evaluated_execution.md` (status lines), `docs/lisp_workflow_drafting_guide.md`, `docs/index.md`, `docs/design/README.md`, `docs/capability_status_matrix.md` |

Order: A, then B, then C (Tasks 3, 5 and 6 may run in parallel), then
C2 (Task 7, after Task 5's validator and helper are merged), then D (Task 4),
then E (Tasks 8 and 9 may run in parallel), then F (Tasks 10 and 11).
Task 9 initially tests the command-only route from Task 4; its provider and
run-ref integration selectors run after Task 8 is merged. Task 11's status
edits land only after Task 10's evidence. Merge prerequisites into each
isolated worktree before dispatch. File disjointness alone is insufficient.

Spike line counts are historical evidence, not implementation budgets:
revised capture conversion, recursive descriptors, full
artifact typing and total traversal were not proved by the spike. Reuse the
existing owners named in each task; no new runtime or generic framework is
part of this plan.

Every task ends with the compatibility evidence named in the task, using the
programs of this table; a task that touches no shared module states so and
skips the builds.

| Program | Target | Why |
| --- | --- | --- |
| `workflows/examples/kiss_backlog_item.orc` (inputs under `workflows/examples/inputs/kiss_backlog_item/`) | 2.14 | oldest maintained example, `with-phase` |
| `workflows/examples/review_revise_design_docs_judgment_panel.orc` | 2.23 | phased delivery, imports |
| `workflows/examples/improve_experiment_proposal.orc` | 2.33 | a parametric specialization whose step ids digest `repr(TypeRef)` |
| the `PROGRAM` of `tests/test_workflow_lisp_target_234.py`, written to a fixed path | 2.34 | the newest existing target |

---

### Task 1: The New Target Exists And Refuses To Run

**Files:**
- Modify: `orchestrator/workflow_lisp/syntax.py` (`SUPPORTED_TARGET_DSL_VERSIONS`, the gate constants near line 51 to 70, the predicates)
- Modify: `orchestrator/workflow/validation.py` (`DEFAULT_SUPPORTED_VERSIONS`, `DEFAULT_VERSION_ORDER`)
- Modify: `orchestrator/workflow/run_ref/config.py`, `orchestrator/workflow/run_ref/bundle_transport.py` (`_SUPPORTED_TARGET_DSL_VERSIONS`)
- Create: `orchestrator/workflow_lisp/closed/__init__.py` (empty docstring module), `orchestrator/workflow_lisp/closed/target.py`
- Modify: `orchestrator/cli/commands/run.py` (`run_workflow`, before `build_frontend_bundle` at line 629), `orchestrator/cli/commands/resume.py` (before `build_frontend_bundle` at line 233)
- Modify: `specs/versioning.md` (a `v2.35 additions` block after the `v2.34` block at line 736, a roadmap line after line 816, a table row after line 967), `specs/dsl.md` line 23 (admitted revisions extend through `"2.35"`), `specs/index.md` line 1 (the title's range)
- Modify: `tests/test_workflow_lisp_target_234.py` (the gate dictionaries)
- Test: `tests/test_workflow_lisp_target_evaluated_execution.py`

**Read first:** `tests/test_workflow_lisp_target_234.py` in full; the Phase 0
Task 0 report's list of every place a version is compared (every gate is
"this target or newer", so the new target passes every 2.x gate with no
edit); design §13.

**Interfaces:**
- Produces: `syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION: str = "2.35"`
  (the owner-selected target; later tasks consume this constant) and `syntax.target_dsl_uses_evaluated_execution(target_dsl_version: str) -> bool`
  (tuple comparison `>=`, like `target_dsl_supports_numeric_surface`).
- Produces: `closed.target.entry_target_dsl_version(path: Path) -> str`
  (reads the module with `compiler.compile_stage1_module` and returns
  `syntax_module.target_dsl_version`) and
  `closed.target.refuse_run_at_evaluated_execution_target(path: Path) -> None`,
  which raises `LispFrontendCompileError` with one diagnostic
  `code="evaluated_execution_unavailable"`, `phase="lowering"`, at the span
  of the module's `:target-dsl` form (the span `target_dsl_unsupported` uses
  today), when the target uses evaluated execution.
- Consumed by: every later task (the predicate); Task 9 (`entry_target_dsl_version`).

- [x] **Step 0: Record the owner-selected target and implementation base.**

The reviewed plan was presented and the owner selected **2.35** on
2026-09-30. Use that number in the registries/docs and the gate constant in
fixtures. `PHASE2_BASE=2e4c7a653d74c06e24c15c284662e5914abd5576` records the
clean integrated source before Task 1 for compatibility comparisons.

- [ ] **Step 1: Write the failing tests**

`tests/test_workflow_lisp_target_evaluated_execution.py`, importing
`_write_program`, `_public_run`, `_log`, `GATE_PREDICATES` and `GATES_FROM_234`
from `tests/test_workflow_lisp_target_234.py`:

```python
from orchestrator.workflow_lisp import syntax
TARGET = syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION

@pytest.mark.parametrize("registry", [syntax.SUPPORTED_TARGET_DSL_VERSIONS, validation.DEFAULT_SUPPORTED_VERSIONS,
                                      run_ref_config._SUPPORTED_TARGET_DSL_VERSIONS, bundle_transport._SUPPORTED_TARGET_DSL_VERSIONS])
def test_the_evaluated_execution_target_is_registered(registry) -> None:
    assert TARGET in registry

def test_shared_validation_orders_the_new_target_last() -> None:
    assert validation.DEFAULT_VERSION_ORDER[-2:] == ("2.34", TARGET)

def test_the_gate_opens_at_the_new_target_only() -> None:
    assert (syntax.target_dsl_uses_evaluated_execution("2.34"), syntax.target_dsl_uses_evaluated_execution(TARGET)) == (False, True)

@pytest.mark.parametrize("gate", sorted({**GATE_PREDICATES, **GATES_FROM_234}))
def test_every_gate_that_234_passes_holds_at_the_new_target(gate: str) -> None:
    assert {**GATE_PREDICATES, **GATES_FROM_234}[gate](TARGET) is True

def test_run_refuses_a_program_at_the_new_target_before_any_command(tmp_path, monkeypatch) -> None:
    files = _write_program(tmp_path, TARGET)
    line = next(n for n, text in enumerate(files["source"].read_text().splitlines(), 1) if ":target-dsl" in text)
    monkeypatch.chdir(tmp_path)
    result = _public_run(files)
    assert result.exit_code == 2
    assert _log(tmp_path / "probe_revise.py") == []
    assert [(d.code, Path(d.span.start.path), d.span.start.line) for d in result.diagnostics] == \
        [("evaluated_execution_unavailable", files["source"], line)]
```

Read `run_workflow`'s result type first and adapt the last assertion to how it
carries diagnostics (it renders them through the logger today; if the result
holds none, assert on the captured log records' `code` through `caplog` with
the diagnostic's rendered location, which `render_diagnostic` prints as
`<path>:<line>:<column>: [<code>]`). Add the resume test the same way
(`orchestrator resume` on a run directory whose `workflow_file` names the
program: exit 2, same code). Add an unregistered next-version refusal derived from the selected target
(`target_dsl_unsupported`, as `test_target_235_is_refused_as_unsupported`).

- [ ] **Step 2: Run them; expected failures**

`pytest -q tests/test_workflow_lisp_target_evaluated_execution.py`: the
registry tests fail with `'2.35' not in ...`, the gate test with
`AttributeError`, the run test with exit 0 and a command in the log (the
program lowers on the flat route because every gate is `>=`).

- [ ] **Step 3: Implement**

Add `"2.35"` to the four registries and to the end of `DEFAULT_VERSION_ORDER`.
Add the constant and predicate to `syntax.py`. Write `closed/target.py`.
In `run_workflow` and in `resume`, inside the `try` that catches
`LispFrontendCompileError` around `build_frontend_bundle`, call
`refuse_run_at_evaluated_execution_target(workflow_path)` first. In
`tests/test_workflow_lisp_target_234.py` add
`GATES_FROM_EVALUATED = {"EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION": syntax.target_dsl_uses_evaluated_execution}`
and include it in `test_every_min_target_gate_has_a_predicate_here`; leave
the 2.34 assertions as they are (2.34 must not pass the new gate).

- [ ] **Step 4: Run the tests; expected pass**

The new module, then `tests/test_workflow_lisp_target_234.py` (its
`test_every_min_target_gate_has_a_predicate_here` fails until the dictionary
is added) and `tests/test_workflow_shared_validation.py` (its version-catalog
test expects the order to end at 2.34: update that expectation as the 2.34
commit did), `tests/test_workflow_lisp_target_233.py`.

- [ ] **Step 5: Documents**

`specs/versioning.md`: a block `v2.35 additions (in progress)` stating that
the target exists, that a program at it is compiled to a closed program and
not to steps, that `run` and `resume` refuse it with
`evaluated_execution_unavailable` until the evaluator lands, and that the
tasks of this plan add the closed program; a roadmap line; a table row.
`specs/dsl.md` line 23: admitted revisions extend through `"2.35"`.
`specs/index.md` line 1: the range (two tests compare it with the highest
supported version).

- [ ] **Step 6: Compatibility evidence**

Build the four programs of the table at the base and at the head. Expected:
every artifact byte-identical (the registries add a member; no gate changes).

- [ ] **Step 7: Commit**

`git add -- orchestrator/workflow_lisp/syntax.py orchestrator/workflow/validation.py orchestrator/workflow/run_ref/config.py orchestrator/workflow/run_ref/bundle_transport.py orchestrator/workflow_lisp/closed orchestrator/cli/commands/run.py orchestrator/cli/commands/resume.py specs tests/test_workflow_lisp_target_234.py tests/test_workflow_lisp_target_evaluated_execution.py tests/test_workflow_shared_validation.py`

`git commit -m "feat: register the evaluated execution target and refuse to run it before the evaluator exists" -- orchestrator/workflow_lisp/syntax.py orchestrator/workflow/validation.py orchestrator/workflow/run_ref/config.py orchestrator/workflow/run_ref/bundle_transport.py orchestrator/workflow_lisp/closed orchestrator/cli/commands/run.py orchestrator/cli/commands/resume.py specs tests/test_workflow_lisp_target_234.py tests/test_workflow_lisp_target_evaluated_execution.py tests/test_workflow_shared_validation.py`

**What this makes harder later:** Phase 3 must remove the guard in `run` and
`resume` and route the new target to the evaluator; the test that pins the
refusal changes then. Nothing else.

---

### Task 2: The Public Compile Entry That Stops After Typecheck

**Files:**
- Create: `orchestrator/workflow_lisp/closed/frontend.py`
- Modify: `orchestrator/workflow_lisp/compiler.py` (`_compile_stage3_graph`, the call of `_lower_workflows_for_route` at line 3083 and the `Stage3CompileResult` construction at line 3130)
- Modify: `orchestrator/workflow_lisp/workflows.py` (`Stage3CompileResult`, line 420)
- Test: `tests/test_workflow_lisp_closed_program_frontend.py`

**Read first:** `experiments/evaluated_execution_spike/frontend.py` (what the
spike captured from `_lower_workflows_for_route`'s arguments); `compiler.py`
lines 2481 to 3208 (`_compile_stage3_graph`, one iteration per module in
topological order); `compile_stage3_entrypoint` (line 651); how
`_select_entry_workflow` and `validated_bundles_by_name` are used by
`build.py` (`_compile_entry`, `_select_and_reattach`).

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class TypedProgram:
    entry: TypedWorkflowDef | None  # None only during graph assembly; public return always selected
    workflows: Mapping[str, TypedWorkflowDef]          # every typed workflow of the graph, by canonical name
    procedures: Mapping[str, TypedProcedureDef]        # every typed procedure, specializations included
    type_env: FrontendTypeEnvironment                  # the entry module's
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment]
    workflow_type_envs: Mapping[str, FrontendTypeEnvironment]
    module_type_envs: Mapping[str, FrontendTypeEnvironment]   # module name -> its environment, whole graph
    command_boundaries: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding]
    command_boundary_origins: Mapping[str, str]  # trusted workspace/package origin; Task 7 adds injection carriage
    externs: Mapping[str, ProviderExtern | PromptExtern]     # entry resolved environment
    module_externs: Mapping[str, Mapping[str, ProviderExtern | PromptExtern]]  # existing environments, no alias flattening
    configuration_bindings: Mapping[str, object]  # all caller/manifest bindings plus used injected bindings
    target: str
    entry_module: str
    entry_dir: str      # logical directory for asset lookup only, not definition identity
    source_file_digests: Mapping[str, str]  # module -> exact bytes consumed by this compile
    local_definition_keys: Mapping[str, object]  # old generated lookup name -> position-free lexical key

    def workflow_type_env(self, name: str) -> FrontendTypeEnvironment: ...
    def procedure_type_env(self, procedure: TypedProcedureDef) -> FrontendTypeEnvironment: ...  # procedure_type_env_for
```

```python
def compile_typed_program(
    entry_path: Path, *, entry_workflow: str, source_roots: tuple[Path, ...],
    command_boundaries: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding],
    provider_externs: Mapping[str, str] | None = None,
    prompt_externs: Mapping[str, PromptExternValue] | None = None,
    workspace_root: Path | None = None,
    source_read_trace: SourceReadTrace | None = None,
) -> TypedProgram
```

  It calls `compile_stage3_entrypoint(...)` with `validate_shared=True`,
  `lowering_route=None`, forwarding one supplied or newly created
  `SourceReadTrace` through entry reading, imports and all compiler reads.
  Before returning the selected `TypedProgram`, call
  `_source_file_digests_from_trace(compile_result=result,
  source_read_records=trace.records, source_revision_vector=trace.revision_vector)`
  and retain its module-to-digest map. Never reread source after compile to
  form it. The existing linked result provides the module graph; no new
  signature or graph-result abstraction is needed.
  It raises `LispFrontendCompileError` with `evaluated_execution_target_required`
  at the `:target-dsl` span when the entry module's target does not use
  evaluated execution, and the typechecker's own diagnostics unchanged when
  the program does not typecheck.
- Produces: `Stage3CompileResult.typed_program: object | None = None`
  (a `TypedProgram` snapshot for source modules in an evaluated-entry graph,
  else `None`; public selection happens after the complete graph returns).
- Rule of `_compile_stage3_graph` (§13): compute `closed_entry` once from
  `graph.modules_by_name[graph.entry_module_name].syntax_module.target_dsl_version`.
  When true, skip `_lower_workflows_for_route` and bundle validation/production
  for **every source module**, including imports declared at older targets.
  Keep imported typed signatures (`_imported_workflow_signatures`), procedure/
  workflow effects, catalogs, environments and typed bodies published in the
  same topological order. `_workflow_name_resolver` already resolves graph
  imports through `import_scope`; do not fabricate `validated_bundles` just to
  populate `external_workflow_names`. Explicit externally supplied compiled
  bundles remain distinct: a reachable target lacking source/typed body is a
  missing-body integration prerequisite: inventory its existing producer and
  preserve the accepted call contract by supplying its typed source body. Do
  not quietly add external calls to release exclusions or fabricate a body
  from flat steps; an admitted call missing its body is a compiler defect.
  The first release's source calls remain admitted.
- For an older-target entry, preserve the existing lowering path. Detect an
  older-to-evaluated call/import edge before lowering the new module, and
  emit `evaluated_execution_target_direction_invalid` at its import/call
  source location, naming both modules/targets. Also check call edges inside
  an evaluated-entry graph: an imported older module cannot call back into a
  module declared at the new target. New-entry-to-old-import remains allowed.
- Consumed by: Tasks 3 to 10.

- [ ] **Step 1: Write the failing tests**

Fixtures: create `tests/fixtures/workflow_lisp/closed_program/` and copy
`loop_in_branch.orc`, `three_call_sites.orc`, `arms_in_loop.orc`,
`if_in_hook.orc`, `loop_in_loop.orc`, `if_over_lists.orc`,
`provider_review.orc`, `prompt_dependency.orc` and `chain.orc` from
`tests/experiments/fixtures/evaluated_execution_spike/`, replacing each
`(:target-dsl "2.33")` with `(:target-dsl "TARGET")` and each
`(defmodule spk/<name>)` with `(defmodule cp/<name>)`. Tests substitute
`TARGET` with `syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION`.

```python
def test_a_program_the_flat_route_refuses_typechecks_into_a_typed_program(tmp_path) -> None:
    entry = install(tmp_path, fixture("loop_in_branch"))      # helpers as the spike's `install`, local to this module
    typed = compile_typed_program(entry, entry_workflow="cp/loop_in_branch::run", source_roots=(tmp_path,),
                                  command_boundaries=BOUNDARIES)
    assert (typed.entry.definition.name, typed.target, sorted(typed.procedures)) == (
        "cp/loop_in_branch::run", TARGET, ["cp/loop_in_branch::fetch"])

def test_the_graph_result_at_the_new_target_holds_no_lowered_workflow(tmp_path) -> None:
    result = compile_stage3_entrypoint(entry, source_roots=(tmp_path,), command_boundaries=BOUNDARIES,
                                       validate_shared=True, workspace_root=tmp_path, lowering_route=None)
    assert (result.entry_result.lowered_workflows, result.entry_result.typed_program is not None) == ((), True)

def test_evaluated_entry_skips_flat_lowering_for_its_whole_source_graph(tmp_path, monkeypatch) -> None:
    # New entry calls an imported old-target workflow with a typecorrect loop in a branch.
    # Replace _lower_workflows_for_route with a raising sentinel: neither module calls it.
    # Every source result has lowered_workflows == () and validated_bundles == {};
    # old workflow signature/effects/body and imported procedure specializations survive.
    ...

def test_the_same_old_entry_keeps_its_existing_flat_route_refusal(tmp_path) -> None:
    # Compile the old module itself through compile_stage3_entrypoint and pin its current code/location.
    ...

def test_an_old_to_new_edge_has_a_located_target_direction_refusal(tmp_path) -> None:
    # Test old entry -> new module and new entry -> old helper -> new callee; neither silently crosses runtimes.
    ...

def test_source_digests_describe_the_compile_reads_not_a_later_reread(tmp_path, monkeypatch) -> None:
    # Record source bytes, then mutate an imported file after its traced read but before API return.
    # Returned map hashes the consumed bytes; a fresh next compile observes the edit.
    ...

def test_a_type_error_at_the_new_target_keeps_its_code(tmp_path) -> None:
    # a signature naming an undeclared type: code `type_unknown` at the same line as at 2.34
    ...

def test_an_entry_at_2_34_is_refused_by_the_typed_entry(tmp_path) -> None:
    # code evaluated_execution_target_required at the :target-dsl line
    ...
```

- [ ] **Step 2: Run; expected failures**

`ImportError` on `closed.frontend`; then, once the module exists but the
graph still lowers, `loop_in_branch` fails with
`workflow_boundary_type_invalid` from the flat route.

- [ ] **Step 3: Implement**

In `_compile_stage3_graph`, derive `closed_entry` from the entry target
**before the module loop** and check target-direction edges. When
`closed_entry`, do not lower; build the `TypedProgram` from the same
arguments the lowering call receives (`typed_workflows`,
`resolved_combined_procedures`, `typed_workflows_by_name`,
`combined_procedure_type_envs`, `workflow_type_envs_by_name`,
`extern_environment`, `command_boundary_environment`, `type_env`), retaining
extern bindings by declaring module and resolved workflow-reference rebinding
so identical aliases in different modules cannot overwrite one another, plus
`module_type_envs` accumulated across the loop (a dict the loop fills with
`type_env` per module name), local-definition lexical facts and `entry_dir`.
Use existing `GeneratedLocalProcedure` metadata for owner/name/capture facts;
recover same-name lexical scope order from the expanded declaration tree,
counting local declarations only. Spans may match an existing node to its
metadata during this compile, but never enter the resulting key. Retain this
small side map, rather than changing old type/definition repr or the existing
span-derived naming function. Put the construction in
`closed/frontend.py` as `typed_program_from_graph(**kwargs) -> TypedProgram`
so graph routing remains a small change in its existing owner. The graph
stays entry-agnostic:
`typed_program_from_graph` sets `entry` to `None`, and
`compile_typed_program` resolves it after the compile: the export surface
of the entry module (`result.graph.export_surfaces_by_name[entry module].workflows_by_name`)
maps `entry_workflow` to its canonical name (also preserve the existing
standalone-entry selection using a fixed namespace), which must be in
`typed.workflows`; otherwise raise `entry_workflow_unknown` at the source
path, the code and location `build._select_entry_workflow` gives today
(that function cannot be reused: it requires a validated bundle). Return
`replace(typed, entry=typed.workflows[canonical])`.

Check `compile_stage3_entrypoint`'s post-processing on a result with no
lowered workflows: `_filter_profile_checked_linked_diagnostics`,
`_collect_declared_transition_binding_diagnostics_for_linked_result` and
`_dedicated_runtime_proof_boundary_diagnostics` must accept an empty tuple;
read each and add the empty-case guard only where one is missing.

- [ ] **Step 4: Run; expected pass**

The new module; `tests/test_workflow_lisp_target_234.py`;
`tests/test_workflow_lisp_generic_unions_runtime.py` (a caller of
`compile_stage3_entrypoint`); `tests/test_workflow_lisp_improve_stdlib.py`.

- [ ] **Step 5: Compatibility evidence**

The four programs of the table: byte-identical (the branch is dead below
the new target).

- [ ] **Step 6: Commit**

`git add -- orchestrator/workflow_lisp/closed/frontend.py orchestrator/workflow_lisp/compiler.py orchestrator/workflow_lisp/workflows.py tests/fixtures/workflow_lisp/closed_program tests/test_workflow_lisp_closed_program_frontend.py`

`git commit -m "feat: a public compile entry that stops after typecheck at the evaluated execution target" -- orchestrator/workflow_lisp/closed/frontend.py orchestrator/workflow_lisp/compiler.py orchestrator/workflow_lisp/workflows.py tests/fixtures/workflow_lisp/closed_program tests/test_workflow_lisp_closed_program_frontend.py`

**What this makes harder later:** `build_frontend_bundle` still expects a
validated bundle; Task 9 gives the closed route its own build function
rather than threading `None` through `_select_and_reattach` and `_emit`.
When Phase 7 retires the flat route, the two build functions merge.

---

### Task 3: The Elaborator At The New Target

**Files:**
- Modify: `orchestrator/workflow_lisp/wcc/model.py` (`WccIdentityFactory`, line 73)
- Inspect, modify only if necessary: `orchestrator/workflow_lisp/wcc/anf.py` (the gated normalization path)
- Modify: `orchestrator/workflow_lisp/wcc/elaborate.py`: `elaborate_typed_workflow_body` (line 219), the `DoneExpr` branch of `_elaborate_expr_to_body` (line 1662), `_retarget_loop_continue` (line 2529) and its call at line 2465, the `PhaseTargetExpr` branch of `_elaborate_expr_to_value` (line 2736), `_prebind_effect_argument_matches` (line 4077)
- Test: `tests/test_workflow_lisp_closed_program_elaboration.py`

**Read first:** `experiments/evaluated_execution_spike/repairs.py`
(`bind_done_values`: the `done` and argument repairs, 103 lines);
`_bind_effectful_loop_state_fields` (elaborate.py line 1791: the pattern to
copy for `done`); `hygiene.fresh_name`, `generated_name_scope`,
`reserved_identifiers`; `phase.py` `PHASE_TARGET_SPECS` (line 46) and
`IMPLEMENTATION_ATTEMPT_TARGET_FIELDS` (line 42);
`lowering/phase_scope.py` lines 330 to 398 (what the flat route gives a
`phase-target`: the field for the implementation context, the join
`<artifact-root>/<phase>/<suffix>` for a generic `PhaseCtx`); the spike
report iteration 3, D1 and D2.

**Interfaces:**
- Produces: `WccIdentityFactory.closed_program: bool = False`, propagated by
  `child_scope`, excluded from `scope_id` and node ids (as
  `enclosing_variants` is). `elaborate_typed_workflow_body(..., closed_program: bool = False)`
  sets it on the root scope. Every rule below applies only when
  `scope.closed_program` is true. Below it, nothing changes: byte identity.
- Rule 1 (§4.3, "an effectful expression in an argument position is bound by
  a `let` before the call, in source order"): in `replace_arg` of
  `_prebind_effect_argument_matches`, prebind an argument when
  `scope.closed_program and _contains_effect(arg_expr)`; also prebind the
  `adapter_inputs` values of a `CommandResultExpr` (pairs) and the
  `keyword_args` of a `RunRefExpr` (already handled), in source order.
  `match_bindings` are wrapped outermost-first, which is source order.
- Rule 2 (§4.3, "a `done` value that is an effect or a `match` is bound by a
  `let` before the `done`"): in the `DoneExpr` branch, when
  `expr.result_expr` is a `MatchExpr` or `_contains_effect(expr.result_expr)`
  (same for `terminal_state_expr`), return
  `_elaborate_let_star(LetStarExpr(bindings=((g, expr.result_expr),), body=replace(expr, result_expr=NameExpr(g, ...)), span=..., form_path=..., expansion_stack=...), ...)`
  with `g = fresh_name(_generated_effect_binding_name_from_scope(generated_name_scope(scope).child_scope("loop-done", authored_binding_name="result"), role="result"), reserved_identifiers(expr, value_env=value_env, compile_time_bindings=compile_time_bindings))`.
- Rule 3 (§4.3, "a `continue` names the loop it is in; the elaborator's
  retargeting descends into joins"): `_retarget_loop_continue(body, *, loop_name, through_joins: bool)`
  gains a `WccJoin` case (`replace(body, body=..., continuation=...)`) taken
  when `through_joins`; the call at line 2465 passes `scope.closed_program`.
  A nested `WccRecJoin` is not entered (its own continues are its own).
- Rule 4 (X3): in the `PhaseTargetExpr` branch, when `scope.closed_program`:
  `active_phase_scope` must be set (else raise the `phase_translation_body_invalid`
  the flat route raises); `ctx = active_phase_scope.ctx_expr` must be a
  `NameExpr` or `FieldAccessExpr` after once-only binding at the with-phase
  site. If another admitted context expression arrives, prebind it through
  the same normalization seam; it is not a new `closed_program_gap`. Infer
  the context's type. If its record has the field `implementation_state_bundle_path`,
  return `WccFieldAccessAtom(base=<ctx as a name atom>, fields=(*ctx.fields, IMPLEMENTATION_ATTEMPT_TARGET_FIELDS[target]))`,
  typed by the record's field type (`type_env.record_field`). Otherwise return
  `WccPureOp(operator="path/join", args=(WccFieldAccessAtom(ctx, (..., "artifact-root")), WccLiteralAtom(f"{phase_name}/{suffix}", literal_kind="string")), field_names=())`
  with `suffix = PHASE_TARGET_SPECS[target][2]`, typed as
  `_build_phase_target_type(phase_name, target)`. `path/join` is an operator
  name only the closed builder reads (Task 4 maps it to the `path_join`
  value); the flat route never sees it.
- Rule 5 (case e, gate report §4): no elaborator change. The builder passes
  `procedure_return_types` without generic templates (Task 4).
- Rule 6 (design §4.3): audit every child edge, not just call operands.
  Effect-containing `select`/`block` under aggregates, operator operands,
  conditions, loop seed/budget, `halt`, `jump`, `continue` and `done` values
  are bound before use. Hoist only within the selected arm/iteration and in
  source order, preserving short-circuiting. Extend the gated elaborator
  prebinding seam first; change `wcc/anf.py` only if normalization loses a
  binding. No hidden effectful child survives outside walked bindings.
- Consumed by: Task 4 (`closed_program=True`), Task 8.

- [ ] **Step 1: Write the failing tests**

Tests get typed programs through `compile_typed_program` (Task 2) and call
`elaborate_typed_workflow_body(typed.entry.typed_body, owner_name=..., type_env=typed.workflow_type_env(name), value_env=dict(signature.params), workflow_return_types=..., procedure_return_types=..., resolved_procedures_by_name=typed.procedures, procedure_type_envs=typed.procedure_type_envs, route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION, closed_program=True)`
then `normalize_wcc_body_to_anf`. Assertions are on WCC node shapes.

```python
def test_an_effectful_argument_is_bound_before_the_call_in_source_order(tmp_path) -> None:
    # (defworkflow run () -> Box (fetch (inc 4)))  with inc and fetch command-backed
    body = elaborate(tmp_path, EFFECT_ARGUMENT)
    lets = let_chain(body)                      # the bound values of the outer let chain, in order
    assert [callee(v) for v in lets] == ["cp/effect_argument::inc", "cp/effect_argument::fetch"]
    assert isinstance(lets[1].args[0], WccNameAtom) and lets[1].args[0].name == outer_let_names(body)[0]

def test_a_done_value_that_is_an_effect_is_bound_before_the_done(tmp_path) -> None:
    body = elaborate(tmp_path, DONE_CALL)       # (done (fetch state.n)) in a loop body
    loop = find(body, WccRecJoin)
    tail = last(loop.body)                      # the loop body's tail after its lets
    assert isinstance(tail, WccLoopDone) and isinstance(tail.result, WccNameAtom)
    assert callee(bound_value_of(loop.body, tail.result.name)) == "cp/done_call::fetch"

def test_every_continue_under_a_join_names_its_loop(tmp_path) -> None:
    body = elaborate(tmp_path, fixture("arms_in_loop"))
    loop = find(body, WccRecJoin)
    assert {node.target_name for node in walk(loop.body) if isinstance(node, WccLoopContinue)} == {loop.loop_name}

def test_a_phase_target_on_the_implementation_context_is_its_field(tmp_path) -> None:
    # the with_phase_composed_binding shape, retargeted, provider inputs (phase-target execution-report)
    perform = find(body, WccPerform)
    assert [(a.base.name, a.fields) for a in perform.positional_args if isinstance(a, WccFieldAccessAtom)][-2:] == \
        [("phase-ctx", ("execution_report_target",)), ("phase-ctx", ("progress_report_target",))]

def test_a_phase_target_on_a_generic_context_is_a_path_join(tmp_path) -> None:
    # (with-phase ctx work (phase-target execution-report)) with ctx : PhaseCtx as in phase_stdlib_run_provider_phase.orc
    value = find(body, WccPureOp)
    assert (value.operator, value.args[0].fields, value.args[1].value) == ("path/join", ("artifact-root",), "work/execution-report.md")

def test_below_the_new_target_the_rules_are_off(tmp_path) -> None:
    # closed_program=False on EFFECT_ARGUMENT raises TypeError("unsupported WCC elaboration node: ProcedureCallExpr")
```

Add parameterized WCC-shape cases for select prefixes, nested blocks, join
body/continuation, record/list fields, operator operands, conditions and each
terminal/loop operand. Assert order and branch-local binding, with an unchosen
arm still under that arm. Also a `continue` whose state field holds an effect still binds it (the
2.33 rule is unchanged); the `#`-ordinal-relevant shape of Review Focus 1 is
not this task's.

- [ ] **Step 2: Run; expected failures**

`TypeError: unsupported WCC elaboration node: ProcedureCallExpr` for the
argument and `done` cases; `{"__wcc_current_loop__"}` for the `continue`
case; `WccPhaseTargetAtom` where a field access is expected.

- [ ] **Step 3: Implement the six rules**

Each rule under `if scope.closed_program`. Keep every existing branch byte
for byte on the other path.

- [ ] **Step 4: Run; expected pass**

The new module; then `tests/test_workflow_lisp_wcc_m4.py`,
`tests/test_workflow_lisp_wcc_m3.py`, `tests/test_workflow_lisp_wcc_m2.py`,
`tests/test_workflow_lisp_wcc_m1.py` (the ANF invariant tests),
`tests/test_workflow_lisp_improve_stdlib.py`,
`tests/test_workflow_lisp_guide_programs.py` (row 16 of the drafting guide
still meets `compiler_defect` at 2.33 and 2.34).

- [ ] **Step 5: Compatibility evidence**

The four programs of the table: byte-identical. `improve_experiment_proposal`
is the one with a `continue` under a join and a specialized callee: its step
ids must not move.

- [ ] **Step 6: Commit**

`git add -- orchestrator/workflow_lisp/wcc/model.py orchestrator/workflow_lisp/wcc/elaborate.py tests/test_workflow_lisp_closed_program_elaboration.py tests/fixtures/workflow_lisp/closed_program`

`git commit -m "feat: elaborate effectful arguments, done values, continue targets and phase-target for the closed program" -- orchestrator/workflow_lisp/wcc/model.py orchestrator/workflow_lisp/wcc/elaborate.py tests/test_workflow_lisp_closed_program_elaboration.py tests/fixtures/workflow_lisp/closed_program`

**What this makes harder later:** `path/join` is an operator the catalog does
not know; if Phase 3 wants to evaluate it through the catalog, the catalog
gains a node kind then. Two elaboration behaviours now live behind one flag;
Phase 7 removes the flag with the flat route.

---

### Task 5: Sites And The Checked Form

**Files:**
- Create: `orchestrator/workflow_lisp/closed/sites.py`, `orchestrator/workflow_lisp/closed/check.py`
- Test: `tests/test_workflow_lisp_closed_program_sites.py`, `tests/test_workflow_lisp_closed_program_check.py`

**Read first:** `experiments/evaluated_execution_spike/sites.py` (`_Scope`,
`_SiteWalker`, `_Validator`) and `table.py` (`to_table`, `_local_sites`);
design §6 (I1 to I4), P4, P5. These two modules are pure functions over the
schema above; no compiler import.

**Interfaces:**
- Produces: `sites.SEPARATOR = " / "`;
  `sites.assign_sites(tree: dict) -> list[tuple[str, str]]`: writes
  `site` (the local path) on every `perform` and `frame` (the local prefix
  plus `<binder>=<callee>`) on every `call` whose callee performs an effect,
  walking the entry body then each definition body on its own; returns the
  site table in program order, appending **only `perform`** rows. A `call`'s effectfulness is read from
  `tree["definitions"][callee]` (memoized with a visiting guard that reports
  `call_cycle` rather than recursing forever on malformed input). An unnamed binder is one that
  starts with `%`.
- Produces: `check.CheckedFormError(ValueError)` with attributes `rule: str`
  and `location: str | None` (the `@.span` of the offending node when it has
  one); `check.validate(tree: dict) -> None` checking, over the entry and
  every definition: every `name` is bound (params, lets, join params, loop
  params, case binds, select prefixes, `list_map` binders); every `jump`
  names an enclosing `join`; every `continue` names the innermost enclosing
  `loop` (not a join's, not an outer loop's); every `perform` has a `site`
  unique within its definition; every `call` names a definition, and the
  call graph is acyclic (no recursive call, P5); every `loop` has a `budget`
  value; every `op` payload passes `validate_pure_expr_payload`; every
  `record` and `inject` has field names equal to its descriptor's; every
  `path_join` has a path descriptor with a root; the `k` of every node is
  one of the schema's. Walk every edge listed in design §6, including
  select prefixes/values, block body, separate join body/continuation and
  exhaustion. Independently enumerate all performs/calls rather than
  trusting the site walk: enforce a site-table bijection, exactly one frame
  per effectful call and no call row in `sites`.
- `validate` also infers/checks every value against the persisted `types`
  table and typed environments. Require exact nominal definitions, primitive
  literal kinds (Bool is not Int), list elements, field projections,
  record/variant field types, catalog argument/result types, strict Bool
  conditions, select arm agreement and block result types. Check entry and
  callee defaults/params/results, capture/call arity and argument/result
  types, join jump/result types, loop seed/state/budget/continue/done/
  exhaustion results, provider result-path origins and every perform's
  result against its command/provider contract or decoded run-ref result.
  Effects must also match their canonical configuration entry. Reuse pure
  catalog descriptor validation/coercion and assignability semantics; do not
  invoke frontend typecheck or accept equality of two unvalidated copied
  labels as proof. Unknown/missing type facts and mismatches fail read-back
  with a stable rule (e.g. `type_mismatch`, `nominal_definition`,
  `call_signature`, `effect_result`, `entry_result`). This proves internal
  type/contract consistency, including definition-name/key agreement and
  capture/residual signature agreement, not artifact authenticity: Phase 3 separately
  compares the stored artifact's digest with its durable run header. Reject
  malformed/duplicate JSON keys and nonfinite numbers before typed checking,
  and reject duplicate definition/type/parameter identities rather than
  silently overwriting them.
- Consumed by: Task 4 (`assign_sites` then `validate` at build), Task 7
  (`validate` when an artifact is read back).

- [ ] **Step 1: Write the failing tests on hand-written trees**

Write a helper `tree(entry_body, definitions={})` in the test module that
returns a minimal program dict (`params: []`, `defaults: {}`). Perform nodes
in these trees need only `{"k": "perform", "class": "command", "result": {...}, "repeat": "rerun", "boundary": "fetch", "command": ["python", "probe.py"], "closure": [], "contract": {...}, "argv": []}`.

```python
def test_three_arms_in_a_loop_give_three_sites_with_the_frame_and_the_loop_segment() -> None:
    # entry body: loop(param "state") whose body binds `got` to a case with three arms,
    # each arm binding `%1` to a call of "cp/arms_in_loop::fetch"; the definition's body performs one unnamed effect
    table = assign_sites(t)
    assert table == [("cp/arms_in_loop::fetch", "#1")]
    assert [n["frame"] for n in calls(t)] == [f"loop:state[*] / got / {arm} / #1=cp/arms_in_loop::fetch" for arm in (...)]

def test_a_pure_binding_takes_no_ordinal_and_a_repeated_name_takes_a_counter() -> None:
    # lets: %1 = op, %2 = perform, x = perform, x = perform  ->  sites ["#1", "x", "x#2"]

def test_a_join_whose_body_performs_an_effect_is_a_segment_and_a_pure_join_is_not() -> None:

def test_a_call_of_a_pure_definition_gets_no_frame_and_no_site() -> None:

def test_the_exhaustion_body_is_its_own_segment() -> None:   # "loop:state / exhausted / e"
```

Add hand-written valid trees with effects in each select arm prefix, a
nested block, join body and continuation with the same authored binder, and
loop exhaustion. Assert independent node/site bijection and call-frame
counts. Tamper an unvisited effect, insert a call into `sites`, remove a
frame, and use authored punctuation to test collision-free presentation.

For `check.validate`, one test per rule, each tampering one node of a valid
tree and asserting `CheckedFormError.rule`: `unbound_name`, `jump_target`,
`continue_target` (a `continue` naming an outer loop from an inner loop),
`site_missing`, `site_duplicate`, `callee_unknown`, `call_cycle`,
`budget_missing`, `payload_invalid`, `record_fields`, `node_kind` plus the
type rules above. Change non-operator descriptors independently: perform
result, entry result, list-map result item, nested record field, call result/
argument, loop state and private nominal name. Each must fail even after the
attacker recomputes the outer digest. Add valid typed trees covering all
value forms so the validator does not reject supported forms indiscriminately.

- [ ] **Step 2: Run; expected failure** `ImportError`.

- [ ] **Step 3: Implement** `sites.py` and `check.py` over the shared schema.
Use small node dispatchers as in the spike, with an independent validation
walk. The spike's small validator is not a full type checker; do not preserve
its omitted type checks to meet its historical line estimate.

- [ ] **Step 4: Run; expected pass.** Collect-only on both modules.

- [ ] **Step 5: Compatibility evidence:** no shared module touched; state
so.

- [ ] **Step 6: Commit**

`git add -- orchestrator/workflow_lisp/closed/sites.py orchestrator/workflow_lisp/closed/check.py tests/test_workflow_lisp_closed_program_sites.py tests/test_workflow_lisp_closed_program_check.py`

`git commit -m "feat: effect sites and the checked form of the closed program" -- orchestrator/workflow_lisp/closed/sites.py orchestrator/workflow_lisp/closed/check.py tests/test_workflow_lisp_closed_program_sites.py tests/test_workflow_lisp_closed_program_check.py`

**What this makes harder later:** `par-map` (Phase 5) adds an item segment
`[<index>]` (I2) to the walker and a node kind to the validator; both are
one case each.

---

### Task 6: Names That Hold No Path

**Files:**
- Create: `orchestrator/workflow_lisp/closed/names.py`
- Modify: `orchestrator/workflow_lisp/type_env.py` (`FrontendTypeEnvironment.from_module`, line 604: the map of nominal descriptor names; a sibling map and a method)
- Test: `tests/test_workflow_lisp_closed_program_names.py`

**Read first:** the spike's `closed.py` lines 122 to 170 (`_Def.bind`,
`_type_id`) and 335 to 350 (`definition_id`); `procedures.py` lines 322 to
391 (`parametric_specialization_name` digests `repr(TypeRef)`;
`proc_ref_specialization_name`); `normalized_type_descriptor.py` lines 102
to 175 (`_nominal_descriptor_name`: exported types get `module::Name`, a
non-exported type its bare name, found through the span's file path);
execution facts A.5; design §4.2 and P6.

**Interfaces:**
- Produces: `FrontendTypeEnvironment.declaring_module(type_ref: TypeRef) -> str | None`:
  the `defmodule` name of the module that declares the nominal type behind
  `type_ref` (`RecordDef`, `UnionDef`, `EnumDef`, `PathDef`, `SchemaDef`),
  exported or not. Implemented as a second map in `from_module`, keyed like
  `_nominal_descriptor_names_by_definition_id` (by `id(definition)`), for
  every definition kind. No dataclass of `definitions.py` gains a field:
  `repr(TypeRef)` includes the definition's repr and is digested into
  specialization names at every existing target.
- Produces, in `closed/names.py`:
  - `canonical_type_identity(type_ref: TypeRef, *, typed: TypedProgram) -> str`:
    a primitive by its name; a nominal type by `<declaring module>::<Name>`,
    the module found through `declaring_module` on the entry environment,
    then each `typed.module_type_envs` value, then the procedure and workflow
    environments; a `DiscriminantTypeRef` as `<union identity>.variant`;
    `ListTypeRef`/`OptionalTypeRef` as `List[<item>]`/`Optional[<item>]`; an
    applied union as `<template identity>[<arg identity>, ...]`. It never
    reads a span, a path or `repr`. A type whose module cannot be found
    raises `CanonicalNameError(type name)`; the builder reports it as a
    located compiler defect and repairs the declaring-module facts. Builtin
    and standalone types use their stable logical namespaces. Failure to
    name an admitted type is not a release exclusion.
  - `canonical_type_descriptor(type_ref, *, typed) -> dict`: reuse the
    normalized descriptor shape and recursively replace all nominal names
    from the declaring-module index, including nested fields, variants,
    applied arguments, list/optional members and private imported types.
    Register/check each nominal definition in the program `types` table.
    Preserve refinements/path roots. Do not change the old descriptor route.
  - `canonical_definition_key(definition, *, typed, binding_facts,
    capture_parameters, residual_signature) -> list`: construct the complete
    §4.2 tuple. Task 4 supplies checked closed value expressions and explicit
    capture parameters before calling this function. Procedure-reference
    facts include recursive target keys, residual signatures and every bound
    argument's formal/type/closed binding; workflow-reference facts include
    canonical workflow keys and resolved extern rebinding. Alpha-normalize
    bound value expressions, retaining tagged primitive kinds. Runtime capture
    facts identify owning formal/argument routes and types, not caller names
    or runtime values. Sort binding maps by formal, preserve ordered fields.
  - `canonical_callee_name(definition, *, key) -> str`: use `module::name`
    only for an unspecialized top-level definition; append full SHA-256 of
    canonical JSON key otherwise. Store `key` beside the body and refuse
    equal names with unequal keys as a compiler defect. A local definition
    uses `typed.local_definition_keys` and existing generated-local metadata,
    never `definition.name`'s span hash. No value/workflow/ref/capture form
    is turned into a release gap.
  - Generated run-ref types: use canonical input/result structural signatures
    when computing containing definition keys, then derive the final nominal
    name/site digest from that definition and its assigned local site. This
    is a two-pass finalization in Task 8, not a self-referential hash.
  - `Renamer`: `bind(name) -> str` returns the name unchanged unless it
    starts with `__`, in which case it returns and records `%<n>`, `n`
    counting from 1 per definition; `ref(name) -> str` returns the recorded
    rename or the name.
- Consumed by: Task 4.

- [ ] **Step 1: Write the failing tests**

Through `compile_typed_program` on `if_in_hook.orc` (it specializes
`std/improve::improve` with types of the entry module and two proc refs):

```python
def test_a_specialized_callee_is_named_by_its_base_and_canonical_arguments(tmp_path) -> None:
    typed = compile(tmp_path, fixture("if_in_hook"))
    (spec,) = [p for p in typed.procedures.values() if p.specialization is not None and p.specialization.base_name == "std/improve::improve"]
    key = canonical_definition_key(spec, typed=typed, **closed_binding_facts(spec))
    assert canonical_callee_name(spec, key=key) == "std/improve::improve[" + sha256(canonical_json(key)).hexdigest() + "]"
    # Inspect the tuple too: all four type bindings and both reference targets are retained.

def test_private_type_identities_and_descriptors_are_recursively_qualified(tmp_path) -> None:
    # Two imported modules each declare private Note, nested in exported records/unions/lists.
    # Their identities and descriptors differ by declared module, including entry/effect result fields.


def test_no_identity_holds_a_path_a_position_or_a_type_repr(tmp_path) -> None:
    for name in every_canonical_name(typed):
        assert str(tmp_path) not in name and "TypeRef" not in name and re.search(r"\.orc:\d+", name) is None

def test_moving_the_program_keeps_every_canonical_name(tmp_path) -> None:
    assert names(tmp_path / "here") == names(tmp_path / "elsewhere" / "deeper")

def test_generated_names_are_renumbered_per_definition() -> None:
    r = Renamer(); assert [r.bind("__wcc_anf_ab12"), r.bind("x"), r.bind("__wcc_effect_cd34"), r.ref("__wcc_anf_ab12")] == ["%1", "x", "%2", "%1"]
```

Add key tests for same base/types with different value substitutions,
workflow references, extern rebindings and bound proc-ref arguments: distinct
keys/names. Two runtime captures of one converted body share a key and have
different call values. Add let-proc same-name nested/sibling scope cases;
blank lines, relocation, pure-binding insertion/renaming change no local key.
Use existing bound-reference forwarding and let-proc fixtures; Task 4 adds
public-builder checks once conversion exists. No placeholder capture helper
is a production dependency of this task: key unit cases use explicit plain
binding facts; public integration follows in Task 4.

- [ ] **Step 2: Run; expected failures** `ImportError`; then missing binding
facts or bare private nominal names until implemented.

- [ ] **Step 3: Implement.** `declaring_module` first (a map beside the existing one), then recursive
descriptors and complete key/name functions in `names.py`. Do not reuse
`repr`, generated local names or raw typechecker run-ref result names.

- [ ] **Step 4: Run; expected pass.**

- [ ] **Step 5: Compatibility evidence**

The four programs of the table: byte-identical. `improve_experiment_proposal`
(2.33) and `review_revise_design_docs_judgment_panel` (2.23) are the ones
whose step ids and binding schema digests hold `repr(TypeRef)`: if
`type_env.py` changed a repr, they would differ.

- [ ] **Step 6: Commit**

`git add -- orchestrator/workflow_lisp/closed/names.py orchestrator/workflow_lisp/type_env.py tests/test_workflow_lisp_closed_program_names.py`

`git commit -m "feat: canonical callee and type identities for the closed program" -- orchestrator/workflow_lisp/closed/names.py orchestrator/workflow_lisp/type_env.py tests/test_workflow_lisp_closed_program_names.py`

**What this makes harder later:** two naming schemes coexist (digested
`%parametric-call.*` names for steps, canonical names for the closed
program) until Phase 7.

---

### Task 7: The Program Artifact, Its Digest, And The Manifest Field `closure`

**Files:**
- Create: `orchestrator/workflow_lisp/closed/program.py`
- Modify: `orchestrator/workflow_lisp/command_boundaries.py` (`ExternalToolBinding` line 80, `CertifiedAdapterBinding` line 129), `orchestrator/workflow_lisp/build_manifest_io.py` (`_parse_command_boundaries_manifest`, both `kind` branches; `_require_optional_string_array` exists)
- Modify: `orchestrator/workflow_lisp/stdlib_contracts.py` (checked-in builtin declarations), `orchestrator/workflow_lisp/compiler.py` (existing injection factories and `_augment_builtin_command_boundaries` origin carriage), `orchestrator/workflow_lisp/closed/frontend.py` (retain effective origins/configuration)
- Test: `tests/test_workflow_lisp_closed_program_artifact.py`, `tests/test_workflow_lisp_command_boundary_closure.py`

**Read first:** the spike's `sites.py` lines 35 to 78 (`ClosedProgram`,
`canonical_digest`, `strip_provenance`, `from_artifact`); design P6, P7,
§8.4 (the representation is part of the identity), C1, §13 (the field is
accepted and ignored at older targets); `build_manifest_io._json_data`
(line 921: honours `json_omit_if_none`); `compiler._command_boundary_fingerprint_payload`
(line 2380: explicit fields, so a new field does not enter the fingerprint
unless added there; do not add it).

**Interfaces:**
- Produces, in `closed/program.py`:
  - `SCHEMA = "workflow-lisp/closed-program/1"`, `REPRESENTATION = "table/1"`.
  - `@dataclass(frozen=True) class ClosedProgram: tree: dict; sites: tuple[tuple[str, str], ...]; digest: str`
    with `artifact() -> str` (canonical JSON of `tree`: `sort_keys=True`,
    `separators=(",", ":")`, `ensure_ascii=False`, `allow_nan=False`, one
    trailing newline; provenance included) and
    `@classmethod from_artifact(text: str) -> ClosedProgram` (parses, checks
    `schema` and `representation`, runs `check.validate`, rebuilds `sites`
    from the nodes' `site` keys and compares with `tree["sites"]`, computes
    the digest). A mismatch or a validation failure raises
    `ClosedProgramInvalid(code="closed_program_invalid", rule, location)`.
  - `canonical_digest(value) -> str` (`"sha256:" + hex` over the same
    canonical JSON) and `strip_provenance(node)`.
  - `program_digest(tree) -> str` = `canonical_digest(strip_provenance(tree))`
    (P7: `sites` are in the tree and enter the digest; `@` does not).
- Produces: `ExternalToolBinding.closure: tuple[str, ...] | None = field(default=None, metadata={"json_omit_if_none": True})`,
  the same on `CertifiedAdapterBinding`. Both parser branches preserve
  absence (`None`) versus `[]` (`()`); explicit `null` is invalid, not absence.
  Validate each path as a nonempty literal string without NUL; no globs,
  environment expansion or exclusions. Use the existing array validator only
  where its null/empty rules match, otherwise add the direct presence check.
  Add `canonical_command_configuration(bindings, *, origins)` in `program.py`: project
  all semantic fields of both boundary kinds, including adapter signature,
  protocol, return contract, stable argv, repeat rule and closure. Normalize
  closure separators and `.` components, retaining `..`, sort/deduplicate;
  relative paths use the command workspace, absolute declarations stay
  absolute. Do not use `posixpath.normpath` (it collapses `..` across symlinks).
  A simple component filter suffices; retain root `.` for an empty relative
  component sequence. No filesystem reads during compile. Emit sorted
  `{base, path}` rows: ordinary relative paths use `workspace`; absolute
  declarations use `absolute`; trusted injected relative paths use
  `package:orchestrator`. Apply the grammar to in-memory bindings too.
- Compiler-owned declarations are required, never exempt. Add the explicit
  checked-in `closure=(".",)` to `validate_review_findings_v1` beside its
  binding in `stdlib_contracts.py`; inventory other admitted injected command
  bindings in the existing compiler factories and give each an authoritative
  declaration there. The initial package-root declaration binds transitive
  compiler/contracts/I/O imports as well as the adapter; no import-discovery
  system or unknown empty declaration is introduced. Its accepted cost is
  divergence for unrelated package-file changes until a smaller closure is
  audited. Later excluded effect classes remain excluded as classes, but a
  reachable admitted command may not lack C1.
- Preserve trusted origin in `CommandBoundaryEnvironment` alongside
  `bindings_by_name` (a small origin map, default workspace for supplied
  bindings). Existing injection functions set package origin only for the
  binding instances they actually inject; preserve the map while rebuilding
  environments and carry it into `TypedProgram`. Never infer builtin origin
  from a matching name: a retained manifest override remains workspace-based.
  `configuration.commands` includes all supplied entries and every injected
  binding used by the closed program. No user field selects package origin,
  and no absolute installation prefix enters program identity.
- Keep `closure` out of old-target binding serialization/fingerprints even
  when explicitly supplied: inspect `_json_data` and every boundary payload
  producer, and omit it in the old route's projection, not globally in the
  model. The existing raw-manifest-byte cache hashing algorithm remains
  untouched. `json_omit_if_none` alone does not handle explicit closure.
- Runtime-only closure work belongs to Phase 3: workspace/symlink resolution,
  sorted file/directory content evidence (including dotfiles/caches),
  missing/unreadable/cyclic-path refusal and disjoint input/result/cache
  destinations. Phase 2 persists declarations sufficient for those rules;
  it neither hashes unavailable workspace contents nor adds exclusions.
  Phase 3 resolves `package:orchestrator` through the existing loaded-package/
  PYTHONPATH seam, binds package-relative evidence (external symlink targets
  remain absolute), and checks dispatch origin against that declared tree
  to prevent workspace/PYTHONPATH shadowing. Caches in evaluator and children
  must be disabled or outside the declared package; none are ignored.
- The refusal C1 itself (`command_boundary_closure_missing`) is Task 4's
  (`require_command_closures`), because it is a rule of the new target and
  Task 4 owns the command node; this task only carries the field.
- Consumed by: Task 4 (`ClosedProgram`, `program_digest`, `binding.closure`),
  Task 9 (`artifact()`, `from_artifact`).

- [ ] **Step 1: Write the failing tests**

On hand-written trees (reuse the tree helper of Task 5's test module by
importing it):

```python
def test_the_digest_leaves_provenance_out_and_the_artifact_keeps_it() -> None:
    a = tree_with_provenance("/here/x.orc"); b = tree_with_provenance("/elsewhere/deeper/x.orc")
    assert program_digest(a) == program_digest(b)
    assert ClosedProgram(a, sites, program_digest(a)).artifact() != ClosedProgram(b, sites, program_digest(b)).artifact()
    assert "/here/x.orc" in ClosedProgram(a, ...).artifact()

def test_the_artifact_reads_back_to_the_same_tree_sites_and_digest() -> None:

def test_a_tampered_operator_payload_is_refused_when_the_artifact_is_read() -> None:
    tree = json.loads(program.artifact())
    selected_op(tree)["payload"]["result_type"] = STRING_DESCRIPTOR
    text = json.dumps(tree)
    with pytest.raises(ClosedProgramInvalid) as e: ClosedProgram.from_artifact(text)
    assert (e.value.code, e.value.rule) == ("closed_program_invalid", "payload_invalid")

def test_another_representation_or_schema_is_refused_when_read() -> None:   # rule "representation"

def test_a_site_table_that_disagrees_with_the_nodes_is_refused() -> None:   # rule "sites"

def test_readback_refuses_non_operator_type_tampering() -> None:
    # Parameterize explicit JSON paths for perform.result, entry.result, list_map.type,
    # nested record field and call result/argument; recompute digest before readback.
    # Assert the corresponding checked-form rule, not just digest inequality.
```

`tests/test_workflow_lisp_command_boundary_closure.py`:

```python
def test_closure_is_parsed_into_the_binding_and_absent_is_none(tmp_path) -> None:
    payload = {"a": {"kind": "external_tool", "stable_command": ["python", "a.py"], "closure": ["lib/", "b.py"]},
               "b": {"kind": "external_tool", "stable_command": ["python", "b.py"]},
               "c": {"kind": "external_tool", "stable_command": ["python", "c.py"], "closure": []}}
    bindings = _parse_command_boundaries_manifest(payload, manifest_path=tmp_path / "commands.json")
    assert [bindings[n].closure for n in "abc"] == [("lib/", "b.py"), None, ()]

@pytest.mark.parametrize("kind", ["external_tool", "certified_adapter"])
def test_closure_grammar_and_canonicalization_for_both_kinds(kind) -> None:
    # Reject null, scalar, non-string, empty path and NUL; absence differs from [].
    # a//./b and a/b deduplicate; a/../b is retained; absolute and overlapping entries survive.
    # In-memory bindings obey the same rules; nonexistent paths need no compile-time reads.

def test_injected_adapters_keep_package_closure_and_manifest_overrides_keep_workspace_origin(tmp_path) -> None:
    # Use compile_typed_program (Task 2) plus canonical configuration projection here.
    # Task 4 adds full build/read-back for a std/phase path using validate_review_findings_v1:
    # closure == [{"base": "package:orchestrator", "path": "."}], no installed absolute prefix.
    # Grammar/origin tests run here; Task 4 adds removal of the authoritative declaration
    # and its located command_boundary_closure_missing refusal after injection.
    # A retained manifest override with the same name has workspace rows, not package rows.
    # Task 9 proves package relocation preserves the full artifact digest; declaration edits change it.

def test_at_2_34_a_manifest_with_closure_builds_the_artifacts_of_one_without(tmp_path) -> None:
    # the PROGRAM of test_workflow_lisp_target_234 at 2.34, built twice with the two manifests through `_build`;
    # Compare all semantic/binding artifacts byte-for-byte; only map the changed build key
    # and declared raw-manifest fingerprint/provenance fields. Assert closure is absent
    # even when supplied. Never broadly scrub a new semantic difference.
```

- [ ] **Step 2: Run; expected failures** `ImportError`; `AttributeError: closure`.

- [ ] **Step 3: Implement** the artifact, canonical configuration and
closure carriage/old-route omission in their existing owners.

- [ ] **Step 4: Run; expected pass.** Then `tests/test_workflow_lisp_build_manifest_io.py`
if it exists (find the manifest parser's owner tests with `rg -l _parse_command_boundaries_manifest tests`),
and `tests/test_workflow_lisp_target_234.py`.

- [ ] **Step 5: Compatibility evidence**

The four programs of the table, whose manifests lack the field:
byte-identical (old-target payload producers omit closure/origin even for
injected declarations; `json_omit_if_none` is sufficient only for absent
manifest declarations, and fingerprint payloads retain their old field set).

- [ ] **Step 6: Commit**

`git add -- orchestrator/workflow_lisp/closed/program.py orchestrator/workflow_lisp/command_boundaries.py orchestrator/workflow_lisp/build_manifest_io.py orchestrator/workflow_lisp/stdlib_contracts.py orchestrator/workflow_lisp/compiler.py orchestrator/workflow_lisp/closed/frontend.py tests/test_workflow_lisp_closed_program_artifact.py tests/test_workflow_lisp_command_boundary_closure.py`

`git commit -m "feat: the closed program artifact with its digest, and the command boundary closure field" -- orchestrator/workflow_lisp/closed/program.py orchestrator/workflow_lisp/command_boundaries.py orchestrator/workflow_lisp/build_manifest_io.py orchestrator/workflow_lisp/stdlib_contracts.py orchestrator/workflow_lisp/compiler.py orchestrator/workflow_lisp/closed/frontend.py tests/test_workflow_lisp_closed_program_artifact.py tests/test_workflow_lisp_command_boundary_closure.py`

**What this makes harder later:** a second representation (Phase 5 or later)
must keep `from_artifact` refusing the other one, and the run header must
carry `representation` (§8.4): Phase 3 reads it from the artifact.

---

### Task 4: The Builder: Bodies, Values, The Table, X1 To X4, Command Nodes

**Files:**
- Create: `orchestrator/workflow_lisp/closed/build.py` (bodies, bound values, calls, the table), `orchestrator/workflow_lisp/closed/values.py` (values, operators, surface objects), `orchestrator/workflow_lisp/closed/context.py` (X1, X2, X4), `orchestrator/workflow_lisp/closed/effects.py` (`require_command_closures`, `translate_perform` for `command_result`; every other kind raises `ClosedProgramGap` naming its form until Task 8 translates providers and run references)
- Modify: `orchestrator/workflow_lisp/typecheck_effects.py` (`typecheck_provider_bundle_path_expr`, line 1188: one gated condition, X4)
- Create: `tests/workflow_lisp_closed_program_helpers.py` (shared by Tasks 4, 8, 9, 10: `install`, `fixture`, `build`, `with_blank_lines`, `BOUNDARIES` with `closure=("probe.py",)` on every binding, `PROVIDERS`, `PROMPTS`, modelled on the spike's test helpers, importing none of the spike)
- Test: `tests/test_workflow_lisp_closed_program_build.py`, `tests/test_workflow_lisp_closed_program_context.py`

**Read first:** the spike's `closed.py` in full (its docstring says what it
supplied for each property), `table.py`; design §4.1 to §4.4, §9.2 (a call
is evaluation); `defunctionalize._lower_wcc_procedure_call` (line 6656:
how the flat route elaborates a callee body, with `_procedure_signature_local_type_bindings`
as the value env and `procedure_type_env_for`); `context_classification._is_run_context_shape`;
`WorkflowSignature.hidden_context_requirements` and
`PromotedEntryHiddenContextRequirement` (`phase.py` line 83: `param_name`,
`context_kind`, `phase_name`); `lowering/workflow_calls._runtime_context_default_value`
(line 181: the present route's constants `state/run`, `artifacts/run`,
`state/<phase>`, `artifacts/<phase>`); `typecheck_effects.typecheck_provider_bundle_path_expr`
(line 1188).

**Interfaces:**
- Consumes: `TypedProgram` (Task 2); `elaborate_typed_workflow_body(..., closed_program=True)`
  (Task 3); `sites.assign_sites`, `check.validate` (Task 5);
  `names.canonical_callee_name`, `canonical_type_identity`, `Renamer`
  and `canonical_type_descriptor`, `canonical_definition_key` (Task 6); `program.ClosedProgram`, `program_digest`, `SCHEMA`,
  `REPRESENTATION`, the bindings' `closure` field (Task 7).
- Produces: `build.build_closed_program(typed: TypedProgram) -> ClosedProgram`.
  Steps inside: `require_command_closures(typed.command_boundaries, manifest_path=None)`
  (C1, before any elaboration), build the entry definition
  (`Definition(canonical, owner, type_env, renamer)`), bind hidden context
  parameters of the entry as leading `let`s (X1), translate the body, attach
  each callee once by canonical name into `definitions` (memoized; a callee
  reached twice with two different bodies is a defect: raise `ValueError`,
  reported as `compiler_defect`), add canonical `types` and complete
  `configuration`, then `assign_sites`, `validate`, and `program_digest`.
  Task 8 later inserts generated run-ref finalization between site assignment
  and validation when it adds run-ref translation. The whole build runs under
  `compiler_defect_boundary(entry path)` so that an internal error is a
  `compiler_defect` located at the innermost node
  (`records_defect_provenance("closed-program")` on the body and value
  dispatchers).
- Produces, in `closed/effects.py`:
  - `require_command_closures(bindings: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding], *, manifest_path: Path | None) -> None`:
    raises `LispFrontendCompileError` with one diagnostic per boundary whose
    `closure is None`, `code="command_boundary_closure_missing"`, at the
    manifest path (`_cli_request_diagnostic`) when given, else at
    `command_boundaries._environment_span()`, message naming the boundary,
    `notes=(f"boundary={name}",)`. Check all supplied entries and used
    compiler-injected command boundaries; preserve the originating manifest
    or command-form location. Validate builtin declarations after injection
    and again before translating any generated admitted command. A builtin
    name is not an exemption. Require Task 7's origin-aware canonical rows;
    never substitute `[]` when declaration data is missing.
  - `translate_perform(builder: Builder, perform: WccPerform, d: Definition, env) -> dict`,
    for `perform_kind == "command_result"`: `boundary` = `payload["adapter_name"] or perform.target_name`;
    `command` = the binding's `stable_command`; `closure` = its canonical
    normalized declaration from `configuration.commands`;
    `contract` = `derive_prompt_guided_structured_result_contract(result type, workflow_name=d.canonical, step_id="effect", type_env=d.type_env, guidance=return_spec.guidance)`
    as `{kind, payload without "path" or source_map_subject}`; move the
    latter diagnostic subject under `@` rather than into program identity; `repeat` = `"never"` when
    `binding.must_not_repeat` else `"rerun"`; `argv` = the values after the
    stable tokens, or for a certified adapter `document` = `[[field.transport_key, value]]`
    in `input_signature` order over the declared inputs. Preserve currently
    admitted invocation protocols; malformed protocols keep their boundary
    validation diagnostic, and a missing admitted translation is a defect,
    not a new release exclusion. Every
    other `perform_kind`, and the binding values `WccProviderSupervision`
    and `WccProviderPeerGroup`, raise `ClosedProgramGap` with the surface
    form's name (`provider-result`, `run-ref`, `request-input`, `trial`,
    `run-provider-phase`, `produce-one-of`, `resume-or-start`,
    `finalize-selected-item`, `resource-transition`, `materialize-view`,
    `with-live-providers`, `with-live-provider-peers`); Task 8 replaces the
    first two with translations.
- Produces: `build.ClosedProgramGap(Exception)` with `form: str`, `message`,
  `span`, `form_path`; `build.gap_diagnostic(gap) -> LispFrontendDiagnostic`
  with `code="closed_program_gap"`, `message=f"`{form}` has no closed form in this release: {message}"`,
  `notes=(f"form={form}",)`, `phase="lowering"`, at the node's span.
  `build_closed_program` converts a gap into `LispFrontendCompileError` before
  the defect boundary sees it. Every refusal names the form in `notes`, so a
  test asserts `notes`, not the message.
- Produces the translation context Task 8 uses:

```python
@dataclass
class Definition:
    canonical: str            # the canonical callee name, or the entry's name
    owner: str                # the elaborator's owner name (definition.name)
    type_env: FrontendTypeEnvironment
    externs: Mapping[str, ProviderExtern | PromptExtern]  # declaring module plus resolved specialization rebinding
    renamer: Renamer
    loops: list[str]          # innermost last

class Builder:
    typed: TypedProgram
    def value(self, value: WccValue, d: Definition, env: Mapping[str, TypeRef]) -> dict: ...
    def desc(self, type_ref: TypeRef, d: Definition) -> dict: ...     # Task 6 recursive canonical descriptor; register nominal facts
    def body(self, node: WccBody, d: Definition, env) -> dict: ...
    def binding(self, value: WccBindingValue, d: Definition, env) -> dict: ...   # perform -> effects.translate_perform(self, ...), call -> self.call, workflow_call -> self.workflow_call
```

- Rules this task implements, each cited:
  - P1: `call` → `{"k": "call", "callee": canonical, "args": [...]}`; the
    callee's body elaborated once with `elaborate_typed_workflow_body(procedure.typed_body, owner_name=procedure.definition.name, type_env=typed.procedure_type_env(procedure), value_env=_procedure_signature_local_type_bindings(procedure), workflow_return_types=<every workflow's return type>, procedure_return_types=<every procedure's, generic templates excluded (case e)>, route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION, closed_program=True)`,
    normalized with `normalize_wcc_body_to_anf`, stored under
    `definitions[canonical] = {"key": key, "params": [[renamed param, descriptor]], "result": descriptor, "body": ...}`. A
    recursive call (the callee is on the active stack) is a `ClosedProgramGap`
    with form `call` ("recursive call"). `workflow_call` likewise, by the
    workflow's canonical name, with keyword arguments matched to parameters,
    a parameter the call leaves out taking its declared default (`lit`) or,
    when the signature has a hidden context requirement for it, the X1/X2
    value; a parameter with neither is a defect of the typechecker
    (`ValueError`).
  - Before P1 names are computed, convert existing `BoundProcArg`, value/
    workflow/reference specialization facts and generated local capture facts
    into closed bindings. Substituted compile-time expressions enter the full
    key; runtime captures become leading typed residual parameters with call
    arguments, evaluated once at their lexical binding before forwarding.
    Preserve the existing `_procedure_signature_local_type_bindings` and
    forwarding rules; never retain surface expressions or runtime refs in
    the artifact. Two captures of the same body share a definition; differing
    substitutions/reference targets/rebindings do not. The plain converted
    facts feed Task 6; no extra closure framework/module is needed.
  - P2: every `WccOpaqueFrontendValue` is translated in `values.py`:
    `UnionVariantTagExpr` → `lit`; `LoopStateSeedExpr` → `record` (type: the
    carrier descriptor); `LoopStateUpdateExpr` → `op` with a `record_update`
    payload; `ListExpr` → `list`; `CompilerListNonemptyHeadExpr` → `op` with
    the catalog's `list_nonempty_head` payload (`compiler_owned: true`,
    `invariant_diagnostic: "list_nonempty_invariant_broken"`);
    `ListMapExpr` → `list_map` (the body elaborated with
    `_elaborate_expr_to_body` under an env extended with the binder, as the
    spike's `frontend()` does, then translated; a body with `let`s becomes a
    `block`); `PathJoinUnderExpr` → `op` with a `path_join_under` payload
    (`path_type` = the descriptor of `path_type_ref`, `child` = `a0`);
    `IfExpr` (a module below 2.26 elaborated under the new target's rules)
    → `select`; `LetStarExpr` (an inlined pure call) → `block` or its value;
    `GeneratedRelpathSeedExpr` → `lit` of `literal_path`;
    `ProviderBundlePathExpr` with a `NameExpr` source → `result_path` (X4);
    `ResourceTransitionExpr` → `ClosedProgramGap` (form `resource-transition`).
    A `WccPhaseTargetAtom` reaching the builder is a defect (Task 3 elaborated
    it away): `ValueError`. A `WccPureOp` with operator `path/join` →
    `path_join`. Any other operator → `op` with a one-operator payload
    validated by `validate_pure_expr_payload` (P5).
  - X1: `context.run_context_value() -> dict` = the record
    `{run-id: {"k": "context", "field": "run-id"}, state-root: lit "state/run", artifact-root: lit "artifacts/run"}`
    with the `RunCtx` descriptor. Bound at the entry for each hidden context
    parameter of kind `RunCtx` as a leading `let <param> = <record>`; supplied
    at a workflow call that leaves such a parameter out.
  - X2: `context.phase_context_value(run: dict, phase_name: str) -> dict` =
    the record `{run: <run>, phase-name: lit phase_name, state-root: lit f"state/{phase_name}", artifact-root: lit f"artifacts/{phase_name}"}`.
    `run` is the caller's context value: the caller's parameter typed
    `RunCtx` as a `name`, or the `run` field of its parameter typed
    `PhaseCtx` (`field`), else `run_context_value()`. Its equality with the
    present route's value is the open item of this plan (design §19, 4).
  - X4: `result_path` carries the declared path descriptor. At the new
    target `typecheck_provider_bundle_path_expr` additionally requires the
    `:as` type's `under` to be `.orchestrate/runs` (the parent of every run
    root, `specs/state.md`), else `provider_bundle_path_target_invalid`;
    this one-line rule in `typecheck_effects.py`, gated by
    `target_dsl_uses_evaluated_execution(context.type_env.target_dsl_version)`,
    belongs to this task.
  - §4.3: a `halt` in a join's body is the join's value: `body()` translates
    it as `halt` and the evaluator (Phase 3) treats it so; nothing to do here
    beyond keeping `halt` in that position. `continue` → `{"k": "continue", "loop": d.loops[-1], ...}`
    only when the WCC node's `target_name` names that loop (Task 3
    guarantees it; a mismatch is a `ValueError`).
- Consumed by: Tasks 8, 9, 10.

- [ ] **Step 1: Write the failing tests**

Through `build(root, sources)` of the helpers module (`install`,
`compile_typed_program`, `build_closed_program`):

```python
def test_three_call_sites_of_one_procedure_are_one_definition_and_three_frames(tmp_path) -> None:
    closed = build(tmp_path, fixture("three_call_sites"))
    callee = "cp/three_call_sites::fetch"
    assert sorted(closed.tree["definitions"]) == [callee]
    assert closed.sites == ((callee, "#1"),)
    assert [c["frame"] for c in calls(closed.tree["body"])] == [f"{n}={callee}" for n in ("a", "b", "c")]

def test_one_procedure_in_three_arms_of_a_match_in_a_loop(tmp_path) -> None:      # Review focus 1
    assert closed.sites == ((callee, "#1"),)
    assert len(calls(closed.tree["body"])) == 3   # check each arm's loop/frame prefix separately

def test_the_program_holds_no_surface_object(tmp_path) -> None:
    for name in ("arms_in_loop", "loop_in_loop", "if_over_lists"):
        closed = build(tmp_path / name, fixture(name))
        validate(closed.tree)  # every node kind/child is in the closed schema
        assert_all_leaves_are_json_values(closed.tree)  # no frontend Expr/TypeRef objects

def test_an_effectful_argument_gives_two_frames_in_source_order(tmp_path) -> None:
    # (fetch (inc 4)): ordered frames #1=...::inc then #2=...::fetch;
    # sites are only the performs in the two callee definitions.

def test_all_reference_bindings_and_runtime_captures_close(tmp_path) -> None:
    # Public builds: same-base value/workflow specializations differ; bound proc refs forward;
    # one captured computation is bound once before two calls, both passing that same value;
    # nested let-proc captures work and no runtime ProcRef or surface Expr survives.

def test_imported_old_target_loop_in_branch_builds_without_flat_lowering(tmp_path) -> None:
    # Task 2's imported fixture now reaches ClosedProgram and passes from_artifact.

def test_private_nominals_remain_distinct_in_entry_effect_and_nested_descriptors(tmp_path) -> None:
    # Two imported private Note types are recursively module-qualified everywhere.

def test_used_injected_adapter_requires_its_declared_package_closure(tmp_path) -> None:
    # Full build/read-back of Task 7's injected adapter; remove declaration to assert
    # located command_boundary_closure_missing. A real manifest override keeps workspace base.

def test_a_loop_in_a_branch_and_a_loop_in_a_loop_build(tmp_path) -> None:
    assert build(tmp_path / "a", fixture("loop_in_branch")).sites and build(tmp_path / "b", fixture("loop_in_loop")).sites

def test_a_list_map_body_is_a_value_over_its_binder(tmp_path) -> None:
    # (list/map ((x xs)) (+ x 1)) -> {"k": "list_map", "binder": "x", "source": {...}, "body": {"k": "op", ...}}

def test_a_recursive_call_is_a_gap_at_the_call(tmp_path) -> None:
    # closed_program_gap, notes ("form=call",), at the recursive call's line;
    # if the typechecker already refuses the program, pin its code instead and say so in the report

def test_a_command_node_carries_its_boundary_closure_contract_and_repeat_rule(tmp_path) -> None:
    closed = build(tmp_path, fixture("three_call_sites"),
                   boundaries={"fetch": ExternalToolBinding("fetch", ("python", "probe.py"), closure=("probe.py",), must_not_repeat=True)})
    (node,) = performs(closed, "cp/three_call_sites::fetch")
    assert (node["class"], node["boundary"], node["command"], node["closure"], node["repeat"], node["contract"]["kind"]) == \
        ("command", "fetch", ["python", "probe.py"], [{"base": "workspace", "path": "probe.py"}], "never", "output_bundle")
    assert "path" not in node["contract"]["payload"]
    assert node["argv"] == [{"k": "lit", "v": "fetch"}, {"k": "name", "n": "n"}]

def test_a_boundary_without_closure_is_refused_before_elaboration(tmp_path) -> None:     # Review focus 3, C1
    with pytest.raises(LispFrontendCompileError) as e:
        build(tmp_path, fixture("three_call_sites"), boundaries={"fetch": ExternalToolBinding("fetch", ("python", "probe.py"))})
    (d,) = e.value.diagnostics
    assert (d.code, d.notes) == ("command_boundary_closure_missing", ("boundary=fetch",))

def test_a_certified_adapter_receives_one_document_in_signature_order(tmp_path) -> None:
    # a CertifiedAdapterBinding with input_signature (b, a) and invocation_protocol json_object_positional_arg,
    # called with :a and :b -> node["document"] == [["b", value_b], ["a", value_a]], node["argv"] == []

def test_a_form_outside_the_release_is_a_gap_naming_it(tmp_path) -> None:
    # one program with (materialize-view ...): code closed_program_gap, notes ("form=materialize-view",), at its line
```

`tests/test_workflow_lisp_closed_program_context.py`:

```python
def test_a_call_that_leaves_out_run_receives_the_run_context_record(tmp_path) -> None:
    # entry `entry` calls a workflow with a hidden `run : RunCtx`; the call's args hold the X1 record
    assert call["args"][i] == {"k": "record", "type": ANY_RUNCTX_DESC, "fields": [
        ["run-id", {"k": "context", "field": "run-id"}], ["state-root", {"k": "lit", "v": "state/run"}], ["artifact-root", {"k": "lit", "v": "artifacts/run"}]]}

def test_a_call_that_leaves_out_a_phase_context_receives_the_phase_record(tmp_path) -> None:
    # fields run (the caller's `run` name), phase-name "work", state-root "state/work", artifact-root "artifacts/work"

def test_the_entry_binds_its_own_hidden_run_context_first(tmp_path) -> None:
    assert closed.tree["body"]["k"] == "let" and closed.tree["body"]["name"] == "run" and "run" not in dict(closed.tree["params"])

def test_a_provider_bundle_path_is_a_result_path_typed_under_the_run_root(tmp_path) -> None:
    # (provider-bundle-path r :as ResultBundle) with (defpath ResultBundle :kind relpath :under ".orchestrate/runs" :must-exist false)
    # Test typechecking and value translation with a typed provider-result binding;
    # Task 4 does not yet translate the provider effect that produces it.
    # -> {"k": "result_path", "n": "r", "type": {...}}; with :under "state" -> provider_bundle_path_target_invalid at the form
    # Task 8 owns the complete provider-producing program build.
```

- [ ] **Step 2: Run; expected failures** `ImportError`, then gaps and
`ValueError`s as each translation is missing.

- [ ] **Step 3: Implement** in this order: `Definition` and `Builder.body`
for `let`/`halt`/`if`/`case`/`join`/`jump`/`loop`/`continue`/`done`;
`values.py` for atoms, ops, select, then each opaque kind; `effects.py`
(`require_command_closures`, the command node, the gaps); `call` and
`workflow_call` with the memoized table; `context.py`; the X4 typecheck
line; canonical type/config facts, sites, validation and digest at the end. Keep the existing responsibilities small;
add no modules solely to meet a line estimate.

- [ ] **Step 4: Run; expected pass.** Then Tasks 5, 6, 7 modules (they are
unchanged but their consumers are new).

- [ ] **Step 5: Compatibility evidence**

`typecheck_effects.py` changed (gated): build the four programs of the table;
byte-identical.

- [ ] **Step 6: Commit**

`git add -- orchestrator/workflow_lisp/closed orchestrator/workflow_lisp/typecheck_effects.py tests/workflow_lisp_closed_program_helpers.py tests/test_workflow_lisp_closed_program_build.py tests/test_workflow_lisp_closed_program_context.py tests/fixtures/workflow_lisp/closed_program`

`git commit -m "feat: build the closed program as a table of definitions with the run's context values" -- orchestrator/workflow_lisp/closed orchestrator/workflow_lisp/typecheck_effects.py tests/workflow_lisp_closed_program_helpers.py tests/test_workflow_lisp_closed_program_build.py tests/test_workflow_lisp_closed_program_context.py tests/fixtures/workflow_lisp/closed_program`

**What this makes harder later:** both target routes retain their own
elaboration consumers until flat-route retirement. Imported source modules
are never flat-lowered during an evaluated-entry build. Context-value runtime
parity remains Phase 3 evidence; any discrepancy must be repaired in the
small context translation, not hidden as a new exclusion.

---

### Task 8: Effect Nodes: Providers, Run References, And The Gaps

**Files:**
- Modify: `orchestrator/workflow_lisp/closed/effects.py` (created by Task 4 with the command node, the closure rule and the gaps), `orchestrator/workflow_lisp/closed/build.py` (call run-ref finalization after site assignment and before validation)
- Test: `tests/test_workflow_lisp_closed_program_effects.py`

**Read first:** the spike's `closed_effects.py` in full; design P3, §1.1
(the classes and the portable subset), §9.1 (inputs), §9.2 (bundle mode is
later), K7; lowering's `_lower_provider_result_operation`
(`lowering/effects.py` line 444: policy, prompt source, typed prompt inputs,
dependencies), `derive_prompt_guided_structured_result_contract`
(`contracts.py`), `typed_prompt_inputs.py` (how a typed prompt input is named
and which renderer it gets), `resolve_default_view_renderer`
(`orchestrator/workflow/view_renderer.py`), `run_ref/config.py`
(`build_run_ref_static_config`, `encode_run_ref_static_config`,
`ReferenceBinding`, `RunRefInput`), `run_ref/contracts.compute_compiler_runtime_identity`,
execution facts A.2 and A.4.

**Interfaces:**
- Consumes: Task 4's `translate_perform`, `Builder.value`, `Builder.desc`,
  `ClosedProgramGap`.
- Produces: two more branches of `translate_perform`, each a `perform` node
  of the schema:
  - `provider_result`: `provider` = `d.externs[target].provider_id`;
    `prompt` preserves `PromptExtern.source_kind` and exact bound `path`.
    `asset_file` carries the logical entry asset base used by the current
    lookup; `input_file` retains workspace/input lookup semantics. Never
    prepend an asset root or reinterpret an input file. Resolve imported
    extern rebindings through the typed module environment, not only the
    entry's alias map. For `defprompt`, emit template and the ordered typed
    slot rows defined above. Preserve `doc` references as required content
    injections (prepend, declaration order), with no renderer; other slots
    retain renderer, repeated placeholder positions, refinements and output
    roles/expected-output facts. Reuse semantic projections from
    `_build_compiler_prompt_fragment_contract` in `lowering/phase_scope.py`
    and `_lower_prompt_fragment_dependencies` without constructing flat steps
    or copying their step-id-based identity. `inputs` retains the established
    typed names, renderer selection and value expressions;
    `dependencies` from `WccPromptDependencyPayload` rows by role, with
    `position` and `instruction`; `policy` = each of `model`, `effort`,
    `delivery`, `materialization_attempts`, `timeout_sec` present in the
    payload, as values; `contract` derived as the command node derives it,
    from the declared result type; `repeat` = `"rerun"`. Payload parts `context_expr`,
    `session_artifact`, `capture_context` are gaps (form `provider-result`,
    naming the part: outside the portable subset, §1.1).
  - `run_ref`: path mode only. Translate inputs to closed typed values;
    retain source/program selection and supported static policy. First build
    a structural canonical input/result signature (recursively canonical
    descriptors, no current generated `RunRefResult$…` name). After sites
    are assigned, derive `site_digest` from the containing definition's
    canonical name and local site, derive the generated result name from
    that site and structural signature, and rewrite every occurrence in
    entry/definition/node descriptors and `types`. Then call
    `build_run_ref_static_config`/`encode_run_ref_static_config` with these
    canonical facts and `RunRefInput(..., ReferenceBinding(f"inputs.{name}"))`.
    Recompute result descriptor digests; never copy `payload.site_digest`,
    `payload.result_digest` or span-based generated names. The definition
    key uses the structural signature so finalization cannot create a hash
    cycle. Reuse `compute_compiler_runtime_identity` only after verifying
    its bytes are package-location independent. Decode/read-back validates
    the config against the containing site, canonical result and inputs.
    Bundle mode stays a located gap under §9.2. The Phase 3 caller adapter
    reuses the existing run-ref ledger/runtime; this does not claim its
    step-oriented caller integration works unchanged.
  - the gaps of Task 4 stay for every other kind, each named by its surface
    form; this task adds a test per form.
- Consumed by: Task 4's `binding()` (unchanged), Task 9, Task 10.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_provider_node_carries_prompt_inputs_policy_dependencies_and_contract(tmp_path) -> None:
    # provider_review.orc and prompt_dependency.orc: prompt source_kind/path/base; inputs [["draft", "<renderer>", {...}]];
    # policy {"model": lit, ...}; dependencies {"required": [...], "optional": [], "position": ..., "instruction": ...}

@pytest.mark.parametrize("source_kind", ["asset_file", "input_file"])
def test_prompt_source_selection_matches_the_existing_lookup(tmp_path, source_kind) -> None:
    # Put distinct sentinel bytes at the asset and workspace/input locations;
    # public compile preserves source_kind/path and the matching existing resolver
    # selects the same bytes as the old route. Assert source selection/content
    # digest, not authored prompt phrasing; neither source is silently coerced.

def test_a_defprompt_application_carries_its_template_and_fills(tmp_path) -> None:
    # Include doc, text, value, path and output-role slots; compare semantic
    # document dependencies/renderers/ordering/refinements/output facts with old lowering.

def test_path_run_ref_and_let_proc_ignore_formatting_and_location(tmp_path) -> None:
    # Public build after blank lines/comments and source/package relocation:
    # keys, generated names, decoded config/site_digest, sites and program digest equal.
    # Changing the actual input/result signature or bound source changes semantic identity.

def test_a_provider_bundle_path_builds_with_its_producing_provider(tmp_path) -> None:
    # Public build of the complete X4 program: provider effect plus result_path
    # with its declared .orchestrate/runs path descriptor, extending Task 4's value-only case.

def test_a_path_mode_run_ref_carries_the_static_config_with_reference_bindings(tmp_path) -> None:
    config = decode_run_ref_static_config(base64.b64decode(node["config"]))
    assert [(i.name, i.binding.reference) for i in config.inputs] == [("seed", "inputs.seed")]

@pytest.mark.parametrize("form", ["materialize-view", "resource-transition", "trial", "request-input", "with-live-providers", "run-provider-phase"])
def test_a_form_outside_the_release_is_a_gap_at_its_own_location(tmp_path, form) -> None:   # Review focus 4
    # one small program per form (write them inline; each typechecks at the new target)
    d = gap(tmp_path, PROGRAMS[form])
    assert (d.code, d.notes, d.span.start.line) == ("closed_program_gap", (f"form={form}",), LINES[form])

def test_a_provider_with_context_capture_and_a_bundle_run_ref_are_gaps(tmp_path) -> None:
```

- [ ] **Step 2: Run; expected failures** `closed_program_gap` with
`form=provider-result` and `form=run-ref` where nodes are expected; the
gap tests pass already (Task 4 raised them) and stay as the record.

- [ ] **Step 3: Implement** the existing effect dispatch, with helpers
`_provider`, `_prompt`, `_inputs`, `_dependencies`, `_run_ref` as needed.
Task 8 owns finalization of run-ref config/descriptors after Task 5 assigns
sites; keep this helper in `effects.py` and insert its call in
`build_closed_program` after `assign_sites` and before `validate` and
`program_digest`. Add the complete provider-producing X4 build check here.

- [ ] **Step 4: Run; expected pass.** Also Task 4's module (unchanged
behaviour for commands).

- [ ] **Step 5: Compatibility evidence:** no shared module touched; state so.

- [ ] **Step 6: Commit**

`git add -- orchestrator/workflow_lisp/closed/effects.py orchestrator/workflow_lisp/closed/build.py tests/test_workflow_lisp_closed_program_effects.py`

`git commit -m "feat: provider and run reference nodes in the closed program" -- orchestrator/workflow_lisp/closed/effects.py orchestrator/workflow_lisp/closed/build.py tests/test_workflow_lisp_closed_program_effects.py`

**What this makes harder later:** each later class replaces a gap branch.
Phase 3 still proves assembled prompt parity and run-ref caller integration;
Phase 2 must already preserve all assembly/contract facts, so that remaining
runtime evidence does not authorize dropping document slots or dependencies.

---

### Task 9: `orchestrator compile` At The New Target: The Build Key And The Artifact On Disk

**Files:**
- Create: `orchestrator/workflow_lisp/closed/artifact.py`
- Modify: `orchestrator/cli/commands/compile.py` (`compile_workflow`, before `normalize_frontend_artifact_exports` at line 63)
- Test: `tests/test_workflow_lisp_closed_program_compile_cli.py`

**Read first:** `build.py` lines 845 to 980 (`_build_frontend_bundle_in_memory`:
how the manifests are loaded and the request resolved), `build_manifest_io.py`
(`_resolve_request`, `_load_string_mapping`, `_load_prompt_extern_mapping`,
`_load_command_boundaries_manifest_payload`, `_parse_command_boundaries_manifest`),
`build_artifacts._fingerprint_build` (line 61: what the flat build key
digests), design P7, §8.4, C7.

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class ClosedProgramBuildResult:
    build_root: Path            # <workspace>/.orchestrate/build/<build key>
    build_key: str
    program: ClosedProgram
    artifact_path: Path         # build_root / "closed_program.json"
    manifest_path: Path         # build_root / "manifest.json"
    entry_workflow: str

def build_closed_program_bundle(request: FrontendBuildRequest) -> ClosedProgramBuildResult
def closed_build_key(*, target: str, entry_workflow: str, source_file_digests: Mapping[str, str],
                     provider_externs: Mapping[str, str], prompt_externs: Mapping[str, object],
                     command_boundary_manifest: Mapping[str, object]) -> str
```

  `build_closed_program_bundle` resolves the request as `build.py` does,
  loads the three manifests with the same loaders, calls
  `require_command_closures(parsed, manifest_path=request.command_boundaries_path)`,
  then `compile_typed_program` with a fresh `SourceReadTrace`, then `build_closed_program`, writes
  `closed_program.json` (`program.artifact()`) and `manifest.json`
  (`{"schema_version": "closed-program-build/1", "build_key", "program_digest", "representation", "target", "entry_workflow", "source_path", "source_roots", "sites": <count>, "artifact_paths": {"closed_program": "build/<key>/closed_program.json"}}`,
  written with `indent=2, sort_keys=True`). `closed_build_key` is
  `sha256(canonical JSON of its arguments)[:16]`; it holds no incidental
  source/install location (authored semantic paths remain). Source files are
  keyed by module name with content digests, taken from the
  exact compile via `typed.source_file_digests` from Task 2's traced API, so
  equivalent builds in relocated workspaces use the same key under each
  workspace's build root. Within one workspace, atomically replace cache
  artifacts only after a successful validated build; provenance can differ.
  A build cache is not the durable run authority of Phase 3.
- `compile_workflow`: after the `.orc` check, `target = entry_target_dsl_version(workflow_path)`;
  when `target_dsl_uses_evaluated_execution(target)`: any `--emit-*` flag
  is refused with `workflow_lisp_cli_input_unsupported` naming the flag
  (the flat artifacts do not exist at this target); otherwise call
  `build_closed_program_bundle` and print the summary
  `{"build_key", "build_root", "entry_workflow", "program_digest", "sites", "artifact_paths"}`;
  in machine mode print `{"status": "accepted", "program_digest": ..., "build_key": ...}`
  through `_print_machine_document`. Errors are handled by the same
  `except` clauses as today.
- Consumed by: Task 10 (the corpus builds through this function), Phase 3
  (`run` reads the checked artifact; resume freshly compiles current source/
  config and compares semantic program identity before memo access, then
  validates and executes the stored artifact).

- [ ] **Step 1: Write the failing tests**

Through `python -m orchestrator compile` in a subprocess with
`PYTHONHASHSEED=0` (the `_build` helper of `tests/test_workflow_lisp_target_234.py`
adapted: no `--emit-*` flags; the program is `PROGRAM` of that module at the
new target, with its actual task-owned probe scripts explicitly declared
in each manifest closure):

```python
def test_compile_writes_the_closed_program_and_its_manifest(tmp_path) -> None:
    summary, build_dir = compile_cli(files)
    program = ClosedProgram.from_artifact((build_dir / "closed_program.json").read_text())
    manifest = json.loads((build_dir / "manifest.json").read_text())
    assert (summary["program_digest"], manifest["program_digest"], manifest["build_key"]) == (program.digest, program.digest, build_dir.name)
    assert program.tree["entry"] == "grt/entry::run" and program.sites

def test_two_builds_of_one_source_at_two_paths_give_one_digest_and_one_build_key(tmp_path) -> None:   # Review focus 5, P7
    a = compile_cli(write(tmp_path / "here")); b = compile_cli(write(tmp_path / "elsewhere" / "deeper"))
    assert (a.digest, a.key) == (b.digest, b.key) and a.artifact != b.artifact     # provenance differs

def test_moving_the_orchestrator_package_changes_no_digest(tmp_path) -> None:
    # copy `orchestrator/` to tmp_path/package, run the CLI with PYTHONPATH there, as the spike's test did

@pytest.mark.parametrize("shape", ["specialized_import", "path_run_ref", "let_proc", "bound_capture"])
def test_blank_lines_and_comments_change_no_digest_and_no_site(tmp_path, shape) -> None:
    # Raw source digests/build key change; semantic program digest, generated names and sites do not.

def test_a_changed_stable_command_or_closure_changes_the_digest(tmp_path) -> None:    # C7

def test_an_unused_manifest_entry_changes_program_digest(tmp_path) -> None:
    # Both command kinds; also provider/prompt resolved configuration changes.
    # JSON whitespace/key order and normalized closure duplicates change no semantic digest.

def test_build_key_uses_the_same_compile_source_snapshot(tmp_path) -> None:
    # Mutate an import after its traced read; key uses consumed bytes, next build uses new bytes.

def test_an_emit_flag_is_refused_at_the_new_target(tmp_path) -> None:    # exit 2, workflow_lisp_cli_input_unsupported

def test_a_manifest_without_closure_is_refused_at_the_manifest_path(tmp_path) -> None:   # Review focus 3
    # exit 2; the diagnostic's span path is the manifest; code command_boundary_closure_missing

def test_the_same_manifest_builds_at_2_34_as_today(tmp_path) -> None:   # the other half of Review focus 3: `_build` of the 2.34 module passes
```

- [ ] **Step 2: Run; expected failures** the CLI builds the flat artifacts
at the new target (Task 2 made lowering skip, so `build_frontend_bundle`
fails on the missing bundle: a `RuntimeError` or `KeyError`, exit 2 with no
code); record it.

- [ ] **Step 3: Implement** `artifact.py` (about 130 lines) and the CLI
branch (about 30 lines).

- [ ] **Step 4: Run; expected pass.** Then `tests/test_workflow_lisp_target_234.py`
and the compile command's existing tests (`rg -l compile_workflow tests`).

- [ ] **Step 5: Compatibility evidence**

`compile.py` changed: the four programs of the table through the CLI;
byte-identical, and the printed summaries equal apart from the output
directory.

- [ ] **Step 6: Commit**

`git add -- orchestrator/workflow_lisp/closed/artifact.py orchestrator/cli/commands/compile.py tests/test_workflow_lisp_closed_program_compile_cli.py`

`git commit -m "feat: compile a program at the evaluated execution target to its closed program artifact" -- orchestrator/workflow_lisp/closed/artifact.py orchestrator/cli/commands/compile.py tests/test_workflow_lisp_closed_program_compile_cli.py`

**What this makes harder later:** two build functions and two manifest
schemas until Phase 7; Phase 3's `run` reads `closed_program.json` from the
build root by `build_key` and copies it beside `run.json` (§8.4).

---

### Task 10: The Corpus Check

**Files:**
- Create: `tests/workflow_lisp_closed_program_corpus.py` (helper, not collected), `tests/test_workflow_lisp_closed_program_corpus.py`

**Read first:** the spike's `census.py` (the corpus roots, how externs were
synthesized from checked-in manifests or the source: read it, do not import
it); the spike report iteration 3, D3 (38 of 52 built and the seven reasons);
design §18 first row; Phase 2 milestones P1, P2, P3.

**Interfaces:**
- Consumes: `build_closed_program_bundle` (Task 9) or `compile_typed_program`
  + `build_closed_program` in process (faster; choose in process).
- Produces: `corpus() -> list[Workflow]` over
  `workflows/examples`, `workflows/library`, `workflows/experiments`,
  `experiments/orc_vs_single_call`, `experiments/mlevolve_pair`: every
  exported workflow of every `.orc` file (52 today);
  `prepare(workflow, scratch) -> Prepared`: copies the file's source root to
  scratch, rewrites the entry's `(:target-dsl "...")` to the new target
  (imported modules keep theirs, §13), synthesizes the externs: providers
  from a checked-in manifest beside the workflow (`*providers*.json`) else
  `codex` for every provider name found in every module under the source
  root; prompts from a manifest else an empty file per prompt name; commands
  from a manifest else `["python", "<the leading literal words of :argv>"]`,
  and an explicit audited closure declaration for every fixture command.
  Do not synthesize an unknown `closure: []`: use checked-in known manifest
  declarations, compiler-owned declarations, or a task-owned stand-in script
  whose implementation is explicitly declared. Empty closure is only for a
  boundary whose empty promise is consciously authored. Record synthetic
  commands/prompts as compile-only evidence, never runtime parity. A boundary
  lacking enough signature/implementation facts to prepare is recorded as
  `not_synthesizable`, with the exact missing facts; it is not a new language
  gap, and the admission matrix must separately cover that supported form.
- Produces: `EXPECTED: dict[str, Outcome]` pinned per workflow: `built`
  (with its site count), `gap(form)`, `refused(code)` (a typecheck refusal
  the flat route gives too), `not_synthesizable`.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.parametrize("workflow", corpus(), ids=str)
def test_every_shipped_workflow_builds_a_closed_program_or_is_refused_by_a_gap_naming_the_form(tmp_path, workflow) -> None:
    prepared = prepare(workflow, tmp_path)
    outcome = try_build(prepared)          # Built(program) | Gap(form, line) | Refused(code) | NotSynthesizable
    assert outcome == EXPECTED[str(workflow)]
    if isinstance(outcome, Built):
        validate(outcome.program.tree)      # P1, P2; pure programs may have zero sites
        assert_perform_site_bijection(outcome.program)
        assert ClosedProgram.from_artifact(outcome.program.artifact()).digest == outcome.program.digest   # P5, P7

def test_the_partition_is_stated() -> None:
    counts = Counter(type(o).__name__ for o in EXPECTED.values())
    assert counts["Built"] >= 38                      # the spike built 38; X2 and X3 now build two more
    assert counts["Gap"] + counts["Refused"] + counts["NotSynthesizable"] + counts["Built"] == len(EXPECTED)
```

Write `EXPECTED` first from the spike's D3 table: `materialize-view` for
the five `validate-design-gap-architecture`, `-stdlib`,
`implementation-phase`, `run-plan-phase`, `run-work-item`;
`resource-transition` for `run-runtime-transition-fixture`,
`run-summary-view`, `apply-drain-status-transition`,
`emit-drain-status-transition-audit`; `trial` for
`qa_placement_trial::compare`; `refused(provider_phased_interactive_capability_missing)`
for `review-revise-design-docs-judgment-panel`; `refused(macro_arity_error)`
for `review-revise-parametric-design-docs`; `built` for the rest, including
`run-with-phase-composed-binding` and `lisp_frontend_design_delta::drain`
(X3 and X2 are built now). Where the run disagrees, the run wins: record the
actual outcome, and if a workflow that the spike built now fails, that is a
finding for the report, not an expectation to lower.

- [ ] **Step 2: Run; expected failures** the pinned outcomes that differ from
the actual ones; each is inspected before `EXPECTED` is corrected.

- [ ] **Step 3: Write the helper** (about 180 lines) and correct `EXPECTED`
from the run, with one line of justification per correction in the report.

- [ ] **Step 4: Run; expected pass.** Time the module; it should stay under
three minutes serial (38 builds at 0.1 to 0.3 s each plus typecheck).

- [ ] **Step 5: P3 evidence** (contracts and complete prompt assembly facts).

For `workflows/examples/improve_experiment_proposal.orc`, the two single-call
workflows, and dedicated input-file/document-slot fixtures, compile both
routes and compare each matched effect's runtime semantics. Remove only the
intentional transport output `path` (R3) and diagnostic `source_map_subject`/
source-map provenance, explicitly naming each ignored field. Keep all output
validation fields, renderer ids, slot kinds/types/order/output roles,
placeholder positions, policy and dependencies' ordered values, roles,
position and instruction. Normalize canonical private type names through the
known module mapping, never by deleting nominal distinctions. Compare prompt
source kind and lookup selection using distinct file contents. Counts alone
are not dependency parity. Reuse existing pure prompt/dependency projection
helpers where available; full executor-free prompt assembly and request
comparison through `run`/`resume` remain Phase 3 evidence. Test name:
`test_contracts_and_prompt_inputs_equal_the_flat_routes_for_the_real_programs`.

Add an explicit admission matrix alongside the shipped corpus: external-tool
and certified-adapter commands; both prompt source kinds; document/rendered/
output slots; plain/generic/value/workflow/ref-bound/captured/local calls;
path run-ref; all nested control edges in design §6. Include direct,
same-module-helper and imported-old-helper shapes for the formerly failing
positions. Every admitted matrix entry builds and round-trips; an internal
compiler failure is repaired, never added to `EXPECTED` as a new gap.

- [ ] **Step 6: Commit**

`git add -- tests/workflow_lisp_closed_program_corpus.py tests/test_workflow_lisp_closed_program_corpus.py`

`git commit -m "test: every shipped workflow builds a closed program or is refused by a gap naming the form" -- tests/workflow_lisp_closed_program_corpus.py tests/test_workflow_lisp_closed_program_corpus.py`

**What this makes harder later:** the pinned partition changes with every
Phase 4 class; the expectation table is the record of what the first release
covers.

---

### Task 11: Documents

**Files:**
- Modify: `specs/versioning.md` (the `v2.35 additions` block of Task 1: add what Phase 2 added), `specs/io.md` (a bullet under the deterministic artifact contracts: the command boundary manifest field `closure`, C1, C2's meaning at build, accepted and ignored below the new target), `docs/design/workflow_command_adapter_contract.md` (a section "Command closure declaration" beside "Command rerun behavior"), `docs/design/workflow_lisp_core_calculus_middle_end.md` (§10.1: the closed program's constructs and values at the new target, with a pointer to the schema of this plan; §11.4: identity at the new target is site and activation path, no lowering schema; §15: the deferred "authority inversion" is selected at gate G1; §16: remove the corresponding line), `docs/design/workflow_lisp_evaluated_execution.md` (Metadata status: Phase 2 implemented at the new target, the evaluator not; §4.1 table: the "Today" column becomes "Before Phase 2"), `docs/lisp_workflow_drafting_guide.md` (§2A: a paragraph after the table stating what a program at the new target gets today: `compile` builds the closed program, `run` refuses with `evaluated_execution_unavailable`, the forms refused by `closed_program_gap`, the `closure` field required), `docs/index.md` (the evaluated execution row: Phase 2 implemented; the Phase 2 plan row), `docs/design/README.md` (the design's status cell), `docs/capability_status_matrix.md` (one row: evaluated execution target, compile implemented, run future)
- Test: the existing document tests `tests/test_workflow_lisp_drain_roadmap_routing.py` (one known failure, `test_historical_q2_index_routes_current_selection_to_evolution_entry_gates`), `tests/test_monitor_docs.py`, and `tests/test_workflow_lisp_guide_programs.py` (the guide's quoted programs are unchanged)

- [ ] **Step 1:** Read each document's section named above and the
`documentation_conventions.md` checklist.
- [ ] **Step 2:** Write the changes. Every statement names the code or the
test that makes it true. No status word beyond "implemented", "refused",
"open".
- [ ] **Step 3:** Run the three test modules one at a time. Record the historical
known failure as baseline evidence, then repair any remaining failure in the
appropriate owner before closeout; never claim a failing selector passed.
- [ ] **Step 4:** Check every relative link of the touched documents resolves
(a ten-line script over `\[[^\]]*\]\(([^)#]+)` per file).
- [ ] **Step 5: Commit**

`git add -- specs docs`

`git commit -m "docs: record the closed program at the evaluated execution target" -- specs docs`

---

## Milestone Evidence

| Milestone | Evidence | Task |
| --- | --- | --- |
| P1. Callee bodies are part of the program | Every corpus workflow whose classes are in the release builds with one definition per canonical callee and no elaboration after `build_closed_program` returns; `three_call_sites` gives one definition and three frames | 4, 10 |
| P2. No surface object in a node | `check.validate` refuses an unknown `k`; every corpus tree is schema-valid JSON with no frontend objects (authored string contents are unrestricted) | 4, 5, 10 |
| P3. Effects carry contract, prompt assembly, policy and repeat rule | Command, provider and run-ref node tests; the contract and typed prompt inputs of the real programs equal the flat route's | 8, 10 |
| P4. The site table | Review focus 1 on `arms_in_loop`; one local perform site, call frames separate; total traversal and bijection | 4, 5 |
| P5. The normal form is checked when built | Every value/call/control/effect/entry type checked; operator and non-operator tampering refused on read | 5, 7 |
| P6. Provenance outside identity | Blank lines, a moved program and a moved package change no site and no digest; no name holds a path, a position or a type repr | 6, 9 |
| P7. The program is an artifact with a digest | Two builds at two paths share identity; unused semantic config edits change program digest; same-compile source bytes key the cache | 7, 9 |

## What Stays Open

- The number of the new target (parent plan, decision 6; design §19, 1):
  the owner sets it; Task 1 writes it once.
- Whether the compiler's `PhaseCtx` (X2) and `phase-target` (X3) values
  equal the present route's (design §19, 4): one program per form, run on
  both routes, once Phase 3 runs programs. Until then `context.py` follows
  the flat route's constants (`_runtime_context_default_value`).
- The rendering of prompt dependency snapshots (design §19, 5): Phase 3,
  when prompt assembly runs outside the executor; the `dependencies` node
  already carries all rows, slot kinds, values, policy and ordering needed
  to prove parity; Phase 3 verifies their actual rendering.
- Which forms outside the release the corpus uses, by count: Task 10's
  expectation table is the answer and the input to Phase 4's order.
- Whether a `list_map` value should instead be a catalog payload: decided
  here as a closed value over its binder (the evaluator extends the
  environment per item); Phase 3 may revisit if the catalog's own `list_map`
  is cheaper to evaluate.

## Verification Commands And Phase 3 Handoff

Run from the implementation worktree root. For each new/renamed test module,
collect it before the narrow test. Substitute a task-owned scratch path:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$PWD python -m pytest --collect-only -q -p no:cacheprovider tests/test_workflow_lisp_closed_program_frontend.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$PWD python -m pytest -q -p no:cacheprovider --basetemp=/tmp/phase2-task2/pytest tests/test_workflow_lisp_closed_program_frontend.py
```

Apply the same commands to each exact test module named in Tasks 1–10;
run existing owner selectors named in each task serially. Run Task 9's
provider/run-ref selectors after Task 8, then the corpus after both. Before
commit inspect `git diff --check` and the actual diff; stage/commit only the
listed paths (include an inspected adjacent owner only when necessary).

Compile smoke, from the worktree root after Task 9's helper installs its
selected-target source/manifests at `/tmp/phase2-smoke` (no flat emit flags):

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 PYTHONPATH=$PWD python -m orchestrator compile /tmp/phase2-smoke/grt/entry.orc --entry-workflow grt/entry::run --source-root /tmp/phase2-smoke --provider-externs-file /tmp/phase2-smoke/providers.json --prompt-externs-file /tmp/phase2-smoke/prompts.json --command-boundaries-file /tmp/phase2-smoke/commands.json
```

Task 9's subprocess fixtures must also compile a provider/run-ref specimen
using the same flags and task-owned manifests. Retain fresh exit 0, summary,
artifact read-back and perform/site bijection results. This public CLI
integration plus corpus round-trip is the Phase 2 orchestrator smoke; `run`
and `resume` intentionally remain unavailable and their no-launch refusal is
tested in Task 1. No external provider dispatch or Phase 3 evaluator is
needed for compile-only scope. The plan revision itself runs document checks,
not these future tests against nonexistent implementation modules.

Phase 3 consumes the checked `effect_class`, result contracts, full call/
capture/type facts, source-kind-preserving prompts, canonical configuration,
site/frame separation and position-free run-ref config. Its plan must retain
fresh compile versus header comparison before memo reads, stored-artifact
validation, preflight in journal order, durable `started` before allocation,
durable atomic header/program publication before `started`, closure evidence
checks before retrying uncommitted attempts, one atomic anchored suffix-
invalidation record, one external dispatch per memo attempt, run-ref settlement classification,
clean-terminal idempotence and profile-aware reader adapters. Closure content
hashes/symlink rules, interpreter pinning (no PATH re-resolution), caches
outside closure and output disjointness remain runtime work. No journal,
retry, terminal, trial-SDK or reader implementation enters this plan.

## Closeout

- [ ] Byte identity for the four programs of the table at the phase's head
  against the recorded `PHASE2_BASE`.
- [ ] Full suite in tmux, alone: `pytest -q -n 16 --dist=worksteal`,
  after narrow selectors pass. Record and resolve failures; do not weaken
  verification or accept a new failure by updating expectations.
- [ ] Fresh output: `python -m orchestrator compile` of
  `experiments/mlevolve_pair/search_compact.orc` retargeted, and of the
  `std/improve` example, at the new target; the summaries and the site
  counts in the report.
- [ ] The corpus table of Task 10 in the report, with the count built.
- [ ] Review by the repository Review role (Sol 6 high), with the owner's
  Critical-only gate above and every finding/evidence disposition recorded.
- [ ] Integrate according to the coordinator's authorized branch workflow;
  this document revision itself neither implements Phase 2 nor authorizes a
  target number, merge or push.
