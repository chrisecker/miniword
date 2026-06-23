# fontfinder.py resolves every non-default-Latin font (and the primary font
# path itself, on macOS/Linux) by shelling out to `fc-match`. PyInstaller's
# static analysis can't see a subprocess.run(['fc-match', ...]) call, so the
# binary never gets bundled and font lookup silently breaks on a machine
# without Homebrew's fontconfig (Latin text still renders via Cairo's native
# fallback, but anything needing actual font *resolution* -- CJK, Hangul,
# Greek not in the default font, etc. -- falls back to .notdef boxes).
set -euo pipefail

APP="$1"  # path to MiniWord.app
FRAMEWORKS="$APP/Contents/Frameworks"
FONTCONFIG_DIR="$APP/Contents/Resources/fontconfig"
FC_PREFIX="$(brew --prefix fontconfig)"
HOMEBREW_PREFIX="$(brew --prefix)"

mkdir -p "$FRAMEWORKS" "$FONTCONFIG_DIR"

# fc-match itself: only needs libfontconfig + libintl, both already bundled
# into Frameworks by bundle_cairo_macos.sh (cairo depends on fontconfig too).
cp "$FC_PREFIX/bin/fc-match" "$FRAMEWORKS/fc-match"
chmod +w "$FRAMEWORKS/fc-match"

# @loader_path (not @executable_path): fc-match runs as its own subprocess,
# so "the calling executable" is fc-match itself, not MiniWord. Both deps
# already sit in this same Frameworks dir.
for dep in libfontconfig libintl; do
  old=$(otool -L "$FRAMEWORKS/fc-match" | awk -v d="$dep" '$1 ~ d {print $1}')
  if [ -n "$old" ]; then
    name=$(basename "$old")
    install_name_tool -change "$old" "@loader_path/$name" "$FRAMEWORKS/fc-match"
  fi
done
codesign --force --sign - "$FRAMEWORKS/fc-match"

# fonts.conf already points at the real macOS system font directories
# (/System/Library/Fonts, /Library/Fonts, ~/Library/Fonts) -- bundle it
# as-is, conf.d included, instead of writing a config from scratch. Its
# Homebrew-absolute <cachedir> is simply skipped at runtime if missing;
# fontconfig falls through to the next (~/.cache/fontconfig), which is
# always writable.
# lives under the shared Homebrew prefix, not the per-formula opt path
# used for the binary above.
cp -R "$HOMEBREW_PREFIX/etc/fonts/." "$FONTCONFIG_DIR/"
