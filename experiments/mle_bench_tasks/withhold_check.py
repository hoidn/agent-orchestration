"""The withholding check on a built agent image (MLE-bench family plan, decision M3 and Task 3).

Run on the agent image's exported file system before any attempt; the result names the image by its digest, and a
paid attempt may start only on an image whose result is a pass. Inputs: the export (a directory, or a tar archive
read as a stream, never unpacked to disk), and the competition's private directory, grading-code directory (the
benchmark's competition directory: grade.py, config.yaml, prepare.py, leaderboard.csv), leaderboard snapshot and
public directory.

What is a hit (each a kind of finding in the result):
  private_hash, grader_hash, leaderboard_hash: a file whose SHA-256 equals that of a private file, a grading-code
      file or the leaderboard snapshot, under any name and at any depth. A source file byte-identical to a public
      file (the competition's description.md) is no target: the agent is given it.
  private_lines: a file holding at least one private-only line. A private-only line is a line of a private text
      file, other than its first line (the header) and blank lines, that occurs in no public text file. Lines are
      compared with surrounding whitespace stripped (so CRLF and LF match); a file's count is the number of
      distinct such lines it holds, per private file. A line that also occurs in a public file is never a hit.
  benchmark: a path component named for the benchmark's package (`mlebench`, `mlebench-<...>`, `mlebench.<...>`,
      `__editable__.mlebench...`) or for the competition id (config.yaml's `id`), as a directory, a file or an
      archive (`<id>.tar.gz`). A file equal by hash to a competition-directory file is a grader_hash.
Fail closed (each fails the check, with the path named):
  unreadable: a path that cannot be read, a special file (fifo, device, socket), a tar member that cannot be
      extracted, a corrupt archive, a hard link to a member not earlier in the tar.
  not_inspected: an archive over the read cap or inside another archive; a file over the read cap whose suffix
      marks a type that could hold the answers (ANSWER_TYPES).
  links_outside: a symbolic link whose target climbs above the export's root (absolute targets are read inside
      the image, as the container sees them). No symbolic link is followed.
An export with no regular file fails too.

Caps, and why (real images are several gigabytes with a deep-learning stack):
  READ_CAP (64 MiB): a file up to this size is read whole, once, for its hash, its lines and, if an archive, its
      members; a larger one is hashed in 1 MiB chunks. Peak memory is one such file plus the private-only lines.
  TEXT_PROBE (8 KiB): a file is text when its first 8 KiB hold no NUL byte (git's rule); only text files enter
      the line check, on both the input and the export side.
  Archives (ARCHIVES suffixes) up to READ_CAP are opened one level deep, their members checked as files.
A file byte-identical to a public file is public content and is not opened further (a public archive copied
unchanged into the image may exceed the cap).

What this cannot see: answers re-encoded (another delimiter, number format, encoding such as UTF-16, a binary
format such as parquet or pickle, compression other than the listed suffixes), split across files or lines
differently, partly altered rows, values only (without their row), or anything learned into model weights.
Memory grows with the private text files' size; time grows with the decompressed size of archive members.

Usage: python -m experiments.mle_bench_tasks.withhold_check --image-ref R --export PATH --private DIR \\
           --grader DIR --leaderboard FILE --public DIR --out result.json
       Exit 0: pass; 1: fail (the result is written either way); 2: refused (bad inputs; nothing written).
"""

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import stat
import sys
import tarfile
import zipfile
import zlib
from pathlib import Path

from experiments.mle_bench_tasks.wrap import PINNED

READ_CAP = 64 << 20
TEXT_PROBE = 8192
CHUNK = 1 << 20
ANSWER_TYPES = (".csv", ".tsv", ".json", ".jsonl", ".parquet", ".txt")
ARCHIVES = (".tar.gz", ".tgz", ".tar", ".zip", ".gz")
KINDS = ("private_hash", "grader_hash", "leaderboard_hash", "private_lines", "benchmark", "not_inspected",
         "unreadable", "links_outside")
PACKAGE = re.compile(r"(__editable__[._-])?mlebench([-_.].*)?")
# zipfile raises RuntimeError for an encrypted member and NotImplementedError for an unknown compression
BROKEN = (OSError, EOFError, zlib.error, tarfile.TarError, zipfile.BadZipFile, RuntimeError, NotImplementedError)


class Refused(Exception):
    """An input the check cannot run on: an unpinned reference, a missing input, a link inside an input tree."""


def _input_files(root):
    """(posix relative path, path) of every file under an input directory; a link or special file is refused."""
    for path in sorted(Path(root).rglob("*")):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise Refused(f"{path}: not a plain file or directory in an input tree")
        if path.is_file():
            yield path.relative_to(root).as_posix(), path


def _sha(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _is_text(head):
    return b"\x00" not in head[:TEXT_PROBE]


def _text_lines(path, skip_header):
    """The stripped non-blank lines of a text file (none for a binary file)."""
    with open(path, "rb") as fh:
        if not _is_text(fh.read(TEXT_PROBE)):
            return
        fh.seek(0)
        if skip_header:
            next(fh, None)
        for line in fh:
            if line := line.strip():
                yield line


def _competition_id(grader):
    config = Path(grader) / "config.yaml"
    found = config.is_file() and re.search(r"(?m)^id:\s*(\S+)", config.read_text())
    return found.group(1) if found else Path(grader).name


def targets(private, grader, leaderboard, public):
    """What the export is searched for: {sha: [(kind, source)]}, public shas, {private-only line: {source}}, id."""
    public_files = list(_input_files(public))
    public_shas = {_sha(path) for _, path in public_files}
    hashes = {}
    sources = [("private_hash", rel, path) for rel, path in _input_files(private)]
    sources += [("grader_hash", rel, path) for rel, path in _input_files(grader)]
    sources.append(("leaderboard_hash", Path(leaderboard).name, Path(leaderboard)))
    for kind, rel, path in sources:
        hashes.setdefault(_sha(path), []).append((kind, rel))
    for sha in public_shas:
        hashes.pop(sha, None)
    lines = {}
    for rel, path in _input_files(private):
        for line in _text_lines(path, skip_header=True):
            lines.setdefault(line, set()).add(rel)
    for _, path in public_files:
        for line in _text_lines(path, skip_header=False):
            lines.pop(line, None)
    return {"hashes": hashes, "public": public_shas, "lines": lines, "id": _competition_id(grader).lower()}


def _norm(name):
    """A tar or zip member name as a relative posix path ('./etc/x' and '/etc/x' are 'etc/x')."""
    return "/".join(part for part in name.split("/") if part not in ("", "."))


def _leaves(rel, target):
    """True when a link at `rel` with `target` climbs above the root."""
    depth = 0 if target.startswith("/") else rel.count("/")
    for part in target.split("/"):
        depth += {"..": -1, ".": 0, "": 0}.get(part, 1)
        if depth < 0:
            return True
    return False


class _Scan:
    """The findings over one export, built one entry at a time."""

    def __init__(self, found, cap):
        self.t, self.cap = found, cap
        self.findings = {kind: [] for kind in KINDS}
        self.checked, self.seen, self.benchmark = 0, set(), set()

    def add(self, kind, path, **extra):
        self.findings[kind].append({"path": path, **extra})

    def name(self, rel, prefix=""):
        """(c) by name: record the first path component named for the benchmark or the competition."""
        parts = rel.split("/")
        for i, part in enumerate(parts):
            base = part.lower()
            stem = next((base[:-len(s)] for s in ARCHIVES if base.endswith(s)), base)
            if stem == self.t["id"] or PACKAGE.fullmatch(base):
                self.benchmark.add(prefix + "/".join(parts[:i + 1]))
                return

    def link(self, path, rel, target):
        if _leaves(rel, target):
            self.add("links_outside", path, target=target)

    def content(self, path, stream, depth=0):
        """(a), (b) and the archive rule for one regular file's bytes."""
        self.checked += 1
        head = stream.read(self.cap + 1)
        whole = len(head) <= self.cap
        digest = hashlib.sha256(head)
        while not whole and (chunk := stream.read(CHUNK)):
            digest.update(chunk)
        sha = digest.hexdigest()
        if sha in self.t["public"]:
            return
        for kind, source in self.t["hashes"].get(sha, ()):
            self.add(kind, path, source=source)
        if whole and _is_text(head):
            self._lines(path, head)
        base = path.rsplit("/", 1)[-1].lower()
        if base.endswith(ARCHIVES):
            self._archive(path, head if whole else None, depth)
        elif not whole and base.endswith(ANSWER_TYPES):
            self.add("not_inspected", path, reason="over the read cap")

    def _lines(self, path, data):
        counts = {}
        for line in {line.strip() for line in data.split(b"\n")} & self.t["lines"].keys():
            for source in self.t["lines"][line]:
                counts[source] = counts.get(source, 0) + 1
        if counts:
            self.add("private_lines", path, lines=dict(sorted(counts.items())))

    def _archive(self, path, data, depth):
        if data is None or depth:
            self.add("not_inspected", path, reason="archive over the read cap" if data is None else "nested archive")
            return
        try:
            self._members(path, data)
        except BROKEN as exc:
            self.add("unreadable", path, reason=type(exc).__name__)

    def _members(self, path, data):
        prefix, base = path + "!", path.rsplit("/", 1)[-1].lower()
        if base.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for info in zf.infolist():
                    rel = _norm(info.filename)
                    self.name(rel, prefix)
                    if not info.is_dir():
                        with zf.open(info) as fh:
                            self.content(prefix + rel, fh, depth=1)
        elif base.endswith(".gz") and not base.endswith(".tar.gz"):
            rel = path.rsplit("/", 1)[-1][:-3]
            self.name(rel, prefix)
            self.content(prefix + rel, gzip.GzipFile(fileobj=io.BytesIO(data)), depth=1)
        else:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tf:
                self.tar(tf, prefix, depth=1)

    def tar(self, tf, prefix="", depth=0):
        """Every member of an open tar, in order; a member that cannot be read ends the tar (the stream is lost)."""
        for member in tf:
            rel = _norm(member.name)
            path = prefix + rel
            self.name(rel, prefix)
            if not rel or member.isdir():
                continue
            if member.issym():
                self.link(path, rel, member.linkname)
            elif member.islnk():  # its bytes were checked under the target's name
                if prefix + _norm(member.linkname) not in self.seen:
                    self.add("unreadable", path, reason="hard link to a member not earlier in the tar")
            elif not member.isreg():
                self.add("unreadable", path, reason="special file")
            elif not self._tar_file(tf, member, path, depth):
                return

    def _tar_file(self, tf, member, path, depth):
        try:
            self.content(path, tf.extractfile(member), depth)
        except BROKEN as exc:
            self.add("unreadable", path, reason=type(exc).__name__)
            return False
        self.seen.add(path)
        return True

    def directory(self, root):
        errors = []
        for top, dirs, files in os.walk(root, onerror=errors.append):
            dirs.sort()
            for name in sorted(dirs + files):
                full = os.path.join(top, name)
                rel = Path(full).relative_to(root).as_posix()
                try:
                    self._dir_entry(full, rel)
                except OSError as exc:
                    self.add("unreadable", rel, reason=type(exc).__name__)
        for exc in errors:
            self.add("unreadable", Path(exc.filename).relative_to(root).as_posix(), reason=type(exc).__name__)

    def _dir_entry(self, full, rel):
        self.name(rel)
        mode = os.lstat(full).st_mode
        if stat.S_ISLNK(mode):
            self.link(rel, rel, os.readlink(full))
        elif stat.S_ISREG(mode):
            with open(full, "rb") as fh:
                self.content(rel, fh)
        elif not stat.S_ISDIR(mode):
            self.add("unreadable", rel, reason="special file")


def check(export, *, private, grader, leaderboard, public, image_ref, cap=READ_CAP):
    """The result for one image: {image, verdict, files_checked, caps, findings: {kind: [{path, ...}]}}."""
    if not PINNED.fullmatch(image_ref):
        raise Refused(f"{image_ref!r}: the image reference is not pinned by digest (<name>@sha256:<64 hex>)")
    for label, path, ok in (("private", private, os.path.isdir), ("grader", grader, os.path.isdir),
                            ("public", public, os.path.isdir), ("leaderboard", leaderboard, os.path.isfile),
                            ("export", export, os.path.exists)):
        if not ok(path):
            raise Refused(f"{path}: the {label} input is missing or of the wrong kind")
    scan = _Scan(targets(private, grader, leaderboard, public), cap)
    if os.path.isdir(export):
        scan.directory(Path(export))
    else:
        try:
            with tarfile.open(export, mode="r|*") as tf:
                scan.tar(tf)
        except BROKEN as exc:
            scan.add("unreadable", str(export), reason=type(exc).__name__)
    findings = scan.findings | {"benchmark": [{"path": p} for p in sorted(scan.benchmark)]}
    findings = {kind: sorted(items, key=lambda f: json.dumps(f, sort_keys=True)) for kind, items in findings.items()}
    passed = scan.checked > 0 and not any(findings.values())
    return {"image": image_ref, "verdict": "pass" if passed else "fail", "files_checked": scan.checked,
            "caps": {"read_bytes": cap, "text_probe_bytes": TEXT_PROBE, "archive_depth": 1}, "findings": findings}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for flag in ("--image-ref", "--export", "--private", "--grader", "--leaderboard", "--public", "--out"):
        parser.add_argument(flag, required=True)
    args = parser.parse_args(argv)
    try:
        result = check(args.export, private=args.private, grader=args.grader, leaderboard=args.leaderboard,
                       public=args.public, image_ref=args.image_ref)
    except Refused as exc:
        print("refused:", exc, file=sys.stderr)
        return 2
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
    print(result["verdict"], args.image_ref)
    return 0 if result["verdict"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
