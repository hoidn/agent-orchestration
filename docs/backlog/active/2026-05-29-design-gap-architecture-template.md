# Backlog Item: Create A Design Gap Architecture Template

Status: active

## Context

`docs/templates/design_template.md` is a general system/spec design template.
It is too broad for bounded design-gap artifacts under
`docs/plans/**/design-gaps/**/implementation_architecture.md`.

The current `docs/templates/design_gap_implementation_architecture_template.md`
is intentionally only a pointer to a good existing example. That avoids
inventing a schema prematurely, but it does not yet provide a durable reusable
template.

## Goal

Create a concise design-gap architecture template, based on the best existing
gap architecture documents, that helps agents draft one bounded gap design
without drifting into system/spec redesign.

## Scope

- Review representative existing gap architecture docs.
- Identify the recurring sections that are genuinely useful.
- Draft a short template for `implementation_architecture.md` gap artifacts.
- Keep "gap design" and "implementation architecture" as the same artifact in
  the wording.
- Update relevant drafting prompts and docs indexes only as needed.

## Non-Goals

- Do not replace the general design template.
- Do not rewrite existing gap architecture docs.
- Do not impose a rigid schema on every small work item.
- Do not make the template longer than the existing good examples require.

## Acceptance Criteria

- The template is clearly distinct from `docs/templates/design_template.md`.
- The template is derived from existing good gap architecture examples.
- The template is short enough to be useful as a prompt asset.
- The Lisp design-gap architect prompts point to the correct template or
  example.
- Existing execution plans and architecture docs are not rewritten.

