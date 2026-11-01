"""Bootstrap for the practice_ci package; run it only through the practice-ci launcher (python3 -I).

Under -I the interpreter puts neither the working directory nor this file's directory on sys.path, so
this adds exactly one entry, the directory holding this file, and then proves the package it imported
is the one beside it. Anything else (a caller's PYTHONPATH, a practice_ci or json.py in the working
directory) is never consulted.
"""

import os
import sys


def _bootstrap() -> int:
    if not sys.flags.isolated:
        sys.stderr.write("practice-ci: run through the launcher, which starts Python with -I\n")
        return 2
    here = os.path.dirname(os.path.realpath(__file__))
    sys.path.insert(0, here)
    import practice_ci

    package = os.path.dirname(os.path.realpath(practice_ci.__file__))
    if package != os.path.join(here, "practice_ci"):
        sys.stderr.write("practice-ci: practice_ci was not loaded from the tooling checkout: %s\n" % package)
        return 2
    from practice_ci import cli

    return cli.main(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(_bootstrap())
