from collections import OrderedDict
from .documentnode import DocumentNode
from ..textmodel.styles import Style, EMPTYSTYLE
from .styles import style_default, updated, normal, h0, h1, h2, h3


class StyleSheet(DocumentNode):
    """Ein Stylesheet ist eine Liste von Styles. Dabei hat jeder
    Style einen eindeutigen Key, mit dem er identifiziert werden kann.

    """
    normal = None  # key of the normal style, kept by set and delete

    def __init__(self):
        self.data = OrderedDict()
        self.cache = {}  # (id(parstyle), id(style)) -> full style


    def set(self, key, value):
        # Style ist eigentlich nicht nötig. Zumindest wenn das
        # Dict wirklich ein registrierter Style ist.
        self.data[key] = Style(**value)
        self.normal = self.role_key('normal')
        self.cache.clear()
        self.notify('style_changed', key)

    def delete(self, key):
        del self.data[key]
        self.normal = self.role_key('normal')
        self.cache.clear()
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
        """The full style (a Style) of style in a paragraph of parstyle:
        defaults, base style, parstyle, style. Cached by the identity of
        the (pooled, never deleted) Styles; set and delete clear it."""
        assert isinstance(parstyle, Style) and isinstance(style, Style), \
            (parstyle, style)
        key = id(parstyle), id(style)
        try:
            return self.cache[key]
        except KeyError:
            result = self.cache[key] = Style(**updated(
                style_default, self.base_style(parstyle), parstyle, style))
            return result

    def mk_parstyle(self, parstyle):
        return self.mk_style(parstyle, EMPTYSTYLE)

    


def adopt_styles(model, styles, sheet):
    """Make the paragraphs of model (pasted; styles: {key: base style}
    of where it was copied from) use the base styles of sheet: a key
    sheet has keeps sheet's style, a style with a role sheet has takes
    sheet's key for it, any other is added to sheet; a base defined
    nowhere is dropped. The keys added (for undo)."""
    from ..textmodel.utils import iter_newlines
    from ..textmodel.styles import updated_style, cleared_style
    rename, added = {}, []
    for key, style in styles.items():
        if sheet.contains(key):
            continue
        role = style.get('role')
        other = sheet.role_key(role) if role else None
        if other:
            rename[key] = other
        else:
            sheet.set(key, style)
            added.append(key)
    for i, _, nl in list(iter_newlines(model.get_xtexel(), 0, True)):
        base = nl.parstyle.get('base')
        if base in rename:
            model.set_parstyle(
                i, updated_style(nl.parstyle, dict(base=rename[base])))
        elif base and not sheet.contains(base):
            model.set_parstyle(i, cleared_style(nl.parstyle, ['base']))
    return added


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


def test_02():
    "adopt_styles: pasted paragraphs use the styles of the target"
    from ..io.txlio import loads
    from ..textmodel.utils import iter_newlines
    model, _ = loads('''[document]
T('a') NL({base="h1"}) T('b') NL({base="style0"})
T('c') NL({base="mine", alignment="center"}) T('d') NL({base="gone"})
C("table", {ncols=1}, [T('e'), {base="h1"}])
''')
    styles = {'h1': dict(role='h1', font_size=20), 'style0': dict(color='red'),
              'mine': dict(color='blue')}
    sheet = StyleSheet()
    sheet.set('normal', dict(role='normal'))
    sheet.set('heading', dict(role='h1', font_size=18))
    sheet.set('mine', dict(color='green'))
    assert adopt_styles(model, styles, sheet) == ['style0']
    assert [dict(nl.parstyle) for *_, nl in
            iter_newlines(model.get_xtexel(), 0, True)][:6] == [
        {'base': 'heading'}, {'base': 'style0'},
        {'base': 'mine', 'alignment': 'center'}, {}, {}, {'base': 'heading'}]
    assert sheet.keys() == ['normal', 'heading', 'mine', 'style0']
    assert sheet.get('mine') == {'color': 'green'}  # the target's wins
    assert sheet.get('style0') == {'color': 'red'}


    



# A stylesheet for tests (and demos) only - documents bring their own.
# Single spacing and no space after paragraphs keep test metrics simple.
_plain = dict(line_spacing=1.0, space_after=0)
testsheet = StyleSheet()
testsheet.set('normal', updated(normal, _plain))
testsheet.set('h0', updated(h0, _plain))
testsheet.set('h1', updated(h1, _plain))
testsheet.set('h2', updated(h2, _plain))
testsheet.set('h3', updated(h3, _plain))
