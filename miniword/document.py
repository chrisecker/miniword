from .textmodel.modelbase import Model
from .stylesheet import StyleSheet


class Document(Model):
    def __init__(self):
        self.charstyles = StyleSheet()
        self.charstyles.set_owner(self, 'charstyles')
        self.liststyles = StyleSheet()
        self.liststyles.set_owner(self, 'liststyles')
        self.parstyles = StyleSheet()
        self.parstyles.set_owner(self, 'parstyles')
        #self.textmodel = sss
        
    def charstyles_changed(self, *args, **kwds):
        self.notify_views('charstyles_changed')

    def liststyles_changed(self, *args, **kwds):
        self.notify_views('liststyles_changed')

    def parstyles_changed(self, *args, **kwds):
        self.notify_views('parstyles_changed')
        

        
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

    from .textmodel.viewbase import ViewBase
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
    doc.parstyles.set('normal', dict(fontsize=9, dolor="black"))    
    assert view.msg == ('model_changed', (doc,), {})

