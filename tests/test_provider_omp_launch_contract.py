import json
from pathlib import Path
import io
import subprocess
import sys

import pytest

from orchestrator.providers.omp_launch_contract import parse_adapter_argv


def _relay(lines: list[bytes], header: bytes | None = None) -> tuple[str | None, bool]:
    """Run a child that writes ``lines`` to stdout and relay it through the
    adapter's live relay; return (session_id, terminal_seen)."""
    from orchestrator.providers.omp_launch_contract import relay_child_output

    body = b"".join(line + b"\n" for line in lines)
    script = (
        "import sys\n"
        f"sys.stdout.buffer.write({body!r})\n"
        "sys.stdout.buffer.flush()\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    out, err = io.BytesIO(), io.StringIO()
    result = relay_child_output(proc, out=out, err=err)
    assert out.getvalue() == body
    return result

import pytest

from orchestrator.providers.omp_launch_contract import parse_adapter_argv


# ---------------------------------------------------------------------------
# Task 10 R2: exact broker pair URL grammar (X2) and setup command
# ---------------------------------------------------------------------------


def _broker_env(url, token="t" * 32) -> dict:
    from orchestrator.providers.omp_launch_contract import (
        BROKER_TOKEN_ENV,
        BROKER_URL_ENV,
    )

    return {BROKER_URL_ENV: url, BROKER_TOKEN_ENV: token}


def test_broker_pair_valid_loopback_forms_validate() -> None:
    from orchestrator.providers.omp_launch_contract import validate_broker_pair

    for url in ("http://127.0.0.1:1", "http://127.0.0.1:65535",
                "http://127.0.0.1:9001", "http://[::1]:9001",
                "http://[::1]:1", "http://127.0.0.1:9001/"):
        observed_url, observed_token = validate_broker_pair(_broker_env(url))
        assert observed_url == url
        assert observed_token == "t" * 32


def test_broker_pair_malformed_urls_rejected() -> None:
    from orchestrator.providers.omp_launch_contract import validate_broker_pair

    for bad in ("https://127.0.0.1:9001", "http://localhost:9001",
                "http://[::1]", "http://127.0.0.1", "http://127.0.0.1:0",
                "http://127.0.0.1:65536", "http://127.0.0.1:port",
                "http://user@127.0.0.1:9001", "http://127.0.0.1:9001?a=1",
                "http://127.0.0.1:9001#f", "http://::1:9001", "not-a-url", ""):
        with pytest.raises(ValueError, match="OMP_AUTH_BROKER_URL"):
            validate_broker_pair(_broker_env(bad))


def test_broker_pair_missing_member_prints_exact_setup_command() -> None:
    from orchestrator.providers.omp_launch_contract import (
        BROKER_TOKEN_ENV,
        BROKER_URL_ENV,
        validate_broker_pair,
    )

    for env in ({}, {BROKER_URL_ENV: "http://127.0.0.1:9001"},
                {BROKER_TOKEN_ENV: "t" * 32}, {BROKER_URL_ENV: ""}):
        with pytest.raises(ValueError, match="omp auth-broker serve"):
            validate_broker_pair(env)
    # No credential value may appear in the refusal text.
    token = "must-not-print-" + "x" * 12
    with pytest.raises(ValueError) as excinfo:
        validate_broker_pair({BROKER_URL_ENV: "http://localhost:9001",
                              BROKER_TOKEN_ENV: token})
    assert token not in str(excinfo.value)


def test_profile_env_names_are_the_closed_omp_conf_env_schema() -> None:
    from orchestrator.providers.omp_launch_contract import (
        BROKER_TOKEN_ENV,
        BROKER_URL_ENV,
        PROFILE_ENV_NAMES,
    )

    assert BROKER_URL_ENV == "OMP_AUTH_BROKER_URL"
    assert BROKER_TOKEN_ENV == "OMP_AUTH_BROKER_TOKEN"
    assert BROKER_URL_ENV in PROFILE_ENV_NAMES
    assert BROKER_TOKEN_ENV in PROFILE_ENV_NAMES
    assert "OMP_BROKER_URL" not in PROFILE_ENV_NAMES
    assert "OMP_BROKER_TOKEN" not in PROFILE_ENV_NAMES


def test_launch_env_names_are_lane_aware() -> None:
    from orchestrator.providers.omp_launch_contract import (
        PROFILE_ENV_NAMES,
        valid_launch_env_names,
    )

    required = sorted({
        "HOME", "OMP_AUTH_BROKER_TOKEN", "OMP_AUTH_BROKER_URL", "PATH",
        "PI_CODING_AGENT_DIR", "SHELL", "TMPDIR", "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME",
    })
    with_lang = sorted([*required, "LANG"])
    assert valid_launch_env_names("omp_no_tools", required)
    assert valid_launch_env_names("omp_conf", with_lang)
    assert valid_launch_env_names("omp_conf_inference", sorted(PROFILE_ENV_NAMES))
    assert valid_launch_env_names("omp", ["HOME", "PATH", "Z_CUSTOM"])
    assert not valid_launch_env_names("omp", ["PATH", "HOME"])
    assert not valid_launch_env_names("omp", ["HOME", "HOME"])
    assert not valid_launch_env_names("omp_no_tools", ["HOME", "PATH"])
    assert not valid_launch_env_names("unknown", sorted(PROFILE_ENV_NAMES))


# ---------------------------------------------------------------------------
# Task 10 R4: settlement is decided only by the shared parsed lifecycle
# authority, never by a raw byte shape
# ---------------------------------------------------------------------------


def _valid_child_lines(agent_end: bytes | None = None) -> list[bytes]:
    fixture = (
        Path(__file__).parent
        / "fixtures/omp/protocol/transient.stdout.jsonl"
    )
    lines = fixture.read_bytes().splitlines()
    if agent_end is not None:
        lines[-1] = agent_end
    return lines


def test_relay_formatted_whitespace_agent_end_settles() -> None:
    session_id, terminal = _relay(_valid_child_lines(
        b'{ "type" : "agent_end", "messages" : [ ] }'
    ))
    assert session_id == "01a030c1-af4f-7000-897e-cb536d4db45f"
    assert terminal is True


def test_relay_agent_end_omitted_is_terminal_settles() -> None:
    _, terminal = _relay(_valid_child_lines(
        b'{"type":"agent_end","messages":[]}'
    ))
    assert terminal is True


def test_relay_malformed_agent_end_is_not_terminal() -> None:
    _, terminal = _relay(_valid_child_lines(b'{"type":"agent_end"}'))
    assert terminal is False


def test_relay_nonterminal_agent_end_is_not_terminal() -> None:
    _, terminal = _relay(_valid_child_lines(
        b'{"type":"agent_end","messages":[],"isTerminal":false}'
    ))
    assert terminal is False


def test_relay_no_agent_end_is_not_terminal() -> None:
    _, terminal = _relay(_valid_child_lines()[:-1])
    assert terminal is False


def test_relay_requires_the_session_header_first() -> None:
    session_id, terminal = _relay([
        b'{"type":"turn_start"}',
        *_valid_child_lines(),
    ])
    assert session_id is None
    assert terminal is False


def test_relay_rejects_invalid_post_terminal_tail() -> None:
    _, terminal = _relay([
        *_valid_child_lines(),
        b'{"type":"turn_end"}',
    ])
    assert terminal is False


def test_validate_agent_end_terminal_parsed_authority() -> None:
    """R4: the single shared lifecycle authority accepts whitespace and an
    omitted optional isTerminal, and refuses malformed/nonterminal events."""
    from orchestrator.providers.omp_protocol import validate_agent_end_terminal

    assert validate_agent_end_terminal(
        {"type": "agent_end", "messages": []}
    ) == (True, None)
    assert validate_agent_end_terminal(
        {"type": "agent_end", "messages": [], "isTerminal": True}
    ) == (True, None)
    assert validate_agent_end_terminal(
        {"type": "agent_end", "messages": [], "isTerminal": False}
    ) == (False, None)
    terminal, error = validate_agent_end_terminal({"type": "agent_end"})
    assert terminal is False and error is not None
    terminal, error = validate_agent_end_terminal({"type": "turn_start"})
    assert terminal is False and error is not None
