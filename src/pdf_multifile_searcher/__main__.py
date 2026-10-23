"""`python -m pdf_multifile_searcher` starts the GUI (or the headless search with --no-gui)."""

import sys

from pdf_multifile_searcher.app import main

if __name__ == "__main__":
    sys.exit(main())
