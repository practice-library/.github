"""Tests of the CI tooling. Importing this package puts tooling/ on sys.path, as the launcher does."""
import os
import sys

TOOLING = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(TOOLING)
if TOOLING not in sys.path:
    sys.path.insert(0, TOOLING)
