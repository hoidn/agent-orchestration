"""Behavioral contract for the advisory YAML root-load deprecation event."""

from __future__ import annotations

import ast
import json
import logging
from pathlib import Path
import re

import pytest

from orchestrator.cli.main import main as cli_main
from orchestrator.exceptions import WorkflowValidationError
from orchestrator.loader import WorkflowLoader


_LOGGER_NAME = "orchestrator.loader.yaml_deprecation"
_EVENT_CODE = "workflow_yaml_authoring_deprecated"
_PURE_EXPR_LOOP_COUNTER = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "workflow_lisp"
    / "valid"
    / "pure_expr_loop_counter.orc"
)
_REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


def _read_repository_text(relative_path: str) -> str:
    return (_REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")


def _markdown_section(document: str, heading: str) -> str:
    lines = document.splitlines()
    start = lines.index(heading)
    heading_level = len(heading) - len(heading.lstrip("#"))
    end = len(lines)
    for index in range(start + 1, len(lines)):
        candidate = lines[index]
        if not candidate.startswith("#"):
            continue
        candidate_level = len(candidate) - len(candidate.lstrip("#"))
        if candidate_level <= heading_level:
            end = index
            break
    return "\n".join(lines[start:end])


def _markdown_table_rows(section: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if all(re.fullmatch(r":?-+:?", cell) for cell in cells):
            continue
        rows.append(cells)
    return rows


def _markdown_link_target(cell: str) -> str:
    match = re.search(r"\[[^]]+\]\(([^)]+)\)", cell)
    assert match is not None, cell
    return match.group(1).strip("<>")


def _markdown_metadata(section: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in section.splitlines():
        match = re.fullmatch(r"\*\*([^*]+):\*\*\s+(.+)", line)
        if match is not None:
            metadata[match.group(1)] = match.group(2)
    return metadata


def _route_registry_entry(path: str) -> dict[str, object]:
    registry = json.loads(
        _read_repository_text("docs/workflow_lisp_route_readiness_registry.json")
    )
    matches = [entry for entry in registry["surfaces"] if entry["path"] == path]
    assert len(matches) == 1
    return matches[0]


def _assert_registry_approved_orc(path: str) -> None:
    assert path.endswith(".orc")
    entry = _route_registry_entry(path)
    assert entry["copy_safety"] == "preferred_current_guidance"
    assert entry["route_label"] == "wcc_default"


def _repository_path_for_link(document_path: str, link_target: str) -> str:
    absolute_target = (
        _REPOSITORY_ROOT / Path(document_path).parent / link_target
    ).resolve(strict=False)
    return absolute_target.relative_to(_REPOSITORY_ROOT).as_posix()


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


def test_fresh_cli_yaml_dry_run_emits_one_structured_event_and_succeeds(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_path = tmp_path / "workflow.yaml"
    _write_valid_workflow(workflow_path)
    monkeypatch.chdir(tmp_path)

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        exit_code = cli_main(["run", str(workflow_path), "--dry-run"])

    assert exit_code == 0
    records = _deprecation_records(caplog)
    assert len(records) == 1
    _assert_yaml_event(records[0], workflow_path)


def test_fresh_cli_orc_dry_run_without_yaml_dependency_emits_no_event(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        exit_code = cli_main(
            [
                "run",
                str(_PURE_EXPR_LOOP_COUNTER),
                "--entry-workflow",
                "run-counter",
                "--dry-run",
            ]
        )

    assert exit_code == 0
    assert _deprecation_records(caplog) == []


def _canonical_import_bindings(tree: ast.AST) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                bindings[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                local_name = alias.asname or alias.name.split(".", 1)[0]
                bindings[local_name] = alias.name if alias.asname else local_name
    return bindings


def _canonical_expression_name(
    expression: ast.expr,
    bindings: dict[str, str],
) -> str | None:
    if isinstance(expression, ast.Name):
        return bindings.get(expression.id, expression.id)
    if isinstance(expression, ast.Attribute):
        owner = _canonical_expression_name(expression.value, bindings)
        return f"{owner}.{expression.attr}" if owner else None
    return None


def _constructor_calls(module_path: Path, canonical_name: str) -> list[ast.Call]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    bindings = _canonical_import_bindings(tree)
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _canonical_expression_name(node.func, bindings) == canonical_name
    ]


def _assert_explicit_warning_suppression(call: ast.Call) -> None:
    policy = next(
        (
            keyword.value
            for keyword in call.keywords
            if keyword.arg == "emit_yaml_deprecation_warning"
        ),
        None,
    )
    assert isinstance(policy, ast.Constant)
    assert policy.value is False


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


def test_persisted_consumer_constructors_explicitly_suppress_yaml_deprecation() -> None:
    repository_root = Path(__file__).resolve().parent.parent
    expectations = (
        (
            repository_root / "orchestrator/cli/commands/resume.py",
            "orchestrator.loader.WorkflowLoader",
            2,
        ),
        (
            repository_root / "orchestrator/cli/commands/resume.py",
            "orchestrator.workflow_lisp.build.FrontendBuildRequest",
            1,
        ),
        (
            repository_root / "orchestrator/cli/commands/report.py",
            "orchestrator.loader.WorkflowLoader",
            1,
        ),
        (
            repository_root / "orchestrator/dashboard/projection.py",
            "orchestrator.loader.WorkflowLoader",
            1,
        ),
    )

    for module_path, canonical_name, expected_count in expectations:
        calls = _constructor_calls(module_path, canonical_name)
        assert len(calls) == expected_count
        for call in calls:
            _assert_explicit_warning_suppression(call)


def test_persisted_constructor_guard_detects_alias_hidden_unsuppressed_call(
    tmp_path: Path,
) -> None:
    mutated_module = tmp_path / "persisted_consumer.py"
    mutated_module.write_text(
        "\n".join(
            (
                "from orchestrator.loader import WorkflowLoader",
                "from orchestrator.loader import WorkflowLoader as PersistedLoader",
                "import orchestrator.loader as loader_module",
                "WorkflowLoader(root, emit_yaml_deprecation_warning=False)",
                "loader_module.WorkflowLoader(root, emit_yaml_deprecation_warning=False)",
                "PersistedLoader(root)",
            )
        ),
        encoding="utf-8",
    )

    calls = _constructor_calls(
        mutated_module,
        "orchestrator.loader.WorkflowLoader",
    )

    assert len(calls) == 3
    with pytest.raises(AssertionError):
        for call in calls:
            _assert_explicit_warning_suppression(call)


def test_author_routing_documentation_hub_defaults_to_workflow_lisp() -> None:
    document = _read_repository_text("docs/index.md")
    fast_triage = _markdown_table_rows(
        _markdown_section(document, "## Fast Triage")
    )
    rows_by_need = {row[0]: row for row in fast_triage[1:]}

    assert _markdown_link_target(rows_by_need["Author new workflows"][1]) == (
        "lisp_workflow_drafting_guide.md"
    )
    assert _markdown_link_target(
        rows_by_need["Maintain existing YAML workflows"][1]
    ) == "workflow_drafting_guide.md"

    authoring_path = _markdown_section(document, "### When Authoring Workflows")
    first_link = re.search(r"\[[^]]+\]\(([^)]+)\)", authoring_path)
    assert first_link is not None
    assert first_link.group(1) == "lisp_workflow_drafting_guide.md"


def test_author_routing_yaml_guide_is_legacy_compatibility_not_new_author_start() -> None:
    document = _read_repository_text("docs/workflow_drafting_guide.md")
    preamble = document.split("\n## ", 1)[0]

    metadata = {
        key.strip(): value.strip()
        for line in preamble.splitlines()
        if ":" in line
        for key, value in [line.split(":", 1)]
    }
    assert metadata["Status"] == "legacy compatibility guide"
    assert _markdown_link_target(metadata["New-author start"]) == (
        "lisp_workflow_drafting_guide.md"
    )


@pytest.mark.parametrize(
    "heading",
    (
        "### Managed Provider Steps (v2.13)",
        "### Conservative Prompt Handling When Reusing Workflows",
        "### Adjudicated Provider Steps",
        "### Preparing A Workflow For `call`",
        "## 8) Compatibility-Edit Checklist",
    ),
)
def test_author_routing_deep_yaml_guide_sections_are_compatibility_scoped(
    heading: str,
) -> None:
    document = _read_repository_text("docs/workflow_drafting_guide.md")
    metadata = _markdown_metadata(_markdown_section(document, heading))

    assert metadata["Authoring scope"] == "`existing_yaml_compatibility`"
    assert _markdown_link_target(metadata["New-author route"]) == (
        "lisp_workflow_drafting_guide.md"
    )


@pytest.mark.parametrize(
    ("heading", "route_scope"),
    (
        (
            "### [Generic Run Watchdog YAML Compatibility Twin]"
            "(../workflows/examples/generic_run_watchdog.yaml)",
            "`existing_yaml_compatibility`",
        ),
        (
            "### [Managed Provider Jobs Demo]"
            "(../workflows/examples/managed_provider_jobs_demo.yaml)",
            "`existing_yaml_compatibility`",
        ),
        ("### [Workflow Examples Directory](../workflows/examples/)", "`reference_only`"),
        (
            "### [NeurIPS Hybrid ResNet Plan/Implementation Workflow]"
            "(../workflows/examples/neurips_hybrid_resnet_plan_impl_review.yaml)",
            "`existing_yaml_compatibility`",
        ),
    ),
)
def test_author_routing_docs_index_yaml_catalog_entries_are_not_copy_routes(
    heading: str,
    route_scope: str,
) -> None:
    document = _read_repository_text("docs/index.md")
    metadata = _markdown_metadata(_markdown_section(document, heading))

    assert metadata["Route scope"] == route_scope
    assert metadata["Copy role"] == "`not_new_author_template`"
    assert _markdown_link_target(metadata["New-author route"]) == (
        "lisp_workflow_drafting_guide.md"
    )


def test_author_routing_readme_and_catalog_select_registry_approved_orc() -> None:
    documents_and_headings = (
        ("README.md", "## Start Here"),
        ("workflows/README.md", "## Which Example Should I Copy?"),
    )

    for relative_path, heading in documents_and_headings:
        rows = _markdown_table_rows(
            _markdown_section(_read_repository_text(relative_path), heading)
        )
        rows_by_goal = {row[0]: row for row in rows[1:]}
        selected_path = _repository_path_for_link(
            relative_path,
            _markdown_link_target(rows_by_goal["Start new authoring"][1]),
        )
        _assert_registry_approved_orc(selected_path)


def test_verified_catalog_routes_new_launches_to_orc_and_retains_yaml_compatibility() -> None:
    document = _read_repository_text("workflows/README.md")
    rows = _markdown_table_rows(_markdown_section(document, "## Workflow Catalog"))
    rows_by_path = {row[0].strip("`"): row for row in rows[1:]}
    orc_path = "workflows/library/verified_iteration_drain/drain.orc"
    yaml_path = "workflows/examples/verified_iteration_drain.yaml"

    assert rows_by_path[orc_path][1] == "Workflow Lisp production primary; input-required"
    assert rows_by_path[yaml_path][1] == (
        "Compatibility/reference twin; retained until Task 6 deletion gate"
    )
    _assert_registry_approved_orc(orc_path)
    assert (_REPOSITORY_ROOT / yaml_path).is_file()

    launch = _markdown_section(document, "## Verified-Iteration Drain Launch")
    assert "python -m orchestrator run workflows/library/verified_iteration_drain/drain.orc" in launch
    assert "--entry-workflow verified_iteration_drain/drain::drain" in launch
    assert "verified_iteration_drain.providers.json" in launch
    assert "verified_iteration_drain.prompts.json" in launch
    assert "verified_iteration_drain.commands.json" in launch
    assert "python -m orchestrator run workflows/examples/verified_iteration_drain.yaml" not in launch


def test_watchdog_catalog_routes_new_launches_to_orc_and_retains_yaml_compatibility() -> None:
    document = _read_repository_text("workflows/README.md")
    rows = _markdown_table_rows(_markdown_section(document, "## Workflow Catalog"))
    rows_by_path = {row[0].strip("`"): row for row in rows[1:]}
    orc_path = "workflows/library/generic_run_watchdog/watchdog.orc"
    yaml_path = "workflows/examples/generic_run_watchdog.yaml"

    assert rows_by_path[orc_path][1] == "Workflow Lisp production primary; input-required"
    assert rows_by_path[yaml_path][1] == (
        "Compatibility/reference twin; retained until Task 6 deletion gate"
    )
    _assert_registry_approved_orc(orc_path)
    assert (_REPOSITORY_ROOT / yaml_path).is_file()

    launch = _markdown_section(document, "## Generic Run Watchdog Launch")
    assert "python -m orchestrator run workflows/library/generic_run_watchdog/watchdog.orc" in launch
    assert "--entry-workflow generic_run_watchdog/watchdog::watchdog" in launch
    assert "generic_run_watchdog.providers.json" in launch
    assert "generic_run_watchdog.prompts.json" in launch
    assert "generic_run_watchdog.commands.json" in launch
    assert "python -m orchestrator run workflows/examples/generic_run_watchdog.yaml" not in launch


def test_author_routing_templates_default_to_orc_and_inventory_yaml_only() -> None:
    document = _read_repository_text("workflows/templates/README.md")
    rows = _markdown_table_rows(_markdown_section(document, "## Template Routes"))
    rows_by_purpose = {row[0]: row for row in rows[1:]}

    new_author_path = _repository_path_for_link(
        "workflows/templates/README.md",
        _markdown_link_target(rows_by_purpose["New template"][1]),
    )
    _assert_registry_approved_orc(new_author_path)

    compatibility_path = _markdown_link_target(
        rows_by_purpose["Existing YAML inventory"][1]
    )
    assert compatibility_path == "autonomous_drain_with_work_instructions.v214.yaml"
    assert rows_by_purpose["Existing YAML inventory"][2] == "Compatibility only"
    assert (_REPOSITORY_ROOT / "workflows/templates" / compatibility_path).is_file()


def test_author_routing_new_author_routes_never_select_frozen_yaml_template() -> None:
    frozen_template = "autonomous_drain_with_work_instructions.v214.yaml"
    route_sections = (
        _markdown_section(_read_repository_text("README.md"), "## Start Here"),
        _markdown_section(_read_repository_text("docs/index.md"), "## Fast Triage"),
        _markdown_section(
            _read_repository_text("workflows/README.md"),
            "## Which Example Should I Copy?",
        ),
        _markdown_section(
            _read_repository_text("workflows/templates/README.md"),
            "## Template Routes",
        ),
    )

    selected_new_author_paths: list[str] = []
    for section in route_sections:
        for row in _markdown_table_rows(section)[1:]:
            if row[0] in {"Start new authoring", "Author new workflows", "New template"}:
                selected_new_author_paths.append(_markdown_link_target(row[1]))

    assert len(selected_new_author_paths) == 4
    assert selected_new_author_paths.count("lisp_workflow_drafting_guide.md") == 1
    assert sum(path.endswith(".orc") for path in selected_new_author_paths) == 3
    assert not any(path.endswith((".yaml", ".yml")) for path in selected_new_author_paths)
    assert frozen_template not in selected_new_author_paths


def test_author_routing_lisp_guide_records_gap_instead_of_creating_yaml() -> None:
    guide = _read_repository_text("docs/lisp_workflow_drafting_guide.md")
    availability_rule = _markdown_section(guide, "## 13. Standard High-Level Forms")

    rows = _markdown_table_rows(availability_rule)
    dispositions = {row[0]: row[1] for row in rows[1:]}
    assert dispositions == {
        "Existing migration": "`retain_existing_authority`",
        "New authoring": "`record_capability_gap`",
        "New YAML/YML workaround": "`prohibited`",
    }


def test_author_routing_normative_yaml_warning_contract_is_structured() -> None:
    contract = _markdown_section(
        _read_repository_text("specs/dsl.md"),
        "### YAML fresh-load deprecation advisory",
    )

    for contract_identifier in (
        "orchestrator.loader.yaml_deprecation",
        "workflow_yaml_authoring_deprecated",
        "workflow_deprecation_code",
        "workflow_deprecation_path",
        "workflow_deprecation_format",
        "Path(requested_path).resolve(strict=False)",
    ):
        assert contract_identifier in contract

    policy_rows = _markdown_table_rows(contract)
    policies_by_purpose = {row[0]: row[1] for row in policy_rows[1:]}
    assert "one" in policies_by_purpose["Explicit fresh YAML/YML root"]
    assert "before parsing" in policies_by_purpose["Explicit fresh YAML/YML root"]
    assert "suppress" in policies_by_purpose["Persisted compatibility read"]
    assert "advisory" in contract.lower()


def test_author_routing_capability_status_keeps_yaml_legacy() -> None:
    rows = _markdown_table_rows(
        _read_repository_text("docs/capability_status_matrix.md")
    )
    rows_by_surface = {row[0]: row for row in rows[1:] if len(row) == 7}

    assert rows_by_surface["YAML fresh-load deprecation surface"][1] == "Implemented"
    assert rows_by_surface["YAML DSL v2.x"][1] == "Legacy"
