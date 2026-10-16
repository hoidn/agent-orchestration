from __future__ import annotations


import pytest

from orchestrator.workflow.run_ref import path_contracts as path_contracts_module
from orchestrator.workflow.run_ref.config import (
    PathProgram,
    ReferenceBinding,
    RunRefInput,
)


_NESTED_TRANSPORT_BOUNDARIES = (
    (
        "List[Measurement]",
        ("(defrecord Measurement (score Float))",),
        {
            "kind": "list",
            "item": {
                "kind": "record",
                "name": "Measurement",
                "fields": [
                    {
                        "name": "score",
                        "type": {"kind": "primitive", "name": "Float"},
                    }
                ],
            },
        },
    ),
    (
        "List[Outcome]",
        ("(defunion Outcome (SCORED (score Float)) (SKIPPED))",),
        {
            "kind": "list",
            "item": {
                "kind": "union",
                "name": "Outcome",
                "variants": [
                    {
                        "name": "SCORED",
                        "fields": [
                            {
                                "name": "score",
                                "type": {"kind": "primitive", "name": "Float"},
                            }
                        ],
                    },
                    {"name": "SKIPPED", "fields": []},
                ],
            },
        },
    ),
)


@pytest.mark.parametrize(
    "descriptor",
    (
        {
            "kind": "union",
            "name": "Choice",
            "variants": [
                {
                    "name": "KEEP",
                    "fields": [
                        {
                            "name": "value",
                            "type": {"kind": "primitive", "name": "String"},
                        }
                    ],
                },
                {"name": "DROP", "fields": []},
            ],
        },
        {
            "kind": "optional",
            "item": {"kind": "primitive", "name": "String"},
        },
        {
            "kind": "map",
            "key": {"kind": "primitive", "name": "String"},
            "value": {"kind": "primitive", "name": "Int"},
        },
    ),
)
def test_exact_union_optional_and_map_signature_descriptors_are_admissible(
    descriptor: dict[str, object],
) -> None:
    configured_input = RunRefInput(
        name="payload",
        type_descriptor=descriptor,
        binding=ReferenceBinding("inputs.payload"),
    )
    signature = {
        "inputs": [{"name": "payload", "required": True, "type": descriptor}],
        "return": descriptor,
    }

    assert path_contracts_module._signature_mismatch_causes(
        signature,
        (configured_input,),
        PathProgram(
            path="candidate.orc",
            entry_name="run",
            return_refinement=descriptor,
        ),
    ) == ()


@pytest.mark.parametrize(
    "descriptor",
    tuple(row[2] for row in _NESTED_TRANSPORT_BOUNDARIES),
    ids=("list-record", "list-union"),
)
def test_nested_structural_signature_accepts_current_nested_boundaries(
    descriptor: dict[str, object],
) -> None:
    configured_input = RunRefInput(
        name="payload",
        type_descriptor=descriptor,
        binding=ReferenceBinding("inputs.payload"),
        allow_nested_structures=True,
    )
    signature = {
        "inputs": [{"name": "payload", "required": True, "type": descriptor}],
        "return": descriptor,
    }
    program = PathProgram(
        path="candidate.orc",
        entry_name="run",
        return_refinement=descriptor,
        allow_nested_structures=True,
    )

    assert path_contracts_module._signature_mismatch_causes(
        signature,
        (configured_input,),
        program,
    ) == ()
