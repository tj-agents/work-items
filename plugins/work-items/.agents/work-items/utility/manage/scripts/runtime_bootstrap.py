"""Expose the shipped runtime package to direct source-checkout scripts."""

from pathlib import Path
import sys


_RUNTIME = Path(__file__).resolve().parents[1] / "runtime" / "src"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))
