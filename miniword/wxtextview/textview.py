# -*- coding: utf-8 -*-

from .testdevice import TestDevice
from .boxes import prev_row, next_row
from ..textmodel.viewbase import ViewBase, overridable_property
from ..textmodel.modelbase import Model
from ..textmodel.textmodel import dump_range
from ..textmodel.texeltree import length, iter_childs
from ..textmodel.utils import find_weight, get_weight, get_localroot, get_path
from ..textmodel import TextModel
from contextlib import contextmanager
import sys
import types


debug = 0
#debug = 1

def undo(info):
    if callable(info[0]):
        func = info[0]
        args = info[1:]    
        redo = func(*args)
    else:
        redo = []
        for child in reversed(info):
            redo.append(undo(child))
    return redo


inf = sys.maxsize


class NullEditor:
    """Always-active no-op editor; keeps the editor slot non-null.

    Implements the full editor protocol with harmless defaults so that
    TextView can call editor methods unconditionally without None-checks.
    """
    is_null = True

    def __init__(self, docview):
        self.docview = docview
        
    # Events — always return False (not consumed)
    def on_leftdown(self, event): return False
    def on_motion(self, event):   return False
    def on_leftup(self, event):   return False
    def on_key(self, key, event): return False

    # Queries — None means "use DocumentView default"
    def selected(self, i1, i2):   return None
    def adjust_viewport(self):    return None

    # Draw cursor + selection
    def draw(self, painter):
        self.docview.draw_cursor(painter)
        self.docview.draw_selection(painter)

    def handle_action(self, action, shift, ctx): return False

    # Clipboard — delegate to docview    
    def copy(self):  self.docview.copy()
    def cut(self):   self.docview.cut()
    def paste(self): self.docview.paste()
    


def _line_starts(model, i1, i2):
    """Return list of line-start indices for all lines overlapping [i1, i2]."""
    starts = []
    ls = model.linestart(i1)
    while ls <= i2:
        starts.append(ls)
        end = model.lineend(ls)
        if end + 1 >= len(model):
            break
        ls = end + 1
    return starts


def right_limit(texel, i0, i):
    if i <= i0 or i>= i0+length(texel):
        return inf 
    if texel.is_container: 
        mutability = texel.get_mutability()
        k = -1    
        for i1, i2, child in iter_childs(texel): 
            k += 1
            if i == i0+i1: 
                if not mutability[k]: 
                    return i
                return i0+i2 
            if i0+i1 < i < i0+i2:  # mitten in dem Element
                return min(i0+i2, right_limit(child, i0+i1, i))
    if texel.is_group:
        for i1, i2, child in iter_childs(texel): 
            if i0+i1 < i < i0+i2:  # mitten in dem Element
                return right_limit(child, i0+i1, i)
    return inf


def left_limit(texel, i0, i):
    # i ist im absoluten KS
    if i <= i0 or i>= i0+length(texel):
        return 0
    if texel.is_container: 
        mutability = texel.get_mutability()
        k = -1    
        for i1, i2, child in iter_childs(texel): 
            k += 1
            if i == i0+i2: 
                if not mutability[k]: 
                    return i
                return i0+i2 
            if i0+i1 < i < i0+i2:  # mitten in dem Element
                return max(i0+i1, left_limit(child, i0+i1, i))
    if texel.is_group:
        for i1, i2, child in iter_childs(texel):
            if i0+i1 < i < i0+i2:  # mitten in dem Element
                return left_limit(child, i0+i1, i)
    return 0


class TextView(ViewBase, Model):
    index = overridable_property('index')
    _index = 0
    selection = overridable_property('selection') # NOTE: i2 can also
                                                  # be smaller than
                                                  # i1!
    _selection = None
    layout = overridable_property('layout')
    maxw = overridable_property('maxw')
    _maxw = 0
    zoom = overridable_property('zoom')
    scale = overridable_property('scale')
    _zoom = 1.0
    _scrollrate = 10, 10
    _TextModel = TextModel

    min_zoom    = 0.2
    max_zoom    = 5.0
    zoom_step   = 0.1

    _pending_range = None
    _inhibit_depth = 0


    
    def __init__(self):
        ViewBase.__init__(self)
        self.editor = NullEditor(self)
        self.clear_undo()
        self.set_model(self._TextModel(''))
        assert self.builder is not None

    ### Editor slot

    editor_registry = []  # editor classes, priority order; subclasses may extend

    def try_install_click_editor(self):
        """Install a click_installable editor at the current index, if any matches.

        Returns True if an editor was installed.
        """
        path = get_path(self.model.get_xtexel(), self.index)
        for cls in self.editor_registry:
            if not cls.click_installable:
                continue
            m = cls.match(self, path)
            if m is not None:
                i1, i2, depth, texel = m
                editor = cls(self, i1, i2, depth)
                self.install_editor(editor, texel)
                return True
        return False

    def install_editor(self, editor, texel):
        """Installs an editor for the texel at positions i1 to i2 in depth d."""        
        editor.install(texel)
        self.editor = editor
        self.notify_views('editor_changed', editor)
        self.refresh()

    def reinstall_editor(self, texel):
        """Called after properties change."""        
        self.editor.reinstall(texel)

    def remove_editor(self):
        if not self.editor.is_null:
            self.editor = NullEditor(self)
            self.notify_views('editor_changed', self.editor)
            self.refresh()

    def update_editor(self):
        """Install, switch, or remove the editor based on current conditions.
        """        
        index = self.index
        editor = self.editor
        path = get_path(self.model.get_xtexel(), index)

        if not editor.is_null:
            m = editor.match(self, path)
            if m is not None:
                i1, i2, depth, texel = m
                assert i1 == editor.i1
                assert i2 == editor.i2
                self.reinstall_editor(texel)
                return
            self.remove_editor()

        for cls in self.editor_registry:
            if not cls.auto_installable:
                continue
            m = cls.match(self, path)
            if m is not None:
                i1, i2, depth, texel = m
                editor = cls(self, i1, i2, depth)
                self.install_editor(editor, texel)
                return

    def create_builder(self):
        # we install the BaseClass as a dummy builder
        from .builder import TestBuilder
        return TestBuilder()

    def clear_caches(self):
        self.builder.clear_caches()

    def set_model(self, model):
        ViewBase.set_model(self, model)
        self.builder = self.create_builder()
        self.rebuild()

    def get_layout(self):
        return self.builder.get_layout()
    
    def rebuild(self):
        self.builder.rebuild()
        self.refresh()

    def join_undo(self, info2, info1):
        # we are joining similar undo entries
        if 0:
            print("join")
            print("info1=", info1)
            print("info2=", info2)
        if info1[0] == info2[0]:
            if info1[0] == self._remove:
                i1, i2 = info1[1:]
                j1, j2 = info2[1:]
                if i2 == j1 and j2-i1<10:
                    return [(self._remove, i1, j2)]
            elif info1[0] == self._undo_remove:
                s, i1, i2 = info1[1:]
                t, j1, j2 = info2[1:]
                #print "i1, i2:", i1, i2
                #print "j1, j2:", j1, j2
                if j2 == i1 and i2-j1<10:
                    t.insert(len(t), s)
                    return [(self._undo_remove, t, j1, i2)]
                if i1 == j1 and i2-j1<10:
                    t.insert(0, s)
                    #print "remove:", repr(t.get_text()), i1, i2+j2-j1
                    return [(self._undo_remove, t, i1, i2+j2-j1)]
                    
        return [info2, info1]

    def undo(self):
        if len(self._undoinfo) > 0:
            self.add_redo(undo(self._undoinfo[0]))
            del self._undoinfo[0]
                
    def add_undo(self, info, clear_redo=1):
        if info is None:
            return
        if self._undo_groups:
            # Grouping active: collect instead of committing immediately.
            self._undo_groups[-1].append(info)
            return
        if len(self._undoinfo):
            joined = self.join_undo(info, self._undoinfo[0])
            self._undoinfo = joined + self._undoinfo[1:]
        else:
            self._undoinfo.insert(0, info)
        if clear_redo:
            self._redoinfo = []
        self.notify_views('undo_changed')

    def redo(self):
        if len(self._redoinfo) > 0:
            self.add_undo(undo(self._redoinfo[0]), 0)
            del self._redoinfo[0]

    def add_redo(self, info):
        # Internal method: add a single redo info
        self._redoinfo.insert(0, info)
        self.notify_views('undo_changed')

    def begin_undo_group(self):
        """Start collecting undo entries into a single group."""
        self._undo_groups.append([])

    def end_undo_group(self):
        """Flush the collected group as one atomic undo entry."""
        l = self._undo_groups.pop()
        if not l:
            return
        n = len(self._undo_groups)
        if n:
            # Append entries to the parent group
            self._undo_groups[n-1].extend(l)
        else:
            # Insert into undo stack directly
            self._undoinfo.insert(0, l)
            self._redoinfo = []
            self.notify_views('undo_changed')
        
    def undocount(self):
        return len(self._undoinfo)

    def redocount(self):
        return len(self._redoinfo)

    def clear_undo(self):
        self._undoinfo = []
        self._redoinfo = []
        self._undo_groups = []


    ### Editing
    def insert(self, i, textmodel):
        self.model.insert(i, textmodel)
        self.index = i+len(textmodel)
        info = self._remove, i, i+len(textmodel)
        self.add_undo(info)

    def insert_text(self, i, text, **style):
        model = self.model.__class__(text, **style)  
        return self.insert(i, model)

    def type_char(self, char):
        if self.has_selection():
            s1, s2 = sorted(self.selection)
            e1, e2 = self.model.expand_range(s1, s2)
            self.remove(e1, e2)
        self.insert_text(self.index, char, **self.get_current_style())
        self.Refresh()
    
    def remove(self, i1, i2):
        info = self._remove(i1, i2)
        self.add_undo(info)
        self.index = i1

    def _remove(self, i1, i2):
        old = self.model.remove(i1, i2)
        self.index = i1
        return self._undo_remove, old, i1, i2

    def _undo_remove(self, old, i1, i2):
        self.model.insert(i1, old)
        self.index = i2
        return self._remove, i1, i2

    def clear_styles(self, i1, i2):
        styles = self.model.clear_styles(i1, i2)
        info = self._set_styles, i1, styles
        self.add_undo(info)

    def set_properties(self, i1, i2, **properties):
        styles = self.model.set_properties(i1, i2, **properties)
        info = self._set_styles, i1, styles
        self.add_undo(info)

    def clear_properties(self, i1, i2, *keys):
        styles = self.model.clear_properties(i1, i2, *keys)
        info = self._set_styles, i1, styles
        self.add_undo(info)
        
    def _set_styles(self, i, styles):
        styles = self.model.set_styles(i, styles)
        return self._set_styles, i, styles

    def set_parstyle(self, i, style):
        styles = self.model.set_parstyle(i, style)
        info = self._set_parstyles, i, styles
        self.add_undo(info)

    def set_parproperties(self, i1, i2, **properties):
        styles = self.model.set_parproperties(i1, i2, **properties)
        info = self._set_parstyles, i1, styles
        self.add_undo(info)

    def clear_parproperties(self, i1, i2, *keys):
        styles = self.model.clear_parproperties(i1, i2, *keys)
        info = self._set_parstyles, i1, styles
        self.add_undo(info)
        
    def _set_parstyles(self, i, styles):
        styles = self.model.set_parstyles(i, styles)
        return self._set_parstyles, i, styles

    def _set_indents(self, i1, i2, indents):
        indents = self.model.set_indents(i1, i2, indents)
        return self._set_indents, i1, i2, indents

    def indent(self):
        model = self.model
        if self.has_selection():
            i1, i2 = sorted(self.selection)
        else:
            i1 = i2 = self.index
        i2 = model.lineend(i2)+1
        old = model.increase_indent(i1, i2)
        self.add_undo((self._set_indents, i1, i2, old))

    def dedent(self):
        model = self.model
        if self.has_selection():
            i1, i2 = sorted(self.selection)
        else:
            i1 = i2 = self.index
        i2 = model.lineend(i2)+1
        old = model.decrease_indent(i1, i2)
        self.add_undo((self._set_indents, i1, i2, old))

    def shift(self, i1, i2, n=4):
        """Insert n spaces at each line start in index range [i1, i2]."""
        model = self.model
        has_sel = self.has_selection()
        s1, s2 = self.selection if has_sel else (0, 0)
        index = self.index
        starts = _line_starts(model, i1, i2)
        spaces = ' ' * n
        for ls in reversed(starts):
            model.insert_text(ls, spaces)
            if index >= ls: index += n
            if s1 >= ls: s1 += n
            if s2 >= ls: s2 += n
        self.index = index
        if has_sel: self.selection = (s1, s2)
        shifted = [ls + j * n for j, ls in enumerate(starts)]
        self.add_undo((self._unshift, shifted, n))

    def _unshift(self, starts, n):
        model = self.model
        has_sel = self.has_selection()
        s1, s2 = self.selection if has_sel else (0, 0)
        index = self.index
        memo = []
        for ls in reversed(starts):
            j = ls
            while j < ls + n and j < len(model) and model.get_text(j, j + 1) == ' ':
                j += 1
            memo.append(model.remove(ls, j))
            rn = j - ls
            if index > ls: index = ls + max(0, index - ls - rn)
            if s1 > ls: s1 = ls + max(0, s1 - ls - rn)
            if s2 > ls: s2 = ls + max(0, s2 - ls - rn)
        self.index = index
        if has_sel: self.selection = (s1, s2)
        return self._undo_unshift, starts, memo, n

    def unshift(self, i1, i2, n=4):
        """Remove up to n leading spaces from each line start in index range [i1, i2]."""
        info = self._unshift(_line_starts(self.model, i1, i2), n)
        self.add_undo(info)

    def _undo_unshift(self, starts, memo, n):
        model = self.model
        has_sel = self.has_selection()
        s1, s2 = self.selection if has_sel else (0, 0)
        index = self.index
        for ls, removed in zip(starts, reversed(memo)):
            rn = len(removed)
            model.insert(ls, removed)
            if index >= ls: index += rn
            if s1 >= ls: s1 += rn
            if s2 >= ls: s2 += rn
        self.index = index
        if has_sel: self.selection = (s1, s2)
        return self._unshift, starts, n

    def transform(self, fun):
        # Apply a tranforming function to the texeltree. Can change
        # index.
        texel = self.model.texel
        new = fun(texel)
        self._set_texel(new)

    def _set_texel(self, new):
        # Helper: exchange the texeltree & add undo
        old = self.model.texel
        self.model.texel = new
        self.index = min(len(self.model), self.index)        
        self.rebuild()
        info = self._set_texel, old
        self.add_undo(info)

    def get_zoom(self):
        return self._zoom

    def set_zoom(self, zoom):
        self._zoom = zoom

    def get_scale(self):
        return self._zoom

    def get_maxw(self):
        return self._maxw

    def get_client_size(self):
        return 800, 600  # headless / test default; wx subclasses override

    def set_maxw(self, maxw):
        if maxw == self._maxw:
            return
        self._maxw = maxw
        self.builder.set_maxw(maxw)
        self.refresh()
        self.notify_views('maxw_changed')

    def insert_newline(self, index, style, parstyle):
        indent = self.model.get_indent(index)
        tmp = self._TextModel('\n', **style)
        tmp.set_parstyle(0, parstyle)
        tmp.set_indent(0, indent)
        self.insert(index, tmp)

    def compute_index(self, x, y):
        if y >= self.layout.height:
            return len(self.model)-1
        if y < 0:
            return 0
        return self.layout.get_index(x, y)


    ### Actions
    handlers = []  # populated after class definition

    def _build_ctx(self):
        # Helper: builds the context for action handling
        model = self.model
        index = self.index
        layout = self.layout
        style = self.get_current_style()
        parstyle = model.get_parstyle(index)
        row, col = self.current_position()
        rect = layout.get_rect(index, 0, 0)
        x, y = rect.x1, rect.y1
        if self.has_selection():
            s1, s2 = sorted(self.selection)
            e1, e2 = model.expand_range(s1, s2)
        else:
            s1 = s2 = e1 = e2 = index
        view = self
        def del_selection():
            if view.has_selection():
                view.remove(e1, e2)
        return types.SimpleNamespace(
            model=model, index=index, layout=layout,
            style=style, parstyle=parstyle,
            row=row, col=col, x=x, y=y,
            s1=s1, s2=s2, e1=e1, e2=e2,
            del_selection=del_selection,
            path=get_path(model.get_xtexel(), index),
        )

    def handle_action(self, action, shift=False):
        ctx = self._build_ctx()
        if not self.editor.handle_action(action, shift, ctx):
            for handler in self.handlers:
                if handler(self, action, shift, ctx):
                    break
        self.refresh()

    def copy(self):
        if not self.has_selection():
            return        
        s1, s2 = self.get_selected()[0] # XXX Assuming just one region
        part = self.model[s1:s2]
        self.to_clipboard(part)

    def paste(self):
        if self.has_selection():
            for s1, s2 in self.get_selected():
                self.model.remove(s1, s2)
                self.index = s1
        textmodel = self.read_clipboard()
        if textmodel is not None:
            self.insert(self.index, textmodel)
                

    def cut(self):
        if self.has_selection():
            self.copy()
            for s1, s2 in self.get_selected():
                self.remove(s1, s2)
         
    def to_clipboard(self, textmodel):
        raise NotImplemented()

    def read_clipboard(self):
        raise NotImplemented()
         
    def select_word(self, x, y):
        i = self.layout.get_index(x, y)
        if i is None:
            return
        model = self.model
        n = len(model)
        try:
            while not model.get_text(i-1, i).isalnum():
                i = i-1
            while model.get_text(i-1, i).isalnum():
                i = i-1
        except IndexError:
            i = 0
        i1 = i
        i = i1
        try:
            while not model.get_text(i, i+1).isalnum():
                i = i+1
            while model.get_text(i, i+1).isalnum():
                i = i+1
        except IndexError:
            i = n
        i2 = i
        self.index = i2
        self.selection = (i1, i2)

    def refresh(self):
        pass

    def check(self):
        from ..textmodel.treebase import is_root_efficient
        assert is_root_efficient(self.layout)

    def rebuild_range(self, i1, i2, delta):
        self.builder.rebuild_range(i1, i2, delta)

    def _rebuild_with_progress(self, i1, i2, delta):
        self.builder.rebuild_range(i1, i2, delta)
        self.refresh()

    def ensure_viewport(self):
        pass

    def adjust_viewport(self):
        pass

    def ensure_index(self, index=None):
        pass

    def _accumulate(self, i1, i2, delta=0):
        self._pending_range = accumulate(self._pending_range, (i1, i2, delta))

    @contextmanager
    def atomic(self):
        """Group multiple model/stylesheet changes into one layout rebuild."""
        self.begin_undo_group()
        self._inhibit_depth += 1
        try:
            yield
        finally:
            self.end_undo_group()
            self._inhibit_depth -= 1
        if self._inhibit_depth == 0 and self._pending_range is not None:
            i1, i2, delta = self._pending_range
            self._pending_range = None
            self._rebuild_with_progress(i1, i2, delta)

    ### Signals issued by model
    def properties_changed(self, model, i1, i2):
        self.rebuild_range(i1, i2, 0)
        self.refresh()

    def inserted(self, model, i, n):
        if not self.editor.is_null:
            self.remove_editor()
        self.rebuild_range(i, i, n)
        if debug:
            self.check()
        if i>= self.index:
            self.index += n
        if self._selection is not None:
            s1, s2 = self.selection
            if i >= s1:
                s1 += n
            if i >= s2:
                s2 += n
            self.selection = s1, s2
        self.refresh()

    def removed(self, model, i, text):
        if not self.editor.is_null:
            self.remove_editor()
        self.rebuild_range(i, i, -len(text))
        n = len(text)
        i1 = i
        i2 = i+n
        m = len(model)
        index = self.index
        if index >= i2:
            self.index = index-n
        elif index > i1:
            self.index = i1
        if self._selection is not None:
            s1, s2 = self.selection
            if s1 >= i2:
                s1 -= n
            elif s1 > i1:
                s1 = i1
            if s2 >= i2:
                s2 -= n
            elif s2 > i1:
                s2 = i1
            self.selection = min(s1, m), min(s2, m)
        self.refresh()

    def keep_cursor_on_screen(self):
        pass
        
    ### Index
    def set_index(self, index, extend=False, update=True):
        old = self._index
        if index < 0:
            index = 0
        elif index > len(self.model):
            index = len(self.model)
        if index != self._index:
            self._index = index
            if index == 0:
                self._current_style = dict(self.model.get_style(0))
            else:
                self._current_style = dict(self.model.get_style(index - 1))
            if extend:
                self.extend_selection()
            elif update:
                self.start_selection()
            self.adjust_viewport()
            self.refresh()
            self.notify_views('index_changed')
        if old != index and not self.editor.is_null:
            self.remove_editor()
        self.update_editor()

    def get_index(self):
        return self._index

    def current_position(self):
        model = self.model
        i = self.index
        if model is None or i == 0:
            return 0, 0
        el, off = get_localroot(model.texel, i)
        local_i = i - off
        row = get_weight(el, 2, local_i)
        col = local_i - find_weight(el, row, 2)
        return row, col

    def move_up(self, shift=False):
        x = self.layout.get_rect(self.index, 0, 0).x1
        i = _navigate(self.layout, self.index, x, prev_row)
        if i is not None:
            self.set_index(i, shift)

    def move_down(self, shift=False):
        x = self.layout.get_rect(self.index, 0, 0).x1
        i = _navigate(self.layout, self.index, x, next_row)
        if i is not None:
            self.set_index(i, shift)

    def move_cursor_to(self, row, col, extend=False, update=True):
        model = self.model
        el, off = get_localroot(model.texel, self.index)
        nlines = el.weights[2] + 1
        row = max(0, min(row, nlines - 1))
        ls = find_weight(el, row, 2)
        try:
            ll = find_weight(el, row + 1, 2) - ls
        except Exception:
            ll = length(el) - ls
        col = max(0, min(col, ll - 1))
        self.set_index(off + ls + col, extend, update)

    def get_selection(self):
        return self._selection

    def set_selection(self, selection):
        old = self._selection
        if selection == old:
            return
        if old is not None:
            i1, i2 = old
        self._selection = selection
        self.refresh()
        self.notify_views('selection_changed')

    def has_selection(self):
        selection = self.selection
        if selection is None:
            return False
        return selection[0] != selection[1]

    def get_selected(self):
        selection = self.selection
        if selection is None:
            return []
        s1, s2 = sorted(selection)
        if s1 == s2:
            return []
        result = self.editor.selected(s1, s2)
        if result is not None:
            return result
        return [self.model.expand_range(s1, s2)]

    def expand_lines(self, i1, i2):
        """Extend (i1, i2) to cover complete lines.

        Calls expand_range first so that i1 and i2 are on the same
        nesting level.  Then shifts the left edge to the start of i1's
        line and the right edge past the NL of i2's line.
        """
        model = self.model
        e1, e2 = model.expand_range(i1, i2)
        s1 = model.linestart(e1)
        s2 = model.lineend(e2) + 1
        return s1, s2

    def start_selection(self):
        index = self.index
        self.selection = index, index
        
    def extend_selection(self):
        # Moves the selection endoint to index
        selection = self.selection
        index = self.index
        if selection is None:
            self.selection = index, index
        else:
            self.selection = selection[0], index

    ### styles

    def fill_style(self, parstyle, style):
        # In the base implementation we do not use any
        # parstyle. Therefore we simply return style. Can be overriden
        # if something more complex is needed.
        return style

    def get_filled_style(self, i):
        """Returns the filled style dict for index i."""
        s = self.model.get_style(i)
        p = self.model.get_parstyle(i)
        return self.fill_style(p, s)        

    _current_style = None    
    def get_current_style(self):
        """Gets the style for the next insert-operation."""
        if self._current_style is None:
            index = self.index
            if index == 0:
                self._current_style = dict(self.model.get_style(index))
            else:
                self._current_style = dict(self.model.get_style(index - 1))
        return self._current_style

    def set_current_style(self, **properties):
        """Sets the style for the next insert-operation."""
        self.get_current_style().update(properties)
        self.notify_views('current_style_changed')

    def clear_current_style(self, *keys):
        """Clears the style for the next insert-operation."""
        style = self.get_current_style()
        for key in keys:
            style.pop(key, None)
        self.notify_views('current_style_changed')

    ### Drawing
    def has_focus(self):
        # Dummy. Needs to be overriden by GUI.
        return True
    
    def draw_background(self, painter):
        pass

    def draw(self, painter):
        self.draw_background(painter)
        self.layout.draw(0, 0, painter)
        self.editor.draw(painter)

    def draw_cursor(self, painter):
        # note that draw_cursor is called by editor
        if not self.has_focus():
            return
        style = self.get_filled_style(self.index).copy()
        current = self.get_current_style()
        style.update(current)
        self.layout.draw_cursor(self.index, 0, 0, painter, style)

    def draw_selection(self, painter):
        # note that draw_selection is called by editor
        for j1, j2 in self.get_selected():
            self.layout.draw_selection(j1, j2, 0, 0, painter)
        




def _navigate(layout, i, x, row_fn):
    first = row_fn(layout, i)
    if first is None:
        return None
    target_y, candidates, cur = first[3], [first], first
    while True:
        nxt = row_fn(layout, cur[0])
        if nxt is None or nxt[3] != target_y:
            break
        candidates.append(nxt)
        cur = nxt
    best_i, best_dist = None, float('inf')
    for r1, r2, rx, ry, row in candidates:
        j = r1 + row.get_index(x - rx, row.height)
        dist = abs(layout.get_rect(j, 0, 0).x1 - x)
        if dist < best_dist:
            best_dist, best_i = dist, j
    return best_i


def default_handler(view, action, shift, ctx):
    """Fallback handler: implements all standard editing actions."""
    model = ctx.model
    index = ctx.index
    row, col = ctx.row, ctx.col
    x, y = ctx.x, ctx.y
    style, parstyle = ctx.style, ctx.parstyle
    e1, e2 = ctx.e1, ctx.e2

    if action == 'dump_info':
        dump_range(model.texel, e1, e2)
        r, c, i0 = model.index2position(index)
        print("index=", index, "row=", r, "col=", c, "i0=", i0)
    elif action == 'dump_boxes':
        ctx.layout.dump_boxes(0, 0, 0)
    elif action == 'move_word_end':
        i, n = index, len(model)
        try:
            while not model.get_text(i, i+1).isalnum(): i += 1
            while model.get_text(i, i+1).isalnum():     i += 1
        except IndexError:
            i = n
        view.set_index(i, shift)
    elif action == 'move_right':
        view.set_index(index + 1, shift)
    elif action == 'move_word_begin':
        i = index
        try:
            while not model.get_text(i-1, i).isalnum(): i -= 1
            while model.get_text(i-1, i).isalnum():     i -= 1
        except IndexError:
            i = 0
        view.set_index(i, shift)
    elif action == 'move_left':
        view.set_index(index - 1, shift)
    elif action == 'move_paragraph_end':
        i, n = model.linestart(index), len(model)
        while model.lineend(i) < n and model.linelength(i) == 1:
            i = model.lineend(i) + 1
        while model.lineend(i) < n and model.linelength(i) > 1:
            i = model.lineend(i) + 1
        view.set_index(i, shift)
    elif action == 'move_down':
        view.move_cursor_to(row + 1, col, shift)
    elif action == 'move_paragraph_begin':
        i = model.linestart(index)
        while i > 0 and model.linelength(model.linestart(i - 1)) == 1:
            i = model.linestart(i - 1)
        while i > 0 and model.linelength(model.linestart(i - 1)) > 1:
            i = model.linestart(i - 1)
        view.set_index(i, shift)
    elif action == 'move_up':
        view.move_cursor_to(row - 1, col, shift)
    elif action == 'move_line_start':
        view.set_index(model.linestart(index), shift)
    elif action == 'move_line_end':
        view.set_index(model.lineend(index), shift)
    elif action == 'move_page_down':
        _, height = view.get_client_size()
        view.set_index(view.compute_index(x, y + height / view.scale), shift)
    elif action == 'move_page_up':
        _, height = view.get_client_size()
        view.set_index(view.compute_index(x, y - height / view.scale), shift)
    elif action == 'move_document_start':
        view.set_index(0, shift)
    elif action == 'move_document_end':
        view.set_index(len(model), shift)
    elif action == 'select_all':
        view.selection = (0, len(model))
    elif action == 'insert_newline':
        view.insert_newline(index, style, parstyle)
    elif action == 'backspace':
        if view.has_selection():
            j1, j2 = model.expand_range(ctx.s1 - 1, ctx.s2)
            view.remove(e1, e2) if j2 != e2 else view.remove(j1, j2)
        elif index > 0:
            j1, j2 = model.expand_range(index - 1, index)
            view.remove(j1, j2)
    elif action == 'copy':
        view.editor.copy()
    elif action == 'paste':
        view.editor.paste()
    elif action == 'cut':
        view.editor.cut()
    elif action == 'delete':
        if view.has_selection():
            ctx.del_selection()
        elif index < len(model):
            j1, j2 = model.expand_range(index, index + 1)
            view.remove(j1, j2)
    elif action == 'indent':
        view.indent()
    elif action == 'dedent':
        view.dedent()
    elif action == 'undo':
        view.undo()
    elif action == 'redo':
        view.redo()
    elif action == 'del_line_end':
        el, off = get_localroot(model.texel, index)
        try:
            i = find_weight(el, row + 1, 2) - 1 + off
        except Exception:
            i = length(el) - 1 + off
        if i == index:
            i += 1
        i = min(i, right_limit(model.texel, 0, index))
        j1, j2 = model.expand_range(index, i)
        view.to_clipboard(model[j1:j2])
        view.remove(j1, j2)
    elif action == 'del_word_left':
        i = index
        try:
            while not model.get_text(i-1, i).isalnum(): i -= 1
            while model.get_text(i-1, i).isalnum():     i -= 1
        except IndexError:
            i = 0
        i = max(i, left_limit(model.texel, 0, index))
        j1, j2 = model.expand_range(i, index)
        view.remove(j1, j2)
    else:
        return False # not handled
    return True


from .editing_modes import text_handler
TextView.handlers = [text_handler, default_handler]


def accumulate(r1, r2):
    """Combine two consecutive update ranges into one.

    r1 = (i1, i2, delta) in original model coordinates.
    r2 = (b1, b2, d2)    in model coordinates after r1 was applied.
    """
    if r1 is None:
        return r2
    elif r2 is None:
        return r1

    pi1, pi2, pd = r1
    b1,  b2,  d2 = r2

    pi2_m0  = pi2 + max(0, -pd)
    pi1_m1  = pi1 + max(0,  pd)

    if b1 > pi1_m1:
        b1o = b1 - pd
        b2o = b2 - pd
    elif b2 < pi1:
        b1o = b1
        b2o = b2
    else:
        b1o = min(b1, pi1)
        b2o = max(b2 - pd, pi2_m0)

    return (min(pi1, b1o), max(pi2_m0, b2o), pd + d2)




class TestTextView(TextView):

    def create_builder(self):
        from .simplelayout import Builder
        return Builder(
            self.model,
            device=TestDevice(),
            maxw=80)

    
testtext = u"""Ein m\xe4nnlicher Briefmark erlebte
Was Sch\xf6nes, bevor er klebte.
Er war von einer Prinzessin beleckt.
Da war die Liebe in ihm geweckt.
Er wollte sie wiederk\xfcssen,
Da hat er verreisen m\xfcssen.
So liebte er sie vergebens.
Das ist die Tragik des Lebens.

(Joachim Ringelnatz)"""


def init_testing():
    model = TextModel(testtext)
    model.set_properties(15, 24, fontsize=14)
    model.set_properties(249, 269, fontsize=14)
    view = TestTextView()
    view.model = model
    assert len(view.layout) == len(model)+1
    return locals()


def test_00():
    "accumulate"
    assert accumulate((2, 5, 0), (8, 12, 0)) == (2, 12, 0)
    assert accumulate((8, 12, 0), (2, 5, 0)) == (2, 12, 0)
    assert accumulate((2, 8, 0), (5, 12, 0)) == (2, 12, 0)
    assert accumulate((5, 5, 1), (10, 10, 1)) == (5, 9, 2)
    assert accumulate((10, 10, 1), (3, 3, 1)) == (3, 10, 2)
    assert accumulate((5, 5, 3), (6, 6, 0)) == (5, 5, 3)
    assert accumulate((5, 5, -3), (7, 7, 0)) == (5, 10, -3)
    assert accumulate((5, 5, -3), (2, 3, 0)) == (2, 8, -3)
    assert accumulate((3, 3, 2), (8, 8, -4)) == (3, 6, -2)
    assert accumulate((5, 5, 2), (3, 10, 0)) == (3, 8, 2)
    assert accumulate((5, 5, -3), (3, 7, 0)) == (3, 10, -3)


def test_02():
    ns = init_testing()
    view = ns['view']
    view.cursor = 5
    view.selection = 3, 6
    return ns


def test_03():
    "set_properties, insert_text, remove"
    ns = init_testing()
    model = ns['model']
    model.set_properties(10, 20, fontsize=15)
    n = len(model)
    text = '\n12345\n'
    model.insert_text(5, text)
    model.remove(5, 5 + len(text))
    assert len(model) == n


def test_04():
    "insert/remove"
    ns = init_testing()
    model = ns['model']
    text = model.get_text()
    n = len(model)
    for i in range(len(text)):
        model.insert_text(i, 'X')
        assert len(model) == n + 1
        model.remove(i, i + 1)
        assert len(model) == n

    for i in range(n - 1):
        old = model.remove(i, i + 1)
        assert len(model) == n - 1
        model.insert(i, old)
        assert len(model) == n


def test_05():
    "join_undo"
    ns = init_testing()
    view = ns['view']
    for i, ch in enumerate('abcd'):
        view.add_undo(view.insert(i, TextModel(ch)))
    assert len(view._undoinfo) == 1

    view._undoinfo = []
    view.add_undo(view.remove(10, 11))
    view.add_undo(view.remove(9, 10))
    assert len(view._undoinfo) == 1


def test_06():
    "grouping undo"
    view = TestTextView()
    view.begin_undo_group()
    view.insert_text(0, 'Hello X')
    assert view.undocount() == 0
    assert len(view._undo_groups) == 1
    view.remove(6, 7)
    view.insert_text(6, 'world!')
    view.end_undo_group()
    assert view.model.get_text() == "Hello world!"
    assert view.undocount() == 1
    view.undo()
    assert view.model.get_text() == ""

    
def test_07():
    "shift / unshift with undo"
    view = TestTextView()
    view.set_model(TextModel('ab\ncd\nef\n'))
    n0 = len(view.model)

    view.shift(0, 5)   # covers first two lines
    assert view.model.get_text() == '    ab\n    cd\nef\n'
    assert len(view.model) == n0 + 8

    view.unshift(0, 9) # same two lines
    assert view.model.get_text() == 'ab\ncd\nef\n'
    assert len(view.model) == n0

    view.undo()        # redo unshift → back to shifted
    assert view.model.get_text() == '    ab\n    cd\nef\n'

    view.undo()        # redo shift → back to original
    assert view.model.get_text() == 'ab\ncd\nef\n'


