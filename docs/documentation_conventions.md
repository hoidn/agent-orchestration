# Documentation Conventions

Status: informative documentation hygiene guide
Normative authority: `specs/` for runtime behavior

Use this guide when adding or revising docs, plans, design docs, workflow
catalog entries, and authoring examples. The goal is to make each page clear
about authority, status, evidence, and copy safety.

## Required Front Matter In Prose

Near the top of new docs, answer these questions in plain text:

- What is this page for?
- Is it normative, current guidance, a target design, a plan, or historical
  context?
- Which spec, design, test, workflow, or run evidence owns the behavior?
- Is the page safe to copy from directly?
- If it describes future work, what should readers use today?

## Status Labels

Use these labels consistently:

- `Current contract`: behavior or guidance accepted for the current checkout.
- `Implemented`: available with runtime/test/spec evidence.
- `Partial`: available only for some routes or with clear limitations.
- `Library`: available as a library/frontend abstraction rather than a raw DSL
  primitive.
- `Designed`: design exists, but implementation is not complete enough for
  normal use.
- `Future`: intentionally deferred.
- `Legacy`: retained for compatibility or migration comparison, not preferred
  for new authoring.
- `Historical`: useful context, but not a current authority.

When status is uncertain, say so explicitly. Do not turn an aspirational design
into current guidance by omission.

## Authority Rules

- Runtime and DSL behavior: `specs/` wins.
- Current Workflow Lisp contracts: accepted component docs under `docs/design/`
  and current tests/examples provide the implementation-facing contract.
- Authoring guidance: `docs/workflow_drafting_guide.md` and
  `docs/lisp_workflow_drafting_guide.md`.
- Design routing: `docs/design/README.md`.
- Surface status: `docs/capability_status_matrix.md`.
- Historical orientation: `MIND_MAP.md`.

If two docs disagree, fix the lower-authority or stale doc rather than copying
the disagreement forward.

## Copy-Safe Examples

Examples intended for copying should:

- run from the repo root;
- avoid maintainer-local absolute paths;
- avoid unstated environment variables;
- name required inputs;
- say whether they are YAML, `.orc`, generated debug output, or test fixtures;
- say whether they are current, partial, legacy, negative, or migration-only.

Examples not intended for copying should say why. Common reasons include legacy
compatibility, negative fixtures, prompt asset issues, missing schema cleanup, or
future design sketches.

## Design Docs

Design docs should state:

- status and scope;
- what they own and what they consume from other docs;
- normative/spec impact;
- implementation evidence required before promotion;
- current fallback behavior if the design is not implemented;
- known open questions and non-goals.

Do not use a design doc to silently redefine normative runtime behavior. Add or
plan the corresponding spec update when behavior changes.

## Plans And Backlog Items

Plans and backlog items should distinguish:

- target architecture;
- implementation tasks;
- verification tasks;
- accepted temporary bridges;
- terminal blocker conditions;
- user-input conditions.

Avoid status labels that make recoverable implementation work look like a
terminal decision. In workflow-drained work, user input should be reserved for
major unresolvable ambiguity in intention or environment issues that require
user intervention.

## Reports And Views

Reports, markdown summaries, rendered debug YAML, stdout, prompt audits, pointer
files, dashboards, and source maps are views unless a contract says otherwise.
When a doc asks readers to trust one of those views, it should also identify the
structured state, artifact, bundle, or spec that backs it.
