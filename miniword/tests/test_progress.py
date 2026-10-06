# -*- coding: utf-8 -*-

"""
Tests for building the pages up to the visible area after a rebuild,
with a progress window if that takes long (ui/mainwindow.build_to):
the windows are disabled, views don't paint or build meanwhile.
IDs PROG-n.

Run with: python runtests.py miniword/tests/test_progress.py
"""

import time

import wx

from .guitest import app


def long_builder(n=300):
    """A PageBuilder for n paragraphs, rebuilt from the start."""
    from ..core.document import Document
    from ..layout.cairodevice import CairoDevice
    from ..layout.pagebuilder import PageBuilder
    from ..layout.rowfactory import Factory
    document = Document()
    document.textmodel.insert_text(0, "Ein Absatz mit etwas Text.\n" * n)
    builder = PageBuilder(document.textmodel,
                          Factory(document.basestyles, device=CairoDevice()))
    builder.settings = document.settings
    builder.rebuild()
    return builder


def test_PROG_1():
    "PROG-1: builds until y is covered, not further; window after delay"
    from ..ui.mainwindow import build_to
    app()
    frame = wx.Frame(None)
    try:
        frame.Show()
        builder = long_builder()
        layout = builder.layout
        assert build_to(builder, 2000, frame, delay=0)  # window shown
        assert layout.height + layout.depth >= 2000
        assert not layout.is_finished
        assert not any(w.IsShown() for w in wx.GetTopLevelWindows()
                       if w is not frame)  # the window is gone
    finally:
        frame.Destroy()


def test_PROG_2():
    "PROG-2: no window if the area is built in time or already covered"
    from ..ui.mainwindow import build_to
    app()
    frame = wx.Frame(None)
    try:
        builder = long_builder()
        assert not build_to(builder, 100, frame)
        assert not build_to(builder, 100, frame, delay=0)  # covered
    finally:
        frame.Destroy()


def shown(canvas):
    """Wait until canvas has painted once (the window is mapped)."""
    painted = []
    canvas.Bind(wx.EVT_PAINT, lambda e: (painted.append(1), e.Skip()))
    canvas.GetTopLevelParent().Show()
    start = time.time()
    while not painted and time.time() - start < 3:
        wx.Yield()
        time.sleep(0.01)
    canvas.Unbind(wx.EVT_PAINT)
    canvas.Bind(wx.EVT_PAINT, canvas.on_paint)


def test_PROG_3():
    "PROG-3: the canvas doesn't paint, build or scroll while build_to runs"
    from ..texteditor.editor import Editor
    from ..texteditor.textcanvas import TextCanvas
    from ..ui.mainwindow import build_to
    app()
    frame = wx.Frame(None, size=(400, 400))
    try:
        builder = long_builder()
        editor = Editor(builder.model)
        canvas = TextCanvas(frame, builder.model, builder, editor)
        editor.canvas = canvas
        builder.assure_finished()
        shown(canvas)
        canvas.Scroll(0, 10 ** 6)  # far down: painting would build there
        builder.rebuild()  # e.g. a setting changed

        start = canvas.GetViewStart()

        def paint():
            canvas.Refresh()
            canvas.Update()  # paints now, if it paints at all
            canvas.adjust_viewport()  # would scroll to the cursor
        builder.assure_y = lambda y, callback=None: \
            type(builder).assure_y(builder, y, paint)
        build_to(builder, 2000, frame)
        assert not builder.layout.is_finished  # only down to y
        assert canvas.GetViewStart() == start
        assert not builder.busy
    finally:
        frame.Destroy()


def during_build(builder, check):
    """Run check() after every build step of the next build_to."""
    builder.assure_y = lambda y, callback=None: type(builder).assure_y(
        builder, y, lambda: (callback and callback(), check()))


def test_PROG_4():
    "PROG-4: while the window shows, all other windows are disabled"
    from ..ui.mainwindow import build_to
    app()
    frame = wx.Frame(None)
    try:
        frame.Show()
        builder = long_builder()
        seen = []
        during_build(builder, lambda: seen.append(
            (frame.IsEnabled(), [w.IsShown() for w in wx.GetTopLevelWindows()
                                 if w is not frame])))
        build_to(builder, 2000, frame, delay=0)
        assert seen and all(not enabled and any(others)
                            for enabled, others in seen)
        assert frame.IsEnabled()
    finally:
        frame.Destroy()


def test_PROG_5():
    "PROG-5: no background build step while busy"
    from ..layout.pagebuilder import PageBuilder
    app()
    builder = long_builder()
    pages = len(builder.layout.childs)
    PageBuilder.busy = True
    try:
        builder.build_background()
        assert len(builder.layout.childs) == pages
    finally:
        PageBuilder.busy = False
    builder.build_step()
    assert len(builder.layout.childs) > pages


def test_PROG_6():
    "PROG-6: side panels update after the build, not during it"
    from ..layout.pagebuilder import PageBuilder
    from ..ui.sidepanel import SidePanel
    app()
    frame = wx.Frame(None)
    try:
        panel = SidePanel(frame)
        updates = []
        panel.update = lambda: updates.append(1)
        PageBuilder.busy = True
        try:
            panel.on_timer(None)
            assert updates == [] and panel._timer.IsRunning()
        finally:
            PageBuilder.busy = False
        panel.on_timer(None)
        assert updates == [1]
    finally:
        frame.Destroy()


def test_PROG_7():
    "PROG-7: the background build runs from the main loop, not in a Yield"
    app()
    builder = long_builder()
    yields = []
    original = wx.Yield
    wx.Yield = lambda: yields.append(1)
    try:
        builder.build_background()
        start = time.time()
        while not builder.layout.is_finished and time.time() - start < 20:
            original()  # the test's main loop
            time.sleep(0.001)
    finally:
        wx.Yield = original
    assert builder.layout.is_finished
    assert yields == []
