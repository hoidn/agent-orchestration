"""The agent-side format check (family plan, decision M3): it replaces the benchmark's format server, which grades a
submission against the answers. This one compares a submission with the public sample submission only, so it can
sit in the agent's image, where no answer is. It refuses only what no grader accepts: a file that cannot be read as
a table, a missing, an extra or a duplicated column (by name; the order does not matter), and missing, extra or
duplicated ids
(the sample's first column, counted as often as the sample has it). Empty values are a note, not a problem: some
graders take an empty cell as "no prediction", and one competition's own sample is all empty. A leading byte-order
mark and blank lines are accepted, as pandas reads them. A submission it accepts can still be refused by the grader.

Usage: python /home/validate_submission.py <submission.csv> [<sample submission>]
  The sample defaults to /home/data/sample_submission.csv, the public copy in the agent's image.
Output: one line per problem, "<code>: <detail>" (no-file, unreadable, empty-file, missing-column, extra-column,
duplicate-column, ragged-row: more fields than the header, missing-id, extra-id, duplicate-id); one line per
note, "note: <code>: <detail>" (empty-value); and "ok: ..." when there is no problem. Exit 0 when there is no problem (notes or not), 1
when there is one, 2 on a usage error or an unreadable sample (on standard error).
Standard library only; it opens the two files it is given and nothing else.
"""

import csv
import sys
from collections import Counter
from pathlib import Path

SAMPLE = Path("/home/data/sample_submission.csv")
SHOWN = 5  # examples printed per problem


def read(path):
    """(header, [(line number, row)]) of a CSV file, a byte-order mark and blank lines skipped as pandas skips them;
    header is None for an empty file."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        return header, [(reader.line_num, row) for row in reader if row]


def _some(items):
    """The first SHOWN items, and how many more."""
    items = list(items)
    more = f" and {len(items) - SHOWN} more" if len(items) > SHOWN else ""
    return ", ".join(map(str, items[:SHOWN])) + more


def column_problems(expected, header):
    """Columns compared by name as counted multisets: a name missing, one not in the sample, one repeated."""
    want, got = Counter(expected), Counter(header)
    found = (("missing-column", [c for c in want if c not in got]), ("extra-column", [c for c in got if c not in want]),
             ("duplicate-column", [c for c in got if c in want and got[c] > want[c]]))
    return [f"{code}: {_some(names)}" for code, names in found if names]


def id_problems(expected, got):
    """Ids compared as counted multisets, so a sample with repeated ids is matched as it is."""
    missing = [i for i in expected if i not in got]
    extra = [i for i in got if i not in expected]
    duplicated = [i for i in got if i in expected and got[i] > expected[i]]
    found = (("missing-id", missing), ("extra-id", extra), ("duplicate-id", duplicated))
    return [f"{code}: {len(ids)} ({_some(ids)})" for code, ids in found if ids]


def row_checks(width, rows):
    """(problems, notes): rows with more fields than the header, which pandas cannot read as a table; and empty
    values, a short row's missing cells included, as a note."""
    ragged = [n for n, row in rows if len(row) > width]
    empty = [f"line {n} column {k + 1}" for n, row in rows for k in range(width) if k >= len(row) or not row[k].strip()]
    found = [f"ragged-row: {len(ragged)} rows with more than {width} fields (lines {_some(ragged)})"] if ragged else []
    return found, ([f"note: empty-value: {len(empty)} ({_some(empty)})"] if empty else [])


def problems(submission, sample_header, sample_rows):
    """(problems, notes) of the submission against the sample."""
    if not submission.is_file():
        return [f"no-file: {submission}"], []
    try:
        header, rows = read(submission)
    except (OSError, UnicodeDecodeError, csv.Error) as e:  # the agent's file, not the check, is at fault
        return [f"unreadable: {e}"], []
    if header is None:
        return ["empty-file: no header and no rows"], []
    found, notes = row_checks(len(header), rows)
    found = column_problems(sample_header, header) + found
    if sample_header[0] in header:
        k = header.index(sample_header[0])
        got = Counter(row[k] for _, row in rows if len(row) > k)
        found += id_problems(Counter(row[0] for _, row in sample_rows), got)
    return found, notes


def main(argv):
    if len(argv) not in (2, 3):
        print(f"usage: {argv[0]} <submission.csv> [<sample submission>]", file=sys.stderr)
        return 2
    sample = Path(argv[2]) if len(argv) == 3 else SAMPLE
    try:
        sample_header, sample_rows = read(sample)
    except (OSError, UnicodeDecodeError, csv.Error) as e:
        print(f"cannot read the sample submission {sample}: {e}", file=sys.stderr)
        return 2
    if not sample_header:
        print(f"the sample submission {sample} is empty", file=sys.stderr)
        return 2
    found, notes = problems(Path(argv[1]), sample_header, sample_rows)
    verdict = [] if found else [f"ok: {len(sample_rows)} rows, columns {', '.join(sample_header)}"]
    print("\n".join(found + notes + verdict))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
