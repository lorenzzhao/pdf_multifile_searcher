#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
#
# Build the Linux release files locally in the same AlmaLinux 8 container as the
# release workflow. Output: release/ in the repository root.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
mkdir -p "$ROOT/release"
docker run --rm \
    -v "$ROOT:/src:ro" -v "$ROOT/release:/out" \
    almalinux:8 bash -c '
        set -e
        cp -r /src /work && cd /work && rm -rf release
        bash packaging/linux/build.sh
        cp release/* /out/
        chown -R '"$(id -u):$(id -g)"' /out
    '
