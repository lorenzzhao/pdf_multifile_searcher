# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""Download the source archives of the LGPL components in the release packages.

The release workflow attaches them to every GitHub release, so the complete source code
of Qt, PySide6 and the AppImage runtime's libfuse is available from the same place as
the packages (see THIRD_PARTY_NOTICES.txt, section 5, and licenses/SOURCES.txt).

Usage:  python packaging/fetch_sources.py DEST
"""

from __future__ import annotations

import sys
from pathlib import Path

from pins import download, load_pins


def main() -> int:
    dest = Path(sys.argv[1]).resolve()
    for source in load_pins()["sources"]:
        path = download(source["url"], source["sha256"], dest / source["name"])
        print(f"{path.name}  ({path.stat().st_size // 1000} kB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
