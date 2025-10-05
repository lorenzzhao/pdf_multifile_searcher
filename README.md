# PDF Multifile Searcher 

A graphical tool to search text in multiple PDF files at once.

Quick run (from project root):

1. Ensure dependencies are installed (pymupdf, tkinter should be available in system):

   pip install pymupdf

2. Run the GUI:

   python3 pdf_multifile_searcher.py

License and distribution note
----------------------------
This project is licensed under the GNU Affero General Public License v3
(AGPL-3.0). The switch to AGPL was made because this project depends on
PyMuPDF, which is available under AGPL-3.0 or a commercial license from
Artifex Software. Under AGPL-3.0, if you distribute the software or operate
it as a network service, you must make the source code available to recipients
or users under AGPL-3.0. If this is incompatible with your distribution goals,
you should either obtain a commercial license for PyMuPDF or replace it with
an alternative library under a compatible license.

Notes:
- The search logic was preserved; the `search_pdfs` function returns a mapping
  of file paths to lists of `Match` objects. This makes it easier to test and
  reuse the search functionality from other scripts.
- The modules use fallback imports so they can be executed both as a script and
  imported as modules during quick tests.
