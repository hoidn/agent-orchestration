# Workflow Lisp Evaluated Execution, Phase 2: The Closed Program Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` to execute this plan task by
> task, with `superpowers:test-driven-development` for every behaviour change
> and `superpowers:verification-before-completion` before any completion
> claim. One worktree per task. Tasks of one group touch disjoint files and
> run in parallel. Reviews are made by a reviewer of a model family other than
> the implementer's. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The compiler produces, for a program at the evaluated execution
target, the closed program that Phase 3's evaluator will run: whole,
calculus-only, with complete effect nodes, a site table, a checked form,
provenance outside identity, and a digest that is the program's identity.

**Architecture:** The pipeline at the new target stops after typecheck and
does not lower to steps. A new package `orchestrator/workflow_lisp/closed/`
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
the constructs, X1 to X4), 6 (I1 to I7), 7.3 (C1 as a manifest rule), 12
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
  2026-09-29. Base: the phase 0 branch at `613993ad`, which holds the revised
  design.
- Decision 6 of the parent plan, the number of the new target, is open. This
  plan writes `3.0` as the placeholder. Task 1 registers the target under
  the number the owner sets, in one constant; every later task and every
  fixture reads the number from that constant, never as a literal.
- In scope: the compiler's output at the new target and the manifest field
  `closure`. Out of scope, Phase 3 and later: the evaluator, the memo,
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
- No identity introduced by this plan contains a file path, a source position
  or the text of a type. `repr(TypeRef)` never enters a name or a digest of
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
- New modules stay under 500 lines and new functions under cyclomatic
  complexity 12. `wcc/elaborate.py`, `compiler.py` and `build.py` are large
  already: add the fewest lines there and put new logic under
  `orchestrator/workflow_lisp/closed/`.
- Commit by pathspec (`git commit -- <paths>`). Commit messages carry no tool
  or assistant attribution.
- The spike under `experiments/evaluated_execution_spike/` is read as the
  prototype and never imported by production code or by this plan's tests.
  Test fixtures needed from `tests/experiments/fixtures/evaluated_execution_spike/`
  are copied under `tests/fixtures/workflow_lisp/closed_program/`.

## Review Focus

Five input classes most likely to bite, each pinned by a test in the task
that owns the code.

1. One procedure called from three arms of one `match` inside a loop must
   give one site per arm, each with the frame `<binder>=<callee>` and the
   loop segment `loop:<param>[*]`, and the same three sites when the loop is
   moved into a called workflow. Task 5 tests it on `arms_in_loop.orc`; Task
   4 tests the table form gives one definition for the callee.
2. A program moved to another path, and the orchestrator package moved to
   another path, must give the same sites and the same program digest; the
   artifact's provenance may differ. Task 7 tests both moves with a
   subprocess, on a program with a specialized imported callee
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

Every task from 4 on reads and writes this schema. It is the contract between
tasks; a task that needs another key adds it here first.

### The program

```json
{
  "schema": "workflow-lisp/closed-program/1",
  "representation": "table/1",
  "target": "3.0",
  "entry": "grt/entry::run",
  "params": [["seed", {"kind": "primitive", "name": "Int"}]],
  "defaults": {"seed": 1},
  "result": {"kind": "record", "name": "grt/entry::Box", "fields": [...]},
  "body": <body>,
  "definitions": {"<canonical callee name>": {"params": ["n"], "body": <body>}},
  "sites": [["grt/entry::run", "a=grt/entry::fetch"], ["grt/entry::fetch", "#1"]]
}
```

- `params` lists the entry's declared parameters, hidden context parameters
  excluded (they are bound in the body, X1). `defaults` holds each declared
  default as its normalized value. Type descriptors are the compiler's
  normalized descriptors (`compiler_normalized_type_descriptor`), which name
  a type `module::Name` and hold no path.
- `definitions` holds one entry per canonical callee name (§4.2), procedures
  and called workflows alike. A body is stored once.
- `sites` is the site table (P4): `[definition, local path]` in program
  order, the entry first, then each definition in first-call order.

### Body nodes

| `k` | Keys | Rule |
| --- | --- | --- |
| `let` | `name`, `value` (a bound value), `body` | sequencing |
| `halt` | `value` | result of the definition, or of a `block` |
| `if` | `cond` (value), `then`, `else` (bodies) | strict `Bool` |
| `case` | `subject` (value), `arms`: `[{variant, bind, body}]` | variant elimination |
| `join` | `name`, `params` (names), `body`, `cont` | second-class continuation; a `halt` reached in `body` is the join's value (§4.3) |
| `jump` | `join`, `args` (values) | |
| `loop` | `name`, `param`, `budget` (value), `init` (value), `body`, `exhausted` (body or `null`), `code` | bounded iteration; `code` is the exhaustion diagnostic code |
| `continue` | `loop`, `args` (values) | names the loop it is in |
| `done` | `value` | |

### Bound values (the `value` of a `let`)

| `k` | Keys | Rule |
| --- | --- | --- |
| `perform` | `class`, `result` (descriptor), `repeat` (`"rerun"` or `"never"`), `site` (set by the site walker), and the class's keys below | one effect |
| `call` | `callee` (canonical name), `args` (values), `frame` (set by the site walker when the callee performs an effect) | evaluation of a definition's body (§9.2) |
| a value | | |

Effect classes of the first release (§1.1, §9.2):

| `class` | Keys |
| --- | --- |
| `command` | `boundary`, `command` (stable tokens), `closure` (list of paths from the manifest, C1), `contract` (`{kind, payload}` without a `path`), and either `argv` (values) or `document` (`[[transport_key, value]]` in signature order, for a certified adapter) |
| `provider` | `provider` (provider id), `prompt` (`{"asset": "<path relative to the source root>"}` or `{"template": "<text>", "fills": [[name, renderer_id, value]]}`), `inputs` (`[[name, renderer_id, value]]`, named as lowering names typed prompt inputs), `dependencies` (`{required: [values], optional: [values], position, instruction}` or `null`), `policy` (`{model, effort, delivery, materialization_attempts, timeout_sec}`, each present only when declared, as values), `contract` |
| `run_ref` | `config` (base64 of `encode_run_ref_static_config`, path mode only, inputs bound as the references `inputs.<name>`, K7), `inputs` (`[[name, value]]`) |

A workflow `call` is not a `perform`: it is a `call` node whose callee is the
workflow's canonical name (§9.2, "a call is evaluation").

### Values

| `k` | Keys | Rule |
| --- | --- | --- |
| `lit` | `v` | literal; a variant tag is a literal |
| `name` | `n` | |
| `field` | `base` (value), `path` (field names) | |
| `record` | `type` (descriptor), `fields` (`[[name, value]]`) | |
| `inject` | `type` (descriptor), `variant`, `fields` | |
| `op` | `payload` (a pure catalog payload, `pure_expr_schema_version` 2, bindings `a0..an`), `args` (values) | one catalog operator; `record_update`, `list_nonempty_head` and `path_join_under` are catalog node kinds |
| `select` | `cond`, `then`, `else`, each arm `{prefix: [{name, value}], value}` | conditional value |
| `list` | `items` (values) | |
| `list_map` | `binder`, `source` (value), `body` (value), `type` (descriptor of the result list) | `list/map` with a pure body; the body reads `binder` as a name |
| `path_join` | `base` (value), `child` (`lit`), `type` (path descriptor) | X3 for a generic `PhaseCtx`: the base path joined with a literal child, under the descriptor's root |
| `block` | `body` | a body evaluated for its value (§4.3) |
| `context` | `field` (`"run-id"`) | a value the run supplies (X1) |
| `result_path` | `n` (the binder of a provider effect), `type` (path descriptor) | the committed attempt's result file (X4) |

### Provenance

Every node that came from a source form carries `"@": {"span": "<path>:<line>:<column>", "form": [...]}`.
The path is the one the reader recorded, as the source map records it today.
`strip_provenance` removes every `@` key; the digest is taken over the
stripped tree (P6, P7).

### Names

- Generated binders (`__wcc_*`, `__spike_*`-style names from the elaborator)
  are renamed `%<n>` per definition, in order of binding. Authored names are
  kept.
- A canonical callee name is `module::name`, or for a specialization
  `base[K=<canonical type identity>, ..., ref=<canonical callee name>]` with
  keys sorted (§4.2). A canonical type identity is `module::Name` for a
  nominal type (the declaring module, exported or not), with applied
  arguments `Name[arg, ...]`, `List[...]`, `Optional[...]` recursively.
- A site's segments and ordinals follow I3 and I4: `then`, `else`, a `case`
  arm's variant, `loop:<param>[*]` (`loop[*]` when the param is generated),
  `loop:<param> / exhausted`, a join's binder when its body performs an
  effect, then the effect's own binder; an unnamed effectful binder takes
  `#<k>`; a repeated name takes `<name>#<k>`. Separator ` / `.

---

## Task Map

| Task | What | Group | Files it owns | Estimate (lines of code, tests excluded) |
| --- | --- | --- | --- | --- |
| 1 | The new target exists and refuses to run | A (alone, first) | `syntax.py`, `workflow/validation.py`, `run_ref/config.py`, `run_ref/bundle_transport.py`, `closed/__init__.py`, `closed/target.py`, `cli/commands/run.py`, `cli/commands/resume.py`, `specs/versioning.md`, `specs/dsl.md`, `specs/index.md` line 1, `tests/test_workflow_lisp_target_234.py` | 70; Task 0 of Phase 0 was 60 |
| 2 | The public compile entry that stops after typecheck | B (alone) | `closed/frontend.py`, `compiler.py` (`_compile_stage3_graph`), `workflows.py` (`Stage3CompileResult`) | 110; the spike's `frontend.py` is 97 by monkeypatch, the gate report estimates 20 for the seam |
| 3 | The elaborator at the new target | C | `wcc/model.py` (`WccIdentityFactory.closed_program`), `wcc/elaborate.py` | 100; gate report estimates 30 + 5 + 15 + 30 for `done` values, `continue`, arguments and `phase-target`, plus the flag |
| 5 | Sites and the checked form | C | `closed/sites.py`, `closed/check.py` | 250; spike measured 59 + 80 (sites) and 101 (validator) |
| 6 | Names that hold no path | C | `closed/names.py`, `type_env.py` (declaring module index) | 90; gate report estimates 60, spike measured 43 |
| 7 | The program artifact, its digest, and the manifest field `closure` | C | `closed/program.py`, `command_boundaries.py`, `build_manifest_io.py` | 130; spike measured 38 for the artifact, plus about 40 for the field |
| 4 | The builder: bodies, values, the table, X1 to X4, command nodes | D (alone) | `closed/build.py`, `closed/values.py`, `closed/context.py`, `closed/effects.py` (commands and the closure rule), `typecheck_effects.py` (one gated line), `tests/workflow_lisp_closed_program_helpers.py` | 520; spike measured 470 (`closed.py`) + 73 (surface objects) + 82 (table) + 40 (commands), less what Tasks 5 to 7 own |
| 8 | Effect nodes: providers, run references, the gaps | E | `closed/effects.py` | 160; spike measured 165 for all classes, gate report estimates 150 to 250 |
| 9 | `orchestrator compile` at the new target: the build key and the artifact on disk | E | `closed/artifact.py`, `cli/commands/compile.py` | 150; gate report estimates 100 |
| 10 | The corpus check | F | `tests/workflow_lisp_closed_program_corpus.py`, `tests/test_workflow_lisp_closed_program_corpus.py` | 180 (test helper); spike's census is 135 |
| 11 | Documents | F | `specs/versioning.md`, `specs/io.md`, `docs/design/workflow_command_adapter_contract.md`, `docs/design/workflow_lisp_core_calculus_middle_end.md`, `docs/design/workflow_lisp_evaluated_execution.md` (status lines), `docs/lisp_workflow_drafting_guide.md`, `docs/index.md`, `docs/design/README.md`, `docs/capability_status_matrix.md` | prose |

Order: A, then B, then C (Tasks 3, 5, 6 and 7 in parallel), then D, then E
(Tasks 8 and 9 in parallel), then F (Tasks 10 and 11 in parallel). Group C
runs in parallel because its four tasks touch disjoint files and consume
only the schema above and the interfaces of Tasks 1 and 2. Total estimate:
about 1,760 lines of production code. The spike's closed-program side
(`closed.py`, `closed_effects.py`, `sites.py`, `table.py`, `repairs.py`,
`frontend.py`) is 1,193 lines; the compiler's version carries the manifest
field, the build key, the CLI branch and the target, which the spike stood
in for.

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
- Modify: `specs/versioning.md` (a `v3.0 additions` block after the `v2.34` block at line 736, a roadmap line after line 816, a table row after line 967), `specs/dsl.md` line 23 (admitted revisions extend through `"3.0"`), `specs/index.md` line 1 (the title's range)
- Modify: `tests/test_workflow_lisp_target_234.py` (the gate dictionaries)
- Test: `tests/test_workflow_lisp_target_evaluated_execution.py`

**Read first:** `tests/test_workflow_lisp_target_234.py` in full; the Phase 0
Task 0 report's list of every place a version is compared (every gate is
"this target or newer", so the new target passes every 2.x gate with no
edit); design §13.

**Interfaces:**
- Produces: `syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION: str = "3.0"`
  (the placeholder; the owner's number replaces it here and nowhere else in
  code) and `syntax.target_dsl_uses_evaluated_execution(target_dsl_version: str) -> bool`
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
program: exit 2, same code). Add the `3.1` refusal
(`target_dsl_unsupported`, as `test_target_235_is_refused_as_unsupported`).

- [ ] **Step 2: Run them; expected failures**

`pytest -q tests/test_workflow_lisp_target_evaluated_execution.py`: the
registry tests fail with `'3.0' not in ...`, the gate test with
`AttributeError`, the run test with exit 0 and a command in the log (the
program lowers on the flat route because every gate is `>=`).

- [ ] **Step 3: Implement**

Add `"3.0"` to the four registries and to the end of `DEFAULT_VERSION_ORDER`.
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

`specs/versioning.md`: a block `v3.0 additions (in progress)` stating that
the target exists, that a program at it is compiled to a closed program and
not to steps, that `run` and `resume` refuse it with
`evaluated_execution_unavailable` until the evaluator lands, and that the
tasks of this plan add the closed program; a roadmap line; a table row.
`specs/dsl.md` line 23: admitted revisions extend through `"3.0"`.
`specs/index.md` line 1: the range (two tests compare it with the highest
supported version).

- [ ] **Step 6: Compatibility evidence**

Build the four programs of the table at the base and at the head. Expected:
every artifact byte-identical (the registries add a member; no gate changes).

- [ ] **Step 7: Commit**

`git commit -- orchestrator/workflow_lisp/syntax.py orchestrator/workflow/validation.py orchestrator/workflow/run_ref/config.py orchestrator/workflow/run_ref/bundle_transport.py orchestrator/workflow_lisp/closed orchestrator/cli/commands/run.py orchestrator/cli/commands/resume.py specs tests/test_workflow_lisp_target_234.py tests/test_workflow_lisp_target_evaluated_execution.py tests/test_workflow_shared_validation.py -m "feat: register the evaluated execution target and refuse to run it before the evaluator exists"`

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
    entry: TypedWorkflowDef
    workflows: Mapping[str, TypedWorkflowDef]          # every typed workflow of the graph, by canonical name
    procedures: Mapping[str, TypedProcedureDef]        # every typed procedure, specializations included
    type_env: FrontendTypeEnvironment                  # the entry module's
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment]
    workflow_type_envs: Mapping[str, FrontendTypeEnvironment]
    module_type_envs: Mapping[str, FrontendTypeEnvironment]   # module name -> its environment, whole graph
    command_boundaries: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding]
    externs: Mapping[str, ProviderExtern | PromptExtern]     # extern_environment.bindings_by_name
    target: str
    entry_module: str
    entry_dir: str      # the entry module's directory relative to the first source root, POSIX

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
) -> TypedProgram
```

  It calls `compile_stage3_entrypoint(...)` with `validate_shared=True`,
  `lowering_route=None`, and returns `result.entry_result.typed_program`.
  It raises `LispFrontendCompileError` with `evaluated_execution_target_required`
  at the `:target-dsl` span when the entry module's target does not use
  evaluated execution, and the typechecker's own diagnostics unchanged when
  the program does not typecheck.
- Produces: `Stage3CompileResult.typed_program: object | None = None`
  (a `TypedProgram` for a module at the new target, else `None`).
- Rule of `_compile_stage3_graph` at the new target (§13): the entry module,
  and every module of the graph whose own target uses evaluated execution,
  skip `_lower_workflows_for_route` and get `lowered_workflows=()`,
  `validated_bundles={}` and a `typed_program`. A module at an older target
  imported by the entry lowers as today (its bundle feeds the importer's
  `call` typecheck through `external_workflow_names`). The closed program
  elaborates the imported definitions again under the new target's rules
  (Task 3's flag), so their flat lowering is unused by the closed route.
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

def test_an_imported_module_at_an_older_target_is_lowered_and_its_procedures_are_typed(tmp_path) -> None:
    # if_in_hook imports std/improve (2.33): its validated bundle exists, and `std/improve::improve[...]`
    # specializations are in typed.procedures
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

In `_compile_stage3_graph`, before the `_lower_workflows_for_route` call:
`closed = target_dsl_uses_evaluated_execution(module_source.syntax_module.target_dsl_version)`.
When `closed`, do not lower; build the `TypedProgram` from the same
arguments the lowering call receives (`typed_workflows`,
`resolved_combined_procedures`, `typed_workflows_by_name`,
`combined_procedure_type_envs`, `workflow_type_envs_by_name`,
`extern_environment`, `command_boundary_environment`, `type_env`), plus
`module_type_envs` accumulated across the loop (a dict the loop fills with
`type_env` per module name) and `entry_dir`. Put the construction in
`closed/frontend.py` as `typed_program_from_graph(**kwargs) -> TypedProgram`
so `compiler.py` gains about ten lines. The graph stays entry-agnostic:
`typed_program_from_graph` sets `entry` to `None`, and
`compile_typed_program` resolves it after the compile: the export surface
of the entry module (`result.graph.export_surfaces_by_name[entry module].workflows_by_name`)
maps `entry_workflow` to its canonical name, which must be in
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

`git commit -- orchestrator/workflow_lisp/closed/frontend.py orchestrator/workflow_lisp/compiler.py orchestrator/workflow_lisp/workflows.py tests/fixtures/workflow_lisp/closed_program tests/test_workflow_lisp_closed_program_frontend.py -m "feat: a public compile entry that stops after typecheck at the evaluated execution target"`

**What this makes harder later:** `build_frontend_bundle` still expects a
validated bundle; Task 9 gives the closed route its own build function
rather than threading `None` through `_select_and_reattach` and `_emit`.
When Phase 7 retires the flat route, the two build functions merge.

---

### Task 3: The Elaborator At The New Target

**Files:**
- Modify: `orchestrator/workflow_lisp/wcc/model.py` (`WccIdentityFactory`, line 73)
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
  `NameExpr` or `FieldAccessExpr` (else `closed_program_gap`, form
  `with-phase`, "context expression is not a name"). Infer the context's
  type. If its record has the field `implementation_state_bundle_path`,
  return `WccFieldAccessAtom(base=<ctx as a name atom>, fields=(*ctx.fields, IMPLEMENTATION_ATTEMPT_TARGET_FIELDS[target]))`,
  typed by the record's field type (`type_env.record_field`). Otherwise return
  `WccPureOp(operator="path/join", args=(WccFieldAccessAtom(ctx, (..., "artifact-root")), WccLiteralAtom(f"{phase_name}/{suffix}", literal_kind="string")), field_names=())`
  with `suffix = PHASE_TARGET_SPECS[target][2]`, typed as
  `_build_phase_target_type(phase_name, target)`. `path/join` is an operator
  name only the closed builder reads (Task 4 maps it to the `path_join`
  value); the flat route never sees it.
- Rule 5 (case e, gate report §4): no elaborator change. The builder passes
  `procedure_return_types` without generic templates (Task 4).
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

Add: a `continue` whose state field holds an effect still binds it (the
2.33 rule is unchanged); the `#`-ordinal-relevant shape of Review Focus 1 is
not this task's.

- [ ] **Step 2: Run; expected failures**

`TypeError: unsupported WCC elaboration node: ProcedureCallExpr` for the
argument and `done` cases; `{"__wcc_current_loop__"}` for the `continue`
case; `WccPhaseTargetAtom` where a field access is expected.

- [ ] **Step 3: Implement the five rules**

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

`git commit -- orchestrator/workflow_lisp/wcc/model.py orchestrator/workflow_lisp/wcc/elaborate.py tests/test_workflow_lisp_closed_program_elaboration.py tests/fixtures/workflow_lisp/closed_program -m "feat: elaborate effectful arguments, done values, continue targets and phase-target for the closed program"`

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
  site table in program order. A `call`'s effectfulness is read from
  `tree["definitions"][callee]` (memoized). An unnamed binder is one that
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
  one of the schema's.
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
    assert table == [("cp/arms_in_loop::run", f"loop:state[*] / got / {arm} / #1=cp/arms_in_loop::fetch") for arm in ("FIRST", "SECOND", "THIRD")] \
        + [("cp/arms_in_loop::fetch", "#1")]
    assert [n["frame"] for n in calls(t)] == [f"loop:state[*] / got / {arm} / #1=cp/arms_in_loop::fetch" for arm in (...)]

def test_a_pure_binding_takes_no_ordinal_and_a_repeated_name_takes_a_counter() -> None:
    # lets: %1 = op, %2 = perform, x = perform, x = perform  ->  sites ["#1", "x", "x#2"]

def test_a_join_whose_body_performs_an_effect_is_a_segment_and_a_pure_join_is_not() -> None:

def test_a_call_of_a_pure_definition_gets_no_frame_and_no_site() -> None:

def test_the_exhaustion_body_is_its_own_segment() -> None:   # "loop:state / exhausted / e"
```

For `check.validate`, one test per rule, each tampering one node of a valid
tree and asserting `CheckedFormError.rule`: `unbound_name`, `jump_target`,
`continue_target` (a `continue` naming an outer loop from an inner loop),
`site_missing`, `site_duplicate`, `callee_unknown`, `call_cycle`,
`budget_missing`, `payload_invalid` (a `result_type` changed in an `op`
payload: the catalog refuses), `record_fields`, `node_kind`.

- [ ] **Step 2: Run; expected failure** `ImportError`.

- [ ] **Step 3: Implement** `sites.py` (about 130 lines) and `check.py`
(about 120 lines), each function under complexity 12: one method per node
kind, as the spike's `_Validator.tail_*`.

- [ ] **Step 4: Run; expected pass.** Collect-only on both modules.

- [ ] **Step 5: Compatibility evidence:** no shared module touched; state
so.

- [ ] **Step 6: Commit**

`git commit -- orchestrator/workflow_lisp/closed/sites.py orchestrator/workflow_lisp/closed/check.py tests/test_workflow_lisp_closed_program_sites.py tests/test_workflow_lisp_closed_program_check.py -m "feat: effect sites and the checked form of the closed program"`

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
    raises `CanonicalNameError(type name)`; the builder reports it as
    `closed_program_gap` (a type without a declaring module is a form the
    closed program cannot name).
  - `canonical_callee_name(procedure: TypedProcedureDef, *, typed: TypedProgram) -> str`:
    `procedure.definition.name` when `procedure.specialization is None`;
    else `f"{spec.base_name}[{', '.join(parts)}]"` with one `K=<identity>`
    per `spec.type_bindings` and one `key=<canonical callee name of the
    target procedure>` per `spec.proc_ref_bindings`, keys sorted; a
    specialization with `value_bindings` or `workflow_ref_bindings`, or a
    proc-ref with bound arguments, raises `CanonicalNameError` (reported as
    `closed_program_gap`, form `bind-proc`).
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
    assert canonical_callee_name(spec, typed=typed) == (
        "std/improve::improve[B=cp/if_in_hook::Note, F=cp/if_in_hook::Note, I=cp/if_in_hook::Brief, "
        "S=cp/if_in_hook::Candidate, review=cp/if_in_hook::review, revise=cp/if_in_hook::revise]")

def test_a_non_exported_type_is_named_by_its_declaring_module(tmp_path) -> None:
    # Note is not exported by cp/if_in_hook; the descriptor route names it `Note`, the identity `cp/if_in_hook::Note`

def test_no_identity_holds_a_path_a_position_or_a_type_repr(tmp_path) -> None:
    for name in every_canonical_name(typed):
        assert str(tmp_path) not in name and "TypeRef" not in name and re.search(r"\.orc:\d+", name) is None

def test_moving_the_program_keeps_every_canonical_name(tmp_path) -> None:
    assert names(tmp_path / "here") == names(tmp_path / "elsewhere" / "deeper")

def test_generated_names_are_renumbered_per_definition() -> None:
    r = Renamer(); assert [r.bind("__wcc_anf_ab12"), r.bind("x"), r.bind("__wcc_effect_cd34"), r.ref("__wcc_anf_ab12")] == ["%1", "x", "%2", "%1"]
```

- [ ] **Step 2: Run; expected failures** `ImportError`; then the bare
`Note` in the second test.

- [ ] **Step 3: Implement.** `declaring_module` first (a map filled beside
the existing one, about 15 lines), then `names.py` (about 80 lines).

- [ ] **Step 4: Run; expected pass.**

- [ ] **Step 5: Compatibility evidence**

The four programs of the table: byte-identical. `improve_experiment_proposal`
(2.33) and `review_revise_design_docs_judgment_panel` (2.23) are the ones
whose step ids and binding schema digests hold `repr(TypeRef)`: if
`type_env.py` changed a repr, they would differ.

- [ ] **Step 6: Commit**

`git commit -- orchestrator/workflow_lisp/closed/names.py orchestrator/workflow_lisp/type_env.py tests/test_workflow_lisp_closed_program_names.py -m "feat: canonical callee and type identities for the closed program"`

**What this makes harder later:** two naming schemes coexist (digested
`%parametric-call.*` names for steps, canonical names for the closed
program) until Phase 7.

---

### Task 7: The Program Artifact, Its Digest, And The Manifest Field `closure`

**Files:**
- Create: `orchestrator/workflow_lisp/closed/program.py`
- Modify: `orchestrator/workflow_lisp/command_boundaries.py` (`ExternalToolBinding` line 80, `CertifiedAdapterBinding` line 129), `orchestrator/workflow_lisp/build_manifest_io.py` (`_parse_command_boundaries_manifest`, both `kind` branches; `_require_optional_string_array` exists)
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
  the same on `CertifiedAdapterBinding`; the manifest key `closure`, an
  array of strings (workspace-relative paths of files and directories),
  parsed with `_require_optional_string_array` into the field; absent means
  `None`. An empty array is a declaration (`()`), not `None`.
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
    text = program.artifact().replace('"name":"Int"', '"name":"String"', 1)   # inside an op payload's result_type
    with pytest.raises(ClosedProgramInvalid) as e: ClosedProgram.from_artifact(text)
    assert (e.value.code, e.value.rule) == ("closed_program_invalid", "payload_invalid")

def test_another_representation_or_schema_is_refused_when_read() -> None:   # rule "representation"

def test_a_site_table_that_disagrees_with_the_nodes_is_refused() -> None:   # rule "sites"
```

`tests/test_workflow_lisp_command_boundary_closure.py`:

```python
def test_closure_is_parsed_into_the_binding_and_absent_is_none(tmp_path) -> None:
    payload = {"a": {"kind": "external_tool", "stable_command": ["python", "a.py"], "closure": ["lib/", "b.py"]},
               "b": {"kind": "external_tool", "stable_command": ["python", "b.py"]},
               "c": {"kind": "external_tool", "stable_command": ["python", "c.py"], "closure": []}}
    bindings = _parse_command_boundaries_manifest(payload, manifest_path=tmp_path / "commands.json")
    assert [bindings[n].closure for n in "abc"] == [("lib/", "b.py"), None, ()]

def test_a_closure_that_is_not_an_array_of_strings_is_refused() -> None:   # command_boundary_manifest_invalid, naming `closure`

def test_at_2_34_a_manifest_with_closure_builds_the_artifacts_of_one_without(tmp_path) -> None:
    # the PROGRAM of test_workflow_lisp_target_234 at 2.34, built twice with the two manifests through `_build`;
    # every artifact equal after mapping the build key (the fingerprint digests the manifest bytes as read;
    # that is today's rule for any manifest edit and is not changed here)
```

- [ ] **Step 2: Run; expected failures** `ImportError`; `AttributeError: closure`.

- [ ] **Step 3: Implement** `program.py` (about 90 lines); the field and its
parsing (about 25 lines).

- [ ] **Step 4: Run; expected pass.** Then `tests/test_workflow_lisp_build_manifest_io.py`
if it exists (find the manifest parser's owner tests with `grep -rl _parse_command_boundaries_manifest tests`),
and `tests/test_workflow_lisp_target_234.py`.

- [ ] **Step 5: Compatibility evidence**

The four programs of the table, whose manifests lack the field:
byte-identical (`json_omit_if_none` keeps every serialized binding the
same; the fingerprint payload lists fields explicitly).

- [ ] **Step 6: Commit**

`git commit -- orchestrator/workflow_lisp/closed/program.py orchestrator/workflow_lisp/command_boundaries.py orchestrator/workflow_lisp/build_manifest_io.py tests/test_workflow_lisp_closed_program_artifact.py tests/test_workflow_lisp_command_boundary_closure.py -m "feat: the closed program artifact with its digest, and the command boundary closure field"`

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
  (Task 6); `program.ClosedProgram`, `program_digest`, `SCHEMA`,
  `REPRESENTATION`, the bindings' `closure` field (Task 7).
- Produces: `build.build_closed_program(typed: TypedProgram) -> ClosedProgram`.
  Steps inside: `require_command_closures(typed.command_boundaries, manifest_path=None)`
  (C1, before any elaboration), build the entry definition
  (`Definition(canonical, owner, type_env, renamer)`), bind hidden context
  parameters of the entry as leading `let`s (X1), translate the body, attach
  each callee once by canonical name into `definitions` (memoized; a callee
  reached twice with two different bodies is a defect: raise `ValueError`,
  reported as `compiler_defect`), then `assign_sites`, `validate`,
  `program_digest`. The whole build runs under
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
    `notes=(f"boundary={name}",)`. Only boundaries the manifest or the
    caller supplied are checked; the compiler's builtin boundaries added by
    `_augment_builtin_command_boundaries` (resume, resource transitions) are
    outside the release and are not.
  - `translate_perform(builder: Builder, perform: WccPerform, d: Definition, env) -> dict`,
    for `perform_kind == "command_result"`: `boundary` = `payload["adapter_name"] or perform.target_name`;
    `command` = the binding's `stable_command`; `closure` = `list(binding.closure)`;
    `contract` = `derive_prompt_guided_structured_result_contract(result type, workflow_name=d.canonical, step_id="effect", type_env=d.type_env, guidance=return_spec.guidance)`
    as `{kind, payload without "path"}`; `repeat` = `"never"` when
    `binding.must_not_repeat` else `"rerun"`; `argv` = the values after the
    stable tokens, or for a certified adapter `document` = `[[field.transport_key, value]]`
    in `input_signature` order over the declared inputs (an adapter with an
    `invocation_protocol` other than `None`/`json_object_positional_arg` is
    a `ClosedProgramGap`, form `command-result`, naming the protocol). Every
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
    renamer: Renamer
    loops: list[str]          # innermost last

class Builder:
    typed: TypedProgram
    def value(self, value: WccValue, d: Definition, env: Mapping[str, TypeRef]) -> dict: ...
    def desc(self, type_ref: TypeRef, d: Definition) -> dict: ...     # compiler_normalized_type_descriptor; DiscriminantTypeRef -> enum descriptor
    def body(self, node: WccBody, d: Definition, env) -> dict: ...
    def binding(self, value: WccBindingValue, d: Definition, env) -> dict: ...   # perform -> effects.translate_perform(self, ...), call -> self.call, workflow_call -> self.workflow_call
```

- Rules this task implements, each cited:
  - P1: `call` → `{"k": "call", "callee": canonical, "args": [...]}`; the
    callee's body elaborated once with `elaborate_typed_workflow_body(procedure.typed_body, owner_name=procedure.definition.name, type_env=typed.procedure_type_env(procedure), value_env=_procedure_signature_local_type_bindings(procedure), workflow_return_types=<every workflow's return type>, procedure_return_types=<every procedure's, generic templates excluded (case e)>, route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION, closed_program=True)`,
    normalized with `normalize_wcc_body_to_anf`, stored under
    `definitions[canonical] = {"params": [renamed params], "body": ...}`. A
    recursive call (the callee is on the active stack) is a `ClosedProgramGap`
    with form `call` ("recursive call"). `workflow_call` likewise, by the
    workflow's canonical name, with keyword arguments matched to parameters,
    a parameter the call leaves out taking its declared default (`lit`) or,
    when the signature has a hidden context requirement for it, the X1/X2
    value; a parameter with neither is a defect of the typechecker
    (`ValueError`).
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
    assert closed.sites == ((entry, f"a={callee}"), (entry, f"b={callee}"), (entry, f"c={callee}"), (callee, "#1"))

def test_one_procedure_in_three_arms_of_a_match_in_a_loop(tmp_path) -> None:      # Review focus 1
    assert closed.sites == tuple((entry, f"loop:state[*] / got / {arm} / #1={callee}") for arm in ("FIRST", "SECOND", "THIRD")) + ((callee, "#1"),)

def test_the_program_holds_no_surface_object(tmp_path) -> None:
    for name in ("arms_in_loop", "loop_in_loop", "if_over_lists"):
        text = build(tmp_path / name, fixture(name)).artifact()
        assert "Expr" not in text and "opaque" not in text

def test_an_effectful_argument_gives_two_sites_in_source_order(tmp_path) -> None:
    # (fetch (inc 4)): sites [(entry, "#1=cp/...::inc"), (entry, "#2=cp/...::fetch"), ...]

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
        ("command", "fetch", ["python", "probe.py"], ["probe.py"], "never", "output_bundle")
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
    # -> {"k": "result_path", "n": "r", "type": {...}}; with :under "state" -> provider_bundle_path_target_invalid at the form
```

- [ ] **Step 2: Run; expected failures** `ImportError`, then gaps and
`ValueError`s as each translation is missing.

- [ ] **Step 3: Implement** in this order: `Definition` and `Builder.body`
for `let`/`halt`/`if`/`case`/`join`/`jump`/`loop`/`continue`/`done`;
`values.py` for atoms, ops, select, then each opaque kind; `effects.py`
(`require_command_closures`, the command node, the gaps); `call` and
`workflow_call` with the memoized table; `context.py`; the X4 typecheck
line; sites, validate, digest at the end. Keep `build.py` and `values.py`
each under 500 lines; `context.py` is about 60, `effects.py` about 80 here.

- [ ] **Step 4: Run; expected pass.** Then Tasks 5, 6, 7 modules (they are
unchanged but their consumers are new).

- [ ] **Step 5: Compatibility evidence**

`typecheck_effects.py` changed (gated): build the four programs of the table;
byte-identical.

- [ ] **Step 6: Commit**

`git commit -- orchestrator/workflow_lisp/closed orchestrator/workflow_lisp/typecheck_effects.py tests/workflow_lisp_closed_program_helpers.py tests/test_workflow_lisp_closed_program_build.py tests/test_workflow_lisp_closed_program_context.py tests/fixtures/workflow_lisp/closed_program -m "feat: build the closed program as a table of definitions with the run's context values"`

**What this makes harder later:** callee bodies are elaborated twice for an
imported module at an older target (once by the flat route for its bundle,
once here); Phase 7 removes the first. A `PhaseCtx` derived from an item
context (`std/drain`) is built by the same rule as any other, and if the
owner's experiment finds the present route's value differs, only
`context.py` changes.

---

### Task 8: Effect Nodes: Providers, Run References, And The Gaps

**Files:**
- Modify: `orchestrator/workflow_lisp/closed/effects.py` (created by Task 4 with the command node, the closure rule and the gaps)
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
  - `provider_result`: `provider` = `typed.externs[target].provider_id`;
    `prompt` = `{"asset": posixpath.normpath(posixpath.join(typed.entry_dir, extern.path))}`
    (the asset path relative to the source root, as the flat route reads it
    relative to the entry module; program content, not provenance) or
    `{"template": application.prompt.declaration.template.text, "fills": [[fill.name, fill.renderer_id, value]]}`
    (a fill without a renderer id, a document slot, is a gap, form
    `defprompt`); `inputs` = `[[name, renderer_id, value]]` with the name the
    last field of a field access, the variable's name, or `"inputs"`, and
    the renderer `resolve_default_view_renderer("path_value" if path else "any_pure_value").renderer_id`;
    `dependencies` from `WccPromptDependencyPayload` rows by role, with
    `position` and `instruction`; `policy` = each of `model`, `effort`,
    `delivery`, `materialization_attempts`, `timeout_sec` present in the
    payload, as values; `contract` derived as the command node derives it,
    from the declared result type; `repeat` = `"rerun"`. Payload parts `context_expr`,
    `session_artifact`, `capture_context` are gaps (form `provider-result`,
    naming the part: outside the portable subset, §1.1).
  - `run_ref`: path mode only; `config` = base64 of
    `encode_run_ref_static_config(build_run_ref_static_config(compiler_runtime_identity_digest=compute_compiler_runtime_identity().digest, site_digest=payload.site_digest, source=payload.source, program=payload.program, inputs=<one RunRefInput per input with ReferenceBinding(f"inputs.{name}")>, result_descriptor=payload.result_descriptor, result_digest=payload.result_digest, target_dsl_version=typed.target))`;
    `inputs` = `[[name, value]]`; bundle mode is a gap (form `run-ref`,
    "bundle mode is a later release", §9.2).
  - the gaps of Task 4 stay for every other kind, each named by its surface
    form; this task adds a test per form.
- Consumed by: Task 4's `binding()` (unchanged), Task 9, Task 10.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_provider_node_carries_prompt_inputs_policy_dependencies_and_contract(tmp_path) -> None:
    # provider_review.orc and prompt_dependency.orc: prompt {"asset": "cp/review.md"}; inputs [["draft", "<renderer>", {...}]];
    # policy {"model": lit, ...}; dependencies {"required": [...], "optional": [], "position": ..., "instruction": ...}

def test_a_defprompt_application_carries_its_template_and_fills(tmp_path) -> None:

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

- [ ] **Step 3: Implement** (about 160 lines, one function per class:
`_provider`, `_prompt`, `_inputs`, `_dependencies`, `_run_ref`).

- [ ] **Step 4: Run; expected pass.** Also Task 4's module (unchanged
behaviour for commands).

- [ ] **Step 5: Compatibility evidence:** no shared module touched; state so.

- [ ] **Step 6: Commit**

`git commit -- orchestrator/workflow_lisp/closed/effects.py tests/test_workflow_lisp_closed_program_effects.py -m "feat: provider and run reference nodes in the closed program"`

**What this makes harder later:** each later class (Phase 4) replaces one
gap branch with a translation; the prompt dependency rendering (design §19,
5) is decided when Phase 3 assembles prompts, and may add a key to the
`dependencies` node.

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
  then `compile_typed_program`, then `build_closed_program`, writes
  `closed_program.json` (`program.artifact()`) and `manifest.json`
  (`{"schema_version": "closed-program-build/1", "build_key", "program_digest", "representation", "target", "entry_workflow", "source_path", "source_roots", "sites": <count>, "artifact_paths": {"closed_program": "build/<key>/closed_program.json"}}`,
  written with `indent=2, sort_keys=True`). `closed_build_key` is
  `sha256(canonical JSON of its arguments)[:16]`; it holds no path (source
  files are keyed by module name with their content digests, taken from the
  compile's `SourceReadTrace` as `_source_file_digests_from_trace` does), so
  two builds of one source at two paths share one build directory, which
  the second overwrites (the artifacts differ only in provenance).
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
  (`run` reads the artifact).

- [ ] **Step 1: Write the failing tests**

Through `python -m orchestrator compile` in a subprocess with
`PYTHONHASHSEED=0` (the `_build` helper of `tests/test_workflow_lisp_target_234.py`
adapted: no `--emit-*` flags; the program is `PROGRAM` of that module at the
new target, with `closure: []` added to its manifest):

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

def test_blank_lines_and_comments_change_no_digest_and_no_site(tmp_path) -> None:

def test_a_changed_stable_command_or_closure_changes_the_digest(tmp_path) -> None:    # C7

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
and the compile command's existing tests (`grep -rl compile_workflow tests | head`).

- [ ] **Step 5: Compatibility evidence**

`compile.py` changed: the four programs of the table through the CLI;
byte-identical, and the printed summaries equal apart from the output
directory.

- [ ] **Step 6: Commit**

`git commit -- orchestrator/workflow_lisp/closed/artifact.py orchestrator/cli/commands/compile.py tests/test_workflow_lisp_closed_program_compile_cli.py -m "feat: compile a program at the evaluated execution target to its closed program artifact"`

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
  and `closure: []` added to every command boundary that lacks it (a
  certified adapter with no manifest cannot be synthesized: the workflow is
  recorded as `not_synthesizable`).
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
        assert outcome.program.sites and "Expr" not in outcome.program.artifact()      # P1, P2
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

- [ ] **Step 5: P3 evidence** (contract and prompt assembly equal to the flat
route's): for `workflows/examples/improve_experiment_proposal.orc` and the
two single-call workflows, compile at their own target through
`compile_stage3_entrypoint` and read, per provider and command step, the
lowered step's `output_bundle`/`expected_outputs` contract (without `path`)
and its `typed_prompt_inputs` rows (name and renderer); assert they equal
the closed program's `contract` and `inputs` for the same effect (matched
by canonical name and binder). Prompt dependency rows are compared by count
and role only (their rendering is the open item, design §19, 5). Add this as
`test_contracts_and_prompt_inputs_equal_the_flat_routes_for_the_real_programs`.

- [ ] **Step 6: Commit**

`git commit -- tests/workflow_lisp_closed_program_corpus.py tests/test_workflow_lisp_closed_program_corpus.py -m "test: every shipped workflow builds a closed program or is refused by a gap naming the form"`

**What this makes harder later:** the pinned partition changes with every
Phase 4 class; the expectation table is the record of what the first release
covers.

---

### Task 11: Documents

**Files:**
- Modify: `specs/versioning.md` (the `v3.0 additions` block of Task 1: add what Phase 2 added), `specs/io.md` (a bullet under the deterministic artifact contracts: the command boundary manifest field `closure`, C1, C2's meaning at build, accepted and ignored below the new target), `docs/design/workflow_command_adapter_contract.md` (a section "Command closure declaration" beside "Command rerun behavior"), `docs/design/workflow_lisp_core_calculus_middle_end.md` (§10.1: the closed program's constructs and values at the new target, with a pointer to the schema of this plan; §11.4: identity at the new target is site and activation path, no lowering schema; §15: the deferred "authority inversion" is selected at gate G1; §16: remove the corresponding line), `docs/design/workflow_lisp_evaluated_execution.md` (Metadata status: Phase 2 implemented at the new target, the evaluator not; §4.1 table: the "Today" column becomes "Before Phase 2"), `docs/lisp_workflow_drafting_guide.md` (§2A: a paragraph after the table stating what a program at the new target gets today: `compile` builds the closed program, `run` refuses with `evaluated_execution_unavailable`, the forms refused by `closed_program_gap`, the `closure` field required), `docs/index.md` (the evaluated execution row: Phase 2 implemented; the Phase 2 plan row), `docs/design/README.md` (the design's status cell), `docs/capability_status_matrix.md` (one row: evaluated execution target, compile implemented, run future)
- Test: the existing document tests `tests/test_workflow_lisp_drain_roadmap_routing.py` (one known failure, `test_historical_q2_index_routes_current_selection_to_evolution_entry_gates`), `tests/test_monitor_docs.py`, and `tests/test_workflow_lisp_guide_programs.py` (the guide's quoted programs are unchanged)

- [ ] **Step 1:** Read each document's section named above and the
`documentation_conventions.md` checklist.
- [ ] **Step 2:** Write the changes. Every statement names the code or the
test that makes it true. No status word beyond "implemented", "refused",
"open".
- [ ] **Step 3:** Run the three test modules one at a time; expected: the
one known failure only.
- [ ] **Step 4:** Check every relative link of the touched documents resolves
(a ten-line script over `\[[^\]]*\]\(([^)#]+)` per file).
- [ ] **Step 5: Commit**

`git commit -- specs docs -m "docs: record the closed program at the evaluated execution target"`

---

## Milestone Evidence

| Milestone | Evidence | Task |
| --- | --- | --- |
| P1. Callee bodies are part of the program | Every corpus workflow whose classes are in the release builds with one definition per canonical callee and no elaboration after `build_closed_program` returns; `three_call_sites` gives one definition and three frames | 4, 10 |
| P2. No surface object in a node | `check.validate` refuses an unknown `k`; the artifact of every built corpus workflow contains no `Expr` and no `opaque` | 4, 5, 10 |
| P3. Effects carry contract, prompt assembly, policy and repeat rule | Command, provider and run-ref node tests; the contract and typed prompt inputs of the real programs equal the flat route's | 8, 10 |
| P4. The site table | Review focus 1 on `arms_in_loop`; sites split into frames and a local site | 4, 5 |
| P5. The normal form is checked when built | One tampering test per rule; a tampered payload refused on read | 5, 7 |
| P6. Provenance outside identity | Blank lines, a moved program and a moved package change no site and no digest; no name holds a path, a position or a type repr | 6, 9 |
| P7. The program is an artifact with a digest | Two builds at two paths give one digest and one build key | 7, 9 |

## What Stays Open

- The number of the new target (parent plan, decision 6; design §19, 1):
  the owner sets it; Task 1 writes it once.
- Whether the compiler's `PhaseCtx` (X2) and `phase-target` (X3) values
  equal the present route's (design §19, 4): one program per form, run on
  both routes, once Phase 3 runs programs. Until then `context.py` follows
  the flat route's constants (`_runtime_context_default_value`).
- The rendering of prompt dependency snapshots (design §19, 5): Phase 3,
  when prompt assembly runs outside the executor; the `dependencies` node
  carries the rows and their position and may gain a key then.
- Which forms outside the release the corpus uses, by count: Task 10's
  expectation table is the answer and the input to Phase 4's order.
- `bind-proc` specializations with captures, value bindings or workflow-ref
  bindings, and proc refs with bound arguments: gaps in the first release
  (Task 6); whether any maintained workflow needs them is read from the
  corpus table.
- Whether a `list_map` value should instead be a catalog payload: decided
  here as a closed value over its binder (the evaluator extends the
  environment per item); Phase 3 may revisit if the catalog's own `list_map`
  is cheaper to evaluate.

## Self-Review Record

Spec coverage: §1.1 (`closed_program_gap`): Tasks 4, 8, 10. §4.1 P1 to P7:
the milestone table. §4.2 (table, canonical names): Tasks 4, 6. §4.3
(constructs, elaboration rules): Tasks 3, 4. §4.4 X1 to X4: Task 4 (X3's
elaboration in Task 3). §6 I1 to I7: Task 5 (I5 to I7 are run-time rules;
I6's text is produced from a site and frames by Phase 3). §7.3 C1: Tasks 4,
7, 9. §12 codes: `closed_program_gap` (4, 8), `command_boundary_closure_missing`
(4, 9), `evaluated_execution_unavailable` (1; not in the design's table,
added by this plan for the interval before Phase 3, and to be recorded in
the design by Task 11). §13: Tasks 1, 2, 7. Placeholder scan: no "TBD",
no "similar to": each task repeats what it needs. Type consistency:
`TypedProgram`, `Definition`, `Builder`, `ClosedProgram`, `assign_sites`,
`validate`, `translate_perform`, `require_command_closures`,
`canonical_callee_name`, `canonical_type_identity`, `Renamer`,
`build_closed_program`, `build_closed_program_bundle`, `closed_build_key`,
`entry_target_dsl_version`, `target_dsl_uses_evaluated_execution` are named
the same in every task that uses them. Review focus: each of the five lines
names its owning task and test.

## Closeout

- [ ] Byte identity for the four programs of the table at the phase's head
  against `613993ad`.
- [ ] Full suite in tmux, alone: `pytest -q -n 16 --dist=worksteal`,
  compared with the failure set of `613993ad`; no new failures.
- [ ] Fresh output: `python -m orchestrator compile` of
  `experiments/mlevolve_pair/search_compact.orc` retargeted, and of the
  `std/improve` example, at the new target; the summaries and the site
  counts in the report.
- [ ] The corpus table of Task 10 in the report, with the count built.
- [ ] Review of the phase by a reviewer of a model family other than the
  implementers'.
- [ ] Merge to `main` by fast-forward; push.
