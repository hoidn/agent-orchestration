# YAML Deprecation Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. Do not create a worktree; repository
> policy requires execution in the existing checkout.

**Goal:** Emit one structured advisory warning for every explicit fresh
YAML/YML root-load attempt, keep persisted compatibility reads quiet, and route
new workflow authors and templates to Workflow Lisp `.orc`.

**Architecture:** `WorkflowLoader.load_bundle()` is the sole warning boundary.
It emits before parsing when a keyword-only policy is enabled; private recursive
imports stay silent. Fresh callers retain the enabled default, while resume,
report, and dashboard persisted reads opt out explicitly. Documentation keeps
YAML as legacy compatibility material and routes new authoring to `.orc`.

**Tech Stack:** Python 3 logging, `WorkflowLoader`, argparse CLI commands,
pytest/caplog, Markdown routing contracts.

**Execution status:** Implemented through Task 5 Step 4. The reviewed design
and plan landed at `bfe460d8` and `4f86b49a`; the loader event, warning-policy
normalization, persisted-read suppression, fresh-route integration, and author
routing landed at `3871099b`, `4e0a700d`, `30b1bd48`, `ee0e520a`, and
`b329c4b3`. Final implementation review bound exact HEAD
`b329c4b396e095d195119996838ea8782e6d1401` and tree
`00b1a2d17c6118695c747b7c3001817e4dd4977d`, returning specification PASS and
quality APPROVED. Task 5 Steps 5–6 remain unchecked because their reviewed
staged tree and resulting commit are the mechanical completion evidence.

**Execution evidence:** The pre-change focused baseline passed 456 tests; its
broad baseline recorded 5139 passed and 17 skipped with exactly the six bound
unrelated failures. The loader boundary finished with 11 focused warning tests
and 268 loader/shared-validation regressions passing. Persisted compatibility
finished with 232 affected-module tests passing. Final verification recorded
550 focused tests passing, 45 routing tests passing, `.orc` and YAML dry-run
smokes with respectively zero and one deprecation events, and 5181 passed plus
17 skipped in the broad suite with exactly the same six failures.

---

## Governing design and scope

This plan implements only Stage 6 Task 4 from
`docs/plans/2026-07-07-yaml-retirement-program.md` and the accepted design
`docs/plans/2026-07-17-yaml-deprecation-surface-design.md`.

It does not:

- reject or remove fresh YAML/YML execution;
- remove PyYAML or `WorkflowLoader`;
- modify any queued YAML/YML workflow or template source;
- create a third `.orc` migration port;
- change validation, diagnostics, exit codes, resume semantics, or bundle
  identity; or
- waive a Task 5 port gate or Task 6 deletion/archive gate.

The seven user-owned dirty paths in the YAML retirement roadmap are protected.
Before every commit, print the complete cached path list, compare it to the task
allowlist, run the literal protected-path guard below, and run
`git diff --cached --check`:

```bash
git diff --cached --name-only -- \
  'docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md' \
  'docs/plans/2026-07-01-workflow-audit-tier-fixes.md' \
  'docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md' \
  'state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt' \
  'tests/test_workflow_non_progress_step_back_demo.py' \
  'workflows/examples/non_progress_step_back_demo.yaml' \
  'workflows/library/prompts/workflow_step_back/diagnose_non_progress.md'
```

Expected: no output.

Every commit also uses this literal complete cached-set check, with the paths
after `assert_cached_paths` replaced by that task's reviewed allowlist:

```bash
assert_cached_paths() {
  EXPECTED="$(printf '%s\n' "$@" | LC_ALL=C sort)"
  ACTUAL="$(git diff --cached --name-only | LC_ALL=C sort)"
  printf 'cached paths:\n%s\n' "$ACTUAL"
  test "$ACTUAL" = "$EXPECTED"
}
assert_cached_paths path/one path/two
git diff --cached --check
```

The equality check runs before the protected-path guard. It prevents an
unrelated non-protected file from entering a commit.

## Task 0: Bind the reviewed prerequisite and baseline

**Files:**

- Create: `docs/plans/2026-07-17-yaml-deprecation-surface-implementation-plan.md`

- [x] **Step 1: Verify the prerequisite commits and selector**

```bash
git merge-base --is-ancestor b17d3b8b HEAD
git merge-base --is-ancestor bfe460d8 HEAD
rg -n '^\*\*Current selector:\*\* Task 4,' \
  docs/plans/2026-07-07-yaml-retirement-program.md
```

Expected: both ancestry checks exit 0 and the roadmap selects Task 4.

- [x] **Step 2: Record the dirty-path boundary**

Run `git status --short` and confirm the seven protected user paths are the only
pre-existing dirty paths. Do not stage, restore, format, or rewrite them.

- [x] **Step 3: Run the pre-change baseline**

```bash
pytest -q -n 16 --dist=worksteal \
  tests/test_loader_validation.py \
  tests/test_resume_command.py \
  tests/test_cli_report_command.py \
  tests/test_dashboard_projection.py \
  tests/test_workflow_lisp_build_artifacts.py
```

Expected: PASS. Record exact counts for closeout.

- [x] **Step 4: Run a fresh protected-tree broad baseline in tmux**

Run `pytest -q -n 16 --dist=worksteal` in tmux before any production/test/doc
implementation edit. Compare failure node IDs to the checked-in authorities:

- `docs/plans/2026-07-13-procedure-migration-identity-compatibility-baseline.json`;
- `docs/plans/2026-07-13-procedure-migration-identity-compatibility-baseline-correction.json`.

The only accepted node IDs are:

```text
tests/test_workflow_output_contract_integration.py::test_provider_valid_output_bundle_overrides_raw_nonzero_exit
tests/test_workflow_semantic_ir.py::test_semantic_ir_adds_typed_prompt_input_lineage_without_runtime_evidence
tests/test_workflow_semantic_ir.py::test_executable_ir_artifact_omits_compile_time_and_frontend_internal_payload_keys
tests/test_workflow_semantic_ir.py::test_compiled_bundle_semantic_ir_preserves_command_boundary_classification
tests/test_provider_role_routing.py::test_design_delta_drain_defaults_route_work_to_codex_gpt54
tests/test_neurips_steered_backlog_runtime.py::test_neurips_steered_backlog_runtime_drafts_gap_item_and_continues_without_relaunch
```

Expected: exactly these six failures and no other node ID. Treat any difference
as a current protected-tree baseline blocker; do not defer it to final closeout.
The correction artifact owns normalized-signature comparison when traces include
nondeterministic or logger-location data.

- [x] **Step 5: Commit this reviewed implementation plan**

Stage only this plan, then run:

```bash
EXPECTED='docs/plans/2026-07-17-yaml-deprecation-surface-implementation-plan.md'
ACTUAL="$(git diff --cached --name-only | LC_ALL=C sort)"
printf 'cached paths:\n%s\n' "$ACTUAL"
test "$ACTUAL" = "$EXPECTED"
# Run the literal protected-path guard from this plan here.
git diff --cached --check
git commit -m "docs: plan YAML deprecation surface"
```

## Task 1: Add the root-load deprecation event

**Files:**

- Modify: `orchestrator/loader.py`
- Create: `tests/test_yaml_deprecation_surface.py`

- [x] **Step 1: Write genuine RED loader-boundary tests**

Add behavioral tests that capture the dedicated logger and assert structured
record fields, never message wording:

- `.yaml` emits exactly one WARNING;
- `.yml` emits exactly one WARNING;
- `load()` emits once through `load_bundle()`;
- a root with recursive YAML/YML imports emits one event bound to the root;
- malformed YAML emits before validation failure;
- `emit_yaml_deprecation_warning=False` emits none;
- a non-YAML suffix emits none; and
- two explicit public root loads emit two events.

The tests must also assert that warning emission leaves the returned bundle and
structured validation exception behavior unchanged.

- [x] **Step 2: Run the RED selector**

```bash
pytest -q tests/test_yaml_deprecation_surface.py -k loader
```

Expected: fail because the constructor policy and structured event do not exist.

- [x] **Step 3: Implement the minimal loader policy**

In `orchestrator/loader.py`:

- define a stable event-code constant and dedicated logger;
- add keyword-only `emit_yaml_deprecation_warning: bool = True` to
  `WorkflowLoader.__init__`;
- store only the boolean policy, not warning history;
- in `load_bundle()`, inspect the requested path suffix case-insensitively and
  emit before `_load_workflow()`;
- attach structured fields with names that cannot collide with standard
  `LogRecord` attributes; and
- keep `_load_workflow()` free of warning emission.

Do not add process-global or loader-instance deduplication.

- [x] **Step 4: Run GREEN and loader regressions**

```bash
pytest --collect-only -q tests/test_yaml_deprecation_surface.py
pytest -q tests/test_yaml_deprecation_surface.py -k loader
pytest -q tests/test_loader_validation.py tests/test_workflow_shared_validation.py
```

Expected: PASS, with every new test collected once.

- [x] **Step 5: Request specification and quality review**

Specification review must confirm once-per-public-root semantics, malformed-file
coverage, silent recursion, structured non-phrasing assertions, and no change to
validation authority. Quality review must confirm logger-field safety,
request-path classification, and absence of hidden mutable deduplication.

- [x] **Step 6: Commit the reviewed loader event**

Stage exactly `orchestrator/loader.py` and
`tests/test_yaml_deprecation_surface.py`, then run:

```bash
EXPECTED="$(printf '%s\n' \
  orchestrator/loader.py \
  tests/test_yaml_deprecation_surface.py | LC_ALL=C sort)"
ACTUAL="$(git diff --cached --name-only | LC_ALL=C sort)"
printf 'cached paths:\n%s\n' "$ACTUAL"
test "$ACTUAL" = "$EXPECTED"
# Run the literal protected-path guard from this plan here.
git diff --cached --check
git commit -m "feat: warn on fresh YAML workflow loads"
```

## Task 2: Keep persisted compatibility reads quiet

**Files:**

- Modify: `orchestrator/cli/commands/resume.py`
- Modify: `orchestrator/cli/commands/report.py`
- Modify: `orchestrator/dashboard/projection.py`
- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `orchestrator/workflow_lisp/build_manifest_io.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_cli_report_command.py`
- Modify: `tests/test_dashboard_projection.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify: `tests/test_yaml_deprecation_surface.py`

- [x] **Step 1: Write RED persisted-consumer tests**

Use real persisted YAML state fixtures for resume, report, and dashboard
projection. Capture the dedicated deprecation logger and assert zero matching
records while the existing command/projection result remains unchanged.

Add a persisted `.orc` resume fixture with an explicit legacy YAML bundle
dependency and assert that its rebuild emits zero events. Bind it against the
same manifest used by a fresh-build positive test so the policy difference, not
fixture shape, determines the outcome.

Before implementation, add negative identity tests proving that toggling the
warning policy changes no build fingerprint, manifest payload, loaded-bundle
identity, Semantic IR, executable IR, or persisted build artifact/state field.

Add an AST/constructor guard proving those three production consumers pass
`emit_yaml_deprecation_warning=False` explicitly. Do not infer suppression from
path location or monkeypatch the logger away.

- [x] **Step 2: Run the RED selector**

```bash
pytest -q \
  tests/test_yaml_deprecation_surface.py \
  tests/test_resume_command.py \
  tests/test_cli_report_command.py \
  tests/test_dashboard_projection.py \
  tests/test_workflow_lisp_build_artifacts.py \
  -k 'deprecation or persisted_yaml'
```

Expected: the persisted paths emit because they still use the default policy.

- [x] **Step 3: Add explicit suppression**

Pass `emit_yaml_deprecation_warning=False` at every persisted YAML loader
construction site in resume, report, and dashboard projection.

Add `emit_yaml_deprecation_warning: bool = True` to `FrontendBuildRequest` and
forward it only to the loader used by explicit YAML bundle dependencies.
Persisted `.orc` resume passes `False`; fresh build callers retain the default.
Request normalization must preserve the policy without adding it to any
identity or persisted payload; `build_frontend_bundle()` consumes the normalized
request rather than bypassing normalization through the caller-owned object.
Prove the policy is absent from build fingerprints, manifests, bundle identity,
semantic/executable IR, and persisted state. Do not change fresh `run.py` or
direct loader defaults.

- [x] **Step 4: Run GREEN and complete consumer regressions**

```bash
pytest -q \
  tests/test_yaml_deprecation_surface.py \
  tests/test_resume_command.py \
  tests/test_cli_report_command.py \
  tests/test_dashboard_projection.py \
  tests/test_workflow_lisp_build_artifacts.py
```

Expected: PASS.

- [x] **Step 5: Request specification and quality review**

Reviewers must verify that only persisted compatibility paths suppress the
event, `.orc` resume behavior is unchanged, and suppression cannot weaken
validation or conceal load failures.

- [x] **Step 6: Commit the reviewed persisted suppression**

Stage exactly the ten Task-2 paths, then run:

```bash
EXPECTED="$(printf '%s\n' \
  orchestrator/cli/commands/report.py \
  orchestrator/cli/commands/resume.py \
  orchestrator/dashboard/projection.py \
  orchestrator/workflow_lisp/build.py \
  orchestrator/workflow_lisp/build_manifest_io.py \
  tests/test_cli_report_command.py \
  tests/test_dashboard_projection.py \
  tests/test_resume_command.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_yaml_deprecation_surface.py | LC_ALL=C sort)"
ACTUAL="$(git diff --cached --name-only | LC_ALL=C sort)"
printf 'cached paths:\n%s\n' "$ACTUAL"
test "$ACTUAL" = "$EXPECTED"
# Run the literal protected-path guard from this plan here.
git diff --cached --check
git commit -m "fix: suppress YAML warnings for persisted reads"
```

## Task 3: Prove fresh CLI and Workflow Lisp dependency routing

**Files:**

- Modify: `tests/test_yaml_deprecation_surface.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Regression only: `orchestrator/cli/commands/run.py`
- Regression only: `orchestrator/workflow_lisp/build.py`

- [x] **Step 1: Add fresh-path integration tests**

Prove:

- a fresh CLI YAML dry-run emits exactly one structured event and still exits
  successfully;
- a fresh `.orc` dry-run with no explicit YAML bundle dependency emits none;
- a fresh Workflow Lisp build with one explicit YAML bundle dependency emits
  one event for that explicit YAML root;
- recursive imports below that bundle do not add events; and
- two explicit YAML bundle dependency roots emit two events.

Use behavioral logger fields and exit/bundle results, not warning text.

- [x] **Step 2: Run the integration tests**

```bash
pytest --collect-only -q \
  tests/test_yaml_deprecation_surface.py \
  tests/test_workflow_lisp_build_artifacts.py
pytest -q \
  tests/test_yaml_deprecation_surface.py \
  tests/test_workflow_lisp_build_artifacts.py \
  -k 'deprecation or imported_workflow_bundle'
```

Expected: PASS without production changes. If a fresh route is incorrectly
suppressed or double-emits and needs a production correction, stop Task 3.
Amend this plan with the exact TDD sequence and production allowlist, obtain a
fresh plan-document approval, commit that plan-only amendment with the one-path
allowlist/guards, then restart Task 3 from its first integration test. Do not
stage a production fix with an uncommitted or unreviewed plan change.

The plan-only amendment commit must run this exact cached check before the
protected guard and commit:

```bash
EXPECTED='docs/plans/2026-07-17-yaml-deprecation-surface-implementation-plan.md'
ACTUAL="$(git diff --cached --name-only | LC_ALL=C sort)"
printf 'cached paths:\n%s\n' "$ACTUAL"
test "$ACTUAL" = "$EXPECTED"
git diff --cached --check
```

- [x] **Step 3: Run end-to-end route smokes**

```bash
python -m orchestrator run \
  tests/fixtures/workflow_lisp/valid/pure_expr_loop_counter.orc \
  --entry-workflow run-counter --dry-run
python -m orchestrator run workflows/examples/assert_gate_demo.yaml --dry-run
```

Expected: both exit 0; the `.orc` route has no YAML deprecation event, and the
YAML route has one.

- [x] **Step 4: Request specification and quality review**

Reviewers must verify the integration tests cover the non-CLI fresh dependency
path and do not encode literal warning phrasing.

- [x] **Step 5: Commit the reviewed integration guards**

Stage exactly the two test files unless a separately reviewed and committed plan
amendment authorized a production correction. For the normal two-test path, run:

```bash
EXPECTED="$(printf '%s\n' \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_yaml_deprecation_surface.py | LC_ALL=C sort)"
ACTUAL="$(git diff --cached --name-only | LC_ALL=C sort)"
printf 'cached paths:\n%s\n' "$ACTUAL"
test "$ACTUAL" = "$EXPECTED"
# Run the literal protected-path guard from this plan here.
git diff --cached --check
git commit -m "test: prove YAML deprecation warning routes"
```

## Task 4: Route new authors and templates to `.orc`

**Files:**

- Modify: `specs/dsl.md`
- Modify: `README.md`
- Modify: `docs/index.md`
- Modify: `docs/lisp_workflow_drafting_guide.md`
- Modify: `docs/workflow_drafting_guide.md`
- Modify: `workflows/README.md`
- Modify: `workflows/templates/README.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `tests/test_yaml_deprecation_surface.py`

- [x] **Step 1: Write RED routing-contract tests**

Assert stable structure and links rather than prose:

- the default authoring entry in `docs/index.md` routes to the Workflow Lisp
  guide;
- the YAML guide is labeled compatibility/legacy and is not the new-author
  start;
- README and workflow catalog choose a registry-approved `.orc` example for new
  authoring;
- template documentation routes new templates to `.orc` and identifies the
  existing YAML template as compatibility-only; and
- the frozen YAML template remains a compatibility-only inventory member and no
  new-author route selects it.

Add a normative-contract assertion that `specs/dsl.md` distinguishes fresh
advisory warnings from persisted compatibility reads without asserting literal
warning wording.

- [x] **Step 2: Run RED**

```bash
pytest -q tests/test_yaml_deprecation_surface.py -k author_routing
```

Expected: fail because current docs still route new authors/templates to YAML.

- [x] **Step 3: Update the normative and informative routes**

- In `specs/dsl.md`, define the advisory fresh-load event and persisted-read
  suppression next to existing non-fatal warning behavior, including the exact
  logger `orchestrator.loader.yaml_deprecation`, code
  `workflow_yaml_authoring_deprecated`, record fields
  `workflow_deprecation_code`, `workflow_deprecation_path`, and
  `workflow_deprecation_format`, and resolved absolute path representation.
- In `docs/index.md` and README, make `.orc` the new-author default.
- Mark `docs/workflow_drafting_guide.md` as legacy compatibility guidance.
- Make the Lisp guide say not to create new YAML when a form is missing; retain
  an existing authority or record a gap instead.
- In `workflows/README.md` and `workflows/templates/README.md`, route new work to
  copy-safe `.orc` examples.
- In `docs/capability_status_matrix.md`, advance the deprecation-surface row
  from Designed to Implemented with the reviewed tests/commits while keeping
  the YAML DSL row `Legacy`.
- Do not edit `workflows/templates/autonomous_drain_with_work_instructions.v214.yaml`
  or any other YAML/YML source.

- [x] **Step 4: Run GREEN and routing regressions**

```bash
pytest -q tests/test_yaml_deprecation_surface.py -k author_routing
pytest -q \
  tests/test_workflow_yaml_orc_gap_list.py \
  tests/test_workflow_lisp_drain_roadmap_routing.py
```

Expected: PASS.

- [x] **Step 5: Request specification and consistency review**

Reviewers must confirm the docs do not claim YAML rejection or universal `.orc`
parity, do not create a third port, and retain compatibility guidance for
existing YAML.

- [x] **Step 6: Commit the reviewed author-routing change**

Stage exactly the nine Task-4 paths, then run this exact cached-set and estate
exclusion check before the protected guard:

```bash
EXPECTED="$(printf '%s\n' \
  README.md \
  docs/capability_status_matrix.md \
  docs/index.md \
  docs/lisp_workflow_drafting_guide.md \
  docs/workflow_drafting_guide.md \
  specs/dsl.md \
  tests/test_yaml_deprecation_surface.py \
  workflows/README.md \
  workflows/templates/README.md | LC_ALL=C sort)"
ACTUAL="$(git diff --cached --name-only | LC_ALL=C sort)"
printf 'cached paths:\n%s\n' "$ACTUAL"
test "$ACTUAL" = "$EXPECTED"
test -z "$(git diff --cached --name-only -- '*.yaml' '*.yml')"
# Run the literal protected-path guard from this plan here.
git diff --cached --check
git commit -m "docs: route new workflow authors to orc"
```

## Task 5: Broad verification, reviews, and Stage 6 closeout

**Files:**

- Modify after implementation reviews pass:
  `docs/plans/2026-07-17-yaml-deprecation-surface-implementation-plan.md`
- Modify after implementation reviews pass:
  `docs/plans/2026-07-17-yaml-deprecation-surface-design.md`
- Modify after implementation reviews pass:
  `docs/plans/2026-07-07-yaml-retirement-program.md`
- Modify after implementation reviews pass:
  `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`
- Modify after implementation reviews pass:
  `docs/plans/2026-07-13-procedure-first-migration-waves-plan.md`
- Modify after implementation reviews pass: `docs/index.md`
- Modify after implementation reviews pass: `docs/capability_status_matrix.md`
- Modify after implementation reviews pass:
  `tests/test_workflow_yaml_orc_gap_list.py`
- Modify after implementation reviews pass:
  `tests/test_workflow_lisp_drain_roadmap_routing.py`

- [x] **Step 1: Run the complete focused lane**

```bash
pytest -q -n 16 --dist=worksteal \
  tests/test_yaml_deprecation_surface.py \
  tests/test_loader_validation.py \
  tests/test_workflow_shared_validation.py \
  tests/test_resume_command.py \
  tests/test_cli_report_command.py \
  tests/test_dashboard_projection.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_cli_safety.py
```

Expected: PASS.

- [x] **Step 2: Run the broad suite in tmux**

```bash
pytest -q -n 16 --dist=worksteal
```

Expected: clean or exactly the established six unrelated failures by exact test
identity. No new warning, loader, CLI, resume, report, dashboard, or Workflow
Lisp build failure may be classified as unrelated.

- [x] **Step 3: Obtain final implementation reviews**

Specification review must bind the exact implementation HEAD and answer whether
fresh/persisted routing, once semantics, normative docs, and Task-7 non-goals
are all preserved. Code-quality review must inspect logger structure, call-site
policy, tests, docs routing, and scope. Require PASS and APPROVED.

For every accepted finding, add a failing test first, make the minimal fix,
rerun affected tests plus the complete focused and broad lanes, and restart both
reviews.

- [x] **Step 4: Advance the exclusive selector from Task 4 to Task 5**

Only after both implementation reviews pass:

- mark Tasks 0–4 and Task-5 Steps 1–4 complete and record commits/evidence;
- mark the design Implemented;
- close the three Task-4 roadmap boxes with evidence;
- select Stage 6 Task 5 exclusively across the canonical roadmap/index/matrix
  surfaces;
- keep YAML `Legacy`, Task 7 parser removal incomplete, and every Task-5/6 gate
  binding; and
- update both routing tests to reject every competing Task 1–4 and 6–7 current
  selector.

Run:

```bash
pytest -q \
  tests/test_workflow_yaml_orc_gap_list.py \
  tests/test_workflow_lisp_drain_roadmap_routing.py
```

Expected: PASS.

- [ ] **Step 5: Freeze and review the exact closeout tree**

Stage exactly the nine closeout paths listed above, then run:

```bash
EXPECTED="$(printf '%s\n' \
  docs/capability_status_matrix.md \
  docs/index.md \
  docs/plans/2026-07-07-yaml-retirement-program.md \
  docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md \
  docs/plans/2026-07-13-procedure-first-migration-waves-plan.md \
  docs/plans/2026-07-17-yaml-deprecation-surface-design.md \
  docs/plans/2026-07-17-yaml-deprecation-surface-implementation-plan.md \
  tests/test_workflow_lisp_drain_roadmap_routing.py \
  tests/test_workflow_yaml_orc_gap_list.py | LC_ALL=C sort)"
ACTUAL="$(git diff --cached --name-only | LC_ALL=C sort)"
printf 'cached paths:\n%s\n' "$ACTUAL"
test "$ACTUAL" = "$EXPECTED"
# Run the literal protected-path guard from this plan here.
git diff --cached --check
CLOSEOUT_REVIEW_BASE="$(git rev-parse HEAD)"
CLOSEOUT_REVIEW_TREE="$(git write-tree)"
```

Obtain independent specification/consistency PASS and execution-quality
APPROVED verdicts that cite both values. Any edit invalidates both verdicts.
Task-5 Steps 5–6 remain unchecked in the reviewed file because their execution
is the mechanical evidence that creates the closeout commit; do not pre-attest
them. The reviewed base/tree and resulting commit are their completion record.

- [ ] **Step 6: Commit the reviewed closeout without restaging**

Verify HEAD and `git write-tree` still equal the reviewed values, verify no
unstaged closeout-path diff exists, re-run the exact cached allowlist and guards,
then commit:

```bash
# Paste the exact values cited by both final review verdicts.
REVIEWED_BASE='<review-cited base commit>'
REVIEWED_TREE='<review-cited staged tree>'
test "$REVIEWED_BASE" != '<review-cited base commit>'
test "$REVIEWED_TREE" != '<review-cited staged tree>'
test "$(git rev-parse HEAD)" = "$REVIEWED_BASE"
test "$(git write-tree)" = "$REVIEWED_TREE"
git diff --quiet -- \
  docs/capability_status_matrix.md \
  docs/index.md \
  docs/plans/2026-07-07-yaml-retirement-program.md \
  docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md \
  docs/plans/2026-07-13-procedure-first-migration-waves-plan.md \
  docs/plans/2026-07-17-yaml-deprecation-surface-design.md \
  docs/plans/2026-07-17-yaml-deprecation-surface-implementation-plan.md \
  tests/test_workflow_lisp_drain_roadmap_routing.py \
  tests/test_workflow_yaml_orc_gap_list.py
EXPECTED="$(printf '%s\n' \
  docs/capability_status_matrix.md \
  docs/index.md \
  docs/plans/2026-07-07-yaml-retirement-program.md \
  docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md \
  docs/plans/2026-07-13-procedure-first-migration-waves-plan.md \
  docs/plans/2026-07-17-yaml-deprecation-surface-design.md \
  docs/plans/2026-07-17-yaml-deprecation-surface-implementation-plan.md \
  tests/test_workflow_lisp_drain_roadmap_routing.py \
  tests/test_workflow_yaml_orc_gap_list.py | LC_ALL=C sort)"
ACTUAL="$(git diff --cached --name-only | LC_ALL=C sort)"
printf 'cached paths:\n%s\n' "$ACTUAL"
test "$ACTUAL" = "$EXPECTED"
# Run the literal protected-path guard from this plan here.
git diff --cached --check
git commit -m "docs: close YAML deprecation surface task"
```

## Completion criteria

Task 4 is complete only when:

1. every explicit fresh YAML/YML root attempt emits one structured advisory
   event before parsing;
2. `load()` and recursive imports cannot double-emit;
3. suppression and non-YAML paths emit no YAML event;
4. resume, report, and dashboard persisted reads suppress explicitly;
5. fresh CLI YAML and Workflow Lisp YAML-dependency paths retain the default;
6. warning behavior cannot change validation, exit codes, bundle identity, or
   resume semantics;
7. normative and author/template routes select `.orc` for new work without
   editing a queued YAML/YML source or claiming unsupported parity;
8. focused and route smoke tests pass, and broad verification is clean or
   fail-closed on the exact established unrelated baseline;
9. independent specification and quality reviews approve the exact final
   implementation tree; and
10. the reviewed closeout advances only Task 4 to Task 5 while YAML remains
    `Legacy` and Tasks 5–7 remain governed by their existing gates.
