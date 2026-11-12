from pathlib import Path

import pytest



def test_public_run_reports_provider_peer_member_count_and_bounds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from tests.test_workflow_lisp_improve_stdlib import _public_run, _public_run_files

    entry = tmp_path / "grt" / "entry.orc"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
                "  (defmodule grt/entry)",
                "  (export run)",
                "  (defworkflow run () -> String",
                "    (with-live-provider-peers ((member_0 \"value\")) member_0)))",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    result = _public_run(_public_run_files(tmp_path, {}))

    assert result.exit_code == 2
    assert "with_live_provider_peers_bindings_invalid" in caplog.text
    assert "value=1" in caplog.text
    assert "minimum=2" in caplog.text
    assert "maximum=8" in caplog.text
