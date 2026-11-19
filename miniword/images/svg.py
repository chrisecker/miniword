"""SVG images: parsed by nanosvg (wx.svg, part of wxPython), drawn with
Cairo into a RecordingSurface - it is used like a decoded bitmap, but
stays vector graphics when drawn (PDF, zoom).

1 px of the SVG is 1 pt, as with bitmaps; other units are converted
(mm, cm, in, pt).

Not supported by nanosvg: <text>, <use>, <style> (CSS), clipPath, mask,
filters, embedded images, #RRGGBBAA colors.
"""
import cairocffi as cairo
import wx.svg as nanosvg


def is_svg(content):
    """Whether content (bytes) is an SVG document."""
    head = content[:1024].lstrip(b'\xef\xbb\xbf \t\r\n')
    return head.startswith(b'<') and b'<svg' in head


def decode_svg(content):
    """(RecordingSurface, width, height) of SVG data, or None (invalid
    data: nanosvg gives no size)."""
    image = nanosvg.SVGimage.CreateFromBytes(content, units='pt', dpi=72)
    w, h = image.width, image.height
    if not (w > 0 and h > 0):
        return None
    surface = cairo.RecordingSurface(cairo.CONTENT_COLOR_ALPHA, (0, 0, w, h))
    draw_svg(image, cairo.Context(surface))
    return surface, w, h


FILL_RULES = [cairo.FILL_RULE_WINDING, cairo.FILL_RULE_EVEN_ODD]
JOINS = [cairo.LINE_JOIN_MITER, cairo.LINE_JOIN_ROUND, cairo.LINE_JOIN_BEVEL]
CAPS = [cairo.LINE_CAP_BUTT, cairo.LINE_CAP_ROUND, cairo.LINE_CAP_SQUARE]
EXTENDS = [cairo.EXTEND_PAD, cairo.EXTEND_REFLECT, cairo.EXTEND_REPEAT]


def draw_svg(image, ctx):
    """Draw a wx.svg.SVGimage with the Cairo context ctx."""
    for shape in image.shapes:
        if not shape.flags & nanosvg.SVG_FLAGS_VISIBLE:
            continue
        if shape.opacity < 1:
            ctx.push_group()
        for path in shape.paths:  # Bezier curves: start, then 3 per curve
            ctx.move_to(*path.points[0])
            curves = iter(path.points[1:])
            for c1, c2, end in zip(curves, curves, curves):
                ctx.curve_to(*c1, *c2, *end)
            if path.closed:
                ctx.close_path()
        if shape.fill.type != nanosvg.SVG_PAINT_NONE:
            ctx.set_source(pattern(shape.fill))
            ctx.set_fill_rule(FILL_RULES[shape.fillRule])
            ctx.fill_preserve()
        if shape.stroke.type != nanosvg.SVG_PAINT_NONE:
            ctx.set_source(pattern(shape.stroke))
            ctx.set_line_width(shape.strokeWidth)
            ctx.set_line_join(JOINS[shape.strokeLineJoin])
            ctx.set_line_cap(CAPS[shape.strokeLineCap])
            ctx.set_miter_limit(shape.miterLimit)
            ctx.set_dash(shape.strokeDashArray, shape.strokeDashOffset)
            ctx.stroke_preserve()
        ctx.new_path()
        if shape.opacity < 1:
            ctx.pop_group_to_source()
            ctx.paint_with_alpha(shape.opacity)


def pattern(paint):
    """A Cairo pattern for a nanosvg paint (color or gradient). nanosvg
    normalizes gradients: linear from (0, 0) to (0, 1), radial around
    (0, 0) with radius 1; the gradient's xform maps user space to that
    (as Cairo's pattern matrix). The focal point is ignored, as by
    nanosvg itself."""
    if paint.type == nanosvg.SVG_PAINT_COLOR:
        return cairo.SolidPattern(*(c / 255 for c in paint.color_rgba))
    if paint.type == nanosvg.SVG_PAINT_LINEAR_GRADIENT:
        result = cairo.LinearGradient(0, 0, 0, 1)
    else:
        result = cairo.RadialGradient(0, 0, 0, 0, 0, 1)
    gradient = paint.gradient
    for stop in gradient.stops:
        result.add_color_stop_rgba(stop.offset,
                                   *(c / 255 for c in stop.color_rgba))
    result.set_extend(EXTENDS[gradient.spread])
    result.set_matrix(cairo.Matrix(*gradient.xform))
    return result


def raster(surface, scale=1):
    """An ImageSurface of a RecordingSurface (e.g. for PNG), scale pixels
    per point."""
    *_, w, h = surface.get_extents()
    image = cairo.ImageSurface(cairo.FORMAT_ARGB32, round(w * scale),
                               round(h * scale))
    ctx = cairo.Context(image)
    ctx.scale(scale, scale)
    ctx.set_source_surface(surface)
    ctx.paint()
    return image


SAMPLE = b'''<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20">
  <rect width="20" height="20" fill="#ff0000"/>
  <rect x="20" width="20" height="20" fill="#0000ff"/>
</svg>'''


def pixel(surface, x, y):
    """(r, g, b, a) of an ImageSurface at (x, y), 0..255."""
    data = surface.get_data()
    i = y * surface.get_stride() + 4 * x
    b, g, r, a = bytes(data[i:i + 4])
    return r, g, b, a


def test_00():
    "is_svg: SVG with and without XML declaration, not PNG or text"
    assert is_svg(SAMPLE)
    assert is_svg(b'\n  <svg xmlns="http://www.w3.org/2000/svg"/>')
    assert not is_svg(b'\x89PNG\r\n\x1a\n')
    assert not is_svg(b'no <svg> at the start')


def test_01():
    "decode_svg: size in points, the shapes drawn"
    surface, w, h = decode_svg(SAMPLE)
    assert (w, h) == (40, 20)
    image = raster(surface)
    assert pixel(image, 5, 10) == (255, 0, 0, 255)
    assert pixel(image, 35, 10) == (0, 0, 255, 255)


def test_02():
    "decode_svg: units are converted, 1 px is 1 pt"
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="%s" height="1in"/>'
    _, w, h = decode_svg(svg % b'10mm')
    assert abs(w - 72 * 10 / 25.4) < 1e-4 and h == 72
    assert decode_svg(svg % b'30')[1] == 30  # px


def test_03():
    "decode_svg: invalid data or no size gives None"
    assert decode_svg(b'<svg nonsense') is None
    assert decode_svg(b'garbage') is None


def test_04():
    "linear gradient: from its start color to its end color"
    svg = b'''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="10">
      <defs><linearGradient id="g">
        <stop offset="0" stop-color="#000000"/>
        <stop offset="1" stop-color="#ffffff"/></linearGradient></defs>
      <rect width="100" height="10" fill="url(#g)"/></svg>'''
    image = raster(decode_svg(svg)[0])
    assert pixel(image, 1, 5)[0] < 10
    assert pixel(image, 98, 5)[0] > 245
    assert 100 < pixel(image, 50, 5)[0] < 155


def test_05():
    "radial gradient: center color in the middle, end color outside"
    svg = b'''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
      <defs><radialGradient id="g">
        <stop offset="0" stop-color="#ff0000"/>
        <stop offset="1" stop-color="#0000ff"/></radialGradient></defs>
      <rect width="100" height="100" fill="url(#g)"/></svg>'''
    image = raster(decode_svg(svg)[0])
    assert pixel(image, 50, 50)[0] > 245
    assert pixel(image, 1, 1)[2] > 245


def test_06():
    "stroke and opacity"
    svg = b'''<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">
      <line x1="0" y1="10" x2="20" y2="10" stroke="#00ff00"
            stroke-width="4"/>
      <rect width="20" height="5" fill="#000000" opacity="0.5"/></svg>'''
    image = raster(decode_svg(svg)[0])
    assert pixel(image, 10, 10) == (0, 255, 0, 255)
    assert pixel(image, 10, 15)[3] == 0
    assert 120 < pixel(image, 10, 2)[3] < 135


def test_07():
    "the recording stays vector graphics in a PDF"
    import io
    surface, w, h = decode_svg(SAMPLE)
    stream = io.BytesIO()
    pdf = cairo.PDFSurface(stream, w, h)
    ctx = cairo.Context(pdf)
    ctx.set_source_surface(surface)
    ctx.paint()
    pdf.finish()
    assert b'/Subtype /Image' not in stream.getvalue()
