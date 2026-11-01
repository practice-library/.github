"""Runs a guard: python3 -I tooling/run_practice_ci.py <guard id>.

-I ignores PYTHONPATH and the current directory (a change under check could plant a module there), so the
tooling directory, next to this file, is the only path added.
TODO: replace by scripts/practice-ci when the core track adds the launcher.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from practice_ci.cli import main  # noqa: E402

sys.exit(main(sys.argv[1:]))
