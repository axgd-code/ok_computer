#!/usr/bin/env bash
set -euo pipefail

# Build standalone executable for current platform using PyInstaller
# Usage: ./build.sh [name]
NAME=${1:-ok_computer_ui}
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

# Create venv and install
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip
# Install runtime and build requirements (build-only deps in requirements.conf)
pip install -r requirements.txt -r requirements.conf

# Determine add-data separator (':' on Unix, ';' on Windows)
SEP=:
case "$(uname -s)" in
  MINGW*|CYGWIN*|MSYS*) SEP=';';;
  *) SEP=':';;
esac

ICON_ARG=()
if [ "$(uname -s)" = "Darwin" ]; then
  ICONSET_DIR="${HERE}/assets/logo.iconset"
  ICON_ICNS="${HERE}/assets/logo.icns"
  LOGO_SVG="${HERE}/static/img/logo.svg"
  mkdir -p "${HERE}/assets"

  if [ -f "$LOGO_SVG" ] && command -v sips >/dev/null 2>&1 && command -v iconutil >/dev/null 2>&1; then
    rm -rf "$ICONSET_DIR"
    mkdir -p "$ICONSET_DIR"

    TMP_BASE_PNG="${HERE}/assets/logo_base.png"
    TMP_PNG="${HERE}/assets/logo_1024.png"
    # Two-step conversion keeps alpha and centers correctly on target canvas.
    sips -s format png "$LOGO_SVG" --out "$TMP_BASE_PNG" >/dev/null 2>&1 || true
    sips -z 1024 1024 "$TMP_BASE_PNG" --out "$TMP_PNG" >/dev/null 2>&1 || true

    if [ -f "$TMP_PNG" ]; then
      sips -z 16 16 "$TMP_PNG" --out "$ICONSET_DIR/icon_16x16.png" >/dev/null
      sips -z 32 32 "$TMP_PNG" --out "$ICONSET_DIR/icon_16x16@2x.png" >/dev/null
      sips -z 32 32 "$TMP_PNG" --out "$ICONSET_DIR/icon_32x32.png" >/dev/null
      sips -z 64 64 "$TMP_PNG" --out "$ICONSET_DIR/icon_32x32@2x.png" >/dev/null
      sips -z 128 128 "$TMP_PNG" --out "$ICONSET_DIR/icon_128x128.png" >/dev/null
      sips -z 256 256 "$TMP_PNG" --out "$ICONSET_DIR/icon_128x128@2x.png" >/dev/null
      sips -z 256 256 "$TMP_PNG" --out "$ICONSET_DIR/icon_256x256.png" >/dev/null
      sips -z 512 512 "$TMP_PNG" --out "$ICONSET_DIR/icon_256x256@2x.png" >/dev/null
      sips -z 512 512 "$TMP_PNG" --out "$ICONSET_DIR/icon_512x512.png" >/dev/null
      sips -z 1024 1024 "$TMP_PNG" --out "$ICONSET_DIR/icon_512x512@2x.png" >/dev/null

      iconutil -c icns "$ICONSET_DIR" -o "$ICON_ICNS" >/dev/null 2>&1 || true
    fi
  fi

  if [ -f "$ICON_ICNS" ]; then
    ICON_ARG=(--icon "$ICON_ICNS")
    echo "Using app icon: $ICON_ICNS"
  else
    echo "No .icns icon generated; building without custom app icon."
  fi
fi

# Run PyInstaller including templates and static folders
# Use --onedir so the app doesn't have to decompress on every launch.
python -m PyInstaller --name "$NAME" --onedir --noconfirm --clean \
  --noconsole \
  "${ICON_ARG[@]}" \
  --add-data "../.env.example${SEP}." \
  --add-data "templates${SEP}templates" \
  --add-data "static${SEP}static" \
  --add-data "${HERE}/../src${SEP}src" \
  --collect-submodules flask \
  --hidden-import socket \
  --hidden-import webview \
  app.py

if [ "$(uname -s)" = "Darwin" ]; then
  echo "Built: dist/${NAME}.app"
else
  echo "Built: dist/${NAME}/"
fi
