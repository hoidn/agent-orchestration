# Workflow Templates

This directory contains non-running workflow templates for authoring new
workflow families. Templates describe structure and naming conventions; they are
not active examples and should not be launched directly without replacing
placeholder imports, scripts, prompts, and paths.

Use templates when changing workflow structure would otherwise mutate an
existing running workflow. Existing active drains should remain stable unless a
separate migration work item intentionally moves them to a new structure.

## Templates

- `autonomous_drain_with_work_instructions.v214.yaml`: skeleton for an
  autonomous drain that consumes separate work instructions in addition to specs,
  backlog/work items, and run evidence. The template keeps selector/gap/block and
  resume mechanics inside workflow-owned steps rather than in the work
  instructions document.
