# Dashboard Persisted Typed Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. Do not create a worktree; repository
> policy requires execution in the existing checkout.

**Goal:** Give the dashboard a tamper-evident, versioned typed workflow-structure
read model for persisted Workflow Lisp runs without reading/recompiling `.orc`
source or fabricating a `LoadedWorkflowBundle`.

**Architecture:** The build emits one canonical `PersistedWorkflowSurfaceGraph`
from an already validated entry bundle, following only call aliases actually used
by ordinary, nested structured, and finalization steps. Manifest and run state
carry the identical build-relative schema/path/entry/digest anchor. The dashboard
verifies both authorities in a fixed fail-closed order, decodes an immutable read
model, and otherwise degrades to state-only summaries.

**Tech Stack:** Python 3 frozen dataclasses, canonical JSON, SHA-256,
`SurfaceStepKind`, Workflow Lisp build artifacts, runtime observability, dashboard,
pytest, tmux.

---

## Scope, authority, and accepted future cost

This corrects Stage 6 Task 2 in
`docs/plans/2026-07-07-yaml-retirement-program.md`. `specs/dsl.md` remains the
normative language authority; no DSL rule changes.

The graph is a dashboard read model, not executable IR, Semantic IR, or a
reconstructed `LoadedWorkflowBundle`. It records exactly the typed structure and
link metadata currently rendered. A future dashboard feature needing another
field must evolve the graph schema and producer/decoder tests. That explicit cost
is accepted to prevent source recompilation and false runtime-contract claims.

Required contracts:

1. `.orc` dashboard reads call no compiler, parser, macro expander, elaborator,
   lowering, `WorkflowLoader`, or authored source reader.
2. Producer input is an already validated `LoadedWorkflowBundle` only.
3. Reachability follows `SurfaceStep.call_alias` recursively through root steps,
   `for_each`, `if` branches, match cases, repeat bodies, and workflow
   finalization. Every used alias must exist in the current bundle's imports.
   Unused bundle imports are ignored.
4. Nodes are keyed by canonical workflow name. Repeated identical node payloads
   (diamonds or two aliases) deduplicate. A repeated name with differing payload
   fails closed. Cycles, missing used aliases/targets, extra serialized aliases,
   unreachable nodes, duplicate JSON keys, and unsupported schemas fail closed.
5. Step data includes name/id/kind, structured/finalization children, call alias,
   input/asset/dependency paths, expected outputs, output/variant bundles,
   publishes/consumes, and adjudicated-provider candidate/evaluator prompt and
   rubric assets used by current renderer link groups.
6. Canonical bytes are exactly UTF-8 of
   `json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
   allow_nan=False)` plus one trailing `\n`. Decoder rejects `NaN`, `Infinity`,
   and `-Infinity` during parse and requires input bytes equal that strict-JSON
   re-encoding.
7. Digests are lowercase `sha256:<64 hex>`. The identical closed anchor
   `{schema_version, path, entry_workflow, sha256}` appears in manifest and state;
   path is POSIX `build/<fingerprint>/persisted_workflow_surface.json`.
8. The build schema/fingerprint contract is bumped so pre-snapshot and
   snapshot-producing builds cannot share a content-addressed directory. Producer
   decodes and validates its final emitted bytes before returning success.
9. A wholly absent state anchor means a legacy run and degrades with a legacy
   warning. A partial/malformed anchor is corruption and degrades with a distinct
   fail-closed warning. Neither route recompiles.
10. Safe relative or absolute recorded `.orc` paths resolve lexically with
    `strict=False` after deletion, including symlink checks through existing
    ancestors. Traversal/symlink escape fails. YAML keeps its existing
    readable-source requirement and live `WorkflowLoader` typed surface.
11. Protected Stage-6 paths are never edited or staged.

## File responsibility map

Create:

- `orchestrator/workflow/persisted_surface.py` — graph schema, frozen read model,
  canonical serializer/decoder, call-edge collector, and invariants. No dashboard,
  YAML, compiler, elaboration, or lowering imports.
- `tests/test_persisted_workflow_surface.py` — isolated topology, closed-wire,
  malformed-graph, and deep-immutability contract tests.
- `docs/plans/2026-07-16-dashboard-persisted-typed-surface-plan.md` — this plan.

Modify:

- `orchestrator/workflow/surface_ast.py` — optional complete persisted-surface
  provenance anchor.
- `orchestrator/workflow_lisp/build.py` — schema bump, graph creation, provenance,
  production self-validation, artifact handoff.
- `orchestrator/workflow_lisp/build_artifacts.py` — canonical artifact emission and
  manifest anchor.
- `orchestrator/runtime_observability.py` — copy the exact complete anchor to run
  state; never synthesize a partial record.
- `orchestrator/dashboard/compiled_workflow.py` — state/manifest/artifact verifier
  and decoder only.
- `orchestrator/dashboard/models.py`, `projection.py`, `server.py` — honest
  `workflow_structure` union, safe deleted-source `.orc` routing, typed renderer.
- `tests/test_workflow_lisp_build_artifacts.py` — producer, topology, invariant,
  canonical-byte, schema/fingerprint tests.
- `tests/test_runtime_observability.py` and
  `tests/test_runtime_observability_cli.py` — unit and real-run exact anchor tests.
- `tests/test_workflow_lisp_procedure_identity_retirement.py` — preserve frozen
  six-artifact historical comparisons by excluding only the four strictly
  validated, dashboard-only persisted-surface provenance fields.
- `tests/test_dashboard_compiled_workflow.py`,
  `tests/test_dashboard_projection.py`, `tests/test_dashboard_server.py`, and
  `tests/test_cli_dashboard_command.py` — reader, path, renderer, endpoint,
  degradation.
- `docs/plans/2026-07-07-yaml-retirement-program.md`, `docs/index.md`, and
  `docs/capability_status_matrix.md` — reviewed closeout only.

## Task 1: Freeze producer, topology, and anchor behavior

- [ ] Add RED producer tests using a minimal `.orc` and real
  `imported_bundle_mix`. Require exactly three nodes for the real fixture: entry,
  same-file helper, external selector. The helper's unused closure imports must
  not become nodes or edges.
- [ ] Add both-direction call topology tests: root/nested/finalization calls are
  followed; unused imports ignored; two aliases and a diamond deduplicate; missing
  used alias fails; an extra serialized alias fails; cycle fails; same-name
  differing payload fails; missing/unreachable nodes fail.
- [ ] Add wire tests: duplicate keys fail, noncanonical valid JSON bytes fail,
  unknown/missing fields fail, unsupported schema fails, invalid/uppercase/short
  digest syntax fails, and exact canonical bytes/digest pass.
- [ ] Add RED runtime tests proving only a complete four-key anchor is persisted
  and a CLI-created run records byte-identical manifest/state anchors.
- [ ] Collect and prove RED:

```bash
pytest --collect-only -q tests/test_workflow_lisp_build_artifacts.py \
  tests/test_runtime_observability.py tests/test_runtime_observability_cli.py \
  tests/test_persisted_workflow_surface.py
pytest -q tests/test_workflow_lisp_build_artifacts.py \
  tests/test_runtime_observability.py tests/test_runtime_observability_cli.py \
  -k 'persisted_surface or compiled_frontend_surface'
pytest -q tests/test_persisted_workflow_surface.py
```

Expected: real missing artifact/schema/anchor failures, not fixture errors.

## Task 2: Implement and self-validate the producer

- [ ] Implement frozen graph/step/common/finalization types and the recursive
  actual-call collector in `persisted_surface.py`.
- [ ] Serialize workflow-name-keyed nodes. Compare canonical payload on repeat
  names; identical deduplicates, differing fails. Do not traverse unused imports.
- [ ] Implement strict byte decoder and topology validation, including canonical
  byte equality before object acceptance.
- [ ] Bump `BUILD_SCHEMA_VERSION` and emit canonical
  `persisted_workflow_surface.json`. Add the identical four-key anchor to manifest
  and selected-bundle provenance using build-relative POSIX path.
- [ ] Decode/validate final emitted bytes and compare the produced entry/anchor
  before returning `FrontendBuildResult`.
- [ ] Persist the exact provenance anchor in runtime observability only when all
  four values are valid.
- [ ] Run GREEN producer/runtime selectors and the complete
  `tests/test_workflow_lisp_build_artifacts.py` plus
  `tests/test_runtime_observability.py`, `tests/test_runtime_observability_cli.py`,
  and `tests/test_persisted_workflow_surface.py` suites.

## Task 3: Replace dashboard fresh reconstruction

- [ ] Add genuine RED tests using real build output for: exact three-node imported
  closure; valid-content tamper; noncanonical bytes; duplicate keys; each state or
  manifest binding mismatch; partial/malformed state anchor; wholly absent legacy
  anchor; source deletion/edit; relative and absolute deleted-source path; lexical
  traversal; symlink escape; no frontend/loader/elaboration/lowering call.
- [ ] Add renderer RED coverage for finalization and every current link-bearing
  field, including adjudicated-provider candidate/evaluator prompt/rubric assets.
- [ ] Add CLI dashboard RED coverage for a bound run, legacy run, and corrupt run.
- [ ] Verify RED with exact selectors:

```bash
pytest -q tests/test_dashboard_compiled_workflow.py \
  -k 'imported_bundle_mix or tamper or canonical or binding or legacy or malformed or source or symlink or no_frontend'
pytest -q tests/test_dashboard_server.py tests/test_cli_dashboard_command.py \
  -k 'persisted_surface or finalization or adjudicated'
```

- [ ] Implement reader verification in this fixed order: closed state anchor and
  digest syntax; content-addressed build root; supported build manifest schema;
  exact manifest anchor equality; safe bound artifact path; actual SHA-256;
  canonical byte equality; closed graph decode; entry/closure invariants.
- [ ] Rename false `workflow_bundle` dashboard fields/helpers to
  `workflow_structure`. Render live YAML bundle and persisted graph through narrow
  typed adapters.
- [ ] Resolve `.orc` workflow paths lexically/safely without requiring final source
  existence; retain existing readable resolution for YAML.
- [ ] Run complete dashboard focused suites GREEN.

## Task 4: Verification, reviews, closeout, and commits

- [ ] Collect every changed test once:

```bash
pytest --collect-only -q tests/test_dashboard_compiled_workflow.py \
  tests/test_dashboard_projection.py tests/test_dashboard_server.py \
  tests/test_cli_dashboard_command.py tests/test_runtime_observability.py \
  tests/test_runtime_observability_cli.py tests/test_workflow_lisp_build_artifacts.py \
  tests/test_persisted_workflow_surface.py
```

- [ ] Run focused tests:

```bash
pytest -q -n 16 --dist=worksteal tests/test_dashboard_compiled_workflow.py \
  tests/test_dashboard_projection.py tests/test_dashboard_server.py \
  tests/test_cli_dashboard_command.py tests/test_runtime_observability.py \
  tests/test_runtime_observability_cli.py tests/test_workflow_lisp_build_artifacts.py \
  tests/test_persisted_workflow_surface.py
```

- [ ] Run real minimal and `imported_bundle_mix` build/dashboard smokes; delete the
  copied `.orc` before repeat projection and require identical typed structure.
- [ ] Run pycompile/import checks. For the architecture grep below, exit 1 is PASS
  (no matches), exit 0 is a blocking match, and exit >1 is command failure:

```bash
python -m py_compile orchestrator/workflow/persisted_surface.py \
  orchestrator/dashboard/compiled_workflow.py
python - <<'PY'
from orchestrator.workflow.persisted_surface import PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA
from orchestrator.dashboard.compiled_workflow import load_persisted_compiled_workflow_surface
print(PERSISTED_WORKFLOW_SURFACE_GRAPH_SCHEMA)
PY
set +e
rg -n 'yaml|WorkflowLoader|elaborate_surface_workflow|build_loaded_workflow_bundle|compile_stage3' \
  orchestrator/dashboard/compiled_workflow.py
status=$?
set -e
test "$status" -eq 1
```

- [ ] Use the `tmux` skill for the broad suite:

```bash
pytest -q -n 16 --dist=worksteal
```

Do not classify a new dashboard/build/runtime-observability failure as unrelated.
If the new build schema or provenance changes a frozen historical-evidence
comparison, validate the complete current persisted-surface binding first and
apply only an exact, reviewed compatibility projection; never regenerate frozen
evidence or weaken production identity comparisons.

- [ ] Obtain independent specification and code-quality reviews. Specification
  review must verify honest read-model claims, actual-call closure, exact anchor,
  path safety, and degradation. Quality review must verify closed decoding,
  ownership, no frontend dependency, renderer completeness, and test behavior.
- [ ] Fix every accepted finding TDD-first and restart both reviews if schema,
  authority, topology, or degradation changes.
- [ ] After approval only, update the Stage 6 roadmap, index, and capability matrix:
  mark Task 2 complete with exact evidence, keep YAML `Legacy`, select Task 3, and
  do not imply parser removal.
- [ ] Run `git diff --check` and print every changed path. Use these exact five
  independently-green commit allowlists in order; never use broad staging:

  1. reviewed plan first:
     `docs/plans/2026-07-16-dashboard-persisted-typed-surface-plan.md`;
  2. producer plus producer/runtime tests:
     `orchestrator/workflow/persisted_surface.py`,
     `orchestrator/workflow/surface_ast.py`,
     `orchestrator/workflow_lisp/build.py`,
     `orchestrator/workflow_lisp/build_artifacts.py`,
     `orchestrator/runtime_observability.py`,
     `tests/test_workflow_lisp_build_artifacts.py`,
     `tests/test_runtime_observability.py`,
     `tests/test_runtime_observability_cli.py`,
     `tests/test_persisted_workflow_surface.py`;
  3. frozen historical-comparison compatibility tests:
     `tests/test_workflow_lisp_procedure_identity_retirement.py`;
  4. reader/dashboard plus dashboard/CLI tests:
     `orchestrator/dashboard/compiled_workflow.py`,
     `orchestrator/dashboard/models.py`, `orchestrator/dashboard/projection.py`,
     `orchestrator/dashboard/server.py`,
     `tests/test_dashboard_compiled_workflow.py`,
     `tests/test_dashboard_projection.py`, `tests/test_dashboard_server.py`,
     `tests/test_cli_dashboard_command.py`;
  5. closeout: `docs/plans/2026-07-07-yaml-retirement-program.md`,
     `docs/index.md`, `docs/capability_status_matrix.md`.

  Before the producer commit, run its complete producer/runtime focused suite on
  that tree. Before the historical-compatibility commit, run its affected selectors
  and full retirement module. Before the reader/dashboard commit, run all focused
  dashboard and CLI tests on that tree. Before closeout, rerun the combined focused
  suite and confirm both reviews still approve.

  After staging each group, write that group's exact expected path list to
  `/tmp/dashboard-surface-expected.txt`, one path per line, then run this
  fail-closed equality/syntax check with `set -e`:

```bash
set -e
sort -u /tmp/dashboard-surface-expected.txt -o /tmp/dashboard-surface-expected.txt
git diff --cached --name-only | sort -u > /tmp/dashboard-surface-cached.txt
cmp -s /tmp/dashboard-surface-expected.txt /tmp/dashboard-surface-cached.txt || {
  diff -u /tmp/dashboard-surface-expected.txt /tmp/dashboard-surface-cached.txt
  exit 1
}
git diff --cached --check
protected="$(git diff --cached --name-only -- \
  'docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md' \
  'docs/plans/2026-07-01-workflow-audit-tier-fixes.md' \
  'docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md' \
  'state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt' \
  'tests/test_workflow_non_progress_step_back_demo.py' \
  'workflows/examples/non_progress_step_back_demo.yaml' \
  'workflows/library/prompts/workflow_step_back/diagnose_non_progress.md')"
printf '%s' "$protected"
test -z "$protected"
```

  The final command must print nothing. Then print
  `git diff --cached --name-only`. Repeat the exact equality, cached diff-check,
  literal seven-path guard, and printed cached list immediately before every
  commit.
- [ ] Preserve the review/commit sequence represented by those five allowlists:
  obtain final plan review and commit the plan before implementation; obtain a
  focused producer/runtime review and commit that independently green group;
  verify and commit any exact frozen historical-comparison compatibility
  correction; obtain combined reader/dashboard and holistic reviews and commit that
  independently green group; then verify and commit the closeout documentation.
  The parent executor creates each real commit using only its corresponding
  verified allowlist.

## Completion criteria

Task 2 is complete only when the real fixture yields exactly the semantic
three-node closure; canonical production bytes are self-validated and identically
anchored in manifest/state; tamper/binding/path/topology failures degrade closed;
deleted `.orc` source never triggers a frontend; legacy absence is distinguished
from corruption; YAML remains live-loader typed; renderer fields and finalization
are preserved; focused/CLI/smoke/broad checks pass; and both reviews approve.
