import wx

from ..core.respath import package_dir


ICONS_DIR = package_dir() / "icons"


def icon(name, size=(20, 20)):
    p = str(ICONS_DIR / name)
    return wx.BitmapBundle.FromSVGFile(p, size)


def themed_icon(name, colour, size=(20, 20)):
    """Render SVG icon with fill colour substituted for current theme."""
    svg = (ICONS_DIR / name).read_bytes()
    hex_col = colour.GetAsString(wx.C2S_HTML_SYNTAX).encode()
    svg = svg.replace(b'#1f1f1f', hex_col)
    return wx.BitmapBundle.FromSVG(svg, wx.Size(*size))


def app_icon_bundle():
    """IconBundle for the MiniWord logo, built at several sizes."""
    logo_svg = str(ICONS_DIR / "miniword.svg")
    bundle = wx.IconBundle()
    for size in (16, 32, 48, 64):
        bmp = wx.BitmapBundle.FromSVGFile(logo_svg, (size, size))
        bundle.AddIcon(wx.Icon(bmp.GetBitmap(wx.Size(size, size))))
    return bundle
