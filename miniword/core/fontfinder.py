"""Platform-independent font discovery.

Linux/macOS: delegates to fc-match (fontconfig CLI, fast).
Windows:     uses the FontLink registry for script fallback, fonttools for
             codepoint verification.  Font files are opened on-demand and
             cached so each file is read at most once per session.
"""
import sys
import os
import subprocess

_path_cache = {}     # (family, bold, italic) -> path | None
_fallback_cache = {} # codepoint -> (path, family) | (None, None)


# ── Windows backend ──────────────────────────────────────────────────────────

if sys.platform == 'win32':
    import winreg
    import threading

    try:
        from fontTools.ttLib import TTFont as _TTFont
    except ImportError:
        try:
            from fonttools.ttLib import TTFont as _TTFont
        except ImportError:
            _TTFont = None
            print(
                'Warning: fonttools not found — font fallback for non-Latin '
                'scripts disabled on Windows.  Install with: pip install fonttools',
                file=sys.stderr,
            )

    _FONTS_DIR = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts')
    _win_index = None      # {family_lower: {(bold, italic): path}}
    _win_font_link = None  # family_lower -> [(path, display_name), ...]
    _win_coverage = {}     # path -> [(codepoint_set, display_name)] — on-demand
    _preload_thread = None

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
            path = value if os.path.isabs(value) else os.path.join(_FONTS_DIR, value)
            # Registry entries like "MS Gothic & MS UI Gothic & MS PGothic" list
            # several family names for one file — register each part individually.
            for part in name.split('&'):
                family = part.strip().lower()
                if family:
                    _win_index.setdefault(family, {})[(bold, italic)] = path
        winreg.CloseKey(key)

    def _build_font_link_index():
        r"""Read FontLink\SystemLink into _win_font_link.

        Each entry is a REG_MULTI_SZ of strings like
        'MSGOTHIC.TTC,MS UI Gothic' or 'MALGUN.TTF,Malgun Gothic,128,96'.
        """
        global _win_font_link
        _win_font_link = {}
        key_path = r'SOFTWARE\Microsoft\Windows NT\CurrentVersion\FontLink\SystemLink'
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        except OSError:
            return
        i = 0
        while True:
            try:
                name, entries, _ = winreg.EnumValue(key, i)
            except OSError:
                break
            i += 1
            chain = []
            for entry in entries:
                parts = entry.split(',')
                if len(parts) < 2:
                    continue
                filename = parts[0].strip()
                display = parts[1].strip()
                path = (filename if os.path.isabs(filename)
                        else os.path.join(_FONTS_DIR, filename))
                chain.append((path, display))
            _win_font_link[name.lower()] = chain
        winreg.CloseKey(key)
        _start_preload()

    def _preload_font_link_coverage():
        if _TTFont is None:
            return
        for path, _ in _font_link_candidates():
            if path not in _win_coverage:
                _coverage_for_path(path)

    def _start_preload():
        global _preload_thread
        if _preload_thread is not None:
            return
        _preload_thread = threading.Thread(
            target=_preload_font_link_coverage,
            daemon=True,
            name='fontlink-preload',
        )
        _preload_thread.start()

    def _coverage_for_path(path):
        """Return cached [(codepoint_set, display_name)] for path.

        Reads and caches the cmap of every sub-font in the file the first
        time it is requested; subsequent calls are a dict lookup.
        """
        if path in _win_coverage:
            return _win_coverage[path]
        entries = []
        if path.lower().endswith('.ttc'):
            n = 0
            while True:
                try:
                    font = _TTFont(path, fontNumber=n, lazy=True)
                    cmap = font.getBestCmap()
                    name = font['name'].getDebugName(1) or ''
                    entries.append((set(cmap.keys()) if cmap else set(), name))
                    n += 1
                except Exception:
                    break
        else:
            try:
                font = _TTFont(path, lazy=True)
                cmap = font.getBestCmap()
                name = font['name'].getDebugName(1) or ''
                entries.append((set(cmap.keys()) if cmap else set(), name))
            except Exception:
                pass
        _win_coverage[path] = entries
        return entries

    def _font_link_candidates():
        """Ordered list of (path, display_name) from the FontLink registry.

        Uses the chains of 'Tahoma' and 'Segoe UI' as representative
        references — they together cover all common scripts on Windows.
        Duplicates are removed while preserving order.
        """
        seen = set()
        candidates = []
        for ref in ('tahoma', 'segoe ui', 'microsoft sans serif'):
            for path, name in _win_font_link.get(ref, []):
                if path not in seen:
                    seen.add(path)
                    candidates.append((path, name))
        return candidates

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
        if _TTFont is None:
            return None, None

        if _win_index is None:
            _build_win_index()
        if _win_font_link is None:
            _build_font_link_index()

        # Fast path: check FontLink candidates (typically ~9 fonts, no pre-scan needed)
        for path, _ in _font_link_candidates():
            for codepoint_set, display_name in _coverage_for_path(path):
                if codepoint in codepoint_set:
                    return path, display_name

        # Slow path: check every installed font (exotic scripts, user-installed fonts)
        link_paths = {p for p, _ in _font_link_candidates()}
        for styles in _win_index.values():
            path = next(iter(styles.values()))
            if path in link_paths:
                continue
            for codepoint_set, display_name in _coverage_for_path(path):
                if codepoint in codepoint_set:
                    return path, display_name

        return None, None

    # Start the preload thread immediately when this module is imported on Windows.
    # cairodevice imports fontfinder at app startup, so the thread gets maximum
    # lead time before the user opens a document with non-Latin text.
    _build_font_link_index()


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
