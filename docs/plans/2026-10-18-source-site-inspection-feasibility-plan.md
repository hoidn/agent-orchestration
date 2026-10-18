# Source-Site Inspection Feasibility And Manifest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove or refute, with executable fixtures on real compiler products, that per-node WCC metadata joins authored sites to closed-program site rows (prerequisite P-1 and fixture F-a), and if proven, implement the read-only source-site manifest `orchestrator/workflow_lisp/source_sites.py` with fixtures F-b through F-e.

**Architecture:** One new module that consumes `prepare_closed_program_bundle` output: callee bodies come from the builder's retained preparations (`Builder.completed_preparations`, `CallableRequest.prepared_body`), the entry body from one re-elaboration through `Builder._command_wcc_body` with the arguments `_build_with_builder` uses; authored expression nodes are walked from each definition's `typed_body.expr`, joined to WCC value nodes by `(path, line, column)` of `metadata.source_span.start`, and to closed-program perform nodes by their `@` start. No typechecker, lowering, CLI flag or artifact change.

**Tech Stack:** Python 3.13; `orchestrator.workflow_lisp` frontend, WCC model and closed builder; pytest.

**Spec:** `docs/design/workflow_lisp_source_site_inspection.md` (§2 carriers, §3 manifest, §7 fixtures P-1 and F-a to F-e, §9 verification); consumer contract in `docs/design/orc_structural_search_driver.md`.

## Global Constraints

- Work in `/home/ollie/Documents/agent-orchestration-search` on branch `feat/orc-structural-search`; run from that root with `PYTHONPATH=/home/ollie/Documents/agent-orchestration-search`.
- The module is read-only: it never writes a build, a run, a REPL command or a `compile` flag, and it never re-infers types from text; every fact comes from the retained build (`result.typed_program`, `result.stage3`, `result.builder`, `result.program`).
- No optimizer vocabulary in the module or its tests (no fitness, archive, selection, candidate scoring); `candidate_id` is not computed here.
- `site_id` = `<owner canonical name>@<path relative to root>:<line>:<column>`, matching `experiments/orc_structural_search/candidates.py`.
- Unknown facts are reported as `"unavailable"` with an exclusion reason; nothing is guessed.
- Commits use pathspecs, no assistant attribution, no `Co-Authored-By` trailer.
- Any `orchestrator/` change runs the narrow selectors first, then `pytest -q -n 16 --dist=worksteal` in tmux before the final commit (check `df -h /tmp` first).

## Review Focus

1. Two WCC nodes can share one `source_span.start` (a `WccLet` and its `bound_value`); the join must prefer the value node for `result_type` and `executable_sites`, and the let for the binder (Task 2 test `test_let_and_bound_value_share_start_but_record_uses_value_node`).
2. A definition the builder never prepares for the selected entry has no WCC facts; its sites must be reported `facts-unavailable`, not omitted silently (Task 2 test `test_unprepared_definition_sites_are_marked_unavailable`).
3. The `@` provenance path is absolute; two candidate roots with the same file name must not collide and relative paths must be computed against the given root (Task 2 test `test_site_ids_are_relative_to_root`).
4. A file the caller did not name contributes no sites and appears only as a dependency (Task 2 test `test_unnamed_files_contribute_only_dependencies`).
5. Re-elaborating the entry body must not mutate the builder or change a later `build_closed_program` artifact (Task 1 test `test_entry_reelaboration_leaves_artifact_bytes_unchanged`).

---

### Task 1: Probe P-1 and F-a on real compiler products

**Files:**
- Create: `tests/test_workflow_lisp_source_sites_probe.py`
- Create (only on failure): `docs/reports/2026-10-18-source-site-inspection-probe.md`

**Interfaces:**
- Consumes: `prepare_closed_program_bundle(request: FrontendBuildRequest, *, source_read_trace=None) -> ClosedProgramBuildResult` (`orchestrator/workflow_lisp/closed/artifact.py`; result fields `typed_program`, `stage3`, `builder`, `program`, `build_key`); `FrontendBuildRequest(source_path, source_roots, entry_workflow, provider_externs_path, command_boundaries_path, workspace_root)` (`orchestrator/workflow_lisp/build.py`); `Builder.completed_preparations` and `Builder.prepared_by_key` holding `CallableRequest`/`WorkflowRequest` with `prepared_body: WccBody` (`orchestrator/workflow_lisp/closed/build.py`); `Builder._command_wcc_body(callable_def, source_program, *, type_env, value_env, ...)`; `WccNodeMetadata` on `.metadata` (`orchestrator/workflow_lisp/wcc/model.py`); `_ast_nodes` (`orchestrator/contracts/closed_program/node_walk.py`) and `ClosedProgram.sites`; the generic dataclass walk pattern in `orchestrator/workflow_lisp/closed/build.py::_wcc_workflow_calls`.
- Produces: a helper module-level function in the test file, later moved to the module: `wcc_value_nodes(body) -> list[object]` (generic dataclass walk over `WccBody`, yielding every node that has a `.metadata` attribute, skipping the `metadata` field itself).

- [ ] **Step 1: Write the probe tests**

```python
EXAMPLES = ["workflows/examples/plan_review_execute.orc", "workflows/examples/improve_experiment_proposal.orc"]

@pytest.mark.parametrize("source", EXAMPLES)
def test_every_closed_perform_start_matches_one_wcc_perform_and_one_site_row(source):
    result = compile_in_process(source)           # FrontendBuildRequest with the example's providers.json
    bodies = owner_wcc_bodies(result)             # dict owner canonical name -> WccBody: callees from completed_preparations, entry re-elaborated
    starts = {}                                   # (path, line, column) -> [WccPerform nodes]
    for owner, body in bodies.items():
        for node in wcc_value_nodes(body):
            if isinstance(node, WccPerform):
                starts.setdefault(key(node.metadata.source_span.start), []).append((owner, node))
    perform_rows = closed_perform_rows(result.program)   # [(owner, site_label, "@".span)]
    assert perform_rows, "fixture must contain perform nodes"
    for owner, site, span in perform_rows:
        assert len(starts.get(parse_span(span), [])) == 1
        assert (owner, site) in result.program.sites

def test_retained_callee_bodies_equal_reelaborated_bodies_node_for_node(): ...   # improve_experiment_proposal: node_id sequences equal
def test_entry_reelaboration_leaves_artifact_bytes_unchanged(): ...               # build_closed_program before/after re-elaboration byte-identical
def test_reelaboration_cost_is_recorded(capsys): ...                              # prints elapsed per owner against the compile; assert < 3x compile wall clock
```

- [ ] **Step 2: Run the probe**

Run: `pytest tests/test_workflow_lisp_source_sites_probe.py -q`
Expected: PASS. On any failure, do not weaken the assertions: write `docs/reports/2026-10-18-source-site-inspection-probe.md` with the failing assertion, the observed counts and the gap, commit it, and stop this plan (Tasks 2 to 4 are not executed; report back).

- [ ] **Step 3: Commit**

```bash
git commit -m "test: probe WCC metadata joins for source-site inspection (P-1, F-a)" -- tests/test_workflow_lisp_source_sites_probe.py
```

### Task 2: The manifest module with bindings, shadowing and the executable-site join

**Files:**
- Create: `orchestrator/workflow_lisp/source_sites.py`
- Create: `tests/fixtures/workflow_lisp/source_sites/shadowing.orc` (a workflow with nested `let*` forms rebinding `x` around a provider call) and `shared_procedure.orc` (two workflows calling one procedure that contains a provider call), each with a `providers.json`
- Test: `tests/test_workflow_lisp_source_sites.py`

**Interfaces:**
- Consumes: Task 1 helpers; `canonical_type_identity(type_ref, *, typed)` and `render_type_ref` (`orchestrator/workflow_lisp/closed/names.py`, `type_env.py`); `walk_expr` (`orchestrator/workflow_lisp/expression_traversal.py`); node classes `ProviderResultExpr`, `RunProviderPhaseExpr`, `AgentExpr`, `ProcedureCallExpr`, `CallExpr`, `RunRefExpr` (`orchestrator/workflow_lisp/expressions.py`); `procedure_effect_inspection` (`orchestrator/workflow_lisp/procedures.py`); `SourceReadRecord.revision` digests via `result.typed_program.source_file_digests`.
- Produces: `build_manifest(result: ClosedProgramBuildResult, *, root: Path, files: Sequence[Path]) -> dict` returning a JSON-serializable mapping `{"build_key", "program_digest", "target", "entry", "file_digests": {rel_path: "sha256:..."}, "sites": {site_id: record}}`; each record has the keys `site_id`, `span` (`{"start": {"path","line","column","offset"}, "end": {...}}`), `file_digest`, `owner` (`{"kind","name","form_path"}`), `kind` (one of `provider-call`, `provider-phased-call`, `agent-turn`, `procedure-call`, `workflow-call`, `run-ref`, `let*`, `if`, `cond`, `match`, `loop`, `list-map`), `result_type` (`{"canonical","rendered"}` or `"unavailable"`), `bindings` (list of `{"name","identity","type"}` in scope order, innermost last), `dependencies` (`{"prompts":[...],"providers":[...],"commands":[...],"modules":[...],"callees":[...]}`), `effects` (`{"inferred": "...rendered...", "restriction": "...|omitted"}`), `executable_sites` (list of `[owner, site_label]`), `authored_calls` (list of `{"callee_kind","callee_name"}`), `eligibility` (`"eligible"` or one of `macro-generated`, `loop-control`, `generated-definition`, `pure-call-unretained`, `facts-unavailable`).
- Bindings: walk the owner's WCC body carrying the chain of enclosing `WccLet` nodes; a binding row is `(bound_name, binding_identity, canonical_type_identity(bound_type_ref))`, prefixed by the owner's parameters from its signature; the innermost occurrence of a repeated name wins.

- [ ] **Step 1: Write the failing tests**

```python
def test_feedback_site_lists_task_and_draft_with_canonical_types():            # F-b on plan_review_execute
    m = manifest("workflows/examples/plan_review_execute.orc")
    site = site_of(m, kind="provider-call", line=29)
    names = {b["name"]: b["type"] for b in site["bindings"]}
    assert "task" in names and names["draft"].endswith("Plan")
def test_let_and_bound_value_share_start_but_record_uses_value_node(): ...
def test_shadowed_name_resolves_to_innermost_identity():                        # F-e
    m = manifest(FIXTURES / "shadowing.orc"); inner, outer = ...
    assert inner_x_identity != outer_x_identity
def test_shared_procedure_site_reports_exactly_the_closed_rows_with_its_start(): # F-d: executable_sites equals the closed rows whose @ start matches; owner stays the procedure; no row is invented
def test_executable_sites_of_pure_composition_is_empty(): ...
def test_unprepared_definition_sites_are_marked_unavailable(): ...
def test_site_ids_are_relative_to_root(tmp_path): ...                           # same file name under two roots
def test_unnamed_files_contribute_only_dependencies(): ...
def test_manifest_is_json_serializable_and_keys_sorted(): ...
def test_result_type_equals_repl_type_for_closed_expression(): ...              # a call with only literal inputs; compare with typecheck_repl_expression
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_workflow_lisp_source_sites.py -q`
Expected: FAIL with `ModuleNotFoundError: orchestrator.workflow_lisp.source_sites`

- [ ] **Step 3: Implement `source_sites.py`**

Public function `build_manifest`; private helpers for the owner-body map (move `owner_wcc_bodies` and `wcc_value_nodes` here and import them from the probe test), the authored walk, the join and the binding chain. Join key is `(path, line, column)`; `offset` is reported from the frontend span only.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_workflow_lisp_source_sites.py tests/test_workflow_lisp_source_sites_probe.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: read-only source-site manifest over the in-memory checked build" -- orchestrator/workflow_lisp/source_sites.py tests/test_workflow_lisp_source_sites.py tests/test_workflow_lisp_source_sites_probe.py tests/fixtures/workflow_lisp/source_sites
```

### Task 3: Authored procedure calls that survive inline normalization (F-c)

**Files:**
- Create: `tests/fixtures/workflow_lisp/source_sites/inlined_procedure.orc` (a workflow calling an effect-free `defproc` the compiler inlines, at 2.39 so the procedure declares no `:effects`)
- Modify: `orchestrator/workflow_lisp/source_sites.py` (`authored_calls` from `result.stage3.authored_direct_calls` by span containment; a `procedure-call` site whose typed body holds the inlined form is still a site)
- Test: `tests/test_workflow_lisp_source_sites.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
def test_inlined_procedure_call_is_a_site_with_authored_calls():              # F-c
    m = manifest(FIXTURES / "inlined_procedure.orc")
    site = site_of(m, kind="procedure-call")
    assert site["authored_calls"] == [{"callee_kind": "procedure", "callee_name": ...}]
def test_pure_helper_call_is_excluded_with_reason(): ...                       # a FunctionCallExpr site reports pure-call-unretained
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_workflow_lisp_source_sites.py -q -k "inlined or pure_helper"`
Expected: FAIL

- [ ] **Step 3: Implement**

- [ ] **Step 4: Run narrow then broad tests**

Run: `pytest tests/test_workflow_lisp_source_sites.py -q`, then in tmux `pytest -q -n 16 --dist=worksteal`
Expected: PASS; the broad run reports no new failures against `docs/plans/2026-10-16-remaining-test-suite-failures.md`

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: authored procedure call sites and pure-helper exclusion in the source-site manifest" -- orchestrator/workflow_lisp/source_sites.py tests/test_workflow_lisp_source_sites.py tests/fixtures/workflow_lisp/source_sites/inlined_procedure.orc
```

### Task 4: Correct the design from the probe and route the result

**Files:**
- Modify: `docs/design/workflow_lisp_source_site_inspection.md` (§2 row for per-node metadata: callee bodies are retained as `CallableRequest.prepared_body` in `Builder.completed_preparations`; only the entry body needs one re-elaboration; §3.3 step 3 and §7 P-1 updated with the measured cost; status stays proposed until the owner records acceptance)
- Modify: `docs/capability_status_matrix.md` (the structural-search row's evidence cell names the probe and manifest tests)
- Modify: `docs/index.md` (row for this plan)

- [ ] **Step 1: Apply the edits**
- [ ] **Step 2: Run the link checker**

Run: `python scripts/check_doc_links.py docs/design/workflow_lisp_source_site_inspection.md docs/capability_status_matrix.md docs/index.md docs/plans/2026-10-18-source-site-inspection-feasibility-plan.md`
Expected: only the known `<a id>` anchors reported

- [ ] **Step 3: Commit**

```bash
git commit -m "docs: record source-site inspection probe results and manifest evidence" -- docs/design/workflow_lisp_source_site_inspection.md docs/capability_status_matrix.md docs/index.md
```
