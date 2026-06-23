import sys
import ctypes.util

__version__ = "0.1.5"


def _patch_find_library_for_homebrew():
    """Let ctypes.util.find_library see Homebrew-installed libraries.

    The macOS system python3 is SIP-protected, so DYLD_LIBRARY_PATH is
    stripped from its environment and find_library('cairo-2') can't see
    a Homebrew-installed cairo even though it's on disk. Only kicks in
    when the normal lookup fails, so it's a no-op on Linux/Windows and
    whenever cairo is already discoverable.
    """
    if sys.platform != 'darwin':
        return
    import os
    orig_find_library = ctypes.util.find_library

    lib_dirs = ['/opt/homebrew/lib', '/usr/local/lib']
    if getattr(sys, 'frozen', False):
        # PyInstaller bundles cairo (and its own dependency tree) into
        # Contents/Frameworks, since it can't see cairocffi's dlopen-by-name
        # call during its static dependency analysis.
        lib_dirs.insert(0, os.path.join(
            os.path.dirname(sys.executable), '..', 'Frameworks'))

    def find_library(name):
        found = orig_find_library(name)
        if found:
            return found
        base = name.removeprefix('lib').removesuffix('-2')
        for lib_dir in lib_dirs:
            for candidate in (f'lib{base}.dylib', f'lib{base}.2.dylib'):
                path = os.path.join(lib_dir, candidate)
                if os.path.exists(path):
                    return path
        return None

    ctypes.util.find_library = find_library


_patch_find_library_for_homebrew()
