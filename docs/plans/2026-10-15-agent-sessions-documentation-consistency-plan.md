# Agent Sessions 2.38 documentation consistency pass

Scope: reconcile current Agent Sessions authoring and runtime routes after the
Agent merge at `ed39c44e`, starting this pass at `60de4c89` and preserving
unrelated local changes. This is documentation
maintenance, not a new target, roadmap selection, runtime change or paid trial.
The before copies and manifest live in
`.superpowers/sdd/2026-10-15-agent-sessions-consistency/`.

1. Trace the documentation hub, capability/design catalogs, README, workflow
   chooser and lifecycle/guide introductions to the implemented bounded 2.38
   extension. Keep REPL's separate 2.35/2.36 boundary and 2.37 qualification gates.
2. Expand the existing Agent guide using the maintained four-turn example,
   its actual declarations/manifests and checked prerequisites. Explain two
   conversations, typed returns, constructor policy versus turn inputs, and
   point recovery/invalidation rules to their normative owners. Add a checked
   compile/dry-run recipe and explicit real-run/resume instructions after the
   command reviewer supplies evidence. Do not invoke providers.
3. Apply only accepted authority-review corrections to current specs/designs;
   preserve historical evidence, paid-smoke limits and the unrun PQ-1c gate.
4. Validate added links/anchors and documented command syntax; reuse valid
   unchanged checks. Compare the task diff against the saved before copies,
   report coverage and any remaining uncertainty. No broad suite, stage or commit.

The narrow approach keeps one current guide and existing example; future Agent
surfaces will still require separate admission, qualification and guide updates.
