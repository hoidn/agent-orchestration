"""Pure result-binding construction over retained prompt-attempt authority."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from orchestrator.workflow.prompt_dependency_evidence import (
    PublicationResult,
    canonical_record_bytes,
    evidence_relative_path,
)
from orchestrator.workflow.provider_attempts import ProviderAttemptScope


IDENTITY_V1 = "workflow_prompt_attempt_identity.v1"
IDENTITY_V2 = "workflow_prompt_attempt_identity.v2"
COMPILED_V1 = "compiled_prompt_fragment_identity.v1"
ATTEMPT_ORDINAL = 3


def _module():
    try:
        return importlib.import_module(
            "orchestrator.workflow.prompt_attempt_result_binding"
        )
    except ModuleNotFoundError:
        pytest.fail(
            "prompt-attempt result-binding module is absent during RED",
            pytrace=False,
        )


def _sha(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _scope(
    *,
    run_id: str | None = None,
) -> ProviderAttemptScope:
    from tests.test_prompt_dependency_evidence import (
        _scope as evidence_scope,
    )

    scope = evidence_scope()
    if run_id is None:
        return scope
    payload = scope.to_dict()
    payload["run_id"] = run_id
    return ProviderAttemptScope.from_dict(payload)


def _fixture() -> dict[str, Any]:
    from orchestrator.workflow.prompt_dependency_evidence import (
        build_fragment_success_evidence_v2,
    )
    from orchestrator.workflow.prompt_identity import (
        build_prompt_attempt_identity,
    )
    from tests.test_prompt_dependency_evidence import (
        _fragment_v1_record,
        _identity_roles,
    )

    scope = _scope()
    retained = _fragment_v1_record()
    record = build_fragment_success_evidence_v2(
        retained_v1=retained,
        prompt_attempt_identity=build_prompt_attempt_identity(
            roles=_identity_roles(
                identity_schema_version=COMPILED_V1,
                phased=False,
            ),
            final_prompt=b"Read these inputs.\n\nbase prompt",
        ),
        compiler_fragment_identity_schema_version=COMPILED_V1,
    )
    payload = canonical_record_bytes(
        record,
        compiler_fragment_identity_schema_version=COMPILED_V1,
    )
    relative_path = evidence_relative_path(scope, ATTEMPT_ORDINAL)
    publication = PublicationResult(
        relative_path=relative_path,
        file_sha256=_sha(payload),
        payload=payload,
        record_kind="prompt_snapshot",
    )
    allocations = {
        scope.key: {
            "scope": scope.to_dict(),
            "last_allocated_ordinal": ATTEMPT_ORDINAL,
            "prompt_fragment_identity_schema_version": COMPILED_V1,
        }
    }
    return {
        "scope": scope,
        "record": record,
        "payload": payload,
        "publication": publication,
        "allocations": allocations,
    }


def _attach_kwargs(fixture: dict[str, Any]) -> dict[str, Any]:
    return {
        "direct_fragment_call": True,
        "compiled_fragment_contract_present": True,
        "delivery": "composed",
        "prompt_attempt_identity_schema_version": IDENTITY_V1,
        "compiler_fragment_identity_schema_version": COMPILED_V1,
        "validated_result_ready_for_commit": True,
        "scope": fixture["scope"],
        "attempt_ordinal": ATTEMPT_ORDINAL,
        "root_provider_attempt_allocations": fixture["allocations"],
        "publication": fixture["publication"],
    }


def _assert_code(expected: str):
    return pytest.raises(
        _module().PromptAttemptResultBindingError,
        match=f"^{expected}:",
    )


def test_eligible_binding_is_closed_and_preserves_unrelated_debug() -> None:
    module = _module()
    fixture = _fixture()

    debug = module.attach_prompt_attempt_result_binding(
        {"provider_trace": {"attempts": 1}},
        **_attach_kwargs(fixture),
    )

    assert debug == {
        "provider_trace": {"attempts": 1},
        "prompt_attempt_result_binding": {
            "schema_version": (
                "workflow_prompt_attempt_result_binding.v1"
            ),
            "scope_sha256": fixture["scope"].key,
            "attempt_ordinal": ATTEMPT_ORDINAL,
            "evidence_relative_path": str(
                fixture["publication"].relative_path
            ),
            "evidence_file_sha256": fixture[
                "publication"
            ].file_sha256,
            "record_kind": "prompt_snapshot",
        },
    }
    assert module.validate_prompt_attempt_result_binding(
        debug["prompt_attempt_result_binding"]
    ) == debug["prompt_attempt_result_binding"]


@pytest.mark.parametrize(
    ("updates",),
    (
        ({"delivery": "phased"},),
        ({"prompt_attempt_identity_schema_version": IDENTITY_V2},),
        ({"direct_fragment_call": False},),
        ({"compiled_fragment_contract_present": False},),
        ({"validated_result_ready_for_commit": False},),
    ),
)
def test_structurally_ineligible_calls_short_circuit_before_publication(
    updates: dict[str, Any],
) -> None:
    module = _module()
    fixture = _fixture()
    kwargs = _attach_kwargs(fixture)
    kwargs.update(updates)
    kwargs["root_provider_attempt_allocations"] = object()
    kwargs["publication"] = object()

    original = {"provider_trace": {"attempts": 1}}
    assert module.attach_prompt_attempt_result_binding(
        original,
        **kwargs,
    ) == original


def test_unknown_evidence_schema_is_ineligible_before_allocator_validation() -> None:
    module = _module()
    fixture = _fixture()
    kwargs = _attach_kwargs(fixture)
    payload = b'{"schema":"workflow_prompt_fragment_snapshot.future"}'
    kwargs["publication"] = PublicationResult(
        relative_path=Path("not/validated/on/ineligible.json"),
        file_sha256=_sha(payload),
        payload=payload,
        record_kind="prompt_snapshot",
    )
    kwargs["root_provider_attempt_allocations"] = object()

    assert module.attach_prompt_attempt_result_binding(
        {"sibling": True},
        **kwargs,
    ) == {"sibling": True}


@pytest.mark.parametrize(
    "payload",
    (
        b"not-json",
        b'{"record_kind":"prompt_snapshot"}',
        b'{"schema":1}',
    ),
)
def test_malformed_evidence_schema_fails_before_allocator_validation(
    payload: bytes,
) -> None:
    module = _module()
    fixture = _fixture()
    kwargs = _attach_kwargs(fixture)
    kwargs["publication"] = PublicationResult(
        relative_path=Path("not/validated/on/malformed.json"),
        file_sha256=_sha(payload),
        payload=payload,
        record_kind="prompt_snapshot",
    )
    kwargs["root_provider_attempt_allocations"] = object()

    with _assert_code("judgment_result_evidence_invalid"):
        module.attach_prompt_attempt_result_binding(
            {"sibling": True},
            **kwargs,
        )


@pytest.mark.parametrize(
    "candidate",
    (
        None,
        {},
        {
            "schema_version": (
                "workflow_prompt_attempt_result_binding.v1"
            ),
            "scope_sha256": "sha256:" + "0" * 64,
            "attempt_ordinal": 1,
            "evidence_relative_path": "evidence.json",
            "evidence_file_sha256": "sha256:" + "1" * 64,
            "record_kind": "prompt_snapshot",
            "extra": None,
        },
        {
            "schema_version": (
                "workflow_prompt_attempt_result_binding.v1"
            ),
            "scope_sha256": "sha256:" + "0" * 64,
            "attempt_ordinal": True,
            "evidence_relative_path": "evidence.json",
            "evidence_file_sha256": "sha256:" + "1" * 64,
            "record_kind": "prompt_snapshot",
        },
        {
            "schema_version": (
                "workflow_prompt_attempt_result_binding.v1"
            ),
            "scope_sha256": "sha256:" + "0" * 64,
            "attempt_ordinal": 1,
            "evidence_relative_path": "../evidence.json",
            "evidence_file_sha256": "sha256:" + "1" * 64,
            "record_kind": "prompt_snapshot",
        },
    ),
)
def test_closed_locator_validator_rejects_invalid_shape(
    candidate: Any,
) -> None:
    with _assert_code("judgment_result_binding_invalid"):
        _module().validate_prompt_attempt_result_binding(candidate)


def test_missing_retained_publication_fails_closed() -> None:
    module = _module()
    fixture = _fixture()
    kwargs = _attach_kwargs(fixture)
    kwargs["publication"] = None

    with _assert_code("judgment_result_binding_missing"):
        module.attach_prompt_attempt_result_binding({}, **kwargs)


def test_existing_binding_refuses_a_second_locator() -> None:
    module = _module()
    fixture = _fixture()
    locator = {
        "schema_version": "workflow_prompt_attempt_result_binding.v1",
        "scope_sha256": fixture["scope"].key,
        "attempt_ordinal": ATTEMPT_ORDINAL,
        "evidence_relative_path": str(
            fixture["publication"].relative_path
        ),
        "evidence_file_sha256": fixture["publication"].file_sha256,
        "record_kind": "prompt_snapshot",
    }

    with _assert_code("judgment_result_binding_ambiguous"):
        module.attach_prompt_attempt_result_binding(
            {"prompt_attempt_result_binding": locator},
            **_attach_kwargs(fixture),
        )


def test_legacy_allocator_publication_events_remain_read_compatible() -> None:
    module = _module()
    fixture = _fixture()
    kwargs = _attach_kwargs(fixture)
    allocations = deepcopy(fixture["allocations"])
    allocations[fixture["scope"].key]["events"] = [
        {"ordinal": 1, "event": "allocated"},
        {"ordinal": 2, "event": "allocated"},
        {"ordinal": ATTEMPT_ORDINAL, "event": "allocated"},
        {
            "ordinal": ATTEMPT_ORDINAL,
            "event": "evidence_published",
            "relative_path": str(fixture["publication"].relative_path),
            "file_sha256": fixture["publication"].file_sha256,
            "record_kind": "prompt_snapshot",
        },
    ]
    kwargs["root_provider_attempt_allocations"] = allocations

    debug = module.attach_prompt_attempt_result_binding({}, **kwargs)

    assert debug["prompt_attempt_result_binding"]["attempt_ordinal"] == (
        ATTEMPT_ORDINAL
    )


def test_duplicate_legacy_publication_event_is_invalid_state() -> None:
    module = _module()
    fixture = _fixture()
    kwargs = _attach_kwargs(fixture)
    allocations = deepcopy(fixture["allocations"])
    publication_event = {
        "ordinal": ATTEMPT_ORDINAL,
        "event": "evidence_published",
        "relative_path": str(fixture["publication"].relative_path),
        "file_sha256": fixture["publication"].file_sha256,
        "record_kind": "prompt_snapshot",
    }
    allocations[fixture["scope"].key]["events"] = [
        {"ordinal": 1, "event": "allocated"},
        {"ordinal": 2, "event": "allocated"},
        {"ordinal": ATTEMPT_ORDINAL, "event": "allocated"},
        publication_event,
        deepcopy(publication_event),
    ]
    kwargs["root_provider_attempt_allocations"] = allocations

    with _assert_code("judgment_result_binding_invalid"):
        module.attach_prompt_attempt_result_binding({}, **kwargs)


def test_root_allocator_must_contain_the_exact_scope() -> None:
    module = _module()
    fixture = _fixture()
    other = _scope(run_id="20260729T000000Z-other")
    kwargs = _attach_kwargs(fixture)
    kwargs["root_provider_attempt_allocations"] = {
        other.key: {
            "scope": other.to_dict(),
            "last_allocated_ordinal": 1,
            "prompt_fragment_identity_schema_version": COMPILED_V1,
        }
    }

    with _assert_code("judgment_result_scope_mismatch"):
        module.attach_prompt_attempt_result_binding({}, **kwargs)


def test_publication_for_a_different_attempt_ordinal_fails_closed() -> None:
    module = _module()
    fixture = _fixture()
    kwargs = _attach_kwargs(fixture)
    allocations = deepcopy(fixture["allocations"])
    entry = allocations[fixture["scope"].key]
    entry["last_allocated_ordinal"] = ATTEMPT_ORDINAL + 1
    kwargs["root_provider_attempt_allocations"] = allocations
    kwargs["attempt_ordinal"] = ATTEMPT_ORDINAL + 1

    with _assert_code("judgment_result_evidence_invalid"):
        module.attach_prompt_attempt_result_binding({}, **kwargs)


@pytest.mark.parametrize(
    "mutation",
    (
        "digest",
        "path",
        "kind",
        "noncanonical",
        "identity_payload",
    ),
)
def test_publication_and_functional_v2_evidence_must_agree_exactly(
    mutation: str,
) -> None:
    from tests.test_prompt_identity import _record_seal

    module = _module()
    fixture = _fixture()
    kwargs = _attach_kwargs(fixture)
    publication = fixture["publication"]
    if mutation == "digest":
        publication = PublicationResult(
            relative_path=publication.relative_path,
            file_sha256="sha256:" + "f" * 64,
            payload=publication.payload,
            record_kind=publication.record_kind,
        )
    elif mutation == "path":
        publication = PublicationResult(
            relative_path=Path("different.json"),
            file_sha256=publication.file_sha256,
            payload=publication.payload,
            record_kind=publication.record_kind,
        )
    elif mutation == "kind":
        publication = PublicationResult(
            relative_path=publication.relative_path,
            file_sha256=publication.file_sha256,
            payload=publication.payload,
            record_kind="failure",
        )
    elif mutation == "noncanonical":
        payload = publication.payload + b"\n"
        publication = PublicationResult(
            relative_path=publication.relative_path,
            file_sha256=_sha(payload),
            payload=payload,
            record_kind=publication.record_kind,
        )
    else:
        record = deepcopy(fixture["record"])
        record["prompt_attempt_identity"]["schema_version"] = IDENTITY_V2
        _record_seal(record)
        payload = json.dumps(
            record,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        publication = PublicationResult(
            relative_path=publication.relative_path,
            file_sha256=_sha(payload),
            payload=payload,
            record_kind=publication.record_kind,
        )
    kwargs["publication"] = publication

    with _assert_code("judgment_result_evidence_invalid"):
        module.attach_prompt_attempt_result_binding({}, **kwargs)


def test_evidence_attempt_scope_must_match_retained_scope() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import _attempt
    from tests.test_prompt_dependency_evidence import _reseal

    module = _module()
    fixture = _fixture()
    other_scope = _scope(run_id="20260729T000000Z-evidence-other")
    record = deepcopy(fixture["record"])
    record["attempt"] = _attempt(other_scope, ATTEMPT_ORDINAL)
    record["run"]["run_id"] = other_scope.run_id
    record["run"]["workflow_file"] = (
        other_scope.resume_scope.root_workflow_file
    )
    _reseal(record)
    payload = canonical_record_bytes(
        record,
        compiler_fragment_identity_schema_version=COMPILED_V1,
    )
    publication = PublicationResult(
        relative_path=fixture["publication"].relative_path,
        file_sha256=_sha(payload),
        payload=payload,
        record_kind="prompt_snapshot",
    )
    kwargs = _attach_kwargs(fixture)
    kwargs["publication"] = publication

    with _assert_code("judgment_result_scope_mismatch"):
        module.attach_prompt_attempt_result_binding({}, **kwargs)
