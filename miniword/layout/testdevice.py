# -*- coding: utf-8 -*-

class TestDevice:
    # Device is a interface layer to capsule platform dependent
    # graphics methods.

    buffering = False

    def create_painter(self, dc, origin, zoom=1.0):
        return dc

    def get_scale(self, dpi, zoom):
        return zoom

    def clear_caches(self):
        pass
    
    def reset_blink(self):
        pass
    
    def set_style(self, style, dc):
        pass
    
    def measure(self, text, style):
        # every char 1 wide, a soft hyphen 0
        return len(text.replace('\u00ad', '')), 1, 0

    def prefix_widths(self, text, style):
        """Widths of text[:i] for i = 0..len(text), each prefix measured
        alone (the reference for faster devices)."""
        return [self.measure(text[:i], style)[0]
                for i in range(len(text) + 1)]

    def measure_parts(self, text, style):
        parts, n = [], 0
        for c in text:
            n += c != '\u00ad'
            parts.append(n)
        return tuple(parts)

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

    def push_clip(self, x, y, w, h, dc):
        pass

    def pop_clip(self, dc):
        pass

    def draw_blinkingrect(self, x, y, w, h, dc):
        pass


TESTDEVICE = TestDevice()
