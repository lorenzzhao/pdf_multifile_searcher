# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""Copyright and license information shown to users (AGPL "Appropriate Legal Notices")."""

from __future__ import annotations

import pytest

from pdf_multifile_searcher import __version__, cli, legal


def test_license_and_notices_are_found() -> None:
    license_text = legal.read_bundled_text(legal.LICENSE_FILE)
    notices = legal.read_bundled_text(legal.NOTICES_FILE)
    assert license_text is not None and "GNU AFFERO GENERAL PUBLIC LICENSE" in license_text
    assert "END OF TERMS AND CONDITIONS" in license_text
    assert notices is not None and "pypdfium2" in notices


def test_unknown_file_returns_none() -> None:
    assert legal.read_bundled_text("NO_SUCH_FILE.txt") is None


def test_version_text() -> None:
    text = legal.version_text("prog", "1.2.3")
    lines = text.splitlines()
    assert lines[0] == "prog 1.2.3"
    assert lines[1] == legal.COPYRIGHT
    assert legal.LICENSE_SPDX in text and legal.SOURCE_URL in text
    assert "NO WARRANTY" in text


def test_cli_version_keeps_line_breaks(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--version"])
    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    assert out.splitlines()[:2] == [f"pdf-multifile-search {__version__}", legal.COPYRIGHT]


def test_about_dialog(qtbot) -> None:
    from pdf_multifile_searcher.gui.dialogs import AboutDialog

    dialog = AboutDialog()
    qtbot.addWidget(dialog)
    assert dialog.license_button.isEnabled()
    assert dialog.notices_button.isEnabled()
