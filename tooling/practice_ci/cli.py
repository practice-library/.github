"""Command line of the practice_ci package; reached only through the practice-ci launcher.

  version [--require-policy-python]        the interpreter and the checkout in use (diagnostic output)
  fragment <name> --root <dir> [--result <file>] [--keep-going]
                                           run one fragment's main in the caller's tree
  approval --root <dir> [--result <file>] [--keep-going]
                                           who added the approval label, judged (label-approval)
  guard denylist --root <dir> [--result <file>]
                                           the denylist guard, inputs from the step's environment
  lint                                     the policy-literals lint over this checkout
  mutants [<name> ...]                     the mutation runner, on an isolated copy of this checkout
"""

import argparse
import os
import platform
import sys
from pathlib import Path

from . import adapter, approval, denylist, fragments, lint, mutants, policy
from .result import ERROR, Result


def _root(text: str) -> Path:
    root = Path(text).resolve()
    if not root.is_dir():
        raise argparse.ArgumentTypeError("no such directory: " + text)
    return root


def _version(args) -> int:
    running = platform.python_version()
    print("practice-ci from %s, python %s (%s)" % (policy.ROOT, running, sys.executable))
    if args.require_policy_python:
        wanted = policy.value("tooling.pythonVersion")
        if running != wanted:
            return adapter.emit(Result(ERROR, "bootstrap.python-version",
                                       "the tooling needs python %s, this is %s" % (wanted, running)))
    return 0


def _fragment(args) -> int:
    result = fragments.run(args.name, args.root)
    return adapter.emit(result, result_file=args.result, keep_going=args.keep_going)


def _approval(args) -> int:
    result = approval.judge(approval.Inputs.from_env(args.root, os.environ))
    return adapter.emit(result, result_file=args.result, keep_going=args.keep_going)


def _guard(args) -> int:
    result = denylist.judge(denylist.Inputs.from_env(args.root, os.environ))
    return adapter.emit(result, result_file=args.result)


def _lint(args) -> int:
    return adapter.emit(lint.run(policy.ROOT))


def _mutants(args) -> int:
    return adapter.emit(mutants.run(policy.ROOT, args.names))


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="practice-ci")
    sub = top.add_subparsers(dest="command", required=True)

    p = sub.add_parser("version")
    p.add_argument("--require-policy-python", action="store_true")
    p.set_defaults(run=_version)

    p = sub.add_parser("fragment")
    p.add_argument("name", choices=sorted(fragments.VOCABULARY))
    p.add_argument("--root", type=_root, required=True)
    p.add_argument("--result")
    p.add_argument("--keep-going", action="store_true")
    p.set_defaults(run=_fragment)

    p = sub.add_parser("approval")
    p.add_argument("--root", type=_root, required=True)
    p.add_argument("--result")
    p.add_argument("--keep-going", action="store_true")
    p.set_defaults(run=_approval)

    p = sub.add_parser("guard")
    p.add_argument("guard", choices=["denylist"])
    p.add_argument("--root", type=_root, required=True)
    p.add_argument("--result")
    p.set_defaults(run=_guard)

    p = sub.add_parser("lint")
    p.set_defaults(run=_lint)

    p = sub.add_parser("mutants")
    p.add_argument("names", nargs="*")
    p.set_defaults(run=_mutants)
    return top


def main(argv: list[str]) -> int:
    args = parser().parse_args(argv)
    try:
        return args.run(args)
    except policy.PolicyError as e:
        return adapter.emit(Result(ERROR, "policy.missing", str(e)))
