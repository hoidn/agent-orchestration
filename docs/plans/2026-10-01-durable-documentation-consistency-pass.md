# August–October Durable Documentation Consistency Pass

> **For agentic workers:** Use `superpowers:subagent-driven-development` for
> scoped repairs, with read-only parallel reviews and coordinator integration.

**Goal:** Reconcile Phase 2 integration and durable concepts changed from
2026-08-01 through the 2026-10-01 checkout, including relevant local changes,
across their authorities, guidance and discovery routes.

**Architecture:** Follow `docs/index.md`, `docs/documentation_conventions.md`
and `docs/capability_status_matrix.md` to the owning specs/designs, then trace
each changed concept through guides, examples and current selection state.
Preserve historical evidence and unrelated local edits. This is a documentation
repair, not authorization to implement pending features or rerun experiments.
Prioritize maintained indexes, specs, designs and guides. Historical records
provide evidence; use only a brief checkpoint notice when readers otherwise
mistake them for current guidance.

**Tech stack:** Markdown, repository history, source/test lookup, existing
validators and safe provider-free command checks.

## Tasks

- [x] Recover the concept footprint from history and the working diff; review
  this plan against the user's scope and the consistency-pass skill.
- [x] Reconcile evaluated execution and Phase 2: target 2.35, internal compiler
  delivery, public CLI availability, closed-program contracts, and later
  runtime/pilot/consumer migration routing.
- [x] Reconcile language changes: strict Boolean control flow, targets
  2.28–2.34, composition, generic unions, pure calls, numeric boundaries and
  repaired defects. Trace current guidance separately from proposed changes.
- [x] Reconcile operational changes: E1/E2 run references and trials, OMP-I1,
  provider context/human input, resume integrity, workspace locks and watchdogs.
- [x] Reconcile research and selection: ES/F1v2, five-axis ORC research,
  effectiveness claims, REC/ME/P-series routing, and relevant local amendments.
- [x] Patch discovery routes (`README.md`, `docs/index.md`,
  `docs/design/README.md`, the capability matrix and workflow/prompt catalogs)
  wherever those concept reviews find stale descriptions or missing routes.
- [x] Validate changed paths/anchors and documented commands; run focused
  checks matching the repaired claims. Inspect the final diff and record
  coverage, intentional historical distinctions and unresolved limitations.

## Verification And Coverage

Use path/symbol/section references in maintained documentation. Status claims
must distinguish implementation, public availability, research selection and
utility evidence. Do not edit historical configurations/results to make them
look current. No live provider calls are needed for this pass. If a repair
requires changing a machine-readable contract, workflow or prompt, validate its
syntax/selection rules and run an appropriate provider-free smoke check.

Record verification results here after integration; link success alone does
not establish semantic agreement or concept coverage.

## Coverage And Decisions

The history window starts at 2026-08-01 and ends at integration `b1c33590`,
with the relevant local ES/demo amendments read as additional evidence.
Three read-only reviewers covered language, operations and research; the
coordinator traced Phase 2 and integrated shared routes. This is a concept
review of recent durable changes and their dependents, not a line-by-line
audit of all repository history or a correctness review of unrelated local
implementation work.

- Phase 2: owning execution design, frontend baseline, selected plans,
  versioning, guide, indexes, internal builder and public target guards.
  Partial compiler delivery does not imply public compilation or execution.
- Language: strict Boolean control, value/continuation composition, generic
  unions, pure helpers, numeric boundaries and the shared defect repairs.
  Repaired resume/diagnostic behavior is distinguished from remaining
  positional and capture defects. Repetition reduction remains unapproved;
  its stale recommendation of an already allocated target is unresolved.
- Operations: run references/trials, OMP-I1, portable context, host input,
  resume projection integrity and workspace/watchdog ownership. The portable
  context design now distinguishes delivered 2.31 carriage from future native
  work. OMP's provider and I/O/state contracts describe caller prerequisites
  and memory-only transport; the maintained runbook owns environment/broker
  preparation. No provider implementation changed.
- Research: ES/F1v2 and its frozen adoption contract, the five-axis roadmap,
  assisted C1, single-call and paired-search claims, and REC/ME/P routing.
  Historical experiments are not rerun or relabeled as current evidence.
  The invocation-guidance portion of the existing C1 proposal is addressed
  under this documentation pass; its receipt-interface implementation and
  any further study allocation remain unselected. Budget and experiment
  manifests, frozen plans and retained measurements are unchanged by this pass.
- Copy safety: the September promotion of `std/improve` remains in force.
  The document-review example compiles without explicit entry selection;
  its explicitly selected entry still hits the bootstrap gate and its
  registry role remains `not_current_guidance`.

The user's priority clarification prompted a retrospective scope review, not
only a final check: current spec and architecture indexes now route numeric,
evaluated-execution and OMP usage directly to maintained contracts/guides.
Additional durable contradictions in provider context, OMP transport and
comparative guidance were repaired. Body rewrites in the historical paired-
search reports were removed in favor of short checkpoint notices, and this
pass's added demo-report banner was removed. Preexisting report edits remain.

## Verification Record

Fresh checks from the repository root:

- `pytest -q -p no:cacheprovider tests/test_workflow_lisp_target_evaluated_execution.py tests/test_workflow_lisp_closed_program_build.py`:
  **63 passed**. A temporary provider-free public CLI probe also compiled
  target 2.34 and confirmed target 2.35 exits 2 with
  `evaluated_execution_unavailable`.
- `pytest -q -p no:cacheprovider tests/test_workflow_lisp_route_readiness.py tests/test_workflow_lisp_improve_example_e2e.py tests/test_workflow_resume_known_defects.py tests/test_workflow_lisp_target_234.py tests/test_workflow_lisp_guide_programs.py`:
  **192 passed, 2 xfailed, 1 failed**. The failed peer-group resume test
  stopped before its intended interruption: retained state records
  `provider_peer_group_failed`, `[Errno 1] Operation not permitted`.
  A minimal local Unix-socket bind/listen probe reproduced the same refusal.
  The sandbox also denied the requested tmux socket, so this focused run
  used the terminal tool's asynchronous session. No test was weakened or
  hidden; peer-group resume was not revalidated in this environment.
- `python -m orchestrator workflow-lisp-route-readiness --check`:
  **61 surfaces, zero issues**, with unchanged selection/copy-safety fields.
  The JSON edit reconciles one stale explanatory note only.
- Public compilation of `review_revise_design_docs.orc` without
  `--entry-workflow`, with its provider/prompt manifests: **exit 0**,
  `status: accepted`, no diagnostics. The README retains this compile-only
  recipe without promoting runtime readiness.
- `pytest -q -p no:cacheprovider tests/test_workflow_lisp_command_boundary_closure.py`:
  **27 passed**, covering the newly documented internal manifest/configuration
  delivery and older-target compatibility. Runtime closure checks remain
  separately gated.
- `pytest -q -p no:cacheprovider tests/test_workflow_lisp_closed_program_artifact.py tests/test_workflow_lisp_closed_program_names.py tests/test_workflow_lisp_closed_program_frontend.py`:
  **100 passed**, checking internal artifact validation, canonical identities
  and typed source-graph compilation after reconciling the design's stale
  feasibility rows. These checks do not establish public CLI delivery.
- Operational guide checks: `trial --help` and `resume --help` succeeded;
  a temporary module containing the documented path-mode `run-ref` specimen
  compiled without invoking providers or child runs.
- OMP session/launch-contract checks plus the three missing/misspelled/malformed
  broker refusal selectors: **22 passed**. The new setup recipe was checked
  against the launcher and shell syntax; no live credential broker was started.
- `pytest -q -p no:cacheprovider tests/test_workflow_lisp_provider_context_e2e.py`:
  **9 passed**, covering the portable-context design's public carriage,
  branching, loop and resume claims with fixture providers.
- Local Markdown link/anchor check: **1,155 links across 64 documents, zero
  unresolved links**. The roadmap's missing 2026-07-22 effectiveness analysis
  is explicitly identified as unavailable historical provenance, with a link
  to later retained pilot evidence rather than a fabricated replacement.
- `git diff --check` and registry JSON parsing passed. Independent language,
  operations and research reviews closed with no remaining findings after
  corrections; the coordinator also inspected the resulting diffs.
- Reviewer checks: **16 passed** for selected resume/diagnostic/pure-helper
  cases; **28 passed, 8 xfailed** for selected scope/capture cases; **1 passed**
  for sequential imported host questions; **72 passed** for CLI trials,
  OMP pinning and watchdog workspace checks. These overlap some coordinator
  checks and are not added into a unique-test total.

The full pytest suite and live-provider studies are not required for these
documentation and explanatory registry-note changes. Remaining runtime
defects and numeric diagnostic/coverage limits remain documented, not fixed
by this pass.
