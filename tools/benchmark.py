"""Benchmarks of typical steps, to notice when MiniWord gets slower.

    python tools/benchmark.py [NAME ...] [-f FILE] [--set KEY=VALUE ...]
                              [--page N] [--runs N] [--profile]
                              [--log CSV | --no-log]

e.g. python tools/benchmark.py redraw key --profile

FILE (-f) defaults to test/einstein.txl. The benchmarks (default all):

  open      loading the file
  typeset   the layout of the whole document with cold caches (as after
            opening), without window
  redraw    painting the window (TextCanvas.draw into a bitmap of the
            window's size: the code of on_paint, without waiting for
            the window system)
  zoomout   redraw at zoom 0.3: many pages at once
  key       typing a character: editing, the layout of the visible
            pages and the redraw
  enter     splitting a paragraph, with layout and redraw
  paste     pasting three paragraphs, with layout and redraw
  restyle   changing the font size of the normal style (all pages are
            set anew; measured: up to the redraw of the visible ones)
  spell     spell checking the visible pages (the word cache filled
            by the first run, as when typing)
  squiggles redraw with the spelling errors marked
  save      writing the TXL file
  pdf       exporting a PDF (with its own layout)

The window shows page N (--page, default 1) with the cursor in its
middle; editing benchmarks work there and are undone after each run.
--set changes document settings as on the command line (e.g.
hyphenation=yes, language=de).

Each run appends one line per benchmark to a CSV file (--log, default
benchmarks.csv in the repository) and prints a summary that compares
the medians with the last run on this computer with the same file and
settings: deviations beyond 20 % are marked. --profile profiles the
measured steps (cProfile, by cumulative time).
"""

import argparse
import cProfile
import itertools
import csv
import datetime
import os
import platform
import pstats
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import wx

THRESHOLD = 0.2  # deviations marked in the summary
FIELDS = ['date', 'commit', 'host', 'file', 'settings', 'benchmark',
          'median', 'min', 'runs']
BENCHMARKS = {}  # name -> function(context): (step, after_step, runs)


def benchmark(name):
    """Register the decorated function as benchmark name."""
    def register(fn):
        BENCHMARKS[name] = fn
        return fn
    return register


class Context:
    """The document (with the settings applied), and a main window for
    it when a benchmark needs one (created on first use)."""
    frame = None

    def __init__(self, path, settings, page):
        from miniword.io.importexport import open_file
        self.path, self.page = path, page
        self.document = open_file(path)
        for key, value in settings:
            self.document.set_setting(key, value)

    def window(self):
        """The main window, showing page N with the cursor in its
        middle."""
        if self.frame is None:
            from miniword.ui.mainwindow import MainFrame
            frame = self.frame = MainFrame(self.document)
            frame.SetSize(1000, 900)
            frame.Show()
            yield_events()  # the window gets its size
            canvas, editor = frame.canvas, frame.editor
            canvas.builder.assure_finished()
            pages = list(canvas.builder.layout.iter_childs())
            j1, j2, page = pages[min(self.page, len(pages)) - 1]
            i = self.document.textmodel.get_text().find(' ', (j1 + j2) // 2)
            editor.index = i if 0 <= i < j2 else (j1 + j2) // 2
            canvas.queued_update_scroll()  # the virtual size, else no scroll
            canvas.adjust_viewport()
            canvas.Refresh()
            yield_events()  # shown on the screen too
        return self.frame

    def reset(self):
        """After a benchmark: the layout finished, no squiggles left."""
        if self.frame is not None:
            self.frame.canvas.builder.assure_finished()
            self.frame.canvas.squiggles = {}

    def close(self):
        if self.frame is not None:
            self.frame.release()
            self.frame.Destroy()


def yield_events():
    for _ in range(5):
        wx.GetApp().Yield()


def before_key(editor):
    """What a key event does first: editor.controller sets the layout up
    to the cursor."""
    editor.controller


def redraw_window(canvas):
    """Paint canvas as on_paint does, into a bitmap of its size."""
    w, h = canvas.GetClientSize()
    bitmap = wx.Bitmap(w, h)
    dc = wx.MemoryDC(bitmap)
    spx, spy = canvas.CalcScrolledPosition((0, 0))
    ox, oy = canvas.content_offset()
    painter = canvas.builder.get_device().create_painter(
        dc, origin=(spx + ox, spy + oy), zoom=canvas.zoom)
    canvas.draw(painter)
    del painter
    dc.SelectObject(wx.NullBitmap)


def nothing():
    pass


@benchmark('open')
def load_file(context):
    from miniword.io.importexport import open_file
    return (lambda: open_file(context.path)), nothing, 3


@benchmark('typeset')
def typeset_document(context):
    from miniword.layout.pagebuilder import PageBuilder
    from miniword.layout.rowfactory import Factory
    from miniword.layout.cairodevice import CairoDevice
    document = context.document

    def step():
        cache = getattr(document.basestyles, 'cache', None)  # of mk_style
        if cache is not None:
            cache.clear()
        builder = PageBuilder(document.textmodel, Factory(
            document.basestyles, device=CairoDevice()))
        builder.settings = document.settings
        builder.rebuild()
        builder.assure_finished()
    return step, nothing, 3


@benchmark('redraw')
def redraw_page(context):
    canvas = context.window().canvas
    redraw_window(canvas)  # the first time: font caches
    return (lambda: redraw_window(canvas)), nothing, 20


@benchmark('zoomout')
def redraw_zoomed_out(context):
    canvas = context.window().canvas
    zoom = canvas.zoom

    def step():
        canvas.set_zoom(0.3)
        redraw_window(canvas)

    def after_step():
        canvas.set_zoom(zoom)
    return step, after_step, 10


def editing_benchmark(context, edit, runs=20):
    """step: edit(editor) and the redraw; after it: undo. The rest of
    the layout is left to the end of the benchmark: a new line moves all
    pages behind it, which are set anew (in the program in the
    background)."""
    frame = context.window()
    canvas, editor = frame.canvas, frame.editor

    def step():
        before_key(editor)
        edit(editor)
        redraw_window(canvas)

    def after_step():
        before_key(editor)
        editor.undo()
    return step, after_step, runs


@benchmark('key')
def type_key(context):
    def edit(editor):
        with editor.atomic():
            editor.remove()
            editor.insert_text('x')
    return editing_benchmark(context, edit)


@benchmark('enter')
def split_paragraph(context):
    return editing_benchmark(context, lambda editor: editor.insert_newline())


@benchmark('paste')
def paste_paragraphs(context):
    model = context.document.textmodel
    end = 0
    for _ in range(3):  # the first three paragraphs
        if end < len(model):
            end = model.lineend(end) + 1
    pasted = model.copy(0, min(end, len(model)))
    return editing_benchmark(context,
                             lambda editor: editor.insert_model(pasted), 10)


@benchmark('restyle')
def change_basestyle(context):
    from miniword.textmodel.styles import Style
    canvas = context.window().canvas
    sheet = context.document.basestyles
    key = sheet.normal_key()
    style = sheet.get(key)
    size = style.get('font_size', 12)
    sizes = itertools.cycle([size + 1, size])  # back and forth

    def step():
        sheet.set(key, Style(**dict(style, font_size=next(sizes))))
        redraw_window(canvas)
    return step, canvas.builder.assure_finished, 6


def check_visible(context):
    """Spell check the visible pages: (checker, those pages)."""
    from miniword.core.document import settings_default
    checker = context.window().spelling
    language = context.document.settings.get(
        'language', settings_default['language'])
    pages = checker.visible_pages()
    for j1, j2, page in pages:
        page.spelling = None
    checker.check_pages(context.document.textmodel, language, pages)
    return checker, pages


@benchmark('spell')
def check_spelling(context):
    return (lambda: check_visible(context)), nothing, 20


@benchmark('squiggles')
def redraw_squiggles(context):
    checker, pages = check_visible(context)
    checker.show(checker.squiggles(pages))
    return (lambda: redraw_window(context.frame.canvas)), nothing, 20


@benchmark('save')
def save_txl(context):
    path = os.path.join(tempfile.mkdtemp(), 'benchmark.txl')
    return (lambda: context.document.save(path)), nothing, 5


@benchmark('pdf')
def export_pdf(context):
    from miniword.io.pdf import export_pdf
    path = os.path.join(tempfile.mkdtemp(), 'benchmark.pdf')
    return (lambda: export_pdf(context.document, path)), nothing, 3


def ms(fn):
    t0 = time.perf_counter()
    fn()
    return (time.perf_counter() - t0) * 1000


def measure(context, name, runs=None, profiler=None):
    """The times [ms] of the runs of benchmark name."""
    step, after_step, default_runs = BENCHMARKS[name](context)
    times = []
    for _ in range(runs or default_runs):
        if profiler is not None:
            profiler.enable()
        times.append(ms(step))
        if profiler is not None:
            profiler.disable()
        after_step()
    context.reset()
    return times


def commit():
    """The current commit, with '+' if there are uncommitted changes."""
    def git(*args):
        return subprocess.run(['git', '-C', ROOT] + list(args),
                              capture_output=True, text=True).stdout.strip()
    return git('rev-parse', '--short', 'HEAD') \
        + ('+' if git('status', '--porcelain', '-uno') else '')


def previous_runs(path, key):
    """{benchmark: row} of the last logged runs with key (host, file,
    settings)."""
    found = {}
    if path and os.path.exists(path):
        with open(path, newline='') as f:
            for row in csv.DictReader(f):
                if (row['host'], row['file'], row['settings']) == key:
                    found[row['benchmark']] = row
    return found


def summary(results, previous):
    """The lines comparing results {name: times} with previous."""
    lines = ['%-8s %9s %9s %9s' % ('', 'median', 'min', 'last')]
    for name, times in results.items():
        median = statistics.median(times)
        line = '%-8s %9.1f %9.1f' % (name, median, min(times))
        row = previous.get(name)
        if row:
            last = float(row['median'])
            change = median / last - 1 if last else 0
            line += ' %9.1f %+5.0f%%' % (last, change * 100)
            if change > THRESHOLD:
                line += '  slower'
            elif change < -THRESHOLD:
                line += '  faster'
        lines.append(line)
    return lines


def write_log(path, key, version, results):
    new = not os.path.exists(path)
    date = datetime.datetime.now().isoformat(timespec='seconds')
    host, file, settings = key
    with open(path, 'a', newline='') as f:
        writer = csv.writer(f)
        if new:
            writer.writerow(FIELDS)
        for name, times in results.items():
            writer.writerow([date, version, host, file, settings, name,
                             '%.1f' % statistics.median(times),
                             '%.1f' % min(times), len(times)])


def main():
    from miniword.__main__ import parse_setting
    parser = argparse.ArgumentParser(
        description=__doc__.split('\n')[0],
        epilog='benchmarks: ' + ', '.join(BENCHMARKS))
    parser.add_argument('benchmark', nargs='*', metavar='NAME',
                        help='the benchmarks to run (default all)')
    parser.add_argument('-f', '--file',
                        default=os.path.join(ROOT, 'test', 'einstein.txl'))
    parser.add_argument('--set', metavar='KEY=VALUE', action='append',
                        default=[], type=parse_setting,
                        help='a document setting, repeatable')
    parser.add_argument('--page', type=int, default=1,
                        help='the page of the editing benchmarks')
    parser.add_argument('--runs', type=int,
                        help='runs of each benchmark (default 3 to 20)')
    parser.add_argument('--profile', action='store_true',
                        help='profile the measured steps')
    parser.add_argument('--log', metavar='CSV',
                        default=os.path.join(ROOT, 'benchmarks.csv'))
    parser.add_argument('--no-log', action='store_true',
                        help='neither compare nor append')
    args = parser.parse_args()
    unknown = [name for name in args.benchmark if name not in BENCHMARKS]
    if unknown:
        parser.error('unknown benchmark %s (of: %s)'
                     % (', '.join(unknown), ', '.join(BENCHMARKS)))
    names = args.benchmark or list(BENCHMARKS)
    settings = [pair for pairs in args.set for pair in pairs]
    log = None if args.no_log else args.log

    app = wx.App(False)
    from miniword.io.importexport import load_formats
    from miniword.ui.mainwindow import load_plugins
    load_formats()
    load_plugins()
    context = Context(args.file, settings, args.page)
    results = {}
    for name in names:
        profiler = cProfile.Profile() if args.profile else None
        results[name] = measure(context, name, args.runs, profiler)
        if profiler is not None:
            print('--- %s' % name)
            pstats.Stats(profiler).strip_dirs().sort_stats(
                'cumulative').print_stats(25)
    pages = len(context.frame.canvas.builder.layout.childs) \
        if context.frame else None
    context.close()

    if args.page != 1:
        settings.append(('page', args.page))  # compared as a setting
    key = (platform.node(), os.path.basename(args.file),
           ' '.join('%s=%s' % pair for pair in settings))
    version = commit()
    previous = previous_runs(log, key)
    last = max((row['date'] for row in previous.values()), default=None)
    print('%s%s, commit %s%s%s' % (
        key[1], ', %d pages' % pages if pages else '', version,
        ', ' + key[2] if key[2] else '',
        ', last run %s' % last if last else ''))
    print('\n'.join(summary(results, previous)))
    if log:
        write_log(log, key, version, results)
    del app


if __name__ == '__main__':
    main()
