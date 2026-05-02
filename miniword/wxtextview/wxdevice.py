# -*- coding: utf-8 -*-

# WxDevice provides a lightweight abstraction layer that keeps device
# and application specific code isolated from the rest of the
# codebase. All pixel coordinates are based on an assumed 96 DPI.


import wx
import time
from .cache import LRUCache


defaultstyle = dict(
    fontsize=10, bgcolor='white', textcolor='black', 
    underline=False, facename='', italic=False, bold=False)


def filled(style, defaultstyle=defaultstyle):
    # fill empty properties with default values
    new = defaultstyle.copy()
    new.update(style)
    return new


def get_font(style):
    weight = {False : wx.FONTWEIGHT_NORMAL,
              True : wx.FONTWEIGHT_BOLD}[style.get('bold', False)]
    slant = {False : wx.FONTSTYLE_NORMAL,
              True : wx.FONTSTYLE_ITALIC}[style.get('italic', False)]

    family = dict(
        roman = wx.FONTFAMILY_ROMAN,
        modern = wx.FONTFAMILY_MODERN, 
        swiss = wx.FONTFAMILY_SWISS,        
    )[style.get('family', 'modern')]
    return wx.Font(
        style['fontsize'], family, slant, weight,
        style['underline'], style['facename'])


class WxDevice:
    """
    Device for rendering with wx.GraphicsContext in PT coordinates.
    Works with gc.Scale() for zoom - all coordinates are in PT.
    """
    zoom = 1.0
    buffering = True

    def get_scale(self, dpi):
        return self.zoom
    def __init__(self):
        self._cache = LRUCache(1000)
        # Temporary GC for measuring
        self._temp_bmp = wx.Bitmap(1, 1)
        self._temp_dc = wx.MemoryDC(self._temp_bmp)
        self._temp_gc = wx.GraphicsContext.Create(self._temp_dc)
        self.reset_blink()

    def clear_caches(self):
        self._cache.clear()
        
    def create_painter(self, dc):
        gc = wx.GraphicsContext.Create(dc)
        gc.Scale(self.zoom, self.zoom)
        return gc

    def reset_blink(self):
        self._blink_reference_time = time.time()        

    def set_style(self, style, gc):
        if hasattr(gc, 'last_style') and  style is gc.last_style:
            return
        gc.last_style = style

        _style = filled(style)
        wx_font = get_font(_style)
        gc_font = gc.CreateFont(wx_font, wx.Colour(_style['textcolor']))
        gc.SetFont(gc_font)
        #gc.SetTextBackground(wx.Colour(_style['bgcolor']))
        
    def measure(self, text, style):
        """
        Measure text width/height, descent, external_leading  in PT as float.
        """
        key = (text, tuple(sorted(style.items())))
        try:
            return self._cache.get(key)
        except KeyError:
            pass
            
        style_filled = filled(style)
        
        wx_font = get_font(style_filled)
        gc_font = self._temp_gc.CreateFont(wx_font, wx.BLACK)
        self._temp_gc.SetFont(gc_font)
        
        w, htot, depth, external_leading = self._temp_gc. \
            GetFullTextExtent(text)

        result = (w, htot-depth, depth)
        self._cache.set(key, result)
        return result
    
    def measure_parts(self, text, style):
        """
        Measure partial text extents in PT.
        Returns list of cumulative widths for each character.
        """
        style_filled = filled(style)
        wx_font = get_font(style_filled)
        gc_font = self._temp_gc.CreateFont(wx_font, wx.BLACK)
        self._temp_gc.SetFont(gc_font)        
        return self._temp_gc.GetPartialTextExtents(text)
    
    def intersects(self, gc, rect):
        """
        Check if rect (in PT) intersects with current clipping region.
        rect: dict-like with items() returning (x1, y1, x2, y2) in PT
        """
        x1, y1, x2, y2 = rect.items()
        
        clip_x, clip_y, clip_w, clip_h = gc.GetClipBox()
        clip_x2 = clip_x + clip_w
        clip_y2 = clip_y + clip_h
        
        return not (x2 < clip_x or x1 > clip_x2 or 
                    y2 < clip_y or y1 > clip_y2)
    
    def draw_text(self, text, x, y, gc):
        """
        Draw text at position (x, y) in PT coordinates.
        """
        gc.DrawText(text, x, y)
    
    def draw_rect(self, x, y, w, h, gc):
        """
        Draw rectangle outline in PT coordinates.
        """
        pen = gc.CreatePen(wx.GraphicsPenInfo(wx.BLACK).Width(1))
        gc.SetPen(pen)
        gc.SetBrush(wx.TRANSPARENT_BRUSH)        
        gc.DrawRectangle(x, y, w, h)
    
    def draw_blinkingrect(self, x, y, w, h, gc):
        """
        Draw blinking cursor rectangle in PT coordinates.
        """
        if not int((time.time()-self._blink_reference_time) * 2) % 2:
            color = wx.BLACK
        else:
            color = wx.LIGHT_GREY
            
        brush = gc.CreateBrush(wx.Brush(color))
        gc.SetBrush(brush)
        gc.SetPen(wx.TRANSPARENT_PEN)        
        gc.DrawRectangle(x, y, w, h)
    
    def invert_rect(self, x, y, w, h, gc):
        """
        Draw semi-transparent selection rectangle in PT coordinates.
        """
        color = wx.Colour(83, 97, 220, 50)
        brush = gc.CreateBrush(wx.Brush(color))
        gc.SetBrush(brush)
        gc.SetPen(wx.TRANSPARENT_PEN)        
        gc.DrawRectangle(x, y, w, h)
    
    def fill_rect(self, x, y, w, h, color, gc):
        """
        Fill rectangle with color in PT coordinates.
        """
        brush = gc.CreateBrush(wx.Brush(wx.Colour(color)))
        gc.SetBrush(brush)
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.DrawRectangle(x, y, w, h)

    def draw_line(self, x1, y1, x2, y2, width, gc):
        """
        Draw a line from (x1,y1) to (x2,y2) with given width in PT coordinates.
        """
        pen = gc.CreatePen(wx.GraphicsPenInfo(wx.BLACK).Width(width))
        gc.SetPen(pen)
        gc.StrokeLine(x1, y1, x2, y2)


        
