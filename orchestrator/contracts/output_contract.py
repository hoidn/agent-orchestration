"""Runtime validation for step-level expected output artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class ContractViolation:
    """Single output contract violation."""
    type: str
    message: str
    context: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize violation for state/error payloads."""
        return {
            "type": self.type,
            "message": self.message,
            "context": self.context,
        }


class OutputContractError(Exception):
    """Raised when expected output artifact validation fails."""

    def __init__(self, violations: List[ContractViolation]):
        self.violations = [violation.to_dict() for violation in violations]
        messages = [f"{v.type}: {v.message}" for v in violations]
        super().__init__("; ".join(messages))


def validate_expected_outputs(expected_outputs: List[Dict[str, Any]], workspace: Path) -> Dict[str, Any]:
    """Validate expected output artifacts and return typed artifact values."""
    resolved_workspace = workspace.resolve()
    artifacts: Dict[str, Any] = {}
    violations: List[ContractViolation] = []
    seen_names: set[str] = set()

    for spec in expected_outputs:
        spec_path = str(spec.get("path", ""))
        output_file = _resolve_workspace_path(resolved_workspace, spec_path)
        artifact_name = str(spec.get("name", "")).strip()
        required = spec.get("required", True)

        if not artifact_name:
            violations.append(ContractViolation(
                type="missing_artifact_name",
                message="Expected output contract is missing required artifact name",
                context={"path": spec_path},
            ))
            continue
        if artifact_name in seen_names:
            violations.append(ContractViolation(
                type="duplicate_artifact_name",
                message="Expected output contract contains duplicate artifact names",
                context={"name": artifact_name, "path": spec_path},
            ))
            continue
        seen_names.add(artifact_name)

        if output_file is None:
            violations.append(ContractViolation(
                type="invalid_output_path",
                message="Output contract path escapes workspace",
                context={"path": spec_path},
            ))
            continue

        if not output_file.exists():
            if required:
                violations.append(ContractViolation(
                    type="missing_output_file",
                    message="Expected output file was not created",
                    context={"path": spec_path},
                ))
            continue

        raw_value = output_file.read_text(encoding="utf-8").strip()
        value_type = spec.get("type")
        parsed_value, violation = _parse_output_value(
            raw_value=raw_value,
            value_type=value_type,
            spec=spec,
            workspace=resolved_workspace,
        )
        if violation is not None:
            violation.context["path"] = spec_path
            violations.append(violation)
            continue

        artifacts[artifact_name] = parsed_value

    if violations:
        raise OutputContractError(violations)

    return artifacts


def validate_output_bundle(output_bundle: Dict[str, Any], workspace: Path) -> Dict[str, Any]:
    """Validate output_bundle JSON contract and return typed artifact values."""
    resolved_workspace = workspace.resolve()
    artifacts: Dict[str, Any] = {}
    violations: List[ContractViolation] = []
    seen_names: set[str] = set()

    bundle_path = str(output_bundle.get("path", ""))
    bundle_file = _resolve_workspace_path(resolved_workspace, bundle_path)
    if bundle_file is None:
        raise OutputContractError([
            ContractViolation(
                type="invalid_bundle_path",
                message="Output bundle path escapes workspace",
                context={"path": bundle_path},
            )
        ])

    if not bundle_file.exists():
        raise OutputContractError([
            ContractViolation(
                type="missing_bundle_file",
                message="Expected output bundle file was not created",
                context={"path": bundle_path},
            )
        ])

    try:
        document = json.loads(bundle_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError) as exc:
        raise OutputContractError([
            ContractViolation(
                type="invalid_json_document",
                message="Output bundle file is not valid JSON",
                context={"path": bundle_path, "error": str(exc)},
            )
        ])

    fields = output_bundle.get("fields")
    if not isinstance(fields, list):
        raise OutputContractError([
            ContractViolation(
                type="invalid_bundle_fields",
                message="Output bundle fields must be a list",
                context={"path": bundle_path},
            )
        ])

    for i, spec in enumerate(fields):
        if not isinstance(spec, dict):
            violations.append(ContractViolation(
                type="invalid_bundle_field",
                message="Output bundle field must be a dictionary",
                context={"path": bundle_path, "index": i},
            ))
            continue

        artifact_name = str(spec.get("name", "")).strip()
        if not artifact_name:
            violations.append(ContractViolation(
                type="missing_artifact_name",
                message="Output bundle field is missing required artifact name",
                context={"path": bundle_path, "index": i},
            ))
            continue
        if artifact_name in seen_names:
            violations.append(ContractViolation(
                type="duplicate_artifact_name",
                message="Output bundle contains duplicate artifact names",
                context={"path": bundle_path, "name": artifact_name},
            ))
            continue
        seen_names.add(artifact_name)

        json_pointer = spec.get("json_pointer")
        if not isinstance(json_pointer, str):
            violations.append(ContractViolation(
                type="invalid_json_pointer",
                message="Output bundle field requires string json_pointer",
                context={"path": bundle_path, "name": artifact_name},
            ))
            continue
        if json_pointer != "" and not json_pointer.startswith("/"):
            violations.append(ContractViolation(
                type="invalid_json_pointer",
                message="Output bundle json_pointer must be empty or start with '/'",
                context={"path": bundle_path, "name": artifact_name, "json_pointer": json_pointer},
            ))
            continue

        found, raw_value = _resolve_json_pointer(document, json_pointer)
        if not found:
            if spec.get("required", True) is False:
                continue
            violations.append(ContractViolation(
                type="json_pointer_not_found",
                message="Output bundle json_pointer did not resolve to a value",
                context={"path": bundle_path, "name": artifact_name, "json_pointer": json_pointer},
            ))
            continue

        value_type = spec.get("type")
        parsed_value, violation = _parse_output_bundle_value(
            raw_value=raw_value,
            value_type=value_type,
            spec=spec,
            workspace=resolved_workspace,
        )
        if violation is not None:
            violation.context["path"] = bundle_path
            violation.context["json_pointer"] = json_pointer
            violations.append(violation)
            continue

        artifacts[artifact_name] = parsed_value

    if violations:
        raise OutputContractError(violations)

    return artifacts


def _parse_output_value(
    raw_value: str,
    value_type: str,
    spec: Dict[str, Any],
    workspace: Path,
) -> tuple[Any, ContractViolation | None]:
    if value_type == "enum":
        allowed = spec.get("allowed", [])
        if raw_value not in allowed:
            return None, ContractViolation(
                type="invalid_enum_value",
                message="Output value is not in allowed enum set",
                context={"value": raw_value, "allowed": allowed},
            )
        return raw_value, None

    if value_type == "integer":
        try:
            return int(raw_value), None
        except ValueError:
            return None, ContractViolation(
                type="invalid_integer",
                message="Output value is not a valid integer",
                context={"value": raw_value},
            )

    if value_type == "float":
        try:
            return float(raw_value), None
        except ValueError:
            return None, ContractViolation(
                type="invalid_float",
                message="Output value is not a valid float",
                context={"value": raw_value},
            )

    if value_type == "bool":
        lowered = raw_value.lower()
        if lowered == "true":
            return True, None
        if lowered == "false":
            return False, None
        return None, ContractViolation(
            type="invalid_bool",
            message="Output value is not a valid boolean literal (expected true|false)",
            context={"value": raw_value, "allowed": ["true", "false"]},
        )

    if value_type == "relpath":
        return _validate_relpath_value(raw_value, spec, workspace)

    return None, ContractViolation(
        type="unsupported_type",
        message="Output contract type is not supported",
        context={"type": value_type},
    )


def _parse_output_bundle_value(
    raw_value: Any,
    value_type: str,
    spec: Dict[str, Any],
    workspace: Path,
) -> tuple[Any, ContractViolation | None]:
    if value_type == "enum":
        allowed = spec.get("allowed", [])
        if not isinstance(raw_value, str) or raw_value not in allowed:
            return None, ContractViolation(
                type="invalid_enum_value",
                message="Output value is not in allowed enum set",
                context={"value": raw_value, "allowed": allowed},
            )
        return raw_value, None

    if value_type == "integer":
        if type(raw_value) is int:
            return raw_value, None
        if isinstance(raw_value, str):
            try:
                return int(raw_value), None
            except ValueError:
                pass
        return None, ContractViolation(
            type="invalid_integer",
            message="Output value is not a valid integer",
            context={"value": raw_value},
        )

    if value_type == "float":
        if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
            return float(raw_value), None
        if isinstance(raw_value, str):
            try:
                return float(raw_value), None
            except ValueError:
                pass
        return None, ContractViolation(
            type="invalid_float",
            message="Output value is not a valid float",
            context={"value": raw_value},
        )

    if value_type == "bool":
        if isinstance(raw_value, bool):
            return raw_value, None
        if isinstance(raw_value, str):
            lowered = raw_value.lower()
            if lowered == "true":
                return True, None
            if lowered == "false":
                return False, None
        return None, ContractViolation(
            type="invalid_bool",
            message="Output value is not a valid boolean literal (expected true|false)",
            context={"value": raw_value, "allowed": ["true", "false"]},
        )

    if value_type == "relpath":
        if not isinstance(raw_value, str):
            return None, ContractViolation(
                type="invalid_relpath",
                message="Output value is not a valid relative path string",
                context={"value": raw_value},
            )
        return _validate_relpath_value(raw_value, spec, workspace)

    return None, ContractViolation(
        type="unsupported_type",
        message="Output contract type is not supported",
        context={"type": value_type},
    )


def _resolve_json_pointer(document: Any, pointer: str) -> tuple[bool, Any]:
    """Resolve RFC 6901-style JSON pointer against decoded document."""
    if pointer == "":
        return True, document

    if not pointer.startswith("/"):
        return False, None

    current = document
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                return False, None
            current = current[token]
            continue

        if isinstance(current, list):
            if token == "-":
                return False, None
            try:
                index = int(token)
            except ValueError:
                return False, None
            if index < 0 or index >= len(current):
                return False, None
            current = current[index]
            continue

        return False, None

    return True, current


def _validate_relpath_value(
    raw_value: str,
    spec: Dict[str, Any],
    workspace: Path,
) -> tuple[Any, ContractViolation | None]:
    if not raw_value:
        return None, ContractViolation(
            type="empty_relpath",
            message="relpath output value cannot be empty",
            context={},
        )

    value_path = Path(raw_value)
    if value_path.is_absolute() or ".." in value_path.parts:
        return None, ContractViolation(
            type="path_escape",
            message="relpath output escapes workspace",
            context={"value": raw_value},
        )

    target = _resolve_workspace_path(workspace, raw_value)
    if target is None:
        return None, ContractViolation(
            type="path_escape",
            message="relpath output escapes workspace",
            context={"value": raw_value},
        )

    under = spec.get("under")
    if under:
        under_root = _resolve_workspace_path(workspace, str(under))
        if under_root is None:
            return None, ContractViolation(
                type="invalid_under_root",
                message="under root escapes workspace",
                context={"under": under},
            )
        if not _is_within(target, under_root):
            normalized_target = _normalize_basename_under_root(
                raw_value=raw_value,
                workspace=workspace,
                under_root=under_root,
                must_exist_target=bool(spec.get("must_exist_target")),
            )
            if normalized_target is not None:
                target = normalized_target
            else:
                return None, ContractViolation(
                    type="outside_under_root",
                    message="relpath output points outside the declared under root",
                    context={"value": raw_value, "under": under},
                )
        if not _is_within(target, under_root):
            return None, ContractViolation(
                type="outside_under_root",
                message="relpath output points outside the declared under root",
                context={"value": raw_value, "under": under},
            )

    if spec.get("must_exist_target") and not target.exists():
        return None, ContractViolation(
            type="missing_target",
            message="relpath target does not exist",
            context={"value": raw_value},
        )

    return target.relative_to(workspace).as_posix(), None


def _normalize_basename_under_root(
    raw_value: str,
    workspace: Path,
    under_root: Path,
    must_exist_target: bool,
) -> Path | None:
    """Normalize bare filenames to under-root paths when contract under-root is present."""
    value_path = Path(raw_value)
    if len(value_path.parts) != 1:
        return None

    basename = value_path.parts[0]
    if basename in {"", ".", ".."}:
        return None

    candidate = (under_root / basename).resolve()
    if not _is_within(candidate, workspace):
        return None
    if not _is_within(candidate, under_root):
        return None
    if must_exist_target and not candidate.exists():
        return None
    return candidate


def _resolve_workspace_path(workspace: Path, relative_path: str) -> Path | None:
    """Resolve a workspace-relative path and reject escapes."""
    if not relative_path:
        return None
    path = Path(relative_path)
    if path.is_absolute():
        return None
    candidate = (workspace / path).resolve()
    if not _is_within(candidate, workspace):
        return None
    return candidate


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
