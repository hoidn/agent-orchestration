# YAML Retirement Task 6 Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this plan task by
> task. Use `superpowers:test-driven-development` for every production change,
> and obtain separate specification-compliance and code-quality reviews at each
> named review gate. Checkbox (`- [ ]`) syntax defines the immutable execution
> template; live progress is recorded only in the closed evidence-root execution
> ledger defined below. Do not edit this approved plan merely to check a box.

**Goal:** Build generic, fail-closed retirement evidence machinery and use it
to remove the 100-path `delete_non_survivor_estate` YAML/YML queue in seven
dependency-safe, independently reviewed batches without rewriting the frozen
v1 handoff or weakening supported-run-consumer gates.

**Architecture:** Preserve the content-addressed
`procedure_first_yaml_retirement_handoff.v1` document as capture authority and
add a separately versioned execution index whose active and history partitions
always reconcile exactly to that frozen queue. Generic scanners capture
occurrence-level repository references and whole-query run-consumer rows;
content-addressed batch projections derive their own distinct containing-run
and frame sets instead of copying whole-query totals. Closed validators combine
those facts with owner-bound support dispositions, root/source-base bindings,
import order, reference dispositions, and batch dependencies. Each deletion
uses a deletion commit followed by an evidence-closure commit, with a closed
reviewed repair chain available between them when a nonexcluded correction is
genuinely necessary. A generated Markdown live projection is a view of the
checked index, never an independently edited queue. The approved plan remains
immutable; a content-addressed evidence-root ledger owns execution progress.

**Tech Stack:** Python 3, dataclasses and typed mappings, JSON, PyYAML for the
temporary authored-YAML import graph, Git plumbing commands, pytest, xdist,
tmux, and the existing Workflow Lisp procedure-retirement state-store scanner
semantics.

**Status:** Review-bound execution contract; it is not executable until the
pre-Task-1 independent approval and exact planning commit below, after which its
bytes are immutable and live progress is recorded only in the content-addressed
execution ledger. This document does not authorize a deletion, owner
attestation, run-store mutation, workflow launch, or protected-path change.

---

## Authority, Scope, And Explicit Tradeoff

Read these before implementation:

- `AGENTS.md` and `docs/index.md`;
- `docs/plans/2026-07-07-yaml-retirement-program.md`, Task 6;
- `docs/plans/2026-07-16-yaml-retirement-handoff-plan.md`, the frozen v1
  handoff contract;
- `docs/plans/2026-07-13-procedure-first-reuse-inventory.json`, specifically
  `yaml_retirement_handoff`;
- `docs/workflow_yaml_estate_triage.md`, as a projection rather than authority;
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`, for the
  still-separate port and promotion gates; and
- `orchestrator/workflow_lisp/procedure_identity_retirement.py`, only as the
  implementation precedent for stable store traversal, race rejection,
  symlink rejection, normalized digests, and match-scoped counts.

This plan owns the generic machinery and the 100-path
`delete_non_survivor_estate` queue. It prepares the same machinery for the
seven-path Design Delta archive and the old sources of the two port queues, but
does not bypass their distinct archive/parity prerequisites. The protected
holdout remains outside the execution index until its owner changes the frozen
handoff through a separately reviewed decision.

The other four queue source sets are immutable exclusion inputs to this plan,
not editable referrers. Task 2 content-binds all ten non-target YAML/YML paths
from the frozen handoff in `non-target-queue-sources.json`: the seven Design
Delta archive sources, both port sources, and the protected holdout. The
holdout row reuses its protected-path byte binding; the other nine rows bind
their exact tracked mode/blob and worktree byte digest. Every batch and final
validator must compare all ten current paths to that immutable record. A fresh
reference scan that would require editing one of these sources blocks the
batch and routes the occurrence to that queue's owner; no reference
classification or execution refinement in this plan authorizes the edit.
From the Task-2 boundary onward, every plan commit also validates the record
and all ten live paths before staging and immediately at HEAD; the more
specific batch and final gates below repeat rather than replace this invariant.

The direct design is deliberately strict: exact content bindings and closed
schemas make ad hoc queue edits, moving a path between batches after review,
adding a run root without owner adoption, or treating a textual search as
proof harder later. That is the intended tradeoff. A legitimate change must
produce a new reviewed index/evidence version instead of silently changing the
meaning of old evidence.

This execution contract intentionally excludes security-only review and
security-only test work. The only independent review kinds are specification
and code quality; no penetration, threat-model, hostile-environment, malicious-
actor, or security-signoff branch is a prerequisite or completion gate. This
exclusion does not relax non-security evidence integrity required for a safe,
deterministic deletion: exact content digests, closed path sets, no-follow file-
type checks, stable-read and tree-race rejection, duplicate-key rejection,
content-addressed history, index/worktree isolation, concurrent-publication
serialization, and crash-prefix recovery remain mandatory. Tests below use
ordinary deterministic mutation, contention, and malformed-input controls for
those properties. Explicit hostile/adversarial-only branches are deferred
outside this plan and make no claim here.

Production mechanisms must contain no workflow-family, queue, repository,
batch, or owner names. Family and queue names are data in evidence records.
Add a permanent source guard that rejects all 100 queue basenames and the five
repository labels from the new `orchestrator/retirement/` package.

The consistency pass classifies two current assumptions as `stale_duplicate`,
not new authority: the migration test that equates the v1 capture's 63
`legacy-retire` rows and pending queue labels with the current live checkout,
and Task 6 wording that says to regenerate the frozen inventory after a
deletion. The frozen v1 document continues to prove what entered Stage 6; the
execution index and its generated projection own what remains. Do not “fix”
the conflict by changing or dropping the v1 counts.

The v1 `zero_supported_matching_nonterminal_consumers` label is retained as
captured text. The execution contract strengthens, rather than weakens, it:
nonterminal matches still block when supported, and failed/terminal matches
also block whenever resume or consumer support remains. Before deletion, the
roadmap explanation and current routing tests must point to this owner-adopted
support rule without editing the frozen label or pretending terminal status
proved abandonment.

The frozen handoff-v1 reference classification enum and the handoff's captured
empty record set remain byte-for-byte unchanged. The v1 handoff intentionally
contains no captured occurrence classification rows: each Task-7 or fresh batch
scan therefore selects exactly one value from the immutable v1 allowed enum for
each new occurrence, then freezes that selected value within that scan
generation and every consuming history event. A later scan with new occurrence
IDs is classified afresh and never copies a nonexistent v1 parent row. In
particular, `remove_exact_occurrence` is not a fifth v1 classification. Only an
execution record whose per-scan frozen selected classification is
`delete_with_source` adds a separate closed postcondition refinement, either
`delete_referrer_with_source` or `remove_exact_occurrence`. The execution index
and history bind the selected v1-enum value and refinement without projecting
an occurrence row or refinement back into v1.

Before Task 1 execution, dispatch one plan-document reviewer with only this
plan, the Stage-6 program, the frozen handoff plan, and the v1 JSON path as
context. It must approve the whole document. Resolve every valid issue and
repeat the full plan review; implementation work cannot substitute for this
gate.

The approved review must return a unique token binding the exact lowercase
SHA-256 of this complete Markdown byte stream. After approval, make one explicit
reviewed planning commit before Task 1's first-write capture; that commit may
contain only this plan and any separately enumerated, deliberately coupled
planning-routing byte. Record the approval token and digest in the commit's
review evidence or message without editing this plan after review. Immediately
after commit, require the exact bytes from
`git show HEAD:docs/plans/2026-07-17-yaml-retirement-task-6-execution-plan.md`
to hash to the reviewer-approved SHA-256 and require the worktree file to be
byte-identical. A missing/untracked plan, digest mismatch, post-review edit, or
commit containing an unreviewed path blocks Task 1. Task 1's initial ledger may
bind only that committed approved digest. This planning commit is outside the
17-task execution ledger because the materialization implementation does not yet
exist; it grants no deletion or owner authority.

## Read-Only Feasibility Audit To Reproduce

The completed planning audit observed the following facts. They are
characterization inputs, not deletion evidence; Task 7 must reproduce them
fresh before mutation.

- The frozen queue contains 100 tracked, currently unmodified paths. The
  UTF-8, newline-delimited sorted path query digest is
  `sha256:2b4cdaf11ce8570c35cde84987ef73a0a51e985d1d8e3588443a16b8ebac2b63`.
- The authored YAML import graph contains 51 internal edges, is acyclic, and
  has no importer outside this queue for a queue target.
- A provisional exact-path-plus-basename search found 1,097 unique
  target/referrer pairs across 211 referrers. The implementation must expand
  these to occurrence-level facts because one target/referrer pair can contain
  both active and historical uses. Those occurrences remain unclassified until
  the checked reference record says whether each active use is deleted with its
  source, rerouted, temporary frontend characterization, or retained history.
  The 1,097 pair count is planning characterization only and is never a
  classification-coverage denominator.
- The five candidate supported roots and whole-queue observations were:

| Root | Canonical-path digest | Matching runs | Matching nonterminal runs | Matching nonterminal frames |
| --- | --- | ---: | ---: | ---: |
| `/home/ollie/Documents/agent-orchestration/.orchestrate/runs` | `sha256:976a73eb92cb0ebc3a82da48834d75dff81fd95fe7052ba0a1152e83e86e2711` | 22 | 6 | 30 |
| `/home/ollie/Documents/agent-orchestration-2/.orchestrate/runs` | `sha256:02f3cfd79422a59183ec4e7d0c2ed92c3ea3523fa5f63eebab7bcf08c8f0fb9b` | 22 | 6 | 30 |
| `/home/ollie/Documents/EasySpin/.orchestrate/runs` | `sha256:b96e1f979beac55bd24ba2fcc74c9fa3df99a2d8021b3fca114b1f4aef1fae57` | 35 | 14 | 79 |
| `/home/ollie/Documents/PtychoPINN/.orchestrate/runs` | `sha256:177188cae936e3a6ee73fe2ae8096e2992deeb3372fcce3232505f4a174eff27` | 45 | 13 | 82 |
| `/home/ollie/Documents/ptychopinnpaper2/.orchestrate/runs` | `sha256:f39dd7a79dd46a1524f9810a9ed0fd12ece70f2512042d68bfcc0cf99041a515` | 4 | 0 | 0 |

- The reviewed batch shape is exactly `15/15/10/15/15/15/15`. The audit did
  not emit exact memberships, so this plan forbids inventing them. A checked,
  data-driven batch-assignment task must materialize all exact paths and pass
  both-direction reconciliation, dependency, category, and independent-review
  gates before the first deletion.
- Characterization associates batches 1–3 with no observed matching
  nonterminal consumers; batch 4 with PtychoPINN; batch 5 with EasySpin; batch
  6 with EasySpin and PtychoPINN; and batch 7 with the current checkout and
  repository copy. Fresh evidence, not this table, decides each gate.
- `orchestrator/demo/trial_runner.py` has an active production default pointing
  at `workflows/examples/generic_task_plan_execute_review_loop.yaml`. It must be
  explicitly rerouted or removed as an exact occurrence in the same reviewed
  batch as that target;
  classification as documentation or history is invalid.

## File And Ownership Map

Keep generic code separated by responsibility:

- Create `orchestrator/retirement/broad_evidence.py`: the minimal queue-neutral
  closed broad-outcome, durable implementation-focused report/subject, review,
  owner-adoption, known-failure comparison, and remediation schemas/builders/
  validators required before any baseline capture.
- Create `orchestrator/retirement/source_bindings.py`: the bootstrap-safe,
  queue-neutral workspace-baseline and immutable-source-record builders and
  validators used from Task 2 onward. Its CLI entry point is
  `python -m orchestrator.retirement.source_bindings`; Task 6 re-exports the
  same implementation rather than replacing or reinterpreting it.
- Create `orchestrator/retirement/__init__.py`: stable public imports only.
- Create `orchestrator/retirement/state_store.py`: safe store traversal and
  generic exact-field consumer scanning.
- Create `orchestrator/retirement/repository.py`: tracked/working-tree textual
  reference capture and authored import-graph extraction.
- Create `orchestrator/retirement/evidence.py`: closed JSON schema validation,
  content bindings, batch eligibility, and live projection data.
- Create `scripts/build_retirement_execution_index.py`: generic CLI over the
  production functions; queue-specific choices arrive through input JSON.
- Modify `orchestrator/workflow_lisp/procedure_identity_retirement.py`: retain
  its public API while delegating stable traversal/read primitives to the new
  generic owner.
- Create `tests/test_retirement_state_store.py`.
- Create `tests/test_retirement_repository.py`.
- Create `tests/test_retirement_evidence.py`.
- Create `tests/test_retirement_broad_evidence.py` and only its minimal
  `tests/fixtures/retirement_broad_evidence/` fixtures in the bootstrap task;
  the later evidence task imports this module rather than redefining it.
- Create `tests/test_retirement_source_bindings.py` in the bootstrap task and
  keep the workspace/non-target source schemas owned by that module thereafter.
- Create `tests/fixtures/retirement_broad_evidence/manifest.v1.json` and
  `tests/fixtures/retirement_evidence/manifest.v1.json`: closed admissible-file
  manifests for their directories. Every canonical valid, invalid, pending,
  and confirmed fixture is named by exactly one manifest row; an unlisted file,
  missing row, duplicate schema/lifecycle role, or path-set digest mismatch
  fails collection. These fixtures are checked contract examples, not family
  evidence.
- Modify `tests/test_workflow_lisp_procedure_identity_retirement.py` for
  compatibility equivalence.
- Modify `tests/test_workflow_lisp_procedure_first_migrations.py` so v1 remains
  immutable capture authority while current state is checked through the
  execution index.
- Modify `tests/test_workflow_lisp_drain_roadmap_routing.py` for selector and
  projection routing.
- Create evidence beneath
  `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/`.
- Create and maintain `execution-ledger.json` beneath that root as the sole live
  task/step progress authority; retain every immutable ledger generation under
  the closed output-snapshot layout; keep this approved Markdown plan immutable.
- Create `docs/workflow_yaml_retirement_execution.md` as generated projection.
- Modify `docs/plans/2026-07-07-yaml-retirement-program.md` before the first
  deletion to route Task 6 to the execution index and replace stale
  “regenerate the frozen inventory” wording with “regenerate the checked live
  projection.”
- Modify `docs/workflow_yaml_estate_triage.md` before the first deletion to
  label it a frozen v1 projection and route current state to the live
  projection.
- Modify `docs/index.md` before the first deletion so all three authority/view
  layers are discoverable and correctly labeled.

Do not put repository searching in `orchestrator/workflow/references.py`; that
module owns runtime structured-ref resolution. Do not leave the generic store
primitive owned only by the procedure-retirement module; that would make YAML
retirement depend on an unrelated evidence schema and error taxonomy.

## Closed Evidence Layout

The execution root is:

```text
docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/
  execution-ledger.json
  materialization-inputs/
    <sha256-of-output-repository-relative-path>/
      <eight-digit-generation>-<normalized-request-sha256-lowercase-hex>.json
  immutable-outputs/
    <sha256-of-output-repository-relative-path>/
      <eight-digit-generation>-<output-file-sha256-lowercase-hex><original-suffix>
  immutable-reviews/
    <subject-logical-path-sha256-lowercase-hex>/
      <subject-file-bytes-sha256-lowercase-hex>/
        <review-kind>-<review-file-bytes-sha256-lowercase-hex>.json
  workspace-baseline.json
  non-target-queue-sources.json
  query.json
  repository-scan.json
  reference-dispositions.json
  compatibility-fact-dispositions.json
  assignment-inputs/
    pre-transition-import-graph.json
  import-graph.json
  batch-category-input.json
  batch-assignment.json
  prospective-assignment-transition.json
  execution-index.json
  initial-root-bindings.json
  reviews/
    implementation-baseline-specification.json
    implementation-baseline-quality.json
    category-input-specification.json
    category-input-quality.json
    assignment-specification.json
    assignment-quality.json
    baseline-specification.json
    baseline-quality.json
    root-scope-pending-specification.json
    root-scope-pending-quality.json
    root-scope-confirmed-specification.json
    root-scope-confirmed-quality.json
    initial-root-bindings-pending-specification.json
    initial-root-bindings-pending-quality.json
    initial-root-bindings-confirmed-specification.json
    initial-root-bindings-confirmed-quality.json
    final-specification.json
    final-quality.json
  review-subjects/
    root-scope-pending.json
    root-scope-confirmed.json
    initial-root-bindings-pending.json
    initial-root-bindings-confirmed.json
  baseline/
    pytest-temp-root-preflight.json
    collect.log
    collect.exit
    collected-node-ids.txt
    pytest-rs.log
    pytest.exit
    pytest.junit.xml
    outcome.json
  implementation-baseline/
    pytest-temp-root-preflight.json
    collect.log
    collect.exit
    collected-node-ids.txt
    pytest-rs.log
    pytest.exit
    pytest.junit.xml
    outcome.json
    known-failure-baseline.json
  implementation-commits/task-03/ ... implementation-commits/task-06/
    focused/
      report.json
      logs/<role-id>.log
      exits/<role-id>.exit
    pytest-temp-root-preflight.json
    collect.log
    collect.exit
    collected-node-ids.txt
    pytest-rs.log
    pytest.exit
    pytest.junit.xml
    outcome.json
    subject.json
    failure-remediation.json       # present only for an approved in-scope reduction
    remediation-specification-review.json # present iff remediation is present
    remediation-quality-review.json       # present iff remediation is present
    skip-change.json                       # present iff skipped-node set changes
    skip-change-specification-review.json  # present iff skip-change is present
    skip-change-quality-review.json        # present iff skip-change is present
    specification-review.json
    quality-review.json
  implementation-commits/task-01-bootstrap/
    bootstrap-workspace-baseline.json
    focused/
      report.json
      logs/<role-id>.log
      exits/<role-id>.exit
    collect.log
    collect.exit
    collected-node-ids.txt
    pytest-rs.log
    pytest.exit
    pytest.junit.xml
    subject.json
    specification-review.json
    quality-review.json
  attestations/pre-implementation/
    broad-failure-baseline.json
  attestations/
    pre-delete/
      supported-run-root-scope.json
      roots/
        976a73eb92cb0ebc3a82da48834d75dff81fd95fe7052ba0a1152e83e86e2711.json
        02f3cfd79422a59183ec4e7d0c2ed92c3ea3523fa5f63eebab7bcf08c8f0fb9b.json
        b96e1f979beac55bd24ba2fcc74c9fa3df99a2d8021b3fca114b1f4aef1fae57.json
        177188cae936e3a6ee73fe2ae8096e2992deeb3372fcce3232505f4a174eff27.json
        f39dd7a79dd46a1524f9810a9ed0fd12ece70f2512042d68bfcc0cf99041a515.json
    batches/batch-01/ ... batches/batch-07/
      run-support-disposition.json
  roots/<canonical-root-digest>/initial-scan.json
  batches/batch-01/ ... batches/batch-07/
    owner-lifecycle/
      pending-subject.json
      pending-specification.json
      pending-quality.json
      pending-consumer.json
      confirmed-subject.json
      confirmed-specification.json
      confirmed-quality.json
      confirmed-consumer.json
    roots/<canonical-root-digest>/pre-delete-scan.json
    roots/<canonical-root-digest>/post-delete-scan.json
    attestations/roots/<canonical-root-digest>.json
    quiescence-continuity/<canonical-root-digest>.json
    batch-projection.json
    pre-delete-gate.json
    pre-deletion-index-baseline.json
    candidate-to-stage.json
    prospective-eligibility-transition.json
    prospective-transition.json
    references/
      pre-repository-scan.json
      pre-reference-dispositions.json
      pre-compatibility-fact-dispositions.json
      tracked-deletion-tombstones.json
      post-repository-scan.json
      post-reference-reconciliation.json
    focused/
      required-commands.json
      checks.json
      logs/<command-id>.log
      exits/<command-id>.exit
    smoke/
      isolated-smoke.json
      stdout.log               # present only when status=performed
      stderr.log               # present only when status=performed
      command.exit             # present only when status=performed
    broad/
      pytest-temp-root-preflight.json
      collect.log
      collect.exit
      collected-node-ids.txt
      pytest-rs.log
      pytest.exit
      pytest.junit.xml
      outcome.json
      failure-remediation.json              # optional strict-subset subject
      remediation-specification-review.json # present iff subject is present
      remediation-quality-review.json       # present iff subject is present
      skip-change.json                       # present iff skipped-node set changes
      skip-change-specification-review.json  # present iff skip-change is present
      skip-change-quality-review.json        # present iff skip-change is present
    deletion-subject.json
    deletion-pending.json
    repairs/repair-01/ ... repairs/repair-NN/
      prospective-transition.json
      repository-scan.json
      repository-reconciliation.json
      focused/required-commands.json
      focused/checks.json
      smoke/isolated-smoke.json
      broad/outcome.json
      subject.json
      reviews/repair-specification.json
      reviews/repair-quality.json
      repair-pending.json
    closure-validation.json
    deletion-closure.json
    reviews/
      eligibility-specification.json
      eligibility-quality.json
      post-edit-specification.json
      post-edit-quality.json
      closure-specification.json
      closure-quality.json
  final/
    prospective-closeout-transition.json
    repository-scan.json
    subject.json
    validators/
      report.json
      logs/<validator-id>.log
      exits/<validator-id>.exit
    focused/
      report.json
      logs/<command-id>.log
      exits/<command-id>.exit
    end-to-end/
      report.json
      logs/<command-id>.log
      exits/<command-id>.exit
    pytest-temp-root-preflight.json
    collect.log
    collect.exit
    collected-node-ids.txt
    pytest-rs.log
    pytest.exit
    pytest.junit.xml
    outcome.json
    failure-remediation.json              # optional strict-subset subject
    remediation-specification-review.json # present iff subject is present
    remediation-quality-review.json       # present iff subject is present
    skip-change.json                       # present iff skipped-node set changes
    skip-change-specification-review.json  # present iff skip-change is present
    skip-change-quality-review.json        # present iff skip-change is present
```

The five pre-delete root filenames are reserved deterministic slots. A file is
materialized only when its root-scope row is `supported`; an excluded row keeps
that slot absent and carries its reason/evidence in the scope record.

Within each conditional repair directory, `focused/`, `smoke/`, and `broad/`
expand to the exact same closed filenames and optional remediation/skip-change cardinality
shown for the parent batch; the compact tree above is not permission to omit
their raw logs/exits/JUnit/node list or add alternate names.

Every JSON object uses an exact key set. Unknown keys, duplicate JSON keys,
unsafe paths, wrong versions, mismatched digests/counts, missing referenced
files, symlink components, or timestamps that precede their bound scans fail
closed. Validators return typed issue rows sorted by `(path, code, message)`;
they never return a bare truthy dictionary.

The paths in this tree are normative, not examples. Every supported root has
both deterministic pre/post store-scan slots in every batch. Every batch has
one pre/post repository-scan pair, separate occurrence and compatibility-fact
pre-disposition records, one post-
reconciliation record, one focused-check manifest with content-addressed
command rows, one closed optional-smoke record, and one complete broad outcome
set. Baseline and final broad evidence use the same eight filenames. Validators
and reviewers may not read an ignored `tmp/` log, exit marker, report, or node
list; all evidence they consume must be beneath this execution root and bound
by exact bytes.

The Task-1 bootstrap subtree contains exactly one
`bootstrap-workspace-baseline.json`; its candidate manifest, bootstrap subject,
and precommit control must name that file exactly once. Each batch
`owner-lifecycle/` directory progresses exactly `0 -> 4 -> 8`: the pending
subject/review pair/consumer land together before the owner pause, and the
confirmed subject/review pair/consumer land together in the last nonexcluded
pre-capture commit. These eight files are distinct from and do not change the
fixed six-file `reviews/` eligibility/post-edit/closure lifecycle.

`non-target-queue-sources.json` is a mandatory immutable input to the execution
index, every pre-delete gate, deletion subject, candidate-to-stage manifest,
post-commit/HEAD validation, and final closeout subject. It is never regenerated
by a deletion batch. All ten rows must remain byte-identical; a mismatch is an
owner-boundary failure, not a referrer-remediation opportunity.

| Deterministic per-batch path | Closed contract |
| --- | --- |
| `roots/<digest>/pre-delete-scan.json` | `workflow-file-store-query.v1` / `root_scan.v1` |
| `roots/<digest>/post-delete-scan.json` | same schema and query as pre; snapshot equality required |
| `owner-lifecycle/{pending,confirmed}-subject.json` | `batch_owner_lifecycle_subject.v1`; immutable pre-capture owner-boundary review subject |
| `owner-lifecycle/{pending,confirmed}-{specification,quality}.json` | exactly four lifecycle `review.v1` files, distinct from the fixed batch `reviews/` directory |
| `owner-lifecycle/{pending,confirmed}-consumer.json` | `batch_owner_lifecycle_consumer.v1`; post-review consuming authority for the matching commit/index transition |
| `prospective-eligibility-transition.json` | `prospective_eligibility_transition.v1`; exact pre-gate external projection/routing bytes committed before repository capture |
| `references/pre-repository-scan.json` | `repository_reference_scan.v1` |
| `references/pre-reference-dispositions.json` | `reference_dispositions.v1` over that exact pre scan |
| `references/pre-compatibility-fact-dispositions.json` | `compatibility_fact_dispositions.v1` over that exact pre scan/import graph |
| `references/tracked-deletion-tombstones.json` | `tracked_deletion_tombstones.v1`, exactly the assigned tracked batch targets |
| `references/post-repository-scan.json` | `repository_reference_scan.v1` over retired plus replacement channels |
| `references/post-reference-reconciliation.json` | `reference_reconciliation.v1` covering both scans in both directions |
| `pre-deletion-index-baseline.json` | `pre_deletion_index_baseline.v1`; post-eligibility-commit real-index authority and exact permitted delta from the Step-5 disclosure |
| `candidate-to-stage.json` | `candidate_to_stage.v1`; immutable simulation from the unchanged post-Step-6 pre-deletion index baseline plus exact worktree transaction |
| `focused/required-commands.json` | `required_focused_commands.v1`; eligibility-reviewed exact base roles, candidate-specific owning selectors, and smoke decision |
| `focused/checks.json` and its `logs/`/`exits/` rows | `focused_checks.v1`; raw files bound by every closed command row |
| `smoke/isolated-smoke.json` and optional outputs | one of the two closed `isolated_smoke.v1` lifecycle fixtures |
| `broad/pytest-temp-root-preflight.json` | `pytest_temp_root_preflight.v1`; exact pytest 8.4.1 automatic-basetemp observation used by failure normalization |
| `broad/collect.log` | exact collect-only stdout/stderr bytes |
| `broad/collect.exit` | base-10 collection exit integer plus LF; must parse as zero |
| `broad/collected-node-ids.txt` | UTF-8, one exact sorted node ID plus LF per row, no duplicates |
| `broad/pytest-rs.log` | exact combined stdout/stderr bytes from the bound command |
| `broad/pytest.exit` | base-10 exit integer plus LF |
| `broad/pytest.junit.xml` | exact JUnit bytes from the same command |
| `broad/outcome.json` | `broad_outcome.v1`, binding the six raw files plus the preflight record |
| `broad/failure-remediation.json` and `broad/remediation-{specification,quality}-review.json` | all three absent for an exact baseline match; all three present for a reviewed strict queue-owned subset |
| `broad/skip-change.json` and `broad/skip-change-{specification,quality}-review.json` | all three absent for an unchanged skip set; all three present for any reviewed added/removed skipped-node transition |
| `reviews/{eligibility,post-edit,closure}-{specification,quality}.json` | exactly six lifecycle `review.v1` files; no additional filename is legal in this `reviews/` directory |

Baseline and final use the same six raw formats, preflight record, and `broad_outcome.v1` under
their own directories. `final/repository-scan.json` uses the same canonical
`repository_reference_scan.v1` schema as assignment and batch scans, over the
exact frozen query and scanner-owned exclusion;
`final/prospective-closeout-transition.json` uses
`prospective_closeout_transition.v1`. Any alternate filename, transient
surrogate, or omitted slot is a schema failure.

The preimplementation baseline and Tasks 3–6 production candidates use the
same eight-file broad contract under `implementation-baseline/` and
`implementation-commits/task-0N/`. Every `collect.exit` is a base-10 integer
plus LF and must parse as exactly zero; `pytest.exit` is preserved exactly and
is adjudicated against the closed known-failure baseline below. Each outcome binds the
exact candidate HEAD/index/worktree production projection with only the fixed
execution-evidence root removed, command, environment, collected
node IDs, log, exit, and JUnit bytes. There is one closed, versioned failure-
payload normalization contract and no ad hoc normalization: the baseline must
contain exactly six failed node IDs and their stable signatures,
and every later gate must contain that exact set/signature table except for a
strict subset removed by separately reviewed, in-scope remediation evidence.
Any added node ID, changed signature, unreviewed disappearance, changed external
failure, or total/exit inconsistency blocks the commit.

## Repository-Scan Freshness And Commit Ordering

Repository-reference eligibility is always observed after the last commit that
can change a nonexcluded byte. A scan binds the capture HEAD, full index digest
for disclosure, and a separately normalized index/worktree candidate projection
with the exact scanner-owned evidence root removed. Only the nonexcluded
projection gates freshness. Later writes or commits confined to that exact
evidence root may populate reviews/index bindings without invalidating the scan;
any changed, added, deleted, staged, or committed path outside it invalidates
the scan, all classifications derived from it, and the gate. Expanding the
exclusion is forbidden. Store scans are independent content snapshots and may
precede these repository-ordering steps, subject to their own adoption and
quiescence rules.

Assignment uses a cycle-free prospective transition: compute the deterministic
membership, materialize and commit every scanner-visible Stage-6 program,
triage, docs-index, live-projection, and routing-test byte, then recapture the
repository scan/import graph and classify its occurrence and compatibility-fact
sets. The reviewed assignment consumes those exact post-commit artifacts; the
new execution index is committed afterward only under the evidence root, and
`project --check` must reproduce the already committed projection.

Every deletion batch uses the same ordering twice. Before eligibility, complete
the reviewed pending owner-lifecycle subject/pair/consumer commit; pause for
owner adoption; then complete the reviewed confirmed owner-lifecycle
subject/pair/consumer commit containing final scan adoption, support disposition,
index state, and a prospective eligibility transition that materializes every
pre-edit external projection/routing byte. These are the only pre-eligibility
commits. Only after that last nonexcluded confirmed commit may the batch
capture and classify its repository scan, build/review the gate, and mark the
index eligible with evidence-root-only writes. After the deletion/referrer
transaction, the existing prospective deletion transition materializes all
post-edit external bytes before the final post scan and subject. Any owner,
index-generated projection, routing, or source commit after either repository
capture restarts from the corresponding prospective-transition commit and fresh
scan; no review or adoption waives staleness.

### Unstaged candidate and Git-index lifecycle

The Step-5 repository scan's `index_identity` is pre-eligibility disclosure, not
the deletion-window baseline: Step 6 intentionally commits the two eligibility
reviews and eligible index/ledger generations. Immediately after that commit
and before any deletion worktree mutation, capture
`pre-deletion-index-baseline.json` under `pre_deletion_index_baseline.v1`. Its
exact top level is `schema_version`, `batch_binding`, `step5_scan_binding`,
`eligibility_commit_binding`, `step5_index_identity`,
`pre_deletion_index_identity`, `permitted_evidence_root_delta`,
`nonexcluded_index_entries_binding`, `normalized_baseline_sha256`, and
`claims_not_made`.

The baseline recomputes the raw index-file SHA-256, `git write-tree` OID,
canonical `git ls-files --stage -z` SHA-256, and
`git diff --cached --binary` byte digest/count. It proves the Step-5-to-post-
Step-6 index-entry delta equals exactly the enumerated Step-5/Step-6 evidence-
root scan/disposition/gate/review/index/ledger request, snapshot, and live-output
paths admitted by the eligibility commit in both directions;
all nonexcluded index entries, modes, and blob OIDs must be byte-identical to
the Step-5 projection. An extra/missing evidence entry, any nonexcluded entry
change, or an eligibility commit with another path fails closed. Raw index bytes,
tree OID, complete entry-stream digest, and cached-diff digest may differ from
Step 5 only as consequences disclosed by that exact permitted entry delta; they
become frozen at the post-Step-6 capture.

Deletion-batch Steps 7–10 then operate only on the working tree. The actual Git
index must stay byte-for-byte equal to this post-Step-6 pre-deletion baseline:
no `git add`, `git rm --cached`, `git update-index`, alternate-index publication,
or tool that refreshes index bytes is permitted. At the Step-7 pre-mutation
boundary and after the deletion transaction, every focused command, broad
command, post scan, subject write, and each independent review recomputes all
four identity components. Any difference from
`pre_deletion_index_identity` invalidates the post-edit evidence and requires
restoration through an explicitly adjudicated recovery, never a relaxed gate.

The candidate presented to checks and reviews is an unstaged working-tree
candidate. A generic builder derives an immutable `candidate_to_stage.v1`
manifest without modifying the real index: start with the frozen pre-delete
index entries from `pre-deletion-index-baseline.json`, apply exactly the
gate/disposition-authorized worktree path/state/byte
changes in memory or in an isolated temporary index, and record the sorted
path/status/mode/blob-or-byte-digest rows, pre-index identity, expected current
candidate tree OID, exact deterministic future-addition path slots with null
digests, normalized row-set digest, and claims not made. If an isolated
temporary index is used, `GIT_INDEX_FILE` must point outside the repository's
actual index and its creation/removal is bound; the real index identity must be
checked before and after. The manifest is a simulation and never evidence that
the candidate is already staged.

Its exact top level is `schema_version`, `pre_deletion_index_baseline_binding`,
`pre_index_identity`,
`worktree_candidate_binding`, `rows`, `row_count`,
`expected_candidate_tree_oid`, `future_additions`,
`normalized_candidate_sha256`, and `claims_not_made`. A future-addition row is
an exact repository-relative path and lifecycle role with a null digest until
Step 11; no wildcard directory, optional extra path, or pre-review staging claim
is legal. The manifest's own request, immutable snapshot, and live-output paths
are excluded from its row set to avoid self-reference and are bound separately
by the consuming deletion subject.

Focused/broad outcomes, the deletion subject, and both post-edit reviews bind
the appropriate immutable candidate-to-stage generation and the repeated
unchanged-index observations. Step 8 creates the checked substantive generation;
after all pre-review scan/test evidence exists, Step 10 creates the next
contiguous generation adding those exact bytes while retaining null slots only
for the subject, two reviews, and closed Step-11 lifecycle/index additions. The
subject binds that Step-10 request/snapshot, and the reviews bind the subject.
Post scans continue to read the unchanged pre-delete blobs
from the real index while tombstones describe only worktree absence. Only Step
11, after both reviews approve, may mutate the actual index. It stages the exact
reviewed transaction plus enumerated evidence/lifecycle paths, then requires
the resulting index entry stream, cached diff, and `git write-tree` OID to equal
the deterministic application recorded by the candidate-to-stage manifest and
the closed post-review additions. A pre-review staged deletion, unrelated cached
diff drift, or mismatch between simulated and actual staging is a hard failure.

## Generic Production Broad Gate

Task 1 first lands the minimal generic broad-evidence foundation under its
explicit bootstrap gate. Task 2 then captures and obtains owner adoption of the
exact known-failure baseline. No queue production task may begin before that
adoption commit. Before each Task 3–6 production commit, rerun the same gate
against that exact candidate and persist it under the mapped directory/session:

| Candidate | Evidence directory | tmux session |
| --- | --- | --- |
| preimplementation | `implementation-baseline` | `yaml-retirement-impl-baseline` |
| Task 3 | `implementation-commits/task-03` | `yaml-retirement-impl-task-03` |
| Task 4 | `implementation-commits/task-04` | `yaml-retirement-impl-task-04` |
| Task 5 | `implementation-commits/task-05` | `yaml-retirement-impl-task-05` |
| Task 6 | `implementation-commits/task-06` | `yaml-retirement-impl-task-06` |

For each mapped directory, write combined `pytest --collect-only -q` output to
`collect.log`, its base-10-plus-LF exit to `collect.exit`, require parsed zero,
and derive the exact sorted `collected-node-ids.txt`. Immediately before the
broad launch, run the closed pytest-temp-root preflight with the same Python,
pytest 8.4.1 installation, cwd, and selected environment; persist
`pytest-temp-root-preflight.json` in the mapped directory and require it valid.
Then launch in the mapped
tmux session from the repository root:

```text
pytest -q -rs -n 16 --dist=worksteal --junitxml=<evidence-dir>/pytest.junit.xml
```

Write combined output directly to `<evidence-dir>/pytest-rs.log` and the exact
process status to `<evidence-dir>/pytest.exit`; preserve and parse that value
without requiring zero. Build
`<evidence-dir>/outcome.json` under `broad_outcome.v1`, binding the exact
candidate tree/index/worktree projection with only the fixed
`docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/` root removed,
plus an exact manifest of the task's evidence files, command/environment, all six raw
files and the preflight record,
totals, and exact failed/skipped node IDs. Task 2 must produce
`outcome=baseline_candidate` with exactly six failures; every later gate must
produce `known_failures_matched` or `approved_failure_subset` under the closed
owner-approved branch below. Each later outcome also binds the exact accepted
skip-set predecessor and either no skip-change files for byte-identical node IDs
or the complete reviewed `broad_skip_change.v1` triple. Skip drift never changes
the failure outcome enum.
Task-2 baseline reviews bind its baseline record. Task-3-through-6
implementation reviews instead bind the single closed implementation subject,
which binds this outcome, its exact baseline/remediation comparison, the
durable focused report, and candidate identity. The production commit includes
that subject and review pair. A changed production candidate after either run
invalidates the focused report, broad gate, subject, and reviews. Tasks 3–6 each make exactly one
production commit under this plan; a change outside that one evidence root
after the run invalidates the gate. Do not land an unchecked intermediate
production commit. If execution genuinely requires a split, first revise and
review this plan with one deterministic broad-evidence directory per additional
commit.

The Task-2 `known-failure-baseline.json` has schema
`broad_known_failure_baseline.v1` and exactly these top-level keys:
`schema_version`, `execution_ledger_binding`, `candidate_binding`, `collection_binding`,
`broad_outcome_binding`, `pytest_exit`, `totals`, `failures`,
`failure_normalization`, `normalized_failure_set_sha256`, `classification_summary`,
and `claims_not_made`. It is valid only when
collection exit is zero and the bound JUnit/log/outcome agree on exactly six
failed node IDs. Each sorted failure row contains exactly `node_id`,
`outcome_kind` (`failure|error`), `failure_payload_sha256`, `ownership_class`
(`queue_owned|external`), `ownership_basis`, and `authorized_remediation_scope`.

`failure_normalization` has the closed schema
`broad_failure_payload_normalization.v1` and exactly the keys
`schema_version`, `repository_root`, `pytest_temp_root_preflight_binding`,
`pytest_version`, `system_temp_root`, `pytest_root_component`,
`pytest_session_parent`, `pytest_temp_prefix_rule`, `ordered_transforms`, and
`normalized_contract_sha256`.

`pytest-temp-root-preflight.json` has schema `pytest_temp_root_preflight.v1`
and exactly `schema_version`, `pytest_executable_binding`, `pytest_version`,
`tmpdir_module_binding`, `environment_binding`, `raw_get_user`,
`root_component_resolution`, `root_component`, `system_temp_root`, `observed_session_parent`,
`observed_basetemp`, `normalized_record_sha256`, and `claims_not_made`. The
preflight uses the same executable/environment as the immediately following
broad run, requires pytest exactly `8.4.1`, binds the exact `_pytest/tmpdir.py`
module bytes, and invokes its automatic-basetemp path with no caller-supplied
`--basetemp`.

The closed probe entry point is:

```text
python -m orchestrator.retirement.broad_evidence probe-pytest-temp-root \
  --pytest-executable <absolute executable resolved for the bound broad argv> \
  --out <evidence-directory>/pytest-temp-root-preflight.json
```

It obtains the component/session parent from the bound pytest runtime; the CLI
has no username, component, parent, or fallback override.

The observed semantics are exactly pytest 8.4.1's
`TempPathFactory.getbasetemp()`: resolve `PYTEST_DEBUG_TEMPROOT` when present,
otherwise `tempfile.gettempdir()`; call the symbol actually resolved by this
code path, `_pytest.tmpdir.get_user()`, and obtain its raw
result; use that raw string unchanged when truthy; use literal `unknown` when
the result is missing/falsy; attempt `pytest-of-<raw-or-unknown>`; and, if that
mkdir raises `OSError`, retry literal `pytest-of-unknown`. Punctuation in a
usable raw username is preserved—it is never sanitized or replaced. A failed
fallback mkdir, ownership mismatch, unreadable result, explicit basetemp,
pytest/module version mismatch, or disagreement between the observed parent and
recorded component fails closed. `root_component_resolution` is exactly one of
`raw_get_user | missing_user_unknown | mkdir_fallback_unknown`.

The normalization object must bind the exact preflight bytes. Its
`system_temp_root`, `pytest_root_component`, and `pytest_session_parent` must
equal the preflight observations, and the parent must equal
`<system-temp-root>/pytest-of-<root-component>` lexically and canonically.
`observed_basetemp` must have that parent and a basename exactly
`pytest-<one-or-more-decimal-digits>`; the probe's numbered suffix is evidence,
not the suffix reused for the following broad run.
Missing, relative, symlink-ambiguous, or internally inconsistent observations
fail closed.
`pytest_temp_prefix_rule` is exactly
`exact_pytest_managed_run_prefix.v1`; `ordered_transforms` is exactly
`["crlf_to_lf.v1", "strip_ansi_csi.v1", "repository_prefix.v1",
"pytest_managed_run_prefix.v1"]`. Any other transform or order is invalid.
The baseline object's `failure_normalization` must equal its bound Task-2
`broad_outcome.v1.failure_normalization` byte-for-byte.

The stable payload is SHA-256 over the canonical tuple of JUnit testcase
identity, outcome kind, and the UTF-8 failure/error payload after these ordered
and only these transforms: normalize CRLF to LF; remove only ANSI CSI escape
sequences admitted by `strip_ansi_csi.v1`; replace the exact canonical repository-root prefix at a path-token
boundary with `<repo>/`; and replace an exact pytest-managed temporary-run
prefix at a path-token boundary with `<pytest-tmp>`. The last prefix is exactly
`<bound-pytest-session-parent>/pytest-<digits>` from the preflight.
Its complete suffix is preserved byte-for-byte, including test-directory
suffixes such as `test_name0`/`_r0`, filenames, assertion text, and exception
text. Either replaceable prefix begins only at payload start or immediately
after one ASCII whitespace byte or one of `"'([{=:`; its matched root/run
component ends only at payload end or immediately before `/`. The boundary rule must not rewrite a
relative or embedded lookalike, a
different unbound session parent/root component, `pytest-X`, `pytest-12x`, an arbitrary temporary path, an
arbitrary number, hash, address, duration, timestamp, or any non-prefix text.
This narrow rule makes pytest worker-run ordinals reproducible without making
semantic path or failure changes disappear.

The Task-2 builder records this exact normalization object and its digest. Every
baseline, implementation, batch, and final outcome recomputes failure payloads
with the same schema and bases, carries the object at `failure_normalization`
and its exact binding in
`baseline_comparison`, and rejects a missing, differently versioned, differently
based, differently ordered, or digest-mismatched contract before comparing any
row. `normalized_failure_set_sha256`, remediation rows, cumulative comparison,
and every reviewer-visible signature table are computed only from these
contract-normalized rows; raw JUnit and log bytes remain separately preserved
and bound. There is no alternate comparator, local string cleanup, arbitrary
normalization, or normalization-based waiver. Totals bind collected/passed/
failed/error/skipped counts, and `pytest_exit` binds both exact bytes and parsed
integer.

`queue_owned` means a failure is causally inside files or behavior this plan
already authorizes Tasks 3–6 to change; its basis enumerates those exact paths
and task. `external` means every fix is outside this queue's authority. The
classification neither assigns external maintenance nor authorizes a fix.
`attestations/pre-implementation/broad-failure-baseline.json` is a closed
pending/owner-confirmed record binding the complete baseline bytes, all six
rows/signatures, category counts, candidate projection, and both approved
baseline reviews. The owner confirms that this exact known-failure set may gate
this queue, that the ownership partition is accurate, and that no out-of-scope
repair is authorized. Personal owner adoption is required; a relayed statement,
prepared template, or reviewer approval is not adoption. Task 2 commits the
owner-confirmed attestation before Task 3 starts.

The attestation top level is exactly `schema_version`, `evidence_status`,
`baseline_binding`, `failure_set_binding`, `normalization_binding`,
`classification_summary`,
`specification_review_binding`, `quality_review_binding`, `owner`,
`owner_confirmations`, `prepared_by`, `prepared_at`, `owner_adoption`, and
`claims_not_made`. Pending state has null owner/adoption values and all fixed
confirmation booleans false; owner-confirmed state preserves every non-owner
byte, requires personal owner identity/role, one timestamp shared or correctly
ordered across confirmation/adoption, and all fixed booleans true. The fixed
statements bind the exact six-row/signature/exit/totals table, the complete
normalization schema/bases/contract digest used to construct that table, the complete
queue-owned/external partition, both approved reviews, permission to use this
baseline for comparison only, and denial of out-of-scope repair authority.
There is no field that authorizes source/store/workflow mutation.

`broad_failure_remediation.v1` has exactly `schema_version`,
`execution_ledger_binding`, `candidate_binding`, `task_scope_binding`, `baseline_binding`,
`removed_failure_rows`, `production_diff`, `focused_regression_evidence`,
`normalized_remediation_sha256`, and `claims_not_made`. Every removed row must
equal one `queue_owned` baseline row byte-for-byte; the candidate diff must be a
nonempty subset of the task's predeclared production/test paths and causally
account for that row. It has no owner field, no external-failure lane, and no
review fields. The separate immutable review pair binds this record; the later
broad outcome binds all three exact byte digests.

For every later implementation, batch, and final broad gate, the validator
compares the observed table to the owner-confirmed baseline. Exact same node
IDs, signatures, totals adjusted for ordinary passes and only reviewed skip-set
transitions, and exact
pytest-exit semantics produce `outcome=known_failures_matched`. A strict subset
is admissible only when every missing `queue_owned` row is named by a
`broad_failure_remediation.v1` record in that candidate's evidence directory.
That record binds the baseline row, exact production diff, focused regression
proof, and task/scope membership. The deterministic
`remediation-{specification,quality}-review.json` pair independently reviews
that immutable record; the later outcome binds the record and both approved
review digests without a self-reference. It may not name an `external` row or a path outside
the task's existing file/scope list. After an approved reduction, all later
gates use the owner baseline minus the cumulative reviewed remediation set;
they do not rewrite the owner baseline. An unexpected disappearance (including
an apparently flaky pass), new failure, changed signature/kind, reappearance of
a remediated failure, or changed exit/totals relation fails closed. There is no
exception artifact, baseline refresh, alternate normalization path, or
comparator-specific cleanup inside this plan.

Skipped-node IDs are a separately gated set, not prose-only disclosure.
`broad_skip_change.v1` contains exactly `schema_version`,
`execution_ledger_binding`, `candidate_binding`, `predecessor_skip_set_binding`, `added_skip_node_ids`,
`removed_skip_node_ids`, `authorized_diff`, `focused_regression_evidence`,
`resulting_skip_set_sha256`, `normalized_skip_change_sha256`, and
`claims_not_made`. Every implementation candidate compares to the Task-2
baseline plus the ordered approved skip-change prefix; every deletion batch
compares to the immediately preceding accepted batch set beginning with the
Task-7 pre-mutation baseline. An unchanged exact skip set requires the record
and its two reviews to be absent. Any added or removed skip ID requires the
record plus deterministic `skip-change-{specification,quality}-review.json`;
the authorized diff must be a nonempty subset of that task/batch's reviewed
candidate paths and the focused evidence must explain every changed ID. The
record cannot name a failed/error node, alter failure remediation, waive an
unmappable JUnit identity, or refresh the baseline. An unreviewed skip drift,
stale predecessor, reordering, or unexplained reappearance fails closed.
Later outcomes bind the complete ordered approved skip-change prefix without
rewriting either baseline. Before the execution index exists, Tasks 3–6 derive
that prefix only from earlier committed implementation-task directories in task
order; Task 7 imports the exact record/review bindings into
`implementation_failure_baseline.approved_skip_changes`.

Task 1 is the sole bootstrap exception because the closed builder does not yet
exist. Before that one commit, run its closed focused command set and the exact
broad xdist command directly, persist the focused report/logs/exits plus raw
broad log/exit/JUnit bytes under
`implementation-commits/task-01-bootstrap/`, and require collection exit zero,
exactly the currently observed six failed node IDs, and no collection/runtime
crash. Two independent reviews bind the bootstrap subject, which binds the
focused report and raw files, and verify that the commit
contains only generic broad-evidence foundation code/tests/fixtures. This raw
observation is not the owner baseline and authorizes no later production task;
Task 2 must recapture it through the landed builder and complete owner adoption.

The execution index schema is `workflow_retirement_execution_index.v1` and
contains exactly the following top-level shape. Canonical fixtures own the
complete nested shapes; the abbreviated rows below do not permit extra keys:

```json
{
  "schema_version": "workflow_retirement_execution_index.v1",
  "created_at_commit": "<40-hex commit>",
  "initial_index_base": {
    "captured_head": "<same 40-hex commit>",
    "initial_ledger_generation": {"live_path": "execution-ledger.json", "request_path": "<immutable path>", "request_sha256": "sha256:<digest>", "snapshot_path": "<immutable path>", "generation": "<positive integer>", "sha256": "sha256:<digest>", "schema_version": "workflow_retirement_execution_ledger.v1"},
    "assignment_binding": {"path": "batch-assignment.json", "sha256": "sha256:<digest>"},
    "normalized_base_sha256": "sha256:<digest>"
  },
  "execution_ledger": {"live_path": "execution-ledger.json", "request_path": "<immutable path>", "request_sha256": "sha256:<digest>", "snapshot_path": "immutable-outputs/<output-path-digest>/<generation>-<file-digest>.json", "generation": "<positive integer>", "sha256": "sha256:<digest>", "schema_version": "workflow_retirement_execution_ledger.v1"},
  "workspace_baseline": {
    "path": "workspace-baseline.json",
    "sha256": "sha256:<digest>",
    "schema_version": "workspace_baseline.v1",
    "dirty_entry_count": "<nonnegative integer>",
    "dirty_path_set_sha256": "sha256:<digest>",
    "dirty_entry_set_sha256": "sha256:<digest>",
    "index_entry_set_sha256": "sha256:<digest>"
  },
  "authority": {
    "path": "docs/plans/2026-07-13-procedure-first-reuse-inventory.json",
    "sha256": "sha256:<file bytes>",
    "handoff_schema_version": "procedure_first_yaml_retirement_handoff.v1",
    "queue_id": "<data, not production code>",
    "queue_path_count": 100,
    "queue_path_list_sha256": "sha256:2b4cdaf1...ac2b63"
  },
  "query": {"path": "query.json", "sha256": "sha256:<digest>"},
  "non_target_queue_sources": {
    "path": "non-target-queue-sources.json",
    "sha256": "sha256:<digest>",
    "schema_version": "non_target_queue_sources.v1",
    "source_count": 10,
    "path_list_sha256": "sha256:<digest>",
    "row_set_sha256": "sha256:<digest>"
  },
  "assignment": {
    "record": {"path": "batch-assignment.json", "sha256": "sha256:<digest>"},
    "specification_review": {"path": "reviews/assignment-specification.json", "sha256": "sha256:<digest>"},
    "quality_review": {"path": "reviews/assignment-quality.json", "sha256": "sha256:<digest>"}
  },
  "implementation_failure_baseline": {
    "outcome": {"path": "implementation-baseline/outcome.json", "sha256": "sha256:<digest>"},
    "record": {"path": "implementation-baseline/known-failure-baseline.json", "sha256": "sha256:<digest>"},
    "specification_review": {"path": "reviews/implementation-baseline-specification.json", "sha256": "sha256:<digest>"},
    "quality_review": {"path": "reviews/implementation-baseline-quality.json", "sha256": "sha256:<digest>"},
    "owner_attestation": {"path": "attestations/pre-implementation/broad-failure-baseline.json", "sha256": "sha256:<digest>"},
    "approved_remediations": [],
    "approved_skip_changes": []
  },
  "baseline": {
    "status": "absent|approved",
    "outcome": null,
    "specification_review": null,
    "quality_review": null
  },
  "root_scope": {
    "status": "absent|pending_owner_confirmation|owner_confirmed",
    "path": null,
    "sha256": null,
    "pending_reviews": null,
    "confirmed_reviews": null
  },
  "initial_root_bindings": {
    "status": "absent|pending_owner_confirmation|owner_confirmed",
    "path": null,
    "sha256": null,
    "pending_reviews": null,
    "confirmed_reviews": null
  },
  "batches": ["<seven closed batch records with exact paths and prerequisites>"],
  "active_paths": ["<sorted not-yet-deleted paths>"],
  "history": ["<append-only deletion records>"],
  "closeout": {
    "status": "open|approved",
    "subject": null,
    "specification_review": null,
    "quality_review": null
  },
  "normalized_index_sha256": "sha256:<digest excluding this field>"
}
```

`created_at_commit` is the existing repository `HEAD` captured immediately
before the first execution-index request is prepared/materialized. It is not
and cannot be the future commit that first contains `execution-index.json`.
`initial_index_base.captured_head` must equal it and binds the exact immutable
initial ledger generation and reviewed assignment bytes present as immutable
materialization inputs at that capture boundary; it does not claim those
evidence-root files were already contained by the captured commit.

The initial request, initial index output snapshot, and containing commit remain
distinct facts. Every later index generation preserves `created_at_commit` and
the complete `initial_index_base` byte-for-byte while advancing only fields
allowed by its lifecycle transition. Validation reopens the captured HEAD,
initial ledger request/snapshot, plan binding, and assignment binding; rejects a
missing/non-ancestor HEAD, a value equal merely to the containing commit, a
ledger/base mismatch, or any later rewrite; and never infers creation provenance
from the commit containing the current live singleton.

`batch_assignment.v1` contains exactly `schema_version`, `query_binding`,
`execution_ledger_binding`,
`repository_scan_binding`, `occurrence_dispositions_binding`,
`compatibility_fact_dispositions_binding`, `pre_transition_import_graph_binding`,
`import_graph_binding`,
`category_input_binding`, `category_review_bindings`, `batches`, `batch_count`,
`path_count`, `path_list_sha256`, `normalized_assignment_sha256`, and
`claims_not_made`. Every binding carries exact path, byte digest, schema
version, relevant row count, and normalized set digest. The category-review
object contains exactly the deterministic specification and quality paths/
digests plus `review_count=2`; both approve the bound category input under
distinct identities.
`batches` is the exact seven-batch partition and each row binds its path-list
count/digest, category IDs, import prerequisites, and deterministic order. The
validator recomputes all counts/digests and requires both disposition sets to
equal their respective scan/import-graph source sets in both directions. A
stale scan, missing/extra compatibility fact, category review over different
bytes, unequal pre/post semantic graph digests, unbound input, or input changed after the prospective assignment commit
rejects the assignment. `execution-index.json` consumes this complete
assignment path/digest plus its two approving assignment-review path/digests,
never a hand-copied subset of the assignment inputs.

`implementation_failure_baseline` is immutable after index creation except that
`approved_remediations` and `approved_skip_changes` may append exact reviewed
record/review path/digest rows in commit order. Its first five bindings must equal the personally adopted
Task-2 chain byte-for-byte. Every broad outcome in the index and every deletion
subject binds that chain plus the complete remediation and skip-change
prefixes; omission, reordering, replacement, or a record not admitted by the generic validator
fails closed.

`execution_ledger` is mandatory from initial index creation through closeout.
Every index update must bind the current valid ledger generation by live path,
immutable snapshot path, generation, and byte digest, and the ledger must bind
this immutable approved plan. The bound snapshot must equal the live singleton
when the index generation is created; later live advancement does not alter or
invalidate that historical snapshot. A stale ledger generation/digest, missing
or mutable snapshot, live/snapshot disagreement at capture, plan-byte mismatch,
more than one in-progress task, a skipped task/step transition, or a task marked
complete before its final reviewed task commit fails closed.

`non_target_queue_sources` is mandatory and immutable from index creation
through closeout. Validation reopens the bound record and all ten live paths,
recomputes its exact path/row sets, verifies the nine tracked source rows
against both Git mode/blob and exact worktree bytes, and verifies the holdout
through its exact `workspace-baseline.json` protected-row binding. A later
index, prospective transition, gate, subject, candidate-to-stage manifest, or HEAD whose
binding differs or whose live path bytes differ fails closed; no batch history
event or reviewed remediation may update this field.

`workspace_baseline` is likewise mandatory and immutable from initial index
creation through closeout. Every generation preserves its exact path, byte
digest, schema, dirty counts/set digests, and complete semantic-index set
digest, then binds a fresh all-dirty validation and the current reconstructed
precommit-control/trailer result. No generation may recapture or refresh this field; any drift
or omitted commit-isolation result fails closed.

`compatibility_fact_dispositions.v1` contains exactly `schema_version`, scan
and import-graph bindings, compatibility-fact source count/set digest, sorted
disposition rows keyed by `compatibility_fact_id`, classified count/set digest,
and `claims_not_made`. It requires exact equality with the scanner/import-graph
compatibility-fact set. Ordinary occurrence rows remain exclusively in
`reference_dispositions.v1`; neither lane may substitute for, duplicate, or
erase the other.

For `root_scope.status=absent`, `path`, `sha256`, `pending_reviews`, and
`confirmed_reviews` must all be null. `pending_owner_confirmation` requires the
record path/digest plus the exact approved pending-review pair and keeps
`confirmed_reviews` null. `owner_confirmed` preserves the pending pair, replaces
the record binding with the confirmed bytes, and requires the exact approved
confirmed-review pair. Both pairs bind immutable lifecycle subjects under
`review-subjects/`; the referenced record's evidence status must agree. No other
nullability combination is legal. Per-batch scan-adoption and disposition
bindings first pass through the distinct pending/confirmed batch owner-lifecycle
subjects, review pairs, and post-review consumers defined below. The later batch
eligibility review pair consumes the confirmed owner-lifecycle consumer and the
fresh repository gate; it does not retroactively authorize an earlier commit.

`initial_root_bindings` is separate from and later than `root_scope`.
`absent` requires null path/digest and null pending/confirmed review pairs.
`pending_owner_confirmation` requires
`initial-root-bindings.json` to contain exactly one supported-root row per
confirmed scope slot, with immutable initial-scan binding and pending
attestation binding, plus the approved pending-review pair over its immutable
lifecycle subject. `owner_confirmed` preserves that pair, requires the same scan
rows and exact owner-confirmed attestation replacements, and adds the approved
confirmed-review pair. Excluded scope slots never acquire an initial binding.
Missing/extra root, changed scan after adoption, lifecycle skip, partial row,
review pair over different bytes, or a binding whose scope digest is not the
immutable owner-confirmed scope fails closed. Updating initial bindings never
rewrites the scope record.

Every nested batch record has an `owner_lifecycle` object with exactly `status`
(`absent | pending_owner_confirmation | owner_confirmed`), `pending_consumer`,
and `confirmed_consumer`. `absent` requires both consumers null. Pending requires
the exact approved `owner-lifecycle/pending-consumer.json` generation and keeps
confirmed null. Confirmed preserves that immutable pending generation and adds
the exact approved confirmed consumer. A batch may become `eligible` only from
`owner_confirmed`; a pending/confirmed skip, consumer replacement, mixed batch,
or repository scan captured before the confirmed consumer's containing commit
fails closed.

`baseline.status=absent` requires all three baseline bindings null;
`approved` requires exact `baseline/outcome.json` and both approved deterministic
review bindings. `closeout.status=open` likewise requires all three closeout
bindings null; `approved` requires exact `final/subject.json` and both final
review bindings. The assignment binding is mandatory from index creation and
must validate the complete closed chain described below, including both
assignment reviews. No partial pair or unreviewed status transition is legal.

The validator requires `active_paths` plus the path-owning history events to be
a disjoint, exact partition of the frozen 100 paths. Repair and closure events
are non-owning and may not enter that partition. A
valid generation first preserves and validates the immutable
`created_at_commit`/`initial_index_base`; no status, owner, batch, repair, or
closeout transition may rebase those fields to its own containing commit or a
newer ledger. A
`deletion_committed_pending_binding` event binds paths, pre-delete blob IDs,
gate digest, the final deletion-subject digest, and the two post-edit review
digests. The final deletion subject is created only after all post-edit scans
and tests complete; each post-edit review binds that subject and the exact
scan/test evidence, never the not-yet-created pending event. Only after both
reviews approve may the pending event be created and included with the
substantive deletion in commit A. The event has no deletion-commit SHA or tree
field: commit A contains and thereby binds the event, while the event cannot
self-bind its containing commit. Zero or more
`deletion_repair_committed_pending_binding` events may follow under the closed
repair lifecycle; they bind reviewed repair subjects without owning paths. The
following evidence-only commit appends a `deletion_evidence_closed` event that
binds the prior deletion event, complete repair chain, now-known substantive
commit coordinates, post-commit checks, and closure reviews. No review artifact
may bind the commit that first contains itself. Reconciliation must pass at
every commit: the pending event owns the removed paths immediately, while
repairs and closure add evidence without owning those paths again. No status in
the frozen v1 handoff changes.

Tasks 1–5 precede the execution-index implementation and therefore run only
their exact available query, compatibility, scanner, loader, and protected-path
validators plus the bootstrap or owner-baseline-aware broad gate required for
their commit. Task 6 runs the new validator's fixture, CLI, module, and
owner-baseline-aware broad suite but still has no repository execution index to
validate. Task 7 first commits prospective scanner-visible assignment/routing bytes, then
captures/reviews the complete assignment, and finally materializes
`execution-index.json` in an evidence-root-only commit that must pass the new
validator immediately before commit and again at HEAD. From that commit onward,
run the execution-index validator immediately before and
after every plan commit, including baseline evidence, pending owner templates,
owner-confirmed replacements, deletion commit A, and closure commit B. No
post-index intermediate commit may leave a path unowned or multiply owned.

## Immutable Plan And Execution Ledger

After the reviewed planning commit, this Markdown file and its checkbox/status
bytes are immutable execution input. Live progress is owned solely by
`execution-ledger.json` under schema
`workflow_retirement_execution_ledger.v1`. Its exact top level is
`schema_version`, `plan_binding`, `task_count`, `tasks`, `current_task`,
`last_transition`, `normalized_ledger_sha256`, and `claims_not_made`.
`plan_binding` contains this path and the exact approved-plan byte digest.
`execution-ledger.json` is the current projection, not the only retained
generation: every generation has the immutable request/output snapshot required
by the Typed materialization surface.
`task_count` is 17. The sorted task rows contain exactly `task_number`,
`title`, `status` (`pending | in_progress | complete`),
`completed_step_count`, `total_step_count`, and sorted exact evidence bindings.
Those bindings may name only already-existing evidence inputs; they never name
a current/future subject, review, or containing commit that binds this ledger.
`current_task` is null only before Task 1 and after Task 17; otherwise it names
exactly one `in_progress` task. A task's final commit atomically marks it
`complete` and marks the next task `in_progress`; Task 17 instead returns
`current_task` to null. `last_transition` binds the complete prior ledger
generation (request path/digest, immutable output path/digest, and generation),
task/step coordinates, old/new status, preparation timestamp, exact
already-existing evidence inputs, and deterministic future subject/review paths
with null digests. It never binds a future subject that will itself bind the
ledger, and never claims or self-binds the commit that will first contain it.

Task 1 creates the canonical fixture, validator, and initial ledger generation
before its focused or broad run. Before every later focused report, scan, broad
run, or review that closes a step, materialize the final intended ledger
generation for that commit, validate its immutable request/snapshot, publish it
to the live path, and freeze that generation. Every broad outcome, review
subject, deletion/repair/closure subject, and final subject binds the exact
ledger generation object: live logical path, immutable snapshot path,
generation, byte digest, schema, and request binding. At subject creation the
live path must equal that snapshot. After review starts, the reviewed snapshot
is immutable; later live ledger advancement is expected and does not invalidate
the earlier subject/review, which reopens the bound snapshot. A subject that
names an older digest at the live path without the immutable generation binding
is invalid. The ledger lives under the fixed scanner-owned evidence exclusion,
so a ledger-generation update does not stale a nonexcluded repository scan. A
task's `complete` transition is only a candidate until both reviews approve and
that exact generation lands unchanged in its final reviewed task commit;
multi-commit tasks advance `completed_step_count` before each applicable gate
without prematurely changing task status.

The required `execution_ledger_binding` has one closed shape everywhere: logical
live path, immutable request path/digest, immutable output snapshot path/digest,
generation, byte digest, and schema version. In particular, the
`broad_known_failure_baseline.v1`, `broad_failure_remediation.v1`,
`broad_skip_change.v1`, `batch_category_input.v1`, and `batch_assignment.v1`
fixtures, builders, validators, and review consumers all require this binding
and reopen the same historical request/snapshot. Their review objects bind the
complete subject bytes containing it. A missing, mutable-path-only, stale, or
cross-task ledger binding rejects the subject and review pair.

No implementer edits this plan to track progress. A required contract change
stops this execution and requires a separately reviewed superseding plan plus a
fresh ledger/evidence root or explicit migration contract. This plan has no
in-place plan-digest rebind command. There is no unchecked checkbox/status-edit
exception.

## Canonical Contract Fixtures And Digest Rules

The plan uses checked canonical fixtures instead of leaving nested schemas to
implementation judgment. Task 1 creates the execution-ledger family, the
broad-evidence families, and the shared `review.v1` family under
`tests/fixtures/retirement_broad_evidence/`; Task 6 creates and validates every
other row below under `tests/fixtures/retirement_evidence/` and imports the
Task-1 broad validators rather than duplicating them:

| Record | Canonical fixture(s) |
| --- | --- |
| immutable-plan execution ledger | `execution_ledger.initial.v1.json`, `execution_ledger.in_progress.v1.json`, `execution_ledger.complete.v1.json` |
| immutable materialization generation request (Task-1 fixture owner) | `retirement_materialization_request.v1.json` |
| pytest automatic-temp-root preflight (Task-1 fixture owner) | `pytest_temp_root_preflight.v1.json` |
| broad failure-payload normalization (Task-1 fixture owner) | `broad_failure_payload_normalization.v1.json` |
| worktree/protected baseline (Task-1 fixture owner) | `workspace_baseline.v1.json` |
| pre-first-write Task-1 bootstrap baseline (Task-1 fixture owner) | `bootstrap_workspace_baseline.v1.json` |
| immutable non-target queue sources (Task-1 fixture owner) | `non_target_queue_sources.v1.json` |
| frozen query (Task-1 fixture owner) | `query.v1.json` |
| deterministic external precommit control (Task-1 fixture owner) | `precommit_control.v1.json` |
| occurrence-level repository scan | `repository_reference_scan.v1.json` (assignment, per-batch pre/post, repair, and final) |
| occurrence dispositions | `reference_dispositions.v1.json` |
| compatibility-fact dispositions | `compatibility_fact_dispositions.v1.json` |
| tracked-deletion tombstones | `tracked_deletion_tombstones.v1.json` |
| post-reference reconciliation | `reference_reconciliation.v1.json` |
| import graph | `import_graph.v1.json` |
| reviewed category input | `batch_category_input.v1.json` |
| exact batch assignment | `batch_assignment.v1.json` |
| execution index | `execution_index.absent.v1.json`, `execution_index.pending_binding.v1.json`, `execution_index.repaired_pending_binding.v1.json`, `execution_index.closed.v1.json` |
| post-eligibility pre-deletion index baseline | `pre_deletion_index_baseline.v1.json` |
| simulated candidate-to-stage manifest | `candidate_to_stage.v1.json` |
| prospective assignment transition | `prospective_assignment_transition.v1.json` |
| prospective eligibility transition | `prospective_eligibility_transition.v1.json` |
| prospective semantic transition | `prospective_transition.v1.json` |
| prospective repair transition | `prospective_repair_transition.v1.json` |
| repair reference reconciliation | `repair_reference_reconciliation.v1.json` |
| prospective closeout transition | `prospective_closeout_transition.v1.json` |
| root scope | `root_scope.pending.v1.json`, `root_scope.confirmed.v1.json` |
| initial-root binding lifecycle | `initial_root_bindings.absent.v1.json`, `initial_root_bindings.pending.v1.json`, `initial_root_bindings.confirmed.v1.json` |
| whole-query/per-batch root scan | `root_scan.v1.json` |
| root scan adoption | `root_attestation.pending.v1.json`, `root_attestation.confirmed.v1.json` |
| unchanged-snapshot adoption proof | `quiescence_continuity.v1.json` |
| containing-run support disposition | `run_disposition.pending.v1.json`, `run_disposition.confirmed.v1.json` |
| batch projection | `batch_projection.v1.json` |
| batch gate | `pre_delete_gate.v1.json` |
| reviewed batch/repair focused command contract | `required_focused_commands.v1.json` |
| focused checks | `focused_checks.v1.json` |
| optional isolated smoke | `isolated_smoke.not_required.v1.json`, `isolated_smoke.performed.v1.json` |
| broad baseline/batch/final outcome | `broad_outcome.v1.json` |
| durable implementation focused verification | `implementation_focused_report.v1.json` |
| implementation candidate review subject | `implementation_verification_subject.v1.json` |
| broad-evidence bootstrap subject | `broad_evidence_bootstrap_subject.v1.json` |
| known broad-failure baseline | `broad_known_failure_baseline.v1.json` |
| owner adoption of known failures | `broad_failure_baseline_attestation.pending.v1.json`, `broad_failure_baseline_attestation.confirmed.v1.json` |
| reviewed in-scope failure reduction | `broad_failure_remediation.v1.json` |
| reviewed skipped-node transition | `broad_skip_change.v1.json` |
| final validator report | `final_validator_report.v1.json` |
| final focused report | `final_focused_report.v1.json` |
| final end-to-end report | `final_end_to_end_report.v1.json` |
| final review subject | `final_review_subject.v1.json` |
| owner lifecycle review subject | `owner_lifecycle_review_subject.{root_scope_pending,root_scope_confirmed,initial_root_bindings_pending,initial_root_bindings_confirmed}.v1.json` |
| per-batch owner lifecycle subject | `batch_owner_lifecycle_subject.{pending,confirmed}.v1.json` |
| per-batch owner lifecycle consuming record | `batch_owner_lifecycle_consumer.{pending,confirmed}.v1.json` |
| deletion/review subject | `deletion_subject.v1.json` |
| deletion lifecycle | `deletion_pending.v1.json`, `repair_subject.v1.json`, `deletion_repair_pending.v1.json`, `closure_validation.v1.json`, `deletion_closure.v1.json` |
| independent review and immutable consumer binding | `review.v1.json`, `review_binding.v1.json` |

Each fixture directory has exactly one `manifest.v1.json` with top-level keys
`schema_version`, `fixture_root`, `rows`, `fixture_count`,
`normalized_path_set_sha256`, `normalized_row_set_sha256`, and
`claims_not_made`. Each sorted row has exactly `path`, `schema_version`,
`lifecycle_role`, `expected_validation` (`accepted | rejected`), and the exact
file-byte SHA-256. The manifest names every fixture file except itself in both
directions; glob expansion is never an admissibility rule. Task candidate
manifests may include only the fixture manifest plus its exact named rows.

### Typed materialization surface

No executor hand-authors a machine-produced record or grows the CLI during
execution. Task 6 lands one-shot queue-neutral materialization transactions:

```text
python scripts/build_retirement_execution_index.py materialize \
  --kind <closed-record-kind> \
  --out <repository-relative-output> \
  --generation <positive-integer> \
  --input <closed-role>=<repository-relative-path> ... \
  --parameter <closed-name>=<typed-value> ... \
  [--prior-request <immutable-request-path> \
   --prior-snapshot <immutable-output-path>]

python scripts/build_retirement_execution_index.py materialize-pending \
  --kind <closed-pending-record-kind> \
  --out <repository-relative-output> \
  --generation <positive-integer> \
  --input <closed-role>=<repository-relative-path> ... \
  --parameter <closed-name>=<typed-value> ... \
  [--prior-request <immutable-request-path> \
   --prior-snapshot <immutable-output-path>]
```

The shared `materialize_transaction` operation—used directly by Task 1's
bootstrap and exposed by both commands—is the only production route that
creates a request or output. It accepts only the selected kind's closed role/name/type grammar from the fixture
manifest; repeated `--input` rows cause the CLI to open the named files and
derive their size/digest/schema bindings, while `--parameter` values are parsed
by kind-specific scalar/path/enum/list rules rather than an open JSON map. The
caller cannot provide a request path, input digest, expected-input-set digest,
normalized request digest, or owner/adoption field.

After validating only the output path and generation needed to choose the lock, the one-shot
operation acquires the persistent per-output-generation kernel advisory lock
before opening inputs or inspecting generation slots and holds that same lock
through request creation, snapshot creation, live publication, reread, and
receipt emission. Under the lock it canonicalizes the complete request with
`normalized_request_sha256` excluded from its own digest projection, computes
and inserts that digest, derives the generation-addressed path, exclusively
creates the immutable file, rereads/validates it, and prints exactly one
canonical JSON receipt with exactly `request_path`, `request_sha256`,
`snapshot_path`, `snapshot_sha256`, `generation`, `output_path`, and
`output_sha256`, only after the live reread succeeds. Thus there is no self-digest cycle, hand-authored request, or
unlock window between request preparation and publication. Two concurrent
byte-identical transactions either return one success plus a typed busy result,
or a later retry returns the same fully validated receipt; concurrent different
transactions for the same output/generation allow exactly one to succeed. A loser fails without
creating an alternate request. The lock is a persistent inode outside the
evidence namespace held with a nonblocking kernel advisory lock for the entire
request/snapshot/live-publication transaction. It is never deleted or stolen:
live contention returns a typed busy error, and process death releases the
kernel lock automatically. A retry acquires that same inode and validates the
request, snapshot, and live slots before continuing; no timestamp, PID text, or
"stale" age changes lock ownership. Ordinary contention returns the typed busy
result until kernel release.

Every transaction request is immutable and retained beneath
`materialization-inputs/<sha256-of-output-repository-relative-path>/` as
`<eight-digit-generation>-<normalized-request-sha256-lowercase-hex>.json`. A generation
is base-10 in the closed range `1..99999999` and is encoded as exactly eight
digits with leading zeroes (`00000001` through `99999999`); every request and
snapshot filename uses that width. The output-path directory key is the
lowercase 64-hex SHA-256 of the exact UTF-8 bytes of the already-validated
canonical repository-relative POSIX output path, with no Unicode
renormalization, separator rewrite, prefix, NUL, or trailing newline. It uses schema
`retirement_materialization_request.v1` with exactly `schema_version`,
`record_kind`, `output_path`, `generation`, `prior_generation_binding`,
`input_bindings`, `parameters`, `expected_input_set_sha256`,
`normalized_request_sha256`, and `claims_not_made`. `input_bindings` is a sorted
list of exact path/size/byte-digest/schema/version bindings; `parameters` is a
per-kind closed object from the fixture manifest, not an open map. The request's
output path must equal the CLI `--out` path. Its deterministic request path must
use the output-path directory key above and the exact eight-digit generation
plus lowercase normalized-request SHA-256 filename; no concatenated or
JSON-encoded alternative hash input is legal. No later transition may overwrite, rename, or reuse that request
path. No separate production command can create or consume a request, and a
request without its same-transaction snapshot/live completion is only a crash
recovery slot, never a successful prepared state.

Every successful materialization first constructs and validates the complete
output bytes in memory, then creates their immutable byte-for-byte snapshot at
`immutable-outputs/<sha256-of-output-repository-relative-path>/`
`<eight-digit-generation>-<output-file-sha256-lowercase-hex><original-suffix>` using exclusive
creation, validates that snapshot, and only then atomically publishes the same
bytes to the live `--out` singleton. A retry may reuse an existing request or
snapshot only when its bytes are identical; conflicting bytes fail closed. The
live output, request, and snapshot must agree on output path, kind, generation,
inputs, and digest before success. A crash after snapshot creation but before
live publication is recoverable by exact replay; a live generation without its
exact immutable request and snapshot is invalid.

Crash recovery is a lock-held compare-and-swap, not a second producer phase.
After reacquiring the same lock, the operation rebuilds the expected request
and output in memory, enumerates the complete generation slot, and permits only
the exact prefix states `empty`, `identical_request_only`,
`identical_request_and_snapshot`, or `identical_complete_publication`. It
continues the missing suffix or returns the identical complete receipt. Any
different/extra request for the generation, mismatched snapshot, live output
without both immutable predecessors, or non-prefix state fails without writing.

Generation 1 requires `prior_generation_binding=null`. Every later generation
requires an exact `prior_generation_binding` with prior request path/digest,
prior immutable-output path/digest, prior generation, and prior live output
path. The materializer validates the transition from the immutable prior
snapshot, not from whatever bytes happen to occupy the live singleton, while
also requiring the live singleton to equal that prior snapshot immediately
before publication. Generations are contiguous per logical output path. Unknown
kind/input/parameter, missing or extra input, output outside its kind's
deterministic slot, generation gap/reuse, stale live bytes, mutable/missing
prior request or snapshot, overwrite without a valid lifecycle transition, or
a request/output/snapshot cycle fails before publication. There is no generic
force-overwrite flag.

All references to a mutable materialized output in a ledger, index, transition,
subject, review, deletion/final evidence record, or candidate manifest use the
closed generation binding: logical live path, immutable snapshot path,
generation, byte digest, schema/version, and request path/digest. At review time
the live singleton must equal the bound snapshot. Historical validation after a
later generation advances validates the immutable request and snapshot and does
not reinterpret the binding as a claim about the current live singleton. A
reviewed subject therefore remains independently verifiable even while the
current ledger, execution index, batch projection, or generated Markdown live
projection advances. A bare mutable path/digest binding is invalid for these
outputs.

The closed `record_kind` partition is:

| Producer mode | Exact materializer kinds |
| --- | --- |
| `materialize` | `execution-ledger`, `query`, `reference-dispositions`, `compatibility-fact-dispositions`, `tracked-deletion-tombstones`, `reference-reconciliation`, `batch-category-input`, `batch-assignment`, `execution-index`, `initial-root-bindings`, `batch-projection`, `candidate-to-stage`, `quiescence-continuity`, `pre-delete-gate`, `required-focused-commands`, `focused-checks`, `isolated-smoke`, `owner-lifecycle-review-subject`, `batch-owner-lifecycle-subject`, `batch-owner-lifecycle-consumer`, `prospective-assignment-transition`, `prospective-eligibility-transition`, `prospective-deletion-transition`, `deletion-subject`, `prospective-repair-transition`, `repair-reference-reconciliation`, `repair-subject`, `deletion-pending`, `deletion-repair-pending`, `closure-validation`, `deletion-closure`, `prospective-closeout-transition`, `final-validator-report`, `final-focused-report`, `final-end-to-end-report`, `final-review-subject`, `implementation-focused-report`, `implementation-verification-subject`, `broad-evidence-bootstrap-subject`, `broad-known-failure-baseline`, `broad-outcome`, `broad-failure-remediation`, and `broad-skip-change` |
| `capture` through an exact existing CLI/module command | `workspace-baseline`, `non-target-queue-sources`, `pytest-temp-root-preflight`, `repository-reference-scan`, `authored-import-graph`, `root-scan`, `pre-deletion-index-baseline`, and raw command/log/exit/JUnit/node-list files |
| `materialize-pending` only | `supported-root-scope`, `root-scan-attestation`, `run-support-disposition`, and `broad-failure-baseline-attestation`; this mode hard-codes null owner/adoption fields and false confirmations |
| `validate-only after external adoption` | owner-confirmed replacements and independent `review.v1` records; production may validate and canonicalize supplied complete bytes but may not select identity, verdict, provenance, or confirmation values |

The shared pending transaction is used by Task 2 through the Task-1
library adapter for `broad-failure-baseline-attestation` and exposed by Task 6
as the explicit `materialize-pending` subcommand for all four kinds. It is not a
prose mode or alias for `materialize`. It accepts only a kind from the four
rows in its table partition. Its one-shot argument grammar admits
only machine/plan bindings and non-owner parameters; it rejects any owner name,
role, confirmation, adoption, provenance, confirmation timestamp, affirmative
boolean, or prepopulated owner-field input. The subcommand constructs the
pending schema with every owner/adoption value null and every confirmation
boolean false, uses the same immutable output-snapshot/live-publication
transaction under one lock, and fails if the ordinary `materialize` route is used for one of
these four kinds. Conversely, `materialize-pending` rejects every other kind.
Confirmed replacements remain validate-only external-adoption inputs and never
pass through either materializer.

The `project`, `project-transition`, and closeout projection modes use the same
request/generation/snapshot protocol even when the logical live output is
Markdown rather than JSON. Their requests are typed to the owning transition or
index generation, their immutable snapshots retain the original suffix and
exact bytes, and every transition/subject binds those snapshots. Authored source
files are not copied into this mechanism merely because they are edited; it
applies to generated singleton outputs whose older reviewed generations would
otherwise be overwritten.

Every Task-7-through-17 instruction to “create,” “build,” “generate,” “write,”
or “prepare” one of these JSON records means this exact typed operation or its
listed `materialize-pending`, capture, or validate-only route. Its request and
output are both included in
the next ledger/subject candidate manifest as the exact generation-addressed
request and immutable output snapshot; the live singleton is additionally
required equal at capture time. Task 6's temporary-repository CLI
smoke enumerates the fixture manifest's complete materializer-kind set in both
directions: every positive kind materializes and validates, while each kind's
missing-input, extra-input, wrong-output-slot, and one schema-specific tamper
case fails without an output. Every mutable lifecycle kind additionally proves
two contiguous prior-generation transitions while retaining and revalidating every
earlier request and immutable output snapshot. Reject a missing/stale prior
binding, output-path-only request collision, generation reuse/gap, request or
snapshot overwrite/tamper, live/snapshot disagreement, later generation used as
an earlier binding, unsupported overwrite, and historical subject that cannot
validate after the live singleton advances. Exercise JSON ledgers and indexes
plus the generated Markdown live projection. This is the lifecycle smoke; a
single execution-index happy path is insufficient.

Each validator requires `set(actual) == set(canonical_fixture)` recursively,
with only explicitly declared map-key collections allowed to vary. Nested enum
sets are closed:

- evidence: `pending_owner_confirmation | owner_confirmed`;
- index binding: `absent | pending_owner_confirmation | owner_confirmed`;
- initial-root binding: `absent | pending_owner_confirmation |
  owner_confirmed`;
- root scope: `supported | excluded_with_owner_reason`;
- run support: `supported | unsupported_abandoned`;
- resume/consumer support: `supported | retired`;
- immutable handoff-v1 reference classification: `delete_with_source |
  reroute_to_orc | temporary_yaml_frontend_test |
  historical_reference_retained`;
- execution refinement when and only when the per-scan selected classification is
  `delete_with_source`: `delete_referrer_with_source |
  remove_exact_occurrence`;
- isolated smoke: `not_required | performed`;
- path encoding: `absolute | workspace_relative`;
- frame kind: `embedded | file` (or a JSON null frame for a top-level match);
- scan adoption: `fresh_owner_re_adoption |
  identical_snapshot_unbroken_quiescence`;
- batch: `pending | blocked | eligible | committed_pending_binding | closed`;
- history event: `deletion_committed_pending_binding |
  deletion_repair_committed_pending_binding | deletion_evidence_closed`; and
- review: `approved | rejected`.

`workspace_baseline.v1` contains exactly `schema_version`, `captured_at`,
`head`, `index_sha256`, `index_entries`, `index_entry_count`,
`index_entry_set_sha256`, `status_rows`, `dirty_entries`, `dirty_entry_count`,
`dirty_path_set_sha256`, `dirty_entry_set_sha256`, `protected_paths`,
`normalized_baseline_sha256`, and `claims_not_made`. Status rows preserve the
complete NUL-decoded porcelain status/path tuple. The sorted `dirty_entries`
set equals every path operand from those rows in both directions, including
both source and destination of a rename/copy; one path may cite multiple status
row IDs but appears once.

`bootstrap_workspace_baseline.v1` reuses those exact workspace fields and adds
exactly `bootstrap_capture_bindings` and `raw_archive_not_persisted=true` before
the normalized digest/claims fields. The capture object binds external archive,
status, index-entry, index-file, and HEAD file byte digests plus the producer
contract version, but no external path is durable authority. Its dirty entries
must equal the pre-first-write status operands and the corresponding archive
members in both directions. Validation rejects an archive member/type/byte
mismatch, a dirty operand absent from the archive without deletion semantics,
an unreported dirty archive difference, or any committed raw archive/user byte.

Each dirty-entry row contains exactly `path`, `status_row_ids`, `existence`,
`file_type`, `lstat_mode`, `index_entries`, `content_binding`, and
`normalized_entry_sha256`. `index_entries` is the exact sorted stage/mode/blob
projection from `git ls-files --stage -z` for that path and may be empty only
when status semantics allow it. `content_binding` is a closed discriminated
union: an absent path has all content fields null; a regular file binds exact
size and SHA-256 of bytes read without following symlinks; a symlink binds the
length and SHA-256 of the raw `readlink` target bytes; an untracked directory,
if porcelain emits one despite `--untracked-files=all`, binds a complete sorted
no-follow descendant manifest with every relative path, type, mode, size, and
regular/symlink byte digest plus its count/set digest; a tracked gitlink binds
its index OID, worktree directory type, and nested HEAD/status snapshot. FIFO,
socket, device, unreadable, racing, duplicate-normalized, or escaping paths fail
capture rather than receive a weak binding. Protected rows remain a separately
named subset/extension and bind exact existence/type/content without claiming
any pre-existing dirty content belongs to this plan.

`index_entries` is the complete sorted NUL-safe `git ls-files --stage` table,
including every path, stage, mode, and blob OID, not merely entries for dirty or
protected paths. `index_sha256` discloses the raw index-file bytes at capture;
the semantic table and its count/set digest are the portable commit-isolation
authority. Commit controls are deliberately not repository evidence and never
enter their own staged set. Immediately before staging, the Task-1-landed
builder derives one canonical `precommit_control.v1` and NUL pathspec beneath
`.git/retirement-commit-controls/<transaction-id>/control.json` and
`paths.nul` plus `message.txt` and `final-message.txt`. All four are external
ephemeral projections of durable reviewed authority; none may be staged.

The control contains exactly `schema_version`, `transaction_id`,
`bootstrap_workspace_baseline_binding`, `workspace_baseline_binding`,
`durable_authority_bindings`, `durable_authority_set_sha256`,
`prior_control_trailers`, `base_head`, `pre_commit_index_binding`,
`allowed_delta_rows`, `allowed_delta_count`, `allowed_path_set_sha256`,
`expected_index_binding`, `expected_commit_tree_oid`, `pathspec_file_binding`,
`base_message_binding`, `final_message_binding`, `normalized_control_sha256`,
and `claims_not_made`.
Task 1 alone requires a non-null bootstrap-workspace binding and null workspace baseline; every later
commit requires the inverse. `durable_authority_bindings` contains the exact
reviewed subject, immutable review pair, and closed post-review consuming
records from which every allowed row is derived. The control has no future,
null, self, control-path, or containing-commit slot.

`pre_commit_index_binding` is reconstructed from the Task-1 bootstrap baseline or the
Task-2 workspace semantic index plus the ordered prior control trailers and
committed deltas. `expected_index_binding` adds only the current allowed staged
rows while retaining unrelated pre-existing staged rows.
`expected_commit_tree_oid` instead applies only those allowed rows to
`base_head`, so it excludes every unrelated staged row. The pathspec binding
contains exact external path, byte SHA-256, byte count, row count, and
`encoding=nul_terminated_literal_paths`; its bytes are the sorted allowed paths,
each encoded as exact UTF-8 followed by NUL, with no wildcard or pathspec magic.
`base_message_binding` contains the exact external `message.txt` path, byte
count, and SHA-256. Its UTF-8 bytes must be nonempty,
end in exactly one LF, contain no `Retirement-Control-*` trailer key, and are
produced noninteractively from the task's closed commit-subject parameter. The
builder never reads an editor, terminal, or environment-supplied message.
`final_message_binding` contains the exact external `final-message.txt` path,
byte count, SHA-256, and `cleanup=verbatim`; its bytes must equal the exact
forward derivation below.

`durable_authority_set_sha256` is lowercase 64-hex SHA-256 of canonical compact
JSON for the sorted durable-authority bindings. `transaction_id` is lowercase
64-hex SHA-256 of the exact byte concatenation
`b"precommit-control.v1\0" + base_head_ascii40 + b"\0" +
durable_authority_set_sha256_ascii64`. The control digest uses canonical compact
JSON excluding exactly `normalized_control_sha256` and
`final_message_binding`; `normalized_control_sha256` is
`sha256:<lowercase-64-hex>`, while the trailer carries exactly its 64-hex digest
portion without the prefix. This deliberate two-field projection breaks the
otherwise unavoidable cycle: compute the control digest first, compose final
message bytes from it, then populate `final_message_binding`; validation
recomputes both directions and includes every field outside that exact
two-field projection. The commit message contains exactly one terminal trailer
block:

```text
Retirement-Control-Schema: precommit_control.v1
Retirement-Transaction-ID: <lowercase-64-hex>
Retirement-Control-SHA256: <lowercase-64-hex>
```

The final raw commit-message byte stream is defined, not inferred from display
text or produced by Git trailer processing. Let `base` be the exact
`message.txt` bytes, already ending in exactly one LF, and let
`transaction_id`/`control_sha256` be their validated lowercase 64-hex values.
The control builder exclusively creates `final-message.txt` with exactly:

```text
base
+ b"\n"
+ b"Retirement-Control-Schema: precommit_control.v1\n"
+ b"Retirement-Transaction-ID: " + transaction_id_ascii64 + b"\n"
+ b"Retirement-Control-SHA256: " + control_sha256_ascii64 + b"\n"
```

Here the first `b"\n"` is the one additional blank separator LF inserted
by the builder between the base message's existing terminal LF and the first
trailer line; it is not part of `message.txt`. There is exactly one such
separator and no blank line between trailer rows or after the final trailer's
single LF. Git receives these already-final bytes and performs no trailer
interpretation, insertion, replacement, or normalization.

The trailers durably bind the otherwise external control without putting it or
the pathspec in the tree. Post-commit validation, including from a fresh clone
with no `.git/retirement-commit-controls/` directory, reconstructs the control
and pathspec from the parent/commit diff, committed subject and immutable
reviews, workspace baseline or Task-1 bootstrap-workspace binding, prior trailer chain, and
current trailer values. Reconstruction reads the raw commit object, splits
headers from the message at the first `b"\n\n"`, and first requires the raw
message body to equal reconstructed `final-message.txt` byte-for-byte and match
`final_message_binding`. It then constructs the exact separator-plus-three-line
suffix above, requires that suffix exactly once, and removes it including the
one separator LF; the remaining bytes must equal `message.txt` byte-for-byte,
match `base_message_binding`, and end in exactly one LF. It requires byte-identical reconstruction, exact control
digest/transaction ID/tree, and exact allowed delta. Thus clone/recreation does
not trust a surviving local control file and there is no manifest/pathspec
self-reference or infinite attestation chain.

Every pre-existing dirty entry is immutable execution input. A later plan step
may add plan-owned paths, but it may not edit, stage, restore, delete, replace,
retarget, chmod, or otherwise change a baseline dirty path. If an assigned
target or required referrer intersects `dirty_entries`, the batch fails closed
before mutation and returns to the owner; status text or an in-scope disposition
does not waive the user's bytes.

`non_target_queue_sources.v1` contains exactly `schema_version`, the frozen
handoff path/digest/schema binding, the `workspace-baseline.json` path/digest,
the exact sorted ten `source_rows`, `source_count=10`, the normalized path-list
and row-set digests, `normalized_record_sha256`, and `claims_not_made`.
`source_rows` is the disjoint exact union of the seven Design Delta archive
sources, two port sources, and one protected holdout selected from the frozen
handoff. Each row binds queue ID, repository-relative path, and disposition
owner. The nine archive/port rows additionally bind regular-file kind, tracked
mode/blob OID, size, and SHA-256 of exact worktree bytes. The holdout row uses
`binding_source=workspace_protected_binding` and binds the exact protected-row
path/digest from `workspace-baseline.json`; it may not duplicate or weaken that
protected-path authority. The other nine rows use
`binding_source=tracked_source_binding`. Missing, extra, duplicated,
cross-queue, untracked, non-regular, symlinked, mode/blob-mismatched, or
byte-mismatched rows fail closed. The record is immutable after Task 2 and is
never regenerated to bless later drift.

`query.v1` is also a Task-1-owned bootstrap contract because Task 2 must create
it before Task 6 exists. It contains exactly `schema_version`, `authority`,
`queue_id`, `paths`, `path_count`, `path_encoding`, `path_list_sha256`,
`capture_commit`, `normalized_query_sha256`, and `claims_not_made`.
`authority` binds the handoff path, exact file bytes, and handoff schema; the
sorted path set must equal the named queue in that bound JSON authority in both
directions. `path_encoding` is the fixed UTF-8 repository-relative POSIX path
plus LF per row used by the list digest. Task 1 registers the closed `query`
request/materializer adapter and a composite `materialize-query` command in
`source_bindings`; the command delegates to the same one-shot lock-held
`materialize_transaction` primitive and emits its canonical
materialization receipt with exactly `request_path`, `request_sha256`,
`snapshot_path`, `snapshot_sha256`, `generation`, `output_path`, and
`output_sha256`. Task 6 imports this fixture and adapter unchanged. It may expose the
same operation through the full script CLI, but it may not redefine, migrate,
or re-materialize the Task-2 query.

`validate-workspace-baseline` re-runs porcelain and no-follow filesystem/index
capture, then requires every baseline dirty-entry row to match existence,
file type, mode, index stages, and content bytes exactly. The complete live
status may additionally contain only paths admitted by the current reviewed
plan candidate/transition manifest; those additions never rewrite or rebaseline
the pre-existing rows. A bootstrap `--allowed-addition` is legal only for an
exact output path enumerated by the current immutable task contract; later
calls use the content-addressed candidate/transition manifest. Neither form may
name a baseline dirty path. Run this validator immediately before and after every
source/evidence mutation, focused/broad/smoke command set, scan capture, review
subject freeze, review, staging operation, commit, and immediate-HEAD
validation from Task 2 through Task 17. Every gate, subject, review, execution-
index generation, deletion/repair/closure/final candidate, and HEAD report binds
the immutable workspace-baseline path/digest plus a fresh validation result.
Any baseline-row drift invalidates the active candidate and all downstream
evidence even when its porcelain status code/path tuple is unchanged.

Before every commit, a NUL-safe staged-path check also rejects intersection
between the allowed commit delta and the complete baseline dirty-path set. The
same validator requires the actual index to equal the external control's
reconstruction from the baseline/prior-trailer chain plus exactly the current
allowed rows. The commit itself uses `git --literal-pathspecs commit --only`
with the external bound NUL pathspec and exact control trailers; the pathspec
contains exactly the allowed paths, so
any preserved pre-existing staged change is excluded from the commit. The
validator runs again immediately afterward and proves those pre-existing index
entries remain present and the committed tree contains exactly the allowed
delta, then deletes the ephemeral transaction directory. A command that commits
the ambient index, omits/duplicates/changes a trailer, uses a broad pathspec, a
textual newline path list, or an unbound pathspec file is forbidden. The
literal seven-path guard below remains a redundant named safety subset for
clean-or-dirty protected files; it is not the boundary for all other dirty
content.

Canonical normalized digests use UTF-8 JSON with sorted keys, compact
separators, and no trailing newline. Except for the one closed exception below,
a record's `normalized_*_sha256` excludes only that exact digest field; nested
referenced-record digests remain included. The closed exception is
`precommit_control.v1`: its `normalized_control_sha256` projection excludes
exactly `normalized_control_sha256` and `final_message_binding` to break the
specified final-message/control-digest cycle. Every other normalized digest
projection excludes only its own digest field. No field beyond those exact
schema-specific exclusions—including owner provenance, timestamps, null
lifecycle slots, or claims-not-made—is excluded. File bindings use SHA-256 of
exact file bytes.
Timestamp fields require RFC 3339 with an explicit UTC offset. Duplicate JSON
keys fail before schema validation.

Scan records have two deliberately different digests. Every `root_scan.v1` and
`repository_reference_scan.v1` contains both `content_snapshot_sha256` and
`normalized_record_sha256`. The content snapshot is canonical JSON over only
the observed semantic snapshot: bound query/version and canonical roots;
sorted scanned/excluded path identities, file byte digests and sizes; parsed
occurrence/run/frame/status rows and counts; candidate/index/worktree facts for
repository scans; and all closed absence/tombstone facts. It excludes producer,
capture commit, started/finished/captured timestamps, elapsed time, record path,
and both digest fields. The normalized record digest excludes only itself and
therefore includes all timestamps/provenance plus the content snapshot digest.
Consequently timestamp-only recapture must preserve
`content_snapshot_sha256` while changing the exact file digest and normalized
record digest. Any semantic row, file byte, query, root, accepted absence, or
tombstone change must change the content snapshot. Owner attestations and
subjects bind both digests plus exact file bytes; equality/quiescence decisions
compare only the content snapshot and never mistake timestamp-inclusive record
inequality for store-content drift.

`required_focused_commands.v1` contains exactly `schema_version`,
`batch_binding`, `candidate_change_projection`, `base_commands`,
`candidate_specific_commands`, `smoke_requirement`, `command_count`,
`command_set_sha256`, `normalized_requirements_sha256`, and `claims_not_made`.
Every batch has these three base roles from repository root with
`PYTHONHASHSEED=0` and `LC_ALL=C.UTF-8`:

```text
collect-batch-core:
  ["pytest", "--collect-only", "-q", "tests/test_retirement_repository.py", "tests/test_retirement_evidence.py", "tests/test_loader_validation.py", "tests/test_workflow_lisp_procedure_first_migrations.py", "tests/test_workflow_lisp_drain_roadmap_routing.py"]
test-batch-core:
  ["pytest", "-q", "tests/test_retirement_repository.py", "tests/test_retirement_evidence.py", "tests/test_loader_validation.py", "tests/test_workflow_lisp_procedure_first_migrations.py", "tests/test_workflow_lisp_drain_roadmap_routing.py"]
validate-non-target-sources:
  ["python", "scripts/build_retirement_execution_index.py", "validate", "--kind", "non-target-queue-sources", "--record", "docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/non-target-queue-sources.json"]
```

The candidate change projection is derived from the fresh pre-scan's two
disposition lanes and committed prospective-eligibility transition, not from
Task-7 characterization or a future deletion-transition digest. It contains
the exact planned path/state roles; the later prospective deletion transition
must reproduce them in both directions before any check runs. Every retained production, CLI, script, routing, loader,
default, or current-guidance referrer edit requires at least one
candidate-specific owning selector row that binds the changed referrer and
test-module bytes; every surviving test referrer changed in place is itself an
exact selector input. The eligibility specification and quality reviews bind
this manifest through `pre-delete-gate.json` and reject an uncovered referrer,
extra command, broad-suite surrogate, or selector that does not collect.

`smoke_requirement.status=performed` is mandatory when the candidate changes
any launch/script/CLI/default/loader route, declares any `reroute_to_orc`
replacement expectation, changes an executable fixture, or is batch 2.
It then contains one exact argv/cwd/environment/state-root row for the affected
surviving route plus exact precondition argv
`["/usr/bin/test", "!", "-e", "<state-root>"]` and cleanup argv
`["/usr/bin/rm", "-rf", "--", "<state-root>"]`; all three command outcomes are
persisted in the smoke record. `not_required` is legal only when the complete transaction is
deletion-only or changes solely historical/report/test-characterization bytes,
with no replacement or executable route; it contains an exact machine-derived
reason code and null command. There is no free-form “if required” choice.

`focused_checks.v1` contains exactly `schema_version`, `candidate_binding`,
`required_commands_binding`, `commands`, `normalized_checks_sha256`, and
`claims_not_made`. Its required binding reopens
`focused/required-commands.json`, and the observed command set must equal all
base plus candidate-specific rows in both directions. Each sorted
command row contains exactly a deterministic `command_id` (SHA-256 of the
canonical argv/cwd/environment tuple), argv rather than shell prose, cwd,
selected environment keys, start/end timestamps, persistent log path/digest,
persistent exit-file path/digest and parsed integer, and outcome. Dynamic map
keys and unbound log paths are forbidden.

`import_graph.v1` contains both `semantic_graph_sha256` and
`normalized_record_sha256`. The semantic digest covers only the exact target
query plus sorted decoded nodes, edges, structural pointers, compatibility
facts, topological order, and cycle/external-importer facts. The normalized
record digest additionally covers capture HEAD, candidate/index projection,
producer, timestamps, and its deterministic record path. The prospective
assignment transition binds the exact pre-transition graph file and both
digests. The reviewed assignment binds the distinct post-routing graph file
and both digests and requires semantic-digest equality with the transition;
exact file and normalized-record equality are neither expected nor used as a
substitute for semantic equality.

`isolated_smoke.not_required.v1` contains the same closed top-level shape as
`isolated_smoke.performed.v1`, with `status=not_required`, a substantive reason,
and null stdout/stderr/exit bindings; those three files must be absent.
`performed` requires exact argv/cwd/external state-dir bindings, persistent
stdout/stderr/exit paths and byte digests, parsed exit zero, before/after
supported-root snapshot digests, and the disposable-root cleanup observation.

Every baseline, implementation-candidate, per-batch, and final
`broad_outcome.v1` record binds both the
exact persistent `pytest -rs` log and a persistent JUnit XML machine report
produced by that same command, plus the persistent ASCII exit file and parsed
integer. It also binds the same-candidate persistent `--collect-only` raw log,
exit file/parsed zero, and sorted node-ID list. Its top level contains exactly
`schema_version`, `candidate_binding`, `execution_ledger_binding`, `collection`, `command`, `environment`,
`collected_node_ids`, `rs_log`,
`exit_result`, `junit_report`, `pytest_temp_root_preflight`,
`failure_normalization`, `outcomes`, `run_root_snapshots`,
`known_failure_baseline_binding`, `approved_remediation_bindings`,
`approved_skip_change_bindings`, `baseline_comparison`,
`normalized_outcome_sha256`, and `claims_not_made`;
canonical fixtures close
every nested key. Snapshot rows have closed `scope_basis` values
`planning_candidate` (baseline, before owner scope) or `owner_supported`
(batches/final, after scope adoption); neither value asserts external-store
absence. The
evidence builder maps every failed or skipped JUnit testcase identity to
exactly one collected pytest node ID and persists those sorted node IDs plus
their counts/digests. Missing XML, a report/log digest mismatch, an outcome
that cannot map one-to-one, or totals that disagree across the log, XML, and
record fails closed. Both collection and broad-run exit files are exactly a
base-10 integer plus LF; missing or extra bytes fail, and collection must be
zero before node IDs are admissible. The preflight binding must be exact, must
precede the broad command under the same bound executable/environment, and must
equal `failure_normalization.pytest_temp_root_preflight_binding`; a stale or
cross-run probe fails closed. The Task-2 preimplementation capture uses
null baseline/remediation bindings and `outcome=baseline_candidate`; it becomes
usable only through the separately reviewed and owner-confirmed baseline record.
Every later gate requires that exact owner-confirmed baseline binding and the
complete cumulative sorted remediation bindings. Its closed outcome is
`known_failures_matched` or `approved_failure_subset`; the latter includes an
empty failure set and pytest exit zero only when reviewed remediation records
account for all baseline failures and no external row was removed. Skips remain
exact node IDs and must match their predecessor set or the complete separately
reviewed skip-change prefix; they never authorize a failure. Counts, prose skip reasons,
or a nonzero exit alone are not evidence.

Every Task-1 and Task-3-through-6 focused verification is durable under
`implementation-commits/<task>/focused/`; console output is never review
evidence. `implementation_focused_report.v1` contains exactly
`schema_version`, `task_contract_binding`, `candidate_binding`,
`execution_ledger_binding`, `required_commands`, `commands`, `command_count`,
`command_set_sha256`, `outcome`, `normalized_report_sha256`, and
`claims_not_made`.
`task_contract_binding` contains only the immutable approved-plan path/digest,
task number, and SHA-256 of the canonical required-command rows specified below.
`candidate_binding` uses the same exact HEAD/tree/index/worktree production
projection and fixed evidence-root exclusion as the paired broad outcome, or
as Task 1's raw bootstrap candidate; the report builder freezes it before the
first focused role and revalidates it after the last.
Each required-command row contains exactly a closed `role_id`, argv array, cwd,
and sorted selected environment. Each observed command row contains exactly the
same four fields plus sorted exact input path/digest bindings, start/end
timestamps, persistent log path/digest, persistent exit path/digest and parsed
integer, and `outcome`. Role IDs are safe deterministic path components. The
only legal raw paths are `focused/logs/<role-id>.log` and
`focused/exits/<role-id>.exit` beneath that task's deterministic directory.
The
required and observed role/argv/cwd/environment sets must be equal in both
directions; `command_count` and `command_set_sha256` bind that exact set. Every
exit file is base-10 plus LF, every parsed exit is zero, every log and input
binding reopens byte-identically, and `outcome=passed`. A missing, extra,
reordered, renamed, nonzero, stale, or console-only command fails closed.

For Tasks 3–6, `implementation_verification_subject.v1` is the sole subject of
both implementation reviews. Its exact top level is `schema_version`,
`task_contract_binding`, `candidate_binding`, `execution_ledger_binding`,
`focused_report_binding`, `broad_outcome_binding`,
`candidate_path_manifest`, `normalized_subject_sha256`, and
`claims_not_made`. The focused report must bind the same candidate identity,
immutable-plan task contract, and ledger bytes as the subject; the required
`broad_outcome.v1` must bind that same candidate and ledger at the deterministic
task path. `candidate_path_manifest` equals every already-existing task-
authorized production, test, fixture, focused, broad, optional remediation/
skip-change, deterministic generation-addressed materialization-request path,
and immutable output-snapshot path in both directions
and binds exact staged states and bytes; it excludes
only the not-yet-written subject itself, its two deterministic future live
review files, and the two corresponding closed immutable-review derivation
slots. Final staged validation requires exactly that manifest plus the subject,
live review pair, and derived immutable snapshots. The subject contains no self digest, review path/digest, or
future commit, so the two reviews can bind it without a cycle. A production, test, fixture,
focused-log, broad-outcome, ledger, or candidate-manifest change invalidates the
subject and both reviews.

Task 1 retains the separate `broad_evidence_bootstrap_subject.v1` because its
raw broad capture validates the builder that will later construct
`broad_outcome.v1`. That subject contains exactly `schema_version`,
`task_contract_binding`, `bootstrap_workspace_baseline_binding`, `candidate_binding`,
`execution_ledger_binding`,
`focused_report_binding`, `collection_binding`, `raw_broad_bindings`,
`observed_totals`, `observed_failed_node_ids`, `candidate_path_manifest`,
`normalized_subject_sha256`, and `claims_not_made`. Its focused report uses the
same generic schema and candidate/ledger equality rules; its candidate manifest
uses the same exact pre-subject coverage and excludes only its own future bytes
and the two deterministic live review files plus their two immutable-review
derivation slots. Final staged validation adds exactly the subject, two live
reviews, and two derived immutable snapshots to the bound manifest. This bootstrap-only
raw binding is not a broad outcome, owner baseline, or exception available to
Tasks 3–6. `bootstrap_workspace_baseline_binding` contains the adopted external
capture's base HEAD, complete semantic index and dirty-entry count/set digests,
archive/status/index capture digests, and normalized binding digest; it is the
durable Task-1 reconstruction authority without persisting user bytes.

The closed required focused command sets, all from repository root with
`PYTHONHASHSEED=0` and `LC_ALL=C.UTF-8`, are:

| Task | Role ID | Exact argv |
| --- | --- | --- |
| 1 | `collect-bootstrap-focused` | `["pytest", "--collect-only", "-q", "tests/test_retirement_broad_evidence.py", "tests/test_retirement_source_bindings.py"]` |
| 1 | `test-bootstrap-focused` | `["pytest", "-q", "tests/test_retirement_broad_evidence.py", "tests/test_retirement_source_bindings.py"]` |
| 1 | `compile-bootstrap` | `["python", "-m", "compileall", "orchestrator/retirement"]` |
| 3 | `collect-state-store-focused` | `["pytest", "--collect-only", "-q", "tests/test_retirement_state_store.py", "tests/test_workflow_lisp_procedure_identity_retirement.py"]` |
| 3 | `test-state-store-focused` | `["pytest", "-q", "tests/test_retirement_state_store.py", "tests/test_workflow_lisp_procedure_identity_retirement.py"]` |
| 3 | `validate-non-target-sources` | `["python", "-m", "orchestrator.retirement.source_bindings", "validate-non-target-sources", "--repository-root", ".", "--record", "docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/non-target-queue-sources.json"]` |
| 4 | `collect-consumer-scan-focused` | `["pytest", "--collect-only", "-q", "tests/test_retirement_state_store.py", "tests/test_workflow_lisp_procedure_identity_retirement.py"]` |
| 4 | `test-consumer-scan-focused` | `["pytest", "-q", "tests/test_retirement_state_store.py", "tests/test_workflow_lisp_procedure_identity_retirement.py"]` |
| 4 | `validate-non-target-sources` | `["python", "-m", "orchestrator.retirement.source_bindings", "validate-non-target-sources", "--repository-root", ".", "--record", "docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/non-target-queue-sources.json"]` |
| 5 | `collect-repository-focused` | `["pytest", "--collect-only", "-q", "tests/test_retirement_repository.py", "tests/test_loader_validation.py"]` |
| 5 | `test-repository-focused` | `["pytest", "-q", "tests/test_retirement_repository.py", "tests/test_loader_validation.py"]` |
| 5 | `validate-non-target-sources` | `["python", "-m", "orchestrator.retirement.source_bindings", "validate-non-target-sources", "--repository-root", ".", "--record", "docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/non-target-queue-sources.json"]` |
| 6 | `collect-evidence-focused` | `["pytest", "--collect-only", "-q", "tests/test_retirement_broad_evidence.py", "tests/test_retirement_state_store.py", "tests/test_retirement_repository.py", "tests/test_retirement_evidence.py"]` |
| 6 | `test-evidence-focused` | `["pytest", "-q", "tests/test_retirement_broad_evidence.py", "tests/test_retirement_state_store.py", "tests/test_retirement_repository.py", "tests/test_retirement_evidence.py"]` |
| 6 | `compile-retirement-package` | `["python", "-m", "compileall", "orchestrator/retirement"]` |
| 6 | `test-cli-temporary-repository-smoke` | `["pytest", "-q", "tests/test_retirement_evidence.py::test_retirement_execution_index_cli_temporary_repository_smoke"]` |
| 6 | `validate-non-target-sources` | `["python", "scripts/build_retirement_execution_index.py", "validate", "--kind", "non-target-queue-sources", "--record", "docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/non-target-queue-sources.json"]` |

The validator is generic: it compares record-supplied rows to the exact
content-addressed task contract supplied as data and contains no task number,
selector, queue, module, repository, or family branch. Canonical fixtures use
neutral paths and role IDs. The plan table and independent reviews determine
the Task-1/3/4/5/6 task-contract inputs; production merely enforces their exact
closed equality.

`prospective_assignment_transition.v1` and
`prospective_eligibility_transition.v1` use the same cycle-breaking rule as the
deletion transition. Each binds a prior authority/input state, intended semantic
index projection, exact sorted nonexcluded external pre/post byte manifest, null
future scan/gate/review bindings, the immutable non-target-source record and a
fresh all-ten validation, and normalized transition digest. Assignment
requires the exact program/triage/docs-index/live-projection/routing-test set;
eligibility additionally binds the immutable pending batch owner-lifecycle
consumer plus the exact externally adopted/continuity records and requires the
exact batch pre-edit projection/routing set. It cannot bind its future confirmed
subject, reviews, consumer, or containing commit. The confirmed subject binds
the transition, and the confirmed consumer closes that cycle-free chain. The
transition is committed with its external bytes before repository capture and
remains immutable afterward. The eventual assignment or eligible index must
render byte-identically while adding only evidence-root bindings.

`deletion_subject.v1` contains exact binding objects—not free-form path lists—
for the execution-ledger generation, every deterministic generation-addressed
materialization request and immutable output snapshot consumed by the batch,
the post-Step-6 pre-deletion index baseline, batch pre/post repository scans,
both pre-disposition lanes, tracked-deletion
tombstones, post reference reconciliation, every supported root's pre/post
store scan, prospective eligibility and deletion transitions, required-focused-
command manifest, focused-check manifest and all referenced logs/exits, isolated-smoke record and optional
outputs, collection log/exit, collected IDs, persistent `-rs` log, persistent
broad-run exit, JUnit report, pytest-temp-root preflight, broad outcome JSON, the immutable owner-confirmed
implementation-failure-baseline chain, and the complete cumulative reviewed
remediation and skip-change prefixes. It additionally contains the immutable
`non-target-queue-sources.json` binding, a fresh all-ten validation result, and
the immutable `workspace-baseline.json` binding plus a fresh all-dirty-entry
existence/type/content validation result, and
an exact assertion that none of those paths occurs in its substantive
transaction. Every object carries a
repository-relative path, SHA-256 of exact bytes, schema version where
applicable, and required parsed status/count fields. A missing, unlisted,
duplicate, or additional evidence binding rejects the subject.

`deletion-subject.json` is finalized after deletion/referrer edits, post-edit
repository and store scans, focused checks, the isolated smoke when required,
and broad pytest complete. It enumerates exact deleted pre-edit blobs, every
non-lifecycle changed/deleted/created path with its pre/post state and digest,
and byte-digest bindings to those scan/test reports. It explicitly lists the
excluded evidence-root index, batch-projection, pending, and review paths and
makes no whole-tree claim. The generated external live projection and any
routing/status document outside the exact scanner-owned evidence-root exclusion
are never excluded: they must reach their final commit-A bytes before the final
post scan and appear in the subject with exact pre/post state and byte digests.
The two post-edit reviews bind only this final subject plus its exact scan/test
bindings; they never bind the pending event. The subsequently created pending
event binds the subject and both approved review byte digests and is included
in commit A, but contains no commit-A SHA/tree field. Closure reviews bind only
the already-existing commit A, its Git tree, `closure-validation.json`, and the
prior subject/event digests. The closure event may bind those review files
because the reviews do not bind the closure event or commit B. This ordering is
the sole deletion lifecycle; a subject created before post-edit evidence, a
review that binds a pending event, or a pending event created before both
reviews approve fails closed.

To avoid a late external-projection mutation, each batch prepares a closed
prospective semantic transition inside the evidence root before its final post
scan. The transition binds prior valid index, exact deletion transaction,
resulting active/history partition, the immutable non-target-source record plus
fresh all-ten validation, and intended batch lifecycle status but has
null post-edit review/pending-event bindings. `project-transition` renders the
external `docs/workflow_yaml_retirement_execution.md` and any required routing
status bytes from that semantic transition. After reviews, the real pending
event/index fills only evidence bindings and must render byte-identically; a
different projection rejects commit A. This is not an alternate authority—the
committed index remains authority and the prospective transition is only a
reviewable commit candidate.

Commit B may modify only files under the exact scanner-owned execution-evidence
root. It may not update the external live projection, roadmap, index outside
that root, routing docs/tests, workflow/reference source, or any other
nonexcluded path. If a nonexcluded change becomes necessary after the final
post scan/reviews but before commit A, invalidate the subject/reviews and repeat
the full final-scan and post-edit-review lifecycle before commit A.

After commit A, a necessary nonexcluded correction enters the sole closed repair
lane; it may not be smuggled into closure. Repairs use monotonically numbered
`repairs/repair-MM/` directories with no gaps. Each
`prospective_repair_transition.v1` binds commit A and every earlier repair
commit/event, the exact intended nonexcluded changes, unchanged active/path-
owning history, the immutable non-target-source record plus fresh all-ten
validation, and null future scan/review/event bindings. Materialize those exact
bytes before recapturing the canonical `repository_reference_scan.v1` retired
and replacement channels and a closed reconciliation against the predecessor's
allowed historical/test and replacement state, unchanged supported-root snapshots, affected focused/
smoke checks, and the broad gate. `repair_subject.v1` then binds the prospective
transition, fresh scan/test evidence, exact pre/post bytes, ledger digest, and
the complete predecessor chain. Specification and quality reviews bind that
immutable subject at the deterministic repair paths.

Only after both repair reviews approve may commit R-MM include a non-path-owning
`deletion_repair_committed_pending_binding` event plus the reviewed correction.
The event binds its prior substantive predecessor commit/tree, prior event,
repair subject, and both review digests, but deliberately contains no R-MM
commit/tree field. It never owns a frozen queue path, changes active/history
ownership, replaces the original deletion event, or authorizes a non-target
source/store mutation. A later necessary correction repeats the same lifecycle
as repair `MM+1`; an unreviewed, missing, duplicate, reordered, or empty repair
event fails closed.

`closure_validation.v1` binds the original deletion commit A/tree, the prior
deletion subject/pending event, the complete ordered zero-or-more repair
commit/event chain, and the immediate substantive predecessor, which is commit
A when the chain is empty or the latest repair commit otherwise. It also binds
the immutable non-target-source record and a fresh all-ten validation at that
predecessor HEAD. `close-prior-deletion` requires current HEAD to equal that
immediate predecessor and derives/validates the evidence-only closure-event
inputs without writing them; the sole `materialize --kind deletion-closure`
transaction creates the event. It does not require commit A to remain the
immediate predecessor after a valid repair.
The closure candidate and commit-B HEAD validators repeat the same chain and
live checks. Thus commit B remains evidence-only while a reviewed repair commit
can intervene without breaking reconciliation or predecessor identity.

The repair schemas are closed. `prospective_repair_transition.v1` contains
exactly `schema_version`, `batch_binding`, `repair_number`,
`predecessor_chain_binding`, `intended_external_changes`,
`non_target_queue_sources_binding`, `non_target_queue_sources_validation`,
`run_root_snapshot_bindings`, `future_bindings`,
`normalized_transition_sha256`, and `claims_not_made`; every future scan,
subject, review, and repair-event digest is null. `repair_subject.v1` contains
exactly `schema_version`, `batch_binding`, `repair_number`,
`execution_ledger_binding`, `prospective_transition_binding`,
`predecessor_chain_binding`, `repository_scan_binding`,
`repository_reconciliation_binding`, `required_focused_commands_binding`,
`focused_binding`,
`smoke_binding`, `broad_binding`, `non_target_queue_sources_binding`,
`non_target_queue_sources_validation`, `run_root_snapshot_bindings`,
`changed_paths`, `normalized_subject_sha256`, and `claims_not_made`.
`repair_reference_reconciliation.v1` contains exactly `schema_version`,
`predecessor_state_binding`, `repair_scan_binding`, `allowed_pre_occurrences`,
`allowed_post_occurrences`, `transition_dispositions`,
`forbidden_active_occurrence_count`, `pre_occurrence_set_sha256`,
`post_occurrence_set_sha256`,
`normalized_reconciliation_sha256`, and `claims_not_made`; the allowed set must
start from the predecessor's closed historical/test and replacement set, every
change must have one reviewed exact transition disposition, the post set must
match the repair scan in both directions, and the forbidden count must be zero.
`deletion_repair_pending.v1` contains exactly `schema_version`, `batch_binding`,
`repair_number`, `prior_substantive_predecessor`, `prior_event_binding`,
`subject_binding`, `review_bindings`, `active_history_binding`,
`normalized_event_sha256`, and `claims_not_made`; it has no containing-commit
field. Canonical fixtures close every nested key, path, digest, count, and null
slot.

Pending owner fixtures have `evidence_status=pending_owner_confirmation`, null
owner/adoption values, a mechanically truthful `prepared_by`, and no affirmative
confirmation booleans. Confirmed fixtures require all owner/adoption fields,
equal or ordered timestamps as specified by the fixture, and every fixed
statement/boolean. A validator must never “upgrade” a pending fixture or supply
an owner value. Production creates each pending fixture only through a prepared
request consumed by `materialize-pending`; ordinary `materialize` is invalid for
these kinds.

`owner_lifecycle_review_subject.v1` contains exactly `schema_version`,
`lifecycle_kind` (`root_scope_pending | root_scope_confirmed |
initial_root_bindings_pending | initial_root_bindings_confirmed`),
`prior_index_generation_binding`,
`record_path`, `record_sha256`, `record_snapshot`,
`dependent_record_snapshots`, `materialization_generation_bindings`,
`execution_ledger_binding`,
`intended_index_projection`, `owner_boundary_checks`,
`normalized_subject_sha256`, and `claims_not_made`. Pending subjects prove all
owner-only fields remain unpopulated; confirmed subjects bind the exact adopted
record, preserve the prior pending subject/review pair, and prove no agent
manufactured adoption. Each subject is immutable at its deterministic
`review-subjects/<lifecycle-kind-with-hyphens>.json` path. The consuming index
can therefore validate the embedded pending snapshot after the live lifecycle
path advances to confirmed bytes. `dependent_record_snapshots` is empty for
root scope and contains every exact per-root attestation snapshot for the
initial-root lifecycles; each snapshot's canonical digest must match its
review-time live file. `prior_index_generation_binding` reopens the immutable
request/output snapshot for the exact review-time prior index object;
`materialization_generation_bindings` does the same for the ledger, pending
record materialization, and generated projection. No review relies on a mutable
old path remaining live.
The consuming index
must reproduce the intended semantic projection exactly while filling only the
two deterministic review-digest slots that are null in the subject. The subject
never binds the future consuming index bytes, so no digest cycle exists. The
index binds the corresponding two review files; replacing the live scope or
initial-binding record later never makes the earlier subject disappear.

### Per-batch pre-capture owner lifecycle

Every batch has a mandatory two-stage owner-lifecycle namespace separate from
its eligibility/post-edit/closure `reviews/` directory. The pending stage lands
before the owner pause; the confirmed stage is the final reviewed nonexcluded
commit before the fresh pre-repository scan. It exists even when every root uses
continuity and the batch projects no runs, so every pre-capture commit has the
same closed authority chain.

`batch_owner_lifecycle_subject.v1` contains exactly `schema_version`,
`lifecycle_stage` (`pending | confirmed`), `batch_binding`,
`execution_ledger_binding`, `prior_index_generation_binding`,
`root_scope_binding`, `initial_root_bindings_binding`, `root_scan_bindings`,
`root_adoption_bindings`, `quiescence_continuity_bindings`,
`run_support_disposition_binding`, `pending_predecessor_binding`,
`prospective_eligibility_transition_binding`, `external_projection_manifest`,
`intended_index_projection`, `future_review_authorizations`, `owner_boundary_checks`,
`normalized_subject_sha256`, and `claims_not_made`. Every binding uses exact
generation-addressed requests/snapshots where applicable. Pending subjects bind
all fresh scans, every mechanically pending root/run form, every continuity
record, null `pending_predecessor_binding`, a null prospective transition, an
empty external manifest, and an intended index whose batch owner lifecycle is
`pending_owner_confirmation`. Confirmed subjects preserve the pending consumer,
bind every owner-confirmed replacement or unchanged continuity record in both
directions, require root-adoption time no later than any dependent run-support
adoption, bind the final prospective eligibility transition and its complete
external pre/post manifest, and intend `owner_confirmed` without claiming
eligibility. A subject never binds its future reviews, consumer, or containing
commit.

`batch_owner_lifecycle_consumer.v1` contains exactly `schema_version`,
`lifecycle_stage`, `batch_binding`, `execution_ledger_binding`,
`prior_index_generation_binding`, `subject_binding`, `review_bindings`,
`pending_predecessor_binding`, `owner_record_bindings`,
`prospective_eligibility_transition_binding`, `external_projection_manifest`,
`intended_index_projection`, `normalized_consumer_sha256`, and
`claims_not_made`. It is materialized only after the stage's specification and
quality reviews approve the immutable subject. The pending consumer requires a
null predecessor/transition and empty external manifest. The confirmed consumer
binds the immutable pending consumer plus the final transition/external bytes.
The same commit may materialize the consuming execution-index generation, which
binds this consumer and fills only review/consumer coordinates already null in
the subject. Neither consumer binds its own containing commit.

The exact paths are
`batches/batch-NN/owner-lifecycle/{pending,confirmed}-subject.json`,
`{pending,confirmed}-specification.json`,
`{pending,confirmed}-quality.json`, and
`{pending,confirmed}-consumer.json`. The pending commit contains exactly the
pending subject, two live reviews plus immutable review snapshots, pending
consumer, pending owner forms/continuity evidence, ledger/index generations,
and their deterministic materialization requests/snapshots. The confirmed
commit contains the analogous confirmed set, owner-confirmed replacements, the
prospective eligibility transition, and every exact external projection/routing
byte it binds. The external pre/post manifest is reviewed before publication;
after the confirmed commit, any owner, projection, routing, source, or test-byte
change invalidates the lifecycle and restarts it before repository capture.

The canonical review object contains exactly `schema_version`, `review_kind`
(`specification | code_quality`), `reviewer`, `reviewed_at`, `subject` (kind,
path, exact byte digest, and optional already-existing commit/tree), `result`,
`issues`, and `claims_not_made`. It has no `self_path`, containing-commit field,
or wildcard tree binding. `approved` requires an empty issue list; `rejected`
requires at least one typed issue. This is the sole review artifact shape used
at implementation, assignment, owner-lifecycle, eligibility, post-edit, repair,
closure, and final gates.
There is no `security`, `threat_model`, or penetration-review kind and no
security-only review artifact is admitted by a review directory or completion
cardinality under this plan.

Before a canonical review path is published or replaced, validate its complete
bytes and exclusively create an immutable copy at
`immutable-reviews/<subject-logical-path-sha256-lowercase-hex>/`
`<subject-file-bytes-sha256-lowercase-hex>/`
`<review-kind>-<review-file-bytes-sha256-lowercase-hex>.json`.

All three digest components are exactly 64 characters in `[0-9a-f]`. The first
preimage is the exact UTF-8 bytes of the already-validated canonical repository-
relative POSIX subject logical path, with no prefix, JSON quoting, Unicode
renormalization, separator rewrite, NUL, or newline. The second preimage is the
complete exact subject-file byte stream as read from disk, including any final
newline. The third preimage is the complete exact validated `review.v1` file
byte stream, likewise including any final newline. There is no canonical-JSON
re-encoding in either file-byte hash. Uppercase hex, an alternate byte preimage,
or a digest placed in the wrong coordinate fails before publication.

A `review_binding.v1` consumes both the canonical logical path and the
immutable snapshot path/digest, review kind, reviewer identity, reviewed-at
value, result, and exact subject coordinates. Historical validation reopens the
immutable snapshot and subject; it never trusts current bytes at a replaceable
logical review path. Immutable review files are exclusive-create, append-only,
and never renamed, overwritten, or deleted.

The closed binding contains exactly `schema_version`, `logical_path`,
`immutable_path`, `sha256`, `review_kind`, `reviewer`, `reviewed_at`, `result`,
`subject`, `normalized_binding_sha256`, and `claims_not_made`. Its subject object
is byte-identical to the review object's closed subject coordinates, and its
digest projection excludes only `normalized_binding_sha256`.

Accordingly, every later instruction or abbreviated schema that says a record
"binds a review path/digest" or "binds review digests" means the complete
`review_binding.v1`, including its immutable snapshot coordinates; a bare live
path plus digest never satisfies that wording.

Every subject's closed future-review authorization therefore contains two
roles per reviewer: the exact deterministic live review path and one
`immutable_review_path.v1` derivation slot carrying the exact subject logical
path/digest and review kind. The slot resolves only after validated review bytes
exist; the external precommit control must derive the unique immutable path by
the three hash rules above. Review-directory cardinalities below count live
canonical files only, while staged/committed allowed deltas contain both live
files and both immutable snapshots. This closed derivation is not a wildcard.

The review subject-kind enum is exactly `broad_evidence_bootstrap |
implementation_failure_baseline | implementation_candidate |
broad_failure_remediation | broad_skip_change | category_input | batch_assignment | broad_baseline | batch_eligibility |
root_scope_pending | root_scope_confirmed | initial_root_bindings_pending |
initial_root_bindings_confirmed | batch_owner_pending |
batch_owner_confirmed | batch_post_edit | batch_repair |
batch_closure | final_closeout`; each value is legal only at the lifecycle/path in the table
below.

Review paths and cardinalities are closed. `review_kind=specification` is legal
only at a `*-specification.json` path and `code_quality` only at the matching
`*-quality.json`; each pair must contain two distinct reviewer identities,
bind byte-identical subject coordinates, and contain exactly two live files. A
re-review may replace the same deterministic live file after its subject or
verdict changes only after preserving the prior review in the immutable review
store. Every prior consuming record retains its exact immutable binding; a new
consumer may bind only the newly validated snapshot. No numbered, dated,
“latest,” wildcard, or auxiliary filename is allowed in a live `reviews/`
directory, and the immutable store is validated separately from those live
cardinality rules.

| Lifecycle | Exact review files | Exact primary subject | Binding that consumes approval |
| --- | --- | --- | --- |
| broad-evidence bootstrap | `implementation-commits/task-01-bootstrap/specification-review.json`, `implementation-commits/task-01-bootstrap/quality-review.json` | `implementation-commits/task-01-bootstrap/subject.json` (`broad_evidence_bootstrap_subject.v1`) | Task-1 bootstrap commit contains the focused report, subject, and both reviews; Task 2's ledger transition binds their exact paths/digests after they exist |
| implementation failure baseline | `reviews/implementation-baseline-specification.json`, `reviews/implementation-baseline-quality.json` | `implementation-baseline/known-failure-baseline.json` | owner attestation binds both; initial index later binds the complete adopted chain |
| implementation candidate | `implementation-commits/task-0N/specification-review.json`, `implementation-commits/task-0N/quality-review.json` for N=3..6 | matching `implementation-commits/task-0N/subject.json` (`implementation_verification_subject.v1`), which binds the focused report and required broad outcome | the reviewed candidate commit contains subject/reviews; the next task's ledger transition binds their exact paths/digests after they exist |
| optional failure remediation | deterministic `remediation-specification-review.json` and `remediation-quality-review.json` beside a Task-3–6, batch `broad/`, or `final/` immutable `failure-remediation.json` | that matching immutable remediation record | later candidate outcome binds record and both review digests |
| optional skip-set transition | deterministic `skip-change-specification-review.json` and `skip-change-quality-review.json` beside a Task-3–6, batch `broad/`, or `final/` immutable `skip-change.json` | that matching immutable skip-change record | later candidate outcome binds record and both review digests and advances only the accepted skip-set prefix |
| category input | `reviews/category-input-specification.json`, `reviews/category-input-quality.json` | `batch-category-input.json` | `batch-assignment.json` binds both digests |
| assignment | `reviews/assignment-specification.json`, `reviews/assignment-quality.json` | `batch-assignment.json` | initial `execution-index.json` binds both digests |
| broad baseline | `reviews/baseline-specification.json`, `reviews/baseline-quality.json` | `baseline/outcome.json` | index baseline binding becomes `approved` with outcome and both review digests |
| pending root scope | `reviews/root-scope-pending-specification.json`, `reviews/root-scope-pending-quality.json` | `review-subjects/root-scope-pending.json` | pending root-scope index binding consumes the pair |
| confirmed root scope | `reviews/root-scope-confirmed-specification.json`, `reviews/root-scope-confirmed-quality.json` | `review-subjects/root-scope-confirmed.json` | confirmed root-scope index binding preserves pending and consumes confirmed pair |
| pending initial roots | `reviews/initial-root-bindings-pending-specification.json`, `reviews/initial-root-bindings-pending-quality.json` | `review-subjects/initial-root-bindings-pending.json` | pending initial-root index binding consumes the pair |
| confirmed initial roots | `reviews/initial-root-bindings-confirmed-specification.json`, `reviews/initial-root-bindings-confirmed-quality.json` | `review-subjects/initial-root-bindings-confirmed.json` | confirmed initial-root index binding preserves pending and consumes confirmed pair |
| pending batch owner lifecycle | `batches/batch-NN/owner-lifecycle/pending-specification.json`, `batches/batch-NN/owner-lifecycle/pending-quality.json` | `batches/batch-NN/owner-lifecycle/pending-subject.json` | matching `pending-consumer.json` binds both before the pending owner-lifecycle commit |
| confirmed batch owner lifecycle | `batches/batch-NN/owner-lifecycle/confirmed-specification.json`, `batches/batch-NN/owner-lifecycle/confirmed-quality.json` | `batches/batch-NN/owner-lifecycle/confirmed-subject.json` | matching `confirmed-consumer.json` preserves the pending consumer and binds both before the final pre-capture commit |
| batch eligibility | `batches/batch-NN/reviews/eligibility-specification.json`, `batches/batch-NN/reviews/eligibility-quality.json` | `batches/batch-NN/pre-delete-gate.json` | batch may become `eligible` only with both approved digests |
| batch post-edit | `batches/batch-NN/reviews/post-edit-specification.json`, `batches/batch-NN/reviews/post-edit-quality.json` | `batches/batch-NN/deletion-subject.json` | pending event binds both before commit A |
| batch repair | `batches/batch-NN/repairs/repair-MM/reviews/repair-specification.json`, `batches/batch-NN/repairs/repair-MM/reviews/repair-quality.json` | matching immutable `repairs/repair-MM/subject.json` | matching non-owning repair event binds both before repair commit R-MM |
| batch closure | `batches/batch-NN/reviews/closure-specification.json`, `batches/batch-NN/reviews/closure-quality.json` | `batches/batch-NN/closure-validation.json` for the already-existing immediate substantive predecessor (commit A or latest repair) and complete chain back to A | closure event binds both before commit B |
| final closeout | `reviews/final-specification.json`, `reviews/final-quality.json` | `final/subject.json` | closeout index update binds both digests; reviewed external bytes remain unchanged |

Top-level review-directory cardinality begins at `2` after the adopted
implementation-failure baseline, then progresses exactly to `4` after
category-input review, `6` after assignment review, `8` after pre-deletion
broad-baseline review, `10` after pending root scope, `12` after confirmed root
scope, `14` after pending initial-root bindings, `16` after confirmed
initial-root bindings, and `18` after final review. Each batch review directory progresses exactly
`0 -> 2` at eligibility, `4` in commit A, and `6` in commit B. A missing member,
extra filename, wrong subject kind/path/digest, cross-stage review, duplicate
reviewer identity, rejected result, or consuming binding created before its
pair is complete fails closed. Each conditional repair review directory has
exactly two files; it does not alter the fixed six-file batch review directory.
Each batch owner-lifecycle directory independently contains exactly four
pending files and four confirmed files; those review pairs do not count toward
the fixed six-file batch review directory.
Each implementation task directory has exactly one specification and one
quality review at its two deterministic root paths; its `focused/` directory
contains only `report.json` plus the report's exact log/exit pairs. Subject and
review cardinality is one/two even when optional broad remediation or skip-change triples are
present, because remediation uses its own separately named subject and review
pair. No implementation review may bind `outcome.json` directly or name focused
results outside the single bound implementation subject.

`prospective_closeout_transition.v1` is the cycle-free final-closeout analogue
of the per-batch prospective transition. Its exact top level is
`schema_version`, `prior_index_binding`, `intended_closeout`, sorted
`external_changes`, `non_target_queue_sources_binding`,
`non_target_queue_sources_validation`, `review_bindings`,
`normalized_transition_sha256`, and `claims_not_made`.
The two non-target fields bind the immutable Task-2 record and a fresh exact
all-ten live validation. `intended_closeout` fixes only the completed queue, selected
next queue, resulting active/history counts, and intended `approved` closeout
status. Before final evidence, `review_bindings` contains the exact final review
paths with null digests and remains immutable through closeout. `external_changes` has exactly four role/path rows:
Stage-6 program, documentation index, generated live projection, and owning
routing test. Each row binds exact pre-state kind/mode/size/byte digest and Git
blob when tracked, plus exact materialized post-state kind/mode/size/byte
digest. Missing/extra path, wrong role, non-regular file, symlink, post-byte
drift, or an already-populated review digest fails closed. The transition is an
evidence-root candidate record, not semantic authority; the committed execution
index remains authority.

The final validator/focused/end-to-end reports are persistent closed evidence,
not prose inferred during review. `final_validator_report.v1`,
`final_focused_report.v1`, and `final_end_to_end_report.v1` each contain exactly
`schema_version`, `candidate_binding`, sorted `commands`, `outcome`,
`normalized_report_sha256`, and `claims_not_made`. Every command row contains
an exact closed role ID used as its deterministic log/exit path component,
argv, cwd, selected environment, input paths/digests, start/end timestamps,
persistent log path/digest, persistent exit path/digest and parsed integer, and
typed issues/outcome. Logs live only at the corresponding deterministic
`final/{validators,focused,end-to-end}/logs/<id>.log`; exits live at matching
`exits/<id>.exit` and are base-10 plus LF. The report's command set must equal
the plan's required selector/validator set in both directions; zero parsed exit,
empty issues, and `outcome=passed` are required. Missing/extra command, log,
exit, stale digest, ignored temporary surrogate, or report assembled from an
unbound console summary fails closed.

`final_review_subject.v1` contains exactly `schema_version`,
`execution_ledger_binding`, pre-review final execution-index generation binding
and zero-active reconciliation, prospective
closeout-transition path/digest, final repository-scan path/digest and exact
allowed historical/test occurrence reconciliation, final validator report
bindings (including every nested log/exit), final focused and end-to-end report
bindings (including every nested log/exit), `final/outcome.json` binding,
workspace-baseline binding plus a fresh all-dirty-entry content comparison,
protected-baseline comparison, immutable non-target-source binding plus a fresh
all-ten validation result, exact sorted nonexcluded closeout candidate
manifest, exact sorted fixed-evidence manifest, deterministic post-review
consuming-path manifest,
`normalized_subject_sha256`, and `claims_not_made`. The nonexcluded manifest is
exactly the transition's four external rows and repeats their pre/post
kind/mode/size/byte digests and pre-edit blob OIDs; it binds the materialized
post bytes reviewed and later staged. The fixed-evidence manifest enumerates
the execution ledger, every transition, scan, validator/focused/end-to-end raw file and report,
collection/broad raw file, pytest-temp-root preflight, and outcome, and every
deterministic generation-
addressed materialization request plus immutable output snapshot by exact
path/size/byte digest; the
subject itself is instead bound by each review's subject digest. The
post-review consuming-path manifest enumerates only the execution index and two
deterministic final review paths as legal later writes. Transition,
repository-scan, report, raw-log, outcome, and subject bytes are already fixed
and bound before review; none may change after review begins. The subject
excludes final-review contents and future closeout
commit/tree, so the final reviews and consuming index update have no digest
cycle. Any other path, any changed evidence byte outside those three consuming
paths, or any changed nonexcluded byte invalidates the subject and all final
evidence.

## Whole-Query Scan And Batch-Projection Semantics

`scan_workflow_file_consumers` always scans the complete 100-path query for one
root. Every occurrence row binds:

- the exact query `target_path`;
- the raw `observed_workflow_file` value and whether it was absolute or
  workspace-relative;
- the canonical normalized source path;
- the supported store file and JSON/JSONL pointer containing the occurrence;
- the distinct containing top-level run ID, top-level state path, raw status,
  and `terminal | nonterminal | unknown` status characterization; and
- either null for a top-level occurrence or a frame identity containing
  `kind`, canonical frame key, frame file/pointer, and optional declared frame
  ID.

Each root-scope row binds `canonical_workspace_root`,
`canonical_workflow_source_base`, and `canonical_run_root`. Canonical identity
for every query row is exactly
`canonical_workspace_root / repository_relative_target_path`; the target path
already begins with `workflows/`, so it is never joined to the workflow source
base. A relative observed `workflow_file` is interpreted as workspace-relative
and must normalize exactly to that canonical identity. An absolute observed
value must normalize to the same identity. The workflow source base is only an
allowed-subtree constraint: it must equal
`canonical_workspace_root / "workflows"`, and every canonical target must be
inside it. The run root must equal
`canonical_workspace_root / ".orchestrate/runs"`. Thus the five fixed triples
are exactly:

| Canonical workspace root | Allowed workflow source base | Canonical run root |
| --- | --- | --- |
| `/home/ollie/Documents/agent-orchestration` | `/home/ollie/Documents/agent-orchestration/workflows` | `/home/ollie/Documents/agent-orchestration/.orchestrate/runs` |
| `/home/ollie/Documents/agent-orchestration-2` | `/home/ollie/Documents/agent-orchestration-2/workflows` | `/home/ollie/Documents/agent-orchestration-2/.orchestrate/runs` |
| `/home/ollie/Documents/EasySpin` | `/home/ollie/Documents/EasySpin/workflows` | `/home/ollie/Documents/EasySpin/.orchestrate/runs` |
| `/home/ollie/Documents/PtychoPINN` | `/home/ollie/Documents/PtychoPINN/workflows` | `/home/ollie/Documents/PtychoPINN/.orchestrate/runs` |
| `/home/ollie/Documents/ptychopinnpaper2` | `/home/ollie/Documents/ptychopinnpaper2/workflows` | `/home/ollie/Documents/ptychopinnpaper2/.orchestrate/runs` |

For example, target `workflows/examples/x.yaml` under the EasySpin slot is
`/home/ollie/Documents/EasySpin/workflows/examples/x.yaml`, never
`/home/ollie/Documents/EasySpin/workflows/workflows/examples/x.yaml`.
Escapes, symlink components, a mismatched workspace/source/run relationship, a
value that resolves to more than one target, a target outside the source-base
subtree, or a root without one unambiguous triple fails closed. The workspace,
source base, run root, and all existing path prefixes must exist without
symlinks, but the final workflow file need not still exist after an earlier
deletion commit; normalization is lexical under the bound workspace and never
falls back to the scanner's current working directory.

Occurrence deduplication uses `(target_path, store_file, object_pointer)`. A
containing run uses `(root_digest, run_directory, run_id)`. An embedded frame
uses `(containing_run_key, "embedded", store_file, object_pointer)`; a file
frame uses `(containing_run_key, "file", canonical_frame_relative_path,
declared_frame_id-or-null)`. Repeated occurrences in one frame do not multiply
the distinct-frame count. Embedded and file frame keys are never coalesced
merely because they expose the same declared ID; uncertain aliasing therefore
fails safe by remaining two consumers. A missing/duplicate run ID, ambiguous
containing directory, or unreadable containing state rejects the scan rather
than assigning a guessed run.

Whole-query run/frame totals and store-wide status totals are disclosure only.
For each batch/root, `batch-projection.json` filters occurrence rows by the
batch's exact path set, binds the batch path-list digest, and derives sorted
distinct containing-run and frame keys plus their own normalized projection
digest. The gate recomputes that projection from the bound whole-query scan;
copying or subtracting aggregate totals is forbidden.

Every distinct containing run in a nonempty batch projection requires a closed
owner-adopted support disposition. `supported` means the run remains a
supported consumer and blocks deletion whenever either resume support or
consumer support is `supported`, independent of its raw status label.
`unsupported_abandoned` is nonblocking only when both resume and consumer
support are explicitly `retired`, with a nonempty reason and content-addressed
evidence, and the owner confirms that no run/store bytes were changed to reach
the decision. Thus a failed-but-resumable run and terminal history whose resume
remains supported block; raw terminality alone never makes a row eligible.
`blocking_run_keys` contains every supported or undispositioned projected run;
`blocking_frame_keys` contains every distinct projected frame owned by those
runs. An abandoned run removes only its own run/frame keys after exact coverage
validation. `pre-delete-gate.json` stores both sorted sets and
`normalized_blocking_set_sha256`, computed from canonical JSON containing the
batch path-list digest plus both sets; the validator recomputes it from scan,
projection, and disposition inputs.
Missing disposition, extra disposition, or incomplete projected-run coverage
blocks the batch. Both-direction tests must prove whole-query-only matches do
not gate an unrelated batch and one batch-scoped supported run/frame does.
The gate also binds the immutable non-target-source record and its fresh
all-ten live validation; either mismatch blocks independently of the run/frame
sets.

## Owner Records And Claim Boundaries

An implementation agent may prepare a pending form, but must not populate
owner identity, confirmation values, adoption timestamps, or owner provenance.
A relayed message is not an attestation. The owner (or an explicitly delegated
agent whose delegation is stated in the record) must review and adopt the
complete record.

### Supported-root scope form

Exact path:
`docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/attestations/pre-delete/supported-run-root-scope.json`.

Schema `workflow_retirement_supported_root_scope.v1` contains exactly:

- `evidence_status` (`pending_owner_confirmation` or `owner_confirmed`);
- the frozen handoff path/digest/schema, queue path count, and query digest;
- `roots`, exactly five fixed slots sorted by canonical run-root digest, with
  canonical workspace root, canonical workflow source base, canonical run
  root, all three path digests, existence/type observations, owner name/role,
  and `scope_disposition` (`supported` or `excluded_with_owner_reason`);
- `external_store_absence`, which defaults to `not_asserted` and may never be
  inferred from the five known roots;
- owner confirmations stating that the list is the owner's complete supported
  scope for this queue, each exclusion is intentional and reason-bound, and
  no scan result or deletion eligibility is attested by the scope record;
- `prepared_by`/`prepared_at`; and
- `owner_adoption` with owner, adopted timestamp, and truthful provenance.

Any excluded slot requires a non-empty owner reason plus one or more
content-addressed evidence pointers. The scope schema contains no scan,
attestation, future-binding, or eligibility fields—null or otherwise. Supported
slots acquire scans only through the later initial-root-binding lifecycle. The
validator does not permit an exclusion merely because it has matches and does
not permit dropping an excluded slot from the five-row scope. Once confirmed,
the scope record/path/digest is immutable for this queue; any genuine scope
change requires a new reviewed scope lifecycle and invalidates all dependent
initial/batch evidence.

### Initial-root binding form

Exact path:
`docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/initial-root-bindings.json`.

Schema `workflow_retirement_initial_root_bindings.v1` contains exactly
`schema_version`, confirmed scope path/digest, query path/digest, `status`,
sorted `supported_roots`, `supported_root_count`, normalized row-set digest,
and `claims_not_made`. Each row binds canonical root identity, exact
`roots/<digest>/initial-scan.json` path/file/content-snapshot/record digests, and
the deterministic per-root attestation path/digest/status. Pending rows require
pending attestations; confirmed rows preserve the scan bytes and require
owner-confirmed attestations. The row set equals every and only supported scope
slot. This record attests bindings, not scope completeness or deletion
eligibility.

### Per-root form

Each deterministic path above whose scope slot is `supported` uses schema
`workflow_retirement_root_scan_attestation.v1` and contains exactly:

- `evidence_status`;
- owner identity/role;
- canonical workspace/source-base/run-root paths and digests;
- scope-record path/digest;
- query path/digest/version/count/path-list digest;
- scan path/digest, start/end timestamps, content snapshot digest,
  timestamp-inclusive normalized record digest, and all match-scoped plus
  store-wide counts;
- `external_store_absence: not_asserted` unless the owner explicitly supplies
  stronger evidence;
- a quiescence object with status, start, end condition, enforcement
  mechanism, and exact permitted mutations;
- owner confirmations that bind only this root/query/scan, distinguish
  batch-scoped projections from whole-query/store-wide disclosures, acknowledge
  that support disposition rather than raw terminality decides blocking, and
  confirm the quiescence statement;
- preparation metadata and owner adoption provenance.

The initial deterministic record binds the whole-query scan. Every batch also
captures both `batches/batch-NN/roots/<digest>/pre-delete-scan.json` and the
post-transaction sibling `post-delete-scan.json`. The gate accepts the fresh
pre scan only with either a fresh owner re-adoption at
`batches/batch-NN/attestations/roots/<digest>.json`, or a machine proof that its
`content_snapshot_sha256` is identical to the adopted initial scan and the
owner-confirmed quiescence window remained unbroken with no unlisted mutation.
The exact scan-file and `normalized_record_sha256` bindings remain required and
normally differ because recapture timestamps differ. Any changed content
snapshot or broken/uncertain window requires re-adoption. An attestation is not
a support waiver.

`quiescence_continuity.v1` binds the adopted and fresh scan paths, exact file
digests, both unequal-or-equal normalized record digests, their required equal
content snapshot digest, and the owner-confirmed unbroken-window evidence. It
rejects a proof that compares file/record digests as the semantic snapshot or
omits either recapture record.

### Per-containing-run support disposition form

For every batch with at least one projected containing run, including batches
1–3 if fresh scans find one, prepare
`attestations/batches/batch-NN/run-support-disposition.json`. Schema
`workflow_retirement_run_support_disposition.v1` binds the batch path digest,
each supported root scan/projection digest, and exactly one row per distinct
containing-run key. A row contains raw status only as evidence, all occurrence
and distinct frame keys, `support_disposition`, `resume_support`,
`consumer_support`, reason, evidence bindings, and owner adoption.

`supported` requires at least one of resume/consumer support to remain
`supported` and always appears in the blocking set. `unsupported_abandoned`
requires both to be `retired`, a substantive reason, evidence that the owner is
retiring future resume/consumer support, and the fixed confirmation that no run
or store mutation was performed or authorized. Missing/extra rows, a supported
row omitted because its status looks terminal, or an abandoned row without
both retirements fails closed. If the owner instead finishes/cancels a run
through its owning system, that is external action, not this record's authority;
the batch must rescan and re-adopt before reconsideration. Direct run-store
deletion or status editing is never authorized.

---

### Task 1: Bootstrap The Generic Broad-Evidence Foundation

**Files:**
- Create: `orchestrator/retirement/__init__.py`
- Create: `orchestrator/retirement/broad_evidence.py`
- Create: `orchestrator/retirement/materialization.py`
- Create: `orchestrator/retirement/source_bindings.py`
- Create: `tests/test_retirement_broad_evidence.py`
- Create: `tests/test_retirement_source_bindings.py`
- Create: `tests/fixtures/retirement_broad_evidence/manifest.v1.json`
- Create: every exact fixture row admitted by that manifest, including the
  workspace-baseline and non-target-source positive/negative families
- Create: `tests/fixtures/retirement_broad_evidence/broad_outcome.v1.json`
- Create: `tests/fixtures/retirement_broad_evidence/broad_failure_payload_normalization.v1.json`
- Create: `tests/fixtures/retirement_broad_evidence/pytest_temp_root_preflight.v1.json`
- Create: `tests/fixtures/retirement_broad_evidence/retirement_materialization_request.v1.json`
- Create: `tests/fixtures/retirement_broad_evidence/query.v1.json`
- Create: `tests/fixtures/retirement_broad_evidence/precommit_control.v1.json`
- Create: `tests/fixtures/retirement_broad_evidence/bootstrap_workspace_baseline.v1.json`
- Create: `tests/fixtures/retirement_broad_evidence/implementation_focused_report.v1.json`
- Create: `tests/fixtures/retirement_broad_evidence/implementation_verification_subject.v1.json`
- Create: `tests/fixtures/retirement_broad_evidence/broad_evidence_bootstrap_subject.v1.json`
- Create: exact baseline, attestation, remediation, skip-change, review, and
  execution-ledger fixture rows named by the manifest
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/execution-ledger.json`
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/implementation-commits/task-01-bootstrap/bootstrap-workspace-baseline.json`
- Create: the exact Task-1 bootstrap paths in the Closed Evidence Layout

- [ ] **Step 1: Write RED closed-contract tests**

Before writing the first Task-1 repository byte, capture the current dirty
workspace in place. Do not clean, stash, restore, clone, or create a worktree.
Create a private external directory with `mktemp -d` beneath
`/tmp/agent-orchestration-yaml-retirement-task1-bootstrap.XXXXXXXX`, require
mode `0700`, and write into it only: current HEAD, raw NUL porcelain-v1 status,
raw NUL `git ls-files --stage` output, SHA-256 of the real index bytes, and a
raw no-dereference archive of the complete worktree excluding only `.git`.
Before the archive, reject any non-regular/non-directory/non-symlink entry
outside `.git`; use GNU tar with sorted names, numeric owner/group zero, mtime
zero, deleted atime/ctime pax keys, one-file-system, and no symlink
dereference. Any capture-command warning/nonzero exit blocks. The archive is
private transient evidence and is never staged or committed.

Run the bootstrap capture exactly from repository root; these are external
writes only:

```bash
bootstrap_root="$(mktemp -d /tmp/agent-orchestration-yaml-retirement-task1-bootstrap.XXXXXXXX)"
chmod 0700 "$bootstrap_root"
test "$(stat -c '%a' "$bootstrap_root")" = 700
repository_root="$(git rev-parse --show-toplevel)"
test -z "$(find "$repository_root" -xdev -path "$repository_root/.git" -prune -o ! \( -type f -o -type d -o -type l \) -print -quit)"
git rev-parse HEAD >"$bootstrap_root/head.txt"
git status --porcelain=v1 -z --untracked-files=all >"$bootstrap_root/status.z"
git ls-files --stage -z >"$bootstrap_root/index-entries.z"
index_path="$(git rev-parse --path-format=absolute --git-path index)"
sha256sum --binary "$index_path" | cut -d ' ' -f 1 >"$bootstrap_root/index.sha256"
tar --create --file="$bootstrap_root/worktree.tar" --format=pax --sort=name \
  --mtime=@0 --owner=0 --group=0 --numeric-owner \
  --pax-option=delete=atime,delete=ctime --one-file-system \
  --exclude='./.git' --exclude='./.git/**' -C "$repository_root" . \
  2>"$bootstrap_root/tar.stderr"
test ! -s "$bootstrap_root/tar.stderr"
sha256sum --binary "$bootstrap_root/worktree.tar" | cut -d ' ' -f 1 \
  >"$bootstrap_root/worktree.tar.sha256"
```

This external capture is the first-write boundary: its status/index streams
define every pre-existing dirty path operand, while the archive binds exact
existence, file type, mode, regular bytes, symlink target bytes, and recursive
directory contents before implementation can touch the repository. Task-1
planned paths must be disjoint from those dirty operands; an intersection
blocks without changing user bytes. The initial implementation slice may write
only the new Task-1 producer/test paths after that disjointness check.

As soon as `source_bindings.py` is runnable, invoke its closed
`adopt-bootstrap-workspace` command with the external capture. It validates the
archive/status/index/HEAD consistency, compares every pre-existing dirty entry
to the live workspace no-follow, and materializes
`bootstrap-workspace-baseline.json` containing the same closed dirty-entry and
semantic-index bindings as `workspace_baseline.v1` plus capture-artifact
digests and `raw_archive_not_persisted=true`. It records hashes/metadata only,
never user content. From that point through the Task-1 commit, run its validator
before and after every mutation, command set, subject/review write, staging, and
commit: baseline dirty entries must remain byte/type/existence-identical, and
all other live changes must equal the exact Task-1 candidate. The bootstrap
baseline is included in the subject and external precommit control and becomes
the durable Task-1 reconstruction authority; delete the private archive only
after post-commit reconstruction succeeds.

```bash
python -m orchestrator.retirement.source_bindings adopt-bootstrap-workspace \
  --repository-root . \
  --bootstrap-root "$bootstrap_root" \
  --out docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/implementation-commits/task-01-bootstrap/bootstrap-workspace-baseline.json
python -m orchestrator.retirement.source_bindings validate-bootstrap-workspace \
  --repository-root . \
  --record docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/implementation-commits/task-01-bootstrap/bootstrap-workspace-baseline.json
```

Test the exact `broad_outcome.v1`, `implementation_focused_report.v1`,
`implementation_verification_subject.v1`,
`broad_evidence_bootstrap_subject.v1`,
`broad_failure_payload_normalization.v1`,
`pytest_temp_root_preflight.v1`,
`broad_known_failure_baseline.v1`,
`broad_failure_baseline_attestation.v1`, and
`broad_failure_remediation.v1`, and `broad_skip_change.v1` shapes plus the shared `review.v1` and
`workflow_retirement_execution_ledger.v1` shapes before
implementing them. Test `query.v1` and its Task-1 materializer plus
`precommit_control.v1`, `bootstrap_workspace_baseline.v1`, and their external
builders/validators in the same RED slice
so Tasks 2–5 have no forward
dependency on Task 6. Cover duplicate
JSON keys, unknown/missing keys, raw-file digest mismatch, invalid exit bytes,
collection failure, JUnit/log/total disagreement, unmappable node IDs, signature
normalization boundaries, new/changed/disappeared/reappeared failures, external
remediation, out-of-scope diffs, incomplete remediation-review pairs, stale
or unreviewed skip-set changes, stale skip predecessors, failure/skip lane crossover,
candidate projections, missing/extra focused roles, argv/selector/environment
drift, nonzero or malformed focused exits, stale focused logs/inputs, candidate
identity disagreement, missing required broad outcomes, and a review that binds
an outcome directly instead of the required subject. Independently reject a
missing/extra candidate-manifest path, a manifest that self-binds its subject or
future reviews, and a staged set other than manifest plus subject, live review
pair, and the two uniquely derived immutable review snapshots.
Positive fixtures cover a six-row baseline, exact
match, and a reviewed strict queue-owned subset. No fixture contains a queue,
repository, module, owner, or failure-specific branch.

For every shared-review fixture, exclusively snapshot each validated live
review into its derived immutable-review path and make the consumer bind that
snapshot. Accept historical validation after a later re-review changes the
live canonical path. Reject a missing, overwritten, renamed,
mutable-path-only, subject-cross-bound, wrong-reviewer, wrong-kind, or
wrong-digest immutable review; reject replacement of a live review unless its
prior bytes already exist and validate at their append-only path. Independently
reject uppercase/non-64-hex in each coordinate and alternate preimages for the
raw subject logical path, exact subject-file bytes, or exact review-file bytes,
including final-newline changes.

Close the normalization boundary with deterministic boundary fixtures, not literal prompt
or incidental prose assertions. Two otherwise identical payloads whose only
difference is the decimal `pytest-<run>` directory under the exact bound
preflight-observed session parent must normalize to the same
signature. Different suffixes after that run directory must remain different.
Patch/observe `_pytest.tmpdir.get_user`—not `_pytest.compat` or
`getpass`—in every branch test. Prove a punctuation-bearing raw username such as `ci.user+gpu` produces and
binds `pytest-of-ci.user+gpu` unchanged, never an underscore-sanitized variant.
Under that binding, `pytest-of-ci_user_gpu` and every other punctuation rewrite
must remain byte-distinct.
Separately prove falsy/missing `get_user()` selects `pytest-of-unknown`, and a
usable raw username whose candidate-root mkdir raises `OSError` also falls back
to `pytest-of-unknown`; a failed fallback mkdir or ownership mismatch rejects.
Near matches at either path-token boundary, another unbound root component,
an unobserved `pytest-of-unknown`, `pytest-X`,
`pytest-12x`, an embedded or relative lookalike, an arbitrary temporary path,
and unrelated decimal values must remain byte-distinct. Independently tamper
the normalization schema version, ordered transforms, bound repository root,
preflight path/digest, pytest/module version, temporary root, observed session
parent, raw component/resolution, rule, and normalized-contract digest and require
both builder and comparator rejection. Run the same fixtures through baseline
construction, later outcome construction, remediation comparison, and final
baseline comparison so no consumer can bypass or reimplement the contract.

In `tests/test_retirement_source_bindings.py`, first test the exact
`workspace_baseline.v1` and `non_target_queue_sources.v1` builders and
validators. Use a temporary Git repository to cover NUL-delimited porcelain
status including spaces, tabs, newlines, renames, and untracked paths; exact
tracked mode/blob/worktree bindings; a protected-row reuse; duplicate/missing/
extra partitions; symlink/special-file rejection; changed byte/mode/blob/size;
and validation both before staging and at a committed HEAD. Require complete
dirty path-operand equality for unstaged, staged, conflicted, deleted, renamed/
copied source+destination, untracked regular, untracked symlink, and directory/
gitlink fixtures. Revalidate no-follow regular bytes, raw symlink-target bytes,
existence, type, mode, index stages, and recursive untracked-directory/gitlink
bindings. The critical deterministic mutation control changes a dirty regular file's bytes
while leaving its porcelain status code and path unchanged and must reject;
parallel controls retarget a dirty symlink, replace file with symlink, recreate
an absent path, and mutate an untracked descendant without changing its top-level
status classification. Reject any baseline dirty path in a staged candidate or
reviewed mutation manifest. Bind the complete semantic index table and exercise
`precommit_control.v1`: preserve an unrelated pre-existing staged entry,
stage only an exact allowed plan delta, validate the reconstructed index/tree
and NUL pathspec, commit only that pathspec, and prove the unrelated entry was
not committed and remains staged. Reject any unrelated staged drift, ambient-
index commit, wildcard/text pathspec, missing/duplicate/changed control trailer,
missing/empty/changed base or final message file, final-message digest/byte
drift, a control digest that includes `final_message_binding` or excludes any
other field, editor/stdin dependence, or same-path wrong
mode/blob. Read the raw commit object with `git cat-file commit`, extract the
message bytes after the first header separator, and require exact forward
derivation and inverse recovery of `message.txt`. Independently reject a
missing separator LF, two or more separator LFs, CRLF, an extra blank line
between trailer rows, a missing/extra final LF, reordered/duplicated trailers,
or hashing/binding any alternative base-message preimage. Delete the external control directory, clone the
repository afresh, and require byte-identical control/pathspec reconstruction
from durable history; reject altered parent/diff/subject/review/baseline/trailer
inputs. Security-only hostile Git-configuration injection is explicitly
deferred and is not a completion gate. Under the bound ordinary configuration,
prove final commit bytes remain exactly unchanged and that the command never
invokes trailer processing. Exercise the exact
module CLI commands from Task 2. The fixture manifest test requires its row set
to equal the directory contents in both directions.

Exercise normalized-digest dispatch directly: `precommit_control.v1` must
exclude exactly `normalized_control_sha256` and `final_message_binding`, while
every other schema must reject any exclusion besides its own normalized digest
field. Reject an unknown schema or schema alias that attempts to select the
exception.

Exercise the Task-1 first-write capture separately. Accept scoped staged,
unstaged, deleted, untracked regular, untracked symlink/directory, rename, and
mode/type/byte cases; adopt their exact no-follow rows, then preserve them
through the Task-1 commit. Reject a Task-1 path intersecting any captured dirty
operand, an archive/status/index mismatch, capture warning, special file, dirty
gitlink unsupported by the bootstrap capture, and any concurrent baseline or
outside-candidate change at every Task-1 mutation/review/staging/commit
boundary. Prove raw user bytes are absent from the committed baseline.

In the Task-1 broad-evidence tests, bootstrap the generic immutable-generation
store, one-shot materialization-transaction API, and the `execution-ledger` kind before creating
the first live ledger. No fixture or test hand-authors the production request.
Require the initial request/output snapshot pair, a contiguous second
generation, immutable prior bytes, and successful historical validation after
the live ledger advances. Reject output-path-only request naming, overwrite,
generation gap/reuse, a generation outside `1..99999999`, any generation
filename not exactly eight digits, an uppercase/non-64-hex or differently
encoded output-path key, stale live bytes, and request/snapshot tamper. Use
competing subprocesses to prove a live advisory-lock holder returns typed busy
to another publisher and that a crashed holder is recoverable only after kernel release and
exact slot validation. Inject crashes immediately after request creation,
immediately before snapshot publication, immediately after snapshot
publication, and immediately before live publication; replay must either
complete the same generation byte-for-byte or fail closed without an alternate
request/snapshot/live file. Task 6
extends this same primitive to the remaining typed kinds; it must not replace or
fork the ledger history mechanism. Also exercise the shared
`materialize_pending` adapter for Task 2's broad-failure-baseline attestation:
owner-shaped request inputs reject and output owner/adoption fields remain
null/false.

- [ ] **Step 2: Implement only the bootstrap surface**

Implement issue-returning closed validators, stable failure-signature
construction, raw-output/JUnit builder, owner-baseline comparison, reviewed
remediation-set accumulation, and reviewed skip-set transition accumulation,
the durable focused-report and implementation-
subject builders/validators, including the immutable-plan ledger validator and
the minimal shared review validator
needed to validate bootstrap, implementation-candidate, baseline, and
remediation pairs, plus the generic append-only immutable-review publisher and
`review_binding.v1` validator. The module receives paths, bindings, and ownership
rows as data; it neither launches pytest nor writes owner fields. Export only
this minimal stable surface from `orchestrator.retirement`.

Implement the pytest-temp-root preflight around the exact bound pytest 8.4.1
automatic-basetemp behavior. Record the raw `get_user()` value and observed
resolution branch/session parent; never synthesize or sanitize a username.
Failure normalization accepts only the preflight-bound parent plus a decimal
`pytest-<run>` component and preserves every suffix byte.

Implement the generic one-shot materialization-transaction API plus exclusive immutable
request/output generation store and
its initial `execution-ledger` and `query` adapters in `materialization.py`, including
snapshot-before-live publication and historical-generation validation. It is
queue-neutral and record-kind-neutral at the storage layer; Task 6 registers
the remaining closed record kinds against the same API. Implement the shared
pending-materialization primitive and register only the Task-2 broad-failure-
baseline attestation adapter here; Task 6 adds the other three adapters and the
explicit CLI without changing semantics.

Implement the source-binding module and its nine exact subcommands:
`capture-workspace-baseline`, `build-non-target-sources`,
`validate-workspace-baseline`, `validate-non-target-sources`,
`materialize-query`, `build-precommit-control`,
`validate-commit-boundary`, `adopt-bootstrap-workspace`, and
`validate-bootstrap-workspace`. The query command accepts only the exact handoff, queue ID,
generation, and output roles, derives the query request through the shared
primitive, materializes it, and prints the canonical receipt; callers cannot
supply paths, counts, or digests. The commit commands build, reconstruct, and
validate the closed external full-index/allowed-delta/pathspec/trailer contract
above and never invoke `git commit`; `validate-commit-boundary --reconstruct`
must work after clone with the local control directory absent. The capture command invokes Git internally with
argv `["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"]`
and parses NUL records without a shell. The build command receives queue IDs
and the protected queue ID as data, selects exact handoff rows, and emits the
closed ten-row record. Workspace capture expands every porcelain path operand
into the closed no-follow dirty-entry snapshot above; validation recomputes that
complete set before comparing. Validation reopens the handoff, workspace baseline,
Git index, and all live paths and returns sorted typed issues with nonzero exit
on any mismatch. Do not implement
store/repository scanners, queue assignment, execution-index, or deletion
lifecycle behavior in this task.

- [ ] **Step 3: Run the bootstrap commit gate**

Use the Task-1 `materialize_transaction` API and ledger adapter to create and validate
the initial `execution-ledger.json` request/output generation; bind the exact immutable approved-
plan digest, advance Task 1 through its final intended pre-commit step, and
freeze its bytes plus every non-evidence candidate byte. Then run the exact
three Task-1 focused roles from the closed command table and
persist their logs/exits plus `focused/report.json`; do not rely on console
output. Run the exact broad xdist command once in tmux, persisting
collect log/exit/node IDs and pytest log/exit/JUnit under
`implementation-commits/task-01-bootstrap/`. This is a raw bootstrap gate, not
a `broad_outcome.v1` baseline: require collection exit zero, readable JUnit,
exactly six mutually consistent failed node IDs, and no collection/runtime
crash. If the observed set is not exactly six, stop and revise the plan rather
than inventing a different baseline. Any later change outside the fixed
execution-evidence root repeats all focused roles and the broad command.
Build `subject.json` under the exact bootstrap schema above. It binds the
Task-1 contract, candidate, ledger, durable focused report and every nested
log/exit, raw broad files, observed totals/failed IDs, and exact candidate path
manifest. It records the raw six-failure observation but makes no baseline or
owner-approval claim.

- [ ] **Step 4: Review and commit the bootstrap**

Obtain specification review followed by code-quality review. Both bind the
exact `subject.json`, which in turn binds the focused results, exact raw broad
files, exact execution-ledger digest, candidate projection, and proof that the
diff contains only the generic bootstrap surface/tests/fixtures/evidence. Any
code, test, focused-evidence, or raw-broad correction invalidates the subject
and both reviews.
Publish both approved reviews to their immutable content-addressed paths and
make the bootstrap consumer bind those snapshots before staging. Build the
external Task-1 control from the adopted bootstrap-workspace binding and complete durable
authority, require the index to equal its expected index, and commit only its
bound NUL pathspec with the exact three trailers. Delete the local control and
reconstruct it from the new commit before accepting HEAD. Commit this bootstrap
once. It does not approve the failures, establish the
owner baseline, or authorize Tasks 3–17.

### Task 2: Characterize, Adopt, And Freeze The Pre-Implementation Boundary

**Files:**
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/workspace-baseline.json`
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/non-target-queue-sources.json`
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/query.json`
- Create: the exact `implementation-baseline/` paths in the Closed Evidence Layout
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/reviews/implementation-baseline-{specification,quality}.json`
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/attestations/pre-implementation/broad-failure-baseline.json`
- Modify: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/execution-ledger.json`

- [ ] **Step 1: Capture repository and protected-path state**

Run this exact bootstrap-safe command; it obtains HEAD and index identity and
uses NUL-delimited porcelain internally, so no path quoting, rename, tab, or
newline is inferred from display text:

```bash
python -m orchestrator.retirement.source_bindings capture-workspace-baseline \
  --repository-root . \
  --protected-path docs/plans/2026-06-20-workflow-step-back-non-progress-recovery-plan.md \
  --protected-path docs/plans/2026-07-01-workflow-audit-tier-fixes.md \
  --protected-path docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/migration_experiment_recommendation_report.md \
  --protected-path state/VERIFIED-ITERATION-DRAIN/iterations/22/checks-log.txt \
  --protected-path tests/test_workflow_non_progress_step_back_demo.py \
  --protected-path workflows/examples/non_progress_step_back_demo.yaml \
  --protected-path workflows/library/prompts/workflow_step_back/diagnose_non_progress.md \
  --out docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/workspace-baseline.json
python -m orchestrator.retirement.source_bindings validate-workspace-baseline \
  --repository-root . \
  --record docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/workspace-baseline.json \
  --allowed-addition docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/workspace-baseline.json
```

Record only results for plan-owned evidence; do not normalize or touch the
protected files.

Persist `workspace-baseline.json` with exact HEAD, sorted complete status rows,
index digest, the exact no-follow content snapshot for every pre-existing dirty
path operand, and the seven named protected-path bindings. Require both-direction
status/path coverage and freeze the dirty path/entry set digests. Its closed
schema distinguishes pre-existing dirty entries from future plan-created entries,
makes no ownership claim over the former, and grants no later mutation authority
over them.

- [ ] **Step 2: Content-bind all ten non-target queue sources**

Select from the frozen handoff exactly the seven
`archive_design_delta_yaml_twin` paths, both port-source paths, and the one
protected-holdout path. Require a disjoint sorted ten-path union and write
`non-target-queue-sources.json` under the closed schema above. For the nine
archive/port sources, bind exact tracked mode/blob OID plus current regular-file
size and worktree SHA-256. For the holdout, bind and reuse its exact protected
row from `workspace-baseline.json`; do not read the holdout as a separately
owned editable source. Build and validate with exactly:

```bash
python -m orchestrator.retirement.source_bindings build-non-target-sources \
  --repository-root . \
  --handoff docs/plans/2026-07-13-procedure-first-reuse-inventory.json \
  --workspace-baseline docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/workspace-baseline.json \
  --tracked-queue-id archive_design_delta_yaml_twin \
  --tracked-queue-id port_verified_iteration \
  --tracked-queue-id port_generic_run_watchdog \
  --protected-queue-id hold_non_progress_step_back \
  --out docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/non-target-queue-sources.json
python -m orchestrator.retirement.source_bindings validate-non-target-sources \
  --repository-root . \
  --record docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/non-target-queue-sources.json
```

Require
their exact bytes/modes/blobs to match the record. Any missing, changed,
untracked, symlinked, or wrongly partitioned source stops Task 2 and routes the
path to its queue owner; this task has no authority to normalize or repair it.

- [ ] **Step 3: Recompute the frozen query from JSON authority**

Use `jq` to select the `delete_non_survivor_estate` paths, require 100 sorted
unique tracked paths, and calculate the newline-delimited digest. Expected:
`sha256:2b4cdaf11ce8570c35cde84987ef73a0a51e985d1d8e3588443a16b8ebac2b63`.

- [ ] **Step 4: Write the content-addressed query record**

Bind the inventory byte digest, handoff schema, queue ID, exact 100 paths,
encoding rule, path-list digest, capture commit, and claims-not-made. The record
does not claim reference or run eligibility. Materialize it through the
Task-1-landed closed adapter, not a Task-6 fixture or hand-authored JSON:

```bash
python -m orchestrator.retirement.source_bindings materialize-query \
  --repository-root . \
  --handoff docs/plans/2026-07-13-procedure-first-reuse-inventory.json \
  --queue-id delete_non_survivor_estate \
  --generation 1 \
  --out docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/query.json
```

Require the canonical receipt to bind the derived immutable request, immutable
query snapshot, live path, and generation. Reopen and validate all three, then
require `path_count=100` and the expected path-list digest above. No Task 6
implementation may replace or reinterpret this generation.

- [ ] **Step 5: Prove the v1 handoff is untouched**

Run exactly:

```bash
pytest -q tests/test_workflow_lisp_procedure_first_migrations.py -k yaml_retirement_handoff
pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py -k yaml_retirement
git diff --exit-code -- docs/plans/2026-07-13-procedure-first-reuse-inventory.json docs/workflow_yaml_estate_triage.md
git diff --cached --exit-code -- docs/plans/2026-07-13-procedure-first-reuse-inventory.json docs/workflow_yaml_estate_triage.md
```

Expected: both selectors pass and the inventory/triage diff is empty.

- [ ] **Step 6: Capture and independently review the exact six-failure baseline**

Run the Generic Production Broad Gate with the `preimplementation` mapping.
Before launching, materialize this task's final execution-ledger bytes and freeze
every path outside the fixed execution-evidence root.
Require `implementation-baseline/collect.exit=0`; use the Task-1 builder to
bind the exact `pytest.exit`, JUnit/log totals, and exactly six failed node IDs
and stable signatures into `known-failure-baseline.json`. Classify every row as
`queue_owned` or `external` with exact path/task evidence. A classification does
not authorize a fix. Obtain specification and quality reviews over the complete
baseline, signature construction, classification, and candidate binding. Any
capture or classification correction invalidates both reviews.

- [ ] **Step 7: Pause for personal owner adoption**

Use the Task-1 one-shot pending-materialization transaction API to create the closed pending
`attestations/pre-implementation/broad-failure-baseline.json` bound to both
approved reviews and all exact six rows. Pause for the owner to personally
confirm the exact baseline and ownership partition and to state that it grants
no authority for out-of-scope repairs. Validate the owner-confirmed replacement;
an agent preparation, standing delegation, or relayed prose does not satisfy
this boundary.

- [ ] **Step 8: Commit the adopted boundary**

Stage only the workspace baseline, immutable non-target-source record, query
record, implementation broad-baseline evidence, both reviews, owner-confirmed
attestation, and the exact execution-ledger update. Revalidate all ten
non-target source bindings with the exact `validate-non-target-sources` command
above and run the protected-path cached guard before committing; repeat that
same command and the protected-byte comparison at HEAD. Tasks 3–17 remain
forbidden until this commit exists. Before every Tasks 3–5 commit, run that same
validator immediately before staging and again at HEAD and bind its persistent
log/exit as an additional required focused role; Task 6's unified CLI delegates
to this already-reviewed implementation rather than superseding it.

### Task 3: Extract Stable Generic State-Store Traversal

**Files:**
- Modify: `orchestrator/retirement/__init__.py`
- Create: `orchestrator/retirement/state_store.py`
- Modify: `orchestrator/workflow_lisp/procedure_identity_retirement.py`
- Create: `tests/test_retirement_state_store.py`
- Modify: `tests/test_workflow_lisp_procedure_identity_retirement.py`
- Create: the exact `implementation-commits/task-03/` paths in the Closed Evidence Layout
- Modify: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/execution-ledger.json`

- [ ] **Step 1: Write RED equivalence and generic-consumer tests**

Cover deterministic ordering/digest, duplicate JSON-key rejection, unreadable
or malformed supported files, `O_NOFOLLOW`, symlink root/component rejection,
file and complete-tree race rejection, JSON/JSONL, stable top-level run
association, and preservation of all current procedure scanner outputs.

- [ ] **Step 2: Run collection and the RED selectors**

```bash
pytest --collect-only -q tests/test_retirement_state_store.py tests/test_workflow_lisp_procedure_identity_retirement.py
pytest -q tests/test_retirement_state_store.py tests/test_workflow_lisp_procedure_identity_retirement.py -k 'generic_store or compatibility'
```

Expected: collection succeeds and new imports/behavior fail before extraction.

- [ ] **Step 3: Move only stable traversal/read primitives**

Move the complete-tree snapshot, supported-file enumeration, stable byte read,
JSON/JSONL object load, canonical digest, and top-level-run association into the
generic module. Keep procedure-specific field catalogs, query version, result
schema, and error compatibility in the existing wrapper.

- [ ] **Step 4: Prove byte-for-byte wrapper compatibility**

Existing procedure fixtures must produce exactly the same normalized result and
digest. Any error-code change is a regression.

- [ ] **Step 5: Run the full owning module and broad candidate gate**

Run the exact three Task-3 focused roles from the closed command table, persist
their logs/exits under `implementation-commits/task-03/focused/`, and build the
closed passing `focused/report.json`. Then run the Generic Production Broad
Gate with the Task-3 mapping. Require
collection exit zero and the exact owner-baseline comparison; any new, changed,
or unexplained missing failure blocks.

- [ ] **Step 6: Review and commit**

Build `implementation-commits/task-03/subject.json` under
`implementation_verification_subject.v1`, binding the exact focused report,
required `outcome.json`, task contract, candidate/ledger identity, and candidate
path manifest. Obtain specification review before code-quality review; both
bind only that subject. Fix and repeat the focused and broad gates, rebuild the
subject, and repeat both reviews after any production or evidence correction.
Commit production and its durable focused/broad evidence only after both
approve.

### Task 4: Add Generic `workflow_file` Top-Level And Nested Consumer Scanning

**Files:**
- Modify: `orchestrator/retirement/state_store.py`
- Modify: `orchestrator/retirement/__init__.py`
- Modify: `tests/test_retirement_state_store.py`
- Create: the exact `implementation-commits/task-04/` paths in the Closed Evidence Layout
- Modify: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/execution-ledger.json`

- [ ] **Step 1: Write both-direction RED tests**

Add `scan_workflow_file_consumers(run_root, workflow_files, workspace_root,
workflow_source_base, query_version)` tests for the exact identity join
`workspace_root / repository_relative_target_path`, workspace-relative and
absolute observed values, source-base allowed-subtree enforcement, top-level
`workflow_file`, nested embedded and file call-frame `workflow_file`, several
occurrences counted once per distinct containing run/frame, raw terminal/
nonterminal/unknown status disclosure, unrelated store totals, and stable
occurrence/run/frame keys.

- [ ] **Step 2: Add negative controls**

Reject basename-only store values, substring matches, path traversal, empty or
duplicate query values, unsupported query versions, workspace escape,
source-base-subtree escape, a source base other than `workspace_root/workflows`,
a run root other than `workspace_root/.orchestrate/runs`, absolute paths outside
the base, a `workflows/workflows/...` double-prefix candidate, a nested match
without a readable containing top-level state, duplicate/ambiguous run IDs,
ambiguous target resolution, symlink/race changes, and ambiguous root
association. Prove same-frame occurrences dedupe while embedded/file identities
with the same declared ID remain distinct.

- [ ] **Step 3: Implement the minimal exact-field scanner**

Use query version `workflow-file-store-query.v1`. The normalized result exposes
the complete occurrence rows defined above; query identity/count/digest;
distinct matching run/frame disclosure counts; store terminal/nonterminal
totals; sorted scanned files; `content_snapshot_sha256`; and the timestamp-
inclusive `normalized_record_sha256`. It performs no support or batch
eligibility judgment. No queue or family knowledge belongs in this function.

- [ ] **Step 4: Verify focused and compatibility suites**

Run the exact three Task-4 focused roles from the closed command table, persist
their logs/exits under `implementation-commits/task-04/focused/`, and require a
valid passing `focused/report.json`.

- [ ] **Step 5: Run the broad candidate gate**

Run the Generic Production Broad Gate with the Task-4 mapping. Require
collection exit zero and the exact owner-baseline comparison.

- [ ] **Step 6: Review and commit**

Reviewers must explicitly confirm that whole-query/store-wide counts never gate
a batch, the workspace-relative identity/source-base constraint cannot
double-prefix `workflows/`, path-triple ambiguity fails closed, and missing/
unreadable containing state cannot silently become eligible. First build
`implementation-commits/task-04/subject.json` under
`implementation_verification_subject.v1`, binding the exact focused report,
required `outcome.json`, task contract, candidate/ledger identity, and candidate
path manifest. Both reviews bind only that subject; rerun focused and broad,
rebuild the subject, and repeat both reviews after any production or evidence
change. Commit after both reviews.

### Task 5: Add The Generic Repository Reference And Import-Graph Scanner

**Files:**
- Create: `orchestrator/retirement/repository.py`
- Modify: `orchestrator/retirement/__init__.py`
- Create: `tests/test_retirement_repository.py`
- Create: the exact `implementation-commits/task-05/` paths in the Closed Evidence Layout
- Modify: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/execution-ledger.json`

- [ ] **Step 1: Write RED repository fixtures**

Create temporary Git repositories proving exact-path and basename capture in
tracked files and working-tree-only content, occurrence-level byte ranges and
referrer digests, multiple differently classified occurrences in one pair,
raw-byte matches in binary and non-UTF-8 files, unreadable/symlink failure,
deterministic ordering, NUL-delimited candidate paths, and complete-tree or
index change rejection. Reproduce the current checkout's 21 tracked files
classified by the audit as binary/non-UTF-8 candidates and prove they are
hashed/scanned without decoding or silent omission.

- [ ] **Step 2: Write RED import-graph fixtures**

Cover `.yaml` and `.yml`, dictionary-shaped imports accepted by
`WorkflowLoader._load_imports`, explicit rejection of list-shaped imports with
`'imports' must be a dictionary`, relative resolution, missing import, path
escape, duplicate alias, cycle, importer-before-imported ordering, an external
surviving importer, and same-batch importer/imported acceptance. The graph
scanner must not accept a shape the runtime loader rejects.

- [ ] **Step 3: Implement normalized scanners**

`scan_repository_references(...)` obtains candidates with NUL-delimited Git
plumbing, snapshots each regular file as bytes, and performs byte-pattern
matching without decoding file content. UTF-8 query paths/basenames are encoded
once; an occurrence stores `matched_bytes_sha256` and base64 matched bytes, not
a decoded string. Binary/NUL/non-UTF-8 bytes are ordinary input. An unreadable
candidate, unsafe Git path, special file, symlink, or stable-read race fails the
entire scan; only a raw-byte non-match is non-evidence.

The scanner emits unclassified occurrence facts only, each with an
`occurrence_id`, target, referrer, referrer digest, byte span, matched-byte
fields, and match basis. `occurrence_id` is the SHA-256 of canonical JSON over
exactly target, referrer, referrer byte digest, byte-span start/end, match
basis, and matched-bytes digest. The scan stores
`occurrence_count` and `normalized_occurrence_set_sha256` over the sorted full
rows. It does not guess active versus historical from directory names.
`scan_authored_import_graph(...)` emits exact nodes/edges, structural pointers,
topological facts, and digest. Both accept their target set as data and contain
no YAML-retirement names.

Classification validation requires a disjoint exact one-to-one join from every
repository occurrence row to one disposition row by `occurrence_id`. The
disposition record binds the scan's exact `occurrence_count` and
`normalized_occurrence_set_sha256` and stores its own equal classified count
and `normalized_classified_occurrence_set_sha256`, recomputed from the complete
scan rows selected by its disposition IDs. That digest must equal the scan's
full normalized occurrence-set digest. Missing, extra, duplicate, stale, or
digest-mismatched rows fail closed; target/referrer-pair coverage is never a
substitute.

The sole non-occurrence exception is an explicitly typed
`compatibility_importer_fact` emitted by `scan_authored_import_graph` when a
dictionary-shaped import accepted by the loader identifies a decoded target/
referrer and structural pointer but YAML quoting/escaping prevents a stable raw
target-path byte range. Its closed loader-form enum has the single value
`yaml_mapping_import_decoded_path`; list imports are rejected, not converted to
facts. Each such fact binds
the importer digest, loader-form enum, structural pointer, target, referrer,
and `compatibility_fact_id`; it must be enumerated in a separately counted and
normalized compatibility-fact set. It does not erase, merge, or replace any
ordinary occurrence row. If multiple compatibility facts collapse to the same
target/referrer pair, or coexist with ordinary rows for that pair, validation
uses fail-closed precedence: any fact/occurrence classified as active makes the
pair active for deletion gating, and conflicting retained/active dispositions
cannot make it eligible. No other scanner limitation permits pair-level
classification.

Every repository scan is versioned exactly `repository_reference_scan.v1`,
binds the exact query
path set/count/digest, capture commit/full index-identity object,
`index_baseline_binding`, nonexcluded-index projection count/digest, working-tree candidate manifest count/digest, candidate
byte digests, scanner version, start/end
timestamps, occurrence count/digest, compatibility-fact count/digest,
`content_snapshot_sha256`, timestamp-inclusive `normalized_record_sha256`, and
a closed exclusion object. Before reading, the scanner freezes a complete
candidate manifest; after reading, it proves every nonexcluded candidate and
the nonexcluded Git-index projection are unchanged. Outside the closed batch
worktree-only deletion window, the full index identity is retained as
disclosure and does not make later exact evidence-root-only commits stale.
Inside Steps 7–10 it is the exact post-Step-6 pre-deletion baseline described
above; no
commit or index mutation is permitted there. The only scanner-owned exclusion is the exact
execution-evidence root passed as data. That root must be a reviewed repository-
relative directory, may contain only generated retirement evidence, and may
not be an ancestor of any queried target, production source, test, routing doc,
or protected path. Every excluded file is still listed with path/digest/reason
`scanner_owned_evidence`; unknown exclusions fail. The scanner writes outputs
only after the immutable candidate snapshot is complete. Thus evidence strings
cannot self-match, while any target/referrer outside the one bound output root
remains in scope.

`index_baseline_binding` is null for every assignment, batch-pre, repair, and
final scan outside a batch's Steps-7-through-10 deletion window. A batch-post
scan requires the exact `pre-deletion-index-baseline.json` path/digest/schema and
must recompute all four equal identity components; any other nullability or a
baseline from another batch fails closed.

The closed full `index_identity` object contains the exact SHA-256 of the actual
Git index file bytes, the exact `git write-tree` OID, SHA-256 of the canonical
NUL-delimited bytes from `git ls-files --stage -z`, and SHA-256 plus byte count
of `git diff --cached --binary`. Capture these with `GIT_OPTIONAL_LOCKS=0` and
prove the raw index-file digest is unchanged before and after all read-only Git
queries. These four values must remain exactly equal to the batch pre-delete
scan from the first worktree deletion through post scan, subject construction,
both post-edit reviews, and the last pre-staging check. The normalized
nonexcluded index projection remains useful for scanner-evidence exclusions,
but it does not replace or relax this exact index-identity invariant.

The closed scan shape always contains both `retired_query`/
`retired_occurrences` and `replacement_query`/`replacement_occurrences`.
Assignment and batch-pre scans bind an empty replacement query with zero rows
and its canonical empty-set digest; batch-post scans bind the exact union of
pre-disposition replacement expectations. This preserves one schema without
allowing replacement rows to leak into retired-target coverage.

Post scans additionally require `tracked_deletion_tombstones.v1`. Its top level
contains exactly `schema_version`, `batch_binding`, `pre_scan_binding`,
`pre_deletion_index_baseline_binding`, `pre_index_binding`, `tombstones`, `tombstone_count`,
`normalized_tombstone_set_sha256`, and `claims_not_made`. Each sorted row
contains exactly the assigned `target_path`, batch path-list digest, pre-index
mode/blob OID, pre-worktree byte digest/size, observed post-worktree state
`absent`, and closed reason `tracked_batch_target_deleted`. The tombstone set
must equal the batch's exact assigned target set in both directions; every row
must have existed as the exact bound regular tracked blob in the pre scan and
must have the same entry/mode/blob in the post-Step-6 pre-deletion baseline, and
must be absent from the worktree only after the deletion transaction. The post
scanner accepts `ENOENT` for those rows while the pre index still exposes the
bound blobs. Any other missing tracked candidate, extra/missing tombstone,
wrong batch, changed index entry, preexisting absence, directory/symlink, or
wrong blob fails the whole scan. Tombstones authorize evidence capture only;
they neither stage deletion nor waive reference reconciliation.

`historical_reference_retained` may survive only under immutable plan/evidence/
report/history roots and never in production code, scripts, routing, current
guidance, tests, or fixtures. `temporary_yaml_frontend_test` may survive only in
an enumerated test/fixture allowlist, must prove rejection/characterization
rather than launch support, and may not open or require the deleted repository
target.

Every execution reference-disposition row selects exactly one classification
from the immutable handoff-v1 allowed enum and freezes that value for its exact
scan/occurrence generation. It does not bind a nonexistent captured v1 row.
When the selected classification is `delete_with_source`, the execution row
additionally requires exactly one closed postcondition refinement:
`delete_referrer_with_source` or `remove_exact_occurrence`. The former requires
the referrer deleted in the same or an earlier batch. The latter removes an old
reference while retaining its referrer without adding a replacement reference.
Its pre row binds the exact old occurrence ID, target, retained referrer,
pre-referrer digest/size, span, matched-bytes digest, and postcondition
`old_occurrence_absent_referrer_present`. Post reconciliation requires that
exact old occurrence absent from the retired channel, the same regular tracked
referrer present with its exact post byte digest/size, no tombstone for that
referrer, and no replacement binding. Deleting or losing the referrer, leaving
the occurrence, matching only a different span, or creating an unmapped new old
reference fails. Every other pre/post occurrence in the edited referrer remains
independently dispositioned and reconciled; one removed span cannot waive the
rest of the file. No other selected classification may carry either execution
refinement, and the refinement is never serialized into or projected back onto
the frozen handoff-v1 enum or empty capture record set.

`reroute_to_orc` has a closed two-record contract. Its pre-disposition row
binds the old `occurrence_id`, exact old target/referrer/span/referrer digest,
and a `replacement_expectation` containing exactly repository-relative `.orc`
path, exact referrer path, required match basis `exact_path_bytes`, and expected
match count `1`. `exact_path_bytes` means the full UTF-8 repository-relative
path bytes with both boundaries either file boundary or a byte outside the
closed path-token alphabet `[A-Za-z0-9._/-]`; a substring inside a longer path
does not match. The post scanner receives two distinct queries: retired YAML
targets populate `retired_occurrences`, while the union of declared replacement
paths populates `replacement_occurrences`; the channels have separate counts
and normalized digests and cannot satisfy each other. The post-reconciliation
row binds the pre disposition and post-scan digests, proves the old occurrence
is absent from the retired channel, and binds exactly one replacement row with
replacement path, referrer, byte-span start/end, post-referrer byte digest,
matched-bytes digest, `replacement_occurrence_id`, and replacement-channel
digest. Zero, duplicate, basename-only, wrong-referrer, stale-digest, or
ambiguous replacement matches fail. Other disposition kinds likewise map each
pre occurrence to its exact permitted post state, and any unmapped new retired-
target occurrence fails closed.

- [ ] **Step 4: Reproduce the characterization**

Against the unchanged checkout expect 51 import edges, acyclic=true, no
surviving importer, and approximately the audited 1,097/211 reference shape.
Any count drift must be explained and reviewed; the deletion gate binds the
fresh occurrence and compatibility-fact counts/digests, not the approximate
planning pair count.

The Task-7 top-level scan/classification freezes assignment-time
characterization only. Before each deletion batch, run a new content-addressed
pre scan against the execution index's exact current `active_paths`, then
classify every occurrence and compatibility fact from that exact scan version.
Because `occurrence_id` includes the referrer byte digest, no disposition from
the assignment scan or an earlier batch may be copied forward. The gate
projects the freshly classified full active-path scan to the batch target set.
After edits, scan the same pre-scan retired-target query plus the declared
replacement query and build the closed reconciliation. It must account for
every pre occurrence, every post retired occurrence, and every post replacement
occurrence in both directions, plus every pre compatibility fact and its exact
post absence/retained state. The per-batch execution-index row binds all six
files and their query/count/digest/version fields; stale scan/disposition
combinations fail before review.

Batch-reference binding nullability is closed by lifecycle: `pending` has all
six null; `blocked` or `eligible` requires the pre scan plus both occurrence and
compatibility-fact dispositions and keeps tombstone plus both post bindings
null; `committed_pending_binding` and `closed` require all six. No mixed post
state or post binding before the deletion
transaction is legal.

Batch review bindings are equally closed: `pending|blocked` has no consuming
review bindings; `eligible` requires exactly the eligibility pair;
`committed_pending_binding` requires eligibility plus post-edit pairs; `closed`
requires all three pairs. The six deterministic files may exist only at or
after their named review stage, and the index/event digest fields must match
their exact bytes.

- [ ] **Step 5: Verify and run the broad candidate gate**

Run the exact three Task-5 focused roles from the closed command table, persist
their logs/exits under `implementation-commits/task-05/focused/`, and build the
closed passing `focused/report.json`. Then run the Generic Production Broad Gate with the Task-5 mapping and
require collection exit zero and the exact owner-baseline comparison.

- [ ] **Step 6: Review and commit**

Build `implementation-commits/task-05/subject.json` under
`implementation_verification_subject.v1`, binding the exact focused report,
required `outcome.json`, task contract, candidate/ledger identity, and candidate
path manifest. Both reviews bind only that subject. Any production or evidence
correction invalidates the focused report, broad outcome, subject, and both
reviews. Commit only the reviewed candidate plus its durable evidence.

### Task 6: Implement Closed Evidence, Execution-Index, And Batch Validators

**Files:**
- Create: `orchestrator/retirement/evidence.py`
- Modify: `orchestrator/retirement/__init__.py`
- Create: `tests/test_retirement_evidence.py`
- Create: `tests/fixtures/retirement_evidence/manifest.v1.json`
- Create: every exact fixture row admitted by that manifest, including one
  `retirement_materialization_request.v1` positive and tamper family per
  materializer kind
- Create: `scripts/build_retirement_execution_index.py`
- Create: the exact Task-6 implementation paths in the Closed Evidence Layout
- Modify: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/execution-ledger.json`

- [ ] **Step 1: Write RED closed-schema tests**

Materialize every canonical fixture listed above except the broad-evidence,
source-binding, query, external precommit-control, and shared-review families
already landed by Task 1; import and exercise those validators without copying
their schemas or fixtures. For repository scan, immutable
non-target queue sources, occurrence and compatibility-fact
dispositions/reconciliation, import graph,
category input, batch assignment, execution-index and initial-root-binding
lifecycles, root scope, root scan/adoption, run support disposition, batch
projection/gate, focused checks, optional smoke, broad-outcome bindings and
comparisons, prospective
assignment/eligibility/deletion/repair/closeout transitions, owner-lifecycle
review subjects, per-batch pending/confirmed owner-lifecycle subjects and
post-review consumers, repair subjects/events, final repository scan, final
validator/focused/end-to-end reports and subject, deletion events,
and reviews, test missing/extra nested keys,
duplicate JSON keys, wrong enum/version, illegal pending/confirmed/null
combinations, wrong digest exclusion, stale path/digest/count, unsafe path,
symlink, timestamp inversion, missing persistent logs/exits/reports, and
referenced-file mutation.

For every mutable materializer family, require generation-addressed immutable
requests and output snapshots in both directions. Advance a ledger, execution
index, batch projection, and generated Markdown projection through at least
three generations; then validate the first and second reviewed subjects using
only their bound historical generations while the live singleton holds the
third. Independently reject an output-path-only request name, overwritten prior
request/snapshot, missing generation, gap/reuse, wrong request digest, wrong
snapshot suffix or byte digest, stale live singleton at publication, historical
binding silently redirected to the live path, and a subject that omits either
the request or output snapshot. A live singleton may advance; no previously
reviewed exact binding may become unverifiable.

Exercise each one-shot `materialize` transaction through its real CLI: accept
each closed kind's exact input/parameter grammar and derive all request,
snapshot, and live-output bytes under one held lock. Reject `prepare-request`,
`--request`, caller-supplied digest/path/owner fields,
unknown/duplicate input roles or parameters, wrong scalar/path/enum/list types,
self-digest mismatch, path derivation mismatch, and noncanonical request bytes
at any path. Use concurrent subprocesses to prove
identical transactions are idempotent and return one complete receipt, while different
transactions for the same output/generation yield exactly one winner, no alternate or successful partial
alternate request, and a deterministic typed loser error. Hold the real
nonblocking advisory lock in one subprocess and prove another receives typed
busy without publication; then terminate holders at the request-created,
snapshot-not-yet-published, snapshot-published, and live-not-yet-published
boundaries and prove exact replay after kernel release. Exercise the exact
eight-digit generation range and exact lowercase-hex hash of canonical output-
path UTF-8 bytes with path characters that distinguish raw bytes from alternate
JSON, prefix, newline, separator, and Unicode-normalized encodings.

Exercise immutable review history in both directions for every lifecycle:
publish each validated review to its derived append-only snapshot before a
consumer accepts it, advance the same canonical live path through a re-review,
and reopen the prior accepted review through only its immutable binding. Reject
a consumer with only a live path/digest, snapshot overwrite/removal, incorrect
subject-path or subject-byte directory, wrong kind/reviewer/result, cross-pair
snapshot, or replacement before prior snapshot preservation.
For all three immutable-review hash coordinates, require exactly lowercase
64-hex and recompute the exact preimages defined above. Independently reject
uppercase hex, shortened/extended hex, hashing JSON-escaped path text, hashing
normalized subject JSON instead of exact subject file bytes, hashing review
content with its trailing newline removed/added, or using the subject digest as
the review-file digest.

Exercise `materialize-pending` for all four and only the four owner-bound kinds.
Require null owner identity, owner-adoption, owner-only provenance, and
confirmation-timestamp values plus false confirmations, while retaining only
the schema-required mechanically truthful `prepared_by`/`prepared_at` fields.
Reject every owner-shaped input at
one-shot argument validation, each pending kind sent through ordinary `materialize`,
every ordinary kind sent through `materialize-pending`, and any attempt to
construct confirmed bytes. Repeat live-contention and all four crash-prefix
tests through the pending command and require the same single-lock behavior.
Confirmed owner replacements remain validate-only.

For `non_target_queue_sources.v1`, prove exact ten-row cardinality and the
seven-archive/two-port/one-holdout partition. Independently reject a changed
byte, mode, blob OID, size, path, queue ID, binding source, protected-row
binding, missing/extra/duplicate row, symlink, and an index or subject that
rebinds the record after Task 2. Accept the holdout only through its exact
workspace protected binding and accept each of the other nine only through its
own exact tracked source binding.

For both scan schemas, prove a recapture with identical semantic content but
different timestamps has equal `content_snapshot_sha256` and unequal
`normalized_record_sha256`/file bytes. Independently change a file byte,
occurrence/status row, query, canonical root, or accepted-absence/tombstone row
and require the content snapshot to change. Reject either digest if recomputed
with the other digest's inclusion/exclusion projection.
For repository scans, require null `index_baseline_binding` outside a batch post
scan and the exact same-batch post-Step-6 baseline plus four-part equality for a
batch post scan; reject missing, extra, cross-batch, stale, or unequal bindings.

- [ ] **Step 2: Write exact reconciliation tests**

Require seven batch sizes `15/15/10/15/15/15/15`, disjoint union exactly 100,
every import edge ordered importer-before-imported or same batch, no surviving
importer, exact prerequisite chain, and `active_paths + path-owning history ==
frozen queue` in both directions at absent, committed-pending-binding, and closed
states. Reject an extra, missing, duplicated, doubly-owned, reordered, or
post-review reassigned path; reject a closure event without exactly one prior
pending event, a pending event that tries to self-bind its commit, a pending
event created before two approved reviews, a post-edit review that binds the
pending event, or a pending event whose subject/review digests differ from the
reviewed bytes.

Exercise review lifecycles in both directions: exact implementation-failure/
category/assignment/baseline/root-scope-pending/root-scope-confirmed/
initial-root-pending/initial-root-confirmed/final top-level pairs produce
cardinalities 2/4/6/8/10/12/14/16/18 and exact batch
eligibility/post-edit/closure pairs produce 2/4/6. Reject a missing pair member,
extra or alternate filename, wrong kind-to-filename mapping, duplicate reviewer,
wrong subject path/digest/kind, rejected result, eligibility without its pair,
pending event without the post-edit pair, closure event without the closure
pair, baseline approval without its pair, and closeout without the final pair.
Independently require each batch owner-lifecycle directory to progress
`0 -> 4 -> 8`, with each post-review consumer binding only its matching subject/
pair, the confirmed consumer preserving the pending consumer, and the confirmed
commit preceding repository capture. Reject a pending or confirmed index update,
continuity/adoption commit, support-disposition commit, or prospective external
projection commit without its already-approved subject/pair/consumer chain.

Prove the complete assignment chain in both directions: accept only an
assignment whose repository scan, occurrence dispositions, compatibility-fact
dispositions, distinct pre-transition and post-routing import graphs, category
input, and two category reviews match exact
paths/bytes/counts/set digests, and an execution index that consumes that exact
assignment. Independently tamper, omit, add, or cross-bind every input and
require rejection. Accept unequal graph file/normalized digests only when the
semantic graph digests are equal; reject an unequal semantic digest even when
membership happens to remain the same, an overwritten pre-transition path, or
a mixed-generation transition/assignment. Prove root scope contains no scan bindings and remains
immutable while the separate initial-root-binding lifecycle alone moves
absent-to-pending-to-owner-confirmed; reject skipped states, partial supported
coverage, excluded-root rows, changed initial scan, or any attempt to update
scope during scan adoption.

Prove the non-target exclusion boundary in both directions: every valid index,
prospective batch transition, pre-delete gate, deletion subject,
candidate-to-stage manifest, closure validation, and final subject binds the same
Task-2 record and passes a fresh live check of all ten paths. Independently
change each of the nine archive/port sources and the protected holdout; require
every lifecycle gate to reject it. Prove no reference disposition,
compatibility-fact disposition, tombstone, history event, broad remediation,
or evidence-only closure can authorize, conceal, or rebaseline that change.

Apply the same lifecycle proof to the complete workspace baseline: every index,
transition, gate, candidate-to-stage manifest, subject, review, repair/closure/
final candidate, staged set, and HEAD validation binds the same baseline and a
fresh all-dirty-entry result. Independently preserve status code/path while
changing a dirty regular file's bytes and require every boundary to reject it;
also reject existence, type, mode, index-stage, symlink-target, untracked-tree,
or gitlink drift, a missing/extra baseline row, a staged baseline path, and a
transaction that claims an in-scope disposition waives dirty-content ownership.
For every commit, reconstruct the complete index from the prior semantic index
and the exact external `precommit_control.v1`; require exact table/tree equality,
exact trailer binding, and a byte-bound NUL pathspec containing exactly the
allowed delta.
Accept a fixture with an unrelated pre-existing staged row only when it remains
unchanged and `git commit --only --pathspec-from-file ... --pathspec-file-nul`
excludes it from the commit under `git --literal-pathspecs`. Reject ambient-index commit, a new/changed/removed
unrelated staged row, an extra/missing/wrong-mode/blob allowed row, a text/newline
pathspec, a pathspec digest mismatch, a baseline-dirty allowed row, or a post-
commit tree that includes the preserved unrelated staged change. Remove the
local control/pathspec and prove a fresh clone reconstructs byte-identical
bytes and validates the trailer chain; reject any reliance on `.git` files
surviving the commit. Repeat the raw `git cat-file commit` forward/inverse test
and every missing/extra-separator or alternative-message-preimage negative
control for a later workspace-baseline-bound commit, not only Task 1. Repeat
under the bound ordinary Git configuration and reject any final-message byte/
digest drift. Hostile configuration injection remains explicitly deferred and
is not a completion gate.

Prove mutation ordering in both directions: a prospective transition renders
the exact external projection before the final post scan and the later valid
pending index renders the same bytes; any nonexcluded projection/routing byte
changed after that scan invalidates the subject/reviews. Accept closure changes
only under the exact execution-evidence root; reject an external projection,
routing doc/test, workflow, source, or arbitrary repository path in commit B.
Prove the explicit recovery is a new final post scan, subject, and two reviews,
not an expanded exclusion or closure waiver.

Prove the post-commit repair chain in both directions. Accept closure directly
after commit A and after one or multiple monotonically numbered reviewed repair
commits. Require each repair event to be non-owning, bind the prior substantive
commit/event and immutable repair subject/review pair, preserve the exact
active/path-owning history partition, and leave all ten non-target sources and
supported run-root snapshots unchanged. Require the repair repository scan and
reconciliation to cover predecessor-allowed historical/test and replacement
occurrences in both directions. Reject a missing/duplicate/reordered
repair number, an empty or unreviewed repair, a repair event that self-binds its
containing commit, a second path-owning event, an intervening unbound commit, a
closure that skips the latest repair, or `close-prior-deletion` invoked when
HEAD is not the chain's immediate substantive predecessor.

Exercise the immutable-plan ledger in both directions: accept only the exact
approved plan digest, one in-progress task, contiguous step counts, and reviewed
pre-gate transitions; reject a checkbox/status edit to this plan, stale ledger
binding, skipped task/step, post-review ledger change, or task completion before
its final reviewed commit.

Exercise initial execution-index provenance in both directions. Capture HEAD
immediately before generation-1 preparation, bind that exact initial ledger
request/snapshot and reviewed assignment in `initial_index_base`, commit the
index afterward, and accept every later generation only when both immutable
fields and the top-level workspace-baseline path/digest/schema/count/set-digest
coordinates are byte-identical. Reject the future containing commit substituted for
`created_at_commit`, a missing/non-ancestor capture, capture after request or
materialization, a different initial ledger/base/assignment digest, a later
generation that refreshes either field or the workspace binding, and a validator that compares the field
to the current index-containing commit.

Exercise skip-set lineage in both directions: require Task-7 baseline as the
first batch predecessor, exact equality when the optional triple is absent,
and one contiguous record/two-review append for every changed set. Reject a
missing/extra/reordered prefix row, stale predecessor digest, unexplained
added/removed ID, failure-node crossover, or an index/outcome that advances the
skip set without all three exact files.

For assignment and eligibility, accept a repository scan only when its capture
follows the last prospective nonexcluded projection/routing commit. Reject a
scan followed by any nonexcluded owner/index projection, routing, source, or
test commit. Accept later exact evidence-root-only review/index bindings using
the unchanged nonexcluded-index projection; reject an expanded exclusion or a
full-index digest treated as the gating freshness digest.

Apply the same both-direction proof to final closeout. Accept an exact
prospective closeout transition whose four external files are materialized
before the final repository scan and remain byte-identical through commit;
after final evidence starts, accept only the enumerated evidence-root
scan/report/subject/review/index bindings. Reject a late program, docs-index,
live-projection, or routing-test change; an extra/missing candidate row; a final
subject whose pre/post bytes differ; a consuming index that renders different
external bytes; or a staged path/digest set unequal to the reviewed subject and
closed post-review consuming-path manifest. The prospective closeout transition
remains byte-identical with null review digests; only the index consumes the
eventual review digests.

- [ ] **Step 3: Write batch-gate direction tests**

Positive: all exact occurrences classified, every supported root freshly bound,
each batch projection recomputed from its whole-query scan, every projected run
closed as `unsupported_abandoned`, valid blobs, dependencies complete, and
protected guard clean. Negative: independently tamper each condition; prove an
unrelated whole-query/store-wide match does not gate this batch; prove one
batch-path-scoped supported run or distinct frame does gate; prove raw terminal
or failed labels do not substitute for support disposition; and prove an
owner-confirmed scan does not waive an undispositioned/supported run.

For references, prove both directions against exact counts and normalized set
digests: two occurrences in one target/referrer pair require two disposition
rows, while one extra/missing/stale disposition fails. Add a separate legacy
loader fixture proving an explicitly identified compatibility-importer fact is
counted independently and that active wins under the fail-closed precedence;
prove an ordinary textual occurrence can never enter that fallback lane.

Add pre/post repository tests proving a changed referrer digest creates fresh
occurrence IDs, stale prior-batch dispositions are rejected, the scanner-owned
evidence exclusion is exact and cannot hide another subtree, an evidence output
does not self-match, every raw-byte candidate remains in the manifest, and the
same pre query is reconciled post-edit. For `reroute_to_orc`, prove exact path,
referrer, span, post-referrer digest, matched-byte digest, and replacement ID
pass; independently tamper each, omit the replacement, duplicate it, or leave
the retired occurrence and require failure.

Prove the frozen handoff-v1 fixture, empty capture record set, and enum remain
byte-for-byte unchanged and reject `remove_exact_occurrence` as a top-level
classification. Require each fresh execution occurrence to select and freeze
one allowed enum value without a v1-row binding. Under a per-scan selected
`delete_with_source` classification, prove its nested
`remove_exact_occurrence` execution refinement passes when the exact old span is
absent and the retained referrer has its bound post digest. Reject the nested
refinement under any other parent, reject a missing or unknown refinement under
`delete_with_source`, and reject any attempt to rewrite the parent or frozen v1
row. Prove both directions also fail when the old span remains, a different
occurrence is removed, the referrer is deleted/tombstoned, the post digest/size
is stale, a replacement is smuggled into the row, or any other occurrence in
the same referrer is left unmapped.

Add tombstone both-direction tests: exact tombstones for every and only assigned
tracked batch target permit the post scan to observe those worktree absences;
one unrelated missing tracked file still fails. Independently reject an extra,
missing, duplicate, pre-absent, wrong-batch, wrong-mode/OID/digest, still-present,
symlink, missing/wrong pre-deletion-baseline binding, or index-changed tombstone
and prove a valid tombstone never suppresses
an occurrence in a retained referrer.

Add actual-index lifecycle tests in a temporary Git repository. A valid
Step-5 disclosure followed by the Step-6 eligibility/review commit must produce
a valid `pre_deletion_index_baseline.v1` only when the index-entry delta is
exactly the enumerated evidence-root files and every nonexcluded entry/mode/blob
is unchanged. Independently reject an extra/missing evidence entry, changed
nonexcluded entry, unbound eligibility commit, stale Step-5 scan, or a four-part
post-commit identity not derived from the exact delta. From that new baseline, a
valid worktree-only deletion must preserve the exact raw index-file SHA-256,
`git write-tree` OID, NUL-delimited `git ls-files --stage -z` SHA-256, and
`git diff --cached --binary` digest/count through post scan, subject, and both
reviews while a `candidate_to_stage.v1` simulation predicts the intended tree.
Independently reject a pre-review `git add`/`git rm --cached`, raw index-byte
refresh, changed cached diff, changed index entry with an equal worktree,
unrelated staged entry, simulated manifest with an extra/missing/wrong-mode/
wrong-digest path, and actual Step-11 staging unequal to the simulation plus
closed post-review additions. The positive Step-11 fixture stages only after
both reviews and proves actual tree/index/cached-diff equality to the reviewed
simulation.

Treat `delete_with_source` refined to same-batch referrer deletion or exact-
occurrence removal, plus reroute, as a checked transaction: the pre-edit gate
requires every active reference to name an exact planned disposition and permits
no unclassified active reference; the post-edit gate then requires zero
surviving active reference. It is incorrect to require the referrer edit to
already exist before the pre-edit record, or to let the planned disposition
stand in for the post-edit rescan.

Add a fresh-referrer authority test: batch targets come from the reviewed
assignment, but the editable/deletable referrer set must equal the current
batch's fresh pre-repository-scan plus its exact two disposition lanes. Reject
a referrer named only by `batch-assignment.json`, Task-7 characterization, or a
prior batch; reject any fresh row whose required edit is one of the ten
non-target sources and report the bound queue-owner route instead.

Add focused-contract both-direction tests. Require the exact three base roles,
derive the complete candidate-specific coverage set from the current
dispositions/transition, and require `focused_checks.v1` command equality.
Independently reject one missing/extra/renamed selector, a selector that
collects zero nodes, stale changed-referrer bytes, a production/CLI/routing
edit without an owning selector, and a broad-only surrogate. Exercise every
smoke predicate: each launch/script/CLI/default/loader/reroute/executable-
fixture case forces `performed`, while a deletion-only/historical-only case
accepts `not_required`; reversing either decision fails closed. Apply the same
derivation to a repair's exact intended change projection.

- [ ] **Step 4: Implement issue-returning validators and CLI**

The CLI supports `capture`, `materialize`,
`materialize-pending`, `validate`, `project`, `project-transition`,
`prepare-pending-binding`, `prepare-repair-binding`, and
`close-prior-deletion`; it never deletes files,
edits state stores, or
auto-populates owner fields. `project` writes canonical Markdown from a fully
valid index only. `project-transition` accepts only one of the five closed
prospective schemas: assignment and eligibility render/verify their exact
pre-repository-capture external manifests; batch deletion and repair write the
candidate external projection before their final post scan; final closeout
verifies the three already-materialized authored rows, writes the generated
live-projection fourth row, then validates all four exact post states. In every lifecycle the
later committed index must render byte-identically. `project --check
<existing-path>` computes canonical bytes without writing and fails on
inequality. `prepare-pending-binding` receives the reviewed deletion-
subject manifest and both approved review byte digests, verifies that each
review binds only the subject and exact scan/test inputs, and accepts no unknown
commit or self-containing tree. It is derive/validate-only: it writes no file,
request, snapshot, live output, or evidence record and returns only a canonical
diagnostic receipt on stdout;
`prepare-repair-binding` accepts only the next contiguous immutable repair
subject and its two approved reviews and proves the derived non-owning repair
event would preserve path ownership. It is likewise derive/validate-only and
writes no evidence byte.
`close-prior-deletion` accepts only a HEAD that is the immediate substantive
predecessor—commit A for an empty repair chain or the latest valid repair commit
otherwise—and derives/validates the complete evidence-only closure-event inputs
without writing them. These three helpers invoke the same pure derivation
functions as the corresponding materializer adapters; their stdout is
diagnostic, is never an input binding, and cannot be staged. The executor must
then invoke the one legal `materialize --kind deletion-pending`,
`deletion-repair-pending`, or `deletion-closure` transaction, which recomputes
the derivation under the materialization lock and exclusively creates the
request, snapshot, and live event.
`materialize` and `materialize-pending` implement the one-shot Typed
materialization surface above and are the only machine-record construction
routes used by Tasks 7–17. `capture` is limited
to the eight capture-mode kinds in that table; it is not an open alias for a
materializer kind. `validate --kind non-target-queue-sources` delegates to the
Task-1 source-binding validator and must return byte-identical typed issues and
exit status for the same record/repository inputs.

Implement generation/path derivation, exclusive immutable request/snapshot
creation, crash-safe snapshot-before-live publication, contiguous transition
validation, and historical-generation validation once in the generic typed
surface. `execution-ledger`, `execution-index`, batch projections, and all
generated external projections must use it; individual record-kind handlers may
not retain or overwrite their own singleton history. Implement one lock-held
request/snapshot/live transaction with canonical complete receipts, and
implement the four-kind pending-owner partition as the explicit
`materialize-pending` route with owner-shaped inputs structurally impossible.
Implement
`candidate-to-stage` as an index-preserving simulation and expose the four-part
actual-index identity check to scans, subjects, reviews, and Step-11 staging
validation. Implement the `pre-deletion-index-baseline` capture kind to close
the Step-5 disclosure/Step-6 evidence-only delta and establish the sole
Steps-7-through-11 index authority.

- [ ] **Step 5: Add permanent genericity and mutation guards**

Scan production source for every queue basename and the labels
`agent-orchestration`, `EasySpin`, `PtychoPINN`, `ptychopinnpaper2`, and
`delete_non_survivor_estate`. Expected: no occurrence.

- [ ] **Step 6: Verify and run the broad candidate gate**

Run the exact five Task-6 focused/compile/CLI roles from the closed command
table. The named CLI-smoke test must exercise the production CLI in a temporary
Git repository rather than mock it and enumerate every materializer and capture
kind from the closed fixture manifest, including all preparation, concurrency,
pending-route, lifecycle, and capture positive/negative controls specified
above. Persist every log/exit under
`implementation-commits/task-06/focused/` and build the closed passing
`focused/report.json`. Then run the Generic Production Broad Gate with the
Task-6 mapping and require collection exit zero and the exact owner-baseline
comparison.

- [ ] **Step 7: Review and commit**

Build `implementation-commits/task-06/subject.json` under
`implementation_verification_subject.v1`, binding the exact focused report,
required `outcome.json`, task contract, candidate/ledger identity, and candidate
path manifest. Both reviews bind only that subject. Any production or evidence
correction invalidates the focused report, broad outcome, subject, and both
reviews. Commit only after the complete candidate passes both stages.

### Task 7: Materialize And Review The Exact Seven-Batch Assignment

**Files:**
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/repository-scan.json`
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/reference-dispositions.json`
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/compatibility-fact-dispositions.json`
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/assignment-inputs/pre-transition-import-graph.json`
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/import-graph.json`
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/batch-category-input.json`
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/batch-assignment.json`
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/prospective-assignment-transition.json`
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/execution-index.json`
- Create: `docs/workflow_yaml_retirement_execution.md`
- Modify: `docs/workflow_yaml_estate_triage.md`
- Modify: `docs/plans/2026-07-07-yaml-retirement-program.md`
- Modify: `docs/index.md`
- Modify: `tests/test_workflow_lisp_procedure_first_migrations.py`
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`
- Modify: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/execution-ledger.json`

- [ ] **Step 1: Review the category input and compute membership**

Persist a reviewed category-input record with exactly one row for every
query path: `path`, closed `category_id`, fixed `preferred_batch`, and a
content-addressed rationale/evidence binding. Categories are data, not
production branches. Require:

- batch 1 (15): call/review, follow-on, repeat-until, depends-on, and revision
  component surfaces;
- batch 2 (15): generic standalone workflows, including the generic task/demo
  default;
- batch 3 (10): remaining simple examples plus the revision monolith;
- batch 4 (15): NeurIPS-family stack surfaces;
- batch 5 (15): major-project surfaces;
- batch 6 (15): shared backlog/tracked/revision surfaces; and
- batch 7 (15): autonomous, ProcRef, Lisp-frontend, and template surfaces.

The category-input top level contains exactly `schema_version`,
`execution_ledger_binding`, `query_binding`, `category_definitions`, `rows`,
`normalized_category_input_sha256`, and
`claims_not_made`. The seven definitions contain only `category_id`,
`preferred_batch`, `required_count`, and descriptive rationale; rows contain
only the four fields above. The generated assignment separately binds the
category-input byte digest and two approved review artifacts that bind that
input at `reviews/category-input-specification.json` and
`reviews/category-input-quality.json`; neither side self-references. Those two
files are the only reviews added at this stage; the immutable two-file
implementation-failure-baseline review pair is already present and bound.

The assignment algorithm contains no search or judgment: validate all 100
category rows; assign each path to its declared `preferred_batch`; require the
fixed quotas; require every importer's batch number to be less than or equal to
its imported target's number; then order paths within a batch by Kahn
topological order with repository-relative lexical path as the only tie-break.
Cycle, quota mismatch, dependency inversion, missing/duplicate row, or an
unrecognized category fails. The generator never moves a path to make the
input pass. Persist every exact path and independently review the category
input before generating/reviewing the assignment.

- [ ] **Step 2: Commit every scanner-visible assignment/routing byte**

Capture the planning-side graph at
`assignment-inputs/pre-transition-import-graph.json`. Create
`prospective-assignment-transition.json` from the reviewed category input and
that exact graph. It binds the graph's exact file digest, normalized record
digest, and semantic graph digest and fixes exact seven-batch membership
and the intended pending index projection while leaving repository-scan,
disposition, assignment-review, and index digests null. Materialize the exact
Stage-6 program, docs index, frozen-triage label, live projection, migration
assertions, and routing-test candidate bytes. The transition's nonexcluded
manifest equals every changed scanner-visible path in both directions.

Review and commit those nonexcluded bytes plus the prospective transition,
category input, and immutable pre-transition graph. The live projection must describe deterministic
membership without claiming assignment approval. This is the last
scanner-visible assignment commit. Run the protected guard and validate HEAD;
any later nonexcluded edit restarts this step before a new scan.

- [ ] **Step 3: Recapture repository/import facts after the routing commit**

Only after Step 2 is committed, run the generic CLI against the frozen query.
Bind exact capture HEAD, full index disclosure, nonexcluded index/worktree
projection, raw-byte candidate manifest including all binary/non-UTF-8
candidates, the exact scanner-owned evidence-root exclusion, scan version/query,
and normalized occurrence/compatibility digests. Capture the post-routing graph
to the distinct canonical `import-graph.json` path; never overwrite the
pre-transition graph. This assignment-time scan is immutable
characterization of the committed routing state; each deletion batch still
captures a new scan. If the post-routing graph has the same
`semantic_graph_sha256`, its expected capture metadata/file/normalized-digest
difference is valid and both exact records remain bound. If its semantic digest
differs for any reason, do not create dispositions or assignment: invalidate
and discard the uncommitted Step-3 outputs, return to Step 1, recapture a new
pre-transition graph, rematerialize/review/commit the category and transition,
then recapture a new post-routing graph. Once any Step-3 repository scan or
post-routing graph exists, an assignment may not bind mixed generations; the
recovery is a superseding Step-2 commit with a complete replacement transition/
input pair followed by fresh Step-3 outputs, never an evidence-only rewrite of
one member.

- [ ] **Step 4: Classify both reference lanes**

Every occurrence row receives and freezes exactly one allowed handoff-v1 enum
classification by `occurrence_id`, plus a same-batch edit/delete path or durable
historical rationale; it does not bind a nonexistent captured v1 row. A
`delete_with_source` selection additionally receives exactly one execution
postcondition refinement, `delete_referrer_with_source` or
`remove_exact_occurrence`, without changing or inventing a frozen v1 record.
Persist and
validate exact equality between the repository scan's occurrence count/digest
and `reference-dispositions.json`'s classified count plus reconstructed full
set digest. Separately classify every explicitly identified compatibility-
importer fact in `compatibility-fact-dispositions.json` and bind its exact
count/digest; apply active-wins
precedence without collapsing ordinary occurrences to pairs. Active code,
scripts, tests, fixtures, current docs, routing, and defaults must be deleted or
have each exact occurrence removed or rerouted by their target's batch.
Specifically classify
`orchestrator/demo/trial_runner.py` as active.

- [ ] **Step 5: Verify the already committed frozen-v1/current-state tests**

Verify the Step-2 test bytes kept all original 110-path/63-row assertions as
capture assertions and added prospective current-state membership assertions
without claiming the not-yet-created execution index exists. The eventual index
tests require active plus historical reconciliation and remove only assumptions
that “captured pending/live” means “currently present on disk.” Do not edit a
test after Step 3; any correction returns to Step 2 and a fresh scan.

- [ ] **Step 6: Build and independently review the complete assignment**

Generate `batch-assignment.json` only after Steps 3–5. It binds exact bytes,
versions, counts, and normalized set digests for the post-routing repository
scan, occurrence dispositions, compatibility-fact dispositions, import graph,
the distinct exact pre-transition import graph, their required equal semantic
graph digests, reviewed category input, and both category-input reviews. Recompute membership
and require it byte-identical to the prospective transition.

Specification review checks every exact path/category and all 51 edges. Quality
review checks the complete input chain, deterministic generation, closed
schemas, every occurrence row
by exact count and normalized set digest, and every separately enumerated
compatibility-importer fact by its exact count/digest. The provisional 1,097
pair count may be reported as characterization but cannot satisfy coverage. No
deletion may begin until both approve at
`reviews/assignment-specification.json` and
`reviews/assignment-quality.json`. Both bind `batch-assignment.json`; the
assignment record already binds both category-review digests. With the immutable
implementation-baseline review pair, top-level review cardinality is exactly
six at this boundary.

- [ ] **Step 7: Create and commit the assignment-consuming index**

Immediately before preparing the generation-1 execution-index request, capture
the current Step-6 `HEAD` as `created_at_commit`. Build
`initial_index_base` from that same HEAD, the current immutable execution-ledger
request/output generation, its approved-plan binding, and the reviewed
assignment path/digest. This capture precedes the generation-1 materialization transaction and is not the
unknown future commit that will first contain the index.

Create `execution-index.json` with all 100 paths active, empty history, seven
pending batches whose nested owner lifecycles are all `absent`, absent root-
scope/initial-root/baseline bindings, and one exact
`batch-assignment.json` path/digest plus the two exact approving assignment-
review path/digests. The index consumes that complete reviewed object rather
than copying its input bindings. Bind the current execution-ledger generation
and require it to equal `initial_index_base.initial_ledger_generation`; require
its approved-plan binding and Task-7 step state
to validate. Bind the immutable Task-2
`non-target-queue-sources.json` path/digest/schema/count/path-list/row-set
coordinates and freshly verify all ten live sources before staging and again
at HEAD. Bind the immutable Task-2 `workspace-baseline.json` coordinates shown
in the top-level schema and a fresh all-dirty/full-index commit-isolation
validation; preserve those coordinates in every later index generation. Bind the immutable Task-2 implementation
failure-baseline outcome/record/two reviews/owner attestation and the complete
cumulative reviewed-remediation list (initially empty unless Tasks 3–6 landed
an approved in-scope reduction), plus the exact ordered reviewed skip-change
list (initially empty unless Tasks 3–6 changed the skipped-node set). Populate
no owner field. Run `project --check`
and require the index renders byte-identically to the live projection already
committed in Step 2;
do not rewrite any nonexcluded path. Stage only evidence-root assignment,
reviews, transition, and index files, run the protected guard, commit, and
validate at HEAD. Any external diff is a hard failure. No deletion may precede
this assignment/index commit. At HEAD, require `created_at_commit` to remain the
captured parent/base HEAD, require the containing commit to be distinct, and
reopen the immutable initial ledger/base bindings. Every later index update
must preserve both fields byte-for-byte.

- [ ] **Step 8: Capture the fresh pre-mutation broad baseline in tmux**

This is the pre-deletion-mutation baseline: it runs after the reviewed generic
machinery and routing commit but before any authored workflow or active
referrer is deleted, rerouted, or edited to remove an exact occurrence. Run
`pytest --collect-only -q` with combined
output written directly to `baseline/collect.log` and base-10-plus-LF status to
`baseline/collect.exit`; require parsed exit zero, extract every exact collected
node ID, sort under `LC_ALL=C`, write it to
`baseline/collected-node-ids.txt`, and bind all three files/count/digests. Then
run and bind `baseline/pytest-temp-root-preflight.json` under the same
pytest-8.4.1 executable/environment and require the closed probe contract.
Then
launch:

```bash
tmux new-session -d -s yaml-retirement-task6-baseline \
  "cd /home/ollie/Documents/agent-orchestration && pytest -q -rs -n 16 --dist=worksteal --junitxml=docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/baseline/pytest.junit.xml > docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/baseline/pytest-rs.log 2>&1; status=\$?; printf '%s\\n' \"\$status\" > docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/baseline/pytest.exit; exit \"\$status\""
```

The closed `outcome.json` binds HEAD/tree, exact command, Python/pytest/
plugin versions, node-list count/digest, log digest, exit code, totals, and
exact failed/skipped node IDs derived one-to-one from the bound JUnit report and
same-candidate collected list. The `-rs` log and JUnit XML byte digests are both
mandatory, and `pytest.exit` is parsed/bound under the closed rule above. No
baseline is approved unless the complete failed-node/signature table exactly
matches the owner-confirmed implementation baseline minus the cumulative set
of separately reviewed in-scope remediations. New/changed failures, external
failure removal, or an unreviewed disappearance fail closed. No
baseline validator or reviewer reads `tmp/`. Record complete before/after tree
snapshots of the five candidate
run roots and require no mutation. Obtain both reviews and commit this evidence
at `reviews/baseline-specification.json` and
`reviews/baseline-quality.json`, then set the index baseline binding to
`approved` with the outcome and both review digests and commit. Top-level review
cardinality is exactly eight before Task 8 or any workflow deletion.

This approved baseline outcome is also the immutable initial skipped-node set
for batch execution. It records exact IDs/digest but makes no claim that a skip
is acceptable behavior; later equality is mandatory unless a batch's reviewed
skip-change triple advances the predecessor set under the closed contract.

### Task 8: Prepare And Obtain Owner Root-Scope Adoption

**Files:**
- Create: the supported-root scope path specified above
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/review-subjects/root-scope-{pending,confirmed}.json`
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/reviews/root-scope-{pending,confirmed}-{specification,quality}.json`
- Modify: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/execution-index.json`
- Modify: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/execution-ledger.json`

- [ ] **Step 1: Generate a pending form mechanically**

Run the one-shot `materialize-pending` transaction for `supported-root-scope`;
ordinary `materialize`, `prepare-request`, and `--request` are forbidden.
Include the five audited slots and exact canonical workspace, workflow source
base, and run-root paths/digests. Leave all owner-only fields pending. State
that unknown external stores are not asserted absent. Supported slots state
scope disposition only; excluded slots carry required owner reason/evidence.
The record contains no current, null, or future scan/attestation bindings.

- [ ] **Step 2: Validate and commit the pending lifecycle**

Set the index root-scope binding to `pending_owner_confirmation` with exact
path/digest, run `project --check` against the unchanged external projection,
run fixture/closed validators, and freeze
`review-subjects/root-scope-pending.json` with the exact pending form, ledger,
prior index, and cycle-free intended pending index projection with null review
digests. Obtain the two reviews at the
deterministic pending paths; only then may the intended index consume their
digests. Stage only the pending form/subject/reviews/index/ledger, run the
protected guard, and commit. Root-scope lifecycle is
evidence-only and may not rewrite a scanner-visible projection. The prior
committed index must show `absent` with null slots. Top-level review cardinality
is exactly ten.

- [ ] **Step 3: Pause at the owner boundary**

Request the owner to confirm the complete supported scope and any exclusions
in the exact file. Do not infer adoption from standing intent or a relayed
summary.

- [ ] **Step 4: Validate an owner-confirmed replacement**

Recompute every workspace/source-base/run-root digest and validate
provenance/timestamps. Fail closed on the first exact field mismatch, missing
excluded slot, unsupported exclusion reason, or ambiguous source base.

- [ ] **Step 5: Review and commit the scope record**

Freeze `review-subjects/root-scope-confirmed.json` with the exact adopted form,
ledger, preserved pending subject/reviews, prior index, and cycle-free intended
confirmed index projection with null confirmed-review digests. The deterministic
confirmed specification and quality reviews bind that subject and confirm it
decides scope only, not scan truth or deletion eligibility. Commit the owner-
confirmed scope/subject/reviews/index/ledger lifecycle only after
`project --check` proves external bytes unchanged, then treat the confirmed
scope bytes as immutable. `initial_root_bindings` remains
`absent`; Task 9 alone may advance it. Top-level review cardinality is exactly
twelve.

### Task 9: Capture Per-Root Scans And Obtain Per-Root Attestations

**Files:**
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/roots/<digest>/initial-scan.json` for each supported root only
- Create: the deterministic per-root attestation path above for each supported root only; excluded slots create no binding/file and remain scope-only
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/initial-root-bindings.json`
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/review-subjects/initial-root-bindings-{pending,confirmed}.json`
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/reviews/initial-root-bindings-{pending,confirmed}-{specification,quality}.json`
- Modify: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/execution-index.json`
- Modify: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/execution-ledger.json`

- [ ] **Step 1: Start an owner-defined quiescence window**

No workflow launch is authorized by this task. Record exact enforcement and
permitted mutations; do not claim a past start time without owner confirmation.

- [ ] **Step 2: Scan every supported root**

Run the exact 100-path query through each supported slot's bound workspace,
workflow source base, and run root. Preserve occurrence rows, distinct
containing-run/frame keys, raw status disclosures, whole-query/store totals,
file digests, timestamps, content snapshot digest, and timestamp-inclusive
record digest. Fail closed on any path-base, race, unreadable, symlink, run
association, or status-read defect.

- [ ] **Step 3: Generate pending per-root forms and pause**

For each supported root run the one-shot `materialize-pending` transaction for
`root-scan-attestation`; reject every owner-shaped input.
No record is required for an excluded slot, whose exclusion is already owner-
bound in the immutable scope record. Validate the supported-root
pending templates plus `initial-root-bindings.json` containing every and only
supported root, and advance only `index.initial_root_bindings` from `absent` to
`pending_owner_confirmation`. Freeze the deterministic pending lifecycle
subject with prior index, exact ledger/record bindings, and a cycle-free intended
index projection whose pending-review digests are null; obtain both pending
reviews, and let the intended index consume their
exact digests before commit. The owner-confirmed scope path/digest remains
byte-identical. Require `project --check` and commit the pending binding/index
lifecycle without rewriting the projection, then pause for the owner to review
and adopt each record; an agent may not convert planning
observations into owner confirmation. Top-level review cardinality is exactly
fourteen.

- [ ] **Step 4: Validate and index the adopted records**

Re-scan if the store changed; a changed scan requires re-adoption and a fresh
pending initial-root binding. Replace only attestation bindings, advance
`initial_root_bindings` to `owner_confirmed`, and keep the root-scope record and
index root-scope binding unchanged. Do not infer
eligibility for the paper root from its planning-time terminal labels: project
its four observed runs by batch and require support disposition for each
projected run just like any other root.

- [ ] **Step 5: Run two-stage review and commit evidence**

Freeze the confirmed lifecycle subject with the exact adopted records, ledger,
preserved pending subject/reviews, prior index, and cycle-free intended confirmed
index projection with null confirmed-review digests.
The deterministic confirmed specification and quality reviews verify exact
supported-root coverage and the independent lifecycle. Let the index consume
their exact digests. Require `project --check` and commit the confirmed
subject/reviews/initial-root bindings/index/ledger
without any nonexcluded change; no source deletion occurs in this task. This is
the last initial-root commit, but every batch still performs its own fresh store
scan/adoption and post-owner repository ordering. Top-level review cardinality
is exactly sixteen.

### Task 10: Execute Batch 1 (15 Paths)

**Files:** Exact targets from `batch-assignment.json`; exact current referrers
come only from this batch's fresh Step-5 pre-repository scan and its two exact
disposition records. Add only the
batch-01 deterministic supported-root scan slots, the six exact reference
files, required-focused-command/check/log/exit paths, closed smoke paths, broad
raw/outcome and optional auxiliary paths,
the eight exact `owner-lifecycle/` subject/review/consumer paths,
projection/gate/pre-deletion-index-baseline/candidate-to-stage,
deletion-subject/lifecycle, contiguous conditional repair paths, six review paths, and the
root `execution-ledger.json` defined by the closed layout and
canonical fixtures above.

The immutable Task-2 `non-target-queue-sources.json` binding and all ten live
source bytes are a cross-cutting batch precondition. Verify them before the
first batch scan, in the pre-delete gate, against the deletion subject and
complete staged commit-A candidate, immediately at commit-A HEAD, against the
candidate and HEAD of every conditional repair, against the evidence-only
commit-B candidate, and immediately at commit-B HEAD. Each check
must recompute all ten path/row bindings, including Git mode/blob plus exact
worktree bytes for the nine archive/port sources and the protected-row binding
for the holdout. A mismatch stops the batch; it is never a disposition or
remediation input.

The immutable Task-2 `workspace-baseline.json` and every pre-existing dirty
entry are an equally mandatory cross-cutting precondition at all those
boundaries and before/after each scan, check, review, staging operation, and
commit. Recompute existence, no-follow type/mode, index stages, and exact
regular/symlink/directory/gitlink content. No batch transaction or staged set
may intersect the baseline dirty-path set; same-status byte drift stops the
batch.

- [ ] **Step 1: Capture fresh store scans at the deterministic batch paths**

First validate the immutable non-target-source record and all ten live source
bindings. Then write every supported root's complete store scan to
`roots/<canonical-root-digest>/pre-delete-scan.json`. Recompute the batch-01
store projections from those versioned occurrence rows and bind each query
path-list, count, version, content snapshot digest, and timestamp-inclusive
record digest. Whole-query and store totals remain disclosure only. Do not
capture the repository scan yet; owner/index/projection commits remain ahead.

- [ ] **Step 2: Satisfy scan-adoption freshness**

For each supported root use either fresh owner re-adoption or an identical-
content-snapshot/unbroken-quiescence proof. Any changed content snapshot or uncertain hold
returns to the owner. For every fresh-adoption root, create the validated
pending template only through one `materialize-pending` transaction. For every
identical branch, materialize the canonical machine continuity record; it cannot
be selected when any semantic snapshot or quiescence fact differs. Timestamp/
record-byte differences alone do not invalidate equal content.

From these exact scans, also compute the batch projection. If it has containing
runs, create one pending `run-support-disposition` through
`materialize-pending`, covering every distinct run regardless of raw status; if
it has none, bind the exact absent slot. Freeze
`owner-lifecycle/pending-subject.json` over all scans, pending forms, continuity
records, projection, ledger generation, and an intended pending index with null
future transition. Obtain its specification then quality review, publish both
immutable snapshots, and materialize `pending-consumer.json` as their sole
post-review consumer. Commit exactly that pending bundle and its index/ledger
generations; no external projection byte changes. Only then pause for the owner
to adopt every pending root and run record. A rejected or changed input restarts
this step with a new immutable subject/review/consumer generation.

- [ ] **Step 3: Resolve support disposition conditionally**

Validate every externally adopted root/run replacement against the immutable
pending consumer. Root-adoption timestamps must precede or equal dependent run-
support adoption. If the projection has no containing runs, preserve the absent
slot; otherwise any `supported` or undispositioned run remains in
`blocking_run_keys` and stops the batch, while `unsupported_abandoned` passes
only under the closed rules above. No owner-confirmed byte is produced or
rewritten by an agent.

With those records final, create `prospective-eligibility-transition.json` and
materialize every intended pre-edit external live-projection/routing byte in
memory for review. Freeze `owner-lifecycle/confirmed-subject.json` over the
pending consumer, adopted/continuity records, transition, exact external pre/
post manifest, ledger generation, and intended owner-confirmed index state that
makes no eligibility claim. Obtain specification then quality review, publish
their immutable snapshots, and materialize `confirmed-consumer.json`. Do not
commit or capture repository references yet.

- [ ] **Step 4: Commit the prospective eligibility projection**

Only after the confirmed subject's two reviews approve and
`confirmed-consumer.json` validates may the materializer publish the exact
reviewed external bytes and owner-confirmed index/ledger generations. The
prospective transition carries the intended batch projection, exact active/
history partition, exact pre-edit external live-projection/routing bytes, and
null repository-scan/disposition/gate/eligibility-review bindings. The external
view exposes only stable membership/partition fields and explicitly does not
claim the gate passed; transient eligibility/review digests remain evidence-
root-only so the eventual eligible index renders the same bytes. Commit exactly
the confirmed subject/reviews/consumer, adopted records, transition, external
manifest bytes, index, ledger, and their closed materialization generations.
Run the protected guard and
execution-index validator, both of which must validate the unchanged ten-source
binding against live bytes. This is the last nonexcluded pre-edit commit. If any
owner, projection, routing, source, or test byte must change later, invalidate
both owner-lifecycle stages and restart Step 2 before recapturing.

- [ ] **Step 5: Recapture and classify pre-edit repository references**

From the committed Step-4 HEAD, write the raw-byte repository scan of the
execution index's exact current active-path query to
`references/pre-repository-scan.json`, using only the exact scanner-owned
evidence-root exclusion. Bind capture HEAD, full index disclosure,
nonexcluded-index/worktree projection, query path-list/count/version, and both
occurrence/compatibility-fact counts and set digests.

Classify every exact current occurrence and compatibility fact—not the Task-7
or prior-batch rows—in separate
`references/pre-reference-dispositions.json` and
`references/pre-compatibility-fact-dispositions.json` lanes. Bind exact planned
postconditions, including every reroute replacement expectation, every target's
`git ls-files -s` blob ID, the exact `workspace-baseline.json` binding plus
current protected-path digests, and the batch dependency state. Materialize
`focused/required-commands.json` from those exact disposition rows and the
intended change projection under the closed base/candidate-specific/smoke rules
above. Build
`pre-delete-gate.json`; require empty derived blocking run/frame sets, exact
confirmed owner-lifecycle consumer binding, exact containing commit/transition,
pre-scan/disposition count+digest equality in both lanes, and no unclassified
active occurrence. The gate binds the immutable non-target-source record, the
exact required-focused-command manifest, and a
fresh ten-source validation result. If either fresh disposition lane requires
editing or deleting one of those ten paths, fail closed and route that exact
occurrence/fact to the disposition owner named by the source row; do not
reclassify it, substitute a Task-7 row, or alter the source.
Independently require the intended target/referrer/projection transaction to be
disjoint from every `workspace-baseline.json.dirty_entries` path; an intersection
is an owner-boundary failure, not authority to overwrite pre-existing work.

- [ ] **Step 6: Obtain specification then quality review of eligibility**

Write exactly `reviews/eligibility-specification.json` and
`reviews/eligibility-quality.json`. Both bind `pre-delete-gate.json` (which
closes its inputs, including the required focused/smoke contract), not their own future commit. Only after both approve may the
index bind their digests and mark the batch `eligible`; review cardinality is
exactly two. This update and its reviews are evidence-root-only. Run
`project --check` against the Step-4 external projection and reject any rewrite
or other nonexcluded diff before committing the eligible index. The repository
scan remains fresh because its nonexcluded projection is byte-identical.

Immediately after that eligibility commit, before any other write or deletion,
capture `pre-deletion-index-baseline.json`. Bind the Step-5 scan's disclosed
four-part identity, the exact eligibility commit/HEAD, and the new four-part
identity. Require the entry delta to equal every and only permitted Step-5/6
evidence-root path in the commit and require all nonexcluded index entries,
modes, and blob OIDs unchanged. This post-commit identity—not the Step-5
disclosure—is the frozen baseline consumed by Steps 7–11. Any failure restarts
from Step 5; do not begin deletion.

- [ ] **Step 7: Apply the exact deletion transaction**

Delete only assigned targets. Apply referrer edits/deletions only from this
batch's fresh Step-5 pre-repository scan and exact current occurrence and
compatibility-fact dispositions; `batch-assignment.json` authorizes target
membership/order only and is not referrer authority. A Task-7 or prior-batch
referrer row is stale even when its path text matches. Revalidate all ten
non-target sources before mutation; none may appear in the transaction.
Before any final post scan, create `prospective-transition.json` and use
`project-transition` to write the exact commit-A bytes of the external live
projection. Apply every required per-batch routing/status edit outside the
evidence root now as well; if none is required, bind an exact empty routing-edit
set. Relative to the Task-2 captured full `git status` and protected-path byte-
digest baseline, the only additional substantive diffs may be the exact
assigned-target transaction, the referrer transaction authorized by the fresh
Step-5 scan/disposition set, and these enumerated projection/routing edits.
Pre-existing dirty entries are not required clean or attributed to this batch,
but every one must retain its exact baseline existence, type, mode, index stages,
and regular/symlink/directory/gitlink content binding. Any intersection with the
assigned/referrer/projection transaction blocks before mutation; the seven named
protected paths remain the redundant stricter subset. Do not run the
final post repository/store scans, create the final subject, pending event, or
post-edit reviews yet. Do not stage any deletion/referrer/projection/routing or
evidence path. Recompute and require the exact post-Step-6
`pre_deletion_index_identity`
before and after the transaction.

- [ ] **Step 8: Verify the unstaged working-tree candidate**

Materialize the first immutable checked `candidate-to-stage.json` generation under
`candidate_to_stage.v1` from `pre-deletion-index-baseline.json` plus only the exact
worktree transaction; do not mutate the actual index. Require its simulated
path/state/mode/digest set and expected candidate tree to preserve all ten
non-target source bindings exactly and contain none of their paths. Bind the
unchanged four-part actual-index identity before and after simulation. Then run
every and only command in the eligibility-reviewed
`focused/required-commands.json`; the three base roles are mandatory and its
candidate-specific rows are the closed narrow behavioral/loader/CLI/dry-run
coverage set.
Persist every exact argv/result under `focused/checks.json`, with logs and exit
files at its content-addressed `focused/logs/<command-id>.log` and
`focused/exits/<command-id>.exit` paths; no result in `tmp/` is admissible.
When the manifest says `performed`, create its exact disposable directory
outside all five workspace/source/run roots, copy the bound self-contained
surviving `.orc` fixture or use the bound surviving route, execute its exact
argv with `--state-dir` inside that disposable root, bind the smoke artifacts,
and verify supported-root snapshots are unchanged. When it says
`not_required`, independently re-evaluate all closed performed predicates and
require all false. The quiescence record must
list this exact isolated mutation; no checkout `.orchestrate/runs` write is
permitted. Always create `smoke/isolated-smoke.json`: choose `not_required` with
the three output files absent, or `performed` with persistent `stdout.log`,
`stderr.log`, and `command.exit` plus their exact bindings.

- [ ] **Step 9: Run broad xdist in tmux on the unstaged candidate**

First write the candidate's `--collect-only` combined output and exit status to
`broad/collect.log` and `broad/collect.exit`, require zero, and derive/bind its
sorted `broad/collected-node-ids.txt`. Immediately run and bind
`broad/pytest-temp-root-preflight.json` under the same pytest-8.4.1 executable/
environment. Use the baseline command with a batch-
specific tmux session, retain `-rs`, and write directly to the
deterministic persistent paths `broad/pytest-rs.log`, `broad/pytest.exit`, and
`broad/pytest.junit.xml`; no intermediate `tmp/` path is permitted. Build
`broad/outcome.json`, bind all six raw inputs plus the exact preflight record,
map every failed/skipped testcase
one-to-one to an exact collected node ID, compare the failure set with the
owner-confirmed implementation baseline, and compare the skip set with the
immediately preceding accepted batch set beginning with the pre-mutation
baseline. Snapshot all
supported run roots before/after and require equality. Require collection exit
zero and `outcome=known_failures_matched|approved_failure_subset`; any new or
changed signature, external failure removal, reappearance, or unreviewed
disappearance fails closed. If and only if this batch's authorized diff removes
a queue-owned baseline failure, write `broad/failure-remediation.json`, obtain
the adjacent two remediation reviews, and then build the outcome binding all
three; all three files stay absent for an exact match.

If and only if the skipped-node set differs, materialize
`broad/skip-change.json`, obtain its adjacent specification and quality reviews,
and then build the outcome with the complete ordered skip-change prefix. All
three files are absent when the skip set is equal. An unreviewed added, removed,
or reappeared skip ID blocks even when the six failure signatures match.

The broad candidate binding includes the immutable non-target-source record
and a fresh validation of all ten live sources; a mismatch invalidates the
candidate regardless of test outcome. It also binds the Step-8
`candidate-to-stage.json` immutable generation
and unchanged before/after actual-index identities; any cached-diff, index-entry,
tree, or raw index-byte drift invalidates the run.

- [ ] **Step 10: Finalize the deletion subject and obtain both post-edit reviews**

After Steps 7–9, freeze the complete nonexcluded candidate. Prove every assigned
tracked target absent and every other pre-scan tracked candidate readable; write
`references/tracked-deletion-tombstones.json`; then run the final post repository
scan using those tombstones and the retired/replacement queries. Only now write
every supported root's `post-delete-scan.json` and
`post-reference-reconciliation.json`; require equal store content snapshots and
separately bind timestamp-inclusive record digests. Immediately revalidate the
post-scan candidate manifest/nonexcluded-index projection. Require its full
index identity to equal `pre-deletion-index-baseline.json`, and repeat that equality immediately before and
after each review. Any subsequent nonexcluded byte or actual-index drift
requires rerunning this final scan, reconciliation, affected checks, subject,
and both reviews.

Materialize the next contiguous `candidate-to-stage.json` generation after all
pre-review scan/test bytes are frozen. It binds those exact existing bytes and
retains null future slots only for `deletion-subject.json`, the two post-edit
reviews, and the closed Step-11 lifecycle/index additions; it still leaves the
actual index equal to the post-Step-6 pre-deletion baseline. Create
`deletion-subject.json` enumerating every substantive pre/post path and
pre-delete blob; exact pre/post bytes for the external live projection and every
routing/status edit; both repository scans, occurrence and compatibility-fact
dispositions, tombstones and reconciliation; every pre/post store scan;
the post-Step-6 pre-deletion index baseline and its exact Step-5 permitted-delta
proof;
prospective eligibility and deletion transitions; focused,
smoke, collection and broad evidence; and, when present, the immutable
remediation and skip-change records and their respective two approved reviews.
It binds the immutable candidate-to-stage manifest, all repeated unchanged-index
observations, and generation-addressed requests/output snapshots for every
mutable materialized input.
It also binds the immutable
non-target-source record and the fresh ten-source validation, and proves none
of the ten paths appears in the subject's changed/deleted/created transaction.
It explicitly excludes only evidence-root
lifecycle/index/batch-projection/review paths. Specification review then
code-quality review bind
only that final subject and its exact test/scan reports; each independently
reopens and validates the subject's post-Step-6 pre-deletion baseline binding.
They do not bind or
mention a pending event, unknown deletion commit, self-containing tree, or
their own containing commit. Any post-review substantive or test/scan change
invalidates the subject and both reviews. Write them only at
`reviews/post-edit-specification.json` and
`reviews/post-edit-quality.json`; review cardinality becomes exactly four.

- [ ] **Step 11: Create the pending event and make deletion commit A**

Only after both Step-10 reviews approve, create the
`deletion_committed_pending_binding` event, update index/projection status, and
bind the final subject plus the two review byte digests. The pending event has
no commit-A SHA/tree field. These are new contiguous immutable generations; the
subject-bound ledger/index/projection request and output snapshots remain
present and independently valid. If Step 9 produced a remediation triple, append
exactly that triple to the cumulative `approved_remediations` prefix; otherwise
preserve it byte-for-byte. If Step 9 produced a skip-change triple, append
exactly that triple to `approved_skip_changes`; otherwise preserve that prefix
byte-for-byte. Run `prepare-pending-binding` as a write-free derivation check,
then invoke exactly one `materialize --kind deletion-pending` transaction; only
that transaction may create the request, immutable snapshot, and live event.
Then run `project --check` over the completed candidate
index and require its computed bytes byte-identical to the already scanned and
reviewed `project-transition` output; do not rewrite that external file. From
this point until commit, create/edit only evidence-root lifecycle/index/batch-
projection/review files. Stage the exact substantive, scan/test, subject,
review, lifecycle, index, external projection, and enumerated routing paths; run
the protected guard;
require the staged-index tree to equal the deterministic application of the
reviewed candidate-to-stage manifest plus its enumerated post-review evidence/
lifecycle files to the unchanged post-Step-6 pre-deletion index baseline.
Require the actual staged
`git write-tree`, NUL-delimited index-entry digest, and cached-diff digest/count
to equal that closed prediction with no other index delta; commit; and immediately
run the closed validator at HEAD. Both staged-tree validation and immediate
HEAD validation recompute and require all ten non-target source bindings
unchanged. Commit A contains
the pending event and therefore binds it without a digest cycle. It must
reconcile active=85/history-owned=15 while batch-01 is
`committed_pending_binding`.

- [ ] **Step 12: Prepare evidence-only closure**

If no nonexcluded correction is required, commit A is the immediate substantive
predecessor. If one is required, do not touch closure files. Execute the closed
`repair-MM` lifecycle: choose the next contiguous number; materialize and bind
the prospective correction; recapture the canonical repository channels and
closed predecessor-state reconciliation plus supported-root snapshots;
materialize `focused/required-commands.json` from the repair's exact intended
change projection, require the repair reviewers to bind it, then run its exact
focused/smoke contract and the broad gate. If that gate changes failures or
skips, require the corresponding separately reviewed remediation/skip-change
triple and append it to the exact cumulative prefix in the repair event/index;
otherwise preserve both prefixes byte-for-byte. Then freeze the
ledger and repair subject; obtain the deterministic repair review pair; use
`prepare-repair-binding` only as a write-free derivation check; invoke exactly
one `materialize --kind deletion-repair-pending` transaction; and commit R-MM
with that materialized non-owning repair event.
Revalidate all ten non-target sources and unchanged path ownership before and
after that commit. Repeat only through another complete numbered repair when a
further nonexcluded correction is necessary.

With commit A or the latest repair commit now the immediate substantive
predecessor, change nothing outside the exact execution-evidence root—including
workflows, references, code, tests, external projection/routing docs, or run
stores. Append `deletion_evidence_closed` binding commit A/tree, the pending
event, the complete ordered repair chain, the immediate predecessor commit/tree,
post-commit validation, and evidence-only closure reviews at exactly
`reviews/closure-specification.json` and `reviews/closure-quality.json`. Both
bind `closure-validation.json`, whose closed subject binds the full chain and
prior subject/event inputs; they never bind a closure candidate tree or commit
B that will contain them. The closure event binds both approved review digests.
Run `close-prior-deletion` only as a write-free derivation check, then invoke
exactly one `materialize --kind deletion-closure` transaction to create its
request, immutable snapshot, and live closure event.

`closure-validation.json` binds the immutable non-target-source record and a
fresh immediate-predecessor HEAD validation of all ten live sources. Any mismatch blocks the
closure instead of being absorbed into evidence-only commit B.

- [ ] **Step 13: Make evidence closure commit B**

Stage only execution-evidence-root index/batch-projection/closure/review files;
any nonexcluded path or external live projection in the staged diff is a hard
failure. Recompute the all-ten binding against the staged candidate, run the
protected guard, commit, and validate both reconciliation and all ten live
source bindings again at commit-B HEAD.
Require batch-01 `closed`,
active=85, and exactly one path-owning pending event, zero or more valid
non-owning repair events, and one non-owning closure event. The batch review
directory must contain exactly the six deterministic files and no others; each
repair review directory contains exactly its two deterministic files.

### Task 11: Execute Batch 2 (15 Paths)

- [ ] **Step 1: Repeat Task 10 Step 1 for `batch-02`**

Capture every supported-root scan against the exact 15-path assignment, starting
from active=85/history-owned=15, with all Task-10 baseline and ten-source checks.

- [ ] **Step 2: Repeat Task 10 Step 2 for `batch-02`**

Land the exact pending owner-lifecycle subject/review pair/consumer bundle and
pause for adoption; require owner-lifecycle cardinality `0 -> 4`.

- [ ] **Step 3: Repeat Task 10 Step 3 for `batch-02`**

Validate adopted root/run records and build the confirmed owner-lifecycle
subject/review pair/consumer plus prospective transition. The active production
default in `orchestrator/demo/trial_runner.py` and its tests must be in the exact
reviewed reroute-or-removal manifest.

- [ ] **Step 4: Repeat Task 10 Step 4 for `batch-02`**

Commit the confirmed owner lifecycle and final pre-capture external bytes;
require owner-lifecycle cardinality `4 -> 8` and no eligibility claim.

- [ ] **Step 5: Repeat Task 10 Step 5 for `batch-02`**

Capture/classify fresh repository occurrences only after the confirmed commit.

- [ ] **Step 6: Repeat Task 10 Step 6 for `batch-02`**

Obtain eligibility reviews and capture the post-eligibility index baseline.

- [ ] **Step 7: Repeat Task 10 Step 7 for `batch-02`**

Apply exactly the reviewed 15-target/referrer/default-route transaction unstaged.

- [ ] **Step 8: Repeat Task 10 Step 8 for `batch-02`**

Run the exact focused contract and mandatory isolated end-to-end smoke for the
chosen replacement/default route; isolated unit tests alone are insufficient.

- [ ] **Step 9: Repeat Task 10 Step 9 for `batch-02`**

Run and bind the broad candidate gate with unchanged index and roots.

- [ ] **Step 10: Repeat Task 10 Step 10 for `batch-02`**

Finalize post scans, candidate manifest, deletion subject, and both reviews.

- [ ] **Step 11: Repeat Task 10 Step 11 for `batch-02`**

Derive write-free, materialize `deletion-pending` once, and make commit A.

- [ ] **Step 12: Repeat Task 10 Step 12 for `batch-02`**

Run any complete reviewed repair chain, then derive write-free and materialize
the single `deletion-closure` event.

- [ ] **Step 13: Repeat Task 10 Step 13 for `batch-02`**

Make evidence-only commit B and prove active=70/history-owned=30. The immutable
ten-source checks apply at every Task-10 boundary.

### Task 12: Execute Batch 3 (10 Paths)

- [ ] **Step 1: Repeat Task 10 Step 1 for `batch-03`**

Capture fresh supported-root scans for the exact 10-path assignment from
active=70/history-owned=30.

- [ ] **Step 2: Repeat Task 10 Step 2 for `batch-03`**

Land the pending owner-lifecycle subject/reviews/consumer and pause; require
cardinality `0 -> 4`.

- [ ] **Step 3: Repeat Task 10 Step 3 for `batch-03`**

Validate adoption/support and build the confirmed subject/reviews/consumer and
prospective transition.

- [ ] **Step 4: Repeat Task 10 Step 4 for `batch-03`**

Commit the confirmed owner lifecycle and exact pre-capture projection; require
cardinality `4 -> 8`.

- [ ] **Step 5: Repeat Task 10 Step 5 for `batch-03`**

Capture/classify the fresh repository lanes from that confirmed HEAD.

- [ ] **Step 6: Repeat Task 10 Step 6 for `batch-03`**

Review eligibility and capture the post-eligibility index baseline.

- [ ] **Step 7: Repeat Task 10 Step 7 for `batch-03`**

Apply only the reviewed 10-target/referrer/projection transaction unstaged.

- [ ] **Step 8: Repeat Task 10 Step 8 for `batch-03`**

Run the exact candidate-to-stage, focused, and smoke contract.

- [ ] **Step 9: Repeat Task 10 Step 9 for `batch-03`**

Run and bind the broad candidate gate.

- [ ] **Step 10: Repeat Task 10 Step 10 for `batch-03`**

Finalize post evidence, subject, and post-edit reviews.

- [ ] **Step 11: Repeat Task 10 Step 11 for `batch-03`**

Derive write-free, materialize `deletion-pending` once, and make commit A.

- [ ] **Step 12: Repeat Task 10 Step 12 for `batch-03`**

Close any reviewed repair chain through the sole materialized closure event.

- [ ] **Step 13: Repeat Task 10 Step 13 for `batch-03`**

Make commit B and prove active=60/history-owned=40. Revalidate the exact seven
archive, two port, and one holdout sources at every Task-10 boundary.

### Task 13: Resolve And Execute Batch 4 (15 Paths)

- [ ] **Step 1: Repeat Task 10 Step 1 for `batch-04`**

Capture all supported roots for the exact 15 paths from active=60/history=40;
planning predicts PtychoPINN consumers, but fresh projections decide.

- [ ] **Step 2: Repeat Task 10 Step 2 for `batch-04`**

Land the pending owner lifecycle for every projected run without terminal-status
filtering and pause; require cardinality `0 -> 4`.

- [ ] **Step 3: Repeat Task 10 Step 3 for `batch-04`**

Validate every adoption/disposition. Any `supported` or undispositioned run
blocks. Build the confirmed lifecycle only when blocking sets can be empty.

- [ ] **Step 4: Repeat Task 10 Step 4 for `batch-04`**

Commit confirmed owner authority/projection and require cardinality `4 -> 8`.

- [ ] **Step 5: Repeat Task 10 Step 5 for `batch-04`**

Capture/classify repository lanes after the final confirmed commit.

- [ ] **Step 6: Repeat Task 10 Step 6 for `batch-04`**

Require empty derived blocking sets, eligibility reviews, and index baseline.

- [ ] **Step 7: Repeat Task 10 Step 7 for `batch-04`**

Apply exactly the reviewed 15-path transaction unstaged.

- [ ] **Step 8: Repeat Task 10 Step 8 for `batch-04`**

Run the exact focused/smoke candidate contract.

- [ ] **Step 9: Repeat Task 10 Step 9 for `batch-04`**

Run the broad candidate gate with unchanged supported roots.

- [ ] **Step 10: Repeat Task 10 Step 10 for `batch-04`**

Finalize post evidence, subject, and post-edit reviews.

- [ ] **Step 11: Repeat Task 10 Step 11 for `batch-04`**

Materialize the pending event once and make commit A.

- [ ] **Step 12: Repeat Task 10 Step 12 for `batch-04`**

Complete any reviewed repair chain and the sole materialized closure event.

- [ ] **Step 13: Repeat Task 10 Step 13 for `batch-04`**

Make commit B and prove active=45/history-owned=55 with ten-source validation at
every Task-10 boundary.

### Task 14: Resolve And Execute Batch 5 (15 Paths)

- [ ] **Step 1: Repeat Task 10 Step 1 for `batch-05`**

Capture all supported roots for 15 paths from active=45/history=55; planning
predicts EasySpin consumers, while fresh projections decide.

- [ ] **Step 2: Repeat Task 10 Step 2 for `batch-05`**

Land/pause on the exact pending owner lifecycle; require `0 -> 4`.

- [ ] **Step 3: Repeat Task 10 Step 3 for `batch-05`**

Require closed run dispositions and empty derived blocking sets; whole-query/
store totals remain disclosed but non-gating. Build confirmed authority.

- [ ] **Step 4: Repeat Task 10 Step 4 for `batch-05`**

Commit confirmed authority/projection and require `4 -> 8`.

- [ ] **Step 5: Repeat Task 10 Step 5 for `batch-05`**

Capture/classify repository lanes after that commit.

- [ ] **Step 6: Repeat Task 10 Step 6 for `batch-05`**

Review eligibility and capture the index baseline.

- [ ] **Step 7: Repeat Task 10 Step 7 for `batch-05`**

Apply only the reviewed 15-path transaction unstaged.

- [ ] **Step 8: Repeat Task 10 Step 8 for `batch-05`**

Run exact candidate-to-stage/focused/smoke checks.

- [ ] **Step 9: Repeat Task 10 Step 9 for `batch-05`**

Run the broad candidate gate.

- [ ] **Step 10: Repeat Task 10 Step 10 for `batch-05`**

Finalize post evidence, subject, and reviews.

- [ ] **Step 11: Repeat Task 10 Step 11 for `batch-05`**

Materialize the pending event once and make commit A.

- [ ] **Step 12: Repeat Task 10 Step 12 for `batch-05`**

Complete any reviewed repairs and sole materialized closure event.

- [ ] **Step 13: Repeat Task 10 Step 13 for `batch-05`**

Make commit B and prove active=30/history-owned=70 with all Task-10 ten-source
checks.

### Task 15: Resolve And Execute Batch 6 (15 Paths)

- [ ] **Step 1: Repeat Task 10 Step 1 for `batch-06`**

Capture all supported roots for 15 paths from active=30/history=70; planning
predicts EasySpin and PtychoPINN consumers.

- [ ] **Step 2: Repeat Task 10 Step 2 for `batch-06`**

Land the pending lifecycle for both projected support sets; require `0 -> 4`.

- [ ] **Step 3: Repeat Task 10 Step 3 for `batch-06`**

Require both fresh support sets to close simultaneously before confirmed
authority is reviewable.

- [ ] **Step 4: Repeat Task 10 Step 4 for `batch-06`**

Commit confirmed authority/projection and require `4 -> 8`.

- [ ] **Step 5: Repeat Task 10 Step 5 for `batch-06`**

Capture/classify repository lanes after confirmed HEAD.

- [ ] **Step 6: Repeat Task 10 Step 6 for `batch-06`**

Review eligibility and capture the index baseline.

- [ ] **Step 7: Repeat Task 10 Step 7 for `batch-06`**

Apply only the reviewed 15-path transaction unstaged.

- [ ] **Step 8: Repeat Task 10 Step 8 for `batch-06`**

Run exact candidate-to-stage/focused/smoke checks.

- [ ] **Step 9: Repeat Task 10 Step 9 for `batch-06`**

Run the broad candidate gate with both root sets unchanged.

- [ ] **Step 10: Repeat Task 10 Step 10 for `batch-06`**

Finalize post evidence, subject, and reviews.

- [ ] **Step 11: Repeat Task 10 Step 11 for `batch-06`**

Materialize the pending event once and make commit A.

- [ ] **Step 12: Repeat Task 10 Step 12 for `batch-06`**

Complete any reviewed repairs and sole materialized closure event.

- [ ] **Step 13: Repeat Task 10 Step 13 for `batch-06`**

Make commit B and prove active=15/history-owned=85 with all ten-source checks.

### Task 16: Resolve And Execute Batch 7 (15 Paths)

- [ ] **Step 1: Repeat Task 10 Step 1 for `batch-07`**

Capture all supported roots for the final 15 paths from active=15/history=85;
planning predicts current-checkout and repository-copy consumers.

- [ ] **Step 2: Repeat Task 10 Step 2 for `batch-07`**

Land the pending lifecycle for every final projected run; require `0 -> 4`.

- [ ] **Step 3: Repeat Task 10 Step 3 for `batch-07`**

Require all final support dispositions and quiescence covering every supported
store through commit-B validation; build confirmed authority only when empty.

- [ ] **Step 4: Repeat Task 10 Step 4 for `batch-07`**

Commit confirmed authority/projection and require `4 -> 8`.

- [ ] **Step 5: Repeat Task 10 Step 5 for `batch-07`**

Capture/classify final active repository lanes after confirmed HEAD.

- [ ] **Step 6: Repeat Task 10 Step 6 for `batch-07`**

Review eligibility and capture the index baseline.

- [ ] **Step 7: Repeat Task 10 Step 7 for `batch-07`**

Apply only the reviewed final 15-path transaction unstaged.

- [ ] **Step 8: Repeat Task 10 Step 8 for `batch-07`**

Run exact candidate-to-stage/focused/smoke checks.

- [ ] **Step 9: Repeat Task 10 Step 9 for `batch-07`**

Run broad evidence with every supported store unchanged.

- [ ] **Step 10: Repeat Task 10 Step 10 for `batch-07`**

Finalize post evidence, subject, and independent post-edit reviews.

- [ ] **Step 11: Repeat Task 10 Step 11 for `batch-07`**

Materialize the pending event once and make commit A.

- [ ] **Step 12: Repeat Task 10 Step 12 for `batch-07`**

Complete any reviewed repairs and sole materialized closure event while keeping
quiescence unbroken.

- [ ] **Step 13: Repeat Task 10 Step 13 for `batch-07`**

Make commit B; prove active=0/history-owned=100, exact 100-path blob preservation
in Git history, and all Task-10 ten-source checks.

### Task 17: Close The Queue And Hand Off The Archive Queue

**Files:**
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/final/prospective-closeout-transition.json`
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/final/repository-scan.json`
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/final/validators/report.json`
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/final/focused/report.json`
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/final/end-to-end/report.json`
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/final/outcome.json`
- Create: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/final/subject.json`
- Modify: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/execution-index.json`
- Modify: `docs/plans/2026-07-07-yaml-retirement-program.md`
- Modify: `docs/index.md`
- Modify: `docs/workflow_yaml_retirement_execution.md`
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`
- Modify: `docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/execution-ledger.json`

Start from Task 16's validated closed index. Before the final repository
reference scan or any final validator, focused, broad, or end-to-end evidence,
materialize the exact closeout candidate bytes: mark only
`delete_non_survivor_estate` complete and select
`archive_design_delta_yaml_twin` next in the Stage-6 program; update
`docs/index.md`; update its owning routing assertion; create
`final/prospective-closeout-transition.json` with null final-review digests; and
run `project-transition` to render the exact matching live-projection bytes.
The transition's external-change set must equal those four paths in both
directions and bind every exact pre/post state and byte digest. Validate it,
then freeze all nonexcluded bytes. This is a prospective uncommitted candidate,
not an early completion claim. Any later nonexcluded change restarts this
entire Task-17 evidence and review lifecycle.

Before every final validator, focused, broad, end-to-end, review-subject,
staged-closeout, and post-commit gate, validate the immutable Task-2
non-target-source record against all ten live sources. The nine archive/port
mode/blob/byte bindings and protected holdout binding must remain exact. No
final evidence or closeout update may regenerate, replace, or waive that
record.

- [ ] **Step 1: Run the final closed validators**

First capture `final/repository-scan.json` over the frozen 100-target query with
the same raw-byte scanner and exact evidence-root exclusion. Reconcile every
remaining occurrence to the final index's allowed immutable historical/test
rows and require zero active occurrence. Then require zero active paths, seven
path-owning pending-binding events paired
one-to-one with seven non-owning closure events, zero or more valid non-owning
repair events each contained in exactly one closed batch chain, seven closed batches, 100 exact
pre-delete blob IDs, zero unclassified active occurrences, all dependencies
satisfied, empty derived blocking sets, and no unsupported owner/adoption claim.

Both `capture-final-repository-scan` and
`validate-final-execution-index` consume the immutable non-target-source
binding and fail if any of its ten live rows differs. If the fresh final scan
finds an otherwise-active occurrence whose removal would require changing one
of those paths, closeout fails and routes it to that source row's queue owner;
the final validator may not synthesize a disposition or edit.

The `final_validator_report.v1` command set is exactly these four role IDs and
argv arrays, executed from `/home/ollie/Documents/agent-orchestration` with
`PYTHONHASHSEED=0` and `LC_ALL=C.UTF-8`; no fifth command or alias is legal:

```text
capture-final-repository-scan:
  ["python", "scripts/build_retirement_execution_index.py", "capture", "--query", "docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/query.json", "--repository-root", ".", "--evidence-root", "docs/plans/evidence/yaml-retirement/delete-non-survivor-estate", "--repository-scan-out", "docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/final/repository-scan.json"]
validate-final-repository-scan:
  ["python", "scripts/build_retirement_execution_index.py", "validate", "--kind", "repository-scan", "--record", "docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/final/repository-scan.json"]
validate-final-execution-index:
  ["python", "scripts/build_retirement_execution_index.py", "validate", "--kind", "execution-index", "--record", "docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/execution-index.json"]
validate-prospective-closeout-transition:
  ["python", "scripts/build_retirement_execution_index.py", "validate", "--kind", "prospective-closeout-transition", "--record", "docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/final/prospective-closeout-transition.json"]
```

The CLI interface implemented in Task 6 must accept these exact generic flags.
Persist every role's combined output and exit at
`final/validators/logs/<validator-id>.log` and
`final/validators/exits/<validator-id>.exit`; assemble and validate
`final/validators/report.json`. No console-only result counts.

- [ ] **Step 2: Run focused gates**

```text
collect-final-focused:
  ["pytest", "--collect-only", "-q", "tests/test_retirement_state_store.py", "tests/test_retirement_repository.py", "tests/test_retirement_evidence.py", "tests/test_workflow_lisp_procedure_first_migrations.py", "tests/test_workflow_lisp_drain_roadmap_routing.py"]
test-final-retirement-core:
  ["pytest", "-q", "tests/test_retirement_state_store.py", "tests/test_retirement_repository.py", "tests/test_retirement_evidence.py"]
test-final-yaml-routing:
  ["pytest", "-q", "tests/test_workflow_lisp_procedure_first_migrations.py", "tests/test_workflow_lisp_drain_roadmap_routing.py", "-k", "yaml_retirement or retirement_handoff"]
```

Execute these three role IDs/argv arrays, from the same cwd/environment as Step
1, as the exact closed command set for
`final/focused/report.json`, with persistent logs/exits under the sibling
deterministic directories. The report must bind collection and execution rows,
not merely the displayed command block.

- [ ] **Step 3: Run the broad suite in tmux**

```bash
tmux new-session -d -s yaml-retirement-task6-final \
  "cd /home/ollie/Documents/agent-orchestration && pytest -q -rs -n 16 --dist=worksteal --junitxml=docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/final/pytest.junit.xml > docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/final/pytest-rs.log 2>&1; status=\$?; printf '%s\\n' \"\$status\" > docs/plans/evidence/yaml-retirement/delete-non-survivor-estate/final/pytest.exit; exit \"\$status\""
```

Before launching, write final collect-only output/status to
`final/collect.log` and `final/collect.exit`, require zero, and derive/bind the
sorted `final/collected-node-ids.txt`. Run and bind
`final/pytest-temp-root-preflight.json` under the same pytest-8.4.1 executable/
environment immediately before launch. Poll with the `tmux` skill. Bind
all six persistent collection/run raw files plus the preflight record in
`final/outcome.json`, map
every failed/skipped testcase one-to-one to an exact collected node ID, compare
the failures to the owner-confirmed implementation baseline/remediation prefix,
and compare skips to the Task-7 pre-queue baseline advanced through the exact
ordered approved skip-change prefix. Require parsed
collection exit zero and compare the signature table independently to the
owner-confirmed implementation baseline plus the complete cumulative reviewed
remediation set. Require
`outcome=known_failures_matched|approved_failure_subset`; no final validator or
reviewer reads `tmp/`; counts alone are not evidence, and any new/changed,
external-removed, reappeared, or unreviewed missing failure blocks closeout.
If closeout itself removes a queue-owned failure, use the exact optional
`final/failure-remediation.json` plus adjacent two-review lifecycle before
building `final/outcome.json`; otherwise all three optional files are absent.

If closeout itself changes the skipped-node set, use the exact optional
`final/skip-change.json` plus its adjacent specification/quality reviews before
building the outcome; otherwise those three files are absent. This record must
bind the immediately preceding batch-7 accepted skip set. A failure remediation
cannot account for skip drift and a skip-change record cannot account for a
failure.

The final broad candidate binds the unchanged non-target-source record and the
fresh all-ten validation performed for that candidate; test success cannot
override a source mismatch.

- [ ] **Step 4: Run final end-to-end checks**

Use the deterministic disposable root
`/tmp/agent-orchestration-yaml-retirement-final-e2e`, require it absent before
setup, and remove it after bound post-run snapshots. The
`final_end_to_end_report.v1` role/argv set is exactly:

```text
assert-e2e-root-absent:
  ["/usr/bin/test", "!", "-e", "/tmp/agent-orchestration-yaml-retirement-final-e2e"]
surviving-orc-dry-run:
  ["python", "-m", "orchestrator", "run", "tests/fixtures/workflow_lisp/valid/pure_expr_loop_counter.orc", "--entry-workflow", "run-counter", "--dry-run", "--state-dir", "/tmp/agent-orchestration-yaml-retirement-final-e2e/orc-state"]
dashboard-persisted-surface:
  ["pytest", "-q", "tests/test_cli_dashboard_command.py::test_dashboard_handler_projects_persisted_surface_run_contracts[bound]", "--basetemp=/tmp/agent-orchestration-yaml-retirement-final-e2e/pytest-dashboard"]
cleanup-e2e-root:
  ["/usr/bin/rm", "-rf", "--", "/tmp/agent-orchestration-yaml-retirement-final-e2e"]
```

All four run in the displayed order from `/home/ollie/Documents/agent-orchestration` with
`PYTHONHASHSEED=0` and `LC_ALL=C.UTF-8`. The first role proves a surviving `.orc`
precondition proves isolation; the second proves a surviving `.orc` enters
through the CLI/dry-run path; the third proves the dashboard consumes the
persisted typed surface without reopening YAML or `.orc` source; and the fourth
is the bound cleanup. The report rejects any alternate selector, missing/extra
role, nonzero exit, preexisting root, or root left
after cleanup. List the exact isolated mutations in the quiescence record and
require every supported run-root snapshot unchanged. Do not launch a held or
retired YAML workflow. Persist the exact command rows, logs, exits, root
snapshots, and cleanup observations in `final/end-to-end/report.json` and its
deterministic sibling directories. Bind a before/after all-ten validation and
require identical non-target source rows.

- [ ] **Step 5: Obtain holistic specification and quality reviews**

Advance the execution ledger to the staged Task-17-complete candidate and
freeze its immutable generation; the status becomes durable only when the
reviewed closeout commit lands unchanged. Create `final/subject.json` under
`final_review_subject.v1`, binding the closed immutable pre-review index
generation (not a future reading of the live singleton), prospective closeout transition, final repository scan,
validator, focused, end-to-end, broad, protected, and routing inputs plus every
nested persistent log/exit and any final remediation or skip-change
record/review triple. It
also binds the immutable non-target-source record and the fresh validation of
all ten live rows. Its exact four-row nonexcluded candidate manifest
binds the Stage-6 program, docs index, live projection, and routing-test pre/post
bytes; its fixed-evidence manifest closes every already-produced final evidence
byte, and its post-review consuming-path manifest closes the only three later
live logical evidence-root writes plus the two derived immutable review
snapshots. It excludes final-review contents/future commit while enumerating
their deterministic paths. Write exactly `reviews/final-specification.json` and
`reviews/final-quality.json`; both bind that subject and must approve under two
distinct reviewer identities. Top-level review cardinality becomes exactly
eighteen and no other review filename is permitted.

Reviewers check all seven deletion/closure commit pairs, the fourteen mandatory
deletion/closure history events, every optional reviewed repair event, owner
claim boundaries, protected-path preservation, exact v1/current
reconciliation at every commit, broad baseline comparisons, and absence of
family branches in production.

- [ ] **Step 6: Consume final reviews and commit closeout**

After both approvals, populate only the final-review bindings and closeout
status in a new execution-index generation under the exact execution-evidence
root; retain and validate the pre-review request/snapshot bound by the subject; the
prospective transition and every other pre-review evidence byte remain
unchanged. Run `project --check` and require the resulting live
projection bytes equal the already materialized and reviewed file; do not
rewrite any nonexcluded path. Require the staged nonexcluded path/state/digest
set to equal the final subject's exact four-row candidate manifest, and require
the complete staged diff to equal that candidate manifest plus the subject's
fixed-evidence manifest, the review-bound subject bytes, and exactly the closed
post-review consuming-path set. An extra path, missing path,
byte drift, or routing/test rewrite is a hard failure and restarts final scan,
validators, focused/broad/end-to-end evidence, subject, and reviews. Run the
protected guard. Append an exact final remediation triple to the index only
when the reviewed subject binds it; otherwise preserve the remediation prefix
byte-for-byte. Append an exact final skip-change triple only when the reviewed
subject binds it; otherwise preserve the skip-change prefix byte-for-byte.
Require the staged manifest to exclude all ten non-target paths
and validate their exact bindings before commit. Commit and validate both the
closeout index and all ten live non-target sources at HEAD.

The commit marks only `delete_non_survivor_estate` complete and selects
`archive_design_delta_yaml_twin` next because its prerequisite queue is closed.
Do not claim that the archive, either port-source deletion, protected holdout,
or Task 7 parser removal is complete.

## Protected-Path Commit Guard

Task 1 first revalidates its bootstrap-workspace baseline; every later task first
runs `validate-workspace-baseline`. Before every commit, run the Task-1-landed
`build-precommit-control` and `validate-commit-boundary` with the complete
durable subject/review/consuming-record authority. The validator requires the
complete current index to equal the external control's reconstruction, rejects
any baseline-dirty allowed path, prints the NUL-safe complete staged delta for
audit, and supplies the exact transaction directory and precomposed final message.
Set `transaction_id` only from that validated canonical receipt and require it
to match lowercase 64-hex; validate both base/final message bindings and the
final message's embedded control digest before invoking Git.
Invoke the commit only as:

```bash
git -c core.hooksPath=/dev/null --literal-pathspecs commit --only --no-gpg-sign \
  --pathspec-from-file=".git/retirement-commit-controls/${transaction_id}/paths.nul" \
  --pathspec-file-nul \
  --file=".git/retirement-commit-controls/${transaction_id}/final-message.txt" \
  --cleanup=verbatim
```

Immediately afterward, rerun both validators in post-commit mode and require
the new commit tree to equal `expected_commit_tree_oid`, the control's allowed paths to
be the only committed delta, and every unrelated pre-existing staged entry to
remain byte-identical in the index. Remove the transaction directory and rerun
`validate-commit-boundary --reconstruct` with no local control bytes; acceptance
requires byte-identical recreation from durable history. Never invoke an
ambient-index commit or stage anything under `.git/retirement-commit-controls/`.
The command never opens an editor or reads stdin. Under ordinary bound test
configuration, the exact `--file`, `--no-gpg-sign`, and per-command null-hooks
invocation must complete without trailer processing. Deliberate hostile editor,
hook, signing, stdin, and system/global/local Git-configuration injection is
security-only work deferred outside this plan and is not a completion gate. A
missing/empty/mismatched base/final message file or final-message
drift fails before Git runs.

As a redundant named safety subset, print `git diff --cached --name-only`, then
run this literal command. It must print nothing:

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

Never stage, restore, rewrite, format, delete, or use a broad Git staging
command on any workspace-baseline dirty path. Also verify the full dirty-entry
content bindings before and after every mutation/command/review/staging/commit
boundary; verify the seven named protected bindings as the redundant subset
before and after every deletion batch.

## Completion Contract

This plan is complete only when all of the following are fresh facts:

1. the frozen v1 handoff bytes and meaning are unchanged; this approved plan's
   checkbox/status bytes remain immutable; and the closed execution ledger
   binds that exact plan while recording every contiguous task/step transition;
   every mutable materialization has immutable generation-addressed request and
   output snapshots, and every prior reviewed subject remains verifiable after
   the live ledger/index/projection singleton advances; every request is created
   by one deterministic lock-held materialization transaction with exact
   eight-digit generations, canonical-path UTF-8 hash keys, and a persistent
   kernel advisory lock whose ordinary contention and crash recovery validate
   all publication slots;
   there is no separately successful prepared-request phase; the pending,
   repair, and closure preparation helpers are write-free derivation checks and
   only their matching materializer kinds create event bytes; and the four pending-owner kinds use only
   `materialize-pending` with owner-shaped inputs forbidden and pending owner
   fields fixed to their exact null/false schema state;
2. generic production scanners and validators pass both-direction tests and
   contain no family/repository branches; the bootstrap evidence foundation is
   independently reviewed; and the personally owner-adopted preimplementation
   baseline plus every Tasks 3–6 production candidate has one closed durable
   focused report, one focused-plus-broad implementation subject, and exactly
   two reviews over that subject; every batch and final candidate has its
   applicable durable focused evidence; and all candidates have durable broad
   xdist evidence with collection exit zero and an exact stable-signature match,
   computed everywhere through the same closed narrow pytest-temp-prefix
   normalization contract bound to a fresh pytest-8.4.1 runtime preflight with
   raw usable usernames or the exact `unknown` fallback, to the six-row baseline
   minus only cumulative separately
   reviewed in-scope remediations, with no new/changed/external-removed or
   unreviewed missing failure, while every skipped-node change follows the
   exact predecessor-bound separately reviewed skip-change chain;
3. the immutable non-target-source record binds exactly seven archive, two
   port, and one protected-holdout path; the nine archive/port mode/blob/byte
   rows and reused protected binding remain exact at every Tasks 10–16
   pre-gate, subject, staged candidate, commit-A/repair/commit-B HEAD validation, and
   final gate; and a fresh reference requiring one of those sources to change
   fails closed to its queue owner; the immutable workspace baseline fully
   content-binds every pre-existing dirty entry and the complete semantic index,
   rejects same-status byte drift at every boundary, and every commit is proven
   through its durable control trailers and fresh-clone reconstruction to
   contain exactly the external control's allowed delta while excluding and
   preserving any unrelated pre-existing staged entry; Task 1 captures and
   adopts the existing scoped dirty workspace before its first repository write,
   forbids overlap with Task-1 paths, and preserves every captured byte/type/
   existence/index binding through its commit without persisting user content;
4. the reviewed assignment binds exact repository scan, separate occurrence
   and compatibility-fact dispositions, import graph, category input/reviews,
   and counts/digests, while the execution index consumes that exact assignment
   and its reviews; `created_at_commit` is the pre-materialization HEAD rather
   than the containing commit, and it plus the immutable initial ledger/base
   binding remains byte-identical across every index generation;
5. the execution index's active plus path-owning history partitions reconcile
   exactly to the frozen 100-path queue at every commit, every repair/closure
   event is separately non-owning, and all seven reviewed batch sizes
   and import dependencies are exact;
6. every batch freshly scans and classifies its exact content-addressed current
   occurrences, reconciles its persistent pre/post retired and replacement
   channels in both directions, and every active reference is classified by the
   immutable v1 enum then deleted with its source, refined to exact-occurrence
   removal, or rerouted while retained historical/test
   references remain explicitly classified; exact batch-target tombstones
   permit only their planned post-scan absence and no unrelated missing tracked
   file, and every assignment/eligibility repository scan follows the last
   nonexcluded projection/routing/owner commit while later writes remain
   evidence-root-only; the Step-5-to-Step-6 index delta is exactly the permitted
   evidence-root eligibility commit with nonexcluded entries unchanged, and
   every deletion candidate remains worktree-only with the exact post-Step-6
   pre-deletion raw index, tree, entry-stream, and cached-diff identity
   unchanged through subject and both reviews, and Step 11 staging equals the
   reviewed candidate-to-stage simulation exactly;
7. owner-confirmed root scope remains immutable and scope-only, the separate
   initial-root-binding lifecycle covers every and only supported roots, and
   both pending/confirmed lifecycles have their exact durable review subjects,
   review pairs, index consumers, and closed top-level cardinalities, while
   every batch also has its distinct reviewed `0 -> 4 -> 8` pending/confirmed
   owner-lifecycle subject/pair/consumer chain committed before repository
   capture without changing the fixed six eligibility/post-edit/closure reviews,
   and
   every supported root and fresh batch scan is owner-bound or proven identical
   by content-only snapshot digest under unbroken quiescence while timestamp-
   inclusive record digests remain separately bound, every distinct projected
   run has a closed support disposition, and every derived blocking set is
   empty;
8. Git history binds all 100 pre-delete blobs;
9. focused, end-to-end, and broad tmux evidence is recorded with exact failed
   and skipped node IDs from persistent bound `-rs` logs, exit files, JUnit
   reports, collected-node lists, and closed outcome JSON; skipped-node drift
   is either absent or accounted for by its exact reviewed transition; no validator or
   reviewer depends on ignored temporary artifacts;
10. every deletion commit is followed, after zero or more closed non-owning
   reviewed repair commits, by an evidence-only closure commit whose immediate
   predecessor and full chain validate; all
   review artifacts use the exact closed assignment/baseline/batch/final
   filenames, cardinalities, and lifecycle bindings without self-reference,
   every accepted/replaced live review has an append-only content-addressed
   snapshot bound by all historical consumers, and both independent final
   reviews approve; and
11. the exact four-file closeout candidate is frozen by the prospective
    transition before final reference scan/tests, remains byte-identical through
    the reviewed staged manifest, and advances routing only to the Design Delta
    archive queue, leaving the two port sources, protected holdout, and YAML
    frontend removal under their own still-open gates.
