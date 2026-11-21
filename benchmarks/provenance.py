"""Run receipts use content hashes. Git text line endings are normalized."""

import hashlib
import json
from pathlib import Path


def digest(path):
    path = Path(path)
    data = path.read_bytes()
    if path.suffix in {".csv", ".md", ".json", ".py"}:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def save_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")
