from dataclasses import dataclass
from typing import Mapping


@dataclass
class ValidationSubjectRef:
    """Generic validation subject identifier for structured provenance remapping."""

    subject_kind: str
    subject_name: str
    workflow_name: str | None = None


def serialize_validation_subject_ref(subject_ref: ValidationSubjectRef) -> dict[str, str]:
    """Serialize a workflow-qualified subject using the shared provenance wire shape."""

    workflow_name = subject_ref.workflow_name
    if not isinstance(workflow_name, str) or not workflow_name:
        raise ValueError("validation subject wire metadata requires a workflow name")

    return {
        "subject_kind": subject_ref.subject_kind,
        "subject_name": subject_ref.subject_name,
        "workflow_name": workflow_name,
    }


def parse_validation_subject_ref(value: object) -> ValidationSubjectRef | None:
    """Parse optional provenance metadata without raising or inferring identity."""

    if not isinstance(value, Mapping):
        return None
    subject_kind = value.get("subject_kind")
    subject_name = value.get("subject_name")
    workflow_name = value.get("workflow_name")
    if not all(
        isinstance(part, str) and part
        for part in (subject_kind, subject_name, workflow_name)
    ):
        return None
    return ValidationSubjectRef(
        subject_kind=subject_kind,
        subject_name=subject_name,
        workflow_name=workflow_name,
    )


@dataclass
class ValidationError:
    """Single validation error."""

    message: str
    path: str = ""
    exit_code: int = 2
    subject_refs: tuple[ValidationSubjectRef, ...] = ()


