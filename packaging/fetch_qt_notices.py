# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""Collect the third-party license notices of the Qt modules shipped in the binaries.

The PySide6 wheels contain no license notices for the third-party code inside Qt, but a
binary bundle has to include them (see THIRD_PARTY_NOTICES.txt, section 5). This script
downloads Qt's attribution pages for the bundled modules and writes them as one text file.

Usage:  python packaging/fetch_qt_notices.py [output-file]
"""

from __future__ import annotations

import html
import re
import sys
import urllib.request
from pathlib import Path

BASE = "https://doc.qt.io/qt-6/"
INDEX = BASE + "licenses-used-in-qt.html"
# Qt modules contained in the bundle (QtWidgets and QtSvg have no third-party code).
MODULES = ("Qt Core", "Qt D-Bus", "Qt GUI")
DEFAULT_OUTPUT = Path(__file__).parent / "licenses" / "QT_THIRD_PARTY_NOTICES.txt"


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "pdf-multifile-searcher-build"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return str(response.read().decode("utf-8"))


def to_text(fragment: str) -> str:
    fragment = re.sub(r"<(br|/p|/h\d|/li|/pre|/div|/tr)[^>]*>", "\n", fragment, flags=re.I)
    fragment = re.sub(r"<li[^>]*>", "  - ", fragment, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "", fragment))
    lines = [line.rstrip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def main_content(page: str) -> str:
    """The attribution text of a Qt documentation page, without navigation."""
    start = re.search(r"<h1[^>]*>", page)
    page = page[start.start() :] if start else page
    end = re.search(r'<div class="footer|<footer|<!-- @@@|</article>', page)
    return page[: end.start()] if end else page


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    index = fetch(INDEX)
    title = re.search(r"<title>(.*?)</title>", index)
    version = title.group(1).split("|")[-1].strip() if title else "Qt 6"
    parts = re.split(r"(<h[23][^>]*>.*?</h[23]>)", index, flags=re.S)
    sections: list[str] = []
    count = 0
    for i in range(1, len(parts), 2):
        heading = to_text(parts[i])
        if heading not in MODULES:
            continue
        links = dict.fromkeys(
            re.findall(r'href="([a-z0-9-]+-attribution-[^"#]+\.html)', parts[i + 1])
        )
        sections.append(f"\n{'=' * 78}\n{heading}\n{'=' * 78}\n")
        for link in links:
            sections.append(to_text(main_content(fetch(BASE + link))))
            sections.append("\n" + "-" * 78 + "\n")
            count += 1
    header = (
        "Third-party code in the Qt libraries shipped with PDF Multifile Searcher\n"
        f"({', '.join(MODULES)}; {version}).\n\n"
        f"Collected from {INDEX} by packaging/fetch_qt_notices.py.\n"
        "Some entries apply only to other platforms; they are kept for completeness.\n"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(header + "\n".join(sections) + "\n", encoding="utf-8")
    print(f"Wrote {count} notices to {output}")
    return 0 if count else 1


if __name__ == "__main__":
    sys.exit(main())
