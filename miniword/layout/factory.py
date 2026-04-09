from ..wxtextview.builder import Factory as FactoryBase
from ..wxtextview.testdevice import TESTDEVICE
from ..wxtextview.boxes import NewlineBox
from ..textmodel.utils import iter_paragraphs
from ..textmodel.texeltree import EMPTYSTYLE
from ..core.styles import updated, style_default

from copy import copy as shallow_copy




class Factory(FactoryBase):
    # The following attributes are set by pagegen. It can always be
    # assumed that they have a meaningful value.
    parstyle = None
    markerstyle = None
    indent_level = None
    line_width = None

    def __init__(self, stylesheet, device=TESTDEVICE):
        self.stylesheet = stylesheet
        FactoryBase.__init__(self, device)

    def copy(self):
        clone = shallow_copy(self)
        
    def mk_style(self, style):
        parstyle = self.parstyle
        stylesheet = self.stylesheet
        basestyle = stylesheet.get(parstyle.get('base', 'normal')) or {}
        return updated(style_default, basestyle, parstyle, style)

    def BR_handler(self, texel, i1, i2):
        return [ForceBreakBox(self.mk_style(texel.style), self.device)]

    def Image_handler(self, texel, i1, i2):
        from ..images import ImageBox
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
        from ..tables.table_factory import build_table_box
        line_width = getattr(self, 'line_width', 400)
        self.page_width = line_width
        return [build_table_box(texel, self)]


    def generate_boxes(self, texel, i):
        """Generator producing a stream of boxes."""
        for i1, i2, l in iter_paragraphs(texel, i):
            boxes = []
            # Iterating groups in reverse (the usual trick) is prevented
            # by the generator, so we set parstyle directly instead.
            nl = l[-1]
            self.markerstyle  = getattr(l[0], 'style', EMPTYSTYLE)
            self.parstyle     = nl.parstyle
            fixed = self.mk_style({}).get('fixed_indent')
            self.indent_level = fixed if fixed is not None else nl.indent
            for node in l:
                boxes.extend(self.create_all(node))
            yield i1, i2, boxes

