import sys
from pathlib import Path


def package_dir():
    """Root of the miniword package's bundled data (icons, plugins, ...).

    On a normal install this is just the package directory. PyInstaller's
    macOS .app bundles split things up: --add-data files land under
    Contents/Resources (Apple bundle convention) while the frozen module's
    own __file__ resolves under Contents/Frameworks, so the two diverge.
    """
    if getattr(sys, 'frozen', False):
        if sys.platform == 'darwin':
            return Path(sys.executable).resolve().parent.parent / 'Resources' / 'miniword'
        return Path(sys._MEIPASS) / 'miniword'
    return Path(__file__).resolve().parent.parent


def frameworks_dir():
    """Contents/Frameworks of a frozen macOS .app bundle, or None elsewhere.

    Holds binaries PyInstaller can't discover itself (e.g. fc-match, cairo's
    own dependency tree) that get bundled by the installer/bundle_*.sh
    scripts instead.
    """
    if getattr(sys, 'frozen', False) and sys.platform == 'darwin':
        return Path(sys.executable).resolve().parent.parent / 'Frameworks'
    return None
