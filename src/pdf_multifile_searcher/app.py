"""Entry point of the GUI (`pdf-multifile-searcher`)."""

from __future__ import annotations

import multiprocessing
import sys
from collections.abc import Sequence

from pdf_multifile_searcher import APP_ID, APP_NAME, __version__
from pdf_multifile_searcher.cli import build_parser, configure_logging, run_headless


def main(argv: Sequence[str] | None = None) -> int:
    multiprocessing.freeze_support()
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.log_level)
    if args.no_gui:
        return run_headless(args, parser)

    # Qt is imported only for the GUI, so the headless mode works without a display.
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    from pdf_multifile_searcher.config import ConfigStore
    from pdf_multifile_searcher.core.models import SearchOptions
    from pdf_multifile_searcher.gui.icons import icon
    from pdf_multifile_searcher.gui.main_window import MainWindow
    from pdf_multifile_searcher.gui.style import apply_theme, current_theme

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setDesktopFileName(APP_ID)
    apply_theme(app, current_theme())
    app.setWindowIcon(icon("app"))

    store = ConfigStore()
    settings = store.load()
    if args.context_words is not None:
        settings.context_words = max(0, args.context_words)
    if args.no_cache:
        settings.use_cache = False
    if args.include_hidden:
        settings.include_hidden = True

    cli_scopes = list(args.folder) or None
    cli_pattern = args.pattern
    cli_options = None
    if args.case_sensitive or args.whole_word or args.regex:
        cli_options = SearchOptions(args.case_sensitive, args.whole_word, args.regex)
    # A command-line session does not overwrite the saved folders and pattern (FR-CLI-04).
    if cli_scopes or cli_pattern is not None:
        store.persist_session = False

    window = MainWindow(
        store,
        settings,
        cli_scopes=cli_scopes,
        cli_pattern=cli_pattern,
        cli_options=cli_options,
        autostart=bool(cli_scopes and cli_pattern),  # FR-CLI-05
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
