# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""The search runner: parallel, streaming and cancellable (FR-SRCH-05…09, FR-MATCH-02).

`SearchRunner.run()` is a generator of events. The CLI iterates it directly; the GUI
iterates it on a background thread and forwards the events as Qt signals.

Files are searched in worker processes. Results arrive in any order, but they are released
in file-path order, so match IDs are unique for the whole run and deterministic.
"""

from __future__ import annotations

import concurrent.futures as cf
import logging
import multiprocessing
import multiprocessing.spawn
import os
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from pdf_multifile_searcher.cache import TextCache
from pdf_multifile_searcher.core.matcher import compile_query
from pdf_multifile_searcher.core.models import (
    FileMatches,
    Match,
    SearchQuery,
    SearchSummary,
    SkippedFile,
)
from pdf_multifile_searcher.core.scopes import collect_files
from pdf_multifile_searcher.core.worker import FileOutcome, FileTask, init_worker, search_file
from pdf_multifile_searcher.pdf_backend import BACKEND_ID

log = logging.getLogger(__name__)

PROGRESS_INTERVAL = 0.1  # seconds between progress events


@dataclass(frozen=True)
class Started:
    files_total: int


@dataclass(frozen=True)
class Progress:
    files_done: int
    files_total: int
    matches: int


@dataclass(frozen=True)
class FileFound:
    result: FileMatches


@dataclass(frozen=True)
class Skipped:
    skipped: SkippedFile


@dataclass(frozen=True)
class Finished:
    summary: SearchSummary


SearchEvent = Started | Progress | FileFound | Skipped | Finished


class WorkerStartError(RuntimeError):
    """The worker processes for a search cannot be started."""


def _prepare_spawn() -> None:
    """Make sure worker processes can be started.

    `multiprocessing` reads the current directory when it starts a worker, which fails if
    that directory was deleted while the program was running (for example the folder the
    program was started from). Searches only use absolute paths, so moving to the home
    folder is harmless. A deleted Python interpreter cannot be repaired; the user gets a
    clear message instead of a bare "[Errno 2]".
    """
    try:
        os.getcwd()
    except OSError:
        home = os.path.expanduser("~")
        log.warning("Working directory no longer exists; switching to %s", home)
        os.chdir(home)
    executable = os.fsdecode(multiprocessing.spawn.get_executable() or "")
    if not executable or not os.path.exists(executable):
        raise WorkerStartError(
            f"The Python interpreter {executable or '(unknown)'} no longer exists, so no "
            "search processes can be started. Please restart the program."
        )


class SearchRunner:
    """Runs one search. Create a new runner for every search."""

    def __init__(
        self,
        scopes: Sequence[str],
        query: SearchQuery,
        *,
        include_hidden: bool = False,
        cache_path: Path | None = None,
        workers: int | None = None,
        in_process: bool = False,
    ) -> None:
        """`in_process=True` searches in the calling thread (CLI and tests). The GUI must
        keep it False, because PDFium may only be used by one thread per process."""
        self.scopes = list(scopes)
        self.query = query
        self.include_hidden = include_hidden
        self.cache_path = cache_path
        self.workers = workers
        self.in_process = in_process
        self._cancel = threading.Event()
        # Validate now so the caller gets PatternError before anything starts.
        compile_query(query)

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def run(self) -> Iterator[SearchEvent]:
        started = time.monotonic()
        summary = SearchSummary()
        collected = collect_files(self.scopes, self.include_hidden)
        files = collected.files
        summary.files_total = len(files)
        for unavailable in collected.unavailable:
            summary.skipped.append(unavailable)
            yield Skipped(unavailable)
        yield Started(len(files))

        writer = TextCache(self.cache_path, BACKEND_ID) if self.cache_path else None
        cache_arg = str(self.cache_path) if self.cache_path else None
        tasks = [FileTask(path, self.query, cache_arg) for path in files]

        arrived: dict[int, FileOutcome] = {}
        next_index = 0
        next_id = 0
        last_progress = 0.0

        def release(index: int) -> Iterator[SearchEvent]:
            nonlocal next_id
            outcome = arrived.pop(index)
            if outcome.error is not None:
                skipped = SkippedFile(outcome.path, outcome.error)
                summary.skipped.append(skipped)
                yield Skipped(skipped)
            if outcome.matches:
                matches = []
                for page_match in outcome.matches:
                    matches.append(Match(next_id, outcome.path, page_match))
                    next_id += 1
                summary.matches += len(matches)
                summary.files_with_matches += 1
                yield FileFound(FileMatches(outcome.path, tuple(matches)))

        def on_arrival(index: int, outcome: FileOutcome) -> Iterator[SearchEvent]:
            nonlocal next_index, last_progress
            arrived[index] = outcome
            summary.files_searched += 1
            if writer is not None and outcome.store_in_cache and outcome.cache_key is not None:
                writer.store(outcome.cache_key, outcome.cache_pages, outcome.cache_error)
            while next_index in arrived:
                yield from release(next_index)
                next_index += 1
            now = time.monotonic()
            if now - last_progress >= PROGRESS_INTERVAL or summary.files_searched == len(tasks):
                last_progress = now
                pending_matches = sum(len(o.matches) for o in arrived.values())
                yield Progress(
                    summary.files_searched, len(tasks), summary.matches + pending_matches
                )

        try:
            if self.in_process or len(tasks) == 0:
                for index, task in enumerate(tasks):
                    if self.cancelled:
                        break
                    yield from on_arrival(index, search_file(task))
            else:
                yield from self._run_pool(tasks, on_arrival)
            # Release whatever arrived out of order before a cancel (IDs stay unique).
            for index in sorted(arrived):
                yield from release(index)
            summary.cancelled = self.cancelled
            summary.seconds = time.monotonic() - started
            yield Finished(summary)
        except GeneratorExit:
            self.cancel()
            raise
        finally:
            if writer is not None:
                writer.close()

    def _run_pool(
        self,
        tasks: list[FileTask],
        on_arrival: Callable[[int, FileOutcome], Iterator[SearchEvent]],
    ) -> Iterator[SearchEvent]:
        workers = self.workers or os.cpu_count() or 2
        workers = max(1, min(workers, len(tasks)))
        _prepare_spawn()
        # "spawn" is safe with a running GUI and identical on all platforms.
        context = multiprocessing.get_context("spawn")
        executor = cf.ProcessPoolExecutor(
            max_workers=workers,
            mp_context=context,
            initializer=init_worker,
            initargs=(logging.getLogger().getEffectiveLevel(),),
        )
        try:
            # Worker processes are started here, on the first submissions.
            futures = {executor.submit(search_file, task): i for i, task in enumerate(tasks)}
        except (OSError, cf.BrokenExecutor) as exc:
            executor.shutdown(wait=False, cancel_futures=True)
            raise WorkerStartError(f"Could not start the search processes: {exc}") from exc
        pending = set(futures)
        any_arrived = False
        try:
            while pending and not self.cancelled:
                done, pending = cf.wait(pending, timeout=0.1, return_when=cf.FIRST_COMPLETED)
                for future in sorted(done, key=futures.__getitem__):
                    index = futures[future]
                    try:
                        outcome = future.result()
                    except cf.BrokenExecutor as exc:
                        if not any_arrived:
                            # No worker ever delivered a result: they could not start.
                            raise WorkerStartError(
                                f"The search processes could not be started: {exc}"
                            ) from exc
                        log.warning("Worker failed on %s: %s", tasks[index].path, exc)
                        outcome = FileOutcome(tasks[index].path, [], "cannot be read")
                    except Exception as exc:  # worker process died
                        log.warning("Worker failed on %s: %s", tasks[index].path, exc)
                        outcome = FileOutcome(tasks[index].path, [], "cannot be read")
                    any_arrived = True
                    yield from on_arrival(index, outcome)
        except GeneratorExit:
            self.cancel()
            raise
        finally:
            executor.shutdown(wait=not self.cancelled, cancel_futures=True)
