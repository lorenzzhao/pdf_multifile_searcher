# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""Download and unpack the pinned standalone Python used for the release packages.

python-build-standalone links OpenSSL 3, SQLite, libffi, libedit and the other libraries
statically, so the packages contain no system copies of them, and its "full" archive
contains the licence texts of every component (see packaging/collect_licenses.py).

Usage:  python packaging/fetch_python.py linux|windows DEST
Result: DEST/python/install (the interpreter), DEST/python/licenses, DEST/python/PYTHON.json
Needs the "zstandard" package unless the running Python is 3.14 or newer.
"""

from __future__ import annotations

import shutil
import sys
import tarfile
from pathlib import Path

from pins import download, load_pins

KEEP = ("python/install/", "python/licenses/", "python/PYTHON.json")


def zstd_reader(path: Path):  # type: ignore[no-untyped-def]
    try:
        from compression import zstd  # Python 3.14+

        return zstd.open(path, "rb")
    except ImportError:
        import zstandard

        return zstandard.ZstdDecompressor().stream_reader(path.open("rb"))


def main() -> int:
    platform, dest = sys.argv[1], Path(sys.argv[2]).resolve()
    archive = load_pins()["python"]["archives"][platform]
    cached = download(archive["url"], archive["sha256"], dest / "download" / "python.tar.zst")
    target = dest / "python"
    if target.exists():
        shutil.rmtree(target)
    with zstd_reader(cached) as raw, tarfile.open(fileobj=raw, mode="r|") as tar:
        for member in tar:
            if member.name.startswith(KEEP) or member.name in KEEP:
                tar.extract(member, dest, filter="tar")
    exe = target / "install" / ("python.exe" if platform == "windows" else "bin/python3")
    if not exe.exists():
        raise SystemExit(f"Interpreter not found in the archive: {exe}")
    if not (target / "licenses").is_dir():
        raise SystemExit("The archive has no licenses folder")
    print(exe)
    return 0


if __name__ == "__main__":
    sys.exit(main())
