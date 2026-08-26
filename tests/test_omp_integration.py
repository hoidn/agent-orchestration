"""Real OMP-I1 integration gates (Task 12, OMP-I1).

Runs the installed pinned OMP build through the real launch adapter against a
live loopback auth broker (profile lanes) or a validated real auth home
(ambient lanes). Every test here carries ``e2e`` and ``requires_secrets``;
missing pinned binary, broker pair, or credential state skips with an exact
reason.

Task 12 F-gate map (deterministic, structural observations only -- no literal
prompt phrasing is ever asserted):

- F3  exact profile cwd binding, workspace repository-context positive
      (``conf`` header ``additionalDirectories``) and negative (``no-tools``),
      conf byte-identity, confinement policy identity, adapter-owned attempt
      root removal, and the empty-cwd removal at run end.
- F4  installed binary/version/digest admission and private-copy execution
      (every successful run here passed the version probe; the frame binds the
      staged private copy's sha256 to the pin).
- F5  the five packaged presets through the real conf lane: exact
      PRESET_TOPOLOGIES advisor/child counts, peer-team hub correlation, and
      the binary/private/session/conf/confinement frame invariants.
- F6  the unrestricted ambient lane: a real transient run whose code-owned lane
      selects `--yolo`, with null confinement and no persisted session.

The remaining gates are intentionally not duplicated here: F1/F7 fork and
TTY resume need a real terminal (tmux/manual trial, Main), F2 nonzero-exit
composition is deterministic only with the fake child (already covered in
``test_provider_omp_launch.py``), and F8 typed-output inference needs a real
inference model call (Main's Step 12.2 declarative trial). No developer path
is hardcoded: the binary resolves from the current HOME, the auth home honors
``OMP_E2E_AUTH_HOME`` first, and all other roots are per-test tmp paths.
"""

from __future__ import annotations

import dataclasses
import io
import json
import os
import shutil
from pathlib import Path

import pytest

import orchestrator.providers.omp_launch as omp_launch
from orchestrator.omp_assets import PRESET_CONF_NAMES, preset_conf_root
from orchestrator.providers.omp_conf import admit_conf_tree
from orchestrator.providers.omp_observation import PRESET_TOPOLOGIES, hub_match
from orchestrator.providers.omp_launch_policy import (
    EMPTY_CWD_ENV,
    empty_omp_cwd_nonce,
    profile_attempt_key,
    profile_attempt_roots,
)
from orchestrator.providers.omp_pin import OMP_BINARY_PIN
from orchestrator.providers.omp_session import parse_journal_bytes
from orchestrator.providers.omp_transport import OmpJsonStdoutAccumulator

# Reuse the launch-module helpers verbatim (they reference their own module
# globals; the fixture below injects the per-test workspace into that global,
# which is per-process and therefore safe under pytest-xdist worksteal).
import tests.test_provider_omp_launch as launch_tests
from tests.test_provider_omp_launch import (
    _HEX64_RE,
    _adapter_argv,
    _env_roots,
    _expectation,
    _frame_bytes,
    _frozen_profile_expectation,
    _live_dir,
    _make_home,
    _run,
    _sha256_file,
    _std_env,
)

_REPLY_PROMPT = b"Reply with exactly: INTEGRATION-OK\n"


@pytest.fixture(autouse=True)
def _workspace(tmp_path: Path) -> Path:
    """One workspace per test; inject it into the imported launch helpers."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    launch_tests.workspace_path = workspace
    return workspace


# ---------------------------------------------------------------------------
# Live prerequisites (portable; skip with exact reasons)
# ---------------------------------------------------------------------------


def live_pinned_binary(tmp_path: Path) -> Path:
    """Stage the installed pinned OMP build as a resolver PATH dir, or skip."""
    installed = Path.home() / ".local" / "bin" / "omp"
    if not installed.is_file():
        pytest.skip("real pinned OMP binary not installed at ~/.local/bin/omp")
    if _sha256_file(installed) != OMP_BINARY_PIN.executable_sha256:
        pytest.skip("installed omp is not the pinned acceptance build (digest mismatch)")
    bindir = tmp_path / "real-bin"
    bindir.mkdir()
    shutil.copyfile(installed, bindir / "omp")
    (bindir / "omp").chmod(0o555)
    return bindir


def live_broker_pair() -> tuple[str, str]:
    """Loopback OMP auth broker pair from the environment, or skip."""
    from orchestrator.providers.omp_launch_contract import validate_broker_pair

    url = os.environ.get("OMP_AUTH_BROKER_URL")
    token = os.environ.get("OMP_AUTH_BROKER_TOKEN")
    if not url or not token:
        pytest.skip(
            "live loopback OMP auth broker pair not configured "
            "(OMP_AUTH_BROKER_URL/OMP_AUTH_BROKER_TOKEN)"
        )
    try:
        return validate_broker_pair({"OMP_AUTH_BROKER_URL": url, "OMP_AUTH_BROKER_TOKEN": token})
    except ValueError:
        pytest.skip("OMP_AUTH_BROKER_URL/OMP_AUTH_BROKER_TOKEN do not form a valid loopback pair")


def real_auth_home() -> Path | None:
    """Validated real auth home (agent.db credential store), never a hardcode.

    ``OMP_E2E_AUTH_HOME`` wins when set; otherwise the current HOME is used
    only after it carries the OMP agent credential store. Returns None when
    no candidate validates.
    """
    candidates: list[Path] = []
    explicit = os.environ.get("OMP_E2E_AUTH_HOME")
    if explicit:
        candidates.append(Path(explicit))
    candidates.append(Path.home())
    for candidate in candidates:
        if (candidate / ".omp" / "agent" / "agent.db").is_file():
            return candidate
    return None


def _accumulate_real(out: bytes, expectation, header_id: str):
    """Feed one real adapter stream through the codec with the real session id."""
    accumulator = OmpJsonStdoutAccumulator(
        expectation=dataclasses.replace(expectation, stdout_session_id=header_id)
    )
    accumulator.feed(out)
    return accumulator.finalize(expected_session_id=header_id, require_terminal=True)


# ---------------------------------------------------------------------------
# F5: the five packaged presets through the real conf lane (fresh sessions)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.requires_secrets
@pytest.mark.parametrize("name", PRESET_CONF_NAMES)
def test_real_preset_canary_exact_observation_topology(
    name: str, tmp_path: Path, _workspace: Path
) -> None:
    """F5: the packaged preset conf runs on the real binary and the adapter
    frame reports exactly PRESET_TOPOLOGIES advisor/child counts.

    The adapter's close-time observer enforces the digest-selected counts and
    the peer-team hub predicate itself, so a topology miss fails the launch.
    The test then asserts the exact frame observation topology and the
    binary/private/session/conf/confinement invariants, plus the F3 conf-lane
    workspace repository-context positive from the session header. Retry only
    a documented transient provider failure; a second mismatch is a gate
    failure (Task 12 Step 12.1).
    """
    bindir = live_pinned_binary(tmp_path)
    broker_url, broker_token = live_broker_pair()
    conf_root = preset_conf_root(name)
    prompt = (
        Path(__file__).parent / "fixtures" / "omp" / "presets" / name / "prompt.md"
    ).read_bytes()

    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    env.update({"OMP_AUTH_BROKER_URL": broker_url, "OMP_AUTH_BROKER_TOKEN": broker_token})
    env["PATH"] = f"{bindir}:{env['PATH']}"

    session_dir = _live_dir(tmp_path, f"preset-{name}__v1")
    argv = _adapter_argv("omp_conf", conf_root=str(conf_root), session_dir=str(session_dir))
    expectation, run_env = _frozen_profile_expectation(
        OMP_BINARY_PIN, argv, lane="conf", env=env, conf_root=str(conf_root),
        session_dir=str(session_dir), visit_key=session_dir.name, persistence="fresh",
    )
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(
        argv=argv, env=run_env, workspace=_workspace, stdin=prompt,
        pin=OMP_BINARY_PIN, out=out, err=err,
        resolver=lambda: omp_launch.resolve_omp_binary(run_env),
    )
    assert rc == 0, err.getvalue()

    child_bytes, frame = _frame_bytes(out.getvalue())
    assert json.dumps(frame, separators=(",", ":")) in out.getvalue().decode("utf-8")
    header = json.loads(child_bytes.splitlines()[0])
    assert header["type"] == "session" and isinstance(header["id"], str) and header["id"]
    metadata, error = _accumulate_real(
        out.getvalue(),
        dataclasses.replace(
            expectation, observed_relpaths=tuple(frame["observed"]["child_relpaths"])
        ),
        header["id"],
    )
    assert error is None and metadata is not None, error

    topology = PRESET_TOPOLOGIES[name]
    # F4: installed binary admission and private-copy execution identity.
    assert frame["binary"]["version"] == OMP_BINARY_PIN.version
    assert _HEX64_RE.fullmatch(frame["binary"]["sha256"]), frame
    assert frame["binary"]["sha256"] == OMP_BINARY_PIN.executable_sha256
    # F5: exact session placement and observation topology from the frame.
    assert frame["lane"] == "conf"
    assert frame["persistence"] == "fresh"
    assert frame["child"]["exit_code"] == 0
    assert frame["session"]["id"] == header["id"]
    assert frame["session"]["visit_key"] == session_dir.name
    primary = frame["session"]["primary_relpath"]
    assert primary.endswith(".jsonl"), frame
    assert primary.rsplit("_", 1)[-1][: -len(".jsonl")] == header["id"], frame
    assert _HEX64_RE.fullmatch(frame["session"]["primary_sha256"]), frame
    assert len(frame["observed"]["advisor_relpaths"]) == topology.advisor, frame
    assert len(frame["observed"]["child_relpaths"]) == topology.child, frame
    assert primary not in frame["observed"]["advisor_relpaths"]
    assert primary not in frame["observed"]["child_relpaths"]
    # F3: conf-lane child binds the adapter-owned empty cwd and exposes the
    # workflow workspace as the repository-context positive in the header.
    assert "omp-empty-" in header["cwd"], header
    additional = header.get("additionalDirectories") or []
    assert any(Path(entry).resolve() == _workspace.resolve() for entry in additional), header
    # F5 hub observation: peer-team requires one matched hub round-trip. The
    # close-time observer already enforced it (rc == 0); re-derive it from the
    # framed session tree so the assertion is visible here.
    if topology.hub_matched:
        matched_total = 0
        for dirpath, _dirs, files in os.walk(session_dir):
            for filename in files:
                if not filename.endswith(".jsonl"):
                    continue
                relpath = os.path.relpath(os.path.join(dirpath, filename), session_dir)
                parsed = parse_journal_bytes((session_dir / relpath).read_bytes(), relpath=relpath)
                matched, unmatched = hub_match(parsed)
                assert not unmatched, f"unmatched hub calls in {relpath!r}"
                matched_total += matched
        assert matched_total >= 1
    # F3/F5: conf admission digest and confinement policy identity from the frame.
    fd = os.open(conf_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        packaged_digest = admit_conf_tree(fd).manifest_sha256
    finally:
        os.close(fd)
    assert frame["conf"]["manifest_sha256"] == packaged_digest, frame
    assert packaged_digest == expectation.conf_manifest_sha256
    confinement = frame["confinement"]
    assert confinement["schema_version"] == "omp_write_confinement.v1", frame
    assert isinstance(confinement["landlock_abi"], int) and confinement["landlock_abi"] >= 3
    assert confinement["policy_sha256"] == expectation.confinement_policy_sha256, frame


# ---------------------------------------------------------------------------
# F3: profile write-authority compound canary (no-tools transient)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.requires_secrets
def test_real_no_tools_workspace_negative_and_attempt_cleanup(
    tmp_path: Path, _workspace: Path
) -> None:
    """F3: the no-tools lane omits the workspace root (header negative), runs
    in the adapter-owned empty cwd, and leaves only deterministic filesystem
    evidence: the frozen conf is byte-identical, and the adapter removes both
    the empty cwd and the whole attempt tree at run end.
    """
    bindir = live_pinned_binary(tmp_path)
    broker_url, broker_token = live_broker_pair()
    conf_root = preset_conf_root("neutral")

    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    env.update({"OMP_AUTH_BROKER_URL": broker_url, "OMP_AUTH_BROKER_TOKEN": broker_token})
    env["PATH"] = f"{bindir}:{env['PATH']}"

    argv = _adapter_argv("omp_no_tools", conf_root=str(conf_root))
    expectation, run_env = _frozen_profile_expectation(
        OMP_BINARY_PIN, argv, lane="no-tools", env=env, conf_root=str(conf_root),
    )
    empty_cwd = run_env[EMPTY_CWD_ENV]
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(
        argv=argv, env=run_env, workspace=_workspace, stdin=_REPLY_PROMPT,
        pin=OMP_BINARY_PIN, out=out, err=err,
        resolver=lambda: omp_launch.resolve_omp_binary(run_env),
    )
    assert rc == 0, err.getvalue()

    child_bytes, frame = _frame_bytes(out.getvalue())
    header = json.loads(child_bytes.splitlines()[0])
    assert header["type"] == "session" and isinstance(header["id"], str) and header["id"]
    metadata, error = _accumulate_real(out.getvalue(), expectation, header["id"])
    assert error is None and metadata is not None, error

    # F3: no-tools/inference receive no workspace tool or context root.
    assert not header.get("additionalDirectories"), header
    # F3: the profile child's process cwd is the adapter-owned empty cwd.
    assert "omp-empty-" in header["cwd"], header
    assert frame["lane"] == "no-tools"
    assert frame["persistence"] == "none"
    assert frame["child"]["exit_code"] == 0
    confinement = frame["confinement"]
    assert confinement["schema_version"] == "omp_write_confinement.v1"
    assert confinement["landlock_abi"] >= 3
    assert confinement["policy_sha256"] == expectation.confinement_policy_sha256
    fd = os.open(conf_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        digest = admit_conf_tree(fd).manifest_sha256
    finally:
        os.close(fd)
    assert frame["conf"]["manifest_sha256"] == digest == expectation.conf_manifest_sha256

    # F3 write-authority close-time cleanup: both adapter-owned roots are gone.
    assert not os.path.lexists(empty_cwd), "empty cwd must be removed at run end"
    attempt_key = profile_attempt_key(
        lane="no-tools", workspace=str(_workspace), session_dir=None,
        conf_root=str(conf_root), env_roots=_env_roots(env),
    )
    nonce = empty_omp_cwd_nonce(empty_cwd, expected_key=attempt_key)
    attempt = profile_attempt_roots(
        env_roots=_env_roots(env), lane="no-tools", workspace=str(_workspace),
        session_dir=None, conf_root=str(conf_root), nonce=nonce,
    )
    assert not os.path.lexists(attempt["HOME"]), "attempt tree must be removed at run end"


# ---------------------------------------------------------------------------
# F6: unrestricted yolo lane (ambient-unrestricted transient)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.requires_secrets
def test_real_unrestricted_yolo_lane_transient(tmp_path: Path, _workspace: Path) -> None:
    """F6: the ambient-unrestricted lane completes through the real binary
    with null confinement and no persisted session. The lane-to-``--yolo``
    child-argv mapping is already asserted at the fake-child execution seam."""
    bindir = live_pinned_binary(tmp_path)
    auth_home = real_auth_home()
    if auth_home is None:
        pytest.skip(
            "no validated real auth home (set OMP_E2E_AUTH_HOME or provide "
            "the OMP agent credential store under $HOME/.omp/agent)"
        )

    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    env["HOME"] = str(auth_home)
    env["PATH"] = f"{bindir}:{env['PATH']}"

    argv = _adapter_argv("omp_unrestricted_workspace")
    expectation = _expectation(OMP_BINARY_PIN, argv, lane="ambient-unrestricted")
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(
        argv=argv, env=env, workspace=_workspace, stdin=_REPLY_PROMPT,
        pin=OMP_BINARY_PIN, out=out, err=err,
        resolver=lambda: omp_launch.resolve_omp_binary(env),
    )
    assert rc == 0, err.getvalue()

    child_bytes, frame = _frame_bytes(out.getvalue())
    assert json.dumps(frame, separators=(",", ":")) in out.getvalue().decode("utf-8")
    header = json.loads(child_bytes.splitlines()[0])
    assert header["type"] == "session" and isinstance(header["id"], str) and header["id"]
    metadata, error = _accumulate_real(out.getvalue(), expectation, header["id"])
    assert error is None and metadata is not None, error

    assert frame["lane"] == "ambient-unrestricted"
    assert frame["persistence"] == "none"
    assert frame["confinement"] is None
    assert frame["child"]["exit_code"] == 0
    assert frame["session"]["visit_key"] is None
    assert frame["session"]["primary_relpath"] is None
    assert frame["observed"] == {"advisor_relpaths": [], "child_relpaths": []}
