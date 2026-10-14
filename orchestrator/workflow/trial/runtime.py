"""Historical trial outcome records and validation, without trial execution."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
from orchestrator.workflow.run_ref.ledger import SettledRunRefResultBinding
from .contracts import TrialCellKey

@dataclass(frozen=True, slots=True)
class TrialCellFailure:
    code: str
    phase: str
    retryable: bool
    secondary_causes: tuple[Any, ...] = ()

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value
            for value in (self.code, self.phase)
        ):
            raise ValueError("trial failure code and phase must be non-empty")
        if type(self.retryable) is not bool:
            raise TypeError("trial failure retryable flag must be boolean")
        if not isinstance(self.secondary_causes, tuple):
            raise TypeError("trial failure secondary causes must be a tuple")
        try:
            canonical_json_bytes(list(self.secondary_causes))
        except (TypeError, ValueError) as exc:
            raise ValueError("trial failure secondary causes are not JSON") from exc

    @property
    def record(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "phase": self.phase,
            "retryable": self.retryable,
            "secondary_causes": list(self.secondary_causes),
        }

@dataclass(frozen=True, slots=True)
class TrialCellOutcome:
    """Task-7 terminal cell authority, before Task-8 evidence/adjudication."""

    cell: TrialCellKey
    status: str
    envelope: Mapping[str, Any] | None
    artifacts: Mapping[str, Any] | None
    settled_result: SettledRunRefResultBinding | None
    committed_row_digest: str | None
    failure: TrialCellFailure | None
    e1_authority_row_digest: str | None

    def __post_init__(self) -> None:
        if type(self.cell) is not TrialCellKey:
            raise TypeError("trial outcome cell must be exact TrialCellKey")
        if self.status == "completed":
            if (
                not isinstance(self.envelope, Mapping)
                or not isinstance(self.artifacts, Mapping)
                or type(self.settled_result) is not SettledRunRefResultBinding
                or not isinstance(self.committed_row_digest, str)
                or self.failure is not None
                or self.e1_authority_row_digest != self.committed_row_digest
            ):
                raise ValueError("completed trial cell outcome is incomplete")
        elif self.status == "failed":
            if (
                self.envelope is not None
                or self.artifacts is not None
                or self.settled_result is not None
                or self.committed_row_digest is not None
                or type(self.failure) is not TrialCellFailure
            ):
                raise ValueError("failed trial cell outcome is invalid")
        else:
            raise ValueError("trial cell outcome status is invalid")
