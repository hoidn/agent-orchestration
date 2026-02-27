"""Tests for built-in summary provider alias."""

from orchestrator.providers.registry import ProviderRegistry
from orchestrator.providers.types import InputMode


def test_summary_provider_alias_exists():
    registry = ProviderRegistry()
    provider = registry.get("claude_sonnet_summary")

    assert provider is not None


def test_summary_provider_alias_defaults_to_sonnet_4_6():
    registry = ProviderRegistry()
    provider = registry.get("claude_sonnet_summary")

    assert provider is not None
    assert provider.defaults.get("model") == "claude-sonnet-4-6"


def test_summary_provider_alias_uses_prompt_transport():
    registry = ProviderRegistry()
    provider = registry.get("claude_sonnet_summary")

    assert provider is not None
    assert provider.input_mode == InputMode.ARGV
    assert "${PROMPT}" in provider.command
