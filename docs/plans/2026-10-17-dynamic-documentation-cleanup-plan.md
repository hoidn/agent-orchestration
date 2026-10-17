# Dynamic Branch Documentation Cleanup

Goal: a reader of the maintained docs can tell what runs, how to run it and
where it stops, without decoding status, authority or delivery-history prose.

Owner decisions (2026-10-17):

- Historical records (`docs/plans/`, `docs/reports/`, `docs/superpowers/`,
  `docs/backlog/`) stay in the tree unchanged. Maintained docs stop citing
  them, except one History section in `docs/index.md`, a design doc's own
  plan link when the design is unimplemented, and an experiment README's link
  to its own result report.
- Typed 2.35/2.36 and native 3.0 are peer profiles chosen by need: typed for
  checked types and resume, native for ordinary functions/closures with
  fresh-only runs. No candidate, adoption, selection or qualification framing.
- Depth: rewrite maintained guides, entry points, catalogs and experiment
  READMEs; change spec wording only (no semantic change); rewrite only the
  metadata/status block of each design doc.

## Writing rules for maintained docs

Remove:

- status/authority boilerplate (`Status: informative ...`, `Normative
  authority: ...`, `Authority lane`, "this page does not select/authorize ...");
- commit, tree and SHA-256 identifiers, review tokens (`*_APPROVED`, `PASS_*`),
  pass/fail counts, task/phase/gate/tranche labels (DC-2, DC-3, DC-F, DC-U,
  DC-P, EL-1, EC-1, CF-1, PC-1, Q0–Q5, L0–L5, M*, MR-*, E0–E3, R0–R3, ES, G1,
  Stage N, Task N) unless the label is a user-visible feature name;
- "branch-qualified", "qualified", "qualification", "candidate", "adoption",
  "selected"/"unselected", "owner-parked", "frozen", "does not certify",
  "no default change";
- delivery narration ("Stage 6 is complete", "Task 7 removed", "now imported",
  "earlier comparison", "the historical report preserves").

Keep:

- what runs: profiles and targets (2.34, 2.35, 2.36, 3.0 are real version
  identifiers), forms, commands, inputs, outputs, user-visible errors;
- limits stated plainly in present tense (for example "native 3.0 runs are
  fresh-only: no resume, retries or result reuse");
- links to the spec or design that owns the behavior, and to runnable examples
  and tests where a reader would use them;
- the `Implemented / Partial / Library / Designed / Future / Retired / Legacy`
  labels in the capability matrix, which `AGENTS.md` names.

## Renamed anchors

| Old | New |
| --- | --- |
| `specs/versioning.md#branch-qualified-target-30` | `#native-target-30` (heading `## Native target 3.0`) |
| `lisp_workflow_drafting_guide.md#2b-dynamic-composition-on-the-qualified-branch` | `#2b-native-30-dynamic-composition` (heading `## 2B. Native 3.0 Dynamic Composition`) |

Every maintained link to an old anchor moves to the new one. Historical
records keep their old fragments; those fall back to the top of the page.

## Work slices (disjoint files)

1. Entry and routing: `README.md`, `docs/index.md` (compact router plus one
   History section), `docs/documentation_conventions.md` (rewritten to the
   rules above), `MIND_MAP.md`, `docs/architecture_overview.md`,
   `docs/orchestration_start_here.md`.
2. Status surfaces: `docs/capability_status_matrix.md` (one sentence of notes
   per row, no evidence hashes), `docs/design/README.md`, metadata/status
   blocks of `docs/design/*.md`.
3. `docs/lisp_workflow_drafting_guide.md`.
4. Remaining guides and catalogs: `docs/lisp_library_reference.md`,
   `docs/orc_workflow_design_lessons.md`, `docs/runtime_execution_lifecycle.md`,
   `docs/work_definition_model.md`, `docs/workflow_lisp_mvp_comparison.md`,
   `docs/omp_upgrade_runbook.md`, other top-level `docs/*.md` that are not
   historical YAML references, `workflows/**/README.md`, `prompts/README.md`,
   `experiments/*/README.md`.
5. Specs wording: `specs/*.md`.

Doc-content tests (`tests/test_workflow_lisp_drain_roadmap_routing.py` and
others that read maintained docs) are updated alongside each slice: assertions
on routing that still exists move to the new text; assertions that pin removed
status prose, hashes or history are replaced with assertions on the route or
contract they protected, or deleted when no route remains.

## Verification

- Relative links and anchors in maintained docs resolve.
- No maintained doc contains the removed terms (search list above).
- Baseline doc-reading test set (64 files) passes at the same or better level
  than the pre-cleanup baseline; `pytest --collect-only` on edited test files.
- `python -m orchestrator compile` on the README compile example still runs.
