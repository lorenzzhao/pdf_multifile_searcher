# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""Shared helpers of the packaging scripts: pinned versions and verified downloads."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any

PACKAGING = Path(__file__).resolve().parent
ROOT = PACKAGING.parent


def load_pins() -> dict[str, Any]:
    with (PACKAGING / "pins.json").open(encoding="utf-8") as fh:
        pins: dict[str, Any] = json.load(fh)
    return pins


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, sha256: str, target: Path) -> Path:
    """Download `url` to `target` unless a file with the right checksum is already there.
    Raises SystemExit if the checksum does not match."""
    if target.exists() and sha256_of(target) == sha256:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "pdf-multifile-searcher-build"})
    with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as fh:
        while chunk := response.read(1 << 20):
            fh.write(chunk)
    actual = sha256_of(partial)
    if actual != sha256:
        partial.unlink()
        raise SystemExit(f"Checksum mismatch for {url}: expected {sha256}, got {actual}")
    partial.replace(target)
    return target
