"""fetch.sh, the one command of the MLE-bench line that reads the Kaggle token (family plan M10, Task 10a).

Every run is against a stand-in `mlebench` (and a stand-in `df`) on a closed PATH, with a fake token this module
generates: no Kaggle, no real credential, no network. The stand-in does what the real tool may do with the token:
it reads kaggle.json from KAGGLE_CONFIG_DIR, prints the account name and key on stdout and stderr, writes them to
its working and temporary directories, tries /dev/tty and asks a question on standard input. The tests then
check that the key and the account name are nowhere outside the token directory, and that the pane shows only
fetch.sh's fixed lines.
"""

import json
import os
import secrets
import select
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.agent_session_shims import closed_path

FETCH = Path(__file__).resolve().parents[2] / "experiments" / "mle_bench_tasks" / "fetch.sh"
FLOOR = 20 * 10**9  # the ladder's free-disk floor, 20 GB (family plan M9)
DONE, FAILED, NO_ROOM = "done", "rules not accepted or download failed", "no room"

# Slug suffixes pick the stand-in's behaviour: `-fail` fails noisily, `-ask` asks the rules question, `-hang` sleeps,
# else done.
STAND_IN = r'''
import json, os, pathlib, resource, sys, tempfile
here = pathlib.Path(__file__).parent
slug, data = sys.argv[sys.argv.index("-c") + 1], sys.argv[sys.argv.index("--data-dir") + 1]
with open(here / "calls", "a") as calls:
    calls.write(slug + "\n")
cred = json.loads((pathlib.Path(os.environ["KAGGLE_CONFIG_DIR"]) / "kaggle.json").read_text())
secret = cred["username"] + ":" + cred["key"]
try:
    with open("/dev/tty", "w") as tty:
        tty.write("tty " + secret + "\n")
    dev_tty = True
except OSError:
    dev_tty = False
report = {"argv": sys.argv[1:], "env": dict(os.environ), "cwd": os.getcwd(), "stdin_tty": os.isatty(0),
          "dev_tty": dev_tty, "core": resource.getrlimit(resource.RLIMIT_CORE)[0]}
print("REPORT " + json.dumps(report), flush=True)
print("stdout " + secret, flush=True)
print("stderr " + secret, file=sys.stderr, flush=True)
pathlib.Path("leak-cwd").write_text(secret)
pathlib.Path(tempfile.gettempdir(), "leak-tmp").write_text(secret)
if slug.endswith("-hang"):
    (here / "hang.pid").write_text(str(os.getpid()))
    import time; time.sleep(60)
if slug.endswith("-fail"):
    raise RuntimeError("download failed for " + secret)
if slug.endswith("-ask"):
    print("You must accept this competition's rules. Open the page now? (y/n): " + secret, flush=True)
    answer = input()
    print("answered " + answer + " " + secret, flush=True)
    sys.exit(1)
private = pathlib.Path(data, slug, "prepared", "private")
private.mkdir(parents=True)
(private / "answers.csv").write_text("id\n1\n")
'''

STAND_IN_DF = r'''
import sys
print("Avail")
for _ in [a for a in sys.argv[1:] if not a.startswith("-")]:
    print(%d)
'''


class Box:
    """One fake machine under tmp_path: a home with the token directory, a bin directory of stand-ins."""

    def __init__(self, root: Path, free: int = 10 * FLOOR):
        self.root, self.home, self.bin = root, root / "home", root / "bin"
        self.token_dir = self.home / ".local" / "state" / "mle-secret"
        self.work, self.tmp = root / "work", root / "tmp"
        for d in (self.bin, self.work, self.tmp):
            d.mkdir(parents=True)
        self.token_dir.mkdir(parents=True, mode=0o700)
        self.token_dir.chmod(0o700)
        self.username, self.key = f"user{secrets.token_hex(6)}", secrets.token_hex(16)
        token = self.token_dir / "kaggle.json"
        token.write_text(json.dumps({"username": self.username, "key": self.key}))
        token.chmod(0o600)
        self._tool("mlebench", STAND_IN)
        self._tool("df", STAND_IN_DF % free)

    def _tool(self, name: str, body: str) -> None:
        (self.bin / name).write_text(f"#!{sys.executable}\n" + body)
        (self.bin / name).chmod(0o700)

    def env(self, **extra) -> dict:
        env = {"HOME": str(self.home), "PATH": closed_path(self.bin), "TMPDIR": str(self.tmp),
               "KAGGLE_CONFIG_DIR": str(self.token_dir)}
        return {k: v for k, v in {**env, **extra}.items() if v is not None}

    def run(self, *slugs: str, stdin: str = "", prefix: tuple = (), **extra) -> subprocess.CompletedProcess:
        return subprocess.run([*prefix, str(FETCH), *slugs], cwd=self.work, env=self.env(**extra), input=stdin,
                              capture_output=True, text=True, timeout=60)

    def calls(self) -> list[str]:
        path = self.bin / "calls"
        return path.read_text().split() if path.exists() else []

    def reports(self) -> list[dict]:
        lines = [l for p in sorted(self.token_dir.rglob("*")) if p.is_file() and p.name != "kaggle.json"
                 for l in p.read_text(errors="replace").splitlines() if l.startswith("REPORT ")]
        return [json.loads(l[len("REPORT "):]) for l in lines]

    def leaks_outside_token_dir(self, *texts: str) -> list[str]:
        """Every file under the box but outside the token directory, and each given text, that holds the key or
        the account name."""
        needles = (self.key.encode(), self.username.encode())
        hits = [f"text {i}" for i, t in enumerate(texts) if any(n in t.encode() for n in needles)]
        for path in self.root.rglob("*"):
            if path.is_file() and not path.is_symlink() and self.token_dir not in path.parents:
                if any(n in path.read_bytes() for n in needles):
                    hits.append(str(path))
        return hits


@pytest.fixture
def box(tmp_path):
    return Box(tmp_path)


# --- refusals: exit 2, the tool never runs ---------------------------------------------------------------------

@pytest.mark.parametrize("value", [None, ""])
def test_refuses_without_the_directory_variable(box, value):
    done = box.run("leaf-classification", KAGGLE_CONFIG_DIR=value)
    assert (done.returncode, done.stdout, box.calls()) == (2, "", [])


@pytest.mark.parametrize("dir_mode, file_mode", [(0o750, 0o600), (0o755, 0o600), (0o701, 0o600),
                                                 (0o700, 0o640), (0o700, 0o644), (0o700, 0o400), (0o700, 0o700)])
def test_refuses_a_token_directory_or_file_of_another_mode(box, dir_mode, file_mode):
    (box.token_dir / "kaggle.json").chmod(file_mode)
    box.token_dir.chmod(dir_mode)
    done = box.run("leaf-classification")
    assert (done.returncode, done.stdout, box.calls()) == (2, "", [])


def test_refuses_a_token_directory_without_the_token_file(box):
    (box.token_dir / "kaggle.json").unlink()
    done = box.run("leaf-classification")
    assert (done.returncode, box.calls()) == (2, [])


def test_refuses_a_token_file_that_is_a_link(box):
    real = box.root / "elsewhere.json"
    (box.token_dir / "kaggle.json").rename(real)
    (box.token_dir / "kaggle.json").symlink_to(real)
    done = box.run("leaf-classification")
    assert (done.returncode, box.calls()) == (2, [])


def test_refuses_a_token_directory_that_is_a_link(box):
    link = box.root / "link-dir"
    link.symlink_to(box.token_dir)
    done = box.run("leaf-classification", KAGGLE_CONFIG_DIR=str(link))
    assert (done.returncode, box.calls()) == (2, [])


def test_refuses_a_relative_token_directory(box):
    rel = os.path.relpath(box.token_dir, box.work)
    done = box.run("leaf-classification", KAGGLE_CONFIG_DIR=rel)
    assert (done.returncode, box.calls()) == (2, [])


def test_refuses_a_token_directory_inside_a_git_repository(box):
    subprocess.run(["git", "init", "-q", str(box.home)], check=True, env={"PATH": "/usr/bin:/bin", "HOME": str(box.root)})
    done = box.run("leaf-classification")
    assert (done.returncode, box.calls()) == (2, [])


@pytest.mark.parametrize("name", ["../leaf", "-a", "--all", "Leaf", "leaf classification", "leaf/x", ""])
def test_refuses_a_name_that_is_not_a_competition_slug(box, name):
    done = box.run("leaf-classification", name)
    assert (done.returncode, done.stdout, box.calls()) == (2, "", [])


def test_refuses_when_no_competition_is_named(box):
    done = box.run()
    assert (done.returncode, box.calls()) == (2, [])


# --- what the pane shows ---------------------------------------------------------------------------------------

def test_prints_one_fixed_line_per_competition_when_the_tool_fails_noisily_or_asks(box):
    done = box.run("leaf-classification", "birds-fail", "patent-ask")
    want = (1, [f"leaf-classification: {DONE}", f"birds-fail: {FAILED}", f"patent-ask: {FAILED}"], "")
    assert (done.returncode, done.stdout.splitlines(), done.stderr) == want


def test_exits_zero_when_every_competition_is_done(box):
    done = box.run("leaf-classification", "mlsp-2013-birds")
    assert done.returncode == 0


def test_the_tool_prepares_into_the_line_s_cache(box):
    box.run("leaf-classification")
    assert (box.home / "mle-cache" / "prepared" / "leaf-classification" / "prepared" / "private").is_dir()


def test_says_no_room_and_does_not_start_the_tool_under_the_disk_floor(tmp_path):
    box = Box(tmp_path, free=FLOOR - 1)
    done = box.run("leaf-classification")
    assert (done.returncode, done.stdout.splitlines(), box.calls()) == (1, [f"leaf-classification: {NO_ROOM}"], [])


# --- where the key and the account name can go -----------------------------------------------------------------

def test_the_key_and_account_name_appear_nowhere_outside_the_token_directory(box):
    done = box.run("leaf-classification", "birds-fail", "patent-ask")
    assert box.leaks_outside_token_dir(done.stdout, done.stderr) == []


def test_the_tool_s_raw_output_is_kept_in_a_private_file_inside_the_token_directory(box):
    box.run("birds-fail")
    secret = f"{box.username}:{box.key}"
    holders = [p for p in box.token_dir.rglob("*") if p.is_file()
               and {f"stdout {secret}", f"stderr {secret}"} <= set(p.read_text(errors="replace").splitlines())]
    assert [oct(p.stat().st_mode & 0o777) for p in holders] == [oct(0o600)]


def test_every_file_the_tool_leaves_in_the_token_directory_is_private(box):
    box.run("birds-fail")
    assert {oct(p.stat().st_mode & 0o777) for p in box.token_dir.rglob("*") if p.is_file()} == {oct(0o600)}


def test_the_tool_reads_nothing_of_fetch_s_own_input(box):
    box.run("patent-ask", stdin="y\n")
    answered = [p for p in box.token_dir.rglob("*") if p.is_file() and "answered" in p.read_text(errors="replace")]
    assert answered == []


def test_the_tool_runs_in_the_token_directory_with_its_temporary_files_there(box):
    box.run("leaf-classification")
    (report,) = box.reports()
    tmp = Path(report["env"]["TMPDIR"])
    assert (report["cwd"], box.token_dir in tmp.parents or tmp == box.token_dir) == (str(box.token_dir), True)


def test_the_tool_is_given_the_directory_path_and_never_the_key_in_its_environment(box):
    box.run("leaf-classification", KAGGLE_KEY="inherited", KAGGLE_USERNAME="inherited")
    (report,) = box.reports()
    env = report["env"]
    leaked = [k for k, v in env.items() if box.key in v or box.username in v]
    assert (env["KAGGLE_CONFIG_DIR"], "KAGGLE_KEY" in env, "KAGGLE_USERNAME" in env, leaked) == (
        str(box.token_dir), False, False, [])


def test_the_tool_s_arguments_are_the_slug_and_the_data_directory_only(box):
    box.run("leaf-classification")
    (report,) = box.reports()
    data = str(box.home / "mle-cache" / "prepared")
    assert report["argv"] == ["prepare", "-c", "leaf-classification", "--data-dir", data]


def test_the_tool_cannot_write_a_core_dump_even_when_fetch_may(box):
    box.run("leaf-classification", prefix=("/usr/bin/prlimit", "--core=unlimited"))
    assert [r["core"] for r in box.reports()] == [0]


def test_stopping_fetch_stops_the_tool_it_started(box):
    proc = subprocess.Popen([str(FETCH), "leaf-hang"], cwd=box.work, env=box.env(), stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pid_file, deadline = box.bin / "hang.pid", time.monotonic() + 30
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    tool = int(pid_file.read_text())
    proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=10)
    deadline = time.monotonic() + 10
    while Path(f"/proc/{tool}").exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    alive = Path(f"/proc/{tool}").exists()
    if alive:
        os.kill(tool, signal.SIGKILL)  # leave no stand-in behind when the test fails
    assert alive is False


def _run_on_a_terminal(box: Box, *slugs: str) -> tuple[int, bytes]:
    """fetch.sh with a pseudo-terminal as its controlling terminal (`setsid --ctty`) and its standard streams, as
    in a pane. Returns the exit code and everything the terminal showed."""
    master, slave = os.openpty()
    proc = subprocess.Popen(["/usr/bin/setsid", "--ctty", str(FETCH), *slugs], cwd=box.work, env=box.env(),
                            stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)
    shown, deadline = b"", time.monotonic() + 60
    while time.monotonic() < deadline:
        if select.select([master], [], [], 1)[0]:
            try:
                chunk = os.read(master, 4096)
            except OSError:  # EIO: every holder of the terminal has closed it
                break
            if not chunk:
                break
            shown += chunk
    else:
        proc.kill()
    os.close(master)
    return proc.wait(timeout=10), shown


def test_on_a_terminal_the_pane_shows_only_the_fixed_lines(box):
    code, shown = _run_on_a_terminal(box, "leaf-classification", "birds-fail", "patent-ask")
    want = [f"leaf-classification: {DONE}", f"birds-fail: {FAILED}", f"patent-ask: {FAILED}"]
    assert (code, shown.decode().splitlines()) == (1, want)


def test_on_a_terminal_the_tool_can_neither_read_nor_open_it(box):
    _run_on_a_terminal(box, "patent-ask")
    assert [(r["stdin_tty"], r["dev_tty"]) for r in box.reports()] == [(False, False)]
