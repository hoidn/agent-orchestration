# Adversarial DAQ Implementation Plan

**Goal:** Implement a runnable, bounded `.orc` experiment that gives an Orc advocate and a skeptical DAQ engineer equal opportunities to substantiate or defeat a scoped claim.

**Architecture:** Two independent provider roles, four rounds, immutable round submissions, an external paired-trial runner, and typed consensus gating in `.orc`. The runner records execution evidence; the two agents judge relevance and interpretation. No third model judge and no prose parsing for routing.

**Tech stack:** Hoidn agent-orchestration at `bb9cb30d8d4b2ea8b24b6d1ee996b198f640a1d2`, target 2.39, Python standard library runner, pytest.

Alternatives considered: prompt-only debate is leaner but lacks mechanical execution evidence; a full DAQ emulator in this deliverable would prematurely choose the experiment the adversaries are meant to discover. Use a small experiment protocol: the builder supplies a stateful simulator/oracle and Orc implementation, the skeptic supplies a baseline and adversarial cases, and both review the oracle before interpreting results.

## Work and verification

- [x] Read current upstream authoring/runtime contracts, attached kit, and current primary LCLS-II sources.
- [x] Record source-grounded counterevidence and explicit limitations.
- [x] Write failing tests for public CLI compilation and evidence collection; add public-runtime convergence, dissent and malformed-result checks.
- [x] Implement `.orc`, two phase-aware prompts, manifests, and runner.
- [x] Exercise actual compiler/runtime using clearly labeled deterministic provider substitutes; verify completed resume adds no effects.
- [x] Test paired runner on deliberately asymmetric synthetic fixtures, failed commands, incomplete evidence and file mutation.
- [x] Review implementation adversarially, repair defects, rerun targeted tests.
- [x] Deliver README, research notes, protocol, and compact distributable archive.

All work stays in this new directory. Existing workspace files and the original zip remain untouched. This implementation is not itself a completed scientific comparison, production controller, or OS sandbox. A finite empirical counterexample refutes only the stated claim; universal impossibility is not an outcome.
