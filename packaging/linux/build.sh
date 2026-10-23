#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
#
# Build the Linux release files: an AppImage and a tar.gz of the program folder.
#
# Runs inside an AlmaLinux 8 container (glibc 2.28), so the result also runs on older
# distributions. Locally:  packaging/linux/build-in-docker.sh
# Output: release/  (relative to the repository root)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

APPIMAGETOOL_URL="https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage"
APPIMAGETOOL_SHA256="ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"
RUNTIME_URL="https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-x86_64"
RUNTIME_SHA256="2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d"
APP_ID="pdf-multifile-searcher"
WORK="${WORK:-/tmp/pdfms-build}"
OUT="$ROOT/release"

echo "== Installing build dependencies"
dnf -y -q install epel-release
dnf -y -q install python3.12 python3.12-pip binutils file findutils tar gzip which \
    fontconfig freetype dbus-libs glib2 libxkbcommon libxkbcommon-x11 \
    mesa-libGL mesa-libEGL libX11 libX11-xcb libxcb xcb-util xcb-util-cursor \
    xcb-util-image xcb-util-keysyms xcb-util-renderutil xcb-util-wm \
    libwayland-client libwayland-cursor libwayland-egl

echo "== Creating the build environment"
rm -rf "$WORK"
mkdir -p "$WORK" "$OUT"
python3.12 -m venv "$WORK/venv"
"$WORK/venv/bin/pip" install --quiet --upgrade pip
"$WORK/venv/bin/pip" install --quiet "$ROOT" pyinstaller
VERSION="$("$WORK/venv/bin/python" -c 'from importlib.metadata import version; print(version("pdf-multifile-searcher"))')"
echo "Version: $VERSION"

echo "== Building the program folder"
"$WORK/venv/bin/pyinstaller" packaging/pdf-multifile-searcher.spec --noconfirm \
    --distpath "$WORK/dist" --workpath "$WORK/pyinstaller"
BUNDLE="$WORK/dist/$APP_ID"
cp -r "$BUNDLE/_internal/licenses" "$BUNDLE/licenses"
cp packaging/README-binary.txt "$BUNDLE/README.txt"

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
cp packaging/linux/$APP_ID.desktop "$APPDIR/$APP_ID.desktop"
cp packaging/linux/$APP_ID.desktop "$APPDIR/usr/share/applications/"
cp packaging/icons/app-icon-256.png "$APPDIR/$APP_ID.png"
cp packaging/icons/app-icon-256.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/$APP_ID.png"
cp packaging/icons/app-icon-256.png "$APPDIR/.DirIcon"
sed "s/@VERSION@/$VERSION/" packaging/linux/$APP_ID.appdata.xml \
    > "$APPDIR/usr/share/metainfo/$APP_ID.appdata.xml"
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
# Start the window program. For a search without a window, pass --no-gui.
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/pdf-multifile-searcher/pdf-multifile-searcher" "$@"
EOF
chmod +x "$APPDIR/AppRun"

TOOL="$WORK/appimagetool"
curl -fsSL -o "$TOOL" "$APPIMAGETOOL_URL"
echo "$APPIMAGETOOL_SHA256  $TOOL" | sha256sum -c -
chmod +x "$TOOL"
RUNTIME="$WORK/runtime-x86_64"
curl -fsSL -o "$RUNTIME" "$RUNTIME_URL"
echo "$RUNTIME_SHA256  $RUNTIME" | sha256sum -c -
APPIMAGE="$OUT/PDF_Multifile_Searcher-$VERSION-x86_64.AppImage"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --no-appstream --runtime-file "$RUNTIME" "$APPDIR" "$APPIMAGE"

echo "== Testing the AppImage"
APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGE" --version | head -1
COUNT="$(APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGE" --no-gui -f tests/data -p Zephyria --no-cache | wc -l)"
[ "$COUNT" -eq 4 ] || { echo "AppImage: expected 4 matches, got $COUNT"; exit 1; }

ls -la "$OUT"
