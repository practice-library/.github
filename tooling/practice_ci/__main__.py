"""Subcommand dispatch: python3 -I scripts/practice-ci <command> [args...].

A command is a module of this package named after it (dashes become underscores) that defines
run(args) -> result.Result. The result is printed as one JSON line and sets the exit code.
The guards of cli.GUARDS (denylist, removed-paths, release-note, size) are the exception: each prints
the one plain line the workflow step reads, with its inputs in the environment.
"""
import importlib
import os
import re
import sys

from practice_ci import cli, result

_COMMAND = re.compile(r"^[a-z][a-z0-9-]*$")
_PRIVATE_MODULES = {"config", "result"}


def commands():
    here = os.path.dirname(os.path.abspath(__file__))
    names = (f[:-3] for f in os.listdir(here) if f.endswith(".py") and not f.startswith("_"))
    return sorted([n.replace("_", "-") for n in names if n not in _PRIVATE_MODULES] + list(cli.GUARDS))


def dispatch(argv):
    if not argv:
        return result.error("practice-ci", "usage: practice-ci <command> [args]; commands: " + ", ".join(commands()))
    command, args = argv[0], argv[1:]
    if not _COMMAND.match(command) or command not in commands():
        return result.error("practice-ci", "unknown command %r; commands: %s" % (command, ", ".join(commands())))
    module = importlib.import_module("practice_ci." + command.replace("-", "_"))
    return module.run(args)


def main(argv):
    if argv and argv[0] in cli.GUARDS:
        # The guards print one plain line that the workflow steps read (ok ... / found ...), not a result.
        return cli.main(argv)
    try:
        res = dispatch(argv)
    except (OSError, ValueError, SyntaxError) as exc:
        res = result.error(argv[0] if argv else "practice-ci", str(exc))
    print(res.to_json())
    return res.exit_code()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
