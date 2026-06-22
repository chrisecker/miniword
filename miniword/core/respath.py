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
