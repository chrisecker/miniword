from ..textmodel.modelbase import Model


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


class UndoRedo(Model):
    def __init__(self, *args, **kwargs):
        self._undoinfo = []
        self._redoinfo = []
        self._undo_groups = []
        super().__init__(*args, **kwargs)  

    def undo(self):
        if len(self._undoinfo) > 0:
            #with self.inhibit_layout():
            self.add_redo(undo(self._undoinfo[0]))
            del self._undoinfo[0]

    def redo(self):
        if len(self._redoinfo) > 0:
            #with self.inhibit_layout():
            self.add_undo(undo(self._redoinfo[0]), 0)
            del self._redoinfo[0]
                
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
        
    def clear_undo(self):
        self._undoinfo = []
        self._redoinfo = []
        self.notify_views('undo_changed')

    def undocount(self):
        return len(self._undoinfo)

    def redocount(self):
        return len(self._redoinfo)

    def join_undo(self, info2, info1):
        # Can be overridden. 
        return [info2, info1] # Default: don't join undo
    
