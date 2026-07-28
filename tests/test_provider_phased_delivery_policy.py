from __future__ import annotations

import pytest

from orchestrator.workflow.provider_phased_delivery.models import (
    PhasedRuntimePolicy,
    ProviderBoundPolicy,
    partition_provider_call_policy,
)


@pytest.mark.parametrize(
    ("policy", "provider_expected", "runtime_expected"),
    (
        ({}, ProviderBoundPolicy(), None),
        (
            {"model": "gpt-5.4", "effort": "high"},
            ProviderBoundPolicy(model="gpt-5.4", effort="high"),
            None,
        ),
        (
            {"delivery": "composed"},
            ProviderBoundPolicy(),
            PhasedRuntimePolicy(
                delivery="composed",
                materialization_attempts=None,
            ),
        ),
        (
            {
                "model": "gpt-5.4",
                "effort": "high",
                "delivery": "phased",
                "materialization_attempts": 2,
            },
            ProviderBoundPolicy(model="gpt-5.4", effort="high"),
            PhasedRuntimePolicy(
                delivery="phased",
                materialization_attempts=2,
            ),
        ),
    ),
)
def test_partition_provider_call_policy_has_exact_ownership(
    policy,
    provider_expected,
    runtime_expected,
) -> None:
    provider, runtime = partition_provider_call_policy(policy)

    assert provider == provider_expected
    assert runtime == runtime_expected


@pytest.mark.parametrize(
    "policy",
    (
        {"unknown": "value"},
        {"model": None},
        {"model": 7},
        {"effort": None},
        {"effort": False},
        {"delivery": 1},
        {"delivery": "unknown"},
        {"materialization_attempts": 2},
        {"delivery": "composed", "materialization_attempts": None},
        {"delivery": "composed", "materialization_attempts": 2},
        {"delivery": "phased"},
        {"delivery": "phased", "materialization_attempts": True},
        {"delivery": "phased", "materialization_attempts": 0},
        {"delivery": "phased", "materialization_attempts": 4},
    ),
)
def test_partition_provider_call_policy_rejects_closed_key_and_scalar_errors(
    policy,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        partition_provider_call_policy(policy)


def test_partition_copies_input_and_never_returns_authoring_mapping() -> None:
    policy = {
        "model": "gpt-5.4",
        "delivery": "phased",
        "materialization_attempts": 1,
    }

    provider, runtime = partition_provider_call_policy(policy)
    policy["model"] = "mutated"

    assert provider.model == "gpt-5.4"
    assert runtime == PhasedRuntimePolicy(
        delivery="phased",
        materialization_attempts=1,
    )
