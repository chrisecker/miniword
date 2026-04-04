import wx
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
ICONS_DIR = BASE_DIR / ".." / "icons"


def icon(name, size=(20, 20)):
    p = str(ICONS_DIR / name)
    return wx.BitmapBundle.FromSVGFile(p, size)
