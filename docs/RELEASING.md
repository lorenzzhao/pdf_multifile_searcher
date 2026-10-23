# Releasing

Releases are built and published by the GitHub Actions workflow
[`.github/workflows/release.yml`](../.github/workflows/release.yml).

## Making a release

1. Set the new version in `pyproject.toml` (`version = "X.Y.Z"`).
2. Add a section `## [X.Y.Z] - YYYY-MM-DD` to `CHANGELOG.md`. Its text becomes the
   release notes.
3. Commit, then create and push the tag:

   ```bash
   git tag -a vX.Y.Z -m "Version X.Y.Z"
   git push origin main vX.Y.Z
   ```

The workflow then builds and tests:

- the Linux AppImage and tar.gz (in an AlmaLinux 8 container, glibc 2.28),
- the Windows installer and portable ZIP (including a silent install/uninstall test),
- the Python wheel and sdist.

It publishes a GitHub Release with all files, `SHA256SUMS.txt`, build provenance
attestations and the release notes. A tag that does not match the version in
`pyproject.toml` stops the release.

Pushes to `main` that change packaging files run the same builds and tests without
publishing anything.

## Building locally

- Linux (needs Docker): `packaging/linux/build-in-docker.sh` → `release/`
- Windows (needs Python 3.11+ and Inno Setup 6): `pwsh packaging/windows/build.ps1` → `release\`
- Only the program folder, on any system: `pyinstaller packaging/pdf-multifile-searcher.spec`

After changing the app icon (`src/pdf_multifile_searcher/resources/app-icon.svg`), run
`QT_QPA_PLATFORM=offscreen python packaging/render_icons.py`.

## Licenses in the standalone programs

The release packages contain third-party components, so their license conditions apply
to every release (see `THIRD_PARTY_NOTICES.txt`, section 5). The build takes care of it:

- `packaging/collect_licenses.py` writes the `licenses` folder of each package and stops
  the build if any binary cannot be assigned to a component with a known license, or if
  a Linux system library has a GPL-family license.
- The `sources` job of the release workflow attaches the source archives of the bundled
  LGPL components (Qt, Qt for Python, AppImage runtime, libfuse) to the release.

## Upgrading bundled components

All bundled versions are pinned, because the notices and the attached source code must
match exactly what is in the packages:

- `packaging/release-constraints.txt`: PySide6-Essentials, shiboken6, pypdfium2,
  platformdirs, PyInstaller.
- `packaging/pins.json`: the standalone Python, the Qt version, the source archives
  (URL and SHA-256) and the AppImage tools.

When upgrading Qt, change PySide6-Essentials, shiboken6, `qt_version` and the Qt and
pyside-setup source archives together, then run `python packaging/fetch_qt_notices.py`
to refresh the Qt notices. PySide6 6.10 and later need glibc 2.34, so upgrading beyond
6.9 also raises the minimum Linux version. When the build stops with an unknown binary,
find out which component it belongs to and add its license before adding it to the
rules in `collect_licenses.py`.

## Publishing to PyPI (one-time setup)

The `pypi` job is skipped until it is set up:

1. Sign in at <https://pypi.org> and open *Your projects → Publishing → Add a new pending
   publisher* with:
   - PyPI project name: `pdf-multifile-searcher`
   - Owner: `lorenzzhao`, repository: `pdf_multifile_searcher`
   - Workflow name: `release.yml`, environment name: `pypi`
2. On GitHub, open *Settings → Environments* and create the environment `pypi`.
3. On GitHub, open *Settings → Secrets and variables → Actions → Variables* and add the
   repository variable `PUBLISH_TO_PYPI` with the value `true`.

From the next release on, the workflow uploads the wheel and sdist to PyPI. To publish an
existing release, re-run its workflow run on GitHub.

## Code signing

The Windows programs are not signed. Signing would remove the SmartScreen warning; the
options are listed in the discussion that led to this setup (SignPath Foundation for
open-source projects, Azure Trusted Signing, or a purchased certificate).
