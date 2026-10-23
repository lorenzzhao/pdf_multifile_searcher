# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""Assemble the "licenses" folder of a standalone package and check its completeness.

Run with the Python of the build environment (the one PyInstaller used), after
PyInstaller and before packing:

    python packaging/collect_licenses.py --bundle DIR --python DIR [--appimage]

--bundle   the program folder built by PyInstaller
--python   the unpacked python-build-standalone "python" folder (packaging/fetch_python.py)
--appimage also add the notices of the AppImage runtime (Linux AppImage only)

Every binary in the bundle must belong to a known component (the program's Python, Qt and
PySide6, PDFium, the Microsoft C++ runtime on Windows, or a system library on Linux whose
licence can be read from its RPM package). Anything else, and any system library under a
GPL-family licence, stops the build, so no component can enter a package unnoticed.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path

from pins import PACKAGING, ROOT, load_pins

PINS = load_pins()
REPOSITORY = "https://github.com/lorenzzhao/pdf_multifile_searcher"
BUNDLED_DISTRIBUTIONS = (
    "pdf-multifile-searcher",
    "PySide6-Essentials",
    "shiboken6",
    "pypdfium2",
    "platformdirs",
    "pyinstaller",
)
WINDOWS = sys.platform.startswith("win")

# Windows: which component each DLL or extension module belongs to (relative paths,
# lower case, "/" separators). Checked in order; the first match wins.
WINDOWS_RULES: list[tuple[str, str]] = [
    ("pyside6/msvcp140*.dll", "msvc"),
    ("pyside6/vcruntime140*.dll", "msvc"),
    ("pyside6/concrt140.dll", "msvc"),
    ("shiboken6/msvcp140*.dll", "msvc"),
    ("shiboken6/vcruntime140*.dll", "msvc"),
    ("vcruntime140*.dll", "msvc"),
    ("msvcp140*.dll", "msvc"),
    ("pyside6/*", "qt"),
    ("shiboken6/*", "qt"),
    ("pypdfium2_raw/*", "pdfium"),
    ("python3*.dll", "python"),
    ("libcrypto-3*.dll", "python"),
    ("libssl-3*.dll", "python"),
    ("libffi-*.dll", "python"),
    ("sqlite3.dll", "python"),
    ("*.pyd", "python"),
]

# System packages whose RPM licence tag names a GPL-family licence for parts that are
# not in the shipped library. Each entry says why the shipped library is not affected.
GPL_TAG_EXCEPTIONS = {
    "libzstd": "The zstd library is BSD-3-Clause OR GPL-2.0 (upstream dual licence); the "
    "GPL-2.0-only parts of the package are command-line tools, which are not shipped.",
}

MSVC_NOTICE = """\
Microsoft Visual C++ runtime
============================

The files vcruntime140*.dll, msvcp140*.dll and concrt140.dll in this package are the
Microsoft Visual C++ runtime. They are "Distributable Code" under the Microsoft Software
License Terms for Microsoft Visual Studio and may be redistributed together with
programs that use them; they remain the property of Microsoft Corporation and may only
be used together with this program. For the GNU licences they are System Libraries.
"""


def is_binary(path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    name = path.name.lower()
    if WINDOWS:
        return name.endswith((".dll", ".pyd"))
    return bool(re.search(r"\.so(\.\d+)*$", name))


def copy_tree_files(files: list[tuple[Path, Path]]) -> None:
    for source, target in files:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def distribution_license_files(name: str, out: Path) -> list[tuple[Path, Path]]:
    """License files of an installed distribution, keeping their folder layout."""
    dist = metadata.distribution(name)
    result = []
    for file in dist.files or []:
        parts = Path(str(file)).parts
        if "licenses" in parts:
            sub = Path(*parts[parts.index("licenses") + 1 :])
        elif re.match(r"(COPYING|LICEN[CS]E)", parts[-1], re.I) and ".dist-info" in str(file):
            sub = Path(parts[-1])
        else:
            continue
        result.append((Path(str(dist.locate_file(file))), out / sub))
    if not result:
        raise SystemExit(f"No license files found for {name}")
    return result


# -- checks of the build environment ---------------------------------------------------


def check_versions() -> dict[str, str]:
    constraints = {}
    for line in (PACKAGING / "release-constraints.txt").read_text().splitlines():
        line = line.split("#")[0].strip()
        if "==" in line:
            name, version = line.split("==")
            constraints[name.strip().lower()] = version.strip()
    versions = {}
    for name in BUNDLED_DISTRIBUTIONS:
        version = metadata.version(name)
        pinned = constraints.get(name.lower())
        if pinned is not None and version != pinned:
            raise SystemExit(f"{name} {version} is installed, but {pinned} is pinned")
        versions[name] = version
    from PySide6.QtCore import qVersion

    if qVersion() != PINS["qt_version"]:
        raise SystemExit(f"Qt {qVersion()} is installed, but {PINS['qt_version']} is pinned")
    versions["Qt"] = qVersion()
    if sys.version.split()[0] != PINS["python"]["version"]:
        raise SystemExit(f"Python {sys.version.split()[0]} runs the build, not the pinned one")
    return versions


# -- Python ------------------------------------------------------------------------------


def python_license_files(python_dir: Path, bundle: Path, out: Path) -> list[tuple[Path, Path]]:
    """Licences of CPython and of the libraries linked into the bundled modules."""
    info = json.loads((python_dir / "PYTHON.json").read_text(encoding="utf-8"))
    bundled_names = {p.name.lower().split(".")[0] for p in bundle.rglob("*") if is_binary(p)}
    paths = {info["license_path"]}
    import ssl

    openssl_3 = ssl.OPENSSL_VERSION.startswith("OpenSSL 3")
    for name, variants in info["build_info"]["extensions"].items():
        if name not in sys.builtin_module_names and name.lower() not in bundled_names:
            continue
        for variant in variants:
            for path in variant.get("license_paths") or []:
                if openssl_3 and "openssl-1.1" in path:
                    continue  # the archive lists both; this build uses OpenSSL 3
                paths.add(path)
    import zlib

    result = []
    for p in sorted(paths):
        if not (python_dir / p).exists() and p.endswith("LICENSE.zlib-ng.txt"):
            # The archive's metadata names zlib-ng, but this build uses classic zlib and
            # ships its licence as LICENSE.zlib.txt; accept that only if it is true.
            if "ng" in zlib.ZLIB_RUNTIME_VERSION:
                raise SystemExit("zlib-ng is used, but its licence file is missing")
            p = p.replace("zlib-ng", "zlib")
        if not (python_dir / p).exists():
            raise SystemExit(f"Licence file listed in PYTHON.json is missing: {p}")
        result.append((python_dir / p, out / Path(p).name))
    return result


# -- system libraries (Linux) -------------------------------------------------------------


def rpm(*args: str) -> str:
    return subprocess.run(["rpm", *args], capture_output=True, text=True, check=True).stdout


def system_library_notices(libraries: list[Path], out: Path) -> list[str]:
    rows: dict[str, list[str]] = {}
    problems = []
    for library in libraries:
        candidates = [Path(d) / library.name for d in ("/usr/lib64", "/lib64", "/usr/lib")]
        host = next((c for c in candidates if c.exists()), None)
        if host is None:
            problems.append(f"{library.name}: not found on the build system")
            continue
        try:
            package = rpm("-qf", "--qf", "%{NAME}", str(host)).strip()
        except subprocess.CalledProcessError:
            problems.append(f"{library.name}: does not belong to an RPM package")
            continue
        version, license_tag, source_rpm = rpm(
            "-q", "--qf", "%{VERSION}-%{RELEASE}\t%{LICENSE}\t%{SOURCERPM}", package
        ).split("\t")
        if re.search(r"\b(A|L)?GPL", license_tag) and package not in GPL_TAG_EXCEPTIONS:
            problems.append(f"{library.name}: package {package} is licensed {license_tag}")
            continue
        license_files = [Path(p) for p in rpm("-qL", package).split() if Path(p).is_file()]
        if not license_files:
            # Older packages list their licence among the documentation files.
            license_files = [
                Path(p)
                for p in rpm("-qd", package).split()
                if re.match(r"(COPYING|COPYRIGHT|LICEN[CS]E)", Path(p).name, re.I)
                and Path(p).is_file()
            ]
        if not license_files:
            # Packages built from the same source package share the licence files.
            for sibling in rpm("-qa", "--qf", "%{NAME}\t%{SOURCERPM}\n").splitlines():
                name, _, srpm = sibling.partition("\t")
                if srpm == source_rpm and name != package:
                    license_files += [
                        Path(p) for p in rpm("-qL", name).split() if Path(p).is_file()
                    ]
        if not license_files:
            # Packages without any licence file: upstream texts kept in the repository.
            stored = PACKAGING / "licenses" / "system" / package
            license_files = sorted(stored.iterdir()) if stored.is_dir() else []
        if not license_files:
            problems.append(f"{library.name}: package {package} has no licence files")
            continue
        for file in license_files:
            target = out / package / file.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, target)
        row = rows.setdefault(package, [package, version, license_tag, source_rpm, ""])
        row[4] = ", ".join(sorted({*row[4].split(", "), library.name} - {""}))
    if problems:
        raise SystemExit("System libraries that cannot be shipped:\n  " + "\n  ".join(problems))
    lines = [
        "System libraries included in this package",
        "==========================================",
        "",
        "These libraries were taken from the build system (AlmaLinux 8) because not every",
        "Linux system provides them. Their licence files are in the folder of each package.",
        "",
        f"{'Package':<24} {'Version':<22} {'Licence':<30} Libraries",
    ]
    for package, version, license_tag, source_rpm, libs in sorted(rows.values()):
        lines.append(f"{package:<24} {version:<22} {license_tag:<30} {libs}")
        lines.append(f"{'':<24} source package: {source_rpm}")
        if package in GPL_TAG_EXCEPTIONS:
            lines.append(f"{'':<24} note: {GPL_TAG_EXCEPTIONS[package]}")
    (out / "SYSTEM_LIBRARIES.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return sorted(rows)


# -- classification of the bundle --------------------------------------------------------


def classify(bundle: Path) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = {}
    unknown = []
    for path in sorted(bundle.rglob("*")):
        if not is_binary(path) or "licenses" in path.relative_to(bundle).parts:
            continue
        rel = path.relative_to(bundle)
        parts = rel.parts[1:] if rel.parts[0] == "_internal" else rel.parts
        key = "/".join(parts).lower()
        if WINDOWS:
            group = next((g for pattern, g in WINDOWS_RULES if fnmatch.fnmatch(key, pattern)), None)
        elif key.startswith(("pyside6/", "shiboken6/")):
            group = "qt"
        elif key.startswith("pypdfium2_raw/"):
            group = "pdfium"
        elif key.startswith("libpython3") or ".cpython-" in key:
            group = "python"
        elif "/" not in key:
            group = "system"
        else:
            group = None
        if group is None:
            unknown.append(key)
        else:
            groups.setdefault(group, []).append(path)
    if unknown:
        raise SystemExit("Binaries of unknown origin in the bundle:\n  " + "\n  ".join(unknown))
    return groups


# -- texts ------------------------------------------------------------------------------


def sources_text(version: str, versions: dict[str, str], appimage: bool) -> str:
    platform = "windows" if WINDOWS else "linux"
    tag = f"v{version}"
    release = f"{REPOSITORY}/releases/tag/{tag}"
    lines = [
        "Source code",
        "===========",
        "",
        f"PDF Multifile Searcher {version} (AGPL-3.0-or-later):",
        f"  {REPOSITORY}/tree/{tag}",
        "  The release page also has it as a source archive. The scripts that built this",
        "  package are in the packaging folder of the source code.",
        "",
        "This package contains libraries under the GNU LGPL. Their complete source code, in",
        "exactly the version contained here, is attached to the release of this version:",
        f"  {release}",
        "",
    ]
    for source in PINS["sources"]:
        if platform in source["packages"] or (appimage and "appimage" in source["packages"]):
            lines += [
                f"  {source['name']}",
                f"    {source['covers']}",
                f"    original location: {source['url']}",
                f"    SHA-256: {source['sha256']}",
                "",
            ]
    lines += [
        f"Qt {versions['Qt']}, PySide6 {versions['PySide6-Essentials']} and shiboken6",
        f"{versions['shiboken6']} are used without changes, as published by the Qt Project.",
        "To use a modified Qt, replace the Qt libraries in the PySide6 folder of this",
        "package with your own build of the same Qt version.",
        "",
        "If any of these archives is no longer available at the release page, open an",
        f"issue at {REPOSITORY}/issues and the source code will be provided, for at",
        "least three years after this release.",
        "",
        "Components under permissive licences (Python, PDFium, platformdirs and others)",
        "have no source code obligation; their notices are in this folder.",
    ]
    return "\n".join(lines) + "\n"


def readme_text(groups: dict[str, list[Path]], system_packages: list[str], appimage: bool) -> str:
    lines = [
        "Licences of PDF Multifile Searcher and of the components in this package",
        "=========================================================================",
        "",
        "LICENSE                    The program: GNU AGPL-3.0-or-later",
        "THIRD_PARTY_NOTICES.txt    Overview of all third-party components",
        "SOURCES.txt                Where to get the source code of this package",
        "VERSIONS.txt               Exact versions of the bundled components",
        "GPL-3.0.txt, LGPL-3.0.txt  Licences of Qt for Python (LGPL-3.0, which builds on",
        "                           the GPL-3.0)",
        "qt/                        Third-party notices of the Qt libraries"
        + (" and ICU" if any("icu" in p.name.lower() for p in groups.get("qt", [])) else ""),
        "python/                    Python and the libraries built into it",
        "pypdfium2/                 pypdfium2, PDFium and PDFium's bundled libraries",
        "platformdirs/              platformdirs",
        "pyinstaller/               PyInstaller; its program launcher is part of the",
        "                           pdf-multifile-searcher and pdf-multifile-search programs",
    ]
    if system_packages:
        lines.append("system-libraries/           Linux system libraries included in this package")
    if "msvc" in groups:
        lines.append("microsoft/                 Microsoft Visual C++ runtime")
    if appimage:
        lines.append("appimage-runtime/           The AppImage runtime that starts this AppImage")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--appimage", action="store_true")
    args = parser.parse_args()
    bundle: Path = args.bundle.resolve()
    out = bundle / "licenses"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()

    versions = check_versions()
    groups = classify(bundle)

    files: list[tuple[Path, Path]] = [
        (ROOT / "LICENSE", out / "LICENSE"),
        (ROOT / "THIRD_PARTY_NOTICES.txt", out / "THIRD_PARTY_NOTICES.txt"),
        (PACKAGING / "licenses" / "GPL-3.0.txt", out / "GPL-3.0.txt"),
        (PACKAGING / "licenses" / "LGPL-3.0.txt", out / "LGPL-3.0.txt"),
        (
            PACKAGING / "licenses" / "QT_THIRD_PARTY_NOTICES.txt",
            out / "qt" / "QT_THIRD_PARTY_NOTICES.txt",
        ),
    ]
    notices = (PACKAGING / "licenses" / "QT_THIRD_PARTY_NOTICES.txt").read_text(encoding="utf-8")
    if f"Qt {PINS['qt_version']})" not in notices.splitlines()[1]:
        raise SystemExit("QT_THIRD_PARTY_NOTICES.txt is not for the pinned Qt version")
    if any("icu" in p.name.lower() for p in groups.get("qt", [])):
        files.append((PACKAGING / "licenses" / "ICU-LICENSE.txt", out / "qt" / "ICU-LICENSE.txt"))
    files += python_license_files(args.python.resolve(), bundle, out / "python")
    files += distribution_license_files("pypdfium2", out / "pypdfium2")
    files += distribution_license_files("platformdirs", out / "platformdirs")
    files += distribution_license_files("pyinstaller", out / "pyinstaller")
    if args.appimage:
        for file in sorted((PACKAGING / "licenses" / "appimage-runtime").iterdir()):
            files.append((file, out / "appimage-runtime" / file.name))
    copy_tree_files(files)

    system_packages: list[str] = []
    if "system" in groups:
        system_packages = system_library_notices(groups["system"], out / "system-libraries")
    if "msvc" in groups:
        (out / "microsoft").mkdir()
        (out / "microsoft" / "MSVC-RUNTIME.txt").write_text(MSVC_NOTICE, encoding="utf-8")

    version = versions["pdf-multifile-searcher"]
    python_build = PINS["python"]["build"]
    version_lines = [f"Python {sys.version.split()[0]} ({python_build})"]
    version_lines += [f"{name} {v}" for name, v in versions.items()]
    (out / "VERSIONS.txt").write_text("\n".join(version_lines) + "\n", encoding="utf-8")
    (out / "SOURCES.txt").write_text(sources_text(version, versions, args.appimage), "utf-8")
    (out / "README.txt").write_text(readme_text(groups, system_packages, args.appimage), "utf-8")

    counts = ", ".join(f"{g}: {len(p)}" for g, p in sorted(groups.items()))
    print(f"Licences collected in {out} ({counts}; system packages: {len(system_packages)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
