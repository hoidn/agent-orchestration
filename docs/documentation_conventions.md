# Documentation Conventions

Rules for adding or editing maintained docs: `README.md`, `MIND_MAP.md`, top-level
`docs/*.md`, `docs/design/`, `docs/templates/`, `specs/`, and the READMEs under
`workflows/`, `prompts/` and `experiments/`.

A reader should be able to tell from any page what it covers, what runs, how to
use it and where it stops.

## Current Guidance And Historical Records

- `specs/` defines normative runtime and language behavior. If a doc and a spec
  disagree, fix the doc (or change the spec on purpose).
- `docs/design/` explains how a feature works and why. A design that is not
  implemented yet may link its own plan.
- Guides, catalogs and indexes route readers to the owning spec or design; they
  do not redefine behavior.
- [`capability_status_matrix.md`](capability_status_matrix.md) records whether a
  surface runs.
- History lives in `docs/plans/`, `docs/reports/`, `docs/superpowers/`,
  `docs/backlog/` and git. Maintained docs do not cite these directories,
  except for the [History section of the index](index.md#history), a design
  doc's own plan while the design is unimplemented, and an experiment README's
  own result report. Leave historical records as they are.

## Writing Rules

Say what is current, in present tense: what the feature is, which targets and
forms run, the commands, inputs, outputs and user-visible errors. Link the spec
or design that owns the behavior and the runnable example or test a reader
would use.

State limits plainly, as facts about today: "native 3.0 runs are fresh-only:
no resume, retries or result reuse." Do not hedge a limit with process language.

Leave these out of maintained docs:

- status or authority boilerplate (`Status: informative`, `Normative
  authority: ...`, "this page does not select or authorize ...");
- commit, tree and SHA-256 identifiers; review tokens (`*_APPROVED`,
  `PASS_*`); pass/fail counts;
- task, phase, gate, stage and tranche labels, unless the label is a
  user-visible feature name;
- delivery narration ("now imported", "Task 7 removed", "the earlier
  comparison");
- qualification and selection framing ("branch-qualified", "candidate",
  "adoption", "selected", "frozen", "does not certify", "no default change").

Version identifiers such as 2.34, 2.35, 2.36 and 3.0 are real target names;
use them.

## Capability Labels

The capability matrix uses these labels:

- `Implemented`: runs, with spec and tests.
- `Partial`: runs for some routes or with stated limits.
- `Library`: provided by a library or frontend abstraction rather than a raw
  runtime primitive.
- `Designed`: a design exists; not usable yet.
- `Future`: intentionally deferred.
- `Retired`: removed; remaining references are history.
- `Legacy`: kept for compatibility; not for new authoring.

## References

Refer to mutable code and docs by path, symbol or section heading, not line
number. Before renaming or removing a heading, search maintained docs for links
to its anchor and update them.

## Examples

An example meant for copying runs from the repo root, uses no
maintainer-local absolute paths or unstated environment variables, names its
inputs, and says which target it uses. An example not meant for copying says
why (negative fixture, reference only, known failure).

## Views

Reports, markdown summaries, rendered debug output, stdout, prompt audits,
pointer files, dashboards and source maps are views. If a doc asks readers to
rely on one, it names the structured state, artifact or spec behind it.
