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
        full_bitmap = bitmap
        if texel.crop:
            cl, cr, ct, cb = texel.crop
            cw, ch = src_w - cl - cr, src_h - ct - cb
            w, h   = cw * texel.scale_x, ch * texel.scale_y
            if bitmap is not None:
                bitmap = self.device.crop_image_surface(bitmap, cl, ct, cw, ch)
        elif src_w:
            w, h = src_w * texel.scale_x, src_h * texel.scale_y
        else:
            w, h = 50, 50
        return [ImageBox(bitmap, w, h, self.device, src_w=src_w, src_h=src_h,
                         full_bitmap=full_bitmap)]

    def Table_handler(self, texel, i1, i2):
        from .tables import build_table_box
        line_width = getattr(self, 'line_width', 400)
        self.page_width = line_width
        return [build_table_box(texel, self)]
