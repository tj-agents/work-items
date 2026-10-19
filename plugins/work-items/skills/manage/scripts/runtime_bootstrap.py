import sys
from pathlib import Path


def bootstrap() -> None:
    runtime = Path(__file__).resolve().parents[1] / "runtime" / "src"
    value = str(runtime)
    if value not in sys.path:
        sys.path.insert(0, value)


bootstrap()
