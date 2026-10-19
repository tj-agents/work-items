from __future__ import annotations

import hashlib
from pathlib import Path


def source_digest() -> str:
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    paths = sorted(
        (
            candidate
            for candidate in root.rglob("*")
            if candidate.is_file() and candidate.suffix in {".py", ".json"}
        ),
        key=lambda candidate: candidate.relative_to(root).as_posix(),
    )
    for path in paths:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()
