"""Command line: ``<guard id> `` runs that guard with its inputs from the environment and prints one line."""
import os
import sys

from practice_ci.guards import denylist, release_note, removed_paths, size

GUARDS = {
    "denylist": denylist.run,
    "removed-paths": removed_paths.run,
    "release-note": release_note.run,
    "size": size.run,
}


def main(argv, env=None):
    if len(argv) != 1 or argv[0] not in GUARDS:
        sys.stderr.write("usage: practice-ci <%s>\n" % "|".join(GUARDS))
        return 2
    line = GUARDS[argv[0]](os.environ if env is None else env)
    sys.stdout.buffer.write((line + "\n").encode("utf-8", "surrogateescape"))
    return 0
