"""The `declaration` input part of a provider-class effect: a provider, a phased provider or an agent turn.

The part digests the class's subject (`declaration_subject`): the site's checked node, or for an agent turn that node
seen as a provider node (`agent_turns.provider_view`). Every new row records `declaration_digest`: the subject as the
program digest's stripping leaves it, so no source position at any depth. Rows written before that rule record
`legacy_declaration_digest`, which kept the positions (absolute source path, line, column) of operand nodes.

Where a fresh input is compared with a recorded row (`replay_parts`; Edit and Continue §2), the fresh `declaration`
is computed by the rule the recorded value satisfies: the recorded value is used only when it equals the earlier rule
applied to the subject being compared. Nothing here writes a row or keys anything by the digest; identities do.

Depends on the closed-program strippings and canonical JSON digests; `written_subject` also reads the run's lineage
(`RunAuthority.program_at`) and that program's site nodes. Holds no state.
"""

from __future__ import annotations

from typing import Any, Mapping

from orchestrator.contracts.closed_program.program import strip_node_provenance, strip_provenance
from orchestrator.workflow.run_ref.contracts import canonical_sha256


def declaration_digest(subject: Mapping[str, Any]) -> str:
    """The part every new row records."""
    return canonical_sha256(strip_node_provenance(subject))


def legacy_declaration_digest(subject: Mapping[str, Any]) -> str:
    """The part of rows written before the position-free rule (kept verbatim; read, never written)."""
    return canonical_sha256(strip_provenance({"body": dict(subject)})["body"])


def declaration_for_replay(recorded: str, subject: Mapping[str, Any], written_subject) -> str:
    """The `declaration` to compare with `recorded`: the recorded value when it is the earlier rule's digest of
    `written_subject` (the subject in the program that wrote the row) and that subject has the new-rule digest of
    `subject`; otherwise the new rule's, so any real difference still diverges. `written_subject` may be a callable
    that returns it, called only when `recorded` differs from the new rule's digest."""
    current = declaration_digest(subject)
    if recorded == current:
        return current
    written = written_subject() if callable(written_subject) else written_subject
    if written is not None and recorded == legacy_declaration_digest(written) and declaration_digest(written) == current:
        return recorded
    return current


def declaration_subject(node: Mapping[str, Any], resolved: Any) -> Mapping[str, Any]:
    """An agent turn's subject is its provider view (`ResolvedTurn.provider_node`); other classes digest the node."""
    return resolved.provider_node if node["class"] == "agent_turn" else node


def written_subject(authority: Any, row: Any, node: Mapping[str, Any], resolved: Any):
    """A callable giving the subject of `row` (a journal entry) in the program that wrote it (Edit and Continue §2):
    the compared subject itself under the run's one program; else that program's site node at the row's identity,
    for an agent turn seen as a provider node through the same agent. None when that program has no such site."""
    subject = declaration_subject(node, resolved)
    program = authority.program_at(row.offset)
    if program is authority.program:
        return lambda: subject

    def lookup():
        from .agent_turns import provider_view
        from .machine import site_nodes
        from .memo_reducer import _DYNAMIC_INDEX
        nodes, identity = site_nodes(program), row.data["identity"]
        written = nodes.get(identity) or nodes.get(_DYNAMIC_INDEX.sub("[*]", identity))
        if written is None or written["class"] != node["class"]:
            return None
        return provider_view(written, resolved.agent) if node["class"] == "agent_turn" else written
    return lookup


def replay_parts(parts: Mapping[str, str], recorded_parts: Mapping[str, str], subject: Mapping[str, Any],
                 written=None) -> dict:
    """A copy of fresh `parts` for comparison with a recorded row's `recorded_parts`; neither mapping is changed (the
    recorded one belongs to a reduced memo row). `written` gives the subject in the program that wrote the row
    (`written_subject`); without it the row was written under the program being compared, so it is `subject`."""
    if "declaration" not in parts or "declaration" not in recorded_parts:
        return dict(parts)
    return {**parts, "declaration": declaration_for_replay(recorded_parts["declaration"], subject,
                                                           subject if written is None else written)}
