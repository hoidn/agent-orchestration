# Dashboard Summary Invocation Tabs

Status: draft implementation design

## Problem

The Summary Hub currently groups summary artifacts by authored step name. That
is useful for scanning the workflow shape, but it blurs repeated invocations of
the same step. A step such as `DraftPlan`, `ExecuteImplementation`, or
`ReviewDesignGapArchitecture` can run in multiple drain iterations or loop
iterations. The page may show several summary links, while input/output links
are resolved from whichever called-workflow state the structure renderer chose.

That makes the view ambiguous:

- a user cannot select invocation 1, 2, or 3 as a coherent unit;
- summaries can be multi-invocation while output links come from the most recent
  matching call frame;
- expected-output pointer files and target Markdown links are not visibly tied
  to the same invocation as the selected summary.

## Design

Render authored workflow steps with invocation-scoped summary panels.

For each workflow step card:

1. gather all matching summary entries for that logical step;
2. group them by invocation key:
   - `frame_root` when present;
   - otherwise `step_id`;
   - otherwise summary/snapshot/error path;
3. produce one invocation panel per key;
4. label panels with scoped context such as `drain iter 0`, `drain iter 1`, or
   `implementation_review_loop iter 3`;
5. default panels to collapsed, so the full workflow still fits on one page.

HTML should use native `<details>` / `<summary>` controls instead of custom
JavaScript tabs for the first pass. This gives the user a numbered selectable
view while preserving CSP simplicity and accessibility. The visual copy may call
these "Invocation 1", "Invocation 2", etc.

## Lineage-Scoped Selection

Invocation selection is not independent per visual row. When a user inspects
Invocation 2 of a child provider step, the enclosing call, repeat, or phase
context must also be understood as Invocation 2's lineage. Otherwise the page can
show a child summary from one call frame while showing parent links or state from
a different call frame.

For the first pass, native collapsed panels avoid explicit JavaScript state.
Each panel is self-contained: summaries, prompts, inputs, outputs, published
links, and consumed links are all resolved from that panel's invocation state.
If custom tab controls are added later, selecting an invocation in a nested step
must synchronize to the nearest matching invocation lineage in ancestor panels.

## Frame-Scoped Link Resolution

Each invocation panel must resolve links against that invocation's state:

- if the summary entry has a `frame_root`, locate the corresponding nested
  call-frame state;
- use that state for `${inputs.*}` substitution from `bound_inputs`;
- use that state's `steps` for expected-output artifacts and output-bundle
  fields;
- fall back to the current step detail only when no invocation state can be
  resolved.

This makes summary links and input/output links agree about which invocation
they describe.

## Path Rules

All links continue through dashboard safe file routes. The invocation resolver
must not expose absolute paths and must ignore missing, unsafe, or non-file
targets.

## Non-Goals

- Do not change workflow runtime state or summary generation.
- Do not add client-side tab JavaScript in this tranche.
- Do not make summary artifacts semantic authority.
- Do not scan arbitrary run files looking for Markdown. Only use authored
  workflow declarations and existing summary index entries.

## Acceptance Criteria

- Repeated summary entries for one step render as separate invocation panels.
- Each invocation panel contains that invocation's summary/error/snapshot links.
- Expected-output pointer and target links resolve using that invocation's
  `bound_inputs` and step state.
- The most recent invocation is not the only visible invocation.
- Existing path-safety tests still pass.
- Selecting or expanding an invocation never mixes that summary with links from a
  different invocation lineage.
