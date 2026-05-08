"""Platform-independent font discovery.

Linux/macOS: delegates to fc-match (fontconfig CLI, fast).
Windows:     reads the font registry; uses fonttools for codepoint fallback.
"""
import sys
import os
import subprocess

_path_cache = {}     # (family, bold, italic) -> path | None
_fallback_cache = {} # codepoint -> (path, family) | (None, None)


# ── Windows backend ──────────────────────────────────────────────────────────

if sys.platform == 'win32':
    import winreg

    _FONTS_DIR = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts')
    _win_index = None  # {family_lower: {(bold, italic): path}}

    # Fonts known to have broad Unicode coverage — checked first for fallback.
    _PRIORITY_FAMILIES = [
        'segoe ui symbol', 'arial unicode ms',
        'microsoft yahei', 'noto sans', 'unifont',
    ]

    def _build_win_index():
        global _win_index
        _win_index = {}
        key_path = r'SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts'
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        except OSError:
            return
        i = 0
        while True:
            try:
                name, value, _ = winreg.EnumValue(key, i)
            except OSError:
                break
            i += 1
            name = name.split('(')[0].strip()
            bold = italic = False
            for suffix, b, it in [
                (' Bold Italic', True,  True),
                (' Bold',        True,  False),
                (' Italic',      False, True),
            ]:
                if name.endswith(suffix):
                    name = name[:-len(suffix)]
                    bold, italic = b, it
                    break
            family = name.lower()
            path = value if os.path.isabs(value) else os.path.join(_FONTS_DIR, value)
            _win_index.setdefault(family, {})[(bold, italic)] = path
        winreg.CloseKey(key)

    def _resolve_windows(family, bold, italic):
        if _win_index is None:
            _build_win_index()
        styles = _win_index.get(family.lower(), {})
        for b, i in [(bold, italic), (bold, False), (False, False)]:
            if (b, i) in styles:
                return styles[(b, i)]
        # prefix fallback
        prefix = family.lower()
        for fam, styles in _win_index.items():
            if fam.startswith(prefix) and styles:
                return next(iter(styles.values()))
        return None

    def _fallback_windows(codepoint):
        try:
            from fonttools.ttLib import TTFont
        except ImportError:
            return None, None
        if _win_index is None:
            _build_win_index()

        all_families = list(_win_index.keys())
        priority = [f for f in _PRIORITY_FAMILIES if f in _win_index]
        rest = [f for f in all_families if f not in _PRIORITY_FAMILIES]

        for family in priority + rest:
            path = next(iter(_win_index[family].values()))
            try:
                font = TTFont(path, lazy=True)
                cmap = font.getBestCmap()
                if cmap and codepoint in cmap:
                    display_name = font['name'].getDebugName(1) or family
                    return path, display_name
            except Exception:
                continue
        return None, None


# ── Public API ────────────────────────────────────────────────────────────────

def resolve_font_path(family, bold, italic):
    """Return the file path for the best matching font, or None."""
    key = (family, bold, italic)
    if key in _path_cache:
        return _path_cache[key]

    if sys.platform == 'win32':
        path = _resolve_windows(family, bold, italic)
    else:
        pattern = family
        if bold and italic:
            pattern += ':bold:italic'
        elif bold:
            pattern += ':bold'
        elif italic:
            pattern += ':italic'
        try:
            result = subprocess.run(
                ['fc-match', pattern, '--format=%{file}'],
                capture_output=True, text=True, timeout=2)
            path = result.stdout.strip() or None
        except (FileNotFoundError, subprocess.TimeoutExpired):
            path = None

    _path_cache[key] = path
    return path


def find_fallback_info(codepoint):
    """Return (path, family) of a font covering codepoint, or (None, None)."""
    if codepoint in _fallback_cache:
        return _fallback_cache[codepoint]

    if sys.platform == 'win32':
        info = _fallback_windows(codepoint)
    else:
        try:
            result = subprocess.run(
                ['fc-match', f':charset={codepoint:04x}', '--format=%{file}\t%{family}'],
                capture_output=True, text=True, timeout=2)
            line = result.stdout.strip()
            if '\t' in line:
                path, fam = line.split('\t', 1)
                info = (path or None, fam.split(',')[0].strip() or None)
            else:
                info = (None, None)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            info = (None, None)

    _fallback_cache[codepoint] = info
    return info
