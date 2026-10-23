# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""Copyright, license and source information shown to users.

The GUI's About dialog and the command line's ``--version`` use these texts, so users
always see the copyright, the license, the lack of warranty and where to get the source
(the AGPL's "Appropriate Legal Notices"). This module does not import Qt.
"""

from __future__ import annotations

import sys
from importlib import metadata
from pathlib import Path

COPYRIGHT = "Copyright (C) 2025–2026 Lorenz Zhao"
LICENSE_NAME = "GNU Affero General Public License, version 3 or later"
LICENSE_SPDX = "AGPL-3.0-or-later"
LICENSE_URL = "https://www.gnu.org/licenses/agpl-3.0.html"
SOURCE_URL = "https://github.com/lorenzzhao/pdf_multifile_searcher"

NO_WARRANTY = (
    "This program comes with ABSOLUTELY NO WARRANTY. This is free software, and you are "
    "welcome to redistribute it under certain conditions; see the license for details."
)

LICENSE_FILE = "LICENSE"
NOTICES_FILE = "THIRD_PARTY_NOTICES.txt"

_DISTRIBUTION = "pdf-multifile-searcher"
_REPO_ROOT = Path(__file__).resolve().parents[2]


def read_bundled_text(name: str) -> str | None:
    """Return the text of a license file shipped with the program, or None.

    Installed packages carry the files in their metadata, the standalone programs in a
    "licenses" folder, and a source checkout in the repository root.
    """
    try:
        dist = metadata.distribution(_DISTRIBUTION)
        for file in dist.files or []:
            if file.name == name:
                return Path(str(dist.locate_file(file))).read_text(encoding="utf-8")
    except (metadata.PackageNotFoundError, OSError, UnicodeDecodeError):
        pass
    for folder in _fallback_folders():
        try:
            return (folder / name).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    return None


def _fallback_folders() -> list[Path]:
    """Where license files live outside installed package metadata."""
    folders = []
    bundle = getattr(sys, "_MEIPASS", None)  # PyInstaller bundle
    if bundle:
        folders.append(Path(bundle) / "licenses")
    if getattr(sys, "frozen", False):
        folders.append(Path(sys.executable).resolve().parent / "licenses")
    folders.append(_REPO_ROOT)
    return folders


def version_text(program: str, version: str) -> str:
    """Text for ``--version``, following the usual GNU convention."""
    return (
        f"{program} {version}\n"
        f"{COPYRIGHT}\n"
        f"License: {LICENSE_SPDX} <{LICENSE_URL}>\n"
        f"Source code: <{SOURCE_URL}>\n"
        f"{NO_WARRANTY}"
    )
