"""Headless command line: output and exit codes (FR-CLI-06, FR-CLI-08, NFR-TEST-07)."""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from pdf_multifile_searcher import cli


def run_cli(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    try:
        code = cli.main(list(args))
    except SystemExit as exc:
        code = int(exc.code or 0)
    out, err = capsys.readouterr()
    return code, out, err


def test_matches_are_printed_one_per_line(capsys, data_dir: Path) -> None:
    code, out, _ = run_cli(capsys, "-f", str(data_dir), "-p", "Zephyria", "--no-cache")
    lines = out.strip().splitlines()
    assert code == cli.EXIT_MATCHES
    assert len(lines) == 4
    assert all(line.split(":")[1] == "1" for line in lines)
    assert all(line.startswith(str(data_dir)) for line in lines)


def test_no_matches_exit_code(capsys, data_dir: Path) -> None:
    code, out, _ = run_cli(capsys, "-f", str(data_dir), "-p", "xyzzy-nothing", "--no-cache")
    assert code == cli.EXIT_NO_MATCHES and out == ""


@pytest.mark.parametrize(
    "args",
    [
        ("-p", "x"),  # no folder
        ("-f", "."),  # no pattern
        ("-f", ".", "-p", "(", "--regex"),  # invalid regex
    ],
)
def test_usage_errors(capsys, args) -> None:
    code, _, err = run_cli(capsys, *args)
    assert code == cli.EXIT_USAGE
    assert "error" in err


def test_csv_output(capsys, data_dir: Path) -> None:
    code, out, _ = run_cli(
        capsys, "-f", str(data_dir), "-p", "lorem ipsum", "--format", "csv", "--no-cache"
    )
    rows = list(csv.reader(io.StringIO(out)))
    assert code == 0
    assert rows[0] == ["file", "page", "context", "id"]
    assert len(rows) == 3
    assert [r[3] for r in rows[1:]] == ["0", "1"]


def test_skipped_files_go_to_stderr(capsys, tmp_path: Path, data_dir: Path) -> None:
    code, _, err = run_cli(
        capsys, "-f", str(data_dir), "-f", str(tmp_path / "gone"), "-p", "Zephyria", "--no-cache"
    )
    assert code == 0
    assert "skipped:" in err and "gone" in err


def test_options_flags(capsys, data_dir: Path) -> None:
    _, out, _ = run_cli(capsys, "-f", str(data_dir), "-p", "The", "-c", "-w", "--no-cache")
    assert len(out.strip().splitlines()) == 17
