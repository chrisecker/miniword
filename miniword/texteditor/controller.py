from .actions import create_ctx, default_handler
import types


class ElementController:
    """Base class for element Controller.

      auto_installable  = True   Installed automatically by update_editor()
                                 when match() returns non-None after a cursor move.
      click_installable = True   Installed on mouse click via try_install_click_editor().

    Lifecycle:
      match(view, path) → editor or None   Called to check whether this editor
                                           applies at the current cursor position.
                                           Returns a fully initialised instance
                                           (i1, i2, depth, texel set) or None.
      install()                            Called once after match() to let the
                                           editor set up any derived state.

    Editors are removed when:
      - the cursor moves and match() returns None
      - the model signals "inserted" or "removed"
      - editor.update_controller() re-evaluates match() and installs
        a different controller (e.g. NullController)
    """
    auto_installable  = False
    click_installable = False
    is_null = False

    def __init__(self, editor, texel, i1, i2, depth):
        self.editor = editor
        self.texel = texel
        self.i1 = i1
        self.i2 = i2
        self.depth = depth

    @classmethod
    def match(cls, editor, path):
        return None

    # Events — always return False (not consumed)
    def on_leftdown(self, event): return False
    def on_motion(self, event):   return False
    def on_leftup(self, event):   return False
    def on_key(self, key, event): return False

    # Queries — None means "use DocumentView default"
    def selected(self, i1, i2):
        return None
    
    def adjust_viewport(self):
        return None

    # Draw cursor + selection
    def draw(self, painter):
        canvas = self.editor.canvas
        if canvas: 
            canvas.draw_cursor(painter)
            canvas.draw_selection(painter)

    def handle_action(self, action, shift):
        ctx = create_ctx(self.editor)
        # default: redirect to editor
        return self.editor.actionhandler(action, shift, ctx)

    # Clipboard — delegate to editor
    def copy(self):  self.editor.copy()
    def cut(self):   self.editor.cut()
    def paste(self): self.editor.paste()
    

class NullController(ElementController):
    is_null = True
    @classmethod
    def match(cls, editor, path):
        # DefaultController always matches!
        for depth, (i1, i2, texel) in enumerate(path):
            return cls(editor, texel, i1, i2, depth)



