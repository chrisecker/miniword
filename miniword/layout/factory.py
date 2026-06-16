import logging

from .builderbase import Factory as FactoryBase
from .testdevice import TESTDEVICE
from .boxes import NewlineBox
from ..textmodel.utils import iter_paragraphs
from ..textmodel.texeltree import EMPTYSTYLE
from ..core.styles import updated, style_default

from copy import copy as shallow_copy

log = logging.getLogger(__name__)




class Factory(FactoryBase):
    # The following attributes are set by pagegen. It can always be
    # assumed that they have a meaningful value.
    parstyle = None
    markerstyle = None
    indent_level = None
    line_width = None

    blobs = {}

    def __init__(self, stylesheet, device=TESTDEVICE):
        self.stylesheet = stylesheet
        self.image_cache = {}
        FactoryBase.__init__(self, device)

    def get_image(self, blob_id):
        """Return ImageData for blob_id, decoding (and caching) on first use."""
        if blob_id not in self.image_cache:
            from ..images.imageio import decode
            blob = self.blobs.get(blob_id)
            self.image_cache[blob_id] = decode(blob) if blob is not None else None
        return self.image_cache[blob_id]

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
        from ..images import ImageBox, ErrorPlaceholderBox
        from ..images.imageio import crop_surface
        image_data = self.get_image(texel.blob_id)
        if image_data is None:
            log.warning("Image not found: %r", texel.blob_id)
            return [ErrorPlaceholderBox(50, 50, self.device)]
        bitmap = image_data.bitmap
        src_w, src_h = image_data.width_px, image_data.height_px
        if texel.crop:
            cl, cr, ct, cb = texel.crop
            cw, ch = src_w - cl - cr, src_h - ct - cb
            w, h   = cw * texel.scale_x, ch * texel.scale_y
            bitmap = crop_surface(bitmap, cl, ct, cw, ch)
        else:
            w, h = src_w * texel.scale_x, src_h * texel.scale_y
        return [ImageBox(bitmap, w, h, image_data, self.device)]

    def Footnote_handler(self, texel, i1, i2):
        from ..footnotes.footnotes import FootnoteAnchorBox, format_fn_label
        self.footnote_counter = getattr(self, 'footnote_counter', 0) + 1
        label = texel.label or format_fn_label(self.footnote_counter, texel.numbering)
        style = self.mk_style(texel.style)
        style['font_size'] *= 0.7
        return [FootnoteAnchorBox(texel, label, style, self.device)]

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

