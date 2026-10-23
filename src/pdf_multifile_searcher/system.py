# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""Hand-off to the operating system: external PDF viewer and file manager (FR-RES-14)."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger(__name__)

# Known Linux PDF viewers that accept a start page, keyed by a fragment of their
# desktop-file ID. Each entry is (executable, argument builder taking path and 1-based page).
_PAGE_AWARE_VIEWERS: list[tuple[str, str, Callable[[str, int], list[str]]]] = [
    ("evince", "evince", lambda p, n: [f"--page-index={n}", p]),
    ("atril", "atril", lambda p, n: [f"--page-index={n}", p]),
    ("xreader", "xreader", lambda p, n: [f"--page-index={n}", p]),
    ("okular", "okular", lambda p, n: ["-p", str(n), p]),
    ("zathura", "zathura", lambda p, n: ["-P", str(n), p]),
    ("qpdfview", "qpdfview", lambda p, n: [f"{p}#{n}"]),
    ("firefox", "firefox", lambda p, n: [f"{Path(p).as_uri()}#page={n}"]),
    ("chromium", "chromium", lambda p, n: [f"{Path(p).as_uri()}#page={n}"]),
    ("google-chrome", "google-chrome", lambda p, n: [f"{Path(p).as_uri()}#page={n}"]),
]


def _spawn(args: list[str]) -> bool:
    try:
        subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except OSError as exc:
        log.warning("Could not start %s: %s", args[0], exc)
        return False


def _default_linux_pdf_app() -> str:
    try:
        result = subprocess.run(
            ["xdg-mime", "query", "default", "application/pdf"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        return result.stdout.strip().lower()
    except (OSError, subprocess.SubprocessError):
        return ""


def open_pdf_external(path: str, page_number: int = 1) -> bool:
    """Open `path` in the system PDF viewer, at `page_number` (1-based) if the viewer
    supports it. Returns True if the page could be passed on, False if it opens at page 1
    (or not at all)."""
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
        return False
    if sys.platform == "darwin":
        _spawn(["open", path])
        return False
    if page_number > 1:
        desktop_id = _default_linux_pdf_app()
        for fragment, exe, build in _PAGE_AWARE_VIEWERS:
            if fragment in desktop_id:
                exe_path = shutil.which(exe)
                if exe_path and _spawn([exe_path, *build(path, page_number)]):
                    return True
                break
    _spawn(["xdg-open", path])
    return page_number <= 1


def show_in_file_manager(path: str) -> None:
    """Show the file selected in the system file manager, or open its folder."""
    if sys.platform.startswith("win"):
        _spawn(["explorer", "/select,", os.path.normpath(path)])
        return
    if sys.platform == "darwin":
        _spawn(["open", "-R", path])
        return
    if shutil.which("dbus-send"):
        try:
            result = subprocess.run(
                [
                    "dbus-send",
                    "--session",
                    "--print-reply",
                    "--dest=org.freedesktop.FileManager1",
                    "--type=method_call",
                    "/org/freedesktop/FileManager1",
                    "org.freedesktop.FileManager1.ShowItems",
                    f"array:string:{Path(path).as_uri()}",
                    "string:",
                ],
                capture_output=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                return
        except (OSError, subprocess.SubprocessError) as exc:
            log.info("File manager D-Bus call failed: %s", exc)
    _spawn(["xdg-open", str(Path(path).parent)])
