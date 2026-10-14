# Workflow Lisp library reference implementation plan

**Goal:** Give authors one task-oriented reference for candidate generation,
evaluation, selection and review/revision, while shortening the drafting guide.

**Accepted approach:** Add `docs/lisp_library_reference.md`. Distinguish reusable
library APIs from example workflows and language composition patterns. Move the
`std/improve` usage detail out of the drafting guide; retain brief guidance and
links, including destinations for existing section anchors. No runtime, workflow,
prompt, manifest, or language changes are selected.

**Authority:** Start with `docs/index.md`, the capability status matrix and the
design index. Existing composition-first/write-once designs govern `std/improve`;
the evaluated execution and command adapter contracts govern current admission.
Canonical `.orc` sources, manifests and their tests establish example behavior.

## Steps

- [x] Add the reference with a task chooser and entries for best-of-N,
  `std/improve`, external evaluation and iterative search. Each entry identifies
  kind, availability, inputs/outputs, dependencies, complete source or a clearly
  bounded complete expression, execution route and operational limits. Explain
  where candidate names and external adapter definitions originate. Prefer
  canonical sources over invented APIs or a second implementation.
- [x] Move existing `std/improve` details from the drafting guide, correcting
  stale descriptions against current sources. Keep old heading anchors as short
  forwarding sections. Replace the obsolete adjudicated-provider recommendation
  with the supported explicit composition route. Preserve unrelated content.
- [x] Route readers from `docs/index.md`, `workflows/README.md` and the pattern
  chooser in `docs/orc_workflow_design_lessons.md`; update active recipe links in
  `docs/capability_status_matrix.md`. Leave historical evidence intact.
- [x] Check Markdown paths and heading anchors, compare copied source with its
  owner, and compile complete reference source examples through the public CLI
  using temporary build/state roots. Existing narrow consumer tests may supply
  runtime evidence where needed; do not spend on live providers. Docs-only changes
  do not require a full runtime suite. Record verification and scope explicitly.
- [x] Obtain an independent review of coverage, accuracy and usability, resolve
  findings, inspect the task diff and verify existing dirty work is preserved.

## Boundaries

The reference is informative and task-oriented, not a new normative spec or a
complete catalog of every historical stdlib module. Existing best-of-N uses
pre-created clones and a serial bounded map; it selects without merging. A clone
is not an OS sandbox. Expression environments remain proposed and unimplemented.
Selection, numerical evaluation and iterative improvement are distinct policies.
Keep the workspace's pre-existing modifications; do not stage or commit them.

## Verification record

Completed 2026-10-14. Independent plan and final reference reviews passed;
review precision about branch-only repair/stall behavior was incorporated.

- 12 selected public consumer tests passed in 92.13s, covering best-of-N,
  `std/improve` outcomes and compact search.
- Three complete documented modules compiled; proposal dry-run, standalone
  evaluator execution, compact search execution, and both completed-run
  resume/report paths passed (11 public CLI commands). The evaluator returned
  valid score zero for `(2, 3)`; search solved that candidate in 10 evaluations.
- The initial standalone evaluator failed `module_path_mismatch`; the final
  example has its own module identity and a fully shown matching manifest.
- 53 new/changed local links passed; every previous guide heading anchor remains.
  Canonical module copies and the adapted evaluator manifest were compared to
  source. The guide shrank from 3,090 to 2,923 lines.
- Unrelated tracked diffs and untouched guide sections match the pre-edit
  snapshots. Whitespace checks passed.

Receipts are under `/tmp/orc-library-reference-wf013q13`, also recorded in
`/tmp/orc-library-reference-current`. No live providers or broad runtime suite
were run: production code, maintained workflows, prompts and manifests did not
change. The documentation pass left changes unstaged; a subsequent user request authorized
the scoped commit. Links to the earlier untracked expression-environments design
were removed so this documentation commit stands on its own.
