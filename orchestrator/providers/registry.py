"""
Provider registry for managing provider templates.

Implements provider template storage, lookup, and parameter merging per specs/providers.md.
"""

import logging
from typing import Any, Dict, List, Optional

from .types import (
    CallPolicyBinding,
    InputMode,
    ProviderSessionMetadataMode,
    ProviderSessionSupport,
    ProviderTemplate,
)


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
        builtin_providers = self._load_builtin_providers()
        for provider in builtin_providers.values():
            self._raise_if_invalid(provider)
        self._builtin_providers = builtin_providers

    def _load_builtin_providers(self) -> Dict[str, ProviderTemplate]:
        """
        Load built-in provider templates.

        Returns:
            Dictionary of built-in provider templates
        """
        def codex_provider(name: str, model: str) -> ProviderTemplate:
            unrestricted_flags = ["--dangerously-bypass-approvals-and-sandbox"]
            return ProviderTemplate(
                name=name,
                command=[
                    "codex",
                    "exec",
                    "--model",
                    "${model}",
                    "--config",
                    "reasoning_effort=${reasoning_effort}",
                    *unrestricted_flags,
                ],
                defaults={"model": model, "reasoning_effort": "high"},
                input_mode=InputMode.STDIN,
                session_support=ProviderSessionSupport(
                    metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
                    fresh_command=[
                        "codex",
                        "exec",
                        "--json",
                        "--model",
                        "${model}",
                        "--config",
                        "reasoning_effort=${reasoning_effort}",
                        *unrestricted_flags,
                    ],
                    resume_command=[
                        "codex",
                        "exec",
                        "resume",
                        "${SESSION_ID}",
                        "--json",
                        "--model",
                        "${model}",
                        "--config",
                        "reasoning_effort=${reasoning_effort}",
                        *unrestricted_flags,
                    ],
                ),
                call_policy_bindings={
                    "model": CallPolicyBinding(target_param="model"),
                    "effort": CallPolicyBinding(target_param="reasoning_effort"),
                },
            )

        def claude_provider(name: str, model: str) -> ProviderTemplate:
            return ProviderTemplate(
                name=name,
                command=["claude", "-p", "${PROMPT}", "--model", "${model}"],
                defaults={"model": model},
                input_mode=InputMode.ARGV,
                call_policy_bindings={
                    "model": CallPolicyBinding(target_param="model"),
                    "effort": CallPolicyBinding(
                        target_param="effort",
                        argv_fragment=["--effort", "${effort}"],
                    ),
                },
            )

        return {
            "claude": claude_provider("claude", "claude-opus-4-6"),
            "claude_sonnet_summary": claude_provider(
                "claude_sonnet_summary", "claude-sonnet-4-6"
            ),
            "claude_haiku_summary": claude_provider(
                "claude_haiku_summary", "haiku"
            ),
            "gemini": ProviderTemplate(
                name="gemini",
                command=["gemini", "-p", "${PROMPT}"],
                defaults={},
                input_mode=InputMode.ARGV
            ),
            "codex": codex_provider("codex", "gpt-5.4"),
            "codex_gpt55": codex_provider("codex_gpt55", "gpt-5.5"),
            "codex_unrestricted_workspace": ProviderTemplate(
                name="codex_unrestricted_workspace",
                command=[
                    "codex",
                    "exec",
                    "--dangerously-bypass-approvals-and-sandbox",
                    "--skip-git-repo-check",
                    "--model",
                    "${model}",
                    "--config",
                    "reasoning_effort=${reasoning_effort}",
                ],
                defaults={},
                input_mode=InputMode.STDIN,
                call_policy_bindings={
                    "model": CallPolicyBinding(target_param="model"),
                    "effort": CallPolicyBinding(target_param="reasoning_effort"),
                },
            ),
            "claude_unrestricted_workspace": ProviderTemplate(
                name="claude_unrestricted_workspace",
                command=[
                    "claude",
                    "-p",
                    "--model",
                    "${model}",
                    "--effort",
                    "${effort}",
                    "--permission-mode",
                    "bypassPermissions",
                ],
                defaults={},
                input_mode=InputMode.STDIN,
                call_policy_bindings={
                    "model": CallPolicyBinding(target_param="model"),
                    "effort": CallPolicyBinding(target_param="effort"),
                },
            ),
        }

    @staticmethod
    def _raise_if_invalid(provider: ProviderTemplate) -> None:
        """Reject an invalid template at either registry entry boundary."""
        errors = provider.validate()
        if errors:
            raise ValueError(f"Invalid provider template: {'; '.join(errors)}")

    def register(self, provider: ProviderTemplate) -> None:
        """
        Register a provider template.

        Args:
            provider: Provider template to register

        Raises:
            ValueError: If provider is invalid
        """
        self._raise_if_invalid(provider)

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
                    input_mode=input_mode,
                    session_support=self._parse_session_support(config.get("session_support")),
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

    def _parse_session_support(self, config: Any) -> Optional[ProviderSessionSupport]:
        """Parse optional session-support command variants from workflow config."""
        if config is None or not isinstance(config, dict):
            return None

        fresh_command = config.get("fresh_command", [])
        resume_command = config.get("resume_command")
        metadata_mode = config.get("metadata_mode", "")
        return ProviderSessionSupport(
            metadata_mode=metadata_mode,
            fresh_command=fresh_command if isinstance(fresh_command, list) else [],
            resume_command=resume_command if isinstance(resume_command, list) else None,
        )

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
        step_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Merge provider defaults with step parameters.

        Step parameters override defaults per specs/providers.md.
        Supports nested structures for AT-44.

        Args:
            provider_name: Provider name
            step_params: Step-level provider parameters (can be nested)

        Returns:
            Merged parameters (step wins over defaults)
        """
        provider = self.get(provider_name)
        if not provider:
            return step_params or {}

        # Start with defaults
        merged = self._deep_copy_dict(provider.defaults)

        # Deep merge step params (step wins)
        if step_params:
            merged = self._deep_merge(merged, step_params)

        logger.debug(f"Merged params for {provider_name}: {merged}")
        return merged

    def _deep_copy_dict(self, source: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a deep copy of a dictionary.

        Args:
            source: Source dictionary

        Returns:
            Deep copy of the dictionary
        """
        import copy
        return copy.deepcopy(source)

    def _deep_merge(self, base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deep merge overlay dict into base dict.

        Args:
            base: Base dictionary
            overlay: Overlay dictionary (takes precedence)

        Returns:
            Merged dictionary
        """
        result = self._deep_copy_dict(base)

        for key, value in overlay.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # Recursively merge nested dicts
                result[key] = self._deep_merge(result[key], value)
            else:
                # Overlay value takes precedence
                result[key] = value

        return result
