#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
#
# Build the Linux release files: an AppImage and a tar.gz of the program folder.
#
# Runs inside an AlmaLinux 8 container (glibc 2.28), so the result also runs on older
# distributions. Locally:  packaging/linux/build-in-docker.sh
# Output: release/  (relative to the repository root)
#
# The program is built with the pinned standalone Python (packaging/pins.json) and the
# pinned packages (packaging/release-constraints.txt); packaging/collect_licenses.py then
# adds the "licenses" folder and stops the build if any binary has an unknown licence.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

APP_ID="pdf-multifile-searcher"
WORK="${WORK:-/tmp/pdfms-build}"
OUT="$ROOT/release"
pin() { python3.12 -c "import json,sys; d=json.load(open('packaging/pins.json')); print(eval('d' + sys.argv[1]))" "$1"; }

echo "== Installing build dependencies"
# Install documentation too: some packages (X11, xcb) keep their licence files there,
# and collect_licenses.py copies them into the package.
sed -i '/^tsflags=nodocs/d' /etc/dnf/dnf.conf
dnf -y -q install epel-release
# python3.12 only runs the build scripts; the program uses the standalone Python.
dnf -y -q install python3.12 python3.12-pip binutils file findutils tar gzip which \
    fontconfig freetype dbus-libs glib2 libxkbcommon libxkbcommon-x11 \
    mesa-libGL mesa-libEGL libX11 libX11-xcb libxcb xcb-util xcb-util-cursor \
    xcb-util-image xcb-util-keysyms xcb-util-renderutil xcb-util-wm \
    libwayland-client libwayland-cursor libwayland-egl

echo "== Creating the build environment"
rm -rf "$WORK/venv" "$WORK/bootstrap" "$WORK/dist" "$WORK/pyinstaller" "$WORK/AppDir"
mkdir -p "$WORK" "$OUT"
python3.12 -m venv "$WORK/bootstrap"
"$WORK/bootstrap/bin/pip" install --quiet zstandard
PYTHON="$("$WORK/bootstrap/bin/python" packaging/fetch_python.py linux "$WORK")"
"$PYTHON" -m venv "$WORK/venv"
"$WORK/venv/bin/pip" install --quiet --upgrade pip
"$WORK/venv/bin/pip" install --quiet -c packaging/release-constraints.txt "$ROOT" pyinstaller
VERSION="$("$WORK/venv/bin/python" -c 'from importlib.metadata import version; print(version("pdf-multifile-searcher"))')"
echo "Version: $VERSION"

echo "== Building the program folder"
"$WORK/venv/bin/pyinstaller" packaging/pdf-multifile-searcher.spec --noconfirm \
    --distpath "$WORK/dist" --workpath "$WORK/pyinstaller"
BUNDLE="$WORK/dist/$APP_ID"
cp packaging/README-binary.txt "$BUNDLE/README.txt"
"$WORK/venv/bin/python" packaging/collect_licenses.py --bundle "$BUNDLE" --python "$WORK/python"

echo "== Smoke tests"
"$BUNDLE/pdf-multifile-search" --version
COUNT="$("$BUNDLE/pdf-multifile-search" -f tests/data -p Zephyria --no-cache | wc -l)"
[ "$COUNT" -eq 4 ] || { echo "Expected 4 matches, got $COUNT"; exit 1; }
set +e
QT_QPA_PLATFORM=offscreen timeout 8 "$BUNDLE/pdf-multifile-searcher"
STATUS=$?
set -e
[ "$STATUS" -eq 124 ] || { echo "The window program exited early with status $STATUS"; exit 1; }

echo "== tar.gz"
TARBALL="$OUT/$APP_ID-$VERSION-linux-x86_64.tar.gz"
tar -C "$WORK/dist" -czf "$TARBALL" "$APP_ID"

echo "== AppImage"
APPDIR="$WORK/AppDir"
mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/share/applications" \
    "$APPDIR/usr/share/icons/hicolor/256x256/apps" "$APPDIR/usr/share/metainfo"
cp -r "$BUNDLE" "$APPDIR/usr/lib/$APP_ID"
# The AppImage additionally contains the AppImage runtime; add its notices.
"$WORK/venv/bin/python" packaging/collect_licenses.py --bundle "$APPDIR/usr/lib/$APP_ID" \
    --python "$WORK/python" --appimage
cp packaging/linux/$APP_ID.desktop "$APPDIR/$APP_ID.desktop"
cp packaging/linux/$APP_ID.desktop "$APPDIR/usr/share/applications/"
cp packaging/icons/app-icon-256.png "$APPDIR/$APP_ID.png"
cp packaging/icons/app-icon-256.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/$APP_ID.png"
cp packaging/icons/app-icon-256.png "$APPDIR/.DirIcon"
sed "s/@VERSION@/$VERSION/" packaging/linux/$APP_ID.appdata.xml \
    > "$APPDIR/usr/share/metainfo/$APP_ID.appdata.xml"
cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/sh
# Start the window program. For a search without a window, pass --no-gui.
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/pdf-multifile-searcher/pdf-multifile-searcher" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

TOOL="$WORK/appimagetool"
curl -fsSL -o "$TOOL" "$(pin "['appimage']['appimagetool_url']")"
echo "$(pin "['appimage']['appimagetool_sha256']")  $TOOL" | sha256sum -c -
chmod +x "$TOOL"
RUNTIME="$WORK/runtime-x86_64"
curl -fsSL -o "$RUNTIME" "$(pin "['appimage']['runtime_url']")"
echo "$(pin "['appimage']['runtime_sha256']")  $RUNTIME" | sha256sum -c -
APPIMAGE="$OUT/PDF_Multifile_Searcher-$VERSION-x86_64.AppImage"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --no-appstream --runtime-file "$RUNTIME" "$APPDIR" "$APPIMAGE"

echo "== Testing the AppImage"
APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGE" --version | head -1
COUNT="$(APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGE" --no-gui -f tests/data -p Zephyria --no-cache | wc -l)"
[ "$COUNT" -eq 4 ] || { echo "AppImage: expected 4 matches, got $COUNT"; exit 1; }

ls -la "$OUT"
