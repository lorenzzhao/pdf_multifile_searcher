# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""Render the app icon (SVG) to the PNG and ICO files used by the packages.

Usage:  QT_QPA_PLATFORM=offscreen python packaging/render_icons.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]
SVG = ROOT / "src" / "pdf_multifile_searcher" / "resources" / "app-icon.svg"
OUT = ROOT / "packaging" / "icons"
SIZES = (16, 24, 32, 48, 64, 128, 256, 512)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def render(renderer: QSvgRenderer, size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return image


def write_ico(images: list[QImage], path: Path) -> None:
    """Write a multi-resolution ICO with PNG-compressed entries (Vista and later)."""
    import struct

    from PySide6.QtCore import QBuffer, QIODevice

    blobs = []
    for image in images:
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        blobs.append(bytes(buffer.data().data()))
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    for image, blob in zip(images, blobs, strict=True):
        size = image.width()
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    path.write_bytes(header + entries + b"".join(blobs))


def main() -> int:
    QGuiApplication(sys.argv[:1])
    renderer = QSvgRenderer(QByteArray(SVG.read_bytes()))
    if not renderer.isValid():
        print(f"Invalid SVG: {SVG}")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    images = {size: render(renderer, size) for size in SIZES}
    for size, image in images.items():
        image.save(str(OUT / f"app-icon-{size}.png"))
    write_ico([images[s] for s in ICO_SIZES], OUT / "app-icon.ico")
    print(f"Wrote icons to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
