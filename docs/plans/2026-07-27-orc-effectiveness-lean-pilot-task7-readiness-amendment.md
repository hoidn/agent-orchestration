# Lean Pilot Task 7 Readiness Amendment

**Status:** Accepted implementation plan

**Governing design:** `docs/superpowers/specs/2026-07-26-orc-effectiveness-lean-pilot-design.md`

**Governing execution plan:** `docs/superpowers/plans/2026-07-26-orc-effectiveness-lean-pilot.md`

## Purpose

Close the last generic contract gaps between the passing A0 calibration and
the first real-provider A1 smoke. This amendment preserves the four-record
evidence model and the existing `run_block` signature. It adds no worktree,
registry, hardcoded package path, retry loop, or provider-isolation
prerequisite.

Round-1 calibration passed with six unique provider sessions. Its external
controller seal is canonical at
`sha256:ad2570d72a0608173232d53beee7990c0e2afaa198f549bae8769083cc8e7f8f`.
The retained pre-session configuration failure started no provider session and
is excluded from the six-review matrix. No pilot lock, apparatus smoke, or live
A1 attempt exists yet.

## Accepted Contract

### Source identity

`pilot_lock.v1.archive` separates the durable repository identity from its
canonical absolute local repository root. It binds a full commit identity, a
canonical relative source-subtree path, the exact Git tree object at
`commit:subtree`, and the resulting rootless archive digest. The runner
materializes `git archive <commit>:<subtree>` into fresh ordinary directories.
The task binds its canonical source-relative task path; both that archived file
and the controller-staged task asset must match `task.brief_digest`.

This uses the authoritative repository directly. A synthetic snapshot
repository or worktree would add provenance and lifecycle boundaries without
improving content identity.

### Closed apparatus and visibility

`apparatus.asset_manifest` is the exact regular-file tree under the explicit
control root. Missing, extra, duplicate, non-regular, unsafe, or
digest-mismatched nodes fail before `STARTED`.

`apparatus.treatment_asset_paths` is an explicit subset of that manifest.
Only this subset is staged into each treatment's private apparatus root.
Evaluator fixtures, reviewer commands, rubric bytes, and calibration evidence
remain controller-only.

Each treatment binds `source_asset_paths`. Its `source_digest` is the canonical
SHA-256 of the sorted corresponding manifest rows. Its command configuration
must be one of those assets and carries a `provider_policy_digest` equal to the
canonical digest of the locked provider policy.

The pilot environment partition is exact. `PATH` and `PYTHONUNBUFFERED` are
the treatment launcher configuration's noncredential entries; `HOME` and
`TMPDIR` are controller-owned; and `CODEX_HOME` is credential-backed and comes
only from `SecretsManager`. The lock allowlist contains exactly those five
names and names only `CODEX_HOME` as a credential. A treatment configuration
that supplies `CODEX_HOME` itself, or omits the locked provider-policy digest,
fails before launch.

### Review and evaluator binding

The review block binds:

- exactly two stable calibrated reviewer identities;
- `INDETERMINATE_ON_DISAGREEMENT`, with no uncalibrated adjudicator;
- the exact selected-final-file allowlist;
- exact permitted check-evidence names, resolved only as
  `<block-id>/<opaque-arm-label>/<name>` under the locked evidence root;
- rubric and passing-calibration-seal paths plus exact byte digests;
- one evaluator configuration path, exact asset set, and bundle digest; and
- one reviewer-command configuration path, exact asset set, and bundle digest.

Bundle digests are canonical digests of sorted bound manifest rows. Reviewer
execution uses the calibrated provider family, model, effort, CLI identity,
environment contract, tool policy, and timeout; its live three-candidate output
schema is separately bound in the reviewer-command bundle.

`task.profile_digest` is derived, not asserted. It is the canonical digest of
the profile version, task ID/source path/brief digest, source archive digest,
selected final files, permitted check-evidence names, visible-check contract,
product exclusions, and evaluator bundle digest.

Reviewer identities are stable qualification roles and may evaluate distinct
packages or blocks. Every provider session ID is globally fresh across
calibration and live review. Each locked reviewer occupies exactly one slot per
live block; duplicate reviewer coverage within a block fails.

Review ingestion joins the result to the exact package ID, raw canonical
package-manifest digest, reviewer ID, rubric digest, review class, and manifest
candidate-label order. Its unordered pair set must equal
`combinations(candidate_labels, 2)` exactly: calibration's two candidates
require one pair and a live three-candidate result requires all three pairs.
Missing, duplicate, reversed-duplicate, or foreign-label pairs fail closed.

### Smoke boundary

A `VALID` `SMOKE` attempt may produce a blind package after the same archive,
product-freeze, command, task, root, and allowlist validation used for a live
package. It is never reviewed or scored: `review_result.v1.review_class`
remains `CALIBRATION | LIVE`, smoke and live IDs are disjoint, and synthesis
accepts review bindings only for valid live blocks.

### Auxiliary controller artifacts

Source maps, materialization receipts, session ledgers, calibration seals,
evaluator outputs, package manifests, label maps, and review/unblinding
bindings remain explicit content-addressed controller artifacts. They are not
a fifth cross-process record kind. No controller input may be inferred from
CWD, an installed package location, or an undeclared environment default.
Each smoke/live label map occupies the immutable deterministic path
`label-maps/<package-id>.json` beneath the locked evidence root; atomic
exclusive publication rejects any preexisting node or symlink traversal and
never replaces an earlier block's map.

### Pilot-specific controller boundary

Task 7 adds no public experiment API or reusable framework. The existing
`scripts/experiments/lean_pilot.py` remains a thin facade and gains only
`prepare` and `execute` commands. Implementation is divided by existing
responsibility among four private modules, each at most 500 physical lines:

- `_pilot_prepare.py`: closed source-map validation, Git-object reads,
  external control-root materialization, calibration-seal validation, and
  `pilot_lock.v1` authoring;
- `_pilot_evidence.py`: frozen projected-product copies, hidden-evaluator
  execution, canonical evaluator evidence, and blind-package construction;
- `_pilot_review.py`: calibrated reviewer command/environment validation,
  fresh-session launch/finalization, review ingestion, and canonical
  review/unblinding bindings; and
- `_pilot_controller.py`: exact attempt-prefix loading and the bounded
  smoke/live/review sequence.

`prepare` requires explicit source-map, repository-root, full-revision,
fresh-control-root, fresh-evidence-root, calibration-seal, and lock-output
paths. `execute` requires the immutable lock plus explicit disjoint work,
evaluation-copy, package, and canonical reviewer-environment paths. Neither
command infers one of these inputs.

`experiments/orc_effectiveness/lean_pilot/apparatus-source-map.json` is the
single closed authoring map. Repository assets are read from one caller-named
full Git commit, never the live working tree. It maps the accepted seventeen
treatment-visible files to `treatment_driver.py`, `task_loop.orc`,
`prompts/*.md`, the four flat control manifests, `task.md`, and
`treatments/{direct,coordinator,orc}.json`.

The same map classifies these controller-only assets:

- the rubric, passing calibration seal, and tracked calibration lock beneath
  `review/`;
- `evaluation/config.json`, the nanoBragg evaluator module at its existing
  repository-shaped relative path, and its runtime fixture closure
  (`cases.json`, all expected tensor files, and all hidden input JSON files);
  and
- `review/reviewer-command.json` plus
  `review/review-result.schema.json`.

Keeping the evaluator module and fixtures at repository-shaped destinations
preserves its existing `__file__`-relative lookup without copying logic. The
live reviewer schema is exact for three candidates, five dimensions per
candidate, and three pairwise results. The calibrated invocation schema
remains calibration evidence and is not silently reused as the live schema.

### Bounded controller and stop semantics

Before `STARTED`, any source, control-root, calibration, environment, CLI, or
join mismatch consumes no attempt. A non-`VALID` smoke launches no live block
and routes `STOP_APPARATUS_NOT_VIABLE`. A `VALID` smoke may contain
treatment-specific failure outcomes; after successful hidden-evaluator and
package mechanics, those outcomes do not block the live prefix.

Every valid smoke/live product is re-frozen, copied under its opaque arm label
to a fresh controller-owned evaluation root, and re-frozen again before the
verified hidden evaluator runs. Evaluator `PASS` or `FAIL` is candidate
evidence. If evaluator execution, its output contract, or blind-package
construction fails after `run_block` has already committed `VALID`, the
controller must not rewrite that attempt or fabricate
`STOP_APPARATUS_NOT_VIABLE`. It preserves the incident and all existing
artifacts, emits no pilot summary, and requires a separately locked pilot.

`INVALID`, `ABORTED`, and surviving `STARTED` live records consume their
ordered IDs and are never rerun. No next ID launches until process-group
quiescence is established. Collection stops immediately at the third valid
live block or after the fifth live ID. If fewer than three valid blocks remain,
every valid block is still reviewed before the truthful
`STOP_INSUFFICIENT_VALID_BLOCKS` summary.

Each live reviewer slot gets one immutable launch intent and at most one
provider start. Pre-intent validation may be corrected without consuming a
session. After provider start, a complete retained terminal transport may be
finalized provider-free, but the slot is never relaunched; an incomplete
session halts without unblinding or summary. All required initial reviews and
canonical review bindings are sealed before any label-map content is read to
publish the canonical unblinding bindings.

## Execution Plan

### Task 1: Amend the contracts with RED tests

- Extend `pilot_lock.v1` with the source-tree, task-source,
  treatment-visibility/source-closure, and review/evaluator bundle fields above.
- Add semantic checks for every derived digest and manifest subset.
- Require the closed control-root tree and treatment/controller visibility
  partition.
- Keep all production modules at or below 500 physical lines.

Both-direction tests cover valid values plus path traversal, missing/extra
assets, wrong Git tree, wrong archived task, bundle/source/profile digest drift,
controller-only leakage, and provider-policy mismatch.

### Task 2: Implement subtree materialization and preflight

- Resolve the locked commit and subtree to the exact locked Git tree before
  `STARTED`.
- Materialize the rootless subtree archive into each fresh arm workspace.
- Recheck archive and task bytes before launch.
- Stage only `treatment_asset_paths`.
- Preserve all existing root, command, environment, start-skew, quiescence,
  checksum, and call-bound guards.

### Task 3: Correct package and review semantics

- Accept only locked `VALID SMOKE` or locked `VALID LIVE` package lineage.
- Derive caller-supplied final-file/check-evidence mappings from the lock and
  reject any difference.
- Bind the expected reviewer ID during ingestion.
- Retain global session-reuse rejection while allowing stable reviewer IDs on
  distinct blocks.
- Require exact package-label order and complete unordered pair coverage for
  both the two-candidate calibration and three-candidate live schemas.
- Reject duplicate live review sessions again during deterministic synthesis.

### Task 4: Materialize and validate the prospective apparatus

- Add the closed apparatus source map, evaluator configuration, calibrated
  reviewer-command configuration, and exact live output schema.
- Implement the four private controller modules and thin `prepare`/`execute`
  CLI wiring described above without adding a public export or framework.
- Use the explicit source map to build a fresh external control root.
- Copy and verify every treatment, task, evaluator, rubric, calibration, and
  reviewer-command asset.
- Generate the complete manifest, visibility subset, source closures, and
  bundle digests before authoring `pilot_lock.v1`.
- Revalidate the calibration seal and calibrated execution contract.
- Run hidden evaluation only on fresh verified copies of frozen products.
- Publish per-block label maps, sealed review bindings, and later unblinding
  bindings at their deterministic immutable paths.
- Run a provider-free preflight and actual-launcher parity check.

### Task 5: Review and verification gate

Run the narrow contract, workspace, runner, evaluation, reporting, treatment
parity, controller-source, evaluator, reviewer, bounded-sequence, CLI, and
module-layout suites first. Provider-free behavioral tests cover both
credential partitions, both candidate-count pair joins, failed smoke, the
third-valid stop, five-attempt shortfall, evaluator failure versus evaluator
apparatus defect, session reuse/partial launch, and pre-unblinding ordering.
Obtain one scoped independent contract/code review. Run the affected broad
suite in tmux with
`pytest -q -n 16 --dist=worksteal`. Do not launch the real-provider smoke until
all gates are green.

### Task 6: Resume Task 7 continuously

Freeze the pilot lock, execute exactly one real-provider smoke, then run the
ordered live prefix until three valid live blocks accrue or five attempts are
consumed. Prepare evaluator evidence and blind packages immediately for every
valid attempt, but delay live review until denominator collection is complete.
Use the two calibrated reviewer identities in fresh sessions, seal all review
bindings before unblinding, create the deterministic summary, obtain the final
evidence review, and route the truthful terminal status without expanding the
claim. Apply the post-`VALID` apparatus-defect preservation rule above rather
than mutating committed evidence.
