# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
# PyInstaller build specification: one folder with two programs,
#   pdf-multifile-searcher   the window program (no console window on Windows)
#   pdf-multifile-search     the command-line program
# Build with:  pyinstaller packaging/pdf-multifile-searcher.spec --noconfirm
#
# Folder mode (not one-file) keeps the Qt libraries as separate, replaceable shared
# libraries, as the LGPL-3.0 requires (see THIRD_PARTY_NOTICES.txt, section 5).
# ruff: noqa
import sys
from importlib import metadata
from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src"
PACKAGING = ROOT / "packaging"
ICON = PACKAGING / "icons" / "app-icon.ico"


def license_files(distribution: str, target: str) -> list[tuple[str, str]]:
    """License files of an installed distribution, keeping their folder layout."""
    dist = metadata.distribution(distribution)
    result = []
    for file in dist.files or []:
        parts = Path(str(file)).parts
        if "licenses" not in parts:
            continue
        sub = Path(*parts[parts.index("licenses") + 1 : -1])
        result.append((str(dist.locate_file(file)), str(Path("licenses") / target / sub)))
    if not result:
        raise SystemExit(f"No license files found for {distribution}")
    return result


datas = [
    (str(SRC / "pdf_multifile_searcher" / "resources"), "pdf_multifile_searcher/resources"),
    (str(ROOT / "LICENSE"), "licenses"),
    (str(ROOT / "THIRD_PARTY_NOTICES.txt"), "licenses"),
    (str(PACKAGING / "licenses" / "GPL-3.0.txt"), "licenses"),
    (str(PACKAGING / "licenses" / "LGPL-3.0.txt"), "licenses"),
    (str(PACKAGING / "licenses" / "QT_THIRD_PARTY_NOTICES.txt"), "licenses"),
]
datas += license_files("pypdfium2", "pypdfium2")
datas += license_files("platformdirs", "platformdirs")
datas += copy_metadata("pdf-multifile-searcher")  # version and license lookup at runtime

# Qt and Python modules the program never uses.
excludes = [
    "tkinter",
    "unittest",
    "pydoc",
    "PySide6.QtNetwork",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQuickControls2",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPrintSupport",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtXml",
    "PySide6.QtConcurrent",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtUiTools",
    "PySide6.QtSvgWidgets",
]


# Qt plugins, libraries and data the program does not need. Some plugins would pull in
# large libraries (Qt Quick/QML via the virtual keyboard, Qt PDF via the PDF image
# plugin, the build machine's GTK via the GTK theme plugin).
import re

PRUNE = re.compile(
    r"""PySide6/(Qt/)?(              # Linux: PySide6/Qt/...  Windows: PySide6/...
        translations/
      | plugins/(
            egldeviceintegrations/
          | platforminputcontexts/\w*qtvirtualkeyboard
          | imageformats/\w*q(pdf|tiff|webp|icns|tga|wbmp)\b
          | platformthemes/\w*qgtk3
          | platforms/\w*q(eglfs|linuxfb|vnc|vkkhrdisplay|minimalegl|direct2d)\b
        )
      | ((lib|bin)/)?(lib)?Qt6(Qml|QmlModels|QmlMeta|QmlWorkerScript|Quick|Pdf|VirtualKeyboard
            |Network|EglFSDeviceIntegration|EglFsKmsSupport|EglFsKmsGbmSupport|OpenGLWidgets)\b
    )""",
    re.X | re.I,
)


def _norm(name: str) -> str:
    return name.replace("\\", "/")


def _is_root(dest: str) -> bool:
    """Binaries loaded directly: Python extensions, Qt plugins, libpython, PDFium."""
    name = _norm(dest).lower()
    base = name.rsplit("/", 1)[-1]
    return (
        base.endswith((".pyd", ".abi3.so"))
        or ".cpython-" in base
        or "/lib-dynload/" in name
        or "/plugins/" in name
        or base.startswith(("libpython", "python3"))
        or name.startswith("pypdfium2_raw/")
    )


# Linux libraries that every desktop provides and that must match the host system
# (following the AppImage project's exclude list); bundling old copies breaks fonts and
# display connections on newer systems.
HOST_LIBS = re.compile(
    r"^lib(fontconfig|freetype|X11|X11-xcb|xcb|dbus-1|GL|EGL|GLX|GLdispatch|OpenGL|drm|gbm"
    r"|wayland-client|wayland-cursor|wayland-egl)\.so(\.\d+)*$"
)


def prune(toc: list) -> list:
    """Drop unwanted Qt parts, then every shared library nothing remaining depends on."""
    from PyInstaller.depend import bindepend

    toc = [entry for entry in toc if not PRUNE.search(_norm(entry[0]))]
    binaries = [e for e in toc if e[2] in ("BINARY", "EXTENSION")]
    by_base: dict[str, list] = {}
    for entry in binaries:
        by_base.setdefault(_norm(entry[0]).rsplit("/", 1)[-1].lower(), []).append(entry)
    keep: set[str] = set()
    todo = [e for e in binaries if _is_root(e[0])]
    while todo:
        entry = todo.pop()
        base = _norm(entry[0]).rsplit("/", 1)[-1].lower()
        if base in keep:
            continue
        keep.add(base)
        try:
            imports = bindepend.get_imports(entry[1])
        except Exception:
            imports = []
        for item in imports:
            name = (item[0] if isinstance(item, tuple) else item).rsplit("/", 1)[-1].lower()
            name = name.rsplit("\\", 1)[-1]
            todo.extend(by_base.get(name, []))
    result = []
    for entry in toc:
        base = _norm(entry[0]).rsplit("/", 1)[-1].lower()
        if entry[2] in ("BINARY", "EXTENSION") and base not in keep:
            continue
        if sys.platform.startswith("linux") and HOST_LIBS.match(_norm(entry[0])):
            continue  # provided by the host system
        if entry[2] == "SYMLINK" and re.search(r"\.(so(\.\d+)*|dll)$", base) and base not in keep:
            continue  # link to a library that was dropped
        result.append(entry)
    return result


def analysis(script: str) -> Analysis:
    result = Analysis(
        [str(PACKAGING / script)],
        pathex=[str(SRC)],
        datas=datas,
        hiddenimports=[],
        excludes=excludes,
        noarchive=False,
    )
    result.binaries = prune(result.binaries)
    present = {_norm(e[0]) for e in result.binaries}

    def wanted(entry: tuple) -> bool:
        if PRUNE.search(_norm(entry[0])):
            return False
        # A symlink to a library that was dropped would be left dangling.
        return entry[2] != "SYMLINK" or _norm(entry[1]) in present or "/" not in _norm(entry[1])

    result.datas = [e for e in result.datas if wanted(e)]
    return result


gui = analysis("entry_gui.py")
cli = analysis("entry_cli.py")

gui_exe = EXE(
    PYZ(gui.pure),
    gui.scripts,
    [],
    exclude_binaries=True,
    name="pdf-multifile-searcher",
    console=False,
    icon=str(ICON),
    upx=False,
)
cli_exe = EXE(
    PYZ(cli.pure),
    cli.scripts,
    [],
    exclude_binaries=True,
    name="pdf-multifile-search",
    console=True,
    icon=str(ICON),
    upx=False,
)

COLLECT(
    gui_exe,
    gui.binaries,
    gui.datas,
    cli_exe,
    cli.binaries,
    cli.datas,
    strip=False,
    upx=False,
    name="pdf-multifile-searcher",
)
