You are in a directory that holds two files:

- `GUIDE.md`, the documentation of the `orchestrator` workflow tool, which is
  installed (try `orchestrator --help`);
- `line_count.sh`, an existing script: `sh line_count.sh FILE` prints the
  number of lines in FILE.

Write a workflow for this tool. Use only `GUIDE.md` and the tool itself; do
not look for other documentation or for the tool's source code.

Create, in this directory:

- `tally.orc`: module `tally`, workflow `run`, with two inputs: `file`, the
  path of a text file relative to this directory, and `target`, an integer;
- `commands.json`: the command manifest the workflow needs;
- any small scripts your commands use.

The workflow runs in rounds. Each round gets the number of lines in `file` by
running `line_count.sh` through a command of the workflow, and then:

- if that number is at least `target`, the workflow stops;
- otherwise, if it has already appended six lines, it stops;
- otherwise it appends one line (any text) to `file`, through a command, and
  starts the next round.

It returns a record with two integer fields: `lines`, the number of lines
`line_count.sh` reported in the last round, and `rounds`, the number of lines
it appended. The workflow calls no model or provider; it uses commands only.

Example: with a file `notes.txt` of two lines in this directory,

    orchestrator run tally.orc --command-boundaries-file commands.json --input file=notes.txt --input target=5

exits 0, and the run's returned value (`workflow_outputs`) is
`{"lines": 5, "rounds": 3}`.

How your work is checked: this directory is copied to a fresh directory for
each check, with a fresh copy of `line_count.sh`, so refer to files by paths
relative to this directory. The checks run the command above with other files
and targets, compare the returned record, and confirm that `line_count.sh`
was called. You are done when the example works.
