import hashlib
import os
from contextlib import contextmanager
from pathlib import Path

from records import ItemError
from runtime_bootstrap import bootstrap

bootstrap()

from tj_work_items.request_journal import RequestJournal


@contextmanager
def adoption_lock(root):
    root = Path(root).resolve()
    directory = RequestJournal(root).root.parent / "adoptions"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (
        hashlib.sha256(os.path.normcase(str(root)).encode("utf-8")).hexdigest()
        + ".lock"
    )
    with path.open("a+b") as handle:
        if handle.seek(0, 2) == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ItemError(
                "repository adoption is already running; retry after its "
                "writer finishes"
            ) from error
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
