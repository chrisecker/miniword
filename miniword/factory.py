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
        from .image import ImageBox, PlaceholderBox
        blob = getattr(self, 'blobs', {}).get(texel.blob_id)
        load_image = getattr(self.device, 'load_image', None)
        if blob is None or load_image is None:
            return [PlaceholderBox(50, 50, self.device)]
        bitmap, src_w, src_h = load_image(blob)
        if bitmap is None:
            return [PlaceholderBox(50, 50, self.device)]
        if texel.crop:
            _x, _y, w, h = texel.crop   # display pt; x/y offset reserved for future
        else:
            w, h = src_w * texel.scale, src_h * texel.scale
        return [ImageBox(bitmap, w, h, self.device)]

