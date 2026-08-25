"""Expected raw lookup filesystem failures stay inside the session domain."""

import pytest

from orchestrator.prompt_session import PromptSessionError, resolve_prompt_session


def test_runs_inventory_error_is_normalized(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from orchestrator import prompt_session_lookup

    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(
        prompt_session_lookup.os,
        "listdir",
        lambda _fd: (_ for _ in ()).throw(PermissionError("denied")),
    )
    with pytest.raises(PromptSessionError, match="prompt_session_not_found"):
        resolve_prompt_session(runs, "run-1")
