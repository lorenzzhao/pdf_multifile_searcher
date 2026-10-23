# Changelog

All notable changes to PDF Multifile Searcher are listed here. Versions follow
[Semantic Versioning](https://semver.org/).

## [2.0.2] - 2026-10-23

### Fixed

- The standalone programs now also contain the notices of the code that Python itself
  incorporates (expat and libmpdec on Windows; HACL*, the Mersenne Twister and others
  on all systems) and the Unicode License for the Unicode data in Python.

## [2.0.1] - 2026-10-23

Corrects the license compliance of the standalone programs. The program itself is
unchanged apart from the About dialog.

### Fixed

- The standalone programs now contain the license texts and notices of every included
  component: Python and the libraries built into it, all bundled Qt modules (including
  Qt SVG and Qt Wayland Client), ICU, PyInstaller's launcher, the Linux system libraries
  and, in the AppImage, the AppImage runtime. Version 2.0.0 missed several of them.
- Every release now has the source code of the included Qt, Qt for Python, AppImage
  runtime and libfuse attached, as their LGPL licenses require.
- The About dialog shows Qt's copyright notice, links the LGPL and GPL, and its
  *Licenses…* window shows every license file of the package.

### Changed

- The standalone programs are built with a self-contained Python 3.12 and pinned
  versions of all components (Qt 6.9.3). The Linux programs no longer include copies of
  OpenSSL 1.1, GNU readline, GLib, GnuTLS and other system libraries; they use the
  system's GLib and C++ runtime instead.

## [2.0.0] - 2026-10-23

A complete rewrite with a new interface, a new PDF engine and standalone programs for
Windows and Linux.

### New

- Standalone programs for Windows (installer and portable ZIP) and Linux (AppImage and
  tar.gz); no Python installation needed.
- Modern interface with light and dark theme that follows the system.
- Search options: match case, whole words, regular expressions, and a history of recent
  searches. Words split across lines or hyphenated at a line end are found too.
- Searches run in the background on all CPU cores; results appear while the search runs,
  and the search can be cancelled with <kbd>Esc</kbd>.
- Text cache: repeated searches of unchanged files no longer read the PDFs again.
- Result list shows the words around each match with the match in bold; sort by file,
  page or ID; export as CSV; a summary lists files that could not be searched and why.
- Viewer with page navigation, zoom, fit width and fit page; all matches on the page are
  highlighted and the selected one stands out; <kbd>F3</kbd> / <kbd>Shift+F3</kbd> step
  through matches across files; open the file in the system PDF viewer at the right page.
- Single PDF files can be added as search scopes, by menu or drag and drop.
- Command-line search without a window (`pdf-multifile-search`), with CSV output.

### Changed

- PDF engine changed from PyMuPDF to pypdfium2; user interface from Tkinter to Qt.
- Settings are stored in the standard settings folder of the system and saved
  immediately. Settings of version 1 are imported on first start.
- Licensed as AGPL-3.0-or-later, with the complete license text and third-party notices.

### Fixed

- Command-line options `--folder` and `--pattern` were ignored.
- Match IDs were not unique when several search folders were used.
- Folders contained in other search folders were searched twice.
- Highlights of a previous result appeared on unrelated pages.
- Paths containing commas broke the saved folder list.
- The window froze during a search.
- A search failed with "[Errno 2] No such file or directory" when the folder the program
  was started from had been deleted.

## [1.0.0] - 2025-10-05

First version (Tkinter and PyMuPDF).

[2.0.0]: https://github.com/lorenzzhao/pdf_multifile_searcher/releases/tag/v2.0.0
