# Multi-Agent Orchestration — Master Spec (v1.1 + v1.1.1)

Status: Normative master. This index defines scope, versioning, conformance, and the module map with stable links to sub-specs. The DSL version and the state schema version are distinct by design.

- Versioning
  - DSL: v1.1 baseline; v1.1.1 adds dependency injection. v1.2 and v1.3 are planned, version-gated.
  - State schema: `schema_version: "1.1.1"`.
  - Validation is strict: unknown fields are rejected at the declared DSL `version`.

- Precedence and scope
  - The spec defines the external contract: DSL, state schema, CLI behavior, acceptance criteria.
  - Implementation architecture (see `arch.md`) provides ADRs and non-normative implementation guidance. If in conflict, the spec governs.

- Module map (normative unless marked informative)
  - DSL and Control Flow: `dsl.md`
  - Variable Model: `variables.md`
  - Providers and Prompt Delivery: `providers.md`
  - Step IO and Capture Limits: `io.md`
  - Dependencies and Injection: `dependencies.md`
  - Run Identity and State: `state.md`
  - Queues and Wait-For: `queue.md`
  - CLI Contract: `cli.md`
  - Observability and Status JSON: `observability.md`
  - Security and Path Safety: `security.md`
  - Versioning and Migration: `versioning.md`
  - Acceptance Tests: `acceptance/index.md`

- Out of scope
  - Concurrency/parallel blocks, while loops, complex expressions, event-driven triggers (beyond polling via wait_for).

- Quick links
  - Path safety: `security.md#path-safety`
  - Injection modes and caps: `dependencies.md#injection`
  - Output capture limits and tee semantics: `io.md#output-capture`
  - CLI safety rails: `cli.md#safety`

## Executive Summary

Versioning note: This specification defines the v1.1 baseline and includes the v1.1.1 additions for dependency injection. The state schema uses `schema_version: "1.1.1"`. Workflows written against v1.1 (without injection) remain valid. The workflow DSL `version:` and the state `schema_version` follow separate version tracks by design. DSL validation is strict: unknown fields are rejected. Workflows that use `depends_on.inject` MUST set `version: "1.1.1"` (or higher); v1.1 workflows must not include `inject`.

This system executes deterministic, sequential workflows described in YAML, including raw shell commands and LLM CLI invocations. Agents coordinate via filesystem queues (`inbox/`, `processed/`, `failed/`). Steps capture outputs as text, lines arrays, or JSON, with deterministic control flow (conditions, goto) and for-each loops. Provider prompts are composed from `input_file` plus optional dependency injection.

## Out of Scope

- Concurrency (sequential only)
- While loops
- Parallel execution blocks
- Complex expression evaluation
- Event-driven triggers
