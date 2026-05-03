import wx
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
ICONS_DIR = BASE_DIR / ".." / "icons"


def icon(name, size=(20, 20)):
    p = str(ICONS_DIR / name)
    return wx.BitmapBundle.FromSVGFile(p, size)


def themed_icon(name, colour, size=(20, 20)):
    """Render SVG icon with fill colour substituted for current theme."""
    svg = (ICONS_DIR / name).read_bytes()
    hex_col = colour.GetAsString(wx.C2S_HTML_SYNTAX).encode()
    svg = svg.replace(b'#1f1f1f', hex_col)
    return wx.BitmapBundle.FromSVG(svg, wx.Size(*size))
