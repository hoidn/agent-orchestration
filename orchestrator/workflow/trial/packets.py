"""Closed treatment-blind evidence packets for target-2.25 trials."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping, Sequence
import json
from pathlib import PurePosixPath
import re
from typing import Any

from orchestrator.workflow.adjudication.models import EvaluatorOutputError
from orchestrator.workflow.adjudication.scoring import (
    parse_evaluator_output,
    scorer_contract_identity_hash,
)
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from orchestrator.workflow.run_ref.source import canonical_source_request

from .checks import TrialCheckResult
from .config import TrialRuntimeRequest
from .contracts import TrialCellKey, TrialOpaqueLabelBinding
from .runtime import TrialCellOutcome


TRIAL_EVALUATION_PACKET_SCHEMA = "trial.evaluation_packet.v1"
TRIAL_EVALUATOR_JSON_CONTRACT = "trial.evaluator_json.v1"

_OPAQUE_LABEL_RE = re.compile(r"opaque-[0-9a-f]{64}\Z")
_RUNTIME_STATE_PATH_BYTES_RE = re.compile(
    rb"(?:^|[^A-Za-z0-9_.-])\.orchestrate(?=/|[^A-Za-z0-9_.-]|$)"
)
_OBSERVATION_MEMBERS = frozenset(
    {
        "task_spec",
        "validated_result",
        "workspace_delta",
        "check_results",
        "declared_artifacts",
        "failure_evidence",
    }
)
_EXCLUDED_IDENTITY_KEYS = frozenset(
    {
        "arm_id",
        "base",
        "treatment",
        "treatment_id",
        "run_ref_source_locator",
        "source_locator",
        "normalized_locator",
        "resolved_commit_sha",
        "authored_setup_identity",
        "program_selector",
        "workflow_source",
        "workflow_source_text",
        "workflow_filename",
        "proposer_id",
        "proposer_lineage",
        "candidate_id",
        "candidate_lineage",
        "child_completion_order",
        "evaluator_completion_order",
        "completion_order",
        "run_log",
        "run_logs",
        "prior_score",
        "previous_score",
        "provider_identity",
        "provider_model",
        "evaluator_provider",
        "evaluator_model",
        "model_identity",
    }
)
_CHECK_OUTPUT_KEYS = frozenset(
    {
        "schema_version",
        "stdout_base64",
        "stderr_base64",
        "stdout_truncated",
        "stderr_truncated",
        "stdout_size_bytes",
        "stderr_size_bytes",
    }
)


class TrialPacketError(ValueError):
    """A stable fail-closed trial packet or citation refusal."""

    def __init__(self, code: str, rejected_value: object, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.rejected_value = rejected_value


def _fail(code: str, rejected_value: object, message: str) -> None:
    raise TrialPacketError(code, rejected_value, message)


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        _fail(
            "trial_packet_policy_invalid",
            value,
            "trial packet evidence must be canonical JSON",
        )
        raise AssertionError("unreachable") from exc


def _canonical_value(value: object) -> Any:
    return json.loads(_canonical_bytes(value).decode("utf-8"))


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, member in pairs:
        if key in value:
            raise ValueError(f"duplicate object key {key!r}")
        value[key] = member
    return value


def _reject_nonfinite_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value}")


def _excluded_identity_key(value: object) -> str | None:
    if isinstance(value, Mapping):
        for key, member in value.items():
            if key in _EXCLUDED_IDENTITY_KEYS:
                return str(key)
            nested = _excluded_identity_key(member)
            if nested is not None:
                return nested
    elif isinstance(value, list):
        for member in value:
            nested = _excluded_identity_key(member)
            if nested is not None:
                return nested
    return None


def _validate_evidence_paths(value: object) -> None:
    if isinstance(value, Mapping):
        for key, member in value.items():
            if key == "path":
                if not isinstance(member, str):
                    _fail(
                        "trial_packet_policy_invalid",
                        member,
                        "trial workspace evidence path must be text",
                    )
                path = PurePosixPath(member)
                if (
                    not member
                    or "\\" in member
                    or path.is_absolute()
                    or path.as_posix() != member
                    or any(part in {"", ".", ".."} for part in path.parts)
                    or ".orchestrate" in path.parts
                ):
                    _fail(
                        "trial_packet_policy_invalid",
                        member,
                        "trial workspace evidence path must be a normalized relpath",
                    )
            _validate_evidence_paths(member)
    elif isinstance(value, list):
        for member in value:
            _validate_evidence_paths(member)


def _contains_text(value: object, needle: str) -> bool:
    if isinstance(value, str):
        return needle in value
    if isinstance(value, Mapping):
        return any(
            needle in str(key) or _contains_text(member, needle)
            for key, member in value.items()
        )
    if isinstance(value, list):
        return any(_contains_text(member, needle) for member in value)
    return False


def _contains_runtime_state_path(value: object) -> bool:
    if isinstance(value, str):
        return ".orchestrate" in value.replace("\\", "/").split("/")
    if isinstance(value, Mapping):
        return any(
            _contains_runtime_state_path(str(key))
            or _contains_runtime_state_path(member)
            for key, member in value.items()
        )
    if isinstance(value, list):
        return any(_contains_runtime_state_path(member) for member in value)
    return False


def _mask_row_members(value: object, exempt: frozenset[str]) -> object:
    if not isinstance(value, Mapping):
        return value
    return {
        key: None if key in exempt else member
        for key, member in value.items()
    }


def _mask_row_list_members(value: object, exempt: frozenset[str]) -> object:
    if not isinstance(value, list):
        return value
    return [_mask_row_members(row, exempt) for row in value]


def _nonexempt_blinding_view(name: str, value: object) -> object:
    """Mask only the evaluator-visible evidence bytes exempted by the spec."""

    if name == "declared_artifacts":
        return _mask_row_list_members(value, frozenset({"path"}))
    if name != "workspace_delta" or not isinstance(value, Mapping):
        return value

    view = dict(value)
    for member in ("changed_files", "deleted_files", "untracked_files"):
        if member in view:
            view[member] = _mask_row_list_members(
                view[member],
                frozenset({"path"}),
            )
    normalized_diff = view.get("normalized_diff")
    if isinstance(normalized_diff, Mapping):
        masked_diff = dict(normalized_diff)
        if "entries" in masked_diff:
            masked_diff["entries"] = _mask_row_list_members(
                masked_diff["entries"],
                frozenset({"path", "text"}),
            )
        view["normalized_diff"] = masked_diff
    if "declared_artifacts" in view:
        view["declared_artifacts"] = _mask_row_list_members(
            view["declared_artifacts"],
            frozenset({"path"}),
        )
    return view


def _decode_check_output_bytes(value: object) -> tuple[bytes, bytes]:
    """Validate and decode one canonical bounded check-output document."""

    if not isinstance(value, str):
        _fail(
            "trial_packet_policy_invalid",
            value,
            "trial check output_bytes must be canonical JSON text",
        )
    try:
        output = json.loads(
            value,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_constant,
        )
    except (TypeError, ValueError) as exc:
        _fail(
            "trial_packet_policy_invalid",
            value,
            "trial check output_bytes must be canonical JSON text",
        )
        raise AssertionError("unreachable") from exc
    if (
        not isinstance(output, dict)
        or set(output) != _CHECK_OUTPUT_KEYS
        or output["schema_version"] != "trial_check_output.v1"
        or _canonical_bytes(output).decode("utf-8") != value
    ):
        _fail(
            "trial_packet_policy_invalid",
            value,
            "trial check output_bytes schema is invalid",
        )

    decoded: list[bytes] = []
    for stream in ("stdout", "stderr"):
        encoded = output[f"{stream}_base64"]
        if not isinstance(encoded, str):
            _fail(
                "trial_packet_policy_invalid",
                encoded,
                "trial check output_bytes base64 member is invalid",
            )
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            _fail(
                "trial_packet_policy_invalid",
                encoded,
                "trial check output_bytes base64 member is invalid",
            )
            raise AssertionError("unreachable") from exc
        if base64.b64encode(raw).decode("ascii") != encoded:
            _fail(
                "trial_packet_policy_invalid",
                encoded,
                "trial check output_bytes base64 member is noncanonical",
            )
        truncated = output[f"{stream}_truncated"]
        size = output[f"{stream}_size_bytes"]
        if (
            type(truncated) is not bool
            or type(size) is not int
            or size < len(raw)
            or truncated is not (size > len(raw))
        ):
            _fail(
                "trial_packet_policy_invalid",
                value,
                "trial check output_bytes bounds are invalid",
            )
        decoded.append(raw)
    return decoded[0], decoded[1]


def _decoded_check_result_streams(value: object) -> tuple[bytes, ...]:
    """Decode only the check-result output_bytes field, never generic base64."""

    if not isinstance(value, list):
        return ()
    streams: list[bytes] = []
    for result in value:
        if isinstance(result, Mapping) and "output_bytes" in result:
            streams.extend(_decode_check_output_bytes(result["output_bytes"]))
    return tuple(streams)


def _validate_nonexempt_blinding(
    *,
    name: str,
    value: object,
    sealed_identity_values: Sequence[str],
) -> None:
    visible = _nonexempt_blinding_view(name, value)
    for sealed in sealed_identity_values:
        if _contains_text(visible, sealed):
            _fail(
                "trial_blinding_policy_invalid",
                sealed,
                "sealed trial identity appears in evaluator-visible evidence",
            )
    if _contains_runtime_state_path(visible):
        _fail(
            "trial_blinding_policy_invalid",
            ".orchestrate",
            "orchestrator state path appears in evaluator-visible evidence",
        )
    if name != "check_results":
        return
    for stream in _decoded_check_result_streams(value):
        for sealed in sealed_identity_values:
            if sealed.encode("utf-8") in stream:
                _fail(
                    "trial_blinding_policy_invalid",
                    sealed,
                    "sealed trial identity appears in decoded check output",
                )
        if _RUNTIME_STATE_PATH_BYTES_RE.search(
            stream.replace(b"\\", b"/")
        ) is not None:
            _fail(
                "trial_blinding_policy_invalid",
                ".orchestrate",
                "orchestrator state path appears in decoded check output",
            )


def _production_identity_values(request: TrialRuntimeRequest) -> tuple[str, ...]:
    """Derive evaluator-hidden authored identities from frozen trial authority."""

    values: set[str] = {
        request.compiler_runtime_identity_digest,
        request.static_config_digest,
        request.trial_step_config_digest,
        request.static_config.evaluation["provider"],
    }
    for arm in request.step_config.arms:
        static = arm.run_ref.run_ref
        source = canonical_source_request(static.source)
        values.add(arm.arm_id)
        values.update(
            str(source[name])
            for name in (
                "normalized_locator",
                "resolved_commit_sha",
                "authored_setup_identity",
            )
        )
        values.add(static.digest)
        values.add(static.site_digest)
        values.update(
            value
            for name, value in static.program.record.items()
            if name != "mode" and isinstance(value, str) and value
        )
        if arm.run_ref.capsule_binding is not None:
            values.add(arm.run_ref.capsule_binding.capsule_digest)
    return tuple(sorted(values, key=lambda value: value.encode("utf-8")))


def _common_task_spec(request: TrialRuntimeRequest) -> dict[str, Any]:
    """Expose only exact common resolved inputs; asymmetric tasks fail closed."""

    inputs = request.resolved_inputs_by_arm
    ordered = [inputs[arm.arm_id] for arm in request.static_config.arms]
    if not ordered or any(
        _canonical_bytes(value) != _canonical_bytes(ordered[0])
        for value in ordered[1:]
    ):
        _fail(
            "trial_packet_policy_invalid",
            "resolved_inputs_by_arm",
            "trial task specification is not common across every arm",
        )
    return {"inputs": _canonical_value(ordered[0])}


def _utf8_prefix(text: str, maximum_bytes: int) -> tuple[str, int]:
    encoded = text.encode("utf-8")
    if len(encoded) <= maximum_bytes:
        return text, 0
    prefix = encoded[:maximum_bytes]
    while prefix:
        try:
            rendered = prefix.decode("utf-8", errors="strict")
            return rendered, len(encoded) - len(prefix)
        except UnicodeDecodeError as exc:
            prefix = prefix[: exc.start]
    return "", len(encoded)


def _bound_normalized_diff(value: object, *, diff_cap_bytes: int) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "entries",
        "catalog_digest",
        "truncated",
        "omitted_bytes",
        "omitted_entries",
    }:
        _fail(
            "trial_packet_policy_invalid",
            value,
            "trial WorkspaceDelta normalized diff is invalid",
        )
    normalized = _canonical_value(value)
    entries = normalized["entries"]
    if (
        not isinstance(entries, list)
        or type(normalized["truncated"]) is not bool
        or type(normalized["omitted_bytes"]) is not int
        or normalized["omitted_bytes"] < 0
        or type(normalized["omitted_entries"]) is not int
        or normalized["omitted_entries"] < 0
        or normalized["truncated"]
        is not (
            normalized["omitted_bytes"] > 0
            or normalized["omitted_entries"] > 0
        )
    ):
        _fail(
            "trial_packet_policy_invalid",
            value,
            "trial WorkspaceDelta normalized diff counters are invalid",
        )
    remaining = diff_cap_bytes
    projected: list[dict[str, Any]] = []
    added_omitted_bytes = 0
    added_omitted_entries = 0
    for entry in entries:
        if (
            not isinstance(entry, Mapping)
            or set(entry) != {"path", "text", "truncated", "omitted_bytes"}
            or not isinstance(entry["path"], str)
            or not isinstance(entry["text"], str)
            or type(entry["truncated"]) is not bool
            or type(entry["omitted_bytes"]) is not int
            or entry["omitted_bytes"] < 0
            or entry["truncated"] is not (entry["omitted_bytes"] > 0)
        ):
            _fail(
                "trial_packet_policy_invalid",
                entry,
                "trial WorkspaceDelta normalized diff entry is invalid",
            )
        rendered, newly_omitted = _utf8_prefix(entry["text"], remaining)
        remaining -= len(rendered.encode("utf-8"))
        added_omitted_bytes += newly_omitted
        if not rendered and entry["text"]:
            added_omitted_entries += 1
            continue
        projected.append(
            {
                "path": entry["path"],
                "text": rendered,
                "truncated": entry["truncated"] or newly_omitted > 0,
                "omitted_bytes": entry["omitted_bytes"] + newly_omitted,
            }
        )
    omitted_bytes = normalized["omitted_bytes"] + added_omitted_bytes
    omitted_entries = normalized["omitted_entries"] + added_omitted_entries
    return {
        "entries": projected,
        "catalog_digest": normalized["catalog_digest"],
        "truncated": omitted_bytes > 0 or omitted_entries > 0,
        "omitted_bytes": omitted_bytes,
        "omitted_entries": omitted_entries,
    }


def _project_workspace_delta(
    value: object,
    *,
    diff_cap_bytes: int,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "base",
        "changed_files",
        "deleted_files",
        "untracked_files",
        "normalized_diff",
        "declared_artifacts",
    }:
        _fail(
            "trial_packet_policy_invalid",
            value,
            "trial completed outcome has an invalid E1 WorkspaceDelta",
        )
    normalized = _canonical_value(value)
    projected = {
        name: normalized[name]
        for name in (
            "changed_files",
            "deleted_files",
            "untracked_files",
            "declared_artifacts",
        )
    }
    projected["normalized_diff"] = _bound_normalized_diff(
        normalized["normalized_diff"],
        diff_cap_bytes=diff_cap_bytes,
    )
    return {
        name: projected[name]
        for name in (
            "changed_files",
            "deleted_files",
            "untracked_files",
            "normalized_diff",
            "declared_artifacts",
        )
    }


def _trusted_check_records(
    request: TrialRuntimeRequest,
    outcome: TrialCellOutcome,
    results: tuple[TrialCheckResult, ...],
) -> list[dict[str, Any]]:
    if outcome.status == "failed":
        if results:
            _fail(
                "trial_packet_policy_invalid",
                len(results),
                "failed trial cells cannot carry post-completion checks",
            )
        return []
    authored = request.static_config.evaluation["checks"]
    expected = tuple(
        row
        for _index, row in sorted(
            enumerate(authored),
            key=lambda item: (
                0 if item[1]["authority"] == "correctness" else 1,
                item[0],
            ),
        )
    )
    if len(results) != len(expected):
        _fail(
            "trial_packet_policy_invalid",
            len(results),
            "trial packet check authority is incomplete",
        )
    freeze_digest: str | None = None
    records: list[dict[str, Any]] = []
    for result, check in zip(results, expected, strict=True):
        if (
            result.check_id != check["check_id"]
            or result.authority != check["authority"]
            or result.required is not check["required"]
            or result.check_spec_digest != canonical_sha256(check)
        ):
            _fail(
                "trial_packet_policy_invalid",
                result.check_id,
                "trial packet check result disagrees with frozen check authority",
            )
        if freeze_digest is None:
            freeze_digest = result.evidence_frozen_digest
        elif result.evidence_frozen_digest != freeze_digest:
            _fail(
                "trial_packet_policy_invalid",
                result.evidence_frozen_digest,
                "trial packet check results span different evidence freezes",
            )
        records.append(result.record)
    return records


def build_trial_evaluation_packet(
    *,
    opaque_label: str,
    observation_include: Sequence[str],
    observations: Mapping[str, Any],
    sealed_identity_values: Sequence[str],
    max_item_bytes: int,
    max_packet_bytes: int,
) -> dict[str, Any]:
    """Project selected observations into one closed, bounded opaque packet."""

    if not isinstance(opaque_label, str) or _OPAQUE_LABEL_RE.fullmatch(
        opaque_label
    ) is None:
        _fail(
            "trial_blinding_policy_invalid",
            opaque_label,
            "trial packet requires an exact opaque evaluation label",
        )
    if isinstance(observation_include, (str, bytes)) or not isinstance(
        observation_include, Sequence
    ):
        _fail(
            "trial_packet_policy_invalid",
            observation_include,
            "trial observation include must be a sequence",
        )
    include = tuple(observation_include)
    if (
        any(
            type(name) is not str or name not in _OBSERVATION_MEMBERS
            for name in include
        )
        or len(set(include)) != len(include)
    ):
        _fail(
            "trial_packet_policy_invalid",
            include,
            "trial observation include must use the unique closed vocabulary",
        )
    if not isinstance(observations, Mapping) or any(
        type(name) is not str for name in observations
    ):
        _fail(
            "trial_packet_policy_invalid",
            observations,
            "trial observations must be a string-keyed mapping",
        )
    if not set(observations).issubset(include):
        _fail(
            "trial_packet_policy_invalid",
            sorted(set(observations).difference(include)),
            "trial observations contain an unselected or unknown member",
        )
    if (
        isinstance(sealed_identity_values, (str, bytes))
        or not isinstance(sealed_identity_values, Sequence)
        or not sealed_identity_values
        or any(type(value) is not str or not value for value in sealed_identity_values)
    ):
        _fail(
            "trial_blinding_policy_invalid",
            sealed_identity_values,
            "trial packet requires the sealed non-empty identity values",
        )
    if (
        type(max_item_bytes) is not int
        or max_item_bytes < 1
        or type(max_packet_bytes) is not int
        or max_packet_bytes < max_item_bytes
    ):
        _fail(
            "trial_packet_limit_invalid",
            {
                "max_item_bytes": max_item_bytes,
                "max_packet_bytes": max_packet_bytes,
            },
            "trial packet byte limits are invalid",
        )

    items: list[dict[str, Any]] = []
    for name in include:
        if name not in observations:
            continue
        value = _canonical_value(observations[name])
        if name in {"workspace_delta", "declared_artifacts"}:
            _validate_evidence_paths(value)
        excluded_key = _excluded_identity_key(value)
        if excluded_key is not None:
            _fail(
                "trial_blinding_policy_invalid",
                excluded_key,
                "excluded identity metadata appears in evaluator-visible evidence",
            )
        _validate_nonexempt_blinding(
            name=name,
            value=value,
            sealed_identity_values=sealed_identity_values,
        )
        item = {"id": name, "kind": name, "value": value}
        if len(_canonical_bytes(item)) > max_item_bytes:
            _fail(
                "trial_packet_limit_invalid",
                name,
                f"trial packet item {name!r} exceeds max_item_bytes",
            )
        items.append(item)
    if not items:
        _fail(
            "trial_packet_citation_invalid",
            [],
            "trial evaluation packet must contain at least one citable item",
        )
    packet = {
        "schema": TRIAL_EVALUATION_PACKET_SCHEMA,
        "evaluation_id": opaque_label,
        "items": items,
        "citable_item_ids": [item["id"] for item in items],
    }
    packet_bytes = _canonical_bytes(packet)
    if len(packet_bytes) > max_packet_bytes:
        _fail(
            "trial_packet_limit_invalid",
            len(packet_bytes),
            "trial evaluation packet exceeds max_packet_bytes",
        )
    return packet


def build_trial_cell_evaluation_packet(
    request: TrialRuntimeRequest,
    outcome: TrialCellOutcome,
    *,
    opaque_label_binding: TrialOpaqueLabelBinding,
    trusted_check_results: tuple[TrialCheckResult, ...],
) -> dict[str, Any]:
    """Project one exact Task-7 outcome through the runtime-owned blind boundary."""

    if type(request) is not TrialRuntimeRequest:
        raise TypeError("trial packet request must be exact TrialRuntimeRequest")
    if type(outcome) is not TrialCellOutcome:
        raise TypeError("trial packet outcome must be exact TrialCellOutcome")
    if type(opaque_label_binding) is not TrialOpaqueLabelBinding:
        raise TypeError("trial packet label must be an exact header binding")
    if outcome.cell not in request.cell_domain:
        _fail(
            "trial_packet_policy_invalid",
            outcome.cell.record,
            "trial packet outcome is outside the request cell domain",
        )
    if opaque_label_binding.cell != outcome.cell:
        _fail(
            "trial_blinding_policy_invalid",
            opaque_label_binding.record,
            "trial packet opaque label does not bind the exact outcome cell",
        )
    if not isinstance(trusted_check_results, tuple) or any(
        type(result) is not TrialCheckResult for result in trusted_check_results
    ):
        raise TypeError("trusted trial check results must be an exact tuple")
    check_records = _trusted_check_records(
        request,
        outcome,
        trusted_check_results,
    )
    evaluation = request.static_config.evaluation
    observations: dict[str, Any] = {}
    if "task_spec" in evaluation["observation_include"]:
        observations["task_spec"] = _common_task_spec(request)
    if outcome.status == "completed":
        if outcome.envelope is None or set(outcome.envelope) != {
            "value",
            "workspace_delta",
            "accounting",
        }:
            _fail(
                "trial_packet_policy_invalid",
                outcome.envelope,
                "trial completed outcome envelope is invalid",
            )
        assert outcome.settled_result is not None
        if (
            canonical_sha256(outcome.envelope["workspace_delta"])
            != outcome.settled_result.workspace_delta_digest
            or canonical_sha256(outcome.envelope["accounting"])
            != outcome.settled_result.accounting_digest
        ):
            _fail(
                "trial_packet_policy_invalid",
                outcome.cell.record,
                "trial completed outcome disagrees with its exact E1 evidence binding",
            )
        workspace_delta = _project_workspace_delta(
            outcome.envelope["workspace_delta"],
            diff_cap_bytes=request.static_config.evaluation["diff_cap_bytes"],
        )
        observations.update(
            {
                "validated_result": outcome.envelope["value"],
                "workspace_delta": workspace_delta,
                "check_results": check_records,
                "declared_artifacts": workspace_delta["declared_artifacts"],
            }
        )
    else:
        if outcome.failure is None:
            _fail(
                "trial_packet_policy_invalid",
                outcome.status,
                "trial failed outcome has no explicit failure evidence",
            )
        observations["failure_evidence"] = outcome.failure.record
    selected = {
        name: observations[name]
        for name in evaluation["observation_include"]
        if name in observations
    }
    return build_trial_evaluation_packet(
        opaque_label=opaque_label_binding.opaque_label,
        observation_include=evaluation["observation_include"],
        observations=selected,
        sealed_identity_values=_production_identity_values(request),
        max_item_bytes=evaluation["max_item_bytes"],
        max_packet_bytes=evaluation["max_packet_bytes"],
    )


def trial_scorer_identity_hash(scorer: Mapping[str, Any]) -> str:
    """Bind a resolved scorer to the trial packet and output contracts."""

    return scorer_contract_identity_hash(
        scorer,
        evaluator_json_contract=TRIAL_EVALUATOR_JSON_CONTRACT,
        evaluation_packet_schema=TRIAL_EVALUATION_PACKET_SCHEMA,
    )


def validate_trial_evaluation_packet(packet: object) -> dict[str, Any]:
    """Validate the closed packet/item schema before evaluator delivery or use."""

    if not isinstance(packet, Mapping) or set(packet) != {
        "schema",
        "evaluation_id",
        "items",
        "citable_item_ids",
    }:
        _fail(
            "trial_packet_policy_invalid",
            packet,
            "trial evaluation packet has missing or extra fields",
        )
    normalized = _canonical_value(packet)
    if normalized["schema"] != TRIAL_EVALUATION_PACKET_SCHEMA:
        _fail(
            "trial_packet_policy_invalid",
            normalized["schema"],
            "trial evaluation packet schema is invalid",
        )
    label = normalized["evaluation_id"]
    if not isinstance(label, str) or _OPAQUE_LABEL_RE.fullmatch(label) is None:
        _fail(
            "trial_blinding_policy_invalid",
            label,
            "trial evaluation packet label is invalid",
        )
    items = normalized["items"]
    if not isinstance(items, list):
        _fail(
            "trial_packet_policy_invalid",
            items,
            "trial evaluation packet items must be a list",
        )
    if not items:
        _fail(
            "trial_packet_citation_invalid",
            items,
            "trial evaluation packet must contain at least one citable item",
        )
    item_ids: list[str] = []
    for item in items:
        if not isinstance(item, dict) or set(item) != {"id", "kind", "value"}:
            _fail(
                "trial_packet_policy_invalid",
                item,
                "trial evaluation packet item has missing or extra fields",
            )
        item_id = item["id"]
        if (
            not isinstance(item_id, str)
            or item_id not in _OBSERVATION_MEMBERS
            or item["kind"] != item_id
        ):
            _fail(
                "trial_packet_policy_invalid",
                item,
                "trial evaluation packet item identity is invalid",
            )
        item_ids.append(item_id)
    if len(set(item_ids)) != len(item_ids):
        _fail(
            "trial_packet_policy_invalid",
            item_ids,
            "trial evaluation packet item identities are duplicated",
        )
    if normalized["citable_item_ids"] != item_ids:
        _fail(
            "trial_packet_citation_invalid",
            normalized["citable_item_ids"],
            "trial packet citable identities disagree with its exact items",
        )
    return normalized


def validate_trial_cell_evaluation_packet(
    packet: object,
    *,
    request: TrialRuntimeRequest,
    cell: TrialCellKey,
    opaque_label_binding: TrialOpaqueLabelBinding,
) -> dict[str, Any]:
    """Recheck a packet against the exact frozen production authority."""

    if type(request) is not TrialRuntimeRequest:
        raise TypeError("trial packet request must be exact TrialRuntimeRequest")
    if type(cell) is not TrialCellKey or cell not in request.cell_domain:
        raise TypeError("trial packet cell must be in the exact request domain")
    if type(opaque_label_binding) is not TrialOpaqueLabelBinding:
        raise TypeError("trial packet label must be an exact header binding")
    if opaque_label_binding.cell != cell:
        _fail(
            "trial_blinding_policy_invalid",
            opaque_label_binding.record,
            "trial packet opaque label does not bind the exact requested cell",
        )
    normalized = validate_trial_evaluation_packet(packet)
    if normalized["evaluation_id"] != opaque_label_binding.opaque_label:
        _fail(
            "trial_blinding_policy_invalid",
            normalized["evaluation_id"],
            "trial packet label disagrees with the sealed header binding",
        )
    evaluation = request.static_config.evaluation
    item_ids = [item["id"] for item in normalized["items"]]
    expected_order = [
        name for name in evaluation["observation_include"] if name in item_ids
    ]
    if item_ids != expected_order:
        _fail(
            "trial_packet_policy_invalid",
            item_ids,
            "trial packet items disagree with configured observation order",
        )
    sealed = _production_identity_values(request)
    for item in normalized["items"]:
        name = item["id"]
        value = item["value"]
        excluded_key = _excluded_identity_key(value)
        if excluded_key is not None:
            _fail(
                "trial_blinding_policy_invalid",
                excluded_key,
                "excluded identity metadata appears in evaluator-visible evidence",
            )
        if name in {"workspace_delta", "declared_artifacts"}:
            _validate_evidence_paths(value)
        if name == "workspace_delta":
            if not isinstance(value, Mapping) or set(value) != {
                "changed_files",
                "deleted_files",
                "untracked_files",
                "normalized_diff",
                "declared_artifacts",
            }:
                _fail(
                    "trial_packet_policy_invalid",
                    value,
                    "trial packet WorkspaceDelta projection is invalid",
                )
            bounded = _bound_normalized_diff(
                value["normalized_diff"],
                diff_cap_bytes=evaluation["diff_cap_bytes"],
            )
            if _canonical_bytes(bounded) != _canonical_bytes(
                value["normalized_diff"]
            ):
                _fail(
                    "trial_packet_limit_invalid",
                    "workspace_delta.normalized_diff",
                    "trial packet normalized diff exceeds its configured cap",
                )
        _validate_nonexempt_blinding(
            name=name,
            value=value,
            sealed_identity_values=sealed,
        )
        if len(_canonical_bytes(item)) > evaluation["max_item_bytes"]:
            _fail(
                "trial_packet_limit_invalid",
                name,
                f"trial packet item {name!r} exceeds max_item_bytes",
            )
    if len(_canonical_bytes(normalized)) > evaluation["max_packet_bytes"]:
        _fail(
            "trial_packet_limit_invalid",
            len(_canonical_bytes(normalized)),
            "trial evaluation packet exceeds max_packet_bytes",
        )
    return normalized


def parse_trial_evaluator_output(
    stdout: bytes | str,
    *,
    packet: Mapping[str, Any],
) -> dict[str, Any]:
    """Parse one exact trial score object and resolve packet-local citations."""

    normalized_packet = validate_trial_evaluation_packet(packet)
    try:
        text = stdout.decode("utf-8", errors="strict") if isinstance(stdout, bytes) else stdout
        document = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_constant,
        )
    except (TypeError, UnicodeError, ValueError) as exc:
        raise EvaluatorOutputError(
            f"trial evaluator stdout must be strict JSON: {exc}"
        ) from exc
    if not isinstance(document, dict) or set(document) != {
        "candidate_id",
        "score",
        "summary",
        "citations",
    }:
        raise EvaluatorOutputError(
            "trial evaluator JSON must contain exactly candidate_id, score, summary, and citations"
        )
    parsed = parse_evaluator_output(
        text,
        expected_candidate_id=normalized_packet["evaluation_id"],
    )
    citations = document["citations"]
    if not isinstance(citations, list) or any(
        not isinstance(citation, str) for citation in citations
    ):
        raise EvaluatorOutputError("trial evaluator citations must be a string list")
    citable = set(normalized_packet["citable_item_ids"])
    if any(citation not in citable for citation in citations):
        _fail(
            "trial_packet_citation_invalid",
            citations,
            "every trial evaluator citation must resolve inside the exact packet",
        )
    return {**parsed, "citations": list(citations)}


__all__ = [
    "TRIAL_EVALUATION_PACKET_SCHEMA",
    "TRIAL_EVALUATOR_JSON_CONTRACT",
    "TrialPacketError",
    "build_trial_cell_evaluation_packet",
    "build_trial_evaluation_packet",
    "parse_trial_evaluator_output",
    "trial_scorer_identity_hash",
    "validate_trial_cell_evaluation_packet",
    "validate_trial_evaluation_packet",
]
