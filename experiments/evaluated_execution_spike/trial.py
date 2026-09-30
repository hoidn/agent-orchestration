"""The trial coordinator behind the spike's performer interface (iteration 4).

The trial runtime is unchanged. `prepare` runs the cells (each arm's run reference), the
evaluation (checks and the judge) and the runtime's own pending commit, `trial_prepared`;
the evaluator commits the memo; `settle` makes the runtime's final commit,
`trial_parent_committed`, against a parent-state view of that memo commit; on a memo hit
`reconcile` prepares again (the runtime reuses its row) and commits (or reuses the commit).

The request is built from the node and the resolved input, not from flat state:
- the static configuration is the node's; each arm's inputs are the references
  `inputs.<name>`, resolved against a parent state that holds only the resolved values;
- the arms' capsule (their bundle-mode programs) is the adapter's;
- the visit key is derived from the identity;
- the sealed opaque labels are drawn once, and read back from the runtime's ledger header
  on a later attempt, as the present route does.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

from orchestrator.workflow.executable_ir import derive_unbound_trial_step_config
from orchestrator.workflow.run_ref.config import RunRefBundleCapsuleBinding
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
from orchestrator.workflow.run_ref.ledger import RunRefVisitKey
from orchestrator.workflow.trial.adjudication import evaluate_trial_execution
from orchestrator.workflow.trial.config import build_trial_runtime_request, decode_trial_static_config
from orchestrator.workflow.trial.contracts import build_sealed_opaque_label_map, derive_trial_cell_effect_scopes
from orchestrator.workflow.trial.ledger import load_trial_event_ledger
from orchestrator.workflow.trial.runtime import execute_trial_cells
from orchestrator.workflow.trial.settlement import commit_trial_parent_settlement, prepare_trial_parent_settlement

STEP = "trial"  # the step name of the parent-state view the runtime's final commit checks


class TrialCoordinator:
    def __init__(self, workspace: Path, run_root: Path, run_ref_root: Path, capsule_dir: Path, capsule_digest: str,
                 runtime_dependencies: Any = None, evaluation_dependencies: Any = None) -> None:
        """`runtime_dependencies`: the cells' materializer and child launcher; `evaluation_dependencies`: the
        checks' runner and the judge (defaults: git, subprocesses and the provider registry)."""

        self.workspace, self.run_root, self.run_ref_root = workspace.resolve(), run_root.resolve(), run_ref_root
        self.capsule_dir, self.capsule_digest = capsule_dir, capsule_digest
        self.runtime_dependencies, self.evaluation_dependencies = runtime_dependencies, evaluation_dependencies
        self.prepared: dict[str, tuple[Any, Any]] = {}

    def request(self, node: dict[str, Any], resolved: dict[str, Any], identity: str) -> tuple[Any, dict[str, Any]]:
        """The runtime request, and the parent state its input references resolve against."""

        static = decode_trial_static_config(base64.b64decode(node["config"]))
        binding = RunRefBundleCapsuleBinding(self.capsule_digest)
        unbound = derive_unbound_trial_step_config(static)
        step_config = replace(unbound, arms=tuple(replace(arm, run_ref=replace(arm.run_ref, capsule_binding=binding))
                                                  for arm in unbound.arms))
        by_arm: dict[str, dict[str, Any]] = {}
        bound: dict[str, Any] = {}
        for arm_id, name, keyword in node["arm_inputs"]:
            value = resolved["inputs"][keyword]
            if bound.setdefault(name, value) != value:
                # ponytail: one parent state for all arms; bind by keyword if arms ever differ on one name
                raise ValueError(f"trial arms bind input `{name}` to different values")
            by_arm.setdefault(arm_id, {})[name] = value
        visit = RunRefVisitKey(parent_run_id=self.run_root.name, execution_frame_id="root", call_frame_id=None,
                               step_id="root." + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16],
                               visit_count=1)
        request = build_trial_runtime_request(step_config=step_config, visit=visit, resolved_inputs_by_arm=by_arm)
        return request, {"bound_inputs": bound, "steps": {}}

    def ledger(self, request: Any) -> Path:
        scopes = derive_trial_cell_effect_scopes(request=request, parent_run_root=self.run_root,
                                                 run_ref_root=self.run_ref_root)
        return scopes[0].trial_root / "trial-events.jsonl"

    def labels(self, request: Any) -> Any:
        ledger = self.ledger(request)
        if not ledger.exists():
            return build_sealed_opaque_label_map(request.cell_domain, salt=os.urandom(32))
        header = load_trial_event_ledger(ledger).rows[0].payload
        labels = tuple(row["opaque_label"] for row in header["sealed_opaque_label_map"]["bindings"])
        return build_sealed_opaque_label_map(request.cell_domain, labels=labels)

    def prepare(self, node, resolved, identity, attempt):
        request, parent_state = self.request(node, resolved, identity)
        execution = execute_trial_cells(
            request, parent_state=parent_state, parent_workspace=self.workspace, parent_run_root=self.run_root,
            run_ref_root=self.run_ref_root, capsule_dir=self.capsule_dir, sealed_opaque_labels=self.labels(request),
            dependencies=self.runtime_dependencies,
        )
        adjudicated = evaluate_trial_execution(request, execution, parent_workspace=self.workspace,
                                               dependencies=self.evaluation_dependencies)
        envelope = json.loads(canonical_json_bytes({"outcomes": list(adjudicated.authored_outcomes),
                                                    "verdict": adjudicated.verdict,
                                                    "verdict_artifact": adjudicated.verdict_artifact.relpath}))
        prepared = prepare_trial_parent_settlement(execution.ledger_path, request=request,
                                                   parent_workspace=self.workspace, result_envelope=envelope)
        self.prepared[identity] = (request, prepared)
        return envelope, None, {"envelope": envelope}

    def settle(self, node, identity, proof) -> None:
        request, prepared = self.prepared.pop(identity)
        self.commit(request, prepared, proof["envelope"])

    def reconcile(self, node, resolved, identity, proof) -> None:
        request, _ = self.request(node, resolved, identity)
        prepared = prepare_trial_parent_settlement(self.ledger(request), request=request,
                                                   parent_workspace=self.workspace, result_envelope=proof["envelope"])
        self.commit(request, prepared, proof["envelope"])

    def commit(self, request: Any, prepared: Any, envelope: dict[str, Any]) -> None:
        """The runtime's final commit, checked against the memo's commit seen as the parent state it expects."""

        artifacts = {"verdict_artifact": envelope["verdict_artifact"]}
        view = {"run_id": request.visit.parent_run_id, "current_step": None, "steps": {STEP: {
            "status": "completed", "name": STEP, "step_id": request.visit.step_id,
            "visit_count": request.visit.visit_count, "trial": envelope, "artifacts": artifacts}}}
        commit_trial_parent_settlement(prepared.ledger_path, request=request, prepared=prepared, step_name=STEP,
                                       expected_artifacts=artifacts, read_parent_state=lambda: view)
