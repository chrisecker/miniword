import wx

from .textmodel.viewbase import ViewBase
from .textmodel.properties import overridable_property
from einstein import get_einstein_model



class Search(ViewBase):
    results = overridable_property('results')
    _results = ()
    substring = ""
    ignorecase = True
    valide = True
    def __init__(self, model):
        ViewBase.__init__(self)
        self.model = model
        
    def search(self, substring, ignorecase=True):
        self.substring = substring
        self.ignorecase = ignorecase
        self.valide = False

    def update(self):
        substring = self.substring
        text = self.model.get_text()
        if self.ignorecase:
            text = text.upper()
            substring = substring.upper()
        if substring == "":
            return list(range(len(text) + 1))  # Sonderfall: leerer String

        results = []
        start = 0
        n = len(substring)
        while True:
            index = text.find(substring, start)
            if index == -1:
                break
            results.append((index, index+n))
            start = index + 1  # +1 erlaubt überlappende Treffer
        self._results = results

    def get_results(self):
        if not self.valide:
            self.update()
        return self._results
        
    def inserted(self, model, i, n):
        self.valid = False

    def removed(self, model, i, text):
        self.valid = False



class SearchPanel(wx.Panel):
    def __init__(self, parent, textview):
        super().__init__(parent)
        self.textview = textview
        self.textmodel = textview.model
        self.search = Search(self.textmodel)

        sizer = wx.BoxSizer(wx.VERTICAL)
        self.search_ctrl = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        sizer.Add(self.search_ctrl, 0, wx.EXPAND | wx.ALL, 5)

        self.list_ctrl = wx.ListCtrl(self, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        self.list_ctrl.InsertColumn(0, "Zeile")
        self.list_ctrl.InsertColumn(1, "Spalte")
        sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.ALL, 5)
        self.SetSizer(sizer)

        # Events
        self.search_ctrl.Bind(wx.EVT_TEXT, self.on_text_changed)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_item_activated)

        self.update_list()

    def on_text_changed(self, event):
        text = self.search_ctrl.GetValue()
        self.search.search(text)
        self.update_list()

    def update_list(self):
        results = self.search.get_results()
        self.list_ctrl.DeleteAllItems()
        model = self.search.model
        for start, end in results:
            row, col = model.index2position(start)
            index = self.list_ctrl.InsertItem(self.list_ctrl.GetItemCount(), str(row + 1))
            self.list_ctrl.SetItem(index, 1, str(col + 1))
        self.list_ctrl.SetColumnWidth(0, wx.LIST_AUTOSIZE)
        self.list_ctrl.SetColumnWidth(1, wx.LIST_AUTOSIZE)

    def on_item_activated(self, event):
        index = event.GetIndex()
        i1, i2 = self.search.results[index]
        self.textview.set_selection((i1, i2))

        
def demo_00():
    from .wxtextview.wxtextview import WXTextView
    app = wx.App(True)
    frame = wx.Frame(None, title="Search Demo", size=(400,300))
    model = get_einstein_model()
    f = wx.Frame(None)
    view = WXTextView(f)
    view.set_model(model)
    f.Show()
    
    panel = SearchPanel(frame, view)

    frame.Show()
    app.MainLoop()

def test_00():
    model = get_einstein_model()
    search = Search(model)
    search.search(r'{\displaystyle E=mc^{2}}')
    assert search.results == [(328, 352)]
    for i1, i2 in reversed(search.results):
        model.remove(i1, i2)
    assert search.results == []
        
    search.search('Einstein')
    assert search.results == [
        (7, 15), (644, 652), (1527, 1535), (2678, 2686), (2781, 2789),
        (3158, 3166), (3285, 3293), (3654, 3662), (3754, 3762)]

    model.remove(0, 7)
    assert search.results == [
        (0, 8), (637, 645), (1520, 1528), (2671, 2679), (2774, 2782),
        (3151, 3159), (3278, 3286), (3647, 3655), (3747, 3755)]
