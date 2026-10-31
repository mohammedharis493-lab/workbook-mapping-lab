"""Small, read-only content pins for a single checked-copy build.

No locks or background services: reject source changes detected between
validation and output release, even when the same path is reused. Callers
must still enforce their own approval and entity-specific review policies.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable


def _digest(path: str) -> str:
    checksum = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


class BuildInputGuard:
    """Content-based pin for selected files consumed by one build.

    File paths and hashes remain private in memory. Error messages contain no
    client paths. The guard does not promise an OS-level filesystem lock.
    """

    def __init__(self, paths: Iterable[str | Path | None]):
        selected = tuple(dict.fromkeys(str(path) for path in paths if path))
        self._expected = {path: _digest(path) for path in selected}

    def verify(self) -> None:
        try:
            if any(_digest(path) != expected for path, expected in self._expected.items()):
                raise ValueError("BUILD_INPUT_CHANGED: input contents changed before output release")
        except OSError as error:
            raise ValueError("BUILD_INPUT_CHANGED: input missing before output release") from error
