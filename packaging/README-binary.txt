PDF Multifile Searcher
======================

Search text in many PDF files at once and view the matches in place.

Starting the program
--------------------
Windows:  pdf-multifile-searcher.exe     (the window program)
Linux:    ./pdf-multifile-searcher

Searching without a window (prints file:page: context for each match):
Windows:  pdf-multifile-search.exe -f C:\Documents -p "invoice"
Linux:    ./pdf-multifile-search -f ~/Documents -p "invoice"
Run it with --help for all options.

Settings and the text cache are stored in your user profile, not in this folder.

License
-------
Copyright (C) 2025–2026 Lorenz Zhao

This program is free software under the GNU Affero General Public License, version 3
or later, and comes with ABSOLUTELY NO WARRANTY.

It contains third-party components, among them Qt and Qt for Python (Copyright (C) The
Qt Company Ltd. and other contributors) under the GNU Lesser General Public License
v3.0. The "licenses" folder contains the license texts and notices of every component
in this package; licenses/README.txt explains what is where, and licenses/SOURCES.txt
says where to get the source code of the program and of the LGPL components.

Source code: https://github.com/lorenzzhao/pdf_multifile_searcher
