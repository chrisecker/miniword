from .wxtextview.builder import Factory as FactoryBase
from .wxtextview.testdevice import TESTDEVICE
from .wxtextview.boxes import NewlineBox
from .styles import updated, style_default


class ForceBreakBox(NewlineBox):
    """Sentinel box for a forced line break (BR texel)."""


class Factory(FactoryBase):

    def __init__(self, stylesheet, device=TESTDEVICE):
        self.stylesheet = stylesheet
        FactoryBase.__init__(self, device)

    def mk_style(self, style):
        parstyle = self.parstyle
        stylesheet = self.stylesheet
        basestyle = stylesheet.get(parstyle.get('base', 'normal')) or {}
        return updated(style_default, basestyle, parstyle, style)

    def BR_handler(self, texel, i1, i2):
        return [ForceBreakBox(self.mk_style(texel.style), self.device)]

    def Image_handler(self, texel, i1, i2):
        from .image import ImageBox
        try:
            blob = getattr(self, 'blobs', {})[texel.blob_id]
            bitmap, src_w, src_h = self.device.load_image(blob)
        except Exception:
            bitmap, src_w, src_h = None, 0, 0
        if texel.crop:
            _x, _y, w, h = texel.crop
        elif src_w:
            w, h = src_w * texel.scale, src_h * texel.scale
        else:
            w, h = 50, 50
        return [ImageBox(bitmap, w, h, self.device)]

    def Table_handler(self, texel, i1, i2):
        from .tables import build_table_box
        line_width = getattr(self, 'line_width', 400)
        self.page_width = line_width
        return [build_table_box(texel, self)]
