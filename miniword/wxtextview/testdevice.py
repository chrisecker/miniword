# -*- coding: latin-1 -*-

class TestDevice:
    # Device is a interface layer to capsule platform dependent
    # graphics methods.

    buffering = False
    zoom = 1.0

    def get_scale(self, dpi):
        return self.zoom

    def clear_caches(self):
        pass
    
    def reset_blink(self):
        pass
    
    def set_style(self, style, dc):
        pass
    
    def measure(self, text, style):
        return len(text), 1, 0 # Dummy for testing

    def measure_parts(self, text, style):
        return tuple(range(1, len(text)+1)) # Dummy for testing

    def intersects(self, dc, rect):
        return True

    def invert_rect(self, x, y, w, h, dc):
        pass

    def draw_text(self, text, x, y, dc):
        pass

    def draw_rect(self, x, y, w, h, dc):
        pass

    def draw_line(self, x1, y1, x2, y2, width, dc):
        pass

    def fill_rect(self, x, y, w, h, color, dc):
        pass

    def draw_blinkingrect(self, x, y, w, h, dc):
        pass

TESTDEVICE = TestDevice()
