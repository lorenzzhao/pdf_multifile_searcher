# PDF Multifile Searcher — Requirements

---

## 1. Introduction

### 1.1 Purpose

This document lists the requirements for the *PDF Multifile Searcher*.

### 1.2 How to review

Every requirement has an ID, a priority and an origin:

- **Priority** (MoSCoW): `Must` · `Should` · `Could` · `Won't` (out of scope for version 1).
- **Origin**:
  - `Existing`: the current program behaves this way, and the rewrite should keep it.
  - `Fix`: the current program tries to do this but has a bug or gap (see §7). The
    requirement describes the *intended* behaviour.
  - `New`: the current program does not do this at all. It is a proposal for you to accept or drop.

To change a requirement, edit its text or priority. To drop one, set it to `Won't` or delete it.
Please do not reuse an ID after deleting it.
Section 8 lists the decisions the rewrite depends on. Answers marked **Proposed** are
recommendations; confirm or change them.

### 1.3 Scope

**In scope:** a desktop GUI application that searches text across many PDF files in one or more
folder trees, lists every match with its context, and shows the matching page with the match
highlighted. A headless command-line search uses the same core.

**Out of scope for version 1:** editing PDFs, OCR of scanned PDFs, entering passwords for encrypted
PDFs, translated UI text, a full-text index, a full-featured PDF viewer (anything beyond FR-VIEW
is handed off to the system's PDF application), network/server operation. The architecture must
not prevent adding the full-text index later (NFR-MAINT-06).

---

## 2. Product overview (as-is)

### 2.1 What the program does today

1. The user registers one or more **search folders**: through a menu dialog, by dragging and
   dropping them, or restored from the last session.
2. The user types a **search pattern** and presses *Search* or Enter.
3. Every PDF found recursively under every search folder is searched page by page for the
   pattern. Matching is case-insensitive and treats the pattern as literal text.
4. Matches are listed in a **result tree**: one parent row per file, one child row per match
   showing the context snippet, the page number and the match ID. The list can be sorted.
5. Selecting a result renders that **page** in the viewer pane, scaled to fit, with every match
   on that page marked. The selected match is drawn in a different colour.
6. A **folder tree** lets the user browse the search folders and open any PDF in the viewer.
7. Window layout, search folders and the last pattern are **persisted** in an INI file.

### 2.2 Current technical baseline

| Aspect | Current choice |
|---|---|
| Language | Python 3 |
| GUI toolkit | Tkinter / ttk + `tkinterdnd2` (drag and drop) |
| PDF engine | PyMuPDF (`pymupdf`, imported as `fitz`), AGPL-3.0 |
| Concurrency | `ThreadPoolExecutor`, one task per PDF file |
| Persistence | `configparser` INI at `~/.pdf_multifile_searcher_config.ini` |
| License | AGPL-3.0 (because of PyMuPDF) |
| Modules | `pdf_multifile_searcher.py` (GUI + entry point, ~760 LOC), `pdf_search.py` (search + sort), `pdf_models.py` (`Match` dataclass) |
| Tests | None automated. Sample PDFs in `test/test_folder_a`, `test/test_folder_b` (generated from `test/resources/*.odt`) |

### 2.3 Glossary

| Term | Meaning |
|---|---|
| **Search folder** | A top-level directory registered by the user. Its whole subtree is searched. |
| **Search scope** | A search folder or a single PDF file registered by the user. |
| **Search pattern** | The text the user searches for. |
| **Match** | One occurrence of the pattern in a PDF: file, page, one or more rectangles, context. |
| **Match ID** | An integer that identifies a match within one search run. |
| **Context** | The words around a match, shown in the result list. |
| **Context area** | The rectangles on the page covered by the context words. |
| **Page text** | The text of one page as extracted from the PDF, with a bounding box for every character. |
| **Matcher** | The program's own component that finds the pattern in page text (FR-SRCH-04). |
| **Text cache** | A local store of extracted page text, used to avoid parsing unchanged PDFs again (FR-CACHE). |
| **PDF backend** | The adapter that wraps the PDF library (NFR-MAINT-02). |
| **Viewer** | The pane that renders a PDF page. |

### 2.4 Target technical baseline (proposed)

These follow from the proposed answers in §8. If you change an answer there, update this table.

| Aspect | Target |
|---|---|
| Language | Python 3.11+ (Q3) |
| GUI toolkit | Qt via PySide6 (LGPL-3.0). Drag and drop, high-DPI and model/view lists are built in (Q1) |
| PDF engine | `pypdfium2` (Apache-2.0 / BSD-3-Clause) behind the PDF backend adapter. PyMuPDF remains a drop-in alternative (Q2) |
| Matching | The program's own matcher on extracted page text: literal, case-sensitive, whole word, regex (FR-SRCH-04, FR-SRCH-13) |
| Concurrency | A pool of worker processes, results streamed to the GUI per file, cancellable (FR-SRCH-05…09) |
| Text cache | SQLite in the platform cache directory, keyed by path, modification time and size (FR-CACHE) |
| Persistence | JSON or TOML in the platform config directory, saved on every change (FR-CFG) |
| Packaging | `pyproject.toml` with GUI and CLI entry points (NFR-PLAT-04) |
| Quality | pytest, ruff, mypy, run in CI (NFR-MAINT-04, NFR-TEST) |
| Modules | `core` (scopes, matcher, search runner, data model), `pdf_backend`, `cache`, `config`, `cli`, `gui` (NFR-MAINT-01) |

---

## 4. Functional requirements

### 4.1 Search folder management (FR-SCOPE)

- **FR-SCOPE-01** · Must · Existing: The user can add a search folder through a folder-selection
  dialog (menu *File → Add search folder*).
- **FR-SCOPE-02** · Must · Existing: The user can add one or more folders by dragging them from the
  system file manager onto the folder tree.
- **FR-SCOPE-03** · Should · Fix: The user can drop individual PDF files onto the folder tree. A
  dropped file becomes a search scope of its own: only that file is searched, not its whole parent
  directory.
  _Today the parent directory is added as a search folder, so the whole directory gets searched (D6)._
- **FR-SCOPE-04** · Must · Existing: The user can remove a search folder by selecting its top-level
  node and pressing <kbd>Del</kbd>. Selecting and pressing <kbd>Del</kbd> on sub-nodes has no effect.
- **FR-SCOPE-05** · Must · Existing: The user can remove all search folders at once (menu
  *File → Clear search folders*).
- **FR-SCOPE-06** · Must · Fix: Before a search starts, the files of all search scopes are
  collected into one list, and duplicates are removed by resolved path (following symlinks). No
  PDF is searched twice, even when scopes are repeated or nested. Adding a scope that is already
  registered is refused with a short message.
  _Today duplicates are accepted and overlapping files are searched twice (D5)._
- **FR-SCOPE-07** · Should · Fix: A registered folder that no longer exists, for example on an
  unmounted drive, is shown as unavailable rather than silently empty. Searching skips it and
  reports that it was skipped.
- **FR-SCOPE-08** · Could · New: A context-menu entry *Remove* on top-level folder nodes, as an
  alternative to <kbd>Del</kbd>.

### 4.2 Folder tree (FR-TREE)

- **FR-TREE-01** · Must · Existing: The left pane shows a tree headed "Search folders". Each
  search folder is a top-level node showing its full path.
- **FR-TREE-02** · Must · Existing: Under each search folder, the tree shows subfolders and PDF
  files, collapsed by default. Folders come first, then files, each sorted by name ignoring case.
  Folders and PDFs have distinct icons.
- **FR-TREE-03** · Must · Existing: Hidden entries (names starting with `.`) are not shown.
- **FR-TREE-04** · Must · Fix: The tree shows the full depth of each folder. To keep this fast,
  children are loaded lazily when a node is first expanded.
  _Today the tree stops after 3 levels while the search recurses without limit, so some matched files cannot be found in the tree (D7)._
- **FR-TREE-05** · Must · Existing: Selecting a PDF file in the tree opens it in the viewer at page 1.
- **FR-TREE-06** · Should · Fix: The tree and the search agree on which files are included,
  including hidden files and folders. Decide in §8 whether hidden ones are searched.
- **FR-TREE-07** · Must · Existing: The tree has a vertical scrollbar and shows about 10 rows.
  Row height adapts to the system font size, so rows are not clipped on high-DPI or small screens.
- **FR-TREE-08** · Could · New: A *Refresh* action that rescans the folders after the file system
  has changed.

### 4.3 Search (FR-SRCH)

- **FR-SRCH-01** · Must · Existing: A single-line text field labelled "Search pattern:" holds the
  pattern.
- **FR-SRCH-02** · Must · Existing: The search starts when the user clicks *Search* or presses
  <kbd>Enter</kbd> or keypad <kbd>Enter</kbd> in the pattern field.
- **FR-SRCH-03** · Must · Existing: The search covers every file with extension `.pdf`
  (case-insensitive) found recursively under every search folder, plus every PDF registered as a
  single-file scope.
- **FR-SRCH-04** · Must · Fix: Each page of each PDF is searched. The PDF backend extracts the page
  text once, with a bounding box for every character. The program's own matcher finds the pattern
  in that text, and the match position is mapped back to one or more rectangles on the page. By
  default, matching is literal text and case-insensitive, as today.
  _Today matching is delegated to `page.search_for`, which offers no options and ties the program
  to PyMuPDF._
- **FR-SRCH-05** · Must · Fix: PDFs are searched in parallel in a pool of worker processes, so that
  multiple CPU cores are actually used.
  _Today a thread pool is used. Text extraction is CPU-bound, so in Python, threads give little
  speed-up._
- **FR-SRCH-06** · Must · Fix: The search runs in the background, so the UI stays responsive
  while it runs.
  _Today the search blocks the GUI thread and the window freezes (D2)._
- **FR-SRCH-07** · Should · New: Progress is visible during a search: files processed out of
  files total, and matches found so far.
- **FR-SRCH-08** · Must · New: The user can cancel a running search. Results found up to that
  point stay visible.
- **FR-SRCH-09** · Must · New: Results are streamed per file and appear in the result list while
  the search runs.
- **FR-SRCH-10** · Must · Fix: An empty or whitespace-only pattern does not start a search. The
  user gets a short hint instead.
- **FR-SRCH-11** · Must · Existing: A new search replaces the previous results completely.
- **FR-SRCH-12** · Must · New: When the search finishes or is cancelled, a summary line is shown,
  for example "37 matches in 12 files · 412 files searched · 3 files skipped". Clicking the
  "skipped" part lists the skipped files with reasons (FR-ERR-02).
- **FR-SRCH-13** · Should · New: Search options, shown as toggles next to the pattern field:
  *case-sensitive*, *whole word*, *regular expression*. An invalid regular expression is reported
  next to the pattern field and does not start a search.
- **FR-SRCH-14** · Should · New: A drop-down history of recent search patterns (for example the
  last 20), persisted across sessions.
- **FR-SRCH-15** · Won't · New: OCR of scanned (image-only) PDFs. This is listed so the decision is
  explicit; see §8.
- **FR-SRCH-16** · Won't · New: A persistent full-text index (for example SQLite FTS5) for
  version 1. Every search runs the matcher over all page text, which comes from the text cache
  where possible (FR-CACHE). The design must allow adding the index later (NFR-MAINT-06).
- **FR-SRCH-17** · Should · New: A match is found even when the pattern is broken across a line
  wrap in the PDF (whitespace and line breaks are treated alike), or split by an end-of-line
  hyphen ("exam-␤ple" matches "example").

### 4.4 Match data and context (FR-MATCH)

- **FR-MATCH-01** · Must · Fix: Each match records the absolute file path, the 0-based page
  index, the character offsets of the match and of its context area in the page text, the context
  text and a match ID. The viewer turns the offsets into one or more rectangles on the page (one
  per line when the match spans lines) when it shows the page, so a search never needs the
  rectangles and can run on cached text alone (FR-CACHE-03).
  _Today a match has exactly one rectangle._
- **FR-MATCH-02** · Must · Fix: Match IDs are unique across the whole search run, including when
  there are several search folders. They are deterministic: numbered by file path order, then page,
  then position on the page. Results arriving out of order from the workers do not change the IDs.
  _Today IDs restart at 0 for each folder and depend on the order in which threads finish (D3, D4)._
- **FR-MATCH-03** · Won't · Existing: The fixed-box context of today, a box that extends 50 pt left
  and right of the match and max(5 pt, ½ × match height) above and below it. It is replaced by
  FR-MATCH-04.
- **FR-MATCH-04** · Must · Fix: The context is taken from the page text around the match, by
  words. It shows up to N whole words before and after the match (default N = 10, configurable),
  on a single line, with whitespace collapsed. It is marked with `…` where it is cut. It stays
  within the page.
  _Today the snippet is cut mid-word, contains `\n` and mixes in fragments of adjacent lines (D17)._
- **FR-MATCH-05** · Should · New: The matched text is shown in bold inside the context snippet.

### 4.5 Result list (FR-RES)

- **FR-RES-01** · Must · Existing: Results are shown as a two-level tree. The parent row is a file
  that has matches; its child rows are that file's matches.
- **FR-RES-02** · Must · Existing: The columns are **File** (on parent rows), **Context**, **Page**
  and **ID**.
- **FR-RES-03** · Must · Fix: The page number is shown 1-based, the way users count pages.
  _Today the 0-based index is shown, while the viewer title shows 1-based numbers (D25)._
- **FR-RES-04** · Must · Existing: When a file path is wider than the File column, it is shortened
  in the middle with `…`, so both the start and the end stay visible. The shortening updates
  whenever the column width changes: on column resize, sash drag or window resize. The full path is
  kept for every operation.
- **FR-RES-05** · Should · Fix: Path shortening is based on the measured text width in the actual
  font. It is triggered by resize events, not by polling.
  _Today it assumes 7 px per character and polls every 100 ms (D18)._
- **FR-RES-06** · Should · New: Hovering over a shortened path shows the full path as a tooltip.
- **FR-RES-07** · Must · Existing: Clicking the File, Page or ID column header sorts by that
  column. Clicking the same header again reverses the order. A new column always starts ascending.
  The Context column is not sortable.
- **FR-RES-08** · Must · Existing: Sorting keeps the file grouping. Sorting by File orders the
  parent rows. Sorting by Page or ID orders the matches inside each file, and the files follow the
  order of their first match.
- **FR-RES-09** · Should · New: The current sort column and direction are shown in the header with
  an arrow.
- **FR-RES-10** · Must · Existing: Selecting a match row opens its file in the viewer at the
  match's page and highlights the selected match (see FR-HL).
- **FR-RES-11** · Should · Fix: Selecting a file row opens the file at the page of its first match.
  _Today it always opens page 1 (D21)._
- **FR-RES-12** · Must · New: The user can step through the matches with the keyboard. The Up and
  Down keys move through the result list. <kbd>F3</kbd> / <kbd>Shift+F3</kbd> go to the next and
  previous match from anywhere in the window, crossing file boundaries. The viewer follows the
  selection.
- **FR-RES-13** · Should · New: The results can be exported as CSV with the columns file, page,
  context and ID. The CSV is UTF-8 and opens correctly in common spreadsheet programs.
- **FR-RES-14** · Should · New: A context menu on result rows with *Open in system PDF viewer*,
  *Copy path* and *Show in file manager*. *Open in system PDF viewer* opens at the match's page
  where the platform's default viewer supports it, and at page 1 otherwise.
- **FR-RES-15** · Should · New: An empty state with the message "No matches" when a search
  finishes without results.

### 4.6 PDF viewer (FR-VIEW)

The viewer is kept small on purpose: it shows search results in place. Anything beyond the
requirements below is handed off to the system's PDF application (FR-RES-14, FR-VIEW-12).

- **FR-VIEW-01** · Must · Fix: The right pane shows one PDF page at a time. By default the page is
  scaled to the width of the pane and scrolls vertically. The user can switch to fit-whole-page.
  _Today the page is always fitted completely, so on narrow panes it is too small to read._
- **FR-VIEW-02** · Must · Existing: The page is re-rendered when the window is resized or the sash
  between the panes is dragged.
- **FR-VIEW-03** · Must · Existing: Menu *File → Open* opens any PDF in the viewer at page 1 through
  a file dialog filtered to `*.pdf`. The file is not added to the search scope.
- **FR-VIEW-04** · Must · Fix: The window title shows the application name, the current file name
  and the page as "Page X / N".
  _Today the title changes from "PDF Multifile Search" to "PDF Viewer - Page X/N" with no file name (D12)._
- **FR-VIEW-05** · Must · Fix: The user can move to the next and previous page with buttons and
  the <kbd>PgUp</kbd> / <kbd>PgDn</kbd> keys.
  _The methods exist today but are not connected to the UI and would crash (D10)._
- **FR-VIEW-06** · Should · New: The user can jump to a page by typing its number.
- **FR-VIEW-07** · Should · New: Zoom in and out (for example 50 % to 400 %) with buttons,
  <kbd>Ctrl</kbd>+<kbd>+</kbd> / <kbd>Ctrl</kbd>+<kbd>−</kbd> and <kbd>Ctrl</kbd>+mouse wheel. The
  page scrolls in both directions when it is larger than the pane. When a match is selected, the
  view scrolls so the match is visible.
  _A scrollbar exists today but has no effect (D11)._
- **FR-VIEW-08** · Should · New: *Next match* and *Previous match* buttons in the viewer toolbar,
  with the same behaviour as FR-RES-12.
- **FR-VIEW-09** · Must · Fix: Only one document is open at a time. The previous document is
  closed when another one is opened.
  _Today documents are never closed (D22)._
- **FR-VIEW-10** · Won't · New: Selecting and copying text in the viewer. Use the system PDF viewer.
- **FR-VIEW-11** · Won't · New: Continuous multi-page scrolling, thumbnails, outlines/bookmarks,
  annotations, forms and printing. Use the system PDF viewer.
- **FR-VIEW-12** · Should · New: A toolbar button *Open in system PDF viewer* for the current file
  and page.

### 4.7 Match highlighting (FR-HL)

- **FR-HL-01** · Must · Existing: When a page is shown from a search result, every match on that
  page is marked.
- **FR-HL-02** · Must · Existing: The selected match is marked in a different colour and with a
  heavier outline than the other matches. Today this is green for the selected match and yellow for
  the others.
- **FR-HL-03** · Must · Fix: The match's rectangles are filled with a strong, semi-transparent
  colour. The context area of the selected match is marked subtly, for example with a light
  outline.
  _Today the dashed outline is drawn around the context area, and a separate highlight annotation is burned into the in-memory document (D9)._
- **FR-HL-04** · Must · Fix: Highlights belong only to the page and search they were computed
  for. Opening a PDF from the folder tree or *File → Open* shows no stale marks.
  _Today, marks from the previous result are drawn on unrelated documents (D8)._
- **FR-HL-05** · Must · Existing: Highlighting never changes the PDF file on disk.
- **FR-HL-06** · Should · New: Highlights also appear when the user browses to another page that
  contains matches from the current search.

### 4.8 Main window and menu (FR-UI)

- **FR-UI-01** · Must · Existing: The main window is split into a left pane (folder tree, pattern
  field, *Search* button, result list) and a right pane (viewer). A draggable sash separates them,
  and each pane has a minimum width of 100 px.
- **FR-UI-02** · Must · Existing: The default window is 1200 × 800 at position (200, 100), with
  the sash at 400 px.
- **FR-UI-03** · Must · Existing: The **File** menu contains *Open*, *Add search folder*,
  *Clear search folders*, *Export results…* (FR-RES-13), a separator and *Exit*.
- **FR-UI-04** · Must · Existing: Closing the window and *File → Exit* both quit the program. The
  configuration is already saved by then (FR-CFG-04).
- **FR-UI-05** · Should · Fix: Remove the stray "Folder: …" labels, which pile up below the search
  pane each time a folder is added (D15). The status bar (FR-UI-06) takes over their purpose.
- **FR-UI-06** · Must · New: A status bar shows search progress (FR-SRCH-07), the search summary
  (FR-SRCH-12) and the currently opened file.
- **FR-UI-07** · Could · New: *Help → About* showing the version, the project license and the
  third-party notices.
- **FR-UI-08** · Should · New: The panes use the platform's native look rather than the debug-style
  light blue and light green backgrounds used today.
- **FR-UI-09** · Should · New: Keyboard shortcuts: <kbd>Ctrl+O</kbd> Open, <kbd>Ctrl+F</kbd>
  focus the pattern field, <kbd>Ctrl+Q</kbd> Exit, <kbd>Esc</kbd> cancel the search,
  <kbd>F3</kbd> / <kbd>Shift+F3</kbd> next and previous match.

### 4.9 Persistence (FR-CFG)

- **FR-CFG-01** · Must · Fix: The configuration is stored per user as a single JSON or TOML file in
  the platform-standard config directory: `$XDG_CONFIG_HOME` (usually `~/.config`) on Linux,
  `%APPDATA%` on Windows, `~/Library/Application Support` on macOS. Lists are stored as real lists.
  _Today it is an INI file in the home directory, `~/.pdf_multifile_searcher_config.ini`._
- **FR-CFG-02** · Must · Existing: The following are saved and restored on startup:
  - the list of search scopes, in order
  - the last search pattern, the search options (FR-SRCH-13) and the pattern history (FR-SRCH-14)
  - the window width, height and x/y position
  - the widths of the File and Context columns
  - the sash position
  - the viewer's fit mode and zoom (FR-VIEW-01, FR-VIEW-07)
- **FR-CFG-03** · Must · Fix: Folder paths of any form, including ones containing commas, `=` or
  non-ASCII characters, survive saving and restoring.
  _Today folders are joined with `,`, so a path containing a comma breaks (D13)._
- **FR-CFG-04** · Must · Fix: Changes are saved when they happen. Layout changes such as resizing
  may be saved with a short delay. Writes are atomic (write to a temporary file, then rename), so
  a crash never leaves a half-written file (D14).
- **FR-CFG-05** · Must · Existing: A missing, empty or partially filled configuration file leads to
  defaults and never to an error.
- **FR-CFG-06** · Should · Fix: A corrupt configuration file, for example one with non-numeric
  widths, is ignored with a warning instead of crashing at startup.
- **FR-CFG-07** · Should · New: A restored window position that would be off-screen, for example
  after a monitor was disconnected, is moved back onto a visible screen.
- **FR-CFG-08** · Must · New: If the old INI file exists and no new configuration file exists yet,
  its settings are imported once on startup. The old file is left untouched. See §6.
- **FR-CFG-09** · Could · New: The sort column and direction are also persisted.

### 4.10 Command line (FR-CLI)

- **FR-CLI-01** · Must · Existing: The program starts from an installed launcher (NFR-PLAT-04), and
  also with `python -m <package>` from a source checkout.
- **FR-CLI-02** · Must · Fix: `-f/--folder PATH` can be given several times. The given folders are
  the search folders for this session.
  _Today the option is parsed and then ignored (D1)._
- **FR-CLI-03** · Must · Fix: `-p/--pattern TEXT` pre-fills the search pattern and takes
  precedence over the saved pattern.
  _Today it is overwritten by the saved pattern (D1)._
- **FR-CLI-04** · Should · New: When folders or a pattern are given on the command line, the
  session does not overwrite the saved folder list and pattern. This is the "command line mode"
  noted as a TODO in the code.
- **FR-CLI-05** · Could · New: When both `--folder` and `--pattern` are given, the search starts
  automatically after launch.
- **FR-CLI-06** · Should · New: A headless mode (for example `--no-gui`, or a separate
  `pdf-multifile-search` command) that runs the same core search without a display. It prints one
  line per match (`file:page: context`) to stdout and skipped files to stderr. The exit code is
  0 if there were matches, 1 if there were none and 2 on usage errors.
- **FR-CLI-07** · Must · Existing: `-h/--help` prints usage.
- **FR-CLI-08** · Should · New: The search options are available as flags: `-c/--case-sensitive`,
  `-w/--whole-word`, `-r/--regex`. A `--format csv` option for the headless mode produces the same
  CSV as FR-RES-13, and `--no-cache` bypasses the text cache.

### 4.11 Error handling (FR-ERR)

- **FR-ERR-01** · Must · Existing: A PDF that cannot be opened (corrupt, encrypted, not really a
  PDF) does not abort the search. It is skipped.
- **FR-ERR-02** · Must · Fix: Skipped files are reported to the user with a reason ("encrypted",
  "damaged", "no text layer", "permission denied"). See the summary in FR-SRCH-12.
  _Today they are silently skipped (D16)._
- **FR-ERR-03** · Must · Existing: An error on a single page does not abort the search of the
  rest of the document.
- **FR-ERR-04** · Must · Fix: Errors when opening a PDF in the viewer are shown to the user, not
  only printed to stdout.
- **FR-ERR-05** · Should · New: Diagnostic output goes through a logger with a configurable level
  instead of `print()`.
- **FR-ERR-06** · Won't · New: Entering a password for an encrypted PDF. Encrypted files are
  reported as skipped (FR-ERR-02).
- **FR-ERR-07** · Should · New: A PDF without any extractable text, which is usually a scanned
  document, is reported as "no text layer". This tells the user why it never matches (FR-SRCH-15).

### 4.12 Text cache (FR-CACHE)

- **FR-CACHE-01** · Should · New: The extracted text of each PDF (FR-SRCH-04) is stored in a local
  SQLite database in the platform-standard cache directory: `$XDG_CACHE_HOME` on Linux,
  `%LOCALAPPDATA%` on Windows, `~/Library/Caches` on macOS. It stores the page text only; match
  rectangles are recomputed from character offsets when a page is shown (FR-MATCH-01).
- **FR-CACHE-02** · Should · New: Cache entries are keyed by the resolved file path, the
  modification time and the file size. If any of them differs, the file is extracted again and the
  entry is replaced. Changing the PDF backend or the cache format also invalidates the entries.
- **FR-CACHE-03** · Should · New: A search whose files are all unchanged and cached does not open
  any PDF. It runs the matcher on the cached text only.
- **FR-CACHE-04** · Should · New: The cache can be turned off in the settings and with `--no-cache`
  (FR-CLI-08). There is also an action *Clear text cache*.
- **FR-CACHE-05** · Should · New: Entries for files that no longer exist are removed from time to
  time, for example at startup for files under the registered scopes. The cache size is shown next
  to *Clear text cache*.
- **FR-CACHE-06** · Must · New: A missing, locked or corrupt cache never stops a search. The program
  falls back to extracting the text directly, logs a warning, and rebuilds the cache when it can.
- **FR-CACHE-07** · Must · New: Only one process writes to the cache, or writes are serialised, so
  that parallel workers (FR-SRCH-05) do not corrupt it.

---

## 5. Non-functional requirements

### 5.1 Performance and responsiveness (NFR-PERF)

- **NFR-PERF-01** · Must · Fix: The UI stays responsive (input handled within 100 ms) at all times,
  including during a search and while the folder tree is loaded.
- **NFR-PERF-02** · Should · New: Searching 1,000 text PDFs of 10 pages each without a cache takes
  at most as long as the current implementation does on the same machine. _Reviewer: set a
  concrete target._
- **NFR-PERF-03** · Should · New: Results containing 10,000 matches stay scrollable and sortable
  without noticeable lag.
- **NFR-PERF-04** · Should · Existing: The time from a click to the rendered page is under 300 ms
  for typical pages.
- **NFR-PERF-05** · Should · New: The PDF that is currently displayed is not opened again from
  disk every time the user selects another match in the same file.
- **NFR-PERF-06** · Should · New: Repeating a search on an unchanged collection, with the text
  cache filled, is at least 10 times faster than the first, uncached search.
- **NFR-PERF-07** · Should · New: The first matches appear in the result list within 1 second of
  starting a search, even when the whole search takes much longer (FR-SRCH-09).

### 5.2 Platform and deployment (NFR-PLAT)

- **NFR-PLAT-01** · Must · Existing: The program runs on Linux desktops (X11 and Wayland).
- **NFR-PLAT-02** · Should · Existing: The program runs on Windows and macOS. Nothing in the
  current code is Linux-specific. _Reviewer: confirm the target platforms._
- **NFR-PLAT-03** · Must · Fix: All runtime dependencies are declared in `pyproject.toml`.
  _Today the README omits `tkinterdnd2` (D20)._
- **NFR-PLAT-04** · Must · New: The program is a Python package built from `pyproject.toml`. It
  can be installed with `pip`/`pipx` and has a GUI entry point and a CLI entry point (FR-CLI-06).
  There is no `sys.path` manipulation.
- **NFR-PLAT-05** · Must · Existing: Drag and drop of folders and PDF files works on all supported
  platforms, including Wayland.
- **NFR-PLAT-06** · Should · New: The program works correctly on high-DPI displays: fonts, row
  heights, icons and page rendering.

### 5.3 Licensing (NFR-LIC)

- **NFR-LIC-01** · Must · Existing: The project and all its dependencies are distributed under
  compatible licenses. The project license follows from the PDF engine chosen in Q2: with PyMuPDF
  it must be AGPL-3.0, with `pypdfium2` and PySide6 a permissive or GPL license is possible.
- **NFR-LIC-02** · Must · Existing: The LICENSE file and third-party notices are kept up to date.
- **NFR-LIC-03** · Must · New: The PDF engine sits behind the PDF backend adapter (NFR-MAINT-02), so
  it can be swapped without changes elsewhere. _See decision Q2._

### 5.4 Maintainability (NFR-MAINT)

- **NFR-MAINT-01** · Must · New: The code is split into these packages. None except `gui` imports
  GUI code, and `core` can be used from the CLI and from tests without a display.
  - `core`: search scopes, file collection, the matcher, the search runner and the data model
  - `pdf_backend`: the PDF library adapter
  - `cache`: the text cache
  - `config`: loading, saving and migrating settings
  - `cli`: the command line
  - `gui`: the Qt user interface
- **NFR-MAINT-02** · Must · New: All PDF library calls go through the PDF backend adapter. Its
  operations are: open a document (reporting "encrypted", "damaged" and so on as typed errors), page
  count, page size, extract page text with a box for every character, render a page to an image at
  a given scale, and close.
- **NFR-MAINT-03** · Must · New: No global mutable state. Today `exit_app` depends on module
  globals and fails when the module is imported (D14).
- **NFR-MAINT-04** · Must · New: Type hints throughout. The code passes `ruff` (lint and format)
  and `mypy` in CI.
- **NFR-MAINT-05** · Must · Fix: No dead code or stray imports (D19).
- **NFR-MAINT-06** · Must · New: Getting page text is one interface in `core`, with "extract
  directly" and "from the text cache" as implementations. A future full-text index (FR-SRCH-16)
  can then be added as a pre-filter that limits which files the matcher runs on, without changes
  to the matcher, the result model or the GUI.
- **NFR-MAINT-07** · Must · New: The matcher (FR-SRCH-04, FR-SRCH-13, FR-SRCH-17, FR-MATCH-04) is a
  pure function from page text and search options to matches, with no PDF or file access.

### 5.5 Testability and quality (NFR-TEST)

- **NFR-TEST-01** · Must · New: Automated pytest tests for the search core, using the sample PDFs
  in `test/`. Expected match counts, pages and contexts are written down as fixtures.
- **NFR-TEST-02** · Must · New: Tests for config round-trip and INI migration (FR-CFG-03,
  FR-CFG-08), match-ID determinism (FR-MATCH-02), overlapping scopes (FR-SCOPE-06) and unreadable,
  encrypted or text-less PDFs (FR-ERR-01, FR-ERR-07).
- **NFR-TEST-03** · Should · New: The test PDF generator (`test/pdf_file_generator.py`) is either
  made reproducible and documented, or removed in favour of committed fixtures.
- **NFR-TEST-04** · Should · New: A CI pipeline runs the tests, `ruff` and `mypy` on every push.
- **NFR-TEST-05** · Must · New: The matcher has unit tests on plain strings, without PDFs. They
  cover the default literal search, each option in FR-SRCH-13, line wraps and hyphenation
  (FR-SRCH-17), and context cutting (FR-MATCH-04).
- **NFR-TEST-06** · Should · New: Cache tests: a hit on an unchanged file, a miss after the file
  is modified, and fallback when the cache is corrupt (FR-CACHE-02, FR-CACHE-06).
- **NFR-TEST-07** · Could · New: Tests that check the headless CLI's output and exit codes
  (FR-CLI-06).

### 5.6 Usability and accessibility (NFR-UX)

- **NFR-UX-01** · Should · New: Every function can be reached with the keyboard.
- **NFR-UX-02** · Should · New: Highlight colours are distinguishable by people with colour-vision
  deficiency. For example, the selected match uses outline thickness as well as colour.
- **NFR-UX-03** · Won't · New: Translated UI text for version 1. The UI is in English. All
  user-visible strings go through Qt's translation function (`tr()`), so translations can be added
  later without code changes. _See Q9._

### 5.7 Privacy and safety (NFR-SEC)

- **NFR-SEC-01** · Must · Existing: The program works fully offline and sends no data anywhere.
- **NFR-SEC-02** · Must · Existing: The program never modifies, moves or deletes the user's PDF
  files.
- **NFR-SEC-03** · Should · New: Symlink loops inside search folders do not cause infinite
  recursion.
- **NFR-SEC-04** · Should · New: The text cache contains text from the user's documents, so it is
  readable only by the user (file mode `0600` on POSIX). *Clear text cache* deletes it completely.

---

## 6. Configuration file format (current, for migration)

```ini
[Folders]
folders = /path/one,/path/two          ; comma-joined, see D13

[Search]
pattern = <last pattern>

[Window]
width = 1200
height = 800
x = 200
y = 100

[Treeview]
file_column_width = 200
context_column_width = 200

[Sash]
position = 400
```

**MIG-01** · Must · New: On first start, the rewrite reads this file if it exists and imports its
settings (FR-CFG-08). The folder list is split on commas; this is the best that can be done, since
the old format cannot represent paths that contain commas.

---

## 7. Known defects in the current implementation

The rewrite must not reproduce these. The references point to the code at `03e893b`.

| ID | Defect | Where |
|---|---|---|
| D1 | `--folder` is stored but never used. `--pattern` is overwritten by the saved pattern when the config is loaded. | `pdf_multifile_searcher.py:44`, `:145`, `:257` |
| D2 | The search runs on the GUI thread, so the window freezes. There is no progress indicator and no way to cancel. | `pdf_multifile_searcher.py:557` |
| D3 | Match IDs restart at 0 for each search folder. With two or more folders, IDs collide and several matches are highlighted as "selected". | `pdf_search.py:30`, `pdf_multifile_searcher.py:574` |
| D4 | The order of match IDs depends on which thread finishes first, so it is not reproducible. | `pdf_search.py:82-86` |
| D5 | Duplicate or nested search folders are accepted. Overlapping files are searched twice and the second result silently replaces the first. | `pdf_multifile_searcher.py:574-577` |
| D6 | Dropping a PDF file registers its parent directory as a search folder, so the whole directory is searched. | `pdf_multifile_searcher.py:325-343` |
| D7 | The folder tree stops at depth 3 and hides dotfiles. The search recurses without limit and includes hidden files. | `pdf_multifile_searcher.py:503` |
| D8 | Overlay rectangles are not cleared when a PDF is opened from the folder tree or *File → Open*, so marks from the previous result appear on unrelated pages. | `pdf_multifile_searcher.py:530`, `:547` |
| D9 | The dashed overlay is drawn around the *context area*, not the match. Highlight annotations are added to the in-memory document again on every selection, and the page is rendered twice. | `pdf_multifile_searcher.py:420-441` |
| D10 | `next_page` and `prev_page` are not connected to the UI and use the attribute `self.page_count`, which does not exist. | `pdf_multifile_searcher.py:728-740` |
| D11 | The viewer scrollbar is attached to the root window, not the viewer, and has no effect because the page always fits the pane. There is no zoom. | `pdf_multifile_searcher.py:188` |
| D12 | The window title changes to "PDF Viewer - Page X/N" and never shows the file name. | `pdf_multifile_searcher.py:418` |
| D13 | Folders are saved comma-joined, so paths that contain commas break. | `pdf_multifile_searcher.py:209`, `:247` |
| D14 | The configuration is saved only on a clean exit. `exit_app` uses module globals, so it fails when the module is imported rather than run as a script. | `pdf_multifile_searcher.py:742` |
| D15 | A "Folder: …" label is packed under the search pane each time a folder is added. After *Clear*, the label still shows the last folder. | `pdf_multifile_searcher.py:485` |
| D16 | Errors only go to stdout through `print`. Unreadable or encrypted PDFs are skipped silently. An empty result gives no feedback. | throughout |
| D17 | The context text comes from a fixed box: it is cut mid-word, contains newlines and mixes in neighbouring lines. | `pdf_search.py:54-62` |
| D18 | Path shortening assumes 7 px per character and polls the column width every 100 ms. | `pdf_multifile_searcher.py:281`, `:370` |
| D19 | Stray `from __hello__ import initialized`, unused imports, a `sys.path` hack, and `_map_column_to_match_attr` mapping to the attribute `context_text`, which does not exist. | `pdf_multifile_searcher.py:4`, `:21`, `:656` |
| D20 | The README does not mention the `tkinterdnd2` dependency. There is no dependency manifest and there are no automated tests. | `README.md` |
| D21 | Selecting a file-level result row opens page 1, not the first matching page. | `pdf_multifile_searcher.py:412-415` |
| D22 | Each selection opens the PDF again with `fitz.open`. The previous document is never closed (resource leak). | `pdf_multifile_searcher.py:666` |
| D23 | An empty pattern is not validated. The search runs and silently returns nothing. | `pdf_multifile_searcher.py:565` |
| D24 | Errors while populating the tree for a missing folder are swallowed, so the folder appears empty without explanation. | `pdf_multifile_searcher.py:251-254` |
| D25 | The result list shows 0-based page numbers. The viewer title shows 1-based numbers. | `pdf_multifile_searcher.py:654` |

---

## 8. Open decisions for the reviewer

These had to be settled before the rewrite started. Version 2.0 implements the **Proposed**
answers; answers marked **Implemented** were decided during the rewrite. §2.4 summarises them.

- **Q1: GUI toolkit.** Keep Tkinter, or move to Qt (PySide6)? Another stack, such as a web UI, is
  also possible.
  → **Proposed:** Qt via PySide6 (LGPL-3.0). Much of today's code works around Tkinter's limits:
  the path-width polling, the hand-built icons, the separate `tkinterdnd2` dependency, and the
  misplaced scrollbar. Qt has native drag and drop, a native look, high-DPI support, model/view
  lists that handle large result sets, and `QPdfView` if it is ever needed.
- **Q2: PDF engine and license.** Keep PyMuPDF (fast and capable, but AGPL-3.0), or switch to a
  permissive engine such as `pypdfium2` (Apache-2.0 / BSD-3-Clause)?
  → **Proposed:** `pypdfium2` behind the PDF backend adapter, with the program's own matcher
  (FR-SRCH-04). This lets the project use a permissive or GPL license. The matcher works on
  extracted text, so it does not depend on the engine: if AGPL is acceptable to you, PyMuPDF can be
  used in the same adapter instead, and the rest of the design stays the same. In return,
  `pypdfium2` needs the program to do more of the matching work itself.
  _Reviewer: the engine is implemented as `pypdfium2`. The project license is still open: the
  LICENSE file still says AGPL-3.0, and no dependency requires that any more._
- **Q3: Language.** Stay with Python, or rewrite in another language?
  → **Proposed:** Python 3.11+. Worker processes cover the performance needs, and the text cache
  covers repeat searches.
- **Q4: Hidden files.** Should hidden files and folders be searched (FR-TREE-06)?
  → **Implemented:** Not by default. *File → Preferences → Include hidden files and folders*
  turns them on for both the tree and the search; `--include-hidden` does the same on the
  command line.
- **Q5: Search options.** Which of case-sensitive, whole word and regex (FR-SRCH-13) are needed?
  Should the search also match text that is broken by hyphenation or line wraps?
  → **Proposed:** All three options (Should), with case-insensitive literal search as the default.
  Line wraps and end-of-line hyphenation are handled (FR-SRCH-17).
- **Q6: OCR.** Must scanned PDFs be searchable (FR-SRCH-15)?
  → **Proposed:** Not in version 1. Text-less PDFs are reported (FR-ERR-07), so the gap is visible.
  OCR could later be added as a text source next to the cache (NFR-MAINT-06).
- **Q7: Indexing.** Is re-reading every file on each search acceptable for your collection sizes,
  or is an index or cache needed (FR-SRCH-16)? How many files and pages are typical?
  → **Proposed:** A text cache (FR-CACHE) for version 1, which removes PDF parsing from repeat
  searches. A full-text index (SQLite FTS5) comes later, if needed; the design leaves room for it
  (NFR-MAINT-06).
  _Reviewer: the typical number of files and pages would still help to set NFR-PERF-02._
- **Q8: Target platforms** (NFR-PLAT-02) **and packaging.** Options are pip, a Flatpak or AppImage,
  or a Windows installer.
  → **Implemented:** A Python package installable with `pip`/`pipx` (NFR-PLAT-04). Tested on
  Linux (Wayland). Windows and macOS are supported by the code but not tested yet. Flatpak,
  AppImage and installers are open.
- **Q9: UI language.** English only, or also German or other languages (NFR-UX-03)?
  → **Proposed:** English only for version 1, with all strings ready for translation.
- **Q10: Headless CLI.** Is a non-GUI search mode wanted (FR-CLI-06)?
  → **Proposed:** Yes. It is almost free once the core is separate, and it makes testing the core
  easier.
- **Q11: Viewer depth.** Is a minimal viewer enough, or is a fuller viewer wanted? Alternatively,
  the program could hand off to the system PDF viewer.
  → **Proposed:** A small viewer (one page, fit-to-width with scrolling, page navigation, zoom,
  match navigation) plus *Open in system PDF viewer* for everything else (FR-VIEW).

---

## 9. Implementation status (version 2.0)

Version 2.0 implements this document, with these exceptions and notes:

- **NFR-UX-03:** user-visible strings are plain Python strings, not yet wrapped in Qt's `tr()`.
- **NFR-PERF-02, -03, -06, -07:** the targets are not measured yet. They need a realistic
  collection of PDFs (see Q7).
- **FR-RES-14 / FR-VIEW-12:** opening at a page works on Linux with Evince, Atril, Xreader,
  Okular, zathura, qpdfview, Firefox and Chromium when they are the default PDF application
  and installed natively (not as Flatpak). Everywhere else the file opens at page 1, and the
  status bar says so.
- **NFR-PLAT-05:** drag and drop is implemented with Qt's standard mechanism but was not
  tested by hand on Wayland.
- **FR-SRCH-17:** PDFium reports a hyphen at a line end as U+FFFE and joins the lines; the
  matcher treats it like a soft hyphen.

Section 7 describes the version 1 code, which has been removed. Section 6 is still used:
the old INI file is imported on first start.

---

## Appendix A. Mapping from current code to requirements

This maps the removed version 1 code (commit `03e893b`) to the requirements.

| Current code | Requirements |
|---|---|
| `pdf_search.search_pdfs` | FR-SRCH-03…05, FR-MATCH-01…04, FR-ERR-01, FR-ERR-03 |
| `pdf_search.sort_results` (unused by the GUI) | FR-RES-07/08 |
| `pdf_models.Match` | FR-MATCH-01 |
| `PDFMultifileSearch.__init__` (layout, menu, widgets) | FR-UI-01…03, FR-TREE-01/07, FR-SRCH-01/02, FR-RES-01/02 |
| `save_configuration` / `load_configuration` | FR-CFG-01…05, FR-CFG-08 |
| `_on_folder_tree_drop`, `add_search_folder`, `clear_search_folders`, `_on_folder_tree_delete` | FR-SCOPE-01…05 |
| `_populate_folder_tree`, `_on_folder_tree_select` | FR-TREE-02…05 |
| `_sort_results_by_column`, `_refresh_results_display` | FR-RES-07/08 |
| `shorten_path_for_width`, `_update_file_path_displays`, column-width polling | FR-RES-04/05 |
| `on_treeview_select` | FR-RES-10/11, FR-HL-01…04 |
| `show_page`, `on_resize`, `on_sash_drag`, `load_pdf`, `open_pdf` | FR-VIEW-01…03, FR-VIEW-09 |
| `next_page` / `prev_page` | FR-VIEW-05 |
| `argparse` block | FR-CLI-01…03, FR-CLI-07 |
| `exit_app`, `WM_DELETE_WINDOW` | FR-UI-04 |
