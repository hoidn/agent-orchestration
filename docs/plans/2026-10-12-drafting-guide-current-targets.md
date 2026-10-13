# Current-target Workflow Lisp drafting guide cleanup

> **For agentic workers:** Use superpowers:subagent-driven-development for the scoped documentation revision and independent review.

**Goal:** Remove obsolete pre-2.35 authoring instructions from the drafting guide without treating still-supported language features or historical runtime evidence as deprecated.

**Architecture:** Keep the guide focused on the admitted evaluated execution surface at 2.35 and 2.36. Preserve relevant compatibility pointers and the real 2.35/2.36 distinctions; leave normative contracts, historical fixtures, and persisted-run behavior unchanged.

**Tech stack:** Markdown documentation, existing pytest behavioral owners, public orchestrator CLI.

## Scope and authority

- Start from `docs/index.md`, `docs/capability_status_matrix.md`, and `docs/design/README.md`.
- Admission and compatibility are governed by `specs/versioning.md`, the evaluated sections of `specs/cli.md`, `specs/io.md`, and `specs/state.md`, and `docs/design/workflow_lisp_evaluated_execution.md`.
- Keep features introduced before 2.35 when admitted by current targets. Do not mechanically retarget historical examples or promise excluded effects.
- Preserve unrelated dirty work, including existing changes to the index and capability matrix.
- This is a guide cleanup, not a new runtime feature, general documentation redesign, or migration of workflows.

## Tasks

- [x] Review the removal boundary against current admission and compatibility contracts.
- [x] Revise `docs/lisp_workflow_drafting_guide.md`: remove the old shape/workaround catalogue, replace obsolete flat-pipeline and target-selection advice, retire old-only executable recipes to brief owner links, and retain current lifecycle/W3 guidance and still-valid authoring principles. Keep useful inbound anchors where possible.
- [x] Reconcile directly affected routes in `docs/index.md` and any other maintained pages whose links/descriptions are invalidated by this cleanup.
- [x] Reconcile `tests/test_workflow_lisp_guide_programs.py` with the removal of historical quotations while preserving all historical behavioral cases and fixture coverage. Do not keep a vacuous quote check or duplicate the deleted guide solely to satisfy it.
- [x] Run collection if tests are renamed/added, narrow affected checks, local link/anchor checks, and an existing public evaluated lifecycle smoke. Run a broader relevant documentation/runtime subset with `pytest -q -n 16 --dist=worksteal` in tmux after the narrow checks.
- [x] Obtain independent documentation review, inspect the final diff and fresh verification evidence, and report the removal scope and any retained compatibility limits.

## Verification boundaries

The existing public evaluated smoke supplies the end-to-end integration check; the historical behavioral tests protect the supported old routes. This change does not require executing every unchanged schematic fragment in the long reference guide or rerunning provider experiments. New or changed runnable recipes must be exercised, rather than inferred correct from inspection.

## Completed verification

- Independent documentation review accepted the final admission, recovery, authority, example routing and compatibility-anchor changes.
- The renamed historical module collected 84 cases. Its `CASES` AST is unchanged; representative success/refusal and fixture coverage passed (3 tests).
- Four affected documentation routing selectors passed.
- The broader relevant group passed: `pytest -q -n 16 --dist=worksteal tests/test_workflow_lisp_guide_programs.py tests/test_workflow_lisp_drain_roadmap_routing.py tests/test_workflow_evaluated_totality.py tests/test_workflow_evaluated_consumers.py` — 576 passed in 276.39 seconds.
- Public evaluated compile/run/resume/invalidate/resume smoke passed in the baseline checks. All nine fenced blocks in the retained public lifecycle recipe are unchanged.
- The changed minimal example compiled and ran at 2.35 with explicit extern manifests and the existing deterministic provider shim; one dispatch committed the typed union and completed with the expected report path.
- Guide outbound file/anchor links and all 41 incoming anchor links resolve; scoped `git diff --check` passed.

No full-repository suite or real provider invocation was needed for this documentation-only cleanup. Historical runtime support and fixtures remain unchanged.
