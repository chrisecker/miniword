"""InspectorBase: common base class for all side-panel inspectors.

Subclasses implement update() which is called lazily whenever the panel
is visible and the model has changed.
"""

import wx
from .design import BAR_BG
from ..textmodel.viewbase import ViewBase


class InspectorBase(wx.Panel, ViewBase):
    """Base for all inspector panels.

    Provides lazy update via EVT_UPDATE_UI: model callbacks set _needs_update,
    the actual update() runs only when the panel is visible.
    """
    _needs_update = False

    def __init__(self, parent, view):
        wx.Panel.__init__(self, parent)
        ViewBase.__init__(self)
        self.SetBackgroundColour(BAR_BG)
        self._view = view
        self.add_model(view)
        self.Bind(wx.EVT_SHOW,      self.on_show)
        self.Bind(wx.EVT_UPDATE_UI, self.on_update_ui)

    def on_show(self, event):
        event.Skip()
        if event.IsShown():
            self._needs_update = True

    def on_update_ui(self, event):
        if self._needs_update and self.IsShownOnScreen():
            self._needs_update = False
            self.update()

    def update(self):
        pass

    def inserted(self, model, i, n):          self._needs_update = True
    def removed(self, model, i, text):        self._needs_update = True
    def properties_changed(self, model, *a):  self._needs_update = True
    def index_changed(self, view):            self._needs_update = True
    def selection_changed(self, view):        self._needs_update = True
