from ..textmodel.modelbase import Model
from ..textmodel.textmodel import TextModel
from .stylesheet import StyleSheet
from .units import cm, mm
from .styles import normal as _normal_style


settings_default = {
    "title":         "",
    "author":        "",
    "paper":         "A4",        # "A4" / "Letter" / "custom"
    "paper_width":   210 * mm,    # used when paper == "custom"
    "paper_height":  297 * mm,
    "margin_top":    2.5 * cm,
    "margin_right":  2.5 * cm,
    "margin_bottom": 2.5 * cm,
    "margin_left":   2.5 * cm,
}


class Document(Model):
    def __init__(self):
        self.charstyles = StyleSheet()
        self.charstyles.set_owner(self, 'charstyles')
        self.liststyles = StyleSheet()
        self.liststyles.set_owner(self, 'liststyles')
        self.basestyles = StyleSheet()
        self.basestyles.set_owner(self, 'basestyles')
        self.basestyles.set('normal', _normal_style)
        self.textmodel = TextModel()
        self.settings = {}
        self.blobs = {}        # {blob_id: bytes}
        self.home_format = 'txl'   # native format; set to ext on import

    def set_setting(self, name, value):
        if name in self.settings:
            old = self.settings[name]
        else:
            old = settings_default[name]
        if value != old:
            if settings_default[name] == value:
                del self.settings[name]
            else:
                self.settings[name] = value
            self.notify_views('setting_changed', name, old)
        return old

    def save(self, path):
        from ..io import txlio
        txlio.save(self, path)

    @classmethod
    def load(cls, path):
        from ..io.importexport import open_file
        return open_file(path)
        
    def charstyles_changed(self, *args, **kwds):
        self.notify_views('charstyles_changed')

    def liststyles_changed(self, *args, **kwds):
        self.notify_views('liststyles_changed')

    def basestyles_changed(self, *args, **kwds):
        self.notify_views('basestyles_changed')
        

        
class TestDocument(Document):
    def charstyles_changed(self, *args, **kwds):
        self.msg = args, kwds

    def liststyles_changed(self, *args, **kwds):
        self.msg = args, kwds

    def attribute_changed(self, *args, **kwds):
        self.msg = args, kwds

        
def test_00():
    "receiving child messages"
    
    doc = TestDocument()

    # testing the charstyles_changed handler
    doc.charstyles.set('normal', dict(fontsize=9, dolor="black"))
    assert doc.msg == ((doc.charstyles, 'normal'), {})
    
    # testing the fallback handler
    doc.xyzstyles = StyleSheet()
    doc.xyzstyles.set_owner(doc, 'xyzstyles')
    doc.msg = None
    doc.xyzstyles.set("x", {})
    assert doc.msg == ((doc.xyzstyles,), {})

    
def test_01():
    "forwarding attribute changes"

    from ..textmodel.viewbase import ViewBase
    class TestView(ViewBase):
        def charstyles_changed(self, *args, **kwds):
            self.msg = "charstyles_changed", args, kwds
        
        def model_changed(self, *args, **kwds):
            self.msg = "model_changed", args, kwds
        
    doc = Document()
    view = TestView()
    view.model = doc

    # testing the charstyles_changed handler
    doc.charstyles.set('normal', dict(fontsize=9, dolor="black"))
    assert view.msg == ('charstyles_changed', (doc,), {})

    # testing the fallback handler
    doc.basestyles.set('normal', dict(fontsize=9, dolor="black"))    
    assert view.msg == ('model_changed', (doc,), {})

