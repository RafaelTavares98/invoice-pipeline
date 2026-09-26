"""Taking attachments out of the mailbox and onto disk, exactly once.

A run that is interrupted halfway must not download everything again on
the next pass, and must never write the same invoice twice. A manifest
keyed on the message identifier is what makes that true.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

MANIFEST_NAME = "manifest.json"


@dataclass(frozen=True)
class StoredFile:
    """One attachment, now on disk, and the mail it came from."""

    path: Path
    message_id: str
    filename: str


def fetch_new(mailbox, store: Path) -> List[StoredFile]:
    """Store every attachment that has not been stored before.

    Returns only what was new on this pass, so a second run over an
    unchanged mailbox returns nothing at all.
    """
    store.mkdir(parents=True, exist_ok=True)
    manifest = read_manifest(store)
    fresh: List[StoredFile] = []
    for message in mailbox.messages():
        if message.identifier in manifest:
            continue
        stored_names = []
        for filename, payload in message.attachments:
            target = store / f"{message.identifier}__{filename}"
            target.write_bytes(payload)
            stored_names.append(target.name)
            fresh.append(StoredFile(target, message.identifier, filename))
        manifest[message.identifier] = stored_names
    write_manifest(store, manifest)
    return fresh


def read_manifest(store: Path) -> Dict[str, List[str]]:
    """What has already been taken out of the mailbox."""
    path = store / MANIFEST_NAME
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_manifest(store: Path, manifest: Dict[str, List[str]]) -> None:
    """Record what has been taken, so the next run can skip it."""
    (store / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
