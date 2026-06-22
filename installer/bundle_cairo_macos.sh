#!/bin/bash
# cairocffi loads cairo via ctypes dlopen-by-name at runtime, so
# PyInstaller's static dependency analysis never sees it and never
# copies it (or its own Homebrew dependency tree) into the .app bundle.
# Without this step, the released .app only works on machines that
# happen to have Homebrew's cairo installed at the same prefix used to
# build it.
set -euo pipefail

APP="$1"  # path to miniword.app
FRAMEWORKS="$APP/Contents/Frameworks"
SRC_DIR="$(mktemp -d)"

mkdir -p "$FRAMEWORKS"
cp "$(brew --prefix cairo)/lib/libcairo.2.dylib" "$SRC_DIR/libcairo.2.dylib"

# dylibbundler corrupts the target when -x points inside -d, so the
# source copy lives outside Frameworks; dylibbundler then writes the
# relinked dependencies (but not the -x target itself) into Frameworks.
# NOTE: deliberately -of (overwrite files), not -od (overwrite dir) --
# -od wipes the *entire* destination dir first, which would delete the
# Python.framework and wxWidgets libraries PyInstaller already put there.
dylibbundler -of -cd -b \
  -x "$SRC_DIR/libcairo.2.dylib" \
  -d "$FRAMEWORKS" \
  -p "@executable_path/../Frameworks/"

# dylibbundler only fixes up -x in place; it has to be copied in manually.
cp "$SRC_DIR/libcairo.2.dylib" "$FRAMEWORKS/libcairo.2.dylib"
chmod +w "$FRAMEWORKS/libcairo.2.dylib"
install_name_tool -id "@executable_path/../Frameworks/libcairo.2.dylib" "$FRAMEWORKS/libcairo.2.dylib"
codesign --force --sign - "$FRAMEWORKS/libcairo.2.dylib"

rm -rf "$SRC_DIR"
