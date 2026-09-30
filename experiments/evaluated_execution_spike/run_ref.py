"""The run-reference coordinator behind the spike's performer interface (design section 9.2, item E).

The run-ref runtime is unchanged. Its request is built from the closed program's node and
the effect's resolved input, not from flat state:

- the static configuration is the node's, built with the program; each of its inputs is
  the reference `inputs.<name>`;
- the parent state those references resolve against holds only the resolved input values;
- the visit key is derived from the identity: step id `root.<digest of the identity>`,
  visit count 1;
- the parent run root, where the runtime keeps its ledger `run-ref-attempts.jsonl`, is the
  spike's run root.

`prepare` runs the child to the runtime's pending commit and returns the settled envelope
(`value`, `workspace_delta`, `accounting`) with its proof; the evaluator commits the memo;
`settle` makes the runtime's final commit; on a memo hit `reconcile` completes a pending one.
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Any

from orchestrator.workflow.executable_ir import RunRefStepConfig, StepCommonConfig
from orchestrator.workflow.run_ref.config import decode_run_ref_static_config
from orchestrator.workflow.run_ref.ledger import RunRefVisitKey
from orchestrator.workflow.run_ref.runtime import (
    RunRefRuntimeDependencies,
    RunRefRuntimeRequest,
    finalize_run_ref_parent_commit,
    prepare_run_ref_settlement,
    validate_completed_run_ref_authority,
)


class RunRefCoordinator:
    def __init__(self, workspace: Path, run_root: Path, run_ref_root: Path,
                 dependencies: RunRefRuntimeDependencies | None = None) -> None:
        """`dependencies`: the runtime's source materializer and child launcher (default: git and a subprocess)."""

        self.workspace, self.run_root, self.run_ref_root = workspace.resolve(), run_root.resolve(), run_ref_root
        self.dependencies = dependencies
        self.prepared: dict[str, tuple[RunRefRuntimeRequest, Any]] = {}

    def request(self, node: dict[str, Any], resolved: dict[str, Any], identity: str) -> RunRefRuntimeRequest:
        static = decode_run_ref_static_config(base64.b64decode(node["config"]))
        step_id = "root." + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        return RunRefRuntimeRequest(
            step_config=RunRefStepConfig(common=StepCommonConfig(), run_ref=static, capsule_binding=None),
            visit=RunRefVisitKey(parent_run_id=self.run_root.name, execution_frame_id="root", call_frame_id=None,
                                 step_id=step_id, visit_count=1),
            parent_state={"bound_inputs": dict(resolved["inputs"]), "steps": {}},
            parent_workspace=self.workspace, parent_run_root=self.run_root, run_ref_root=self.run_ref_root,
            capsule_dir=None,
        )

    def prepare(self, node, resolved, identity, attempt):
        request = self.request(node, resolved, identity)
        prepared = prepare_run_ref_settlement(request, dependencies=self.dependencies)
        self.prepared[identity] = (request, prepared)
        proof = {"settled_result": prepared.settled_result.record, "artifacts": dict(prepared.artifacts)}
        return prepared.envelope, None, proof

    def settle(self, node, identity, proof) -> None:
        request, prepared = self.prepared.pop(identity)
        finalize_run_ref_parent_commit(request, prepared, persisted_settled_result=proof["settled_result"])

    def reconcile(self, node, resolved, identity, proof) -> None:
        validate_completed_run_ref_authority(self.request(node, resolved, identity),
                                             settled_result=proof["settled_result"], artifacts=proof["artifacts"],
                                             reconcile_pending=True)
