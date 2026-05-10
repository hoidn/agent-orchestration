# Workflow Lisp Legacy Adapter

Status: draft internal design  
Depends on: `docs/design/workflow_language_design_principles.md`

## Purpose

`LegacyAdapter` is the quarantine boundary for old scripts, pointer
conventions, markdown parsers, command protocols, and report-derived semantic
fields that cannot be removed immediately.

Legacy adapters exist to preserve migration paths without letting compatibility
debt become new language semantics.

## Allowed Uses

Legacy adapters may bridge:

- markdown line-prefix extraction
- old pointer-file conventions
- command scripts that emit legacy JSON
- queue movement scripts pending a resource-transition backend
- historical workflow state layouts

## Required Metadata

Every adapter declares:

```text
name
legacy_reason
owner module
input contracts
output contracts
fixtures
deprecation status
replacement path
source-map behavior
```

## Validation Responsibilities

Adapter validation checks:

- adapter is explicitly marked legacy
- required fixtures exist
- extracted fields have typed contracts
- adapter outputs validate before publication
- adapter effects are recorded in the effect graph
- adapter cannot be imported by new standard-library modules unless explicitly
  allowed

## Required Invariants

- Legacy adapters are not semantic authority. They are migration boundaries.
- New high-level forms must not parse markdown reports directly.
- A legacy adapter that extracts semantic fields from prose must be fixture
  tested.
- Adapter output, not source prose, becomes the structured semantic value.

## Open Questions

- Whether legacy adapters live in a separate module namespace such as
  `legacy/*`.
- Whether lints warn or error when non-legacy modules depend on legacy
  adapters.
- How to track adapter deprecation in roadmap/backlog state.
