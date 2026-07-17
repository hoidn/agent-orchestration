# YAML Retirement Stage-6 Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the reviewed procedure-first inventory and the 2026-07-14
deletion-first steering decision into one exact, machine-checked Stage-6 YAML
retirement handoff without deleting, porting, archiving, renaming, or launching
any workflow.

**Architecture:** Add a `yaml_retirement_handoff` projection to the existing
procedure-first inventory. It partitions the complete checked-in
`workflows/**/*.yaml` and `workflows/**/*.yml` estate into five exact queues,
maps all 63 `legacy-retire` call records into the two queues that contain them,
and separately freezes retained Workflow Lisp effect/public boundaries as
non-retirement inputs. The handoff records repository-reference and run-store
scan contracts, but Stage 6 remains fail-closed: no later deletion is eligible
until its exact queue has zero unclassified active references and zero
match-scoped supported nonterminal run/call-frame consumers.

**Tech Stack:** JSON, Markdown, PyYAML-backed test helpers, `git grep`, `rg`,
pytest, Git, and the existing procedure-first inventory/routing tests.

**Status:** Complete at `7e6adc367a6a16745b5334b2ffc05795f061141d`.
Tasks 1–5 produced the reviewed, machine-checked five-queue handoff and closed
Migration-Waves Task 7 without changing workflow source or run stores. All
Stage-6 queues remain pending their own gates; Migration-Waves Task 8 owns the
whole-wave closeout and final routing change.

---

## Authority And Entry Gate

This plan is a bounded component of Task 7 in
`docs/plans/2026-07-13-procedure-first-migration-waves-plan.md`. Its durable
authorities are:

- `docs/plans/2026-07-07-yaml-retirement-program.md`, specifically the
  2026-07-14 deletion-first steering amendment;
- `docs/plans/2026-07-13-procedure-first-reuse-inventory.json`, for active
  call/public-entry records and append-only migration history;
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`, for the two
  surviving YAML families' later `.orc` promotion gates;
- `docs/design/workflow_lisp_procedure_first_reuse_contract.md`, for retained
  Workflow Lisp public/effect boundaries; and
- the runtime source/checksum behavior in
  `orchestrator/cli/commands/resume.py` and `orchestrator/state.py`, which makes
  nonterminal source consumers a deletion gate rather than a documentation
  detail.

Do not start this plan until Migration-Waves Task 6 has completed both
independent reviews and committed its inventory result. The expected Task-6
closeout is:

- 0 `procedure-candidate` active records;
- 32 `effect-adapter` active records;
- 63 `legacy-retire` active records;
- 13 separate `public-entry` records; and
- one append-only history row.

If the fresh inventory differs, stop before writing RED tests and reconcile
Task 6. Do not silently change the queue totals below to accommodate an
unreviewed source or inventory delta.

This plan intentionally does **not**:

- delete or rewrite any YAML/YML workflow;
- create either surviving `.orc` port;
- archive the Design Delta YAML family;
- mutate any run store or decide that a persisted run is stale/unsupported;
- claim that repository reference searches discover arbitrary downstream
  clones; or
- advance the governing roadmap to Stage 6. Migration-Waves Task 8 owns that
  final routing change after the broad gate and holistic reviews.

## Locked Queue Contract

The checked-in estate observed during planning contains 110 YAML/YML paths.
The implementation must materialize every path explicitly in the inventory;
the counts below are acceptance constraints, not substitutes for path lists.

| Queue ID | Disposition | YAML/YML paths | `legacy-retire` IDs | Stage-6 owner |
| --- | --- | ---: | ---: | --- |
| `delete_non_survivor_estate` | Delete; no `.orc` replacement required by steering | 100 | 53 | YAML retirement Task 6, dependency-aware batches of at most 15 files |
| `archive_design_delta_yaml_twin` | Archive after reconfirming the already-promoted `.orc` primary | 7 | 10 | Design Delta archive gate plus YAML retirement Task 6 |
| `port_verified_iteration` | Create, prove, promote, then retire its own `.orc` port | 1 | 0 | YAML retirement Task 5 |
| `port_generic_run_watchdog` | Create, prove, promote, then retire its own `.orc` port | 1 | 0 | YAML retirement Task 5 |
| `hold_non_progress_step_back` | Preserve until the owning recovery work records delete-or-port disposition | 1 | 0 | Step-back recovery owner, then YAML retirement |

The deletion-first steering authorizes `delete_non_survivor_estate` as an
early independent Stage-6 tranche once its own reference, import,
supported-run-consumer, batch-size, and review gates pass; it does not wait for
the two ports or enabling frontend tasks. `archive_design_delta_yaml_twin`
retains `delete_non_survivor_estate` as its exact queue prerequisite.

The singleton paths are exactly:

- `workflows/examples/verified_iteration_drain.yaml`;
- `workflows/examples/generic_run_watchdog.yaml`; and
- `workflows/examples/non_progress_step_back_demo.yaml`.

The Design Delta archive queue is exactly:

1. `workflows/examples/lisp_frontend_design_delta_drain.yaml`
2. `workflows/library/lisp_frontend_design_delta_selector.v214.yaml`
3. `workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml`
4. `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml`
5. `workflows/library/lisp_frontend_design_delta_done_review.v214.yaml`
6. `workflows/library/lisp_frontend_design_delta_plan_phase.v214.yaml`
7. `workflows/library/lisp_frontend_design_delta_implementation_phase.v214.yaml`

`delete_non_survivor_estate` is the exact complement of those ten paths in
the materialized 110-path estate. The complement must still be stored as 100
explicit paths; Stage 6 must never compute its deletion set from a future
glob. Its 53 call records and the Design Delta queue's 10 call records must
partition the 63 active `legacy-retire` IDs exactly once.

The 100-file queue may be split into execution batches only after parsing the
YAML import graph. Each batch is at most 15 files. An importing source is
removed before or in the same batch as its imported library; a library is not
removed while an importer outside the current-or-earlier batches survives.
`workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml`
is in the 100-file queue and must retire before the Design Delta archive
queue, because it imports the Design Delta YAML parent.

Archive means removal from the live `workflows/` estate with provenance kept
in Git history and content-addressed blob IDs. Do not create a live YAML
archive directory: that would preserve the authoring surface under another
name. Historical decision artifacts, including
`artifacts/work/review-parity-check/design_delta_parent_drain.json`, remain
tracked evidence rather than copies of the YAML source.

## Inventory Handoff Schema

Add exactly one top-level object, `yaml_retirement_handoff`, without changing
the meaning of `source_commit` (which remains authored-call extraction
provenance):

```json
{
  "yaml_retirement_handoff": {
    "schema_version": "procedure_first_yaml_retirement_handoff.v1",
    "captured_at_commit": "<full commit before handoff edits>",
    "governing_plan": "docs/plans/2026-07-07-yaml-retirement-program.md",
    "claim_scope": {
      "authoring_roots": ["workflows"],
      "suffixes": [".yaml", ".yml"],
      "downstream_clones_discovered": false
    },
    "estate": {
      "path_count": 110,
      "normalized_path_sha256": "sha256:<digest>",
      "paths": ["<110 exact sorted paths>"]
    },
    "queues": [
      {
        "queue_id": "<one of the five locked IDs>",
        "status": "pending",
        "disposition": "<delete|archive|port|hold>",
        "paths": ["<exact sorted paths>"],
        "legacy_retire_record_ids": ["<exact sorted stable IDs>"],
        "replacement": {
          "kind": "<none|existing_orc_primary|new_orc_port|owner_disposition>",
          "paths": ["<exact replacement paths when already present>"],
          "rationale": "<contract rationale, not parity overclaim>"
        },
        "evidence_paths": [
          {
            "role": "<stable evidence role>",
            "path": "<repository-relative evidence path>"
          }
        ],
        "archive_destination": {
          "kind": "git_history",
          "require_predelete_blob_ids": true
        },
        "stage_6_gate": "<stable task/section reference>",
        "prerequisite_queue_ids": ["<queue IDs>"],
        "reference_gate": "zero_unclassified_active_references",
        "run_consumer_gate": "zero_supported_matching_nonterminal_consumers"
      }
    ],
    "preserved_workflow_lisp_boundaries": {
      "disposition": "preserve_workflow_lisp_boundary",
      "effect_adapter_record_ids": ["<32 exact sorted IDs>"],
      "public_entry_record_ids": ["<13 exact sorted IDs>"]
    },
    "reference_scan_contract": {
      "scopes": ["tracked_repository", "working_tree", "yaml_import_graph"],
      "allowed_classifications": [
        "delete_with_source",
        "reroute_to_orc",
        "temporary_yaml_frontend_test",
        "historical_reference_retained"
      ],
      "deletion_rule": "zero_unclassified_active_references",
      "records": [
        {
          "referenced_yaml_path": "<exact queued path>",
          "referrer_path": "<durable repository-relative path>",
          "reference_kind": "<yaml_import|launch_or_script|test_or_fixture|current_doc|historical_doc>",
          "classification": "<one allowed classification>"
        }
      ],
      "normalized_records_sha256": "sha256:<digest>"
    },
    "run_consumer_scan_contract": {
      "root_scope_status": "pending_adjudication",
      "matching_scope": "exact queue source paths, including nested call-frame ownership",
      "missing_or_unreadable_status": "nonterminal",
      "gate_fields": [
        "matching_terminal_run_count",
        "matching_nonterminal_run_count",
        "matching_call_frame_count"
      ],
      "non_gating_store_fields": [
        "store_terminal_run_count",
        "store_nonterminal_run_count"
      ],
      "deletion_rule": "zero supported matching nonterminal run or call-frame consumer"
    },
    "reconciliation": {
      "estate_path_count": 110,
      "queued_path_count": 110,
      "legacy_retire_record_count": 63,
      "queued_legacy_retire_record_count": 63,
      "effect_adapter_record_count": 32,
      "preserved_effect_adapter_record_count": 32,
      "public_entry_record_count": 13,
      "preserved_public_entry_record_count": 13
    }
  }
}
```

The reference records must use durable path/symbol classifications, not
unstable source line numbers. Search both each exact path and its basename,
because YAML import declarations are normally relative. A textual historical
reference is allowed to remain when explicitly classified; the gate is zero
unclassified **active** references, not zero textual matches.

The run-consumer contract must use match-scoped counts. A nonterminal run of
an unrelated workflow is disclosed under `store_*` fields and does not block a
queue. A match nested below a top-level run belongs to that containing run.
Missing/unreadable status fails closed as nonterminal. The selected supported
run roots and any disposition of stale/unsupported stores require their own
Stage-6 adjudication; this handoff does not manufacture that decision.

A read-only planning probe observed 84 YAML run records labeled `running` or
`suspended`. That number is hygiene context only. It is not evidence that any
record is live, supported, resumable, or in the final supported-root scope, and
it must not be copied into a gating field without a fresh scoped scan and
adjudication.

## Protected Working-Tree Guard

The following user-owned dirty paths are outside this plan and every commit:

- `docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md`
- `docs/plans/2026-07-01-workflow-audit-tier-fixes.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md`
- `state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt`
- `tests/test_workflow_non_progress_step_back_demo.py`
- `workflows/examples/non_progress_step_back_demo.yaml`
- `workflows/library/prompts/workflow_step_back/diagnose_non_progress.md`

Before Task 1, record `git status --short` and SHA-256 for each protected file.
Before every commit, print the complete cached path list, then run the literal
guard below. It must print nothing:

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

Never stage, restore, rewrite, format, or delete a protected path. In
particular, `hold_non_progress_step_back` records the protected YAML path in
the queue manifest but does not authorize changing its bytes.

---

### Task 1: Lock The Handoff Schema And Exact Partition With RED Tests

**Files:**
- Modify: `tests/test_workflow_lisp_procedure_first_migrations.py`
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`

- [x] **Step 1: Capture the Task-7 baseline**

Record the full Task-6 completion commit, `git status --short`, the seven
protected-file digests, and the current inventory totals. Confirm no Task-7
owned file is already modified.

- [x] **Step 2: Add a reusable handoff validator in the migration test module**

Implement a test-only validator that:

1. discovers sorted `workflows/**/*.yaml` and `workflows/**/*.yml` paths;
2. validates the schema and enum fields above;
3. proves the five path lists are disjoint and equal the discovered estate;
4. proves counts are exactly `100 + 7 + 1 + 1 + 1 = 110`;
5. proves the three singleton and seven Design Delta paths are exact;
6. proves the 63 active `legacy-retire` IDs occur exactly once as `53 + 10`;
7. proves every queued legacy ID points at a path in its queue;
8. proves the 32 effect adapters and 13 public entries are listed exactly once
   under `preserved_workflow_lisp_boundaries` and nowhere in a retirement
   queue; and
9. proves `source_commit` was not repurposed as the handoff capture commit.

Use structured JSON assertions. Do not assert literal explanatory prose.

- [x] **Step 3: Add both-direction mutation coverage**

Parameterize copies of the handoff document and prove the validator rejects:

- one missing estate path;
- one extra/nonexistent path;
- a duplicated path across queues;
- `.yml` omission (`workflows/examples/test_validation.yml`);
- a legacy ID missing from both queues;
- a legacy ID assigned twice or assigned to the wrong path queue;
- an effect-adapter/public-entry ID inserted into a retirement queue;
- a missing retained Workflow Lisp boundary;
- a sixth queue or a renamed queue ID;
- a changed Design Delta seven-path set; and
- a port queue whose replacement kind is `none`.

- [x] **Step 4: Add run/reference gate contract tests**

Add generic fixtures proving:

- a supported matching nonterminal top-level run rejects deletion;
- a supported matching nested call-frame associates with and rejects its
  containing top-level run;
- missing/unreadable status rejects deletion;
- unrelated store-wide nonterminal runs do not gate the queue;
- a matching terminal run is evidence only;
- an unclassified active repository reference rejects deletion; and
- an explicitly classified historical reference does not.

These are contract/record tests only; they must not mutate `.orchestrate` or
launch a workflow.

- [x] **Step 5: Add roadmap-program structural guards**

In `tests/test_workflow_lisp_drain_roadmap_routing.py`, parse stable headings
and table fields to require:

- exactly the two port families;
- the separate Design Delta archive queue;
- `.yaml` and `.yml` coverage;
- the reference and supported-run-consumer gates;
- Git-history archive semantics;
- the protected non-progress holdout; and
- Task 7 remaining a handoff-only task with Task 8 next.

Reject the stale six-family promotion table and the superseded open
port-vs-absorb state structurally. Avoid tests coupled to exact paragraph
phrasing.

- [x] **Step 6: Collect and run RED selectors**

```bash
pytest --collect-only -q \
  tests/test_workflow_lisp_procedure_first_migrations.py \
  tests/test_workflow_lisp_drain_roadmap_routing.py

pytest -q \
  tests/test_workflow_lisp_procedure_first_migrations.py \
  tests/test_workflow_lisp_drain_roadmap_routing.py \
  -k 'retirement_handoff or yaml_retirement'
```

Expected: collection succeeds; new positive tests fail because the handoff
object and corrected program queues do not yet exist. Mutation/unit helpers
may already pass.

Do not commit RED-only tests.

### Task 2: Materialize The Machine Handoff And Human Inventory Projection

**Files:**
- Modify: `docs/plans/2026-07-13-procedure-first-reuse-inventory.json`
- Modify: `docs/plans/2026-07-13-procedure-first-reuse-inventory.md`
- Test: `tests/test_workflow_lisp_procedure_first_migrations.py`

- [x] **Step 1: Generate the exact estate and record mappings read-only**

From the repository root, enumerate both suffixes, calculate the normalized
path-list digest, and extract active record IDs from JSON. Do not derive a
deletion list from Markdown.

```bash
find workflows -type f \( -name '*.yaml' -o -name '*.yml' \) | sort
jq -r '.records[] | select(.classification == "legacy-retire") | [.source_path, .id] | @tsv' \
  docs/plans/2026-07-13-procedure-first-reuse-inventory.json | sort
jq -r '.records[] | select(.classification == "effect-adapter") | .id' \
  docs/plans/2026-07-13-procedure-first-reuse-inventory.json | sort
jq -r '.records[] | select(.record_kind == "public-entry") | .id' \
  docs/plans/2026-07-13-procedure-first-reuse-inventory.json | sort
```

Expected after Task 6: 110 YAML/YML paths, 63 legacy IDs, 32 effect-adapter
IDs, and 13 public-entry IDs.

- [x] **Step 2: Add the minimal handoff object**

Populate the schema exactly as specified. Store all 110 estate paths, all 100
delete paths, all record IDs, and all preserved boundary IDs explicitly and in
sorted order. Set every queue `status` to `pending`; this task supplies routing,
not deletion eligibility.

For the Design Delta replacement, name
`workflows/library/lisp_frontend_design_delta/drain.orc`, the route-readiness
registry, and the preserved historical parity artifact. Do not claim
per-child parity or cross-source resume.

For the verified-iteration queue, point to the incomplete translation input at
`docs/plans/2026-07-05-post-foundation-target-completion-plan.md` Task 15 and
state that Stage 6 must add parity, promotion, a verification cycle, and YAML
retirement. For the watchdog queue, record a named prerequisite for a new
bounded implementation plan rather than inventing an `.orc` path that does not
exist.

- [x] **Step 3: Freeze a pending reference-scan contract without overclaiming**

Task 7 is handoff-only and intentionally defers the actual reference scan to
Stage 6. Record the exact future scopes (`tracked_repository`, `working_tree`,
and `yaml_import_graph`), allowed classifications, empty records, normalized
empty-record digest, and `capture_status: pending_stage_6_scan`. Synthetic
fixtures prove the gate semantics; they are not captured repository evidence.

Stage 6 performs the eventual exact-path and basename searches:

```bash
git grep -n -F -- '<exact-path-or-basename>' -- .
rg -n --fixed-strings '<exact-path-or-basename>' . \
  --glob '!.git/**' --glob '!*.pyc' --glob '!**/__pycache__/**'
```

It then parses YAML import maps to distinguish import edges from textual
mentions and normalizes each result to durable paths and one allowed
classification. Current tests/docs/imports remain scheduled work; this handoff
does not claim they were scanned or removed.

Record that this scope covers the repository and current working tree, not
unknown downstream clones.

- [x] **Step 4: Record the run-consumer scan contract, not an eligibility claim**

Document the match-scoped query fields and fail-closed status semantics in the
handoff. A fresh read-only probe may disclose store-wide hygiene totals, but
leave supported-root scope `pending_adjudication` and every queue `pending`.
Do not call a `running`/`suspended` label live or supported without separate
evidence. Do not mutate, terminalize, repair, resume, or delete any run.

- [x] **Step 5: Update the narrative inventory**

Add one concise “Stage-6 YAML Retirement Handoff” section that:

- states the 110-path and 63-ID reconciliation;
- presents the five queues and exact counts;
- explains 53/10 legacy mapping;
- records that 32 effect adapters and 13 public entries remain Workflow Lisp
  boundaries outside YAML retirement;
- distinguishes Git-history source archival from retained historical evidence;
- states the reference/run-consumer gates and pending adjudication boundary;
  and
- makes no deletion, parity, resume, or downstream-consumer claim.

- [x] **Step 6: Run GREEN inventory selectors**

```bash
python -m json.tool \
  docs/plans/2026-07-13-procedure-first-reuse-inventory.json >/dev/null

pytest -q tests/test_workflow_lisp_procedure_first_migrations.py \
  -k 'inventory or legacy_retire or retirement_handoff'
```

Expected: PASS.

### Task 3: Graduate The Triage Into A Stage-6 Queue Projection

**Files:**
- Modify: `docs/workflow_yaml_estate_triage.md`
- Test: `tests/test_workflow_lisp_procedure_first_migrations.py`

- [x] **Step 1: Replace draft authority with projection authority**

Keep the JSON handoff as machine authority. Change the triage header from a
superseded draft heuristic to a generated human projection that names the JSON
object and its capture commit/digest.

- [x] **Step 2: Include both YAML suffixes and every exact path**

Project all 110 inventory paths, including
`workflows/examples/test_validation.yml`. For each row show:

- exact path;
- queue ID;
- disposition;
- retained replacement or deletion rationale;
- legacy-record count;
- archive destination;
- reference/run-consumer gate; and
- current queue status.

Remove the stale draft-class totals. End with exact queue totals and legacy-ID
totals derived from the JSON handoff.

- [x] **Step 3: Add reproducible extraction commands**

Embed commands that cover both `.yaml` and `.yml` and validate the projection
against the JSON object. Do not refer to a nonexistent “Phase-1 Task-13
generator script”; the historical plan contains an inline one-off generator,
not a checked-in script.

- [x] **Step 4: Run projection tests**

```bash
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py \
  -k 'retirement_handoff or yaml_estate or triage'
```

Expected: PASS with the Markdown path/queue projection equal to JSON.

### Task 4: Correct The Stage-6 Program Without Starting It

**Files:**
- Modify: `docs/plans/2026-07-07-yaml-retirement-program.md`
- Test: `tests/test_workflow_lisp_drain_roadmap_routing.py`

- [x] **Step 1: Normalize the steering and architecture header**

Mark the older “port versus absorb remains open” paragraph as superseded or
remove its live instruction. State once that exactly verified-iteration and
generic-watchdog receive independent `.orc` ports.

Correct the architecture summary: Tasks 1–3 are ungated enabling work; the
deprecation surface is gated but its first-family condition is already met by
the Design Delta `.orc` primary. Do not describe four tasks as ungated.

- [x] **Step 2: Add the five exact handoff queues**

Make the JSON handoff the Stage-6 work list and reproduce its five queue IDs,
counts, dependencies, and statuses. Preserve the high-level deletion-first
order:

1. dependency-aware non-survivor deletion batches after their gates;
2. gap-list refresh for the two surviving port families;
3. Design Delta archive after its post-procedure compile/smoke/E2E and
   historical-evidence gate;
4. dashboard typed-surface and loader-validation separation;
5. explicit YAML deprecation surface;
6. the two independent `.orc` ports through parity/promotion; and
7. final remaining-YAML and frontend deletion after the holdout is resolved.

This ordering records future work only. Do not check any Stage-6 execution box.

- [x] **Step 3: Replace the stale six-family Task-5 table**

Task 5 must contain exactly two promotion families:

- `verified_iteration_drain`, with the older Task-15 translation plan as an
  input but not promotion evidence; and
- `generic_run_watchdog`, gated on a dedicated implementation plan.

Delete the stale promotion instructions for autonomous drain, NeurIPS, major
project, and ProcRef families; they are members of the deletion queue.

- [x] **Step 4: Strengthen estate deletion and archive gates**

Replace “ungated” deletion with these requirements per exact batch:

- pre-delete Git blob IDs recorded;
- every repository/working-tree reference classified;
- zero unclassified active references;
- import prerequisites satisfied;
- supported run roots adjudicated;
- zero match-scoped supported nonterminal top-level or nested call-frame
  consumers;
- batch size at most 15;
- affected tests/docs/fixtures deleted, rerouted, or explicitly retained as
  temporary frontend characterization; and
- narrow plus broad baseline comparison recorded.

Do not require zero textual references: historical plans/evidence may retain
classified references. Do not let store-wide unrelated nonterminal totals gate
a batch.

- [x] **Step 5: Correct suffix, archive, generator, and resume wording**

- Cover both `*.yaml` and `*.yml` in estate and final-zero checks.
- Define archive as Git-history removal, not a live YAML archive tree.
- Replace the nonexistent generator-script instruction with the JSON-driven
  projection check.
- Preserve the conservative fail-closed rule that deletion cannot strand a
  supported nonterminal run. Final frontend policy for already persisted,
  terminal historical runs remains a separately recorded Stage-6 decision.
- Carry forward the exact protected-path guard from this plan.

- [x] **Step 6: Run the corrected-program tests**

```bash
pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py \
  -k 'yaml_retirement or migration_wave'
```

Expected: PASS.

### Task 5: Close Migration-Waves Task 7 On Reviewed Handoff Evidence

**Files:**
- Modify: `docs/plans/2026-07-13-procedure-first-migration-waves-plan.md`
- Modify: `docs/plans/2026-07-16-yaml-retirement-handoff-plan.md`
- Test: `tests/test_workflow_lisp_procedure_first_migrations.py`
- Test: `tests/test_workflow_lisp_drain_roadmap_routing.py`

- [x] **Step 1: Run the complete focused handoff gate**

```bash
python -m json.tool \
  docs/plans/2026-07-13-procedure-first-reuse-inventory.json >/dev/null

pytest --collect-only -q \
  tests/test_workflow_lisp_procedure_first_migrations.py \
  tests/test_workflow_lisp_drain_roadmap_routing.py

pytest -q \
  tests/test_workflow_lisp_procedure_first_migrations.py \
  tests/test_workflow_lisp_drain_roadmap_routing.py \
  -k 'legacy_retire or retirement_handoff or yaml_retirement or migration_wave'

git diff --check -- \
  docs/plans/2026-07-07-yaml-retirement-program.md \
  docs/workflow_yaml_estate_triage.md \
  docs/plans/2026-07-13-procedure-first-reuse-inventory.json \
  docs/plans/2026-07-13-procedure-first-reuse-inventory.md \
  tests/test_workflow_lisp_procedure_first_migrations.py \
  tests/test_workflow_lisp_drain_roadmap_routing.py
```

Expected: JSON parses, collection succeeds, focused tests pass, and diff check
is clean.

- [x] **Step 2: Prove the task stayed handoff-only**

Compare the Task-7 start commit and working tree. No workflow source, runtime,
compiler, prompt, run store, fixture, or parity artifact may have changed under
this task. The only dirty paths outside the owned set must match the recorded
user baseline.

- [x] **Step 3: Obtain independent specification review**

The reviewer checks:

- the five exact queue sets and 110-path partition;
- 53/10 mapping of all 63 legacy IDs;
- preservation of all 32 effect-adapter and 13 public-entry IDs;
- no parity or cross-source-resume overclaim;
- fail-closed reference/run-consumer gates;
- pending rather than invented supported-root adjudication;
- corrected deletion-first program order; and
- no Stage-6 execution or YAML mutation.

Expected: PASS. Fix every valid issue and rerun the complete focused gate.

- [x] **Step 4: Obtain independent quality review**

The reviewer checks deterministic ordering/digests, schema clarity, mutation
coverage, durable path/section references, protected-path discipline, absence
of brittle literal-prose assertions, and consistency among JSON, narrative,
triage, program, and selector.

Expected: APPROVED. Fix every valid issue, rerun the complete focused gate,
then repeat both reviews when a correction changes contract meaning.

- [x] **Step 5: Mark Task 7 complete and Task 8 current**

Only after both reviews pass, update the migration-wave plan:

- check all four Task-7 steps;
- record the exact handoff counts and review evidence;
- state that no YAML/workflow/run mutation occurred;
- state that all Stage-6 queues remain pending their own gates; and
- select Task 8 Step 1 without advancing the governing roadmap to Stage 6.

- [x] **Step 6: Rerun routing tests after selector update**

```bash
pytest -q \
  tests/test_workflow_lisp_procedure_first_migrations.py \
  tests/test_workflow_lisp_drain_roadmap_routing.py \
  -k 'retirement_handoff or yaml_retirement or migration_wave'
```

Expected: PASS with Task 7 complete and Task 8 Step 1 current.

- [x] **Step 7: Stage exact paths and commit**

Stage only these eight paths:

```bash
git add \
  docs/plans/2026-07-07-yaml-retirement-program.md \
  docs/workflow_yaml_estate_triage.md \
  docs/plans/2026-07-13-procedure-first-reuse-inventory.json \
  docs/plans/2026-07-13-procedure-first-reuse-inventory.md \
  docs/plans/2026-07-13-procedure-first-migration-waves-plan.md \
  docs/plans/2026-07-16-yaml-retirement-handoff-plan.md \
  tests/test_workflow_lisp_procedure_first_migrations.py \
  tests/test_workflow_lisp_drain_roadmap_routing.py
```

Print `git diff --cached --name-only`. It must equal that exact eight-path set.
Run the literal protected-path guard from this plan; it must print nothing.

```bash
git commit -m "Route compatibility workflows to YAML retirement"
```

Expected: one reviewable handoff commit and no workflow/run mutation.

## Handoff To Migration-Waves Task 8

Task 8 remains responsible for the focused whole-wave gate, broad pytest suite
in tmux, holistic reviews, and synchronization of:

- `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`;
- `docs/capability_status_matrix.md`; and
- `docs/index.md`.

Those surfaces must not call the triage a draft after Task 8, must mention both
YAML suffixes, and must select Stage 6 only after the migration-wave gate
passes. Stage 6 then executes the five queues under their own reference,
run-consumer, parity, archive, and owner gates; this handoff commit is not
deletion authorization.
