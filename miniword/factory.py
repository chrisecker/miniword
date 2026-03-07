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

