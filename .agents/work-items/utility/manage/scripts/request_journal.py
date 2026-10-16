import json
from pathlib import Path
import subprocess

from records import ItemError


class RequestJournal:
    def __init__(self, root):
        root = Path(root).resolve()
        try:
            result = subprocess.run(["git", "-C", str(root), "rev-parse", "--git-common-dir"],
                                    capture_output=True, text=True, encoding="utf-8", timeout=15, check=False)
        except (OSError, subprocess.SubprocessError) as error:
            raise ItemError("cannot locate repository request receipts") from error
        if result.returncode or not result.stdout.strip():
            raise ItemError("request receipts require a Git source checkout")
        common = Path(result.stdout.strip())
        self.root = (common if common.is_absolute() else root / common).resolve() / "work-items/requests"

    def path(self, key):
        import hashlib
        return self.root / (hashlib.sha256(key.encode("utf-8")).hexdigest() + ".json")

    def read(self, key, fingerprint):
        path = self.path(key)
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ItemError("request receipt is unreadable; reconcile before submission") from error
        if not isinstance(value, dict) or set(value) != {"fingerprint", "resource_id"} or value["fingerprint"] != fingerprint or (value["resource_id"] is not None and (type(value["resource_id"]) is not int or value["resource_id"] <= 0)):
            raise ItemError("request receipt differs or is invalid; reconcile before submission")
        return value

    def reserve(self, key, fingerprint):
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            with self.path(key).open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps({"fingerprint": fingerprint, "resource_id": None}) + "\n")
        except FileExistsError as error:
            raise ItemError("request is already reserved; reconcile without another POST") from error

    def complete(self, key, fingerprint, resource_id):
        self.root.mkdir(parents=True, exist_ok=True)
        if type(resource_id) is not int or resource_id <= 0:
            raise ItemError("request response has no durable identity; reconcile without reposting")
        self.path(key).write_text(json.dumps({"fingerprint": fingerprint, "resource_id": resource_id}) + "\n", encoding="utf-8", newline="\n")
