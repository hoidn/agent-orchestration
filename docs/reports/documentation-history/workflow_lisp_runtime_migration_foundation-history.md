# Workflow Lisp Runtime Migration Foundation: Historical Sections

Status: **Historical.** Original sections retain their original tense, measurements
and acceptance language as evidence, not current authority or work selection.
Current owner: [workflow_lisp_runtime_migration_foundation.md](../../design/workflow_lisp_runtime_migration_foundation.md).

## 4. Baseline Status Snapshot

| Surface | Baseline authority | Regression evidence to preserve |
| --- | --- | --- |
| command `output_bundle.path` env injection | Normative in `specs/io.md` | env override, parent creation/validation, missing-bundle failure tests |
| command `variant_output.path` | Normative in `specs/io.md` / `specs/dsl.md` | env override, parent creation/validation, missing-bundle failure tests, command `variant_output` coverage |
| provider `output_bundle.path` target binding | Normative in `specs/io.md` / `specs/dsl.md` / `specs/providers.md` | provider target-binding tests and provider spec/readme alignment |
| provider `variant_output.path` target binding | Normative in `specs/io.md` / `specs/dsl.md` / `specs/providers.md` | provider target-binding tests and wrong-path failure diagnostic |
| private collection contracts | Private executable Workflow Lisp lane; public YAML remains conservative | validator tests for list/map/record-like values and nested relpaths |
| scalar/list/map materialized value views | Private value-view lane; public YAML `pointer.path` remains relpath-compatible unless widened | string/list/map view tests; pointer-as-view invariants |
| collection publish/consume | Private executable artifact lineage with embedded contracts/provenance | private artifact catalog + state persistence tests; collection artifact publish/consume tests |
| prompt extern source semantics | `asset_file` is source-relative; `input_file` is workspace-relative | explicit extern manifest model and docs/examples |
| historical parity report generation | Retired tool/evidence surface; frozen reports remain in history | preserved report bytes and historical plans |
| `non_regressive` | Frozen historical derived field | preserved reports; never hand-edit or regenerate |
| StateLayout / PathAllocator | Ownership boundary in `workflow_lisp_state_layout.md` plus this foundation | allocation/provenance, run-isolated private path, source-map, and Semantic IR tests |
| hidden `__write_root__...` inputs | Compatibility mechanism, not public API | public-boundary inspection tests and runtime-contract visibility tests |

The remaining post-foundation work builds on these surfaces. If any row
regresses, downstream promotion evidence is invalid until the row is repaired
and evidence is refreshed.

## 13. Tranche 4: Migration Promotion Gate Hardening

### 13.1 Historical Contract

This tranche hardened the former manifest-driven parity generator into a
release gate. The generator and its manifest are now retired; the following
mode semantics are retained only to interpret frozen reports and plans.

At minimum, `--require-non-regressive` exits nonzero when any selected target lacks valid, complete, current, computed non-regression evidence.

Gate modes:

`--require-non-regressive`

- selected targets must have `report_valid=true`;
- selected targets must have `evidence_complete=true`;
- selected targets must have computed `non_regressive=true`;
- ineligible targets may pass this gate but must not become primary.

`--require-promotable`

- selected targets must satisfy all `--require-non-regressive` requirements;
- selected targets must also have `eligible_for_primary_surface=true`;
- strict gate acceptance/rejection is the only place where derived `primary_surface` carries release-policy force.

Decision table:

| `report_valid` | `evidence_complete` | `non_regressive` | `eligible_for_primary_surface` | `--require-non-regressive` | `--require-promotable` | gate-layer `primary_surface` |
| --- | --- | --- | --- | --- | --- | --- |
| false | any | any | any | fail | fail | not derived |
| true | false | any | any | fail | fail | not derived |
| true | true | false | any | fail | fail | not derived |
| true | true | true | false | pass | fail | `yaml` |
| true | true | true | true | pass | pass | `orc` |

The command must validate both freshly generated reports and reused existing reports against the same schema/version contract before including them in an aggregate index.

Existing reports are not authority merely because they are JSON objects. `non_regressive` remains computed from evidence. Target manifests and hand-authored reports must not provide it.

Per-target parity reports stay evidence-only artifacts. If the CLI needs a machine-readable strict-gate result beyond markdown/index rendering, it should emit a separate versioned `gate_evaluation` object rather than turning the report itself into promotion policy authority.

Rendered markdown and index rows may still display a derived `primary_surface` informatively, matching current reusable-report behavior. That display remains a view. Only `--require-promotable` gate evaluation may treat the derivation as release-policy authority.

If persisted, `gate_evaluation` should record gate mode, selected-target identities, per-target pass/fail reasons, and any derived `primary_surface` decision. It may be regenerated from reusable reports plus current manifest/selection context without mutating the per-target reports themselves.

Gate-layer or derived-view `primary_surface` is derived from:

```text
computed non_regressive
AND promotion_eligibility.eligible_for_primary_surface
```

When `non_regressive=true` but `eligible_for_primary_surface=false`, reports and derived gate views must make the distinction explicit: the candidate may be non-regressive against recorded evidence but still not promotable.

### 13.2 Required Report Fields

The strict gate report schema must include at least:

- `schema_version`;
- `workflow_family`;
- `candidate`;
- `yaml_primary`;
- `target_identity`;
- `evidence`;
- `evidence_freshness`;
- `promotion_eligibility`;
- `compile_artifacts`;
- tooling-computed `non_regressive`;
- `generated_at`;
- `generated_by`;
- `tool_version`; and
- optional accepted waivers with owner and expiry.

`target_identity` must contain the exact identity material strict reuse checks will validate:

- `targets_schema_version`;
- `target_manifest_path`;
- `target_manifest_sha256`;
- `target_index` or another stable selected-target key within that manifest;
- `workflow_family`;
- `candidate_path`;
- `candidate_sha256`;
- `yaml_primary_path`; and
- `entry_workflow`.

`evidence_freshness` must carry the freshness inputs strict gating uses:

- `generated_at`;
- `compile_manifest_path`, when compile evidence produced one;
- `compile_manifest_sha256`, when compile evidence produced one;
- `compiled_workflow_checksum`, when compile/run evidence exposes it;
- `required_artifacts`, including each required artifact's expected path and status/digest comparator when available; and
- `evidence_refs`, keyed by evidence role, with the path, digest or stable identifier, and freshness notes needed to prove the report still corresponds to the selected target and current evidence set.

Strict reuse checks compare the selected target against the report's manifest hash, candidate source digest, compile-manifest digest when present, compiled workflow checksum when present, and required evidence references. Any mismatch or missing required comparator makes the reused report stale for gate purposes.

`report_valid` and `evidence_complete` are gate-derived checks, not authored fields:

- `report_valid=true` only when the report schema version matches, all required fields above are present and parse as the declared structures, `target_identity` matches the selected manifest row exactly, the report does not publish gate-owned fields such as `primary_surface`, and tooling can recompute `non_regressive` from the embedded evidence without disagreement.
- `evidence_complete=true` only when required evidence roles are present, required compile artifacts are present and passing, waivers are still valid, and `evidence_freshness` supplies every comparator required for the selected target: manifest digest, candidate digest, compile-manifest digest when present, compiled-workflow checksum when present, and required evidence/artifact references.

`primary_surface` is a gate-layer or derived-view delta in this document. It must be derived by tooling from computed non-regression and eligibility; it is not authored in the target manifest and it is not a required parity-report field.

### 13.3 Acceptance

- Target manifests cannot provide `non_regressive`.
- Hand-authored reports cannot provide authoritative `non_regressive`.
- Reused reports validate schema/version, selected target identity, manifest/checksum freshness, and required evidence references before contributing to an aggregate gate.
- `--require-non-regressive` exits nonzero when any selected target lacks valid, complete, current, computed non-regression evidence.
- `--require-promotable` exits nonzero unless selected targets are both non-regressive and eligible for primary surface.
- Non-regressive but ineligible candidates do not become primary, and `primary_surface` remains a gate/view derivation rather than a report-owned authority field.
