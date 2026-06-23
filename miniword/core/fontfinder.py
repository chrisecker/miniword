"""Platform-independent font discovery.

Linux/macOS: delegates to fc-match (fontconfig CLI, fast).
Windows:     uses the FontLink registry for script fallback, fonttools for
             codepoint verification.  Coverage data is persisted to disk so
             each font file is parsed at most once across sessions.
"""
import sys
import os
import subprocess

from .respath import frameworks_dir, package_dir

_path_cache = {}     # (family, bold, italic) -> path | None
_fallback_cache = {} # codepoint -> (path, family) | (None, None)
_scan_needed = False # set by init_preload(); queried by __main__ after wx init


def _fc_match_argv0():
    """Path to fc-match, plus extra env vars needed to find its config.

    On a frozen macOS build, fc-match and its fonts.conf are bundled
    alongside the app (installer/bundle_fontconfig_macos.sh) since
    PyInstaller can't see this module's subprocess calls to find it itself.
    """
    frameworks = frameworks_dir()
    if frameworks is None:
        return 'fc-match', {}
    fonts_conf = package_dir().parent / 'fontconfig' / 'fonts.conf'
    return str(frameworks / 'fc-match'), {'FONTCONFIG_FILE': str(fonts_conf)}


_FC_MATCH, _FC_EXTRA_ENV = _fc_match_argv0() if sys.platform != 'win32' else (None, {})
_FC_ENV = {**os.environ, **_FC_EXTRA_ENV} if _FC_EXTRA_ENV else None


# ── Windows backend ──────────────────────────────────────────────────────────

if sys.platform == 'win32':
    import json
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
    _win_coverage = {}     # path -> [(codepoint_set, display_name)]
    _coverage_lock = threading.Lock()

    _CACHE_VERSION = 0

    # ── persistent cache ─────────────────────────────────────────────────────

    def _encode_coverage(cp_set):
        """Encode a codepoint set as a mixed list.

        Isolated codepoints and pairs are stored as plain ints; consecutive
        runs of three or more are stored as [start, end] (inclusive).  This
        keeps the JSON compact for both dense blocks and sparse characters.
        """
        if not cp_set:
            return []
        result = []
        start = prev = None
        for cp in sorted(cp_set):
            if prev is None:
                start = prev = cp
            elif cp == prev + 1:
                prev = cp
            else:
                if prev - start >= 2:
                    result.append([start, prev])
                else:
                    result.extend(range(start, prev + 1))
                start = prev = cp
        if prev - start >= 2:
            result.append([start, prev])
        else:
            result.extend(range(start, prev + 1))
        return result

    def _decode_coverage(encoded):
        """Decode a mixed list into one combined codepoint set."""
        result = set()
        for entry in encoded:
            if isinstance(entry, list):
                result.update(range(entry[0], entry[1] + 1))
            else:
                result.add(entry)
        return result

    _fallback_save_timer = None  # threading.Timer for debounced fallback save

    def _cache_path():
        base = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
        return os.path.join(base, 'miniword', 'font_coverage.json')

    def _fallback_cp_cache_path():
        base = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
        return os.path.join(base, 'miniword', 'fallback_codepoints.json')

    def _load_fallback_cp_cache():
        """Pre-populate _fallback_cache from disk so find_fallback_info is instant."""
        path = _fallback_cp_cache_path()
        if not os.path.exists(path):
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for cp_str, entry in data.items():
                cp = int(cp_str)
                if cp not in _fallback_cache:
                    fpath, fname = entry
                    if fpath is None or os.path.exists(fpath):
                        _fallback_cache[cp] = (fpath, fname)
        except Exception:
            pass

    def _do_save_fallback_cp():
        global _fallback_save_timer
        _fallback_save_timer = None
        try:
            path = _fallback_cp_cache_path()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            data = {str(cp): list(info) for cp, info in list(_fallback_cache.items())}
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f)
        except Exception:
            pass

    def _schedule_fallback_cp_save():
        """Debounced save: write _fallback_cache to disk 2 s after last new entry."""
        global _fallback_save_timer
        if _fallback_save_timer is not None:
            return
        t = threading.Timer(2.0, _do_save_fallback_cp)
        t.daemon = True
        t.start()
        _fallback_save_timer = t

    def _load_coverage_cache():
        """Populate _win_coverage from disk. Returns True if cache was valid."""
        path = _cache_path()
        if not os.path.exists(path):
            return False
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data.get('version') != _CACHE_VERSION:
                return False
            loaded = {}
            for font_path, entry in data.get('entries', {}).items():
                if not os.path.exists(font_path):
                    return False  # font was removed
                if abs(os.path.getmtime(font_path) - entry['mtime']) > 1.0:
                    return False  # font was updated
                loaded[font_path] = [
                    (_decode_coverage(e[0]), e[1]) for e in entry['coverage']
                ]
            _win_coverage.update(loaded)
            return True
        except Exception:
            return False

    def _save_coverage_cache():
        """Persist _win_coverage to disk for future startups."""
        if not _win_coverage:
            return
        try:
            cache_file = _cache_path()
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            entries = {}
            with _coverage_lock:
                snapshot = dict(_win_coverage)
            for font_path, items in snapshot.items():
                try:
                    mtime = os.path.getmtime(font_path)
                except OSError:
                    continue
                entries[font_path] = {
                    'mtime': mtime,
                    'coverage': [[_encode_coverage(cp_set), name] for cp_set, name in items],
                }
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump({'version': _CACHE_VERSION, 'entries': entries}, f)
        except Exception:
            pass

    # ── font index ───────────────────────────────────────────────────────────

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
        r"""Read FontLink\SystemLink into _win_font_link."""
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

    def _coverage_for_path(path):
        """Return cached [(codepoint_set, display_name)] for *path*.

        Thread-safe: a lock prevents duplicate work when the preload thread
        and the main thread race on the same file.
        """
        with _coverage_lock:
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

        with _coverage_lock:
            _win_coverage.setdefault(path, entries)
            return _win_coverage[path]

    def _font_link_candidates():
        """Ordered (path, display_name) pairs from FontLink, deduplicated."""
        seen = set()
        candidates = []
        for ref in ('tahoma', 'segoe ui', 'microsoft sans serif'):
            for path, name in _win_font_link.get(ref, []):
                if path not in seen:
                    seen.add(path)
                    candidates.append((path, name))
        return candidates

    def _preload_font_link_coverage(progress_cb=None):
        """Parse FontLink fonts and persist the cache.

        progress_cb(done, total) is called after each font if provided.
        Sleeps briefly between fonts to yield the GIL when running in background.
        """
        import time
        if _TTFont is None:
            return
        candidates = _font_link_candidates()
        total = len(candidates)
        for i, (path, _) in enumerate(candidates):
            with _coverage_lock:
                already = path in _win_coverage
            if not already:
                _coverage_for_path(path)
            if progress_cb:
                progress_cb(i + 1, total)
            else:
                time.sleep(0.002)
        _save_coverage_cache()

    def _resolve_windows(family, bold, italic):
        if _win_index is None:
            _build_win_index()
        styles = _win_index.get(family.lower(), {})
        for b, i in [(bold, italic), (bold, False), (False, False)]:
            if (b, i) in styles:
                return styles[(b, i)]
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

        candidates = _font_link_candidates()

        # Fast path: FontLink candidates (~9 fonts, coverage pre-loaded from cache)
        for path, _ in candidates:
            for codepoint_set, display_name in _coverage_for_path(path):
                if codepoint in codepoint_set:
                    return path, display_name

        # Slow path: every installed font (exotic scripts, user-installed fonts)
        link_paths = {p for p, _ in candidates}
        for styles in _win_index.values():
            path = next(iter(styles.values()))
            if path in link_paths:
                continue
            for codepoint_set, display_name in _coverage_for_path(path):
                if codepoint in codepoint_set:
                    return path, display_name

        return None, None


# ── Public API ────────────────────────────────────────────────────────────────

def init_preload():
    """Phase 1 — fast init at import time (before wx is available).

    Builds the font index and loads the two disk caches.  Sets _scan_needed;
    call run_preload_sync() via a progress dialog if it is True.
    """
    global _scan_needed
    if sys.platform != 'win32':
        return
    _build_font_link_index()
    _load_fallback_cp_cache()   # tiny; eliminates main-thread fontTools for known codepoints
    _scan_needed = not _load_coverage_cache()  # True = coverage cache missing or stale


def run_preload_sync(progress_cb=None):
    """Phase 2 — full font-coverage scan.

    Run this after wx is available (e.g. inside a progress-dialog thread).
    progress_cb(done, total) is called after each font file is parsed.
    """
    if sys.platform == 'win32':
        _preload_font_link_coverage(progress_cb)

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
                [_FC_MATCH, pattern, '--format=%{file}'],
                capture_output=True, text=True, timeout=2, env=_FC_ENV)
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
                [_FC_MATCH, f':charset={codepoint:04x}', '--format=%{file}\t%{family}'],
                capture_output=True, text=True, timeout=2, env=_FC_ENV)
            line = result.stdout.strip()
            if '\t' in line:
                path, fam = line.split('\t', 1)
                info = (path or None, fam.split(',')[0].strip() or None)
            else:
                info = (None, None)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            info = (None, None)

    _fallback_cache[codepoint] = info
    if sys.platform == 'win32':
        _schedule_fallback_cp_save()
    return info
