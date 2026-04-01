# Workflow Authoring Skill Plan

## Goal

Create a personal skill for authoring workflows in the agent-orchestration DSL that:

- points agents to the right repo docs in the right order
- encodes the prompt/runtime/workflow boundary discipline from `docs/workflow_drafting_guide.md`
- helps convert ad hoc agent tasks into structured workflows
- avoids the prompt-leakage and orchestration-boundary mistakes that happened in this session
- stays concise enough to be worth loading

## Why this skill is needed

This session exposed repeated workflow-authoring failure modes:

- leaking workflow mechanics into prompts
- treating prompts as the easiest place to patch deterministic workflow behavior
- not explicitly following the drafting guide as a live checklist while writing prompts
- muddling workflow boundaries, runtime responsibilities, and provider-step responsibilities

Those are reusable authoring mistakes, not one-off bugs. They justify a skill.

## Scope

The skill should cover:

- initial doc-reading order for workflow work in this repo family
- the four workflow authoring surfaces:
  - workflow boundary
  - runtime dependencies
  - provider prompt sources
  - artifact storage/lineage
- deterministic vs non-deterministic split
- prompt-boundary rules
- minimal workflow verification expectations

The skill should not:

- restate the full DSL spec
- duplicate large sections of `workflow_drafting_guide.md`
- try to be a general workflow-language textbook

## Design

The skill will live at:

- `~/.agents/skills/workflow-authoring/SKILL.md`

It should be concise and operational:

- clear trigger conditions in frontmatter
- explicit required reading order:
  - `docs/index.md`
  - `docs/workflow_drafting_guide.md`
  - `specs/dsl.md`
  - `specs/variables.md`, `specs/dependencies.md`, `specs/providers.md`
  - `workflows/README.md` and examples
- a short checklist for:
  - decomposing deterministic vs non-deterministic work
  - keeping prompts task-local
  - choosing workflow artifacts, gates, and loop structure
  - verification steps

## Verification

Given the lack of a dedicated skill validator in this repo, verification will be lightweight:

- confirm the skill file exists in the discovery path
- confirm valid frontmatter shape (`name`, `description`)
- inspect word count and keep it reasonably lean
- manually confirm the skill includes the concrete failure modes from this session

## Deliverables

- `~/.agents/skills/workflow-authoring/SKILL.md`
- this plan doc
