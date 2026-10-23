# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""Command line: shared argument parser and the headless search mode (FR-CLI).

This module must not import Qt, so the headless mode works without a display.
"""

from __future__ import annotations

import argparse
import logging
import multiprocessing
import sys
from collections.abc import Sequence

from pdf_multifile_searcher import APP_NAME, __version__, legal
from pdf_multifile_searcher.cache import default_cache_path
from pdf_multifile_searcher.core.export import write_csv
from pdf_multifile_searcher.core.matcher import PatternError
from pdf_multifile_searcher.core.models import (
    DEFAULT_CONTEXT_WORDS,
    Match,
    SearchOptions,
    SearchQuery,
)
from pdf_multifile_searcher.core.runner import FileFound, SearchRunner, Skipped, WorkerStartError

EXIT_MATCHES = 0
EXIT_NO_MATCHES = 1
EXIT_USAGE = 2
EXIT_ERROR = 3
EXIT_INTERRUPTED = 130


def build_parser(headless_only: bool = False) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf-multifile-search" if headless_only else "pdf-multifile-searcher",
        description=f"{APP_NAME}: search text in many PDF files at once.",
        # Keeps the line breaks of the --version text.
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-f",
        "--folder",
        action="append",
        default=[],
        metavar="PATH",
        help="folder (searched recursively) or PDF file to search; can be repeated",
    )
    parser.add_argument("-p", "--pattern", help="text to search for")
    parser.add_argument("-c", "--case-sensitive", action="store_true", help="match case")
    parser.add_argument("-w", "--whole-word", action="store_true", help="match whole words only")
    parser.add_argument(
        "-r", "--regex", action="store_true", help="treat the pattern as a regular expression"
    )
    parser.add_argument(
        "--context-words",
        type=int,
        metavar="N",
        help=f"words of context before and after a match (default {DEFAULT_CONTEXT_WORDS})",
    )
    parser.add_argument("--no-cache", action="store_true", help="do not use the text cache")
    parser.add_argument(
        "--include-hidden", action="store_true", help="also search hidden files and folders"
    )
    if not headless_only:
        parser.add_argument(
            "--no-gui", action="store_true", help="search without a window and print the matches"
        )
    parser.add_argument(
        "--format",
        choices=("text", "csv"),
        default="text",
        help="output format of the headless search (default: text)",
    )
    parser.add_argument("--jobs", type=int, metavar="N", help="number of worker processes")
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="diagnostic output level (default: WARNING)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=legal.version_text(parser.prog, __version__),
        help="show version, copyright and license information and exit",
    )
    return parser


def query_from_args(args: argparse.Namespace, context_words: int) -> SearchQuery:
    return SearchQuery(
        pattern=args.pattern or "",
        options=SearchOptions(
            case_sensitive=args.case_sensitive,
            whole_word=args.whole_word,
            regex=args.regex,
        ),
        context_words=args.context_words if args.context_words is not None else context_words,
    )


def run_headless(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Search and print one line per match (FR-CLI-06)."""
    if not args.pattern or not args.folder:
        parser.error("the headless search needs --pattern and at least one --folder")
    try:
        runner = SearchRunner(
            args.folder,
            query_from_args(args, DEFAULT_CONTEXT_WORDS),
            include_hidden=args.include_hidden,
            cache_path=None if args.no_cache else default_cache_path(),
            workers=args.jobs,
        )
    except PatternError as exc:
        parser.error(str(exc))

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    found = 0
    csv_rows: list[Match] = []
    try:
        for event in runner.run():
            if isinstance(event, FileFound):
                found += len(event.result.matches)
                if args.format == "csv":
                    csv_rows.extend(event.result.matches)
                else:
                    for m in event.result.matches:
                        print(f"{m.path}:{m.page_number}: {m.context}", flush=False)
            elif isinstance(event, Skipped):
                print(f"skipped: {event.skipped.path} ({event.skipped.reason})", file=sys.stderr)
    except KeyboardInterrupt:
        runner.cancel()
        return EXIT_INTERRUPTED
    except WorkerStartError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if args.format == "csv":
        write_csv(csv_rows, sys.stdout)
    sys.stdout.flush()
    return EXIT_MATCHES if found else EXIT_NO_MATCHES


def configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level), format="%(levelname)s %(name)s: %(message)s")


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of `pdf-multifile-search` (always headless)."""
    multiprocessing.freeze_support()
    parser = build_parser(headless_only=True)
    args = parser.parse_args(argv)
    configure_logging(args.log_level)
    return run_headless(args, parser)


if __name__ == "__main__":
    sys.exit(main())
