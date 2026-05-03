import weakref
import wx


class ColourManager:
    def __init__(self):
        self._registry  = weakref.WeakKeyDictionary()
        self._custom    = {}
        self._installed = weakref.WeakSet()
        self._callbacks = []

    def define(self, name, fn):
        """Register a custom colour name mapped to a callable."""
        self._custom[name] = fn

    def set(self, widget, attr, colorname):
        """Assign a colour role to a widget attribute, now and on theme change."""
        if widget not in self._registry:
            self._registry[widget] = []
            self._auto_install(widget)
        bindings = self._registry[widget]
        for i, (a, _) in enumerate(bindings):
            if a == attr:
                bindings[i] = (attr, colorname)
                break
        else:
            bindings.append((attr, colorname))
        try:
            setattr(widget, attr, self._resolve(colorname))
            widget.Refresh()
        except RuntimeError:
            del self._registry[widget]

    def register(self, widget, callback):
        """Register a no-arg callback for widgets with custom bitmap drawing."""
        self._auto_install(widget)
        self._callbacks.append(weakref.WeakMethod(callback))

    def get(self, colorname):
        return self._resolve(colorname)

    def _resolve(self, colorname):
        if colorname in self._custom:
            return self._custom[colorname]()
        return wx.SystemSettings.GetColour(getattr(wx, f'SYS_COLOUR_{colorname}'))

    def _auto_install(self, widget):
        top = widget.GetTopLevelParent()
        if isinstance(top, wx.TopLevelWindow) and top not in self._installed:
            top.Bind(wx.EVT_SYS_COLOUR_CHANGED, self._on_change)
            self._installed.add(top)

    def _on_change(self, event):
        self.update()
        event.Skip()

    def update(self):
        dead = []
        for widget, bindings in list(self._registry.items()):
            try:
                for attr, colorname in bindings:
                    setattr(widget, attr, self._resolve(colorname))
                widget.Refresh()
            except RuntimeError:
                dead.append(widget)
        for widget in dead:
            del self._registry[widget]
        live = []
        for ref in self._callbacks:
            cb = ref()
            if cb is not None:
                cb()
                live.append(ref)
        self._callbacks = live


colours = ColourManager()

colours.define('ButtonHover', lambda: wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNFACE).ChangeLightness(90))
colours.define('Highlight',   lambda: wx.SystemSettings.GetColour(wx.SYS_COLOUR_HOTLIGHT))
colours.define('WarningRed',  lambda: wx.Colour(200, 0, 0))
colours.define('CanvasBg',    lambda: wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNFACE).ChangeLightness(93))
