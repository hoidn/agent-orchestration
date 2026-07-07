# Parent-Callable Stdlib Backlog-Drain Compile/Smoke Regression Architecture

Status: draft implementation architecture (fourteenth re-entry revision,
2026-07-06; blocked-recovery revision after the thirteenth revision's
blocker-verification slice was executed and stopped `BLOCKED` on a live
evidence-route failure the thirteenth revision did not anticipate: the
compile-time reference-family evidence resolver selected the newest
versioned drain root (`…-R46`) on `drain-summary.json` presence alone, and
that root lacked the required `design-gaps/` summary directory, so the
Section-14 compile, the parent-callable smoke, and the reference-family
conformance lane all failed closed on
`reference_family_conformance_input_missing` before any owned closure step
could run. That blocker is resolved on the current checkout by landed
commit 3b62f1c (`Skip incomplete reference-family evidence roots`), which
narrows resolver candidacy in
`orchestrator/workflow_lisp/build.py::_reference_family_versioned_roots` to
versioned roots providing both `drain-summary.json` and `design-gaps/`; the
resolver now selects the complete `…-R42` root, and fresh verification this
revision pass shows the entire owned acceptance surface green — compile
exit 0 (fingerprint `2524aa25a3869738`), parent smoke 5 passed,
reference-family conformance 17 passed, parity selector 22 passed, drain
stdlib 63 passed, runtime smoke 1 passed — with exactly the nine
already-routed non-parity residuals in the broad build-artifacts lane.
This revision retires the R49 blocker-verification detour: the resolver
completeness rule joins the landed read-only baseline (Gate D below, kept
for the record), evidence-route regressions get an explicit residual route,
and the slice returns to the closure ladder — fresh re-verification of the
owned surfaces, classification of the known residuals, and closure. No
repair scope is added or widened.)
Design gap id: `workflow-lisp-runtime-native-drain-parent-callable-stdlib-backlog-drain-compile-smoke-regression`
Target design: `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
Baseline context: `docs/design/workflow_lisp_frontend_specification.md`
Command/effect authority: `docs/design/workflow_command_adapter_contract.md`

## Scope

This architecture closes exactly the selected regression: the Section-14 CLI
compile of `lisp_frontend_design_delta/drain::drain` and the parent-callable
smoke acceptance surfaces required by target-design Sections 11, 13.4, and 14
were red at one remaining checked-evidence coherence link (Gate C), and —
as the R49 blocker verification proved — subsequently at one
evidence-route input link (Gate D). As of this (fourteenth) revision both
are repaired on the current checkout: the sanctioned full-manifest
regeneration has been executed and verified fresh, and the resolver
completeness rule has landed at HEAD. The slice's remaining work is fresh
re-verification of the owned surfaces, classification of the known
non-parity residuals in the broad build-artifacts lane per `Residual
Failure Routing`, and closure. The repaired gates, kept for the record:

- **Gate C — stale derived parity evidence versus the current checked parity
  targets manifest.** The reference-family conformance profile
  (`orchestrator/workflow_lisp/reference_family_conformance.py::_reconcile_parity_surface`,
  raised through `build.py:1630` as
  `[reference_family_conformance_invalid] design-delta reference-family
  conformance profile failed: reference_family_parity_report_invalid`)
  validates the derived parity report
  `artifacts/work/review-parity-check/design_delta_parent_drain.json` against
  the checked targets manifest
  `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
  via `migration_parity.validate_report_for_target`, which requires the
  report's `target_identity` to match the identity rebuilt from the current
  manifest exactly — including `target_manifest_sha256`, the SHA-256 of the
  manifest file bytes. The checked report (generated 2026-06-25 by the
  sanctioned `python -m orchestrator migration-parity` generator) pins
  `sha256:93c8e5…`, the digest of the committed (HEAD) manifest. The working
  tree carries an in-flight manifest edit (digest `870b5b…`) that renames two
  runtime-audit transition expectations to the names the live family source
  actually declares and routes through
  (`lisp_frontend_design_delta/transitions::write-drain-status-runtime-native`,
  `…::record-blocked-recovery-outcome-stdlib`, both present in
  `workflows/library/lisp_frontend_design_delta/transitions.orc`). Validation
  therefore fails closed with `target_identity.target_manifest_sha256 does
  not match current selected target`. The derived report is the stale
  artifact; the manifest edit is coherent with live authored evidence; the
  validation is a live contract.

- **Gate D — resolver-selected incomplete versioned evidence root (the R49
  blocker), repaired at HEAD.** The reference-family evidence resolver
  (`orchestrator/workflow_lisp/build.py::_reference_family_versioned_roots`,
  consumed via `_resolve_reference_family_evidence_paths`) selects the
  newest versioned drain root as the source of the conformance profile's
  required evidence inputs, including the `design_gap_summary_root`
  (`<artifact_root>/design-gaps/`) consumed by
  `build_reference_family_conformance_profile`. Before commit 3b62f1c,
  candidacy required only `drain-summary.json`, so the resolver selected
  `artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R46/`, whose
  `design-gaps/` directory does not exist; the compile then failed closed
  with `reference_family_conformance_invalid:
  reference_family_conformance_input_missing`, blocking the entire owned
  acceptance ladder (R49 blocked progress report, 2026-07-06). Commit
  3b62f1c (`Skip incomplete reference-family evidence roots`) narrows
  candidacy to roots providing both `drain-summary.json` and
  `design-gaps/`, so incomplete roots (`…-R45` through `…-R47` on this
  checkout) are skipped and the resolver selects the complete `…-R42`
  root. That completeness rule is landed read-only baseline for this
  slice: re-litigating it, backfilling `design-gaps/` into an incomplete
  runtime-owned root by hand, or forcing selection of a specific root is
  out of scope, and any future evidence-route regression routes out per
  `Residual Failure Routing`.

The slice's repair was to regenerate the derived parity evidence for the
full stale-digest coherence class under
`artifacts/work/review-parity-check/` — the JSON report, markdown report,
and index row for every family whose checked report was pinned to a digest
other than the current `parity_targets.json` digest (all three manifest
families, `cycle_guard_demo`, `design_plan_impl_stack`, and
`design_delta_parent_drain`), plus the shared `index.json`,
`gate_evaluation.json`, and generator-owned logs — through one full-manifest
invocation of the sanctioned `migration-parity` generator against the
current checked targets manifest. The manifest digest is manifest-wide, so
any manifest edit invalidates every family report in the shared root at
once; regenerating only one family cannot reconcile the shared surface and
the generator correctly refuses to persist it. That regeneration has been
executed and holds: the shared root is coherent, the conformance profile's
migration-parity surface reconciles (the `design_delta_parent_drain` JSON
validates against the current target identity; JSON, markdown metadata, and
index row agree), and the Section-14 compile and the focused feasibility
selectors are green. The twelfth revision's expectation that the broad
build-artifacts selector would also go green was wrong: nine residual
failures remain in that lane, all non-parity, all in surfaces read-only for
this slice; they are enumerated in the evidence section below and routed in
`Residual Failure Routing`.

The parity surface is a coherence gate, not a promotion gate: the checked
report records `non_regressive: false` and
`eligible_for_primary_surface: false` (missing runtime-audit and dry-run
evidence keeps them false), and `_reconcile_parity_surface` passes the
surface on validation plus three-way agreement regardless of those values.
Restoring the compile does not require, and must not fake, non-regressive or
promotion-eligible status (target design Sections 13.4/14: compile/smoke
success is not YAML-primary promotion).

Everything earlier revisions repaired or scoped as landed baseline stays
landed baseline to keep green, not repair surface: the three-manifest
checked-input rebaseline now in the working tree
(`design_delta_parent_drain.boundary_authority.json`,
`design_delta_parent_drain.value_flow_census.json`,
`design_delta_parent_drain.resume_plumbing_retirement.json`), the
imported-module workflow-call resolution, the loop-body structured-control
flattening and its runtime execution, the carrier-free parent terminal
boundary, the drain-stdlib test-vehicle alignment, the lowered
`std/drain::backlog-drain` callable-child owner boundary (commit 08ece19),
and the reference-family evidence-root completeness rule (commit 3b62f1c;
Gate D above). Re-litigating, reverting, or re-implementing any of them is
out of scope.

Out of scope, unchanged: retirement of `run-state` carriers, fixture-mirror
sync, selector adapter redesign, provider request-record authoring, gap
re-entry convergence, done-review policy, private `PhaseCtx` boundary work,
any YAML-primary promotion claim, any change to reconciliation, validation,
conformance-profile, or parity-gate logic, and any change to the in-flight
working-tree edits of checked manifests this slice does not own.

## Evidence (2026-07-06, current checkout, fresh post-3b62f1c output)

- The evidence route is repaired. The live resolver
  (`_resolve_reference_family_evidence_paths`) now selects the complete
  `LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R42` root:
  `drain_summary_path` and `design_gap_summary_root` both exist under
  `artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R42/`, and the
  incomplete `…-R45`/`…-R46`/`…-R47` roots (missing `design-gaps/` and/or
  `drain-summary.json`) are no longer candidates (fresh probe this
  revision pass). The `reference_family_conformance_input_missing` failure
  the R49 blocked report proved is no longer reproducible.
- The parity repair landed and holds. The earlier blocked run executed the sanctioned
  full-manifest regeneration (`python -m orchestrator migration-parity
  --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json
  --output-root artifacts/work/review-parity-check`), and fresh verification
  in this revision pass confirms all three family reports
  (`cycle_guard_demo.json`, `design_plan_impl_stack.json`,
  `design_delta_parent_drain.json`) bind
  `target_identity.target_manifest_sha256` to the current working-tree
  manifest digest
  `sha256:870b5b78b2f9b21b24334b50698a527afa8a187050b3eab2161437c31f6517f8`;
  no report in the shared root still pins the stale HEAD digest `93c8e5…`.
  Generator-computed values: `cycle_guard_demo` `non_regressive=true`,
  `design_plan_impl_stack` `non_regressive=true`,
  `design_delta_parent_drain` `non_regressive=false` (runtime-audit JSONL
  absent on this checkout, as expected); `gate_evaluation.json` is in
  `advisory` mode. Nothing was fabricated.
- The Section-14 CLI compile (`python -m orchestrator compile
  workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow
  lisp_frontend_design_delta/drain::drain` with the checked provider,
  prompt, and command-boundary externs) exits 0 (fresh run this revision
  pass; build fingerprint `2524aa25a3869738`, lowering route `wcc_m4`), with
  no `reference_family_conformance_invalid` diagnostic of any inner code.
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k
  "selected_item_stdlib or parent_drain_build_and_execution_smoke" -q`:
  5 passed, 88 deselected (fresh). The Section-13.4 parent-callable
  execution smoke is green.
- Green guards (fresh): `tests/test_workflow_lisp_migration_parity.py -k
  "design_delta_parent_drain or adapter_census or boundary_authority" -q`
  (22 passed), `tests/test_workflow_lisp_reference_family_conformance.py -q`
  (17 passed), `tests/test_workflow_lisp_drain_stdlib.py -q` (63 passed),
  `tests/test_lisp_frontend_autonomous_drain_runtime.py -k
  "design_gap_runtime_smoke" -q` (1 passed).
- `tests/test_workflow_lisp_build_artifacts.py -k "design_delta_parent_drain
  or boundary_authority or adapter_census" -q`: 9 failed, 80 passed, 94
  deselected (fresh this revision pass; the deselected count grew by one
  because commit 3b62f1c added a resolver-completeness test). None of
  the nine failures is a parity-surface failure; they fall into exactly two
  verified classes, both in surfaces this slice holds read-only:
  - **Run-state bridge retirement status (4 tests).**
    `test_design_delta_parent_drain_imported_backlog_drain_build_artifacts_record_derived_child_phase_binding`
    expects `private_compatibility_bridge_inputs == ("run_state_path",)`
    while the live build emits `()`;
    `test_design_delta_parent_drain_boundary_authority_report_records_generated_and_managed_path_evidence`
    expects generated-internal inputs the live boundary-authority report no
    longer records outside the managed write-root subset;
    `test_design_delta_parent_drain_resume_plumbing_retirement_report_records_drain_run_state_bridge_as_checked_compatibility`
    expects `transitions.resource.drain_run_state` as checked
    compatibility/`BLOCKED` while the live report marks it `RETIRED`; and
    `test_design_delta_parent_drain_default_resume_report_marks_live_run_state_bridges_blocked_or_historical_only`
    asserts that row is absent from `cleanup_candidates` while the live
    report exposes it with `cleanup_action=REMOVE_COMPATIBILITY_ALLOWLIST`.
    The live lowering has retired the drain run-state bridge; the test
    contract still encodes the pre-retirement compatibility shape.
  - **Reference-family completed-gap fixture evidence (5 tests).**
    `test_design_delta_parent_drain_build_emits_reference_family_conformance_profile`
    fails in its tmp fixture workspace with
    `reference_family_conformance_invalid:
    reference_family_completed_gap_artifact_missing`, raised by
    `_reconcile_completed_gaps`
    (`reference_family_conformance.py:517-665`) over the evidence the
    `_aligned_reference_family_*` fixture helpers construct; the four
    negative tests
    (`test_design_delta_parent_drain_build_rejects_reference_family_completed_gap_summary_mismatch`,
    `…_rejects_reference_family_parity_surface_mismatch`,
    `…_rejects_reference_family_invalid_parity_report`,
    `…_rejects_reference_family_malformed_parity_markdown`) now fail earlier
    on the same completed-gap condition and no longer isolate the parity
    diagnostics they assert. The aligned fixture helpers are stale against
    the live completed-gap reconciliation contract; the real-repo compile
    passes the same gate.
  Repairing either class requires editing test expectations/fixture helpers
  or family lowering/report behavior — read-only surfaces here — so both are
  routed in `Residual Failure Routing`, not absorbed.
- Live mechanism knowledge, retained for any future manifest edit:
  single-target regeneration fails closed while any shared-root report pins
  a stale manifest digest. `run_migration_parity`
  (`migration_parity.py:875-925`) regenerates only the selected targets but
  then calls `_validated_gate_rows_for_targets(all_targets, …)`
  (`migration_parity.py:950-973`), which loads the existing on-disk report
  for each unselected family from
  `artifacts/work/review-parity-check/<family>.json` and validates it via
  `_validate_report_for_gate` (`migration_parity.py:699`) /
  `_require_exact_mapping_match` (`migration_parity.py:2655`) against the
  current manifest; `write_reports()` runs only after aggregate validation
  succeeds (`migration_parity.py:925`). This validate-all-before-write
  behavior is a live coherence contract of the shared index, not a defect to
  patch around: the sanctioned repair for a stale-digest class is one
  full-manifest generator invocation without a `--target` filter. The
  bootstrap circularity — the generator's compile evidence command hitting a
  red conformance gate — is deliberately handled by
  `migration_parity._recover_compile_outputs_from_failed_conformance`
  (`migration_parity.py:2800`), which accepts a compile that failed only on
  `reference_family_conformance_invalid` when its build manifest matches the
  candidate source digest and required artifacts exist. Using that route is
  in-contract; editing it is not.

## Ownership

The derived parity evidence under `artifacts/work/review-parity-check/` for
the full stale-digest coherence class — the `<family>.json` and
`<family>.md` reports for `cycle_guard_demo`, `design_plan_impl_stack`, and
`design_delta_parent_drain`, the shared `index.json` and
`gate_evaluation.json`, and the generator-owned logs under `logs/` — is this
slice's repair surface. These files are
untracked, generator-owned derived verification evidence: they are written
only by the sanctioned `migration-parity` generator, never hand-edited, and
they carry fail-closed freshness bindings (`target_manifest_sha256`, log and
artifact digests) to the exact checked inputs they were generated against.
Per target design Section 10 they are verification vehicles, never semantic
authority over compiled evidence.

`workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json` is a
read-only checked compile input for this slice, in its current working-tree
form: the in-flight runtime-audit transition renames are coherent with the
live family source and are preserved as-is. This slice neither reverts the
edit to match the stale report (that inverts evidence authority) nor extends
it. If implementation finds a manifest row incoherent with live compiled or
authored evidence, that is routed to the owning lane, not silently repaired
here.

`orchestrator/workflow_lisp/migration_parity.py` (target loading, target
identity, report generation, `validate_report_for_target`,
`compute_non_regressive`, waiver rules, and the failed-conformance compile
recovery), `orchestrator/workflow_lisp/reference_family_conformance.py` (the
conformance profile and its parity-surface reconciliation), and
`orchestrator/workflow_lisp/build.py` (evidence-path resolution — including
the versioned-root completeness rule landed by commit 3b62f1c — and the
conformance gate raise) are read-only contract authority for this slice. The
fail-closed parity-surface validation is the live enforcement of
target-design Sections 13.4/14 (parity evaluates the public contract without
treating rendered files as semantic authority); weakening, reordering, or
special-casing it is forbidden.

The three rebaselined checked manifests
(`design_delta_parent_drain.boundary_authority.json`,
`design_delta_parent_drain.value_flow_census.json`,
`design_delta_parent_drain.resume_plumbing_retirement.json`), the family
profile and other checked externs files, all compiler/lowering/stdlib/`.orc`
family sources, and the test suites are read-only for this slice, kept green
through their existing guards.

Versioned run roots under `state/**` and `artifacts/work/LISP-*/**`
(including the R42 drain summary the diagnostic anchors to) are runtime-owned
evidence, never hand-editable.

`docs/design/workflow_command_adapter_contract.md` governs any touched
script, command step, command-boundary row, certified adapter, or
runtime-native transition decision in this slice (none are expected; the
generator is an existing sanctioned CLI surface, not a new adapter).

## Contract

### Parity Evidence Regeneration (Gate C)

The migration-parity surface of the reference-family conformance profile must
reconcile against the current checked targets manifest: acceptance is a green
Section-14 compile (exit 0), not the first diagnostic disappearing.
The regenerated evidence must satisfy the unmodified validation chain —
`validate_report_for_target` (exact `target_identity` match including
`target_manifest_sha256`, gate-owned-field absence, recomputed
`non_regressive` agreement, evidence-freshness digest checks), markdown
metadata parsing, and the JSON/markdown/index three-way agreement — under the
unmodified conformance-profile logic.

Regeneration rules:

- The whole stale-digest coherence class is regenerated in one full-manifest
  generator invocation against the current working-tree
  `parity_targets.json` bytes, so every family's pinned
  `target_manifest_sha256`, the embedded `runtime_audit_artifacts` identity
  rows, and all log/artifact digests bind to the same checked inputs the
  compile-time validation will rebuild, and the generator's
  validate-all-before-write aggregate check passes as designed.
- `non_regressive` and `eligible_for_primary_surface` take whatever values
  the unmodified generator computes from real evidence. With the runtime
  audit JSONL absent on this checkout, `non_regressive` remains `false` and
  the derived primary surface remains `yaml`; that is a passing coherence
  surface and must not be "improved" by fabricating audit, dry-run, or waiver
  evidence.
- The generator's compile evidence command may be recovered through the
  existing failed-conformance recovery route while the gate is red; the
  recovered build must be a real compile of the current candidate source
  (matching source digest and required artifacts), not a stale or foreign
  build root.
- No hand edit of any file under `artifacts/work/review-parity-check/` — not
  the sha fields, not the markdown metadata block, not the index row.
- Regenerating the other manifest families (`cycle_guard_demo`,
  `design_plan_impl_stack`) is in scope exactly because their reports share
  the same stale manifest digest: the manifest edit invalidated them in the
  same stroke, and the outside-uses rule assigns their same-tranche
  regeneration to this slice. Their regenerated values are whatever the
  unmodified generator computes from their real evidence — this slice makes
  no claim about, and must not manipulate, their `non_regressive` or
  promotion status.
- Regeneration must not extend past the shared output root
  `artifacts/work/review-parity-check/` or past the families declared in the
  current checked manifest.

### Rule For Outside Uses

The derived parity evidence and the checked targets manifest are consumed
outside this gap's files: the Section-14 compile's conformance gate
(`build.py` evidence-path constants), the feasibility smoke tests, the
design-delta build-artifacts lane, the migration-parity test lane, the
reference-family conformance test lane, and the post-WCC inventory surface
all resolve the same paths. One rule for all of them, and for future slices:

- derived parity evidence under `artifacts/work/review-parity-check/` is
  written only by the sanctioned `migration-parity` generator; consumers
  treat it as freshness-bound verification evidence, never as semantic
  authority, and never hand-edit it to satisfy a gate;
- the checked targets manifest is the identity anchor: any edit to
  `parity_targets.json` bytes — including formatting — invalidates every
  derived report pinned to its digest, and the slice that lands such an edit
  owns regenerating the affected family reports in the same tranche (this
  gap exists because the in-flight transition-rename edit did not);
- runtime-audit expectation rows in the targets manifest must name
  transitions the live family source declares and routes through; aligning
  those rows to live evidence is legitimate, aligning live evidence to stale
  rows is not;
- no consumer may satisfy a parity-surface failure by reverting checked
  manifest edits to match stale derived evidence, faking freshness digests,
  fabricating non-regressive/waiver/audit evidence, or weakening
  `validate_report_for_target`, `_reconcile_parity_surface`, or the
  conformance gate; and
- parity coherence green is not promotion: `non_regressive`,
  `eligible_for_primary_surface`, and primary-surface derivation remain owned
  by the migration-parity and promotion gates (target design Section 15).

## Command Adapter And Runtime-Native Policy

No new command adapter, script, inline Python/shell, stdout protocol, report
parsing, pointer authority, or committed JSON-rewrite tooling may be
introduced for this repair. The regeneration uses the existing sanctioned
`python -m orchestrator migration-parity` CLI surface exactly as recorded in
the checked report's `generated_by` provenance. Existing declared backends
and command-boundary rows keep their current shapes per
`docs/design/workflow_command_adapter_contract.md`; no `retirement_status`,
adapter-contract, or runtime-native promotion change is in scope.

## Allowed Shapes

- Regenerating the JSON and markdown reports for all three manifest families
  (`cycle_guard_demo`, `design_plan_impl_stack`,
  `design_delta_parent_drain`), the shared
  `artifacts/work/review-parity-check/index.json` and
  `gate_evaluation.json`, and the generator-owned logs, exclusively through
  one full-manifest invocation of the sanctioned `migration-parity`
  generator against the current checked targets manifest.
- Relying on the existing failed-conformance compile-recovery route while the
  gate is red, unmodified.
- Verifying the repair exclusively through the unmodified conformance gate
  and the existing test lanes (fresh compile and selector output).
- Classifying any post-regeneration residual failure in the broad lanes and
  routing it per `Residual Failure Routing` instead of absorbing it.

## Forbidden Shapes

- Hand-editing anything under `artifacts/work/review-parity-check/` —
  including patching `target_manifest_sha256`, freshness digests, markdown
  metadata, or index rows to match the current manifest without regenerating.
- Reverting or reformatting
  `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
  (in whole or in part) to make the stale report's pinned digest match, or
  extending that manifest beyond its current working-tree content.
- Editing `migration_parity.py`, `reference_family_conformance.py`,
  `build.py`, or any validation/loader logic to change parity-surface
  behavior, ordering, or strictness — including widening the
  failed-conformance recovery, skipping `validate_report_for_target`,
  softening `_require_exact_mapping_match`, tolerating digest mismatches, or
  removing the conformance gate raise.
- Fabricating evidence to flip `non_regressive` or promotion eligibility:
  hand-authoring runtime-audit JSONL, dry-run evidence, or waivers; or
  claiming YAML-primary promotion from compile/smoke success.
- Editing the three rebaselined checked manifests, the family profile, the
  checked externs, any compiler/lowering/stdlib/`.orc` source, or any test
  expectation to influence the conformance outcome.
- Hand-editing run-state, run-root, or drain-summary evidence; rereading
  rendered summaries, reports, pointer files, stdout, or debug YAML as
  semantic authority.
- Absorbing unrelated red surfaces (fixture-mirror sync, selector adapters,
  run-state carrier retirement, missing runtime-audit evidence production)
  into this slice because the compile now reaches them.

## Acceptance Conditions

This slice is accepted when, on the current checkout, all of the following
hold with fresh command output:

- the live evidence resolver
  (`build.py::_resolve_reference_family_evidence_paths`) selects a
  versioned root providing both `drain-summary.json` and an existing
  `design-gaps/` directory (on this checkout `…-R42`); if it instead
  selects an incomplete root or finds no candidate, that is an
  evidence-route regression routed per `Residual Failure Routing`, and
  this slice stops rather than backfilling runtime-owned evidence or
  forcing selection;
- the Section-14 CLI compile of
  `workflows/library/lisp_frontend_design_delta/drain.orc` with entry
  `lisp_frontend_design_delta/drain::drain` and the checked provider,
  prompt, and command-boundary externs exits 0, with no
  `reference_family_conformance_invalid` diagnostic of any inner code —
  including `reference_family_parity_report_invalid`,
  `reference_family_parity_report_missing`,
  `reference_family_parity_surface_mismatch`, and
  `reference_family_primary_surface_authored` (target design Section 14);
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k
  "selected_item_stdlib or parent_drain_build_and_execution_smoke" -q`
  passes in full (5 tests; the parent smoke is the Section-13.4
  parent-callable execution surface);
- `tests/test_workflow_lisp_build_artifacts.py -k "design_delta_parent_drain
  or boundary_authority or adapter_census" -q` is run fresh, no failure in
  it is a parity-surface failure (`reference_family_parity_report_invalid`,
  `reference_family_parity_report_missing`,
  `reference_family_parity_surface_mismatch`,
  `reference_family_primary_surface_authored`) or a failure introduced by
  this slice's regeneration, and every failure maps to a residual class
  already routed in `Residual Failure Routing` (on this checkout: the nine
  known failures in the run-state-bridge-status and
  completed-gap-fixture-evidence classes). The lane going fully green is not
  required for closure — its non-parity residuals are owned by other lanes —
  but a failure that matches no routed class blocks this slice until it is
  diagnosed and either repaired (if in scope) or routed with fresh evidence;
- the green guard lanes stay green:
  `tests/test_workflow_lisp_migration_parity.py -k
  "design_delta_parent_drain or adapter_census or boundary_authority" -q`
  (22 passed baseline), `tests/test_workflow_lisp_drain_stdlib.py -q` (63
  passed baseline), `tests/test_lisp_frontend_autonomous_drain_runtime.py -k
  "design_gap_runtime_smoke" -q` (1 passed baseline), and
  `tests/test_workflow_lisp_reference_family_conformance.py -q` (17 passed
  baseline);
- every regenerated report in the shared root binds to the current manifest
  digest (no report under `artifacts/work/review-parity-check/` still pins
  `93c8e5…`), and each report's recorded values are generator-computed from
  real evidence: no family's `non_regressive` or promotion eligibility was
  flipped by fabricated audit, dry-run, or waiver evidence, and each
  family's JSON, markdown metadata, and index row agree;
- the change is bounded: no tracked file is modified by this slice — the
  repair writes only the untracked generator-owned parity evidence under
  `artifacts/work/review-parity-check/` — and the in-flight working-tree
  edits to `parity_targets.json` and the three rebaselined checked manifests
  are preserved byte-for-byte; and
- no validation logic, conformance-profile logic, recovery route, loader
  rule, gate, source workflow, or test expectation was edited, widened, or
  weakened to achieve the above.

When the conditions above are green, the gap closes as done under
target-design Sections 11/13.4/14 for the compile and parent-smoke surfaces
it owns. If a fresh in-scope failure appears in a surface this slice touched,
it is this slice's regression to fix before ending. If, after the parity
surface reconciles, the same conformance profile fails closed on another
stale *derived* evidence link of the same checked-evidence coherence class,
diagnosing and regenerating that link through its sanctioned generator is in
scope for this slice; anything requiring a checked-manifest, logic, or
source change routes out per `Residual Failure Routing`.

## Residual Failure Routing

If a broad rerun still fails after the focused conditions pass, route the
failure to the owning lane instead of reopening or expanding this gap:

- the run-state bridge retirement status class verified fresh on 2026-07-06
  (`test_design_delta_parent_drain_imported_backlog_drain_build_artifacts_record_derived_child_phase_binding`,
  `…_boundary_authority_report_records_generated_and_managed_path_evidence`,
  `…_resume_plumbing_retirement_report_records_drain_run_state_bridge_as_checked_compatibility`,
  `…_default_resume_report_marks_live_run_state_bridges_blocked_or_historical_only`:
  live reports mark `transitions.resource.drain_run_state` as `RETIRED` with
  a `REMOVE_COMPATIBILITY_ALLOWLIST` cleanup candidate and emit no private
  compatibility-bridge inputs, while the tests still encode the
  pre-retirement checked-compatibility/`BLOCKED` bridge shape):
  `workflow-lisp-design-delta-compatibility-carrier-retirement`, which owns
  reconciling the run-state bridge test contract with the live carrier-free
  lowering;
- the reference-family completed-gap fixture-evidence class verified fresh
  on 2026-07-06
  (`test_design_delta_parent_drain_build_emits_reference_family_conformance_profile`
  plus the four `…_build_rejects_reference_family_*` negative tests failing
  early on `reference_family_completed_gap_artifact_missing` raised by
  `_reconcile_completed_gaps` over the `_aligned_reference_family_*` fixture
  helpers' workspaces, so the negative tests no longer isolate the parity
  diagnostics they assert):
  `workflow-lisp-runtime-native-drain-reference-family-parity-evidence-binding-repair`,
  whose declared verification scope already includes the dedicated
  reference-family conformance and build-artifact reference-family tests;
- reference-family evidence-route regressions — the resolver selecting a
  versioned root that lacks a required conformance input despite the
  completeness rule (for example a future run publishing
  `drain-summary.json`, a `state/<root>/drain/run_state.json`, and an
  empty or malformed `design-gaps/` directory), no candidate root
  remaining eligible, or a defect in the completeness rule itself:
  `workflow-lisp-runtime-native-drain-reference-family-parity-evidence-binding-repair`
  for the evidence-binding route, and the run-mechanics lane that
  publishes versioned roots
  (`workflow-lisp-runtime-native-drain-shared-empty-run-state-retirement-and-reference-family-evidence-alignment`)
  for incomplete-root production — never a hand backfill of
  `artifacts/work/LISP-*/design-gaps` from this slice;
- missing or stale runtime-audit JSONL evidence production (making
  `non_regressive` true is a promotion concern, not a compile-gate concern):
  the migration-parity/promotion evidence lanes, not this slice;
- a `cycle_guard_demo` or `design_plan_impl_stack` regeneration failure whose
  cause is a genuine source, runtime, or checked-manifest defect in that
  family (not staleness of its derived report): the lane owning that family's
  migration evidence, not this slice — this slice owns only the coherent
  regeneration of stale derived reports against the current manifest;
- checked-manifest coherence failures re-emerging at the
  boundary-authority / value-flow-census / resume-plumbing gates (a new
  lowering-driven rename): the lane that landed the regenerating change owns
  the same-tranche rebaseline per the ninth revision's outside-uses rule;
- transition-authoring gate failures (`transition_authoring_invalid`):
  `workflow-lisp-design-delta-compatibility-carrier-retirement`;
- fixture-mirror sync, `SelectedItemResult` fixture construction, and deeper
  run-state carrier semantics:
  `workflow-lisp-design-delta-compatibility-carrier-retirement` and the
  drain run-state lanes;
- work-item owner-path or private-context boundary behavior:
  `workflow-lisp-design-delta-work-item-private-phasectx-boundary`;
- selector adapter or selector call-shape regressions:
  `workflow-lisp-runtime-native-drain-selector-stdlib-call-contract-regression-reopen`
  or
  `workflow-lisp-runtime-native-drain-selector-stdlib-single-ctx-signature-alignment-regression-reopen`;
- shared review/fix type-resolution or `std/phase` owner-lane diagnostics,
  should they recur:
  `workflow-lisp-runtime-native-drain-shared-std-phase-owner-lane-self-hosting-regression-reopen`;
  and
- post-ifexpr phase-family export/boundary failures:
  `workflow-lisp-phase-family-boundary-rehabilitation-post-ifexpr`.
