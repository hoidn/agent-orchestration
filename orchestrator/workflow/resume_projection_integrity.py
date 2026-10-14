"""Read-only identity for historical nested run scopes."""

from dataclasses import dataclass

@dataclass(frozen=True)
class ResumeScopePath:
    """Immutable identity-only path from the root run to one audited scope."""

    root_workflow_file: str
    call_frame_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.root_workflow_file, str) or not self.root_workflow_file:
            raise ValueError("root_workflow_file must be a non-empty string")
        if not isinstance(self.call_frame_ids, (list, tuple)):
            raise ValueError("call_frame_ids must be a list or tuple")
        object.__setattr__(self, "call_frame_ids", tuple(self.call_frame_ids))
        if any(
            not isinstance(frame_id, str) or not frame_id
            for frame_id in self.call_frame_ids
        ):
            raise ValueError("call_frame_ids must contain non-empty strings")

    @classmethod
    def root(cls, workflow_file: str) -> "ResumeScopePath":
        """Construct the root scope path for one resumed run."""
        return cls(root_workflow_file=workflow_file)

    def child(self, frame_id: str) -> "ResumeScopePath":
        """Return an immutable child scope path for one reached call frame."""
        if not isinstance(frame_id, str) or not frame_id:
            raise ValueError("frame_id must be a non-empty string")
        return ResumeScopePath(
            root_workflow_file=self.root_workflow_file,
            call_frame_ids=(*self.call_frame_ids, frame_id),
        )

    @property
    def projection_scope(self) -> str:
        """Return the stable current projection kind for diagnostics."""
        return "call_frame" if self.call_frame_ids else "root"

    def as_context(self) -> list[dict[str, str]]:
        """Serialize only root and call-frame identities."""
        return [
            {
                "kind": "root",
                "workflow_file": self.root_workflow_file,
            },
            *(
                {
                    "kind": "call_frame",
                    "frame_id": frame_id,
                }
                for frame_id in self.call_frame_ids
            ),
        ]
