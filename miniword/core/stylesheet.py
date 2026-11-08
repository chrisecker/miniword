from collections import OrderedDict
from .documentnode import DocumentNode
from ..textmodel.styles import create_style
from .styles import style_default, updated, normal, h0, h1, h2, h3


class StyleSheet(DocumentNode):
    """Ein Stylesheet ist eine Liste von Styles. Dabei hat jeder
    Style einen eindeutigen Key, mit dem er identifiziert werden kann.

    """
    normal = None  # key of the normal style, kept by set and delete

    def __init__(self):
        self.data = OrderedDict()

    def set(self, key, value):
        # create_style ist eigentlich nicht nötig. Zumindest wenn das
        # Dict wirklich ein registrierter Style ist.
        self.data[key] = create_style(**value)
        self.normal = self.role_key('normal')
        self.notify('style_changed', key)

    def delete(self, key):
        del self.data[key]
        self.normal = self.role_key('normal')
        self.notify('style_removed', key)

    def role_key(self, role):
        """Key of the first style with role, None if there is none."""
        return next((key for key, style in self.data.items()
                     if style.get('role') == role), None)

    def normal_key(self):
        """Key of the normal style (role 'normal'), used for paragraphs
        without base. None if there is none."""
        return self.normal

    def base_style(self, parstyle):
        """The base style of a paragraph: its base, else (also for a
        missing one) the normal style; {} if there is none."""
        return self.get(parstyle.get('base')) \
            or self.get(self.normal_key()) or {}

    def get(self, key):
        return self.data.get(key)
    
    def items(self):
        return list(self.data.items())

    def keys(self):
        return list(self.data.keys())

    def contains(self, key):
        return key in self.data

    def mk_style(self, parstyle, style):
        # XXX implement caching
        return updated(style_default, self.base_style(parstyle), parstyle,
                       style)

    def mk_parstyle(self, parstyle):
        # XXX implement caching
        return updated(style_default, self.base_style(parstyle), parstyle)

    


def undo_basestyle_change(basestyles, name, old_style, new_style):
    """Undo/redo helper for basestyle edits (see Editor.add_undo)."""
    if old_style is None:
        basestyles.delete(name)
    else:
        basestyles.set(name, old_style)
    return undo_basestyle_change, basestyles, name, new_style, old_style


def test_00():
    ss = StyleSheet()
    ss.set('normal', dict(fontsize=10, color="black"))
    ss.set('h1', dict(fontsize=12, color="red"))
    s = ss.get('normal')
    assert s == dict(fontsize=10, color="black")
    s = ss.get('h1')
    assert s == dict(fontsize=12, color="red")
    assert ss.items() == [('normal', {'fontsize': 10, 'color': 'black'}),
                          ('h1', {'fontsize': 12, 'color': 'red'})]


def test_01():
    "The normal style is found by its role, not by its key"
    ss = StyleSheet()
    ss.set('h1', dict(role='h1', font_size=18))
    assert ss.normal_key() is None
    assert ss.base_style({}) == {}
    ss.set('body', dict(role='normal', font_size=11))
    assert ss.normal_key() == 'body'
    assert ss.base_style({})['font_size'] == 11
    assert ss.base_style({'base': 'h1'})['font_size'] == 18
    assert ss.base_style({'base': 'gone'})['font_size'] == 11
    ss.delete('body')
    assert ss.normal_key() is None


    



# A stylesheet for tests (and demos) only - documents bring their own.
# Single spacing and no space after paragraphs keep test metrics simple.
_plain = dict(line_spacing=1.0, space_after=0)
testsheet = StyleSheet()
testsheet.set('normal', updated(normal, _plain))
testsheet.set('h0', updated(h0, _plain))
testsheet.set('h1', updated(h1, _plain))
testsheet.set('h2', updated(h2, _plain))
testsheet.set('h3', updated(h3, _plain))
