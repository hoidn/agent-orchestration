# Workflow Templates

This directory retains non-running compatibility templates. New workflow
families start from a registry-approved Workflow Lisp `.orc` example and adapt
typed procedures and contracts; do not create another YAML/YML template here.

Existing active drains should remain stable unless a separate migration work
item intentionally moves them to a new structure. The retained YAML template
remains useful only when maintaining its existing compatibility shape.

## Template Routes

| Purpose | Starting point | Status |
| --- | --- | --- |
| New template | [Workflow Lisp review/revise example](../examples/review_revise_design_docs.orc) | Registry-approved current `.orc` guidance; adapt it only when its typed review/fix shape fits. |
| Existing YAML inventory | [`autonomous_drain_with_work_instructions.v214.yaml`](autonomous_drain_with_work_instructions.v214.yaml) | Compatibility only |

The compatibility-only YAML inventory entry is an autonomous-drain skeleton
that consumes separate work instructions in addition to specs, backlog/work
items, and run evidence. It is frozen migration inventory, not a new-author
route, and remains unchanged until its retirement queue is resolved.
