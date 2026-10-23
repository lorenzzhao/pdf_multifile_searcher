# PDF Multifile Searcher

A desktop tool to search text in many PDF files at once. Matches are listed with their
context, and the matching page is shown right next to the list with the match highlighted.

## Features

- Search any number of folders (recursively) and single PDF files. Add them through the
  menu, the buttons above the folder tree, or by dragging them from the file manager.
- Literal search by default, with optional **case-sensitive**, **whole word** and **regular
  expression** modes. Words broken across lines or hyphenated at a line end are found too.
- Searches run in the background on all CPU cores. Results appear while the search runs,
  and you can cancel at any time (<kbd>Esc</kbd>).
- A text cache makes repeated searches of unchanged files much faster.
- Results show the words around each match with the match in bold, and can be sorted by
  file, page or ID and exported as CSV.
- A built-in viewer with page navigation, zoom and fit modes. All matches on the page are
  highlighted, and the selected one stands out. <kbd>F3</kbd> / <kbd>Shift+F3</kbd> step
  through matches across files. *Open in system PDF viewer* hands the file to your usual
  PDF application, at the right page where possible.
- Light and dark theme following the system.
- A headless command line mode for scripts.

## Installation

Python 3.11 or newer is required.

```bash
pipx install .
```

For development, from the project root:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Usage

Start the application:

```bash
pdf-multifile-searcher
```

Command-line options pre-fill the window. If both folders and a pattern are given, the
search starts right away. Folders and patterns given this way are not saved.

```bash
pdf-multifile-searcher -f ~/Documents/invoices -f ~/Downloads/report.pdf -p "total amount"
```

Search without a window and print `file:page: context` for each match:

```bash
pdf-multifile-search -f ~/Documents -p "invoice \d+" --regex --whole-word
```

Exit codes: `0` matches found, `1` no matches, `2` usage error, `3` the search could
not run. Use `--format csv` for CSV
output and `--help` for all options. `pdf-multifile-searcher --no-gui …` does the same.

### Keyboard shortcuts

| Key | Action |
|---|---|
| <kbd>Ctrl+F</kbd> | Focus the search field |
| <kbd>Enter</kbd> | Search |
| <kbd>Esc</kbd> | Cancel the search |
| <kbd>F3</kbd> / <kbd>Shift+F3</kbd> | Next / previous match |
| <kbd>PgDn</kbd> / <kbd>PgUp</kbd> | Next / previous page |
| <kbd>Ctrl++</kbd> / <kbd>Ctrl+-</kbd> / <kbd>Ctrl</kbd>+wheel | Zoom |
| <kbd>Ctrl+1</kbd> / <kbd>Ctrl+2</kbd> | Fit width / fit page |
| <kbd>Ctrl+O</kbd> | Open a PDF in the viewer |
| <kbd>Ctrl+E</kbd> | Export results as CSV |
| <kbd>Del</kbd> | Remove the selected search folder |

## Files

| What | Linux | Windows | macOS |
|---|---|---|---|
| Settings | `~/.config/pdf-multifile-searcher/settings.json` | `%APPDATA%\pdf-multifile-searcher` | `~/Library/Application Support/pdf-multifile-searcher` |
| Text cache | `~/.cache/pdf-multifile-searcher/` | `%LOCALAPPDATA%\pdf-multifile-searcher\Cache` | `~/Library/Caches/pdf-multifile-searcher` |

Settings from version 1 (`~/.pdf_multifile_searcher_config.ini`) are imported automatically
the first time. The old file is left untouched. The text cache can be turned off or cleared
under *File → Preferences*.

## Development

```bash
.venv/bin/pytest           # tests (the GUI tests run offscreen)
.venv/bin/ruff check .     # lint
.venv/bin/ruff format .    # format
.venv/bin/mypy             # type check
```

The code is split into layers (see `docs/REQUIREMENTS.md`, NFR-MAINT-01):

- `core/`: search scopes, the matcher, the search runner and the data model. No GUI code.
- `pdf_backend.py`: the only module that talks to the PDF library (pypdfium2).
- `cache.py`, `config.py`, `system.py`: text cache, settings, hand-off to the OS.
- `cli.py`: the command line; `gui/`: the Qt user interface.

## License

Copyright (C) 2025–2026 Lorenz Zhao

This program is free software: you can redistribute it and/or modify it under the terms
of the GNU Affero General Public License as published by the Free Software Foundation,
either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU Affero General Public License for more details.

The full license text is in [`LICENSE`](LICENSE). In short: if you distribute this program,
modified or not, or let users interact with a modified version over a network, you must
make the complete corresponding source code available to them under the same license.

### Third-party components

The program uses Qt for Python (PySide6, LGPL-3.0), pypdfium2 and PDFium (Apache-2.0 /
BSD-3-Clause, with further bundled components) and platformdirs (MIT). All of them are
compatible with the AGPL. They are not part of this repository; `pip` installs them from
PyPI together with their own license files. See
[`THIRD_PARTY_NOTICES.txt`](THIRD_PARTY_NOTICES.txt) for the details, including what a
binary bundle of the program would have to contain.

Version 1 depended on PyMuPDF; version 2 no longer does.
