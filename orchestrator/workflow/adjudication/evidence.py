"""Evaluation packet construction for adjudicated-provider candidates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .models import EVALUATION_PACKET_SCHEMA, SECRET_DETECTION_POLICY, EvidencePacketError
from .utils import _hash_bytes, _jsonable, _resolve_json_pointer, _stable_hash, _workspace_file

def build_evaluation_packet(
    *,
    candidate_id: str,
    candidate_workspace: Path,
    rendered_prompt: str,
    expected_outputs: list[dict] | None,
    output_bundle: dict | None,
    artifacts: Mapping[str, Any],
    scorer: Mapping[str, Any],
    evidence_limits: Mapping[str, int] | None,
    workflow_secret_values: Sequence[str],
    rubric_content: str | None = None,
    consumed_artifacts: Mapping[str, Any] | None = None,
    consumed_relpath_targets: Mapping[str, str] | None = None,
    candidate_metadata: Mapping[str, Any] | None = None,
    prompt_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    limits = {
        "max_item_bytes": 262144,
        "max_packet_bytes": 1048576,
    }
    if isinstance(evidence_limits, Mapping):
        limits.update({key: int(value) for key, value in evidence_limits.items()})
    evidence_items: list[dict[str, Any]] = []
    _add_text_evidence(
        evidence_items,
        name="candidate_prompt",
        path=None,
        content=rendered_prompt,
        limits=limits,
        workflow_secret_values=workflow_secret_values,
    )
    if rubric_content is not None:
        _add_text_evidence(
            evidence_items,
            name="rubric",
            path=None,
            content=rubric_content,
            limits=limits,
            workflow_secret_values=workflow_secret_values,
        )

    normalized_consumes = {
        str(name): value
        for name, value in (consumed_artifacts or {}).items()
        if isinstance(name, str)
    }
    target_by_consume = {
        str(name): target
        for name, target in (consumed_relpath_targets or {}).items()
        if isinstance(name, str) and isinstance(target, str)
    }
    for name in sorted(normalized_consumes):
        value = normalized_consumes[name]
        _add_text_evidence(
            evidence_items,
            name=f"consume.{name}.value",
            path=None,
            content=str(value),
            limits=limits,
            workflow_secret_values=workflow_secret_values,
        )
        target_relpath = target_by_consume.get(name)
        if target_relpath is not None:
            _add_file_evidence(
                evidence_items,
                candidate_workspace=candidate_workspace,
                name=f"consume.{name}.target",
                relpath=target_relpath,
                limits=limits,
                workflow_secret_values=workflow_secret_values,
            )

    if output_bundle:
        bundle_path = _workspace_file(candidate_workspace, str(output_bundle.get("path", "")))
        bundle_text = _read_text_evidence(bundle_path)
        _add_text_evidence(
            evidence_items,
            name="output_bundle",
            path=str(output_bundle.get("path", "")),
            content=bundle_text,
            limits=limits,
            workflow_secret_values=workflow_secret_values,
        )
        bundle_doc = json.loads(bundle_text)
        for field_spec in output_bundle.get("fields", []):
            if (
                isinstance(field_spec, dict)
                and field_spec.get("type") == "relpath"
                and field_spec.get("must_exist_target")
            ):
                found, relpath_value = _resolve_json_pointer(bundle_doc, str(field_spec.get("json_pointer", "")))
                if found and isinstance(relpath_value, str):
                    _add_file_evidence(
                        evidence_items,
                        candidate_workspace=candidate_workspace,
                        name=f"{field_spec.get('name')}.target",
                        relpath=relpath_value,
                        limits=limits,
                        workflow_secret_values=workflow_secret_values,
                    )
    else:
        for spec in expected_outputs or []:
            if not isinstance(spec, dict):
                continue
            name = str(spec.get("name", "output"))
            output_path = str(spec.get("path", ""))
            value_text = _read_text_evidence(_workspace_file(candidate_workspace, output_path))
            _add_text_evidence(
                evidence_items,
                name=f"{name}.value_file",
                path=output_path,
                content=value_text,
                limits=limits,
                workflow_secret_values=workflow_secret_values,
            )
            if spec.get("type") == "relpath" and spec.get("must_exist_target"):
                _add_file_evidence(
                    evidence_items,
                    candidate_workspace=candidate_workspace,
                    name=f"{name}.target",
                    relpath=str(artifacts.get(name, value_text.strip())),
                    limits=limits,
                    workflow_secret_values=workflow_secret_values,
                )

    total_bytes = sum(int(item["byte_size"]) for item in evidence_items)
    if total_bytes > limits["max_packet_bytes"]:
        raise EvidencePacketError("evidence_packet_too_large", "evaluation packet exceeds max_packet_bytes")
    packet = {
        "packet_schema": EVALUATION_PACKET_SCHEMA,
        "candidate_id": candidate_id,
        "scorer_identity_hash": scorer.get("scorer_identity_hash"),
        "scorer": {
            "scorer_identity_hash": scorer.get("scorer_identity_hash"),
            "evaluator_provider": scorer.get("evaluator_provider"),
            "evaluator_model": scorer.get("evaluator_model"),
            "evaluator_params_hash": scorer.get("evaluator_params_hash"),
            "evaluator_config_hash": scorer.get("evaluator_config_hash"),
            "evaluator_prompt_source_kind": scorer.get("evaluator_prompt_source_kind"),
            "evaluator_prompt_source": scorer.get("evaluator_prompt_source"),
            "evaluator_prompt_hash": scorer.get("evaluator_prompt_hash"),
            "rubric_source_kind": scorer.get("rubric_source_kind"),
            "rubric_source": scorer.get("rubric_source"),
            "rubric_hash": scorer.get("rubric_hash"),
        },
        "candidate": {
            "candidate_id": candidate_id,
            **dict(candidate_metadata or {}),
        },
        "prompt": {
            "composed_prompt_hash": _hash_bytes(rendered_prompt.encode("utf-8")),
            **dict(prompt_metadata or {}),
        },
        "evidence_confidentiality": scorer.get("evidence_confidentiality") or "same_trust_boundary",
        "secret_detection_policy": SECRET_DETECTION_POLICY,
        "evidence_valid": True,
        "evidence_invalid_reasons": [],
        "artifacts": dict(artifacts),
        "consumed_artifacts": _jsonable(normalized_consumes),
        "evidence_items": evidence_items,
    }
    packet["evaluation_packet_hash"] = _stable_hash(packet)
    return packet

def _add_file_evidence(
    evidence_items: list[dict[str, Any]],
    *,
    candidate_workspace: Path,
    name: str,
    relpath: str,
    limits: Mapping[str, int],
    workflow_secret_values: Sequence[str],
) -> None:
    path = _workspace_file(candidate_workspace, relpath)
    _add_text_evidence(
        evidence_items,
        name=name,
        path=relpath,
        content=_read_text_evidence(path),
        limits=limits,
        workflow_secret_values=workflow_secret_values,
    )


def _add_text_evidence(
    evidence_items: list[dict[str, Any]],
    *,
    name: str,
    path: str | None,
    content: str,
    limits: Mapping[str, int],
    workflow_secret_values: Sequence[str],
) -> None:
    encoded = content.encode("utf-8")
    if len(encoded) > int(limits["max_item_bytes"]):
        raise EvidencePacketError("evidence_item_too_large", f"score-critical evidence item '{name}' exceeds max_item_bytes")
    for secret_value in workflow_secret_values:
        if isinstance(secret_value, str) and secret_value and secret_value in content:
            raise EvidencePacketError("secret_detected_in_score_evidence", "score-critical evidence contains a workflow-declared secret")
    evidence_items.append(
        {
            "name": name,
            "path": path,
            "byte_size": len(encoded),
            "sha256": _hash_bytes(encoded),
            "read_status": "embedded",
            "text_encoding": "utf-8",
            "content": content,
        }
    )


def _read_text_evidence(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise EvidencePacketError("non_utf8_score_evidence", f"score-critical evidence '{path}' is not UTF-8") from exc
    except OSError as exc:
        raise EvidencePacketError("score_evidence_read_failed", f"score-critical evidence '{path}' cannot be read") from exc


def _resolve_json_pointer(document: Any, pointer: str) -> tuple[bool, Any]:
    if pointer == "":
        return True, document
    if not pointer.startswith("/"):
        return False, None
    current = document
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
            continue
        if isinstance(current, list):
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
