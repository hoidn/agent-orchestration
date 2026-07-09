# Refactoring Plan: Split `orchestrator/workflow_lisp/build.py` into Flat Sibling Modules

> **Execution status (verified 2026-07-09):** Verified at `36aafed448892b2f773b27c8c507db31bccd15fd` (`Extract materialize view step interpreter behind a permanent delegator`). Tasks 1-5 are landed in `31df2a663fe4a7d4306ab9a5dbd0cf304e1a9495` (`Move stateless build manifest io helpers to sibling module`), `e9df325c3654f7b6e6b97a598726b0984b4688a3` (`Move design-delta certification helpers to sibling module`), `5efeb981144d15164f964a3404c99554141577a2` (`Move build artifact writers and serializers to sibling module`), `962766b39c06a06b8d8ef086f47dcd8ad83f1cdc` (`Thread design-delta reports through evidence and payload bundles`), and `dfdf55c4072e2f8eb595b59f3a96a4bb227023be` (`Slice frontend bundle build into compile select assemble emit stages`). The `_compile_entry`, `_select_and_reattach`, and `_emit` stage helpers are present; Task 6, the final full-suite, module-size, and certification gate, remains. Unrelated user work exists in the checkout and must be preserved.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Break the 6,075-line `orchestrator/workflow_lisp/build.py` into flat sibling modules so that (a) the design-delta certification lane becomes an excisable unit behind a narrow `DesignDeltaEvidence` / `serialize_design_delta_reports` interface, (b) stateless manifest-io and artifact-writer helpers move out from under the public dataclasses, and (c) `build.py` shrinks to the public surface (dataclasses + `build_frontend_bundle` + its stage helpers). Strictly behavior-preserving: same artifacts, same content-addressed fingerprints, same failure modes.

**Architecture:** House-style flat siblings, not a package. Three new modules — `build_manifest_io.py`, `build_design_delta.py`, `build_artifacts.py` — plus the residual `build.py`. Dependency direction is strictly one-way: `build.py` → all three; `build_design_delta.py` and `build_artifacts.py` may import `build_manifest_io.py`; nothing imports `build.py` back. Public names (`FrontendBuildRequest`, `build_frontend_bundle`, and the handful of `_`-prefixed helpers that tests and CLI import directly) stay importable from `orchestrator.workflow_lisp.build` via re-export so no consumer edits are required.

**Tech Stack:** Python 3.13, pytest, pyflakes 3.4.0 (already installed).

**Scope assumption (recorded):** This plan implements Roadmap item 3 ("build.py split") of `docs/plans/2026-07-07-refactoring-dead-code-and-lowering-consolidation.md`. It does **not** touch the executor decomposition, drain migration, or YAML retirement. The final `build_frontend_bundle` stage-slicing (increment 5) is the only new intra-`build.py` structure; the first four increments are pure ownership moves.

## Global Constraints

- Run all commands from the repo root `/home/ollie/Documents/agent-orchestration`.
- The working tree contains the user's in-flight work. **Stage by explicit path only** (`git add <file> <file>`). Never `git add -A`, `git add -u`, or `git commit -a`.
- Commit messages: short imperative sentence, matching repo style (e.g. `Route selector and gap drafting to stronger models`). **No** conventional-commit prefixes, **no** mention of Claude/Claude Code, **no** Co-Authored-By trailers.
- No worktrees. Never use `--no-verify`.
- Narrowest pytest selectors first; treat fresh command output as the verification evidence. After changing any test module, run `pytest --collect-only <module>` on it.
- Do not touch `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R*` directories — they are compile-evidence inputs for the certification lane.
- Frozen surfaces (do not modify): `orchestrator/workflow_lisp/lowering/phase_drain.py` lines 592-1979, `orchestrator/workflow_lisp/lowering/drain_terminal.py`, everything gated on the `lisp_frontend_design_delta/drain::drain` entry in `build.py`, `migration_parity.py`. **Additional rule for this plan: design-delta gated logic moves verbatim — no behavior edits during the split.** The loader-gating on family/entry (e.g. `_is_design_delta_family_profile_candidate`, the `entry_workflow != "lisp_frontend_design_delta/drain::drain"` row-filter, the `boundary_authority_registry is not None` guard) moves character-for-character. Every `LispFrontendCompileError` raise inside the certification region keeps its exact code, message template, and `path=` argument.
- If a step's verification fails twice in a row, stop and report instead of forcing it green.

### The line numbers in this plan are drift-anchored to function names

The tree is mid-flight with uncommitted changes. **Every task begins with a `grep -n "def <name>"` re-anchor step.** Trust the function names, not the absolute line numbers printed here — they were captured 2026-07-07 and will shift as earlier increments land. Any task whose re-anchor step prints a materially different structure than described must STOP and report before editing.

---

## Entry gate (BLOCKING — verify before Task 1)

The authoring brief assumed "Phase-1 plan Tasks 7 and 8 landed." **This is not true in the current tree.** Verify and satisfy the gate first:

- [ ] **Gate check 1: the duplicate `_iter_surface_steps` must be gone (Phase-1 Task 7).**

  Run:
  ```bash
  grep -n "def _iter_surface_steps" orchestrator/workflow_lisp/build.py
  ```
  Required: **exactly one** line (the typed traversal, currently `_iter_surface_steps(steps: Sequence[SurfaceStep])`). If two lines print (the second being `_iter_surface_steps(steps: Any) -> tuple[Any, ...]`), the shadowing-traversal bug is still live. **STOP** and land `docs/plans/2026-07-07-refactoring-dead-code-and-lowering-consolidation.md` Task 7 first. Do not proceed — moving a duplicated definition into a new module would either duplicate the bug or silently change which definition wins.

- [ ] **Gate check 2: the guarded unused-import sweep (Phase-1 Task 8) has run, or is accepted as not-a-blocker.**

  Task 8 is not a hard prerequisite for correctness, but it reduces churn. Run:
  ```bash
  pyflakes orchestrator/workflow_lisp/build.py | grep "imported but unused" | wc -l
  ```
  If this is large (>10), note it: the moves below will relocate imports, and a pre-existing unused-import backlog makes the per-module pyflakes checks noisier. Not blocking, but record the baseline count so the post-move pyflakes deltas are interpretable.

- [ ] **Gate check 3: baseline the two smoke selectors on the current tree.**

  Run and record PASS/FAIL + counts (the tree carries in-flight work; you need a before-picture):
  ```bash
  pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q -k "smoke"
  pytest tests/test_workflow_lisp_build_artifacts.py -q
  ```
  If either is already RED on the untouched tree, capture that; a task's job is to not make it *more* red, not to fix pre-existing failures.

---

## Cluster map (verified 2026-07-07 against the in-flight tree)

| Cluster | Function-name anchors | Approx lines | Destination |
|---|---|---|---|
| Public dataclasses + reference-family paths | `ReferenceFamilyEvidencePaths`…`FrontendArtifactExportRequest`, `_resolve_reference_family_evidence_paths` | 329-625 | **stays in `build.py`** |
| `build_frontend_bundle` + export helpers | `build_frontend_bundle`, `normalize_frontend_artifact_exports`, `emit_requested_frontend_artifact_exports`, `load_imported_workflow_bundle_manifest` | 626-1940 | **stays in `build.py`** |
| Request/manifest loaders + validators | `_resolve_request`…`_select_entry_workflow` | 1941-2645 | `build_manifest_io.py` |
| Design-delta loaders | nine `_maybe_load_design_delta_*` + `_is_design_delta_family_profile_candidate` + `_family_profile_metadata_for_entry` | 2646-3090 | `build_design_delta.py` |
| Provenance helpers | `_boundary_authority_registry_provenance`…`_observability_old_writer_pair_provenance` | 3024-3090 | `build_design_delta.py` |
| Surface-step / provider-shape helpers | `_collect_materialize_view_effects`, `_bundle_index_by_surface_name`, `_iter_surface_steps`, `_provider_request_field_observation`, `_collect_provider_input_shape_observations` | 3091-3285 | **stays in `build.py`** (shared traversal; see Task 3 note) |
| Compatibility-bridge materialization | `_materialize_design_delta_compatibility_bridge_bundles`…`_augment_design_delta_compatibility_bridge_lineage` | 3286-3744 | `build_design_delta.py` |
| Prerequisite-report + entry-publication builders | `_build_slug`, `_design_delta_prerequisite_report_paths`, `_with_report_path`, `_build_design_delta_observability_summary_prerequisite_report`, `_build_entry_publication_report`, `_collect_entry_publication_lowerings`, `_entry_publication_*` | 3745-4247 | see Task 4 note (split) |
| Design-delta serializers | `_serialize_design_delta_adapter_census`, `_serialize_design_delta_boundary_authority_report`, `_allowed_resume_plumbing_retirement_registry_rows`, `_serialize_design_delta_g8_deletion_evidence`, `_design_delta_contract_is_path_like`, `_design_delta_generated_internal_entry_is_path_like` | 4248-4844 | `build_design_delta.py` |
| Artifact writers + serializers | `_fingerprint_build`, `_write_build_artifacts`, `_public_runtime_plan_payload`, `_build_manifest`, `_serialize_*` (AST/source-map/boundary), `_validate_lexical_checkpoint_artifacts`, `_validate_selected_workflow_hidden_compatibility_bridge_public_boundary`, `_origin_payload`, `_display_workflow_name`, `_command_boundary_metadata_for_workflow` | 4845-5987 (minus design-delta bits) | `build_artifacts.py` |
| Design-delta retirement serializers | `_resume_plumbing_retirement_source_texts`, `_serialize_lexical_checkpoint_points_for_retirement`, `_serialize_lexical_checkpoint_shadow_reports_for_retirement` | 5302, 5392, 5503 | `build_design_delta.py` |
| Stateless io leaf helpers | `_load_json_file`, `_resolve_manifest_relative_path`, `_sha256_path`, `_cli_request_diagnostic`, `_json_data` | 5988-6075 | `build_manifest_io.py` |

**Drift note found during verification:** the brief placed the surface-step helpers (`_iter_surface_steps` etc., 3091-3285) inside the design-delta cluster. They are **not** design-delta-specific — `_collect_provider_input_shape_observations` feeds the always-emitted provider-input-shape report and `_iter_surface_steps` is shared. They stay in `build.py`. This plan keeps them there; only the design-delta serializers/loaders/bridge move.

**Direct-importer inventory (drives which moves need re-exports):**
- `_parse_command_boundaries_manifest` — imported by **9 test files** (view_dual_run, lexical_checkpoint_restore, source_map, design_delta_bridge_adapter_compatibility, diagnostics, structured_results, wcc_m4, command_adapters, resource_stdlib) and the feasibility test. → **Task 1 needs a permanent re-export.**
- `_cli_request_diagnostic` — imported by `orchestrator/cli/commands/compile.py` and `explain.py`. → **Task 1 needs a re-export.**
- `_json_data`, `_origin_payload` — imported by `orchestrator/cli/commands/explain.py`. `_origin_payload` lives in the artifacts cluster; `_json_data` in manifest-io. → **Tasks 1 and 4 need re-exports.**
- `_display_workflow_name` — imported by the feasibility test (`tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py:40`). Lives in artifacts cluster. → **Task 4 needs a re-export.**
- `_serialize_lexical_checkpoint_points_for_retirement` — **monkeypatched** as `build._serialize_lexical_checkpoint_points_for_retirement` in `tests/test_workflow_lisp_build_artifacts.py:9744`. It must remain an attribute of the `build` module after moving to `build_design_delta.py`, i.e. `build.py` must `from .build_design_delta import _serialize_lexical_checkpoint_points_for_retirement` **and reference that imported name at its call site** so the monkeypatch takes effect. → **Task 3 has a dedicated verification for this.**
- All other suites import only `FrontendBuildRequest` / `build_frontend_bundle` (public, never move) or reach helpers via `importlib.import_module("orchestrator.workflow_lisp.build")` + `getattr` (satisfied by re-exports).

---

## Task 1: Move stateless manifest-io helpers to `build_manifest_io.py`

Lowest-risk move: the request/manifest loaders, `_require_*` validators, and the five stateless io-leaf helpers are pure functions with no design-delta coupling. They are the shared substrate the other two new modules will import, so they move first.

**Files:**
- Create: `orchestrator/workflow_lisp/build_manifest_io.py`
- Modify: `orchestrator/workflow_lisp/build.py` (delete moved defs; add re-export imports)

**Interfaces:** No signature changes. The module exports (unchanged signatures):
- `_resolve_request(request: FrontendBuildRequest) -> FrontendBuildRequest`
- `_load_string_mapping(path, *, label) -> dict[str, str]`
- `_load_prompt_extern_mapping(path) -> Mapping[str, object]`
- `_load_command_boundaries_manifest_payload(path) -> Mapping[str, object]`
- `_parse_command_boundaries_manifest(payload, *, manifest_path) -> ...`
- `_require_string_array`, `_require_optional_string_array`, `_require_mapping_field`, `_require_string_field`, `_require_optional_string_field`, `_require_input_signature`, `_require_transition_binding`, `_require_view_binding` (validators, signatures verbatim)
- `_select_entry_workflow(compile_result, *, requested_name, source_path) -> FrontendEntrySelection`
- `_load_json_file(path: Path, *, label: str) -> Any`
- `_resolve_manifest_relative_path(manifest_path: Path, entry_path: str) -> Path`
- `_sha256_path(path: Path) -> str`
- `_cli_request_diagnostic(*, code, message, path) -> LispFrontendDiagnostic`
- `_json_data(value: Any) -> Any`

- [ ] **Step 1: Re-anchor the cluster boundaries**

  Run:
  ```bash
  grep -n "def _resolve_request\|def _select_entry_workflow\|def _maybe_load_design_delta_family_profile_catalog\|def _load_json_file\|def _json_data" orchestrator/workflow_lisp/build.py
  ```
  Expected order: `_resolve_request` < `_select_entry_workflow` < `_maybe_load_design_delta_family_profile_catalog` (the manifest-io loader block ends where the design-delta loaders begin) and the io-leaf block `_load_json_file … _json_data` sits at the tail. The move set is the **top block** `_resolve_request` through `_select_entry_workflow` (inclusive) **plus** the **tail block** `_load_json_file` through `_json_data` (inclusive). If `_maybe_load_design_delta_*` appears *inside* the top block, STOP — the tree diverged.

- [ ] **Step 2: Create `build_manifest_io.py` with the moved defs**

  Create the file with this header, then move (cut, do not copy) the two blocks' function bodies into it verbatim:

  ```python
  """Stateless request/manifest loaders, field validators, and io leaf helpers for the Workflow Lisp build.

  Extracted from build.py. Pure functions — no design-delta coupling, no build-state.
  Imported by build.py, build_design_delta.py, and build_artifacts.py; imports nothing from them.

  Contract: see docs/design/README.md build-surface section. Behavior is byte-identical
  to the pre-split build.py definitions.
  """

  from __future__ import annotations

  import hashlib
  import json
  from collections.abc import Mapping, Sequence
  from pathlib import Path
  from typing import Any
  ```

  Then add the domain imports these functions actually reference. Discover them mechanically rather than guessing:
  ```bash
  # names referenced by the moved functions but defined elsewhere in build.py's import block
  grep -nE "FrontendBuildRequest|FrontendEntrySelection|LispFrontendDiagnostic|LispFrontendCompileError|_require_|CommandBoundary|MaterializeViewBindingReference|SourceSpan|SourcePosition" orchestrator/workflow_lisp/build.py | sed -n '1,40p'
  ```
  Decision rule for each symbol used by a moved function:
  - If it is a **public dataclass that stays in build.py** (`FrontendBuildRequest`, `FrontendEntrySelection`): import it in `build_manifest_io.py` as `from .build import FrontendBuildRequest, FrontendEntrySelection` **only if** that does not create a cycle. It **does** create a cycle (build.py will import build_manifest_io). Resolve by using a `TYPE_CHECKING`-guarded import for the annotations and a runtime-safe construction: `_select_entry_workflow` **constructs** `FrontendEntrySelection`, so it needs the real class. Move `_select_entry_workflow` construction to use a deferred `from .build import FrontendEntrySelection` **inside the function body**, OR (cleaner) leave `_select_entry_workflow` in `build.py` and move only the pure loaders/validators/io-leaf helpers. **Choose the second option** — it avoids the cycle entirely. Update this task's Interface list to drop `_select_entry_workflow` if you take that path, and note the decision in the commit body.
  - If it is imported from a sibling module (`from .diagnostics import LispFrontendDiagnostic`, `from .command_boundaries import ...`): copy that exact import line into `build_manifest_io.py`.

- [ ] **Step 3: Re-export from `build.py`**

  Delete the moved defs from `build.py`. Add, grouped near the other relative imports:
  ```python
  from .build_manifest_io import (
      _cli_request_diagnostic,
      _json_data,
      _load_command_boundaries_manifest_payload,
      _load_json_file,
      _load_prompt_extern_mapping,
      _load_string_mapping,
      _parse_command_boundaries_manifest,
      _require_input_signature,
      _require_mapping_field,
      _require_optional_string_array,
      _require_optional_string_field,
      _require_string_array,
      _require_string_field,
      _require_transition_binding,
      _require_view_binding,
      _resolve_manifest_relative_path,
      _resolve_request,
      _sha256_path,
  )
  ```
  (Add `_select_entry_workflow` here only if Step 2 chose to move it.) These re-exports are **permanent, not temporary** — `_parse_command_boundaries_manifest`, `_cli_request_diagnostic`, and `_json_data` have live external importers (9 tests + 2 CLI commands), so they must stay reachable from `orchestrator.workflow_lisp.build`.

- [ ] **Step 4: Verify import graph, no cycle, and external importers still resolve**

  Run:
  ```bash
  python -c "import orchestrator.workflow_lisp.build; import orchestrator.workflow_lisp.build_manifest_io; print('IMPORT_OK')"
  python -c "from orchestrator.workflow_lisp.build import _parse_command_boundaries_manifest, _cli_request_diagnostic, _json_data; print('REEXPORT_OK')"
  python -c "from orchestrator.cli.commands import compile as c, explain as e; print('CLI_OK')"
  pyflakes orchestrator/workflow_lisp/build_manifest_io.py
  ```
  Expected: `IMPORT_OK`, `REEXPORT_OK`, `CLI_OK`; pyflakes silent (no unused imports, no undefined names). An `ImportError` for a cycle → revisit the Step-2 decision rule (keep `_select_entry_workflow` in build.py).

- [ ] **Step 5: Behavioral suites**

  Run:
  ```bash
  pytest tests/test_workflow_lisp_build_artifacts.py -q
  pytest tests/test_workflow_lisp_command_adapters.py tests/test_workflow_lisp_source_map.py tests/test_workflow_lisp_view_dual_run.py -q
  pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q -k "smoke"
  ```
  Expected: PASS (same as the Entry-gate baseline).

- [ ] **Step 6: Commit**

  ```bash
  git add orchestrator/workflow_lisp/build.py orchestrator/workflow_lisp/build_manifest_io.py
  git commit -m "Move stateless build manifest io helpers to sibling module"
  ```

---

## Task 2: Move design-delta serializers, loaders, and bridge materialization to `build_design_delta.py`

The largest and highest-value move. All design-delta-gated helpers relocate together so the certification lane's future retirement is a file deletion plus two call-site removals. **No behavior edits** — every gate and raise moves verbatim.

**Files:**
- Create: `orchestrator/workflow_lisp/build_design_delta.py`
- Modify: `orchestrator/workflow_lisp/build.py` (delete moved defs; add re-export imports; retarget call sites to the imported names)

**Interfaces:** The move preserves each helper's existing signature (re-exported). The *narrowing* interface (`DesignDeltaEvidence` / `serialize_design_delta_reports`) is deferred to Task 5, because the payload computation is currently interleaved through the body of `build_frontend_bundle` (verified: 17 payload variables assigned across lines ~808-1611, interspersed with `LispFrontendCompileError` raises and calls to sibling-module report builders). Task 2 moves only the **free functions**; Task 5 threads them behind the dataclass once the writers and body-slicing are in place.

  Functions moved to `build_design_delta.py` (signatures verbatim):
  - Loaders: `_maybe_load_design_delta_family_profile_catalog`, `_maybe_load_design_delta_boundary_authority_registry`, `_maybe_load_design_delta_value_flow_census`, `_maybe_load_design_delta_transition_authoring_manifest`, `_maybe_load_design_delta_consumer_rendering_census`, `_maybe_load_design_delta_observability_old_writer_pair_manifest`, `_maybe_load_design_delta_compatibility_bridge_manifest`, `_maybe_load_design_delta_rendering_cleanup_manifest`, `_maybe_load_design_delta_rendering_ergonomics_manifest`, `_maybe_load_design_delta_view_dual_run_vectors`, `_maybe_load_design_delta_view_dual_run_report`, `_maybe_load_design_delta_resume_plumbing_retirement_manifest`
  - Candidacy/metadata: `_is_design_delta_family_profile_candidate`, `_family_profile_metadata_for_entry`
  - Provenance: `_boundary_authority_registry_provenance`, `_value_flow_census_provenance`, `_consumer_rendering_census_provenance`, `_observability_old_writer_pair_provenance`
  - Bridge materialization: `_materialize_design_delta_compatibility_bridge_bundles`, `_surface_with_compatibility_bridge_steps`, `_reattach_bundle_provenance`, `_reattach_bundle_semantic_ir`, `_compatibility_bridge_surface_step`, `_compatibility_bridge_target_binding`, `_compatibility_bridge_value_document`, `_compatibility_bridge_manifest_value_document`, `_augment_design_delta_compatibility_bridge_lineage`
  - Prerequisite reports: `_build_slug`, `_design_delta_prerequisite_report_paths`, `_with_report_path`, `_build_design_delta_observability_summary_prerequisite_report`
  - Serializers: `_serialize_design_delta_adapter_census`, `_serialize_design_delta_boundary_authority_report`, `_allowed_resume_plumbing_retirement_registry_rows`, `_serialize_design_delta_g8_deletion_evidence`, `_design_delta_contract_is_path_like`, `_design_delta_generated_internal_entry_is_path_like`
  - Retirement serializers: `_resume_plumbing_retirement_source_texts`, `_serialize_lexical_checkpoint_points_for_retirement`, `_serialize_lexical_checkpoint_shadow_reports_for_retirement`

  **Stays in build.py** (not design-delta-specific despite adjacency): `_reattach_bundle_semantic_ir` is called on the general path — verify at Step 1 whether it references only `derive_workflow_semantic_ir`; if so it may stay. `_collect_materialize_view_effects`, `_bundle_index_by_surface_name`, `_iter_surface_steps`, `_provider_request_field_observation`, `_collect_provider_input_shape_observations` **stay** (shared traversal). `_build_entry_publication_report` and its helpers → Task 4 (artifacts).

- [ ] **Step 1: Re-anchor and classify the boundary helpers**

  Run:
  ```bash
  grep -n "def _maybe_load_design_delta\|def _is_design_delta_family_profile_candidate\|def _family_profile_metadata_for_entry\|def _boundary_authority_registry_provenance\|def _materialize_design_delta_compatibility_bridge_bundles\|def _reattach_bundle_semantic_ir\|def _augment_design_delta_compatibility_bridge_lineage\|def _serialize_design_delta\|def _resume_plumbing_retirement_source_texts\|def _serialize_lexical_checkpoint_points_for_retirement\|def _serialize_lexical_checkpoint_shadow_reports_for_retirement\|def _allowed_resume_plumbing_retirement_registry_rows" orchestrator/workflow_lisp/build.py
  ```
  For `_reattach_bundle_semantic_ir` and `_reattach_bundle_provenance`, check callers:
  ```bash
  grep -n "_reattach_bundle_semantic_ir\|_reattach_bundle_provenance" orchestrator/workflow_lisp/build.py
  ```
  Decision rule: both are called unconditionally in `build_frontend_bundle` (:783, :800) on the general path, but they exist specifically to re-thread provenance/semantic-IR onto bridge-materialized bundles. Because they are called on **every** build (not just design-delta), and their bodies do not gate on design-delta, **keep them in build.py** to avoid an import-back edge. Move only the strictly design-delta-named helpers. Record this classification in the commit body.

- [ ] **Step 2: Create `build_design_delta.py`**

  ```python
  """Design-delta certification lane: loaders, provenance, compatibility-bridge
  materialization, and report serializers for the Workflow Lisp build.

  Extracted from build.py. Every function here is gated on the design-delta family
  or the `lisp_frontend_design_delta/drain::drain` entry; this module is the excision
  unit for retiring the certification lane (delete the file + its two call sites in
  build_frontend_bundle + one DesignDeltaEvidence field).

  Behavior is byte-identical to the pre-split build.py definitions — no gate or raise
  was edited during the move. See CLAUDE.md frozen-surface rules.

  May import build_manifest_io; must not import build (one-way dependency).
  """

  from __future__ import annotations
  ```
  Then move the classified functions verbatim. Add imports mechanically:
  ```bash
  # sibling-module symbols the moved functions reference
  grep -nE "load_workflow_family_profile_catalog|load_design_delta_boundary_authority_registry|is_design_delta_parent_drain_target_workflow|checked_design_delta_public_input_names|DESIGN_DELTA_|reconcile_value_flow_census|build_consumer_rendering_census_report|WorkflowFamilyProfileCatalog|LoadedWorkflowBundle|WorkflowProvenance|SurfaceStep" orchestrator/workflow_lisp/build.py | sed -n '1,60p'
  ```
  For each referenced symbol: if it comes from a `.family_profiles` / `.phase_family_boundary` / `.value_flow_census` / etc. import in build.py, copy that exact import line into `build_design_delta.py`. For the stateless helpers (`_cli_request_diagnostic`, `_json_data`, `_sha256_path`, `_load_json_file`), add `from .build_manifest_io import _cli_request_diagnostic, _json_data, _load_json_file, _sha256_path`.

- [ ] **Step 3: Re-export and retarget call sites in `build.py`**

  Delete the moved defs. Add a `from .build_design_delta import (...)` block listing **every** moved name (alphabetized). Then confirm the call sites inside `build_frontend_bundle` now resolve to the imported names (they do automatically — same module-level name). **Critical for the monkeypatch:** verify the call sites at the retirement-serializer references still read the module-level name so `build._serialize_lexical_checkpoint_points_for_retirement = ...` in tests rebinds them:
  ```bash
  grep -n "_serialize_lexical_checkpoint_points_for_retirement\|_serialize_lexical_checkpoint_shadow_reports_for_retirement\|_resume_plumbing_retirement_source_texts" orchestrator/workflow_lisp/build.py
  ```
  These must appear both as the `from .build_design_delta import ...` line and as bare-name calls inside `build_frontend_bundle`. Since Python resolves the bare name against `build`'s module globals (which the import populated and the monkeypatch overwrites), the patch works. Do **not** change the call sites to `build_design_delta._serialize_...` — that would break the monkeypatch.

- [ ] **Step 4: Verify the monkeypatch and re-exports**

  Run:
  ```bash
  python -c "import orchestrator.workflow_lisp.build as b; import orchestrator.workflow_lisp.build_design_delta as d; assert b._serialize_lexical_checkpoint_points_for_retirement is d._serialize_lexical_checkpoint_points_for_retirement; print('REEXPORT_IDENTITY_OK')"
  python -c "from orchestrator.workflow_lisp.build import _display_workflow_name" 2>&1 | head -1  # still in build.py (Task 4 moves it) — should succeed
  pyflakes orchestrator/workflow_lisp/build_design_delta.py
  ```
  Expected: `REEXPORT_IDENTITY_OK`; pyflakes silent. Then the monkeypatch-bearing suite:
  ```bash
  pytest tests/test_workflow_lisp_build_artifacts.py -q -k "retirement or checkpoint"
  ```
  Expected: PASS (the monkeypatch at test line ~9744 must take effect — if it silently no-ops, the split broke name resolution; STOP).

- [ ] **Step 5: Full behavioral + certification smoke**

  Run:
  ```bash
  pytest tests/test_workflow_lisp_build_artifacts.py -q
  pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q -k "smoke"
  pytest tests/test_workflow_lisp_design_delta_bridge_adapter_compatibility.py tests/test_workflow_lisp_view_dual_run.py tests/test_workflow_lisp_transition_authoring.py -q
  ```
  Expected: PASS. Any new `LispFrontendCompileError` behavior change (a build that previously passed now raising, or vice versa) means a gate moved incorrectly — STOP and diff the moved function against `git show HEAD:orchestrator/workflow_lisp/build.py`.

- [ ] **Step 6: Commit**

  ```bash
  git add orchestrator/workflow_lisp/build.py orchestrator/workflow_lisp/build_design_delta.py
  git commit -m "Move design-delta certification helpers to sibling module"
  ```

---

## Task 3: Move artifact writers and serializers to `build_artifacts.py`

Relocate the artifact-writing surface — fingerprint, the big `_write_build_artifacts`, `_build_manifest`, the AST/source-map/boundary serializers, checkpoint serializers, and the boundary validators — leaving `build.py` holding only `build_frontend_bundle` and the public dataclasses.

**Files:**
- Create: `orchestrator/workflow_lisp/build_artifacts.py`
- Modify: `orchestrator/workflow_lisp/build.py` (delete moved defs; add re-export imports)

**Interfaces:** Signatures verbatim. Exported (partial list; the full set is every non-design-delta function in 4845-5987):
- `_fingerprint_build(*, request, compile_result, imported_bindings, entry_selection, provider_externs, prompt_externs, command_boundary_manifest, family_profile_catalog, boundary_authority_registry, value_flow_census, consumer_rendering_census, observability_old_writer_pair_manifest, resume_plumbing_retirement_manifest) -> str`
- `_write_build_artifacts(...) -> Mapping[str, Path]` (the ~40-kwarg writer — signature unchanged in this task; narrowing happens in Task 5)
- `_public_runtime_plan_payload`, `_build_manifest`, `_collect_origin_keys`, `_checkpoint_program_identity`, `_serialize_lexical_checkpoint_points`, `_validate_lexical_checkpoint_artifacts`, `_serialize_lexical_checkpoint_shadow_report`, `_serialize_frontend_ast`, `_serialize_expanded_frontend_ast`, `_serialize_typed_frontend_ast`, `_serialize_lowered_workflows`, `_serialize_source_map`, `_serialize_workflow_boundary_projection`, `_validate_selected_workflow_hidden_compatibility_bridge_public_boundary`, `_origin_payload`, `_display_workflow_name`, `_command_boundary_metadata_for_workflow`

  Plus the entry-publication builders (`_build_entry_publication_report`, `_collect_entry_publication_lowerings`, `_entry_publication_policy_row_id`, `_entry_publication_slug`, `_entry_publication_source_map_step_ids`) — these are report builders, not gated loaders; they belong with the other serializers.

- [ ] **Step 1: Re-anchor and confirm no design-delta bodies remain in range**

  Run:
  ```bash
  grep -n "def _fingerprint_build\|def _write_build_artifacts\|def _build_manifest\|def _serialize_workflow_boundary_projection\|def _validate_selected_workflow_hidden_compatibility_bridge_public_boundary\|def _display_workflow_name\|def _command_boundary_metadata_for_workflow\|def _build_entry_publication_report" orchestrator/workflow_lisp/build.py
  grep -n "def _serialize_design_delta\|def _resume_plumbing_retirement_source_texts\|def _serialize_lexical_checkpoint_points_for_retirement" orchestrator/workflow_lisp/build.py
  ```
  Expected: the second grep prints **nothing** (Task 2 already moved those). If it prints, Task 2 is incomplete — STOP.

- [ ] **Step 2: Create `build_artifacts.py` and move the defs**

  ```python
  """Artifact fingerprinting, writing, and serialization for the Workflow Lisp build.

  Extracted from build.py. Produces the on-disk build tree (frontend_ast.json,
  runtime_plan.json, source_map.json, manifest.json, and the optional design-delta
  report artifacts) from already-computed payloads. Content-addressed fingerprints
  and artifact bytes are byte-identical to the pre-split build.py.

  May import build_manifest_io and build_design_delta; must not import build.
  """

  from __future__ import annotations
  ```
  Move the functions verbatim. `_write_build_artifacts` calls `_serialize_lowered_workflows`, `_serialize_lexical_checkpoint_points`, etc. — all moving together, so no cross-module edit. `_serialize_workflow_boundary_projection` and `_validate_selected_workflow_hidden_compatibility_bridge_public_boundary` call `checked_design_delta_public_input_names` / `is_design_delta_parent_drain_target_workflow` — import those from `.phase_family_boundary` (copy the exact import line from build.py). Add `from .build_manifest_io import _json_data, _sha256_path, _cli_request_diagnostic` and, if any serializer references a design-delta provenance helper, `from .build_design_delta import _boundary_authority_registry_provenance, _value_flow_census_provenance, _consumer_rendering_census_provenance, _observability_old_writer_pair_provenance` (verify with grep — `_build_manifest` uses all four).

- [ ] **Step 3: Re-export from `build.py`**

  Delete the moved defs; add a `from .build_artifacts import (...)` block listing every moved name. `_display_workflow_name`, `_origin_payload`, `_json_data` must be reachable from `build` for the feasibility test and CLI explain — since Task 1 already re-exports `_json_data` from build_manifest_io, do not double-import it; keep a single source. Confirm `_cli_request_diagnostic` still comes from `build_manifest_io` (Task 1), not re-declared here.

- [ ] **Step 4: Verify import graph and external importers**

  ```bash
  python -c "import orchestrator.workflow_lisp.build, orchestrator.workflow_lisp.build_artifacts; print('IMPORT_OK')"
  python -c "from orchestrator.workflow_lisp.build import _display_workflow_name, _origin_payload, _json_data; print('REEXPORT_OK')"
  python -c "from orchestrator.cli.commands import explain; print('CLI_OK')"
  pyflakes orchestrator/workflow_lisp/build_artifacts.py orchestrator/workflow_lisp/build.py
  ```
  Expected: `IMPORT_OK`, `REEXPORT_OK`, `CLI_OK`; pyflakes silent on both (a residual unused import in build.py means a helper the writers used is now only imported for re-export — that is expected and pyflakes should not flag re-exported-then-used names; if it flags a genuinely-unused import, remove it).

- [ ] **Step 5: Full artifact + fingerprint parity**

  ```bash
  pytest tests/test_workflow_lisp_build_artifacts.py -q
  pytest tests/test_workflow_lisp_entry_publication.py tests/test_workflow_lisp_rendering_ergonomics.py tests/test_workflow_lisp_lexical_checkpoint_restore.py -q
  pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q -k "smoke"
  ```
  Expected: PASS. `test_workflow_lisp_build_artifacts.py` reads emitted JSON and asserts fingerprints — a fingerprint drift here means `_fingerprint_build` changed inputs during the move (it must not). STOP and diff on any fingerprint failure.

- [ ] **Step 6: Commit**

  ```bash
  git add orchestrator/workflow_lisp/build.py orchestrator/workflow_lisp/build_artifacts.py
  git commit -m "Move build artifact writers and serializers to sibling module"
  ```

---

## Task 4: Design and thread the narrowing `DesignDeltaEvidence` / `DesignDeltaReportPayloads` interface

Now that the free functions live in `build_design_delta.py` and the writer lives in `build_artifacts.py`, replace the interleaved loose-variable threading in `build_frontend_bundle` with two dataclasses. This is the payoff: `_write_build_artifacts`'s ~18 optional design-delta kwargs collapse to **one** `DesignDeltaReportPayloads` bundle, and the loader outputs collapse to **one** `DesignDeltaEvidence` bundle. Retiring the lane later becomes: delete `build_design_delta.py`, delete the two bundle-construction calls, delete one field.

**This task changes control flow shape but not behavior.** The certification region's raises stay exactly where they are — they move as a unit into a `serialize_design_delta_reports` function that returns the payload bundle (raising identically on mismatch).

**Files:**
- Modify: `orchestrator/workflow_lisp/build_design_delta.py` (add the two dataclasses + `load_design_delta_evidence` + `serialize_design_delta_reports`)
- Modify: `orchestrator/workflow_lisp/build_artifacts.py` (`_write_build_artifacts` accepts one `DesignDeltaReportPayloads | None` in place of the ~18 design-delta kwargs)
- Modify: `orchestrator/workflow_lisp/build.py` (`build_frontend_bundle` calls the two new functions instead of the interleaved block)

**Interfaces — designed field-by-field from the verified sources:**

`DesignDeltaEvidence` bundles the **loader outputs** threaded through `build_frontend_bundle` into `_fingerprint_build`, `_build_manifest`, and the certification region (verified against those three signatures):

```python
@dataclass(frozen=True)
class DesignDeltaEvidence:
    """Design-delta certification inputs loaded once, threaded to fingerprint/manifest/reports.

    All fields are None for non-design-delta builds. This is the single field that a
    future retirement of the certification lane removes from build_frontend_bundle.
    """
    family_profile_catalog: WorkflowFamilyProfileCatalog | None
    family_profile_metadata: Mapping[str, object] | None
    boundary_authority_registry: Mapping[str, object] | None
    value_flow_census: Mapping[str, object] | None
    consumer_rendering_census: Mapping[str, object] | None
    observability_old_writer_pair_manifest: Mapping[str, object] | None
    compatibility_bridge_manifest: Mapping[str, object] | None
    transition_authoring_manifest: Mapping[str, object] | None
    resume_plumbing_retirement_manifest: Mapping[str, object] | None
    view_dual_run_vectors: Mapping[str, object] | None
    view_dual_run_report: Mapping[str, object] | None
```

`DesignDeltaReportPayloads` bundles the **18 optional design-delta artifact payloads** that `_write_build_artifacts` currently takes as loose kwargs. Verified field-by-field against `_write_build_artifacts` (lines ~4919-4939) and its `build_frontend_bundle` call site (~1671-1687) — these are exactly the payloads whose `if payload is not None:` blocks add an artifact file:

```python
@dataclass(frozen=True)
class DesignDeltaReportPayloads:
    """Optional design-delta report artifacts, replacing the loose kwargs of _write_build_artifacts.

    Every field defaults to None / empty and maps 1:1 to an emitted <name>.json artifact
    when populated. For non-design-delta builds all fields are None and no design-delta
    artifact is written.
    """
    adapter_census: Mapping[str, object] | None = None
    boundary_authority_report: Mapping[str, object] | None = None
    value_flow_census_report: Mapping[str, object] | None = None
    consumer_rendering_census_report: Mapping[str, object] | None = None
    typed_prompt_input_report: Mapping[str, object] | None = None
    observability_summary_report: Mapping[str, object] | None = None
    entry_publication_report: Mapping[str, object] | None = None
    compatibility_bridge_report: Mapping[str, object] | None = None
    compatibility_bridge_generated_steps: Sequence[Mapping[str, object]] = ()
    rendering_cleanup_report: Mapping[str, object] | None = None
    rendering_ergonomics_report: Mapping[str, object] | None = None
    transition_authoring_report: Mapping[str, object] | None = None
    resume_plumbing_retirement_report: Mapping[str, object] | None = None
    parent_drain_census_alignment_report: Mapping[str, object] | None = None
    reference_family_conformance_profile: Mapping[str, object] | None = None
    default_resume_report: Mapping[str, object] | None = None
    g8_deletion_evidence: Mapping[str, object] | None = None
    checkpoint_points_for_retirement: Mapping[str, object] | None = None
    checkpoint_shadow_report_for_retirement: Mapping[str, object] | None = None
```

Signatures:
```python
def load_design_delta_evidence(
    *,
    entry_workflow: str | None,
    canonical_entry_name: str,
    source_path: Path,
    command_boundary_manifest: Mapping[str, object],
) -> DesignDeltaEvidence: ...

def serialize_design_delta_reports(
    evidence: DesignDeltaEvidence,
    *,
    compile_result: LinkedStage3CompileResult,
    entry_selection: FrontendEntrySelection,
    validated_bundles_by_name: Mapping[str, LoadedWorkflowBundle],
    workflow_boundary_projection_payload: Mapping[str, object],
    source_map_payload: Mapping[str, object],
    command_boundaries: ...,
    command_boundary_manifest: Mapping[str, object],
    provider_externs: Mapping[str, str],
    prompt_externs: Mapping[str, object],
    resolved_request: FrontendBuildRequest,
    build_root: Path,
) -> DesignDeltaReportPayloads: ...
```

**Constraint:** `serialize_design_delta_reports` contains the entire certification region (currently `build_frontend_bundle` ~808-1611) **moved verbatim**, including every `raise LispFrontendCompileError(...)`. This is the load-bearing behavior. The two `checkpoint_*_for_retirement` fields carry the retirement-serializer outputs currently computed at ~1358-1363 and written via `_write_build_artifacts`'s `lexical_checkpoint_points` / `..._shadow_report` slots when the retirement path is active — verify their exact write mechanism at Step 2 and preserve it (they override the normal checkpoint payloads on the retirement path; do not double-emit).

- [ ] **Step 1: Extract `load_design_delta_evidence`**

  In `build_design_delta.py`, write `load_design_delta_evidence` that calls the already-moved `_maybe_load_design_delta_*` loaders in the **same order and with the same gating** as `build_frontend_bundle` currently does (verify the order and the `if boundary_authority_registry is not None:` / `if consumer_rendering_census is not None and value_flow_census is not None:` guards against lines ~662-718 and ~831-845). Return a `DesignDeltaEvidence`. In `build_frontend_bundle`, replace the loader block with:
  ```python
  design_delta = load_design_delta_evidence(
      entry_workflow=resolved_request.entry_workflow,
      canonical_entry_name=entry_selection.canonical_name,
      source_path=resolved_request.source_path,
      command_boundary_manifest=command_boundary_manifest,
  )
  ```
  Update `_fingerprint_build` and `_build_manifest` call sites to read `design_delta.boundary_authority_registry` etc. (or pass the bundle and unpack inside — choose the smaller diff; passing the bundle is fewer edits but widens those two signatures, so prefer reading fields at the call site).

  Note: `family_profile_catalog` is needed by `compile_stage3_entrypoint` (line ~679) **before** `entry_selection` exists, and `boundary_authority_registry` needs `entry_selection.canonical_name`. So `load_design_delta_evidence` cannot load everything in one call — the catalog loads first. Resolve by either (a) a two-phase load (`load_design_delta_family_catalog(...)` returns the catalog; `load_design_delta_evidence(catalog, entry_selection, ...)` returns the rest), or (b) keep the catalog load inline and bundle the rest. **Choose (a)** — it keeps the compile-order dependency explicit. Add `load_design_delta_family_catalog(*, entry_workflow, source_path) -> WorkflowFamilyProfileCatalog | None` to the interface and have `DesignDeltaEvidence` carry the already-loaded catalog.

- [ ] **Step 2: Extract `serialize_design_delta_reports`**

  Cut the certification region from `build_frontend_bundle` (the block that assigns the 18 report payloads, ~808-1611, plus the two retirement-serializer calls ~1358-1363) into `serialize_design_delta_reports` in `build_design_delta.py`. Return a populated `DesignDeltaReportPayloads`. Every `raise LispFrontendCompileError(...)` moves verbatim. In `build_frontend_bundle`, replace the region with:
  ```python
  report_payloads = serialize_design_delta_reports(design_delta, compile_result=compile_result, ...)
  ```
  Verify the retirement-path checkpoint override:
  ```bash
  grep -n "checkpoint_points_payload\|checkpoint_shadow_report_payload\|_serialize_lexical_checkpoint_points_for_retirement" orchestrator/workflow_lisp/build.py
  ```
  Preserve whatever overrides the normal checkpoint artifacts on the retirement path.

- [ ] **Step 3: Narrow `_write_build_artifacts`**

  In `build_artifacts.py`, replace the 18 loose design-delta kwargs of `_write_build_artifacts` with a single `design_delta_reports: DesignDeltaReportPayloads | None = None` parameter. Group the `if payload is not None: artifact_paths[...] = ...; payloads[...] = _json_data(payload)` blocks behind **one private helper** `_add_design_delta_artifacts(artifact_paths, payloads, build_root, reports)` so a future retirement deletes it cleanly. Keep the core (non-design-delta) artifact set exactly as-is. **Do NOT merge design-delta payload handling into the core artifact dict** — keep it isolated behind the helper.

  Update the `build_frontend_bundle` call: `_write_build_artifacts(..., design_delta_reports=report_payloads)`.

- [ ] **Step 4: Verify byte-identical artifacts and identical failure modes**

  ```bash
  pytest tests/test_workflow_lisp_build_artifacts.py -q
  pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q
  pytest tests/test_workflow_lisp_view_dual_run.py tests/test_workflow_lisp_transition_authoring.py tests/test_workflow_lisp_entry_publication.py -q
  ```
  Expected: PASS with **no** fingerprint or artifact-content diffs (the build tree is content-addressed; if a design-delta build lands in a different `build_root` fingerprint, an input changed — STOP). Run the full feasibility suite (not just `-k smoke`) here because this task moves the raises.

- [ ] **Step 5: Confirm the retirement-deletion story holds (documentation-as-test)**

  Verify the excision is now a 3-edit deletion by inspection:
  ```bash
  grep -c "load_design_delta_family_catalog\|load_design_delta_evidence\|serialize_design_delta_reports" orchestrator/workflow_lisp/build.py
  grep -c "DesignDeltaEvidence\|DesignDeltaReportPayloads" orchestrator/workflow_lisp/build.py
  ```
  Expected: the design-delta call surface in `build.py` is now a small, countable set (the two/three bundle constructors + the `design_delta`/`report_payloads` locals). Record the count in the commit body as the retirement-cost metric.

- [ ] **Step 6: Commit**

  ```bash
  git add orchestrator/workflow_lisp/build.py orchestrator/workflow_lisp/build_design_delta.py orchestrator/workflow_lisp/build_artifacts.py
  git commit -m "Thread design-delta reports through evidence and payload bundles"
  ```

---

## Task 5: Slice `build_frontend_bundle` into stage functions inside `build.py`

With the three siblings extracted, `build_frontend_bundle` is now compile → select/reattach → assemble-reports → emit. Extract four private stage functions **inside `build.py`** (no new module) to bring the function under the complexity budget and make the pipeline legible. Pure mechanical extraction — no behavior change.

**Files:**
- Modify: `orchestrator/workflow_lisp/build.py`

**Interfaces (all private, all inside build.py):**
- `_compile_entry(resolved_request, *, family_catalog) -> (compile_result, entry_selection)` — the manifest loads + `compile_stage3_entrypoint` + `_select_entry_workflow`.
- `_select_and_reattach(compile_result, entry_selection, *, resolved_request, design_delta) -> (validated_bundle, validated_bundles_by_name, source_map_payload, workflow_boundary_projection_payload, build_root, fingerprint, provenance)` — the bridge materialization + provenance/semantic-IR reattach + fingerprint + build_root.
- `_assemble_reports(design_delta, *, compile_result, entry_selection, ...) -> DesignDeltaReportPayloads` — thin wrapper over `serialize_design_delta_reports` (mostly argument marshalling; keep only if it reduces the `build_frontend_bundle` argument-threading noise).
- `_emit(validated_bundle, report_payloads, *, build_root, ...) -> FrontendBuildResult` — `_write_build_artifacts` + `_build_manifest` + manifest write + `FrontendBuildResult` construction.

- [ ] **Step 1: Re-anchor the body regions**

  Run:
  ```bash
  grep -n "def build_frontend_bundle\|compile_stage3_entrypoint(\|_select_entry_workflow(\|_materialize_design_delta_compatibility_bridge_bundles(\|_fingerprint_build(\|_write_build_artifacts(\|return FrontendBuildResult" orchestrator/workflow_lisp/build.py
  ```
  These mark the four stage boundaries. Confirm they appear in ascending order within `build_frontend_bundle`.

- [ ] **Step 2: Extract the four stage functions**

  Mechanically extract each region into a private function taking exactly the locals it reads and returning exactly the locals its callers need downstream. Use a small `@dataclass` for the `_select_and_reattach` return tuple if it exceeds ~5 elements (readability). Keep every line verbatim; only introduce the parameter/return plumbing.

- [ ] **Step 3: Verify complexity and behavior**

  ```bash
  python -c "import orchestrator.workflow_lisp.build; print('OK')"
  # optional cyclomatic check if radon is available; otherwise wc -l as a proxy
  awk '/^def build_frontend_bundle/,/^def [a-zA-Z]/' orchestrator/workflow_lisp/build.py | wc -l
  pytest tests/test_workflow_lisp_build_artifacts.py -q
  pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q -k "smoke"
  pytest tests/workflow_lisp_characterization.py -q 2>/dev/null || pytest tests/test_workflow_lisp_wcc_m1.py tests/test_workflow_lisp_wcc_m2.py -q
  ```
  Expected: `build_frontend_bundle` body shrinks to a short orchestration sequence; all suites PASS.

- [ ] **Step 4: Commit**

  ```bash
  git add orchestrator/workflow_lisp/build.py
  git commit -m "Slice frontend bundle build into compile select assemble emit stages"
  ```

---

## Final gate

### Task 6: Full-suite verification + module-size check

- [ ] **Step 1: Confirm the size goal**

  ```bash
  wc -l orchestrator/workflow_lisp/build.py orchestrator/workflow_lisp/build_manifest_io.py orchestrator/workflow_lisp/build_design_delta.py orchestrator/workflow_lisp/build_artifacts.py
  ```
  Expected: each module materially smaller than the 6,075-line original. `build.py` should now be roughly the public dataclasses + `build_frontend_bundle` + stage helpers + re-export blocks. (The 500-line house guideline is aspirational for the two largest siblings, which may exceed it; note any that do and whether a further split is warranted.)

- [ ] **Step 2: Full suite (long-running — use the tmux skill)**

  Run in tmux: `pytest -q`
  Expected: same failures-before == failures-after relative to the Entry-gate baseline. Any *new* red is a regression from the split — STOP and bisect against the per-task commits.

- [ ] **Step 3: Certification compile smoke**

  ```bash
  pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q
  pytest tests/test_workflow_lisp_build_artifacts.py -q
  ```
  Expected: PASS.

- [ ] **Step 4: Report**

  Summarize: lines per module before/after, the re-exports kept (with their external importers), the `DesignDeltaEvidence`/`DesignDeltaReportPayloads` field counts, and the measured retirement cost from Task 4 Step 5. Do not push; leave commits local for review.
