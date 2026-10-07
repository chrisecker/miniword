from ..textmodel import TextModel
from ..textmodel.viewbase import overridable_property
from ..textmodel.submodel import SubModel, Footnote
from ..textmodel.modelbase import Model
from ..textmodel.texeltree import length, EMPTYSTYLE
from ..textmodel.utils import iter_leafes, get_path
from .undoredo import UndoRedo
from .controller import NullController
from .actions import default_handler
from contextlib import contextmanager
from weakref import WeakKeyDictionary

"""
Note:
- after change of model or view update_controller has to be called! 
"""

_editor_canvas = WeakKeyDictionary() # {editor: canvas}

class Editor(UndoRedo):
    index = overridable_property('index', 'Position of text cursor')
    _index = 0
    selection = overridable_property('selection', 'Tupel (i1, i2) or None')
    _selection = None
    current_style = overridable_property('current_style', 'A style dict')
    _current_style = EMPTYSTYLE
    controller = overridable_property('controller')
    _controller = None # computed lazily by get_controller
    _controller_dirty = True
    canvas = overridable_property('canvas', 'Optional reference to canvas')
    _canvas = None

    actionhandler = staticmethod(default_handler)
    controller_registry = []

    # During tests editor might not have a canvas so that access to
    # layout is not possible. We therefore provide an optional layout
    # attribut which can be used for testing.
    layout = None
    
    # the following attributes are set by "switch_target"
    flow = 0
    offset = 0
    anchor = 0
    
    def __init__(self, root=None):
        if root is None:
            root = TextModel()
        self.root = root
        self.other = TextModel() # XXX entfernen ??
        self.target = self.root
        self.update_controller()
        assert self.controller
        super().__init__()

    def set_canvas(self, canvas):
        _editor_canvas[self] = canvas

    def get_canvas(self):
        return _editor_canvas.get(self)

    def switch_target(self, flow, index):
        """Find the model responsible for flow and index and install it."""

        # In this baseclass we only have the root flow so switching is
        # pointless. This method needs to be overriden if severeal
        # flows are needed. The following code is ment as an
        # illustration of the steps.
        if flow == 0:
            target = self.root
            offset = 0
            anchor = 0
        else:
            raise AttributeError(flow)
        new = target, offset, anchor
        old = self.target, self.offset, self.anchor
        if new == old:
            return        
        self.target = target
        self.offset = offset
        self.anchor = anchor
        self.flow = flow
        self.notify_views('target_changed')

    @contextmanager
    def atomic(self):
        """Group multiple model/stylesheet changes into one layout rebuild."""
        self.begin_undo_group()
        try:
            yield
        finally:
            self.end_undo_group()
    
    def abs_idx(self, j):
        return j + self.offset

    def abs_idxs(self, *args):
        offset = self.offset 
        return [j + offset for j in args]

    def local_idx(self, j):
        return j - self.offset
    
    def local_idxs(self, *args):
        offset = self.offset 
        return [i - offset for i in args]

    def get_index(self):
        return self._index

    def set_index(self, index, extend=False, update=True):
        model = self.target
        old = self._index
        if index < 0:
            index = 0
        elif index > len(model):
            index = len(model)
        if index != self._index:
            #self.ensure_index(index+1)
            self._index = index
            if index == 0:
                self._current_style = dict(model.get_style(0))
            else:
                self._current_style = dict(model.get_style(index - 1))
            if extend:
                self.end_selection()
            elif update:
                self.start_selection()
            if self.canvas is not None:
                self.canvas.reset_blink()
                self.canvas.adjust_viewport()
                self.canvas.refresh()                
            self.notify_views('index_changed')
        #if old != index and not self.editor.is_null:
        #    self.remove_editor()
        self.update_controller()
        
    def get_selection(self):
        return self._selection

    def set_selection(self, selection):
        old = self._selection
        if selection == old:
            return
        if old is not None:
            i1, i2 = old
        self._selection = selection
        #self.refresh()
        self.notify_views('selection_changed')

    def has_selection(self):
        selection = self.selection
        if selection is None:
            return False
        return selection[0] != selection[1]

    def selected_ranges(self):
        """Get selected ranges."""
        selection = self.selection
        if selection is None:
            return []
        s1, s2 = sorted(selection)
        if s1 == s2:
            return []
        result = self.controller.selected(s1, s2)
        if result is not None:
            return result
        return [self.target.expand_range(s1, s2)]

    def start_selection(self):
        """Sets the selection start to index."""
        index = self.index
        self.selection = index, index
        
    def end_selection(self):
        """Moves the selection endpoint to index."""
        selection = self.selection
        index = self.index
        if selection is None:
            self.selection = index, index
        else:
            self.selection = selection[0], index

    ### Insert & remove
    def insert_text(self, text):
        new = TextModel(text, **self.current_style)
        i = self.abs_idx(self.index)
        info = self._insert(self.flow, i, new)
        self.add_undo(info)

    def insert_texel(self, texel):
        new = self.target.create_textmodel()
        new.texel = texel
        i = self.abs_idx(self.index)
        info = self._insert(self.flow, i, new)
        self.add_undo(info)

    def _insert(self, flow, i, new):
        self.switch_target(flow, i)
        j = self.local_idx(i)
        self.target.insert(j, new)
        self.index = j+len(new)
        return self._remove, flow, i, i+len(new)

    def remove(self):
        self.begin_undo_group()
        try:
            for j1, j2 in reversed(self.selected_ranges()):
                i1, i2 = self.abs_idxs(j1, j2)
                self.remove_range(j1, j2)
        finally:
            self.end_undo_group()

    def remove_range(self, j1, j2):
        i1, i2 = self.abs_idxs(j1, j2)
        info = self._remove(self.flow, i1, i2)
        self.add_undo(info)
        self.index = j1
            
    def _remove(self, flow, i1, i2):
        self.switch_target(flow, i1)
        j1, j2 = self.local_idxs(i1, i2)
        old = self.target.remove(j1, j2)
        self.index = j1
        self.selection = j1, j1
        return self._insert, flow, i1, old

    def join_undo(self, info2, info1):
        # Merge consecutive insertions resp. consecutive removals into a
        # single undo entry, so that e.g. typing several characters in a
        # row can be undone with one undo step. Merging stops once the
        # combined range reaches nmax, roughly limiting undo steps to
        # word-sized chunks.
        nmax = 10
        try:
            fn2, flow2, a2, b2 = info2
            fn1, flow1, a1, b1 = info1
        except (TypeError, ValueError):
            return [info2, info1]
        if flow2 != flow1:
            return [info2, info1]
        if fn2 == self._remove and fn1 == self._remove and a2 == b1:
            # undo of two consecutive insertions -> remove combined range
            if b2-a1 < nmax:
                return [(self._remove, flow2, a1, b2)]
        if fn2 == self._insert and fn1 == self._insert:
            # undo of two consecutive removals -> reinsert combined text
            if a2+len(b2) == a1 and len(b1)+len(b2) < nmax:
                # consecutive backspaces
                return [(self._insert, flow2, a2, b2+b1)]
            if a2 == a1 and len(b1)+len(b2) < nmax:
                # consecutive deletes
                return [(self._insert, flow2, a2, b1+b2)]
        return [info2, info1]

    def set_texel_attributes(self, i1, texel, **attributes):
        """Replace the texel at i1 with a clone that has updated attributes."""
        new_texel = texel
        for key, value in attributes.items():
            new_texel = getattr(new_texel, 'set_' + key)(value)
        new = self.target.create_textmodel()
        new.texel = new_texel
        j = self.local_idx(i1)
        with self.atomic():
            self.add_undo(self._remove(self.flow, i1, i1+length(texel)))
            self.add_undo(self._insert(self.flow, i1, new))
        # keep the cursor on the (replaced) texel, so a click-installed
        # controller (e.g. ImageSizeController) stays installed
        self.index = j

    def insert_newline(self):
        model = self.target
        index = self.index
        style = self.current_style
        parstyle = model.get_parstyle(index)
        indent = model.get_indent(index)
        tmp = model.create_textmodel('\n', **style)
        tmp.set_parstyle(0, parstyle)
        tmp.set_indent(0, indent)
        i = self.abs_idx(index)
        info = self._insert(self.flow, i, tmp)
        self.add_undo(info)

    ### Copy & Paste
    def _to_clipboard(self, model):
        if self.canvas is not None:
            self.canvas.to_clipboard(model)
    
    def copy(self):
        if not self.has_selection():
            return
        s1, s2 = self.selected_ranges()[0] # XXX Assuming just one region
        part = self.target[s1:s2]
        self._to_clipboard(part)

    def paste(self):
        if self.canvas is None:
            return
        new = self.canvas.read_clipboard()
        if new is None:
            return
        i = self.abs_idx(self.index)
        info = self._insert(self.flow, i, new)
        self.add_undo(info)

    def cut(self):
        if self.has_selection():
            self.copy()
            self.remove()

    ### Styles
    def clear_styles(self):
        if not self.has_selection():
            return
        j1, j2 = self.selection
        i1, i2 = self.abs_idxs(j1, j2)        
        model = self.target
        styles = model.clear_styles(j1, j2)
        info = self._set_styles, self.flow, i1, styles
        self.add_undo(info)

    def set_properties(self, **properties):
        if not self.has_selection():
            return
        j1, j2 = self.selection
        i1, i2 = self.abs_idxs(j1, j2)        
        styles = self.target.set_properties(j1, j2, **properties)
        info = self._set_styles, self.flow, i1, styles
        self.add_undo(info)

    def clear_properties(self, *keys):
        if not self.has_selection():
            return
        j1, j2 = self.selection
        i1, i2 = self.abs_idxs(j1, j2)
        styles = self.target.clear_properties(j1, j2, *keys)
        info = self._set_styles, self.flow, i1, styles
        self.add_undo(info)

    def _set_styles(self, flow, i, styles):
        self.switch_target(flow, i)
        j = self.local_idx(i)
        styles = self.target.set_styles(j, styles)
        return self._set_styles, flow, i, styles

    def set_parstyle(self, style):        
        model = self.target
        j = self.index
        i = self.abs_idx(j)
        styles = model.set_parstyle(j, style)
        info = self._set_parstyles, self.flow, i, styles
        self.add_undo(info)

    def set_parproperties(self, **properties):
        if not self.has_selection():
            return
        j1, j2 = self.selection
        i1, i2 = self.abs_idxs(j1, j2)        
        styles = self.target.set_parproperties(j1, j2, **properties)
        info = self._set_parstyles, self.flow, i1, styles
        self.add_undo(info)

    def clear_parproperties(self, *keys):
        if not self.has_selection():
            return
        j1, j2 = self.selection
        i1, i2 = self.abs_idxs(j1, j2)        
        styles = self.target.clear_parproperties(j1, j2, *keys)
        info = self._set_parstyles, self.flow, i1, styles
        self.add_undo(info)

    def _set_parstyles(self, flow, i, styles):
        self.switch_target(flow, i)
        j = self.local_idx(i)
        styles = self.target.set_parstyles(j, styles)
        return self._set_parstyles, flow, i, styles

    def get_current_style(self):
        """Gets the style for the next insert-operation."""
        # XXX current_style ist kein style, sondern einfach ein
        # Dict. Textmodel wandelt es bei insert um. Ich denke, es
        # passt so.
        if self._current_style is None:
            j = self.index
            if j > 0:
                j -= 1
            self._current_style = dict(self.target.get_style(j))
        return self._current_style
 
    def set_current_style(self, properties):
        """Sets the style for the next insert-operation."""
        if self._current_style == properties:
            return
        self._current_style = properties.copy()
        self.notify_views('current_style_changed')
    
    ### Indent
    def _set_indents(self, flow, i1, i2, indents):
        j1, j2 = self.local_idxs(i1, i2)
        self.switch_target(flow, i1)
        indents = self.target.set_indents(j1, j2, indents)
        return self._set_indents, flow, i1, i2, indents

    def indent(self):
        """One level more; in code 4 spaces at the line starts."""
        j1, j2 = self.selected_range()
        if self.is_code(j1):
            return self.shift_lines(j1, j2, 4)
        j2 = self.target.lineend(j2)+1
        i1, i2 = self.abs_idxs(j1, j2)
        old = self.target.increase_indent(j1, j2)
        self.add_undo((self._set_indents, self.flow, i1, i2, old))

    def dedent(self):
        """One level less; in code up to 4 spaces less at the line
        starts."""
        j1, j2 = self.selected_range()
        if self.is_code(j1):
            return self.shift_lines(j1, j2, -4)
        j2 = self.target.lineend(j2)+1
        i1, i2 = self.abs_idxs(j1, j2)
        old = self.target.decrease_indent(j1, j2)
        self.add_undo((self._set_indents, self.flow, i1, i2, old))

    def selected_range(self):
        """(j1, j2): the selection, or the cursor."""
        if self.has_selection():
            return tuple(sorted(self.selection))
        return self.index, self.index

    def is_code(self, j):
        """Whether the paragraph at j is code: its base style has the
        role 'pre'."""
        if self.canvas is None:
            return False
        base = self.target.get_parstyle(j).get('base')
        style = base and self.canvas.builder.stylesheet.get(base)
        return bool(style) and style.get('role') == 'pre'

    def _line_starts(self, i1, i2):
        """Line starts of all lines overlapping [i1, i2]."""
        model = self.target
        starts = [model.linestart(i1)]
        while model.lineend(starts[-1]) < i2 \
                and model.lineend(starts[-1]) + 1 < len(model):
            starts.append(model.lineend(starts[-1]) + 1)
        return starts

    def shift_lines(self, j1, j2, n):
        """Insert n spaces at the start of each line in [j1, j2], or
        remove up to -n leading spaces; one undo step. Cursor and
        selection stay with the text."""
        model = self.target
        changes = []  # (line start, spaces inserted (+) or removed (-))
        for ls in self._line_starts(j1, j2):
            if n > 0:
                changes.append((ls, n))
            else:
                head = model.get_text(ls, min(ls - n, len(model)))
                k = len(head) - len(head.lstrip(' '))
                if k:
                    changes.append((ls, -k))

        def moved(j):  # a position at a line start stays there
            return j + sum(d if d > 0 else -min(-d, j - ls)
                           for ls, d in changes if ls < j)
        index = moved(self.index)
        selection = self.selection and tuple(map(moved, self.selection))
        self.begin_undo_group()
        try:
            for ls, d in reversed(changes):
                i = self.abs_idx(ls)
                if d > 0:
                    new = TextModel(' ' * d, **model.get_style(ls))
                    self.add_undo(self._insert(self.flow, i, new))
                else:
                    self.add_undo(self._remove(self.flow, i, i - d))
        finally:
            self.end_undo_group()
        self.index = index
        if selection:
            self.selection = selection

    ### Controller
    def try_install_click_controller(self):
        """
        Install a click_installable controller at the current
        index, if any matches.

        Returns True if a controller was installed.
        """
        path = get_path(self.target.get_xtexel(), self.index)
        if self.canvas is not None:
            # Make sure the layout covers the current index before
            # find_box() (called from match()) walks it.
            self.canvas.builder.assure_index(self.abs_idx(self.index), self.flow)
        for cls in self.controller_registry:
            if not cls.click_installable:
                continue
            try:
                m = cls.match(self, path)
            except IndexError:
                continue
            if m is not None:
                self.set_controller(m)
                return True
        return False

    def set_controller(self, controller):
        self._controller = controller
        self._controller_dirty = False
        self.notify_views('controller_changed', controller)
        #self.refresh()

    def get_controller(self):
        # Computed lazily: by the time a controller is actually accessed
        # (drawing, key/mouse events), the layout has been brought up to
        # date for the relevant area (e.g. via assure_rect during paint),
        # so find_box() can succeed even though the layout build itself
        # is lazy/incremental.
        if self._controller_dirty:
            self._controller = self.compute_controller()
            self._controller_dirty = False
        return self._controller

    def update_controller(self):
        """Mark the controller stale so it gets re-evaluated on next access."""
        self._controller_dirty = True

    def compute_controller(self):
        """Install, switch, or remove the controller based on current conditions."""
        controller = self._controller
        path = get_path(self.target.get_xtexel(), self.index)

        if self.canvas is not None:
            # Box controllers need self.canvas.layout, which does not
            # exist yet during Editor.__init__. The layout build is lazy
            # and incremental, so make sure it covers the current index
            # before find_box() walks it.
            self.canvas.builder.assure_index(self.abs_idx(self.index), self.flow)

        if not (controller is None or controller.is_null):
            # Note: Controler is None during init!
            try:
                m = controller.match(self, path)
            except IndexError:
                m = None
            if m is not None:
                # The current controller still matches. We reinstall it.
                return m

        if self.canvas is not None:
            for cls in self.controller_registry:
                if not cls.auto_installable:
                    continue
                try:
                    m = cls.match(self, path)
                except IndexError:
                    continue
                if m is not None:
                    return m
        return NullController.match(self, path)


class TwoFlowEditor(Editor):
    # An editor for two flows (root and footnotes).
    def switch_target(self, flow, index):
        if flow == 0:
            target = self.root
            offset = 0
            anchor = 0
        elif flow == 1:
            model = self.get_footnotemodel(index)
            target = model
            offset = model.offset
            anchor = model.anchor
        else:
            raise AttributeError(flow)
        new = target, offset, anchor
        old = self.target, self.offset, self.anchor
        if new == old:
            return        
        self.target = target
        self.offset = offset
        self.anchor = anchor
        self.flow = flow
        self.notify_views('target_changed')

    def find_footnote(self, i):
        # helper: find the footnote-texel which holds position i in
        # the footnote-flow. Returns (texel, offset, chain), chain as
        # in footnotes.iter_footnotes - nested footnotes included.
        from ..footnotes.footnotes import iter_footnotes
        last = None
        for offset, chain, anchor in iter_footnotes(self.root.texel):
            texel = chain[-1][1]
            n = length(texel.content)
            if offset <= i < offset + n:
                return texel, offset, chain
            last = texel, offset, chain
        if last is not None and i == last[1] + length(last[0].content):
            # i is the position right after the last character of the
            # last footnote, ie. a valid cursor position at its end.
            return last
        raise IndexError(i)

    def get_footnotemodel(self, i):
        # Helper: Create a content model for the footnote at character
        # offset i in the footnote flow. For a nested footnote it is
        # a SubModel of the enclosing footnote's SubModel, so changes
        # are written back level by level up to the root.
        texel, offset, chain = self.find_footnote(i)
        model = self.root
        for anchor, footnote in chain:
            model = SubModel(model, anchor, offset, footnote.content)
        return model


def test_00():
    "insert & remove"    
    editor = Editor()
    editor.insert_text('Hello')
    editor.insert_text('World!')
    editor.index = 5
    editor.insert_text(' ')
    assert editor.root.get_text() == 'Hello World!'

    editor.selection = (5, 11)
    editor.remove()
    assert editor.root.get_text() == 'Hello!'
    
    editor.index = 5
    editor.insert_text(' Chris')
    assert editor.root.get_text() == 'Hello Chris!'

def test_01():
    "undo & redo"
    editor = Editor()
    editor.insert_text('Hello')
    editor.insert_text(' ')
    editor.insert_text('World!')
    assert editor.root.get_text() == 'Hello World!'
    # consecutive insertions are merged into undo steps of limited size
    assert editor.undocount() == 2
    editor.undo()
    assert editor.root.get_text() == 'Hello '
    editor.redo()
    assert editor.root.get_text() == 'Hello World!'
    editor.undo()
    editor.insert_text('Chris!')
    assert editor.root.get_text() == 'Hello Chris!'

def test_06():
    "undo merging for removals"
    editor = Editor()
    editor.insert_text('Hello World!')
    editor.clear_undo()

    # consecutive backspaces (deleting "World!" from the end)
    for i in range(6):
        editor.index = len(editor.root)
        editor.remove_range(editor.index-1, editor.index)
    assert editor.root.get_text() == 'Hello '
    assert editor.undocount() == 1
    editor.undo()
    assert editor.root.get_text() == 'Hello World!'

    editor.clear_undo()
    # consecutive deletes (deleting "Hello" from the start)
    for i in range(5):
        editor.remove_range(0, 1)
    assert editor.root.get_text() == ' World!'
    assert editor.undocount() == 1
    editor.undo()
    assert editor.root.get_text() == 'Hello World!'

def test_02():
    "find_footnote"
    from ..textmodel.submodel import mk_test, _get_text

    editor = TwoFlowEditor()
    editor.root = mk_test()

    texel, offset, anchor = editor.find_footnote(0)
    assert offset == 0
    n = length(texel.content)

    texel, offset, anchor = editor.find_footnote(100)
    assert offset == 0
    texel, offset, anchor = editor.find_footnote(n)
    assert offset == n
    m = length(texel.content)    
    texel, offset, anchor = editor.find_footnote(102)
    assert offset == n
    texel, offset, anchor = editor.find_footnote(192)
    assert offset == n
    texel, offset, anchor = editor.find_footnote(193)
    assert offset == n
    texel, offset, anchor = editor.find_footnote(194)
    assert offset == n

    # 195 is the position right after the last character of the last
    # footnote, ie. a valid end-of-model cursor position.
    texel, offset, anchor = editor.find_footnote(195)
    assert offset == n

    try:
        editor.find_footnote(196)
        assert False
    except IndexError:
        pass

def test_03():
    "target switching"
    from ..textmodel.submodel import mk_test, _get_text

    editor = TwoFlowEditor()
    editor.root = mk_test()

    editor.switch_target(1, 0)

    assert editor.flow == 1
    m = editor.target
    assert isinstance(m, SubModel)
    
    editor.insert_text("XYZ")
    t = _get_text(editor.root.texel)
    assert t.startswith("Albert Einstein[XYZAlbert Einstein (1879–1955)")
    editor.undo()
    t = _get_text(editor.root.texel)
    assert t.startswith("Albert Einstein[Albert Einstein (1879–1955)")

    # switching to second footnote
    editor.switch_target(1, 102)
    m = editor.target
    assert isinstance(m, SubModel)
    assert editor.flow == 1
    assert editor.offset == 102
    assert editor.anchor == 73

    assert editor.abs_idx(0) == editor.offset
    assert editor.local_idx(102) == 0
    editor.insert_text("XYZ")

    t = _get_text(editor.root.texel)
    assert "XYZErschienen" in t
    editor.undo()
    t = _get_text(editor.root.texel)
    assert "XYZErschienen" not in t

def test_03b():
    "nested footnotes: typing goes into the right footnote, undo works"
    from ..textmodel.submodel import _get_text
    from ..footnotes.footnotes import _nested_doc

    xtexel, f1, f2, f3 = _nested_doc()
    root = TextModel()
    root.set_xtexel(xtexel)
    editor = TwoFlowEditor()
    editor.root = root
    assert _get_text(root.texel) == 'ab[xy[uv]z]cd[w]'

    # flow: F1 'xy[F2]z' 0..5, F2 'uv' 5..8, F3 'w' 8..10
    assert editor.find_footnote(5)[1] == 5
    assert editor.find_footnote(8)[1] == 8

    editor.switch_target(1, 5)
    assert editor.offset == 5
    editor.index = editor.local_idx(5)
    editor.insert_text('X')
    assert _get_text(root.texel) == 'ab[xy[Xuv]z]cd[w]'

    editor.switch_target(1, 9)
    assert editor.offset == 9
    editor.index = editor.local_idx(9)
    editor.insert_text('Y')
    assert _get_text(root.texel) == 'ab[xy[Xuv]z]cd[Yw]'

    editor.undo()
    editor.undo()
    assert _get_text(root.texel) == 'ab[xy[uv]z]cd[w]'

def test_03c():
    "clear_styles and set_parstyle, with undo"
    editor = Editor()
    editor.insert_text('Hello World')
    editor.selection = (0, 5)
    editor.set_properties(bold=True)
    assert editor.root.get_style(2).get('bold')
    editor.clear_styles()
    assert not editor.root.get_style(2).get('bold')
    editor.undo()
    assert editor.root.get_style(2).get('bold')

    editor.index = 3
    editor.set_parstyle({'base': 'normal', 'alignment': 'right'})
    assert editor.root.get_parstyle(3).get('alignment') == 'right'
    editor.undo()
    assert editor.root.get_parstyle(3).get('alignment') != 'right'


def test_04():
    "controller"
    editor = Editor()
    editor.insert_text('Hello')
    editor.insert_text('World!')
    c = editor.controller
    i = editor.index
    editor.controller.handle_action('move_left', False)
    assert editor.index == i-1
    # moving the cursor triggers a new controller object
    assert editor.controller is not c
    editor.controller.handle_action('move_line_start', False)
    assert editor.index == 0
    
def test_05():
    "basic editing"
    from ..textmodel.submodel import mk_test, _get_text

    editor = TwoFlowEditor()
    editor.root = mk_test()
    r = editor.root

    editor.switch_target(1, 102) # switch to 2nd footnote
    assert _get_text(editor.target.texel)[29:63] == \
        'Zur Elektrodynamik bewegter Körper'

    # 1. insert text
    get = lambda i1, i2: editor.target.get_text(i1, i2)
    editor.index = 29
    editor.insert_text('XYZ')
    assert get(29, 35) == 'XYZZur'
    editor.undo()
    assert get(29, 32) == 'Zur'
    editor.redo()
    assert get(29, 35) == 'XYZZur'
    editor.undo()

    # 2. properties
    editor.selection = (29, 63)
    get = lambda i: editor.target.get_style(i)
    assert not get(29) 
    editor.set_properties(italic=True)
    assert get(29)
    editor.undo()
    assert not get(29)
    editor.redo()
    assert get(29)
    editor.undo()
    assert not get(29)

    # 3. current_style
    editor.index = 29
    assert not editor.current_style
    assert not get(29)
    editor.current_style = dict(bgcolor='red')
    editor.insert_text('XYZ')
    assert get(29)
    assert editor.current_style
    editor.undo()
    assert not get(29)
    editor.redo()
    assert get(29)
    editor.undo()
    assert not get(29)

    # 4. indent
    editor.selection = (29, 63)
    get = lambda i: editor.target.get_indent(i)
    assert get(29) == 0
    editor.indent()
    assert get(29) == 1    
    editor.undo()
    assert get(29) == 0
    editor.redo()
    assert get(29) == 1

    # 5. dedent
    editor.dedent()
    assert get(29) == 0
    editor.undo()
    assert get(29) == 1
    editor.redo()
    assert get(29) == 0
    
    
    
    
    
    
    
    
    

    
    
    
    
    
