# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
# PyInstaller build specification: one folder with two programs,
#   pdf-multifile-searcher   the window program (no console window on Windows)
#   pdf-multifile-search     the command-line program
# Build with:  pyinstaller packaging/pdf-multifile-searcher.spec --noconfirm
#
# Folder mode (not one-file) keeps the Qt libraries as separate, replaceable shared
# libraries, as the LGPL-3.0 requires (see THIRD_PARTY_NOTICES.txt, section 5).
# The "licenses" folder is added afterwards by packaging/collect_licenses.py, which also
# checks that every binary in the result has a known licence.
# ruff: noqa
import sys
from importlib import metadata
from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src"
PACKAGING = ROOT / "packaging"
ICON = PACKAGING / "icons" / "app-icon.ico"


datas = [
    (str(SRC / "pdf_multifile_searcher" / "resources"), "pdf_multifile_searcher/resources"),
]
datas += copy_metadata("pdf-multifile-searcher")  # version and license lookup at runtime


# Qt and Python modules the program never uses.
excludes = [
    "tkinter",
    "unittest",
    "pydoc",
    "readline",
    "curses",
    "dbm",
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
# display connections on newer systems. GLib, the C++ runtime and zlib are on every
# desktop too; leaving them out also keeps their dependencies (GnuTLS and others) out.
HOST_LIBS = re.compile(
    r"^lib(fontconfig|freetype|X11|X11-xcb|xcb|dbus-1|GL|EGL|GLX|GLdispatch|OpenGL|drm|gbm"
    r"|wayland-client|wayland-cursor|wayland-egl|glib-2\.0|gthread-2\.0|gobject-2\.0"
    r"|gmodule-2\.0|gio-2\.0|pcre|pcre2-8|stdc\+\+|gcc_s|z)\.so(\.\d+)*$"
)


# Windows: the Universal C Runtime (ucrtbase.dll and its api-ms-win-* forwarders) is part
# of Windows 10 and 11, the minimum the programs support, so it is not redistributed.
WINDOWS_HOST_LIBS = re.compile(r"^(api-ms-win-[\w-]+|ucrtbase)\.dll$", re.I)


def _is_host_lib(dest: str) -> bool:
    base = _norm(dest).rsplit("/", 1)[-1]
    if sys.platform.startswith("linux"):
        return bool(HOST_LIBS.match(base))
    return sys.platform.startswith("win") and bool(WINDOWS_HOST_LIBS.match(base))


def direct_imports(path: str) -> list[str]:
    """Names of the libraries a binary links directly.

    On Linux, PyInstaller's get_imports() uses ldd, which also lists indirect
    dependencies; then a host library such as GLib could not keep its own dependencies
    out of the bundle. readelf lists only the direct ones (DT_NEEDED).
    """
    if sys.platform.startswith("linux"):
        import subprocess

        out = subprocess.run(
            ["readelf", "-d", path], capture_output=True, text=True, check=False
        ).stdout
        return re.findall(r"\(NEEDED\)\s+Shared library: \[([^\]]+)\]", out)
    from PyInstaller.depend import bindepend

    return [item[0] if isinstance(item, tuple) else item for item in bindepend.get_imports(path)]


def prune(toc: list) -> list:
    """Drop unwanted Qt parts, then every shared library nothing remaining depends on."""
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
        if base in keep or _is_host_lib(entry[0]):
            continue  # host libraries are neither kept nor followed
        keep.add(base)
        try:
            imports = direct_imports(entry[1])
        except Exception:
            imports = []
        for item in imports:
            name = item.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
            todo.extend(by_base.get(name, []))
    result = []
    for entry in toc:
        base = _norm(entry[0]).rsplit("/", 1)[-1].lower()
        if entry[2] in ("BINARY", "EXTENSION") and base not in keep:
            continue
        if _is_host_lib(entry[0]):
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
