# M1 Estate Shrink Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete served-purpose retirement, migration, queue, and gate
machinery; narrow two remaining compatibility shims; remove unsupported demo
wheel contents; and reversibly archive the closed legacy run estate without
changing current `.orc` behavior.

**Architecture:** Work seam by seam. First remove surviving test and
documentation dependencies, then delete each zero-consumer implementation
cluster behind focused checks, prove the surviving product surface with one
green broad non-security gate, and only then move the frozen legacy run
directories into a content-verified same-filesystem archive. Current route
readiness, `frontend_kind` provenance, state-only reporting, and the six
current-format nonterminal runs remain; M1 removes only their obsolete
migration or compatibility coupling.

**Tech stack:** Python 3.13, pytest/xdist, Workflow Lisp `.orc`, setuptools
wheel discovery, Git, POSIX filesystem rename and SHA-256 manifests.

**Status:** historical complete. Tasks 0–9, ordered final reviews, reviewed
closure commit, and postcommit control are complete at commit
`57c2604e595d22dc9d9d656409607f81b332b5f8`, tree
`fc0fdbefe2cdd99cf0f9de604aa63582f79425ea`. The external closure record
currently has SHA-256
`b5c0624bd6759e4cf2a3d0153c42a1aa9068ebcab2050c15237d9cb74b95470b`.
Task 0's historical selection act was the externally reviewed commit
`4e71093d`; no checked-in byte self-attests an external verdict.

---

## Authority, entry evidence, and resolved bounds

This plan executes Phase M1 of
`docs/plans/2026-07-26-substrate-maintenance-track.md`, including the adopted
`M1 Inventory Extension` in
`docs/plans/2026-07-26-provider-at-least-once-loosening-amendment.md`.

M0's repository plan remains historical closure evidence. Its external exact
commit record is
`/home/ollie/.tmp/m0-green-baseline-20260729/closure-verdicts.md`, SHA-256
`88f35cdd872ba9e5a9602d3e756ee81e2911c2384e74c6fa2388cdb907e2ba0e`.
That record binds ordered final approval, commit
`f15b888d0c4862f7e229b990255d5f34c7392591`, tree
`8a75f24fde68b657d2f84b28aa8b4d34df5089cf`, and a 418-pass postcommit
control. M0 is historical complete; this plan does not reopen M0, Q5, or any
L-series gate and does not re-review an unchanged surface.

Three read-only censuses at the M0 closure tree establish M1's starting
boundary:

| Estate | Current measured boundary | M1 disposition |
| --- | ---: | --- |
| Retirement production | 7 files, 22,485 physical lines | delete |
| Dedicated retirement tests/support | 5 files, 22,739 physical lines | delete |
| Dedicated retirement fixtures | 64 files, 10,065 physical lines | delete |
| Direct retirement estate | 76 files, 55,289 physical lines | delete |
| YAML-retirement evidence | 217 files, 29,750,265 bytes; Git tree `8df00515e3d88a7d9783dd3ff76286cff973044b` | preserve byte-for-byte |
| Run store | 4,174 directories; 4,173 `state.json`; 4,083 terminal; 90 nonterminal; one state-less orphan | archive only the bound closed/legacy set |
| Nonterminal partition | 84 YAML/YML, six `.orc` | archive YAML/YML; retain `.orc` |
| Route-readiness registry | 59 current surfaces at census | retain; strip retired migration coupling |

The initial normalized run census over
`(run_id, status, state_sha256)` was
`f929bf532336ba52a48327132615a3358373c044a9f7edd625d6843faf3a6ae3`.
It is context, not the archive binding: Task 8 captures the authoritative
post-test census.

The owner has directed unattended roadmap execution. The following bounded
implementation decisions are therefore recorded here rather than escalated:

1. **Retirement evidence is sufficient.** The immutable
   `docs/plans/evidence/yaml-retirement/` tree plus the YAML-retirement program
   and proportionality ruling are the closure authority. M1 creates no new
   evidence schema, repair class, capture window, or attestation lifecycle.
2. **Route readiness stays current.** Delete migration-parity and post-WCC
   coupling only. Keep the registry, compiler checks, CLI verb, active
   authoring routes, and ordinary route fixtures.
3. **`frontend_kind` stays provenance.** Keep its persisted field, compiler
   producer, validation, resume, observability, and presentation consumers.
   Remove only the redundant executor compatibility property and duplicate
   outer guard identified by the fresh census.
4. **Demo support stays in the repository but leaves the wheel.** Add a
   setuptools package-discovery exclusion for `orchestrator.demo` and
   `orchestrator.demo.*`. Do not invent an optional extra.
5. **Dashboard and report compatibility stay.** Dashboard is excluded by the
   parent track and state-only reporting remains useful for current `.orc`
   runs. M1 removes only the completed YAML/YML resume fast-return.
6. **Current-format nonterminal runs stay live.** The six census-bound `.orc`
   run IDs are:
   `20260529T223321Z-r6iyao`,
   `20260529T230000Z-ydbxzx`,
   `20260529T232643Z-lhokp3`,
   `20260603T213041Z-1mvh31`,
   `20260610T234855Z-fto5hz`, and
   `20260617T224849Z-kkyu4c`.
   M1 neither resumes nor dispositions them.
7. **Closed legacy runs move, not delete.** Terminal runs, the 84
   owner-dispositioned unsupported/abandoned YAML/YML nonterminal runs, and
   the state-less orphan `20260615T010145Z-xl2f1b` move by same-filesystem
   rename into a reversible archive after all run-creating tests finish.

The reviewed Task 0 candidate explicitly amends two stale parent-scope
phrases. First, it supersedes the amendment's 2026-07-26 blanket inclusion of
the route-readiness cluster: the fresh census proves route readiness is a
current 59-surface authoring/copy-safety authority, so M1 deletes only its
migration-parity coupling. Second, “terminal-legacy-read compatibility” is
fixed to mean the executable completed-YAML resume fast return. Read-only
report/dashboard rendering does not resume or reconstruct a workflow and
remains outside M1 under the parent's dashboard exclusion. These are
reviewable scope corrections in the M1 selection act, not silent
implementation deviations.

### Hard bounds

- No Q5 or L-series gate is reopened, repeated, or re-reviewed.
- No WCC middle-end, provider-isolation, provider adapter, dashboard, security,
  secret-handling, or safety behavior is edited. Security-related tests are
  outside M1's explicitly non-security broad gate, per owner direction.
- No ML, MC, MR, M2, M3, M4, E0, P-series, parked-evolution, prompt-calculus,
  or type-parsimony work is selected by this plan.
- Historical plans, reports, and `docs/plans/evidence/yaml-retirement/` are
  immutable provenance. Current routing may describe their tools as
  historical, but historical commands are not rewritten.
- No workflow is launched and no current `.orc` run is resumed.
- No worktree, new evidence schema, durable recovery class, capture window, or
  discretionary attestation is created.
- Each behavior-changing task uses RED-first tests. Each task receives its
  plan-mandated independent specification review followed by a distinct
  quality review exactly once; replay only after a material correction.
- Deletions must remain net-negative. Exact added/deleted physical-line and
  tracked-byte totals are recorded at closure.

### What this makes harder

Historical retirement and migration-evidence generators will be recoverable
only from Git, not from the installed package. Archived runs will no longer
appear in ordinary live-run listings until deliberately restored. Keeping the
six old current-format nonterminal runs means M1 does not fully empty the live
root; their later disposition remains separate work.

## Historical execution closure

Tasks 0–7 landed in order:

| Task | Commit |
| --- | --- |
| 0 — selection | `4e71093d` |
| 1 — surviving-consumer decoupling | `0f4db4fa` |
| 2 — retirement-estate deletion | `2f7d736f` |
| 3 — queue/prompt-gate retirement | `95644b8f` |
| 4 — migration-gate retirement | `cb96425d` |
| 5 — frontend/demo compatibility narrowing | `96a02c9f` |
| 6 — YAML resume compatibility retirement | `3f5008fc` |
| 7 — repository-real LSP test isolation | `dae747e7` |

Task 8 was an archive-only operation and created no repository commit. Across
Tasks 1–7, the exact tracked deletion census from the M0 closure tree is:

| Estate | Files | Physical lines | Bytes |
| --- | ---: | ---: | ---: |
| Production | 14 | 29,155 | 1,199,106 |
| Tests excluding fixtures | 10 | 30,261 | 1,157,018 |
| Fixtures | 64 | 10,065 | 392,435 |
| Documentation/configuration/other | 3 | 429 | 21,121 |
| **Total** | **91** | **69,910** | **2,769,680** |

The frozen YAML-retirement evidence stayed byte-for-byte at Git tree
`8df00515e3d88a7d9783dd3ff76286cff973044b`: 217 files and 29,750,265
bytes. The retired generators, queue helpers, and migration gates are
historical; the strict runtime contracts, route-readiness registry,
`frontend_kind` provenance, and state-only report/dashboard views remain
current.

Task 7's exact non-security verification record is:

- collection: 9,692 discovered, 9,675 selected, and 17 owner-excluded
  security tests; log SHA-256
  `5d464250787c2149d251679ab31dc0381f719d4a6dbc5e380e97a4650782d0e7`;
- focused aggregate: 1,858 passed and 1 skipped; log SHA-256
  `81604f3bfbd39cfc4a58c8975bde1e9dbb9718c67f7165979ec3d12b1e68bb73`;
- final broad xdist: 9,656 passed and 19 skipped; log SHA-256
  `1a78dcf6ad66ae7ed2b109c7f4013a334d142d6b8cb963e5d0a9755a00e678cf`;
  and
- the clean wheel contains neither `orchestrator/demo/` nor `.pt` members.

Task 8 moved exactly 4,168 closed/legacy run directories into
`.orchestrate/archive/m1-estate-shrink/20260730T103533Z-063385d73b1f` and
retained exactly the six bound current-format nonterminal `.orc` runs. The two
quiet censuses share SHA-256
`063385d73b1f4f222ac2ebf4f44c3190363af4b74c952c8540c0ac1610136922`;
the archived regular-file manifest has SHA-256
`7c240c68c3a4b6067fb8315aee9a174e12e45c8cf943ad791181c3d0ffbfc213`;
and the retained live-root ID-set has SHA-256
`a0f6f197e1cf9d0b5c6c5f2581007c50d31658397c6fa297c89042b5e87c1c0b`.
Both ordered Task 8 reviews approved the archive record.

Task 9's routing selector, 59-surface route-readiness check, CLI-help check,
retired-package absence checks, and clean wheel-content test all passed without
workflow execution or a live-run-root write. Their combined log has SHA-256
`892ffa2926f8fef700c1be75fe6916010f3e6fab9591d67e34e52812edb3a5cc`.

---

### Task 0: Select M1 on the completed census

**Files:**

- Create:
  `docs/plans/2026-07-29-m1-estate-shrink-component-plan.md`
- Modify: `docs/plans/2026-07-26-substrate-maintenance-track.md`
- Modify: `docs/index.md`
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`

- [x] **Step 1: Capture the three read-only censuses**

Record the retirement, extension, and selector/run-store results in
`Authority, entry evidence, and resolved bounds`. Do not create a second
machine-readable inventory.

- [x] **Step 2: Resolve the implementation choices**

Record the seven choices above: existing retirement evidence is sufficient;
route readiness retained; `frontend_kind` retained as provenance; demo
excluded from the wheel; report/dashboard retained; six `.orc` nonterminal
runs retained; closed legacy runs moved reversibly.

- [x] **Step 3: Write the routing test RED**

Replace the stale M0-candidate assertion with an M1 assertion that requires:

- M0's externally bound commit/tree/postcommit closure;
- this component plan routed from the track and index;
- M1's selected bounded deletion shape;
- current route readiness and `frontend_kind` provenance retained;
- Tasks 0–9 and ordered review tokens present; and
- archive, security, Q/L, and evidence-schema bounds literal.

Before the plan and routing edits, the selector must fail because this plan
does not exist.

- [x] **Step 4: Route the completed M0 boundary and M1 candidate**

Update the substrate-track header, phase table, M0 section, and M1 section.
Update both substrate routing entries and the current-substrate selection
paragraph in `docs/index.md`. Keep the M0 plan entry as historical evidence.
The text must say that selection is effected by external ordered approval and
commit of the exact Task 0 candidate, not by its own status prose.

- [x] **Step 5: Run the routing selector**

```bash
pytest -q \
  tests/test_workflow_lisp_drain_roadmap_routing.py::test_m1_estate_shrink_routes_the_completed_m0_boundary_and_bounded_deletion_plan
```

Expected: one pass.

- [x] **Step 6: Obtain the single ordered plan-review pass**

Bind both reviewers to the same `git diff` hash and plan-file SHA-256.
Specification review runs first; quality review runs only after specification
approval. Required verdicts:

1. `M1_PLAN_SPEC_APPROVED`
2. `M1_PLAN_QUALITY_APPROVED`

If either reviewer identifies a material issue, apply one batched correction
and replay the ordered pair once. Otherwise do not repeat either review.

- [x] **Step 7: Commit the reviewed Task 0 candidate**

Stage only the four Task 0 paths and commit with subject:

```text
Select M1 estate shrink
```

Record the exact commit/tree and review-record digest in the external M1
closure workspace. Begin Task 1 immediately.

---

### Task 1: Decouple surviving tests from retirement tooling

**Files:**

- Modify: `tests/test_workflow_lisp_procedure_first_migrations.py`
- Modify: `tests/test_workflow_lisp_key_migrations.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_loader_validation.py`
- Test: `tests/test_yaml_frontend_retirement.py`

- [x] **Step 1: Prove the current coupling**

Collect the five surviving modules and inventory only references to
`orchestrator.retirement` and
`orchestrator.workflow_lisp.procedure_identity_retirement`.

- [x] **Step 2: Write the replacement boundary assertions**

Keep current runtime behavior coverage while removing served-purpose
generators:

- remove the procedure-first carrier/leak scanner fixtures and their tests;
- replace tracked-plan identity-store regeneration tests with checks over the
  already-retained static run/evidence artifacts, or delete the assertion when
  it exists solely to test the retiring generator;
- remove only the obsolete retirement-evidence patch arm from the resume
  ordering test while preserving checksum/projection/executor ordering; and
- replace loader retirement-reader implementation guards with package-absence
  and current YAML-frontend-retirement boundaries.

Do not weaken `tests/test_yaml_frontend_retirement.py`.

- [x] **Step 3: Remove the mixed-module imports and obsolete cases**

Delete private retirement-tool imports, helpers, patches, and tests. Keep the
remaining modules collectible without `create=True` patches or import
fallbacks.

- [x] **Step 4: Run collection and focused behavior checks**

```bash
PYTHONDONTWRITEBYTECODE=1 pytest --collect-only -q -p no:cacheprovider \
  tests/test_workflow_lisp_procedure_first_migrations.py \
  tests/test_workflow_lisp_key_migrations.py \
  tests/test_resume_command.py \
  tests/test_loader_validation.py \
  tests/test_yaml_frontend_retirement.py

PYTHONDONTWRITEBYTECODE=1 pytest -q \
  tests/test_workflow_lisp_procedure_first_migrations.py \
  tests/test_workflow_lisp_key_migrations.py \
  tests/test_loader_validation.py \
  tests/test_yaml_frontend_retirement.py \
  tests/test_resume_command.py::test_projection_resume_root_cli_audit_precedes_override_session_process_and_executor
```

- [x] **Step 5: Run ordered Task 1 reviews and commit**

Review the exact diff for preservation of surviving behavior, then quality.
Required verdicts:
`M1_TASK1_SPEC_APPROVED`, then `M1_TASK1_QUALITY_APPROVED`.
Commit subject:

```text
Decouple M1 retirement consumers
```

---

### Task 2: Delete the served-purpose retirement estate

**Files:**

- Delete: `orchestrator/retirement/`
- Delete:
  `orchestrator/workflow_lisp/procedure_identity_retirement.py`
- Delete: `tests/test_retirement_attempt_migration.py`
- Delete: `tests/test_retirement_source_bindings.py`
- Delete: `tests/test_retirement_broad_evidence.py`
- Delete: `tests/retirement_broad_evidence_support.py`
- Delete:
  `tests/test_workflow_lisp_procedure_identity_retirement.py`
- Delete: `tests/fixtures/retirement_broad_evidence/`
- Delete:
  `tests/fixtures/workflow_lisp/procedure_identity_retirement/`
- Preserve: `docs/plans/evidence/yaml-retirement/`

- [x] **Step 1: Reconfirm the pre-deletion boundary**

Require no production consumer outside the deletion set and no surviving test
import after Task 1. Reconfirm the evidence Git tree is
`8df00515e3d88a7d9783dd3ff76286cff973044b` before deletion.

- [x] **Step 2: Delete in dependency order**

Delete dedicated tests/fixtures, the standalone identity-retirement module,
then `attempt_migration`, `source_bindings`, `materialization`,
`broad_evidence`, `safe_io`, and the retirement package initializer. There is
no `state_store.py`; do not invent or search for a replacement.

- [x] **Step 3: Prove package and reference absence**

```bash
rg -n \
  'orchestrator\\.retirement|orchestrator/retirement|procedure_identity_retirement' \
  orchestrator tests scripts pyproject.toml

python - <<'PY'
import importlib.util
from setuptools import find_packages

assert importlib.util.find_spec("orchestrator.retirement") is None
assert (
    importlib.util.find_spec(
        "orchestrator.workflow_lisp.procedure_identity_retirement"
    )
    is None
)
assert "orchestrator.retirement" not in find_packages(include=["orchestrator*"])
PY
```

Any remaining current code/test reference is a failure. Historical docs and
evidence references are permitted.

- [x] **Step 4: Run the surviving focused boundary**

Repeat Task 1's collection and focused run. Confirm the YAML-retirement
evidence tree and file count are unchanged.

- [x] **Step 5: Run ordered Task 2 reviews and commit**

Required verdicts:
`M1_TASK2_SPEC_APPROVED`, then `M1_TASK2_QUALITY_APPROVED`.
Commit subject:

```text
Retire served-purpose migration evidence tooling
```

---

### Task 3: Remove dead queue and prompt-gate utilities

**Files:**

- Modify: `specs/queue.md`
- Modify: `specs/acceptance/index.md`
- Modify: `MIND_MAP.md`
- Modify: `orchestrator/fsq/__init__.py`
- Delete: `orchestrator/fsq/queue.py`
- Delete: `tests/test_queue_operations.py`
- Delete: `scripts/provider_prompt_dependency_broad_gate.py`
- Delete: `tests/test_provider_prompt_dependency_broad_gate.py`
- Delete:
  `tests/baselines/workflow_lisp/provider_prompt_dependencies_broad_known_failures.json`
- Delete: `scripts/validate_prompt_dependency_evidence.py`
- Modify: `tests/test_prompt_dependency_evidence.py`
- Modify: `orchestrator/exceptions.py`
- Remove ignored local files, if present:
  `orchestrator/__pycache__/loader.cpython-311.pyc` and
  `orchestrator/__pycache__/loader.cpython-313.pyc`

- [x] **Step 1: Amend queue authority before deleting its helper**

Change `specs/queue.md` so atomic `*.tmp` to `*.task` publication is an
author/tool convention rather than a promised framework `QueueManager` API.
Apply the same ownership wording to the normative inbox-atomicity row in
`specs/acceptance/index.md`, and update the stale `MIND_MAP.md` edge. Preserve
`WaitFor` and the independent CLI processed-item clean/archive behavior.

- [x] **Step 2: Write RED absence and retention controls**

Require `QueueManager` and its re-exports absent while `WaitFor` remains
importable. Require both removed prompt-gate scripts absent while the live
`workflow.prompt_dependency_evidence` validator remains covered. Replace
wrapper-specific AST assertions with assertions against the live validator
module only.

- [x] **Step 3: Delete utilities and correct loader wording**

Delete the queue half, gate scripts, dedicated test, and gate-owned known
failure baseline. Correct only the stale loader docstring in
`orchestrator/exceptions.py`. Remove the two ignored bytecode files from the
local filesystem; they are not commit content.

- [x] **Step 4: Run focused checks**

```bash
pytest -q \
  tests/test_wait_for.py \
  tests/test_at60_wait_for_integration.py

pytest -q \
  tests/test_prompt_dependency_evidence.py \
  tests/test_prompt_dependency_content_snapshot.py \
  tests/test_workflow_lisp_provider_prompt_dependencies.py \
  tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py \
  tests/test_provider_attempt_allocation.py

python -m orchestrator --help
```

Security- and safety-named modules are not part of this M1 selector.

- [x] **Step 5: Run ordered Task 3 reviews and commit**

Required verdicts:
`M1_TASK3_SPEC_APPROVED`, then `M1_TASK3_QUALITY_APPROVED`.
Commit subject:

```text
Retire dead queue and prompt gates
```

---

### Task 4: Retire drained migration gates while preserving route readiness

**Files:**

- Delete:
  `orchestrator/workflow_lisp/migration_parity.py`
- Delete:
  `orchestrator/cli/commands/migration_parity.py`
- Delete: `tests/test_workflow_lisp_migration_parity.py`
- Delete:
  `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
- Delete:
  `orchestrator/workflow_lisp/post_wcc_inventory.py`
- Delete:
  `orchestrator/cli/commands/post_wcc_inventory.py`
- Delete: `tests/test_workflow_lisp_post_wcc_inventory.py`
- Delete:
  `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/post_wcc_current_state_inventory.json`
- Delete:
  `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/post_wcc_reconciliation_index.md`
- Modify: `orchestrator/workflow_lisp/route_readiness.py`
- Modify:
  `orchestrator/cli/commands/route_readiness.py`
- Modify: `orchestrator/cli/main.py`
- Modify: `orchestrator/cli/commands/__init__.py`
- Modify: `tests/test_workflow_lisp_route_readiness.py`
- Modify: `tests/test_workflow_lisp_cli.py`
- Modify: `tests/test_workflow_lisp_procedure_first_migrations.py`
- Modify: `tests/test_workflow_lisp_stdlib_form_migration.py`
- Modify: `tests/test_lisp_frontend_autonomous_drain_runtime.py`
- Modify:
  `docs/workflow_lisp_route_readiness_registry.json`
- Modify:
  `docs/plans/2026-07-13-procedure-first-reuse-inventory.json`
- Modify the current, non-historical migration/authoring authorities and
  prompts that still route through the drained generators

- [x] **Step 1: Freeze active versus retired ownership**

Retain route-registry compilation, copy-safety checks, CLI validation, and
ordinary route fixtures. Remove only migration-manifest comparison and
post-WCC inventory generation. Preserve frozen parity reports as historical
evidence.

- [x] **Step 2: Write RED CLI and registry controls**

Require the migration-parity and post-WCC verbs absent from
`python -m orchestrator --help`. Require the route-readiness verb and current
registry cases to remain valid. Remove only the retired evidence row and
parity-only test cases; do not hard-code a replacement count until the edited
registry validates.

- [x] **Step 3: Delete the drained clusters and update current authority**

Remove CLI parser/dispatch/imports, modules, dedicated tests, manifests, and
generated post-WCC views. Strip migration coupling from route readiness.
Update current architecture/drafting/README/prompt/inventory references.
Historical plans and reports retain their commands and paths.

- [x] **Step 4: Run focused and CLI integration checks**

```bash
pytest --collect-only -q \
  tests/test_workflow_lisp_route_readiness.py \
  tests/test_workflow_lisp_examples.py \
  tests/test_workflow_lisp_stdlib_form_migration.py \
  tests/test_workflow_lisp_procedure_first_migrations.py \
  tests/test_lisp_frontend_autonomous_drain_runtime.py \
  tests/test_workflow_lisp_cli.py

pytest -q \
  tests/test_workflow_lisp_route_readiness.py \
  tests/test_workflow_lisp_examples.py \
  tests/test_workflow_lisp_stdlib_form_migration.py \
  tests/test_workflow_lisp_procedure_first_migrations.py \
  tests/test_lisp_frontend_autonomous_drain_runtime.py \
  tests/test_workflow_lisp_cli.py

python -m orchestrator workflow-lisp-route-readiness \
  --registry docs/workflow_lisp_route_readiness_registry.json --check
python -m orchestrator --help
```

- [x] **Step 5: Run ordered Task 4 reviews and commit**

Required verdicts:
`M1_TASK4_SPEC_APPROVED`, then `M1_TASK4_QUALITY_APPROVED`.
Commit subject:

```text
Retire drained Workflow Lisp migration gates
```

---

### Task 5: Narrow frontend compatibility and demo packaging

**Files:**

- Modify: `orchestrator/workflow/executor.py`
- Modify: `tests/test_runtime_observability.py`
- Modify: `pyproject.toml`
- Create: `tests/test_packaging_contract.py`
- Test: active demo and runtime-observability suites

- [x] **Step 1: Write the frontend RED boundary**

Change the three runtime-observability fixtures that assign
`_compiled_frontend_kind` directly so they construct
`CompiledFrontendIndex` provenance. Assert current compiled provenance still
drives observability. Do not remove the persisted `frontend_kind` field,
producer, validation guards, resume logic, or presentation consumers.

- [x] **Step 2: Remove only the redundant executor shim**

Delete the seven-line compatibility property and duplicate two-line outer
guard identified by the census. A zero-context grep/diff check must show that
no other `frontend_kind` behavior changed.

- [x] **Step 3: Write the wheel RED and exclude demo packages**

Build a wheel before the change and demonstrate it contains
`orchestrator/demo/`. Add:

```toml
exclude = ["orchestrator.demo", "orchestrator.demo.*"]
```

to setuptools package discovery. Add a wheel-content assertion that the built
wheel contains neither `orchestrator/demo/` nor `.pt` files. Keep repository
demo sources, fixtures, and tests.

- [x] **Step 4: Run focused behavior and packaging checks**

```bash
pytest -q tests/test_runtime_observability.py -k compiled_frontend
pytest -q \
  tests/test_runtime_observability_cli.py \
  tests/test_dashboard_compiled_workflow.py
pytest -q tests/test_workflow_shared_validation.py \
  -k 'provider_call_policy or generated_step_admission'
pytest -q tests/test_subworkflow_calls.py -k retry_lineage

pytest -q \
  tests/test_demo_provisioning.py \
  tests/test_demo_linear_classifier_evaluator.py \
  tests/test_demo_nanobragg_entrypoint_evaluator.py \
  tests/test_demo_nanobragg_evaluator.py \
  tests/experiments/test_lean_pilot_evaluation.py \
  tests/experiments/test_lean_pilot_treatment_parity.py
```

Build a clean wheel and inspect its archive contents. Do not install torch or
add a demo extra.

- [x] **Step 5: Run ordered Task 5 reviews and commit**

Required verdicts:
`M1_TASK5_SPEC_APPROVED`, then `M1_TASK5_QUALITY_APPROVED`.
Commit subject:

```text
Narrow frontend and demo compatibility
```

---

### Task 6: Remove completed-YAML resume compatibility

**Files:**

- Modify: `orchestrator/cli/commands/resume.py`
- Modify: `tests/test_resume_command.py`
- Modify: `tests/test_yaml_frontend_retirement.py`
- Modify: `specs/dsl.md`
- Modify: `docs/runtime_execution_lifecycle.md`
- Modify current CLI/state documentation only if it promises the fast-return

- [x] **Step 1: Write the RED legacy-resume assertion**

Change the completed YAML/YML resume cases in `tests/test_resume_command.py`
and `tests/test_yaml_frontend_retirement.py` to require nonzero failure with
`.orc required`, no executor construction, and an unchanged run-directory
snapshot. Keep current `.orc` completed-resume behavior green.

- [x] **Step 2: Delete only the completed-YAML fast return**

Remove the `workflow_suffix in {".yaml", ".yml"}` plus completed-state
success branch. Leave the single non-`.orc` fail-closed guard. Do not touch
report or dashboard rendering.

- [x] **Step 3: Update the explanatory compatibility boundary**

Amend the normative frontend/resume boundary in `specs/dsl.md`, then its
explanation in `docs/runtime_execution_lifecycle.md`: every non-`.orc` resume
now fails closed after state lookup. State-only report/dashboard views remain
non-executable observability.

- [x] **Step 4: Run focused CLI and state checks**

```bash
pytest -q \
  tests/test_resume_command.py \
  tests/test_cli_report_command.py \
  tests/test_dashboard_projection.py \
  tests/test_dashboard_server.py \
  tests/test_yaml_frontend_retirement.py

python -m orchestrator --help
```

- [x] **Step 5: Run ordered Task 6 reviews and commit**

Required verdicts:
`M1_TASK6_SPEC_APPROVED`, then `M1_TASK6_QUALITY_APPROVED`.
Commit subject:

```text
Retire completed YAML resume compatibility
```

---

### Task 7: Prove the post-deletion code boundary

**Files:** no intentional product edits. If and only if the exact broad gate
reproduces an xdist-only repository-sharing race, a test-isolation correction
may touch the owning test without changing product or LSP behavior.

- [x] **Step 1: Run collection before execution**

Run collection using the exact non-security exclusions below. A collection
failure must be fixed at its owning earlier M1 seam; it is not reclassified.

- [x] **Step 2: Run the focused ownership aggregate**

Run all surviving modules named in Tasks 1–6 together plus:

```bash
pytest -q \
  tests/test_workflow_lisp_generic_run_watchdog.py \
  tests/test_workflow_lisp_verified_iteration_drain.py \
  tests/test_lisp_frontend_autonomous_drain_runtime.py \
  tests/test_workflow_lisp_drain_roadmap_routing.py
```

- [x] **Step 3: Run the exact broad non-security gate in tmux**

From the repository root:

```bash
pytest -q -n 16 --dist=worksteal \
  --ignore=tests/test_at61_at62_wait_for_path_safety.py \
  --ignore=tests/test_cli_safety.py \
  --ignore=tests/test_execution_safety.py \
  --ignore=tests/test_provider_isolation_attestation.py \
  --ignore=tests/test_provider_isolation_backend.py \
  --ignore=tests/test_provider_isolation_backend_identity_negatives.py \
  --ignore=tests/test_provider_isolation_bundle_broker.py \
  --ignore=tests/test_provider_isolation_candidate.py \
  --ignore=tests/test_provider_isolation_controller_lifecycle.py \
  --ignore=tests/test_provider_isolation_environment.py \
  --ignore=tests/test_provider_isolation_environment_cli.py \
  --ignore=tests/test_provider_isolation_execution.py \
  --ignore=tests/test_provider_isolation_network_preflight.py \
  --ignore=tests/test_provider_isolation_policy.py \
  --ignore=tests/test_provider_isolation_runtime_authority.py \
  --ignore=tests/test_provider_isolation_schema_resources.py \
  --ignore=tests/test_provider_isolation_workflow_continuation.py \
  --ignore=tests/test_provider_isolation_workflow_lifecycle.py \
  --ignore=tests/test_provider_launch_shim.py \
  --ignore=tests/test_secrets.py \
  --ignore=tests/test_workflow_provider_isolation_integration.py \
  -k 'not security and not secret and not isolation and not safety'
```

Expected: exit `0` with only the 17 owner-excluded security selectors
deselected and no retained-failure comparison.

- [x] **Step 4: Fail closed on any broad failure**

Do not reclassify a nonzero xdist result. If the established
shared-repository L5 race reproduces, prove it passes serially, make the
smallest test-only workspace-isolation correction, obtain
`M1_TASK7_SPEC_APPROVED` then `M1_TASK7_QUALITY_APPROVED` for that correction,
and rerun the complete exact broad command over all 9,675 selected tests to
exit `0`. This is gate reliability work, not an L5 behavior change or gate
reopening. Any other failure returns to its owning M1 task.

- [x] **Step 5: Record fresh logs and continue**

Store logs outside Git under the M1 closure workspace, record their SHA-256
digests, and proceed directly to Task 8. Do not add an evidence schema or
baseline-comparison lifecycle.

---

### Task 8: Reversibly archive the closed legacy run estate

**Files:** filesystem move under `.orchestrate/`; no product source edit.

- [x] **Step 1: Establish a final quiet census**

Require no live `orchestrator run` or `orchestrator resume` process. Capture
two identical censuses, normalized by run ID, at least 60 seconds apart. Fail closed
if any run changes, a seventh current-format nonterminal appears, one of the
six retained IDs changes status/content, or a top-level run entry is a
symlink.

- [x] **Step 2: Create the archive directory and plain manifests**

Create:

```text
.orchestrate/archive/m1-estate-shrink/<UTC>-<census-digest12>/
  census-before.tsv
  move-plan.tsv
  regular-files.sha256
  symlinks.tsv
  disposition.txt
  runs/
```

These are plain operational files, not a new application schema. Before
creating the leaf archive, require its destination path absent and require
`stat` to report the same device for `.orchestrate/runs` and the archive
parent. The census records run ID, state presence, status, frontend partition,
file count, byte count, and state SHA-256. `move-plan.tsv` has one
lexicographically ordered row per selected run with its exact disposition
(`terminal`, `unsupported_abandoned_yaml_nonterminal`, or
`stateless_orphan`) and source-state digest. `regular-files.sha256` covers
every regular file relative to the selected run roots; `symlinks.tsv` records
each internal symlink path and target without dereferencing it.
`disposition.txt` cites this plan and the owner disposition for legacy
nonterminal runs.

- [x] **Step 3: Move exactly the bound set by same-filesystem rename**

Move:

- every terminal run;
- every nonterminal YAML/YML run already owner-dispositioned
  unsupported/abandoned; and
- state-less orphan `20260615T010145Z-xl2f1b`.

Do not move the six current-format nonterminal runs. Rename each top-level run
directory into the archive's `runs/` directory; do not copy-and-delete.
After every interruption, validate that each planned ID exists in exactly one
of source or destination with the bound state/content digest. Continue
lexicographically when every observed row validates. If any row is missing,
duplicated, or mismatched, stop and restore already-moved rows in reverse
lexicographic order, only into absent source IDs; never continue across an
invalid partial move.

- [x] **Step 4: Verify content and retained-live state**

From the archive `runs/` directory, verify every regular-file hash and
internal symlink entry. Require the archived census to equal the selected
pre-move census, and require the live root to contain exactly the six retained
run IDs with unchanged state hashes.

Restoration is intentionally simple: while no run/resume process is live,
rename an archived run directory back only when the destination ID is absent,
then re-run its manifest check. Never overwrite a live run ID.

- [x] **Step 5: Run ordered Task 8 reviews**

Review the pre/post census, manifest verification, exact retained IDs, and
restore instructions. Required verdicts:
`M1_TASK8_SPEC_APPROVED`, then `M1_TASK8_QUALITY_APPROVED`.
No repository commit is needed for the ignored archive; bind the review and
manifest digests in the external closure record.

---

### Task 9: Close M1 on current routing and exact evidence

**Files:**

- Modify: `docs/capability_status_matrix.md`
- Modify: `docs/index.md`
- Modify: `docs/design/README.md`
- Modify:
  `docs/design/workflow_lisp_procedure_migration_identity_compatibility.md`
- Modify: `docs/plans/2026-07-26-substrate-maintenance-track.md`
- Modify:
  `docs/plans/2026-07-29-m1-estate-shrink-component-plan.md`
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`
- Modify any current drafting/architecture route left stale by Tasks 2–6

- [x] **Step 1: Record exact closure facts**

Record exact production/test/fixture LOC and tracked-byte deletion totals,
focused/broad/package gate results and log digests, archive census/manifest
digests, the retained six-run live-root digest, and each task commit. Mark
retirement generators and drained migration gates historical while keeping
the strict runtime contracts and route readiness current.

- [x] **Step 2: Update routing and capability status**

Mark M1 an implemented closure candidate, M0 historical complete, and ML
eligible but unselected pending its own ML-0 specification amendment and
component plan. Do not select ML, MC, or MR by listing. Keep Q/L completion
wording unchanged.

- [x] **Step 3: Run post-archive non-mutating controls**

Run the roadmap routing selector, route-readiness check, CLI help, package
absence checks, and wheel-content check. Do not re-run a workflow or a test
that writes the live run root after the Task 8 archive census.

- [x] **Step 4: Obtain ordered final reviews**

Bind the exact closure diff, task-commit list, gate-log digests, and archive
manifest digest. Required verdicts, once each:

1. `M1_FINAL_SPEC_APPROVED`
2. `M1_FINAL_QUALITY_APPROVED`

If a material finding changes a byte or evidence binding, apply one batched
correction and replay the ordered pair. Do not re-review unchanged M0, Q5, or
L-series surfaces.

- [x] **Step 5: Commit the exact reviewed closure candidate**

Commit only the reviewed repository bytes with subject:

```text
Close M1 estate shrink
```

Bind the resulting commit and tree to the external verdict record. The commit
must contain exactly the reviewed index.

- [x] **Step 6: Run the postcommit control**

Run the non-mutating Task 9 selector against the committed tree. Record its
result and log SHA-256 externally. Only then mark M1 complete and expose ML as
eligible/unselected; selection of the next tranche requires its own governing
gate and plan.

Closure commit
`57c2604e595d22dc9d9d656409607f81b332b5f8` has tree
`fc0fdbefe2cdd99cf0f9de604aa63582f79425ea`. The postcommit selector passed in
1.03 seconds; its log SHA-256 is
`63666262609cff772df33f9b25c9d6a2f55668c9028953f476842f31ddc09e3b`.
The external record contains `M1_FINAL_SPEC_APPROVED` followed by
`M1_FINAL_QUALITY_APPROVED`; neither review was repeated because neither found
a material issue.

---

## Completion gate

M1 is complete only when:

- Tasks 0–9 are complete;
- the 55,289-line direct retirement estate and the measured extension estate
  are deleted with exact totals recorded;
- current route readiness, `frontend_kind` provenance, report/dashboard
  state-only views, and the six current-format nonterminal runs remain;
- `docs/plans/evidence/yaml-retirement/` retains its original Git tree;
- the broad non-security xdist gate and serial concurrency control exit `0`;
- the wheel contains no `orchestrator/demo/` package;
- the legacy archive passes its content manifest and restore contract;
- capability and routing docs describe current versus historical surfaces
  truthfully;
- ordered final reviews approve the exact candidate;
- those exact bytes are committed; and
- the postcommit non-mutating control passes.
