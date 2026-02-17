from .wxtextview.builder import Factory as FactoryBase
from .wxtextview.testdevice import TESTDEVICE
from .styles import updated



class Factory(FactoryBase):
    
    def __init__(self, stylesheet, device=TESTDEVICE):
        self.stylesheet = stylesheet
        self.device = device

    def mk_style(self, style):
        parstyle = self.parstyle
        stylesheet = self.stylesheet
        basestyle = stylesheet[parstyle.get('base', 'normal')]
        return updated(basestyle, parstyle, style)
        
    
