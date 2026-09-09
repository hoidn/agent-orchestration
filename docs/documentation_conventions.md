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
- `Planned`: roadmap position and a gated plan exist, but the governing design
  is not yet accepted and implementation must not begin.
- `Future`: intentionally deferred.
- `Retired`: removed from the live product or evidence surface; retained
  references are historical provenance.
- `Legacy`: retained for compatibility or migration comparison, not preferred
  for new authoring.
- `Historical`: useful context, but not a current authority.

When status is uncertain, say so explicitly. Do not turn an aspirational design
into current guidance by omission.

## Authority Rules

- Runtime and DSL behavior: `specs/` wins.
- Current Workflow Lisp contracts: accepted component docs under `docs/design/`
  and current tests/examples provide the implementation-facing contract.
- Runnable workflow authoring: `docs/lisp_workflow_drafting_guide.md`.
- Historical YAML/YML interpretation and translation:
  `docs/workflow_drafting_guide.md`; the retired frontend cannot execute it.
- Design routing: `docs/design/README.md`.
- Surface status: `docs/capability_status_matrix.md`.
- Historical orientation: `MIND_MAP.md`.

If two docs disagree, fix the lower-authority or stale doc rather than copying
the disagreement forward.

Indexes, catalogs, maps, and README hubs own discoverability: links, reading
paths, status, and evidence routing. They do not redefine the behavior or policy
owned by the linked spec, design, plan, or artifact contract.

## Durable References

Reference mutable source and documentation by path, symbol, or section. Use
exact line numbers only for immutable evidence artifacts or when the line itself
is the claim under review.

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
