# DSL v2.14 Materialization And Variant Draft

## Status

This is a Phase 0 characterization reference. It is non-normative and does not
advertise public `version: "2.14"` support.

## Current Brittle Patterns To Freeze

- Artifact materialization is expressed today through command or provider steps
  that write JSON bundles and rely on `expected_outputs` or `output_bundle`
  contracts for validation.
- Implementation tagged-union outcomes are emulated with two report targets and
  a follow-up materialization step that decides between `COMPLETED` and
  `BLOCKED` after provider execution.
- Current implementation-phase selection uses fresh-report detection rather than
  content-addressed snapshot diffs. The oracle harness freezes that behavior so
  later v2.14 work can change it deliberately.
- Variant-specific behavior is modeled today by explicit queue-routing and
  control-flow steps rather than a first-class variant contract surface.
- Invalid bundles can leave candidate files on disk while still failing contract
  publication. The Phase 0 tests preserve that current no-commit behavior.

## Mapping To Future v2.14 Surfaces

### `materialize_artifacts`

Current approximation:

- command step writes a JSON bundle
- `output_bundle` enforces `relpath`, enum, and `must_exist_target` contracts
- downstream steps consume the published artifact values

Phase 0 oracle coverage:

- valid relpath materialization under `docs/plans`
- missing required target failure
- invalid enum bundle failure without artifact publication

### `pre_snapshot`

Current approximation:

- implementation phases capture a phase-start timestamp
- follow-up materialization inspects report freshness after execution

Phase 0 oracle coverage:

- single fresh execution report selects `COMPLETED`
- single fresh progress report selects `BLOCKED`
- both fresh reports fail as ambiguous
- no fresh reports fail as missing output

### `variant_output`

Current approximation:

- implementation state bundle exposes a discriminant plus variant-specific
  fields (`execution_report_path` or `progress_report_path`)
- downstream workflow logic branches on `implementation_state`

Phase 0 oracle coverage:

- completed-path exposure
- blocked-path exposure
- review-approve and review-revise control surfaces

### `select_variant_output`

Current approximation:

- deterministic follow-up command resolves a tagged-union outcome from the
  current report targets and publishes the selected bundle

Phase 0 oracle coverage:

- exact one-of-two outcome selection
- no-change and multi-change failure characterization via report presence

## Explicit Deferrals

Phase 0 does not introduce:

- public `version: "2.14"` loading
- snapshot-diff content hashing
- first-class variant proof syntax
- same-version v2.14 workflow translations
- spec text that claims public availability
