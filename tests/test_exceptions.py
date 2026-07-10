import pytest

from orchestrator.exceptions import (
    ValidationSubjectRef,
    parse_validation_subject_ref,
    serialize_validation_subject_ref,
)


def test_validation_subject_ref_round_trips_through_exact_wire_mapping() -> None:
    subject_ref = ValidationSubjectRef(
        subject_kind="variant_output_field",
        subject_name="execute::Decision::ACCEPTED::report",
        workflow_name="demo/module::entry",
    )

    serialized = serialize_validation_subject_ref(subject_ref)

    assert serialized == {
        "subject_kind": "variant_output_field",
        "subject_name": "execute::Decision::ACCEPTED::report",
        "workflow_name": "demo/module::entry",
    }
    assert parse_validation_subject_ref(serialized) == subject_ref


@pytest.mark.parametrize("workflow_name", [None, ""])
def test_serialize_validation_subject_ref_rejects_unqualified_workflow(
    workflow_name: str | None,
) -> None:
    subject_ref = ValidationSubjectRef(
        subject_kind="variant_output_field",
        subject_name="execute::Decision::ACCEPTED::report",
        workflow_name=workflow_name,
    )

    with pytest.raises(ValueError):
        serialize_validation_subject_ref(subject_ref)


@pytest.mark.parametrize(
    "value",
    [
        None,
        "variant_output_field",
        {},
        {
            "subject_kind": "variant_output_field",
            "subject_name": "execute::Decision::ACCEPTED::report",
        },
        {
            "subject_kind": "variant_output_field",
            "subject_name": "execute::Decision::ACCEPTED::report",
            "workflow_name": None,
        },
        {
            "subject_kind": "variant_output_field",
            "subject_name": 42,
            "workflow_name": "demo/module::entry",
        },
    ],
)
def test_parse_validation_subject_ref_returns_none_for_malformed_optional_metadata(
    value: object,
) -> None:
    assert parse_validation_subject_ref(value) is None
