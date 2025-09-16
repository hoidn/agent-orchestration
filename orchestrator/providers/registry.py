"""
Provider registry for managing provider templates.

Implements provider template storage, lookup, and parameter merging per specs/providers.md.
"""

import logging
from typing import Dict, List, Optional
from pathlib import Path

from .types import ProviderTemplate, InputMode


logger = logging.getLogger(__name__)


class ProviderRegistry:
    """
    Registry for provider templates.

    Manages provider templates from workflow definitions and provides
    lookup and validation capabilities.
    """

    def __init__(self):
        """Initialize empty provider registry."""
        self._providers: Dict[str, ProviderTemplate] = {}
        self._builtin_providers = self._load_builtin_providers()

    def _load_builtin_providers(self) -> Dict[str, ProviderTemplate]:
        """
        Load built-in provider templates.

        Returns:
            Dictionary of built-in provider templates
        """
        return {
            "claude": ProviderTemplate(
                name="claude",
                command=["claude", "-p", "${PROMPT}", "--model", "${model}"],
                defaults={"model": "claude-sonnet-4-20250514"},
                input_mode=InputMode.ARGV
            ),
            "gemini": ProviderTemplate(
                name="gemini",
                command=["gemini", "-p", "${PROMPT}"],
                defaults={},
                input_mode=InputMode.ARGV
            ),
            "codex": ProviderTemplate(
                name="codex",
                command=["codex", "exec", "--model", "${model}",
                        "--dangerously-bypass-approvals-and-sandbox"],
                defaults={"model": "gpt-5"},
                input_mode=InputMode.STDIN
            )
        }

    def register(self, provider: ProviderTemplate) -> None:
        """
        Register a provider template.

        Args:
            provider: Provider template to register

        Raises:
            ValueError: If provider is invalid
        """
        errors = provider.validate()
        if errors:
            raise ValueError(f"Invalid provider template: {'; '.join(errors)}")

        self._providers[provider.name] = provider
        logger.debug(f"Registered provider: {provider.name}")

    def register_from_workflow(self, providers_config: Dict[str, Dict]) -> List[str]:
        """
        Register providers from workflow configuration.

        Args:
            providers_config: Provider definitions from workflow YAML

        Returns:
            List of validation errors (empty if all valid)
        """
        errors = []

        for name, config in providers_config.items():
            try:
                # Parse input mode
                input_mode = InputMode(config.get("input_mode", "argv"))

                provider = ProviderTemplate(
                    name=name,
                    command=config.get("command", []),
                    defaults=config.get("defaults", {}),
                    input_mode=input_mode
                )

                # Validate before registering
                validation_errors = provider.validate()
                if validation_errors:
                    errors.extend(validation_errors)
                else:
                    self.register(provider)

            except Exception as e:
                errors.append(f"Error registering provider '{name}': {e}")

        return errors

    def get(self, name: str) -> Optional[ProviderTemplate]:
        """
        Get a provider template by name.

        Args:
            name: Provider name

        Returns:
            Provider template or None if not found
        """
        # Check workflow providers first, then built-in
        return self._providers.get(name) or self._builtin_providers.get(name)

    def exists(self, name: str) -> bool:
        """
        Check if a provider is registered.

        Args:
            name: Provider name

        Returns:
            True if provider exists
        """
        return name in self._providers or name in self._builtin_providers

    def list_providers(self) -> List[str]:
        """
        List all registered provider names.

        Returns:
            List of provider names
        """
        return list(set(self._providers.keys()) | set(self._builtin_providers.keys()))

    def merge_params(
        self,
        provider_name: str,
        step_params: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """
        Merge provider defaults with step parameters.

        Step parameters override defaults per specs/providers.md.

        Args:
            provider_name: Provider name
            step_params: Step-level provider parameters

        Returns:
            Merged parameters (step wins over defaults)
        """
        provider = self.get(provider_name)
        if not provider:
            return step_params or {}

        # Start with defaults
        merged = dict(provider.defaults)

        # Overlay step params (step wins)
        if step_params:
            merged.update(step_params)

        logger.debug(f"Merged params for {provider_name}: {merged}")
        return merged