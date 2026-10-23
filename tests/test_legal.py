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
    assert legal.QT_COPYRIGHT in text


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
    assert dialog.licenses_button.isEnabled()
    assert [title for title, _ in dialog.documents] == [legal.LICENSE_FILE, legal.NOTICES_FILE]


def test_licenses_dialog_lists_bundle_folder(qtbot, tmp_path, monkeypatch) -> None:
    from pdf_multifile_searcher.gui.dialogs import LicensesDialog

    folder = tmp_path / "licenses"
    (folder / "qt").mkdir(parents=True)
    (folder / "LICENSE").write_text("agpl")
    (folder / "qt" / "QT_THIRD_PARTY_NOTICES.txt").write_text("qt notices")
    monkeypatch.setattr(legal, "bundled_license_folder", lambda: folder)
    documents = legal.license_documents()
    assert [title for title, _ in documents] == ["LICENSE", "qt/QT_THIRD_PARTY_NOTICES.txt"]
    dialog = LicensesDialog(documents)
    qtbot.addWidget(dialog)
    dialog.list.setCurrentRow(1)
    assert dialog.view.toPlainText() == "qt notices"
