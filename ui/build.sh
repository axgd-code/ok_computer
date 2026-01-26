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

# Run PyInstaller including templates and static folders
python -m PyInstaller --name "$NAME" --onefile --noconfirm --clean \
  --noconsole \
  --add-data "templates${SEP}templates" \
  --add-data "static${SEP}static" \
  --add-data "${HERE}/../src${SEP}src" \
  --collect-submodules flask \
  --hidden-import socket \
  --hidden-import webview \
  app.py

echo "Built: dist/$NAME"
