"""Behavioral contract for the advisory YAML root-load deprecation event."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from orchestrator.exceptions import WorkflowValidationError
from orchestrator.loader import WorkflowLoader


_LOGGER_NAME = "orchestrator.loader.yaml_deprecation"
_EVENT_CODE = "workflow_yaml_authoring_deprecated"


def _write_valid_workflow(path: Path, *, name: str = "example") -> None:
    path.write_text(
        f'version: "2.14"\nname: {name}\nsteps:\n'
        "  - name: Done\n"
        "    command: [echo, done]\n",
        encoding="utf-8",
    )


def _deprecation_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == _LOGGER_NAME]


def _assert_yaml_event(record: logging.LogRecord, requested_path: Path) -> None:
    assert record.levelno == logging.WARNING
    assert record.workflow_deprecation_code == _EVENT_CODE
    assert record.workflow_deprecation_path == str(requested_path.resolve(strict=False))
    assert record.workflow_deprecation_format == "yaml"


@pytest.mark.parametrize("suffix", (".yaml", ".yml", ".YAML"))
def test_loader_emits_one_structured_event_for_yaml_root_suffixes(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    suffix: str,
) -> None:
    workflow_path = tmp_path / f"workflow{suffix}"
    _write_valid_workflow(workflow_path)

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        WorkflowLoader(tmp_path).load_bundle(workflow_path)

    records = _deprecation_records(caplog)
    assert len(records) == 1
    _assert_yaml_event(records[0], workflow_path)


def test_loader_load_delegates_without_double_emitting(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_path = tmp_path / "workflow.yaml"
    _write_valid_workflow(workflow_path)
    loader = WorkflowLoader(tmp_path)
    delegated_paths: list[Path] = []
    real_load_bundle = loader.load_bundle

    def capture_delegation(path: Path):
        delegated_paths.append(path)
        return real_load_bundle(path)

    monkeypatch.setattr(loader, "load_bundle", capture_delegation)

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        loader.load(workflow_path)

    assert delegated_paths == [workflow_path]
    records = _deprecation_records(caplog)
    assert len(records) == 1
    _assert_yaml_event(records[0], workflow_path)


def test_relative_yaml_request_emits_absolute_resolved_path(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_path = tmp_path / "workflow.yaml"
    _write_valid_workflow(workflow_path)
    monkeypatch.chdir(tmp_path)

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        bundle = WorkflowLoader(tmp_path).load_bundle(Path("workflow.yaml"))

    assert bundle.surface.name == "example"
    records = _deprecation_records(caplog)
    assert len(records) == 1
    _assert_yaml_event(records[0], workflow_path)


def test_recursive_yaml_imports_emit_only_for_the_requested_root(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    child_path = tmp_path / "child.yml"
    _write_valid_workflow(child_path, name="child")
    root_path = tmp_path / "root.yaml"
    root_path.write_text(
        'version: "2.14"\n'
        "name: root\n"
        "imports:\n"
        "  child: child.yml\n"
        "steps:\n"
        "  - name: Done\n"
        "    command: [echo, done]\n",
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        WorkflowLoader(tmp_path).load_bundle(root_path)

    records = _deprecation_records(caplog)
    assert len(records) == 1
    _assert_yaml_event(records[0], root_path)


def test_malformed_yaml_emits_before_structured_load_failure(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    workflow_path = tmp_path / "malformed.yaml"
    workflow_path.write_text("version: [\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        with pytest.raises(WorkflowValidationError) as exc_info:
            WorkflowLoader(tmp_path).load_bundle(workflow_path)

    records = _deprecation_records(caplog)
    assert len(records) == 1
    _assert_yaml_event(records[0], workflow_path)
    assert len(exc_info.value.errors) == 1
    assert exc_info.value.errors[0].message.startswith("Failed to load workflow:")


def test_explicit_suppression_emits_no_yaml_deprecation_event(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    workflow_path = tmp_path / "workflow.yaml"
    _write_valid_workflow(workflow_path)

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        WorkflowLoader(
            tmp_path,
            emit_yaml_deprecation_warning=False,
        ).load_bundle(workflow_path)

    assert _deprecation_records(caplog) == []


def test_non_yaml_suffix_emits_no_yaml_deprecation_event(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    workflow_path = tmp_path / "workflow.orc"
    _write_valid_workflow(workflow_path)

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        WorkflowLoader(tmp_path).load_bundle(workflow_path)

    assert _deprecation_records(caplog) == []


def test_two_explicit_root_loads_emit_two_events_without_instance_deduplication(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    workflow_path = tmp_path / "workflow.yaml"
    _write_valid_workflow(workflow_path)
    loader = WorkflowLoader(tmp_path)

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        first = loader.load_bundle(workflow_path)
        second = loader.load_bundle(workflow_path)

    records = _deprecation_records(caplog)
    assert len(records) == 2
    assert first == second
    for record in records:
        _assert_yaml_event(record, workflow_path)


def test_warning_policy_changes_neither_bundle_nor_validation_diagnostics(
    tmp_path: Path,
) -> None:
    valid_path = tmp_path / "valid.yaml"
    _write_valid_workflow(valid_path)
    invalid_path = tmp_path / "invalid.yaml"
    invalid_path.write_text(
        'version: "2.14"\nname: invalid\nsteps: not-a-list\n',
        encoding="utf-8",
    )

    enabled = WorkflowLoader(tmp_path)
    suppressed = WorkflowLoader(
        tmp_path,
        emit_yaml_deprecation_warning=False,
    )

    assert enabled.load_bundle(valid_path) == suppressed.load_bundle(valid_path)

    with pytest.raises(WorkflowValidationError) as enabled_error:
        enabled.load_bundle(invalid_path)
    with pytest.raises(WorkflowValidationError) as suppressed_error:
        suppressed.load_bundle(invalid_path)

    assert enabled_error.value.errors == suppressed_error.value.errors
