"""End-to-end tests for the orchestrator using real CLIs.

These tests are:
- Skipped by default (require ORCHESTRATE_E2E environment variable)
- Dependent on real CLI tools (claude, codex) being available
- Slower than unit tests
- Used for final validation and release gates
"""