# -*- coding: latin-1 -*-


from ..textmodel.viewbase import ViewBase, overridable_property
from ..textmodel.modelbase import Model
from ..textmodel.textmodel import dump_range
from ..textmodel.texeltree import length, iter_childs
from ..textmodel import TextModel
import sys


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
    _zoom = 1.0
    _scrollrate = 10, 10
    _TextModel = TextModel
    def __init__(self):
        ViewBase.__init__(self)
        self.clear_undo()
        self.set_model(self._TextModel(''))
        assert self.builder is not None
        assert self.layout is not None

    def create_builder(self):
        raise NotImplementedError

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
        assert self.layout is not None

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
        if self._undo_group is not None:
            # Grouping active: collect instead of committing immediately.
            self._undo_group.append(info)
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

    def undocount(self):
        return len(self._undoinfo)

    def redocount(self):
        return len(self._redoinfo)

    def clear_undo(self):
        self._undoinfo = []
        self._redoinfo = []
        self._undo_group = None  # None = not grouping; list = collecting entries
        self._undo_stack = []   # stack of parent groups for nested begin/end pairs

    # ------------------------------------------------------------------
    # Undo grouping
    # ------------------------------------------------------------------

    def begin_undo_group(self):
        """Push a new undo group onto the stack."""
        self._undo_stack.append(self._undo_group)
        self._undo_group = []

    def end_undo_group(self):
        """Pop the current undo group.

        If a parent group is active, the entries are merged into it.
        Only the outermost end_undo_group commits to _undoinfo.
        """
        group = self._undo_group
        self._undo_group = self._undo_stack.pop()
        if not group:
            return
        if self._undo_group is not None:
            # Still inside a parent group: merge entries upward.
            self._undo_group.extend(group)
            return
        # Outermost group closed: commit to _undoinfo.
        entry = group[0] if len(group) == 1 else group
        # Insert directly, bypassing join_undo (groups must not be merged).
        self._undoinfo.insert(0, entry)
        self._redoinfo = []
        self.notify_views('undo_changed')

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
    
    def transform(self, fun):
        # Apply a tranforming function to the texeltree. Can change
        # index.
        texel = self.model.texel
        new = fun(texel)
        info = self._set_texel(new)
        self.add_undo(info)

    def _set_texel(self, new):
        old = self.model.texel
        self.model.texel = new
        self.index = min(len(self.model), self.index)        
        self.rebuild()
        return self._set_texel, old

    def get_zoom(self):
        return self._zoom

    def set_zoom(self, zoom):
        self._zoom = zoom

    def get_maxw(self):
        return self._maxw

    def set_maxw(self, maxw):
        if maxw == self._maxw:
            return
        self._maxw = maxw
        self.builder.set_maxw(maxw)
        self.Refresh()
        self.notify_views('maxw_changed')

    def indent_rows(self, firstrow, lastrow, n=4):
        model = self.model
        has_selection = self.has_selection()
        if has_selection:
            s1, s2 = self.selection
        else:
            s1 = s2 = 0
        index = self.index
        for line in range(lastrow, firstrow-1, -1): # indent
            i = model.linestart(line)
            model.insert_text(i, ' '*n)
            if index >= i:
                index += n
            if s1 >= i:
                s1 += n
            if s2 >= i:
                s2 += n
        self.index = index
        if has_selection:
            self.selection = (s1, s2)            
        info = self._dedent_rows, firstrow, lastrow, n
        self.add_undo(info)

    def _dedent_rows(self, firstrow, lastrow, n):
        has_selection = self.has_selection()
        if has_selection:
            s1, s2 = self.selection
        else:
            s1 = s2 = 0
        index = self.index
        memo = []
        model = self.model
        for line in reversed(list(range(firstrow, lastrow+1))):
            i = model.linestart(line)
            for j in range(i, i+n+1):
                if j > len(model): break
                if model.get_text(j, j+1) != ' ': break
            memo.append(model.remove(i, j))
            if index > i:
                index = i+max(0, index-j)
            if s1 > i:
                s1 = i+max(0, s1-j)
            if s2 > i:
                s2 = i+max(0, s2-j)
        self.index = index
        if has_selection:
            self.selection = (s1, s2)
            
        assert len(memo) == lastrow-firstrow+1
        return self._undo_dedent, firstrow, memo, n
        
    def dedent_rows(self, firstrow, lastrow, n=4):
        info = self._dedent_rows(firstrow, lastrow, n)
        self.add_undo(info)

    def _undo_dedent(self, firstrow, memo, n):
        model = self.model
        lastrow = firstrow+len(memo)-1
        memo = list(memo)
        for line in reversed(list(range(firstrow, lastrow+1))):
            i = model.linestart(line)
            model.insert(i, memo[0])
            memo = memo[1:]
        return self._dedent_rows, firstrow, lastrow, n

    def compute_index(self, x, y):
        if y >= self.layout.height:
            return len(self.model)-1
        if y < 0:
            return 0
        return self.layout.get_index(x, y)

    _current_style = None

    def get_current_style(self):
        if self._current_style is None:
            index = self.index
            if index == 0:
                self._current_style = dict(self.model.get_style(index))
            else:
                self._current_style = dict(self.model.get_style(index - 1))
        return self._current_style

    def set_current_style(self, **properties):
        style = self.get_current_style()
        style.update(properties)
        self.notify_views('current_style_changed')

    def clear_current_style(self, *keys):
        style = self.get_current_style()
        for key in keys:
            style.pop(key, None)
        self.notify_views('current_style_changed')

    def handle_action(self, action, shift=False):
        #print("action = ", action, shift)
        model = self.model
        index = self.index
        layout = self.layout
        style = self.get_current_style()
        parstyle = model.get_parstyle(index)
        row, col = self.current_position()
        rect = layout.get_rect(index, 0, 0)
        x = rect.x1
        y = rect.y1
        if self.has_selection():
            s1, s2 = sorted(self.selection)
            e1, e2 = self.model.expand_range(s1, s2)
        else:
            s1 = s2 = e1 = e2 = index

        def del_selection():
            if self.has_selection():
                self.remove(e1, e2)

        if action == 'dump_info':
            dump_range(model.texel, e1, e2)
            row, col = model.index2position(index)
            print("index=", index)
            print("row=", row)
            print("col=", col)

        elif action == 'dump_boxes':
            layout.dump_boxes(0, 0, 0)
        elif action == 'indent':
            row1 = model.index2position(s1)[0]
            row2 = model.index2position(s2)[0]
            self.indent_rows(row1, row2)
        elif action == 'dedent':
            row1 = model.index2position(s1)[0]
            row2 = model.index2position(s2)[0]
            self.dedent_rows(row1, row2)            
        elif action == 'move_word_end':
            i = index
            n = len(model)
            try:
                while not model.get_text(i, i+1).isalnum():
                    i = i+1
                while model.get_text(i, i+1).isalnum():
                    i = i+1
            except IndexError:
                i = n
            self.set_index(i, shift)
        elif action == 'move_right':
            self.set_index(index+1, shift)
        elif action == 'move_word_begin':
            i = index
            try:
                while not model.get_text(i-1, i).isalnum():
                    i = i-1
                while model.get_text(i-1, i).isalnum():
                    i = i-1
            except IndexError:
                i = 0
            self.set_index(i, shift)
        elif action == 'move_left':
            self.set_index(index-1, shift)
        elif action == 'move_paragraph_end':
            i = row
            try:
                while model.linelength(i) == 1:
                    i += 1
                while model.linelength(i) > 1:
                    i += 1
                self.move_cursor_to(i, 0, shift)
            except IndexError:
                self.set_index(len(model), shift)                    
        elif action == 'move_down':
            self.move_cursor_to(row+1, col, shift)
        elif action == 'move_paragraph_begin':
            i = row-1
            while i >= 0 and model.linelength(i) == 1:
                i -= 1
            while i >= 0 and model.linelength(i) > 1:
                i -= 1
            self.move_cursor_to(i+1, 0, shift)
        elif action == 'move_up':
            self.move_cursor_to(row-1, col, shift)
        elif action == 'move_line_start':
            self.set_index(model.linestart(row), shift)
        elif action == 'move_line_end':
            self.set_index(model.linestart(row)+model.linelength(row)-1, shift)
        elif action == 'move_page_down':
            _, height = self.GetClientSize()
            i = self.compute_index(x, y + height / self.zoom)
            self.set_index(i, shift)
        elif action == 'move_page_up':
            _, height = self.GetClientSize()
            i = self.compute_index(x, y - height / self.zoom)
            self.set_index(i, shift)
        elif action == 'move_document_start':
            self.set_index(0, shift)
        elif action == 'move_document_end':
            self.set_index(len(model), shift)
        elif action == 'select_all':
            self.selection = (0, len(model))
        elif action == 'insert_newline':
           tmp = self._TextModel('\n', **style)
           tmp.set_parstyle(0, parstyle)
           indent = model.get_indent(index)
           tmp.set_indent(0, indent)
           self.insert(index, tmp)            
        elif action == 'insert_newline_indented':
            i = model.linestart(row)
            s = model.get_text(i, index)
            l = s[:len(s)-len(s.lstrip())]
            tmp = self._TextModel('\n'+l, **style)
            tmp.set_parstyle(0, parstyle)
            self.insert(index, tmp)            
        elif action == 'backspace':
            if self.has_selection():
                j1, j2 = self.model.expand_range(s1-1, s2)
                if j2 != e2:
                    self.remove(e1, e2)
                else:
                    self.remove(j1, j2)
            else:
                i = self.index
                if i>0:
                    j1, j2 = self.model.expand_range(i-1, i)
                    self.remove(j1, j2)
        elif action == 'copy':
            self.copy()
        elif action == 'paste':
            self.paste()
        elif action == 'cut':
            self.cut()
        elif action == 'delete':
            if self.has_selection():
                del_selection()
            else:
                i = self.index
                if i < len(self.model):
                    j1, j2 = self.model.expand_range(i, i+1)
                    self.remove(j1, j2)
        elif action == 'undo':
            self.undo()
        elif action == 'redo':
            self.redo()
        elif action == 'del_line_end':
            i = model.linestart(row)+model.linelength(row)-1
            if i == index:
                i += 1
            i = min(i, right_limit(model.texel, 0, index))
            j1, j2 = self.model.expand_range(index, i)
            self.to_clipboard(model[j1:j2])
            self.remove(j1, j2)
        elif action == 'del_word_left':
            # find the beginning of the word
            i = index
            try:
                while not model.get_text(i-1, i).isalnum():
                    i = i-1
                while model.get_text(i-1, i).isalnum():
                    i = i-1
            except IndexError:
                i = 0
            i = max(i, left_limit(model.texel, 0, index))                
            j1, j2 = self.model.expand_range(i, index)
            self.remove(j1, j2)
        self.Refresh()

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
        raise NotImplemented()

    def check(self):
        from ..textmodel.treebase import is_root_efficient
        assert is_root_efficient(self.layout)

    def rebuild_range(self, i1, i2, delta):
        self.builder.rebuild_range(i1, i2, delta)

    ### Signals issued by model
    def properties_changed(self, model, i1, i2):
        self.rebuild_range(i1, i2, 0)
        self.refresh()

    def inserted(self, model, i, n):
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

    def get_index(self):
        return self._index

    def current_position(self):
        # Returns the cursorposition as tuple (row, col)
        model = self.model
        i = self.index
        if model is None or i == 0:
            return 0, 0
        return model.index2position(i)

    def move_cursor_to(self, row, col, extend=False, update=True):
        # Moves cursor to (row, col). If this position is non existent
        # the next possible value is selected.

        # extend: extend selection
        # update: update selection 

        model = self.model
        row = max(0, min(row, model.nlines()-1))
        col = max(0, min(col, model.linelength(row)-1))
        self.set_index(model.position2index(row, col), extend, update)

    def get_selection(self):
        return self._selection

    def set_selection(self, selection):
        old = self._selection
        if selection == old:
            return
        if old is not None:
            i1, i2 = old
        self._selection = selection
        self.Refresh()
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
        return [(s1, s2)]

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
        
        
    
