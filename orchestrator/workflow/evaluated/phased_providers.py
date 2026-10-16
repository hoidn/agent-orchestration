"""Concrete evaluated owners for the shared phased provider coordinator."""

from __future__ import annotations

from contextlib import closing
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import stat
import time
from hashlib import sha256

from orchestrator.contracts.output_contract import OutputContractError, validate_expected_outputs
from orchestrator.workflow.provider_phased_delivery.bindings import (
    AttemptAllocation, AttemptComposition, FunctionalEvidencePublication,
    PhasedOperationFailure, PhasedProviderAttemptPrepared, PhasedProviderAttemptFailure,
    PreparedSuccessCommit, SerializedAttemptEvent,
    CandidatePathBinding, CandidatePreflight, CandidateSnapshot, CandidateResetResult,
    FrozenCandidate, FrozenCandidateFile, FrozenCandidateRestoration,
    FrozenCandidateVerification, OutputPositionValidation, StructuredResultValidation,
    ValidatedArtifact, ValidatedStructuredResult,
)
from orchestrator.providers.interactive_terminal import (
    InteractiveTerminalTurnQueueAdapter, InteractiveTerminalReservation,
)
from orchestrator.providers.types import InteractiveSessionSupport, validate_interactive_session_support_capability
from orchestrator.workflow.provider_attempts import ProviderAttemptScope, EnclosingStep
from orchestrator.workflow.resume_projection_integrity import ResumeScopePath
from orchestrator.workflow.provider_phased_delivery.coordinator import PhasedProviderAttemptCoordinator
from orchestrator.workflow.provider_phased_delivery.endpoint import PhasedSubmitEndpoint
from orchestrator.workflow.provider_phased_delivery.frames import render_task_turn, render_initial_materialization_turn
from orchestrator.workflow.provider_phased_delivery.protocol import (
    PHASED_PROVIDER_BINDING_ENV, derive_submit_binding_and_locator,
)
from orchestrator.workflow.provider_phased_delivery.ledger import (
    ProviderPromptPhaseLedgerWriter, encode_header, _candidate_manifest, _decoded_manifest,
)
from orchestrator.workflow.provider_phased_delivery.models import CandidateDigestRow
from orchestrator.workflow.provider_phased_delivery.coordinator import _runtime_diagnostic
from orchestrator.workflow.provider_phased_delivery.diagnostics import _Q2_VALIDATION_CODES
from orchestrator.workflow.run_ref.contracts import canonical_sha256, canonical_json_bytes
from orchestrator.workflow.workspace_files import WorkspaceFiles
from .providers import ProviderPerformerError
from .run_header import _reject_duplicate_keys
from .commands import CommandPerformerError, validate_effect_result
from .values import EvaluatedValueError


def _bytes_digest(content):
    return "sha256:" + sha256(content).hexdigest()


def _relative(path):
    if (not isinstance(path, str) or not path or "\x00" in path
            or PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts
            or PurePosixPath(path).as_posix() != path or path == "."):
        raise ValueError("candidate path must be exact normalized relative POSIX text")
    return path


def _identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _validation_diagnostic(reason, error, default):
    violations = getattr(error, "violations", ())
    code = violations[0].get("type", default) if violations else default
    return _runtime_diagnostic(reason, canonical_value=code if code in _Q2_VALIDATION_CODES else default)


class _SubmittedFiles:
    """Feed shared validators the captured candidate, preserving path checks."""

    def __init__(self, owner, contents):
        self.owner, self.contents, self.workspace = owner, contents, owner.workspace

    def relative(self, path):
        return self.owner.relative(path)

    def exists(self, path):
        key = self.relative(path).as_posix()
        return self.contents[key] is not None if key in self.contents else self.owner.exists(path)

    def read(self, path, **kwargs):
        key = self.relative(path).as_posix()
        if key not in self.contents:
            return self.owner.read(path, **kwargs)
        content = self.contents[key]
        if content is None:
            raise FileNotFoundError(key)
        return content


class PhasedCandidates:
    """Pin exact candidate parents; never clear directories or foreign files."""

    def __init__(self, node, resolved, *, workspace_files, attempt_files,
            result_path, runtime_owned_roots=()):
        self.node, self.resolved = node, resolved
        self.workspace_files, self.attempt_files = workspace_files, attempt_files
        self.result_path = _relative(result_path)
        self.runtime_owned_roots = (workspace_files.workspace / ".orchestrate",
            *(Path(path) for path in runtime_owned_roots))
        self.preflight_result = None
        self.parents = {}
        self.contents = {}
        self.identities = {}
        self.snapshot_result = None
        self.value = None

    def close(self):
        for owner, _leaf in self.parents.values():
            owner.close()
        self.parents.clear()

    def declared_bindings(self):
        expected = self.resolved.expected_outputs
        names = [row["name"] for row in expected]
        if (any(not isinstance(name, str) or not name or name == "__structured_result_bundle__"
                for name in names) or len(names) != len(set(names))):
            raise ValueError("candidate output names must be unique and unreserved")
        bindings = tuple(CandidatePathBinding(index, "expected_output", row["name"],
            _relative(row["path"])) for index, row in enumerate(expected))
        bindings += (CandidatePathBinding(len(bindings), "structured_bundle",
            "__structured_result_bundle__", self.result_path),)
        return CandidatePreflight.create(bindings=bindings)

    def preflight(self, previous=None):
        preflight = self.declared_bindings()
        if previous is not None and previous != preflight:
            raise ValueError("foreign recovered candidate declarations")
        physical = set()
        try:
            for binding in preflight.bindings:
                path = binding.workspace_relative_path
                destination = self.workspace_files.workspace / path
                if binding.role == "expected_output" and any(
                    destination == root or root in destination.parents
                    for root in (*self.runtime_owned_roots, self.attempt_files.workspace)):
                    raise ValueError("candidate output overlaps runtime-owned storage")
                if previous is None and self.workspace_files.exists(path):
                    raise ValueError("candidate path already exists")
                self.workspace_files.ensure_parent(path)
                parent_path = Path(path).parent
                owner = (self.workspace_files.duplicate() if parent_path == Path(".")
                    else self.workspace_files.subroot(parent_path))
                key = (os.fstat(owner.root_fd).st_dev, os.fstat(owner.root_fd).st_ino, Path(path).name)
                if key in physical:
                    owner.close()
                    raise ValueError("candidate paths alias")
                physical.add(key)
                self.parents[path] = (owner, Path(path).name)
            self.preflight_result = preflight
            if previous is None:
                self._check_absent()
            return preflight
        except BaseException:
            self.close()
            raise

    def _check_parent(self, path):
        actual, pinned = os.stat(self.workspace_files.workspace, follow_symlinks=False), os.fstat(self.workspace_files.root_fd)
        if not stat.S_ISDIR(actual.st_mode) or (actual.st_dev, actual.st_ino) != (pinned.st_dev, pinned.st_ino):
            raise ValueError("candidate workspace root replaced")
        owner, _ = self.parents[path]
        parent_path = Path(path).parent
        current = (self.workspace_files.duplicate() if parent_path == Path(".")
            else self.workspace_files.subroot(parent_path))
        try:
            observed, pinned = os.fstat(current.root_fd), os.fstat(owner.root_fd)
            if (observed.st_dev, observed.st_ino) != (pinned.st_dev, pinned.st_ino):
                raise ValueError("candidate parent replaced")
        finally:
            current.close()
        return self.parents[path]

    def _check_absent(self):
        for path in self.parents:
            owner, leaf = self._check_parent(path)
            if owner.exists(leaf):
                raise ValueError("candidate absence could not be proven")

    def snapshot(self, preflight, ordinal):
        if preflight is not self.preflight_result:
            raise ValueError("foreign candidate preflight")
        contents, identities, rows = {}, {}, []
        for binding in preflight.bindings:
            path = binding.workspace_relative_path
            owner, leaf = self._check_parent(path)
            content, identity, presence = None, None, "missing"
            try:
                with owner.open_read(leaf) as source:
                    before = os.fstat(source.fileno())
                    content = source.read()
                    after = os.fstat(source.fileno())
                if (_identity(before) != _identity(after) or _identity(after) != _identity(owner.stat(leaf))
                        or before.st_nlink != 1):
                    raise ValueError("candidate changed while snapshotting or has aliases")
                identity, presence = _identity(after), "regular"
            except FileNotFoundError:
                pass
            except OSError:
                content, presence = None, "invalid"
            contents[path], identities[path] = content, identity
            rows.append(CandidateDigestRow(binding.contract_ordinal, binding.role,
                binding.logical_name, path, presence,
                len(content) if content is not None else None,
                _bytes_digest(content) if content is not None else None))
        snapshot = CandidateSnapshot.create(preflight=preflight,
            submission_ordinal=ordinal, rows=tuple(rows))
        self.contents, self.identities, self.snapshot_result = contents, identities, snapshot
        return snapshot

    def _submitted(self, snapshot):
        if snapshot is not self.snapshot_result:
            raise ValueError("foreign candidate snapshot")
        return _SubmittedFiles(self.workspace_files, self.contents)

    def validate_outputs(self, snapshot):
        diagnostic = None
        try:
            validate_expected_outputs(self.resolved.expected_outputs,
                workspace=self.workspace_files.workspace,
                workspace_files=self._submitted(snapshot), finite_floats=True)
            artifacts = tuple(ValidatedArtifact(row["name"], row["path"])
                for row in self.resolved.expected_outputs)
        except (OutputContractError, OSError, ValueError) as exc:
            artifacts, diagnostic = (), _validation_diagnostic("output_validation_failed", exc, "invalid_output_path")
        return OutputPositionValidation(snapshot.snapshot_sha256, artifacts, diagnostic)

    def validate_result(self, snapshot):
        try:
            submitted = self._submitted(snapshot)
            value, _, artifacts = validate_effect_result(self.node,
                submitted.read(self.result_path), self.result_path, submitted)
            if set(artifacts) & {row["name"] for row in self.resolved.expected_outputs}:
                raise ValueError("structured and output-position artifact names overlap")
            self.value = value
            return StructuredResultValidation(snapshot.snapshot_sha256,
                ValidatedStructuredResult(canonical_json_bytes(value.json_value())), None)
        except (OutputContractError, CommandPerformerError, EvaluatedValueError,
                OSError, ValueError, TypeError) as exc:
            self.value = None
            return StructuredResultValidation(snapshot.snapshot_sha256, None,
                _validation_diagnostic("structured_result_validation_failed", exc, "invalid_json_document"))

    def _stable(self, path, *, allow_missing=False, contents=True):
        owner, leaf = self._check_parent(path)
        try:
            info = owner.stat(leaf)
        except FileNotFoundError:
            if allow_missing:
                return owner, leaf
            raise
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or (contents and (_identity(info) != self.identities[path]
                    or owner.read(leaf) != self.contents[path]))):
            raise ValueError("candidate is no longer its stable owned regular file")
        if _identity(owner.stat(leaf)) != _identity(info):
            raise ValueError("candidate changed while checking ownership")
        return owner, leaf

    def reset(self, snapshot):
        self._submitted(snapshot)
        # Check the whole set before deleting any candidate.
        for path in self.parents:
            self._stable(path, allow_missing=self.contents[path] is None)
        for path in self.parents:
            owner, leaf = self._stable(path, allow_missing=self.contents[path] is None)
            if owner.exists(leaf):
                owner.unlink(leaf)
        self._check_absent()
        return CandidateResetResult(snapshot.snapshot_sha256,
            snapshot.preflight_sha256, "all_bound_paths_absent")

    def freeze(self, snapshot):
        self._submitted(snapshot)
        for path in self.parents:
            self._stable(path)
        return FrozenCandidate.create(snapshot=snapshot, files=tuple(
            FrozenCandidateFile(binding, self.contents[binding.workspace_relative_path])
            for binding in self.preflight_result.bindings))

    def restore(self, frozen):
        for item in frozen.files:
            path = item.binding.workspace_relative_path
            owner, leaf = self._stable(path, allow_missing=True, contents=False)
            owner.write_atomic(leaf, item.content)
            self.identities[path] = _identity(owner.stat(leaf))
            self.contents[path] = item.content
        return FrozenCandidateRestoration(frozen.frozen_sha256, len(frozen.files))

    def verify(self, frozen, restoration):
        if (restoration.frozen_sha256 != frozen.frozen_sha256
                or restoration.restored_paths != len(frozen.files)):
            raise ValueError("foreign restoration")
        for item in frozen.files:
            self._stable(item.binding.workspace_relative_path)
        return FrozenCandidateVerification(frozen.frozen_sha256, True)


def capture_phased_deadline(node, *, now=time.monotonic):
    """Capture t0 before input reads; no default provider timeout is authority."""
    if node.get("class") != "provider_phased":
        raise TypeError("checked phased provider required")
    operand = node.get("policy", {}).get("timeout_sec", {})
    timeout = operand.get("v")
    if (operand.get("k") != "lit" or operand.get("type") != {"kind": "primitive", "name": "Int"}
            or type(timeout) is not int or timeout <= 0):
        raise ValueError("phased timeout must be an explicit positive Int literal")
    t0 = now()
    try:
        budget = float(timeout)
        deadline = t0 + budget
    except (OverflowError, TypeError) as exc:
        raise ValueError("phased deadline is not representable") from exc
    if (type(t0) is not float or not math.isfinite(t0) or not math.isfinite(budget)
            or not math.isfinite(deadline) or deadline <= t0):
        raise ValueError("phased deadline is not a finite advancing deadline")
    return deadline


class _AuditLedger:
    """Optional diagnostic writer; poisoned audit output cannot become authority."""

    def __init__(self, writer=None):
        self.writer = writer

    def append(self, *args, **kwargs):
        if self.writer is not None:
            try:
                self.writer.append(*args, **kwargs)
            except Exception:
                self.close()

    def close(self):
        writer, self.writer = self.writer, None
        if writer is not None:
            try:
                writer.close()
            except Exception:
                pass


def _candidate_operation(reason, method, *args):
    try:
        return method(*args)
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        raise PhasedOperationFailure(_runtime_diagnostic(reason)) from exc


class EvaluatedPhasedBindings:
    """Project one evaluator allocation into the retained concrete protocol."""

    def __init__(self, attempt, *, deadline, transport_root):
        if type(deadline) is not float or not math.isfinite(deadline):
            raise ValueError("original phased deadline required")
        self.attempt, self.deadline, self.transport_root = attempt, deadline, Path(transport_root)
        _relative(attempt.result_path)
        self.allocation = AttemptAllocation(ProviderAttemptScope(
            run_id=attempt.authority.header["run_id"],
            resume_scope=ResumeScopePath(attempt.authority.header["workflow_file"], ()),
            runtime_step_id=attempt.identity,
            enclosing_step=EnclosingStep(attempt.identity, attempt.identity, 1),
            loop_iteration=None, adjudication_subject=None), attempt.ordinal)
        result = attempt.attempt_files.workspace / "result.json"
        if result != attempt.authority.run_root / attempt.result_path:
            raise ValueError("result path must bind the evaluator's allocated attempt")
        self.candidates = PhasedCandidates(attempt.node, attempt.resolved,
            workspace_files=attempt.workspace_files, attempt_files=attempt.attempt_files,
            result_path=result.relative_to(attempt.workspace_files.workspace).as_posix(),
            runtime_owned_roots=(attempt.authority.run_root,))
        self.reservation = self.adapter = self.composition = self.receipt = None

    def observed_at(self):
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def monotonic_now(self):
        return time.monotonic()

    def allocate_attempt(self):
        # This is a projection of the existing ordinal, never another allocation.
        return self.allocation

    def derive_attempt_deadline(self, allocation):
        if allocation is not self.allocation:
            raise ValueError("foreign evaluated allocation")
        return self.deadline

    def prestart_no_backend_allocation_proof(self):
        if self.adapter is not None:
            return self.adapter.prove_no_backend_allocation()
        from orchestrator.providers.interactive_terminal import NoBackendAllocationProof
        return NoBackendAllocationProof("no_backend_allocation", False, True)

    def compose_attempt(self, allocation, *, deadline):
        return _candidate_operation("preparation_failed", self._compose, allocation, deadline)

    def _compose(self, allocation, deadline):
        attempt = self.attempt
        if allocation is not self.allocation or deadline != self.deadline or time.monotonic() >= deadline:
            raise ValueError("foreign or expired phased preparation")
        if attempt.node.get("class") != "provider_phased" or attempt.resolved.canonical_cut is None:
            raise ValueError("checked phased request and captured canonical cut required")
        support = getattr(attempt.provider_executor.registry.get(attempt.node["provider"]),
            "interactive_session_support", None)
        if not isinstance(support, InteractiveSessionSupport) or validate_interactive_session_support_capability(support):
            raise ValueError("required interactive capability is unavailable or malformed")
        for leaf in ("tmux.sock", "phased-" + "0" * 32 + ".sock"):
            if len(os.fsencode(self.transport_root / ("orc-peer-" + "0" * 32) / leaf)) > 103:
                raise ValueError("trusted transport root is too long")
        self.reservation = InteractiveTerminalTurnQueueAdapter.reserve_recoverable(self.transport_root)
        self.adapter = InteractiveTerminalTurnQueueAdapter(attempt.attempt_files.workspace,
            socket_root=self.transport_root, reservation=self.reservation)
        binding, locator = derive_submit_binding_and_locator(
            attempt_scope_sha256=allocation.scope.key, socket_root=self.reservation.path,
            nonce=self.reservation.adapter_token, deadline=deadline)
        cut = attempt.resolved.canonical_cut
        if (cut.canonical_composed != attempt.resolved.prompt.encode("utf-8")
                or cut.projection.canonical_composed.sha256 != attempt.resolved.input_parts["prompt"]
                or canonical_sha256(asdict(cut.projection)) != attempt.resolved.input_parts["phased_cut"]
                or canonical_sha256("provider_phased_protocol_frame.v1") != attempt.resolved.input_parts["phased_protocol"]):
            raise ValueError("phased canonical capture changed after resolution")
        task = render_task_turn(cut=cut)
        initial = render_initial_materialization_turn(cut=cut, submit_keys=support.message_submit_keys)
        invocation, error = attempt.provider_executor.prepare_interactive_invocation(
            provider_name=attempt.node["provider"], params={}, context={},
            prompt_content=task.delivered_turn.decode("utf-8"), invocation_id=attempt.identity,
            member_id="evaluated", attempt_scope_key=allocation.scope.key,
            attempt_ordinal=allocation.attempt_ordinal, cwd=attempt.launch_cwd or attempt.workspace,
            env={"ORCHESTRATOR_OUTPUT_BUNDLE_PATH": str(attempt.attempt_files.workspace / "result.json"),
                PHASED_PROVIDER_BINDING_ENV: binding.opaque_value}, secrets=None,
            timeout_sec=attempt.resolved.policy["timeout_sec"],
            provider_call_policy={key: attempt.resolved.policy[key]
                for key in ("model", "effort") if key in attempt.resolved.policy})
        if error is not None or invocation is None or invocation.support != support:
            raise ValueError("interactive provider preparation failed or capability drifted")
        if attempt.resolved.policy.get("delivery") != "phased":
            raise ValueError("phased transport policy required")
        self.composition = AttemptComposition(cut, attempt.resolved.policy["materialization_attempts"],
            task, initial, invocation.pre_prompt_command, invocation, binding, locator, deadline)
        self.candidates.runtime_owned_roots += (self.reservation.path,)
        return self.composition

    def preflight_candidates(self, composition):
        return _candidate_operation("preparation_failed", self._preflight, composition)

    def _preflight(self, composition):
        if composition is not self.composition:
            raise ValueError("foreign phased composition")
        preflight = self.candidates.preflight()
        attempt = self.attempt
        self.receipt = {"schema_version": "evaluated_phased_provider_attempt.v1", "state": "intent",
            "identity": attempt.identity, "attempt": attempt.ordinal,
            "input_digest": attempt.input_digest, "result_path": attempt.result_path,
            "candidates": [row.to_dict() for row in preflight.bindings],
            "transport": self.reservation.to_dict()}
        attempt.attempt_files.create("prompt.txt", composition.cut.canonical_composed, exclusive=True)
        if attempt.attempt_files.exists("phased-attempt.json"):
            raise ValueError("phased ownership receipt already exists")
        _store_receipt(attempt.attempt_files, self.receipt)
        return preflight

    def create_ledger(self, allocation, composition):
        writer = None
        try:
            header = encode_header(scope=allocation.scope, ordinal=allocation.attempt_ordinal,
                cut=composition.cut, materialization_attempts=composition.materialization_attempts,
                created_at=self.observed_at())
            files = self.attempt.attempt_files
            files.create("phases.jsonl", header, exclusive=True)
            writer = ProviderPromptPhaseLedgerWriter._from_created_file(
                path=files.workspace / "phases.jsonl", descriptor=files.open_journal("phases.jsonl"),
                attempt=json.loads(header)["attempt"])
        except (OSError, ValueError, RuntimeError):
            pass
        return _AuditLedger(writer)

    def create_endpoint(self, composition):
        return PhasedSubmitEndpoint(binding=composition.submit_binding,
            locator=composition.endpoint_locator, configured_total=composition.materialization_attempts,
            reservation=self.reservation)

    def receive_attempt_event(self, *, boundary, endpoint, deadline):
        if boundary != "AWAITING_SUBMIT":
            return None
        while time.monotonic() < deadline:
            try:
                event = endpoint.receive_event(deadline=min(deadline, time.monotonic() + 0.05))
                return SerializedAttemptEvent("submit", event)
            except TimeoutError:
                pass
            # This only detects an early exit. Natural success still requires adapter.join.
            files = WorkspaceFiles(self.reservation.path)
            try:
                if files.exists("provider.exit-status"):
                    return SerializedAttemptEvent("provider_exit")
            finally:
                files.close()
        return SerializedAttemptEvent("deadline")

    def snapshot_candidates(self, preflight, submission_ordinal):
        return _candidate_operation("preparation_failed", self.candidates.snapshot, preflight, submission_ordinal)

    def validate_output_positions(self, snapshot):
        return self.candidates.validate_outputs(snapshot)

    def validate_structured_result(self, snapshot):
        return self.candidates.validate_result(snapshot)

    def reset_candidates(self, snapshot):
        return _candidate_operation("candidate_reset_failed", self.candidates.reset, snapshot)

    def freeze_candidate(self, snapshot, output, structured):
        return _candidate_operation("candidate_freeze_failed", self.candidates.freeze, snapshot)

    def publish_functional_evidence(self, frozen, actual_deliveries):
        # Inline commit evidence is authority; this projection needs no extra sidecar.
        payload = canonical_json_bytes({"manifest_sha256": frozen.manifest.manifest_sha256,
            "turns": [asdict(turn.projection) for turn in actual_deliveries]})
        return FunctionalEvidencePublication.create(frozen=frozen, actual_deliveries=actual_deliveries,
            relative_path="phased-attempt.json", evidence_sha256=_bytes_digest(payload))

    def restore_frozen_candidate(self, frozen):
        return _candidate_operation("frozen_restoration_failed", self.candidates.restore, frozen)

    def verify_frozen_candidate(self, frozen, restoration):
        return _candidate_operation("frozen_verification_failed", self.candidates.verify, frozen, restoration)

    def prepare_success_commit(self, **kwargs):
        return PreparedSuccessCommit(**kwargs)

    def finalize_failure(self, first_diagnostic, lifecycle):
        # The full returned failure is handled below, where cleanup proofs are available.
        pass


_PROOF_FIELDS = {"schema_version", "identity", "attempt", "input_digest", "result_path",
    "result_digest", "candidate_manifest", "canonical_prompt_sha256", "actual_deliveries_sha256",
    "natural_shutdown"}
_RECEIPT_BINDINGS = {"identity", "attempt", "input_digest", "result_path", "candidates", "transport"}
_RECEIPT_SCHEMA = "evaluated_phased_provider_attempt.v1"


def validate_phased_commit_proof(proof, *, identity=None, attempt=None, input_digest=None,
        result_path=None, result_digest=None, canonical_prompt_sha256=None, candidates=None):
    """Check the closed proof; contextual callers must supply enclosing bindings."""
    if not isinstance(proof, dict) or set(proof) != _PROOF_FIELDS:
        raise ValueError("phased commit proof has missing or unknown fields")
    if (proof["schema_version"] != "evaluated_phased_provider_commit.v1"
            or not isinstance(proof["identity"], str) or not proof["identity"]
            or type(proof["attempt"]) is not int or proof["attempt"] <= 0):
        raise ValueError("phased commit proof identity or ordinal invalid")
    _relative(proof["result_path"])
    for key in ("input_digest", "result_digest", "canonical_prompt_sha256", "actual_deliveries_sha256"):
        digest = proof[key]
        if (not isinstance(digest, str) or len(digest) != 71 or not digest.startswith("sha256:")
                or any(char not in "0123456789abcdef" for char in digest[7:])):
            raise ValueError("invalid phased proof digest")
    natural = proof["natural_shutdown"]
    if (not isinstance(natural, dict) or natural != {"disposition": "natural_exit", "return_code": 0,
            "pane_absent": True, "server_absent": True, "proof_complete": True}
            or type(natural["return_code"]) is not int
            or any(type(natural[key]) is not bool for key in ("pane_absent", "server_absent", "proof_complete"))):
        raise ValueError("invalid natural shutdown proof")
    manifest, recorded = _decoded_manifest(proof["candidate_manifest"])
    if manifest.disposition != "frozen" or manifest.manifest_sha256 != recorded:
        raise ValueError("phased manifest is not an exact frozen candidate")
    for key, expected in (("identity", identity), ("attempt", attempt), ("input_digest", input_digest),
            ("result_path", result_path), ("result_digest", result_digest),
            ("canonical_prompt_sha256", canonical_prompt_sha256)):
        if expected is not None and proof[key] != expected:
            raise ValueError("phased proof does not bind the enclosing " + key)
    if candidates is not None:
        declarations = [{key: row.to_dict()[key] for key in (
            "contract_ordinal", "role", "logical_name", "workspace_relative_path")} for row in manifest.rows]
        if canonical_json_bytes(declarations) != canonical_json_bytes(list(candidates)):
            raise ValueError("phased proof has foreign candidate declarations")
    return proof


def _check_attempt_root(files):
    for path, device, inode in getattr(files, "_phased_ancestor_bindings", ()):
        with closing(WorkspaceFiles(path)) as current:
            linked = os.fstat(current.root_fd)
            if (linked.st_dev, linked.st_ino) != (device, inode):
                raise ValueError("phased attempt ancestor replaced")
    with closing(WorkspaceFiles(files.workspace)) as current:
        linked, pinned = os.fstat(current.root_fd), os.fstat(files.root_fd)
        if (linked.st_dev, linked.st_ino) != (pinned.st_dev, pinned.st_ino):
            raise ValueError("phased attempt directory replaced")


def _load_receipt(files):
    _check_attempt_root(files)
    info = files.stat("phased-attempt.json")
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
        raise ValueError("foreign phased ownership receipt file")
    return json.loads(files.read("phased-attempt.json", max_bytes=1024 * 1024),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite phased receipt")))


def _store_receipt(files, receipt):
    _check_attempt_root(files)
    files.write_atomic("phased-attempt.json", canonical_json_bytes(receipt))
    _check_attempt_root(files)


def _transition_receipt(files, previous, receipt):
    if canonical_json_bytes(_load_receipt(files)) != canonical_json_bytes(previous):
        raise ValueError("phased ownership receipt changed before transition")
    _store_receipt(files, receipt)


def _validate_transport_shape(transport):
    fields = set(InteractiveTerminalReservation.__dataclass_fields__) - {"root"}
    if not isinstance(transport, dict) or set(transport) != fields:
        raise ValueError("invalid phased transport fields")
    token = transport["adapter_token"]
    if (transport["schema_version"] != "interactive_terminal_reservation.v1"
            or not isinstance(token, str) or len(token) != 32
            or any(char not in "0123456789abcdef" for char in token)
            or transport["namespace"] != "orc-peer-" + token
            or not isinstance(transport["boot_id"], str) or not transport["boot_id"]
            or any(type(transport[key]) is not int or transport[key] < 0
                for key in fields - {"schema_version", "adapter_token", "namespace", "boot_id"})):
        raise ValueError("invalid phased transport domains")


def validate_phased_settlement_receipt(files, proof):
    """Read-only K3 admission; torn or absent local receipts add no authority."""
    validate_phased_commit_proof(proof)
    try:
        receipt = _load_receipt(files)
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        receipt = None
    _check_attempt_root(files)
    if receipt is not None:
        if not isinstance(receipt, dict) or receipt.get("schema_version") != _RECEIPT_SCHEMA:
            raise ValueError("foreign phased receipt")
        for key in ("identity", "attempt", "input_digest", "result_path"):
            if key in receipt and receipt[key] != proof[key]:
                raise ValueError("foreign phased receipt binding")
        if "proof" in receipt and canonical_json_bytes(receipt["proof"]) != canonical_json_bytes(proof):
            raise ValueError("phased receipt proof mismatch")
        if receipt.get("state") == "settled":
            if set(receipt) != {"schema_version", "state", "proof"}:
                raise ValueError("invalid settled receipt shape")
            return True
        if receipt.get("state") not in {"intent", "prepared"}:
            raise ValueError("phased receipt cannot settle")
        if set(receipt) != ({"schema_version", "state"} | _RECEIPT_BINDINGS
                | ({"proof"} if receipt["state"] == "prepared" else set())):
            raise ValueError("phased receipt has missing or unknown fields")
        if type(receipt["attempt"]) is not int or receipt["attempt"] <= 0:
            raise ValueError("invalid phased receipt ordinal")
        _validate_transport_shape(receipt["transport"])
        validate_phased_commit_proof(proof, candidates=receipt["candidates"])


def settle_phased_receipt(files, proof):
    """Memo-only local settlement, without reopening candidates or transport."""
    if validate_phased_settlement_receipt(files, proof):
        return
    _store_receipt(files, {"schema_version": _RECEIPT_SCHEMA, "state": "settled", "proof": proof})


def validate_phased_attempt_receipt(receipt, *, identity, attempt, input_digest, result_path,
        candidates, transport_root):
    """The closed operational receipt never supplies its own expected binding."""
    if not isinstance(receipt, dict) or receipt.get("schema_version") != _RECEIPT_SCHEMA:
        raise ValueError("invalid phased attempt receipt schema")
    state = receipt.get("state")
    if state == "settled":
        if set(receipt) != {"schema_version", "state", "proof"}:
            raise ValueError("invalid settled phased receipt shape")
        validate_phased_commit_proof(receipt["proof"], identity=identity, attempt=attempt,
            input_digest=input_digest, result_path=result_path, candidates=candidates)
        return None
    if state not in {"intent", "prepared", "abandoned"} or set(receipt) != (
            {"schema_version", "state"} | _RECEIPT_BINDINGS | ({"proof"} if state == "prepared" else set())):
        raise ValueError("invalid phased attempt receipt state or fields")
    for key, expected in (("identity", identity), ("attempt", attempt),
            ("input_digest", input_digest), ("result_path", result_path), ("candidates", list(candidates))):
        if receipt[key] != expected:
            raise ValueError("foreign phased attempt " + key)
    if type(receipt["attempt"]) is not int or receipt["attempt"] <= 0:
        raise ValueError("invalid phased attempt ordinal")
    _relative(receipt["result_path"])
    declarations = tuple(CandidatePathBinding(**row) for row in receipt["candidates"])
    CandidatePreflight.create(bindings=declarations)
    reservation = InteractiveTerminalReservation.from_dict(transport_root, receipt["transport"])
    if state == "prepared":
        validate_phased_commit_proof(receipt["proof"], identity=identity, attempt=attempt,
            input_digest=input_digest, result_path=result_path, candidates=candidates)
    return reservation


def recover_phased_provider_attempt(attempt, *, deadline, transport_root):
    """K4 cleanup only; the evaluator owns the replacement ordinal and budget."""
    if type(deadline) is not float or not math.isfinite(deadline) or time.monotonic() >= deadline:
        raise ValueError("finite advancing recovery deadline required")
    bindings = EvaluatedPhasedBindings(attempt, deadline=deadline, transport_root=transport_root)
    try:
        declarations = bindings.candidates.declared_bindings()
        receipt = _load_receipt(attempt.attempt_files)
        reservation = validate_phased_attempt_receipt(receipt, identity=attempt.identity,
            attempt=attempt.ordinal, input_digest=attempt.input_digest, result_path=attempt.result_path,
            candidates=[row.to_dict() for row in declarations.bindings], transport_root=transport_root)
        if receipt["state"] == "settled":
            raise ValueError("committed phased attempt cannot be abandoned")
        if receipt["state"] == "abandoned":
            return True
        admission = PhasedSubmitEndpoint.inspect_owned(reservation, deadline=deadline)
        # Even read-only endpoint admission must precede adapter revocation/signalling.
        adapter = InteractiveTerminalTurnQueueAdapter(attempt.attempt_files.workspace,
            socket_root=Path(transport_root), reservation=reservation)
        proof = adapter.recover_failed(reservation, deadline=deadline)
        if not proof.cleanup_complete:
            raise ValueError("provider resource cleanup incomplete")
        PhasedSubmitEndpoint.recover_owned(reservation, deadline=deadline,
            provider_cleanup=proof, admission=admission)
        if canonical_json_bytes(_load_receipt(attempt.attempt_files)) != canonical_json_bytes(receipt):
            raise ValueError("phased receipt changed before candidate cleanup")
        preflight = bindings.candidates.preflight(previous=declarations)
        snapshot = bindings.candidates.snapshot(preflight, 1)
        bindings.candidates.reset(snapshot)
        if time.monotonic() >= deadline:
            raise ValueError("recovery deadline expired before abandonment")
        _transition_receipt(attempt.attempt_files, receipt, {key: value for key, value in receipt.items()
            if key != "proof"} | {"state": "abandoned"})
        return True
    finally:
        bindings.candidates.close()


@dataclass(frozen=True)
class EvaluatedPhasedPrepared:
    value: object
    proof: dict
    prepared: PhasedProviderAttemptPrepared
    coordinator: PhasedProviderAttemptCoordinator
    bindings: EvaluatedPhasedBindings

    @property
    def deadline(self):
        return self.prepared.deadline


def prepare_phased_provider_attempt(attempt, *, deadline, transport_root):
    """Return prepared value and proof, durably recording K2 before projection."""
    bindings = EvaluatedPhasedBindings(attempt, deadline=deadline, transport_root=transport_root)
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    outcome = coordinator.prepare()
    if type(outcome) is PhasedProviderAttemptFailure:
        cleanup_error = None
        try:
            resources_clean = (outcome.natural_shutdown_proof is not None or
                outcome.provider_cleanup_proof is not None and
                (getattr(outcome.provider_cleanup_proof, "cleanup_complete", False) or
                    getattr(outcome.provider_cleanup_proof, "proof_complete", False)))
            if (bindings.receipt is not None and resources_clean
                    and outcome.endpoint_shutdown_status in {"complete", "not_allocated"}):
                if canonical_json_bytes(_load_receipt(attempt.attempt_files)) != canonical_json_bytes(bindings.receipt):
                    raise ValueError("phased receipt changed before candidate cleanup")
                snapshot = bindings.candidates.snapshot(bindings.candidates.preflight_result, 1)
                bindings.candidates.reset(snapshot)
                _transition_receipt(attempt.attempt_files, bindings.receipt,
                    {**bindings.receipt, "state": "abandoned"})
        except (OSError, ValueError, RuntimeError) as exc:
            cleanup_error = str(exc)
        finally:
            coordinator.close()
            bindings.candidates.close()
        raise ProviderPerformerError(outcome.first_diagnostic.code, outcome.first_diagnostic.reason,
            exit_info={"cleanup_error": cleanup_error} if cleanup_error is not None else None)
    value = bindings.candidates.value
    proof = {"schema_version": "evaluated_phased_provider_commit.v1",
        "identity": attempt.identity, "attempt": attempt.ordinal, "input_digest": attempt.input_digest,
        "result_path": attempt.result_path, "result_digest": canonical_sha256(value.json_value()),
        "candidate_manifest": _candidate_manifest(outcome.prepared.frozen.manifest),
        "canonical_prompt_sha256": attempt.resolved.input_parts["prompt"],
        "actual_deliveries_sha256": outcome.prepared.evidence.actual_deliveries_sha256,
        "natural_shutdown": outcome.natural_shutdown.to_dict()}
    validate_phased_commit_proof(proof, candidates=bindings.receipt["candidates"])
    prepared = EvaluatedPhasedPrepared(value, proof, outcome, coordinator, bindings)
    try:
        _transition_receipt(attempt.attempt_files, bindings.receipt,
            {**bindings.receipt, "state": "prepared", "proof": proof})
    except (OSError, ValueError, RuntimeError) as exc:
        coordinator.close()
        bindings.candidates.close()
        raise ProviderPerformerError("provider_phased_publication_failed", "prepared receipt publication failed") from exc
    return prepared


def verify_phased_precommit(prepared):
    """The evaluator calls this immediately before its first memo commit."""
    if time.monotonic() >= prepared.deadline:
        raise ProviderPerformerError("provider_timeout", "original phased deadline expired before commit")
    frozen = prepared.prepared.prepared.frozen
    prepared.bindings.candidates.verify(frozen, FrozenCandidateRestoration(frozen.frozen_sha256, len(frozen.files)))
    attempt = prepared.bindings.attempt
    if canonical_json_bytes(_load_receipt(attempt.attempt_files)) != canonical_json_bytes(
            {**prepared.bindings.receipt, "state": "prepared", "proof": prepared.proof}):
        raise ValueError("phased ownership receipt does not bind the prepared result")
    candidates = prepared.bindings.candidates
    output = candidates.validate_outputs(candidates.snapshot_result)
    structured = candidates.validate_result(candidates.snapshot_result)
    if not output.valid or not structured.valid:
        raise ProviderPerformerError("provider_phased_publication_failed", "prepared result contract no longer holds")
    validate_phased_commit_proof(prepared.proof, identity=attempt.identity, attempt=attempt.ordinal,
        input_digest=attempt.input_digest, result_path=attempt.result_path,
        canonical_prompt_sha256=attempt.resolved.input_parts["prompt"],
        result_digest=canonical_sha256(prepared.value.json_value()),
        candidates=prepared.bindings.receipt["candidates"])
    if (prepared.proof["candidate_manifest"] != _candidate_manifest(frozen.manifest)
            or prepared.proof["actual_deliveries_sha256"] != prepared.prepared.prepared.evidence.actual_deliveries_sha256
            or prepared.proof["natural_shutdown"] != prepared.prepared.natural_shutdown.to_dict()
            or prepared.proof["result_digest"] != prepared.prepared.prepared.structured.result.sha256):
        raise ValueError("phased proof changed after preparation")
    if time.monotonic() >= prepared.deadline:
        raise ProviderPerformerError("provider_timeout", "original phased deadline expired during verification")


def settle_phased_provider_attempt(prepared):
    """Only call after the evaluator has durably committed its memo."""
    settle_phased_receipt(prepared.bindings.attempt.attempt_files, prepared.proof)
    prepared.coordinator.settle(prepared.prepared)
    prepared.bindings.candidates.close()
