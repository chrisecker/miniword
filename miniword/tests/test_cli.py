# -*- coding: utf-8 -*-

"""
Tests for the command line (miniword.__main__.parse_args). IDs CLI-n.

Run with: python runtests.py miniword/tests/test_cli.py
"""

import contextlib
import io

from ..__main__ import parse_args


def run(*argv):
    """(exit code or None, output) of parsing argv."""
    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output), \
                contextlib.redirect_stderr(output):
            parse_args(list(argv))
    except SystemExit as e:
        return e.code, output.getvalue()
    return None, output.getvalue()


def test_CLI_1():
    "CLI-1: a file to open and --debug, both optional"
    args = parse_args([])
    assert args.file is None and not args.debug
    args = parse_args(['brief.txl', '--debug'])
    assert args.file == 'brief.txl' and args.debug


def test_CLI_2():
    "CLI-2: -h and --help describe the options and exit"
    for option in ('-h', '--help'):
        code, output = run(option)
        assert code == 0
        assert 'usage: miniword' in output
        assert 'file' in output and '--debug' in output
        assert '--version' in output


def test_CLI_3():
    "CLI-3: --version; an unknown option is an error, not a file name"
    from .. import __version__
    code, output = run('--version')
    assert code == 0 and __version__ in output
    code, output = run('--unknown')
    assert code == 2 and 'unrecognized arguments' in output


def test_CLI_4():
    "CLI-4: --install-desktop, --uninstall-desktop"
    args = parse_args(['--install-desktop'])
    assert args.install_desktop
    assert not args.uninstall_desktop
    assert parse_args(['--uninstall-desktop']).uninstall_desktop


def test_CLI_5():
    "CLI-5: -o OUTFILE needs a document to read"
    args = parse_args(['brief.md', '-o', 'brief.pdf'])
    assert args.output == 'brief.pdf'
    assert parse_args(['brief.md', '--output', 'b.txl']).output == 'b.txl'
    code, output = run('-o', 'brief.pdf')
    assert code == 2 and '-o needs a document' in output


def test_CLI_6():
    "CLI-6: convert writes by extension; errors give exit code 1"
    import os
    import tempfile
    import wx
    from ..__main__ import convert
    from ..plugins import mdfilter  # registers Markdown
    if wx.App.Get() is None:
        wx.App(False)
    with tempfile.TemporaryDirectory() as folder:
        md = os.path.join(folder, 'a.md')
        with open(md, 'w', encoding='utf-8') as f:
            f.write('# Title\n\nSome **bold** text.\n')
        txl = os.path.join(folder, 'a.txl')
        pdf = os.path.join(folder, 'a.pdf')
        assert convert(md, txl) == 0
        assert convert(txl, pdf) == 0
        with open(pdf, 'rb') as f:
            assert f.read(5) == b'%PDF-'
        with contextlib.redirect_stderr(io.StringIO()) as err:
            assert convert(txl, os.path.join(folder, 'a.xyz')) == 1
            assert convert(os.path.join(folder, 'missing.md'), pdf) == 1
        assert 'no format' in err.getvalue()


def test_CLI_7():
    "CLI-7: --set KEY=VALUE, read by the type of the default"
    from ..core.units import cm, mm
    args = parse_args(['a.md', '-o', 'a.pdf', '--set', 'margin_left=2cm',
                       '--set', 'hyphenation=Yes', '--set', 'paper=a5',
                       '--set', 'header_left=text:Draft: 1',
                       '--set', 'footer_center=title',
                       '--set', 'title=A=B'])
    assert args.set == [[('margin_left', 2 * cm)], [('hyphenation', True)],
                        [('paper', 'A5')],
                        [('header_left', ('text', 'Draft: 1'))],
                        [('footer_center', ('title', ''))],
                        [('title', 'A=B')]]
    args = parse_args(['a.md', '-o', 'a.pdf', '--set', 'paper=170x240mm'])
    (paper, (_, width), (_, height)), = args.set
    assert paper == ('paper', 'custom')
    assert abs(width - 170 * mm) < 1e-9 and abs(height - 240 * mm) < 1e-9
    for setting in ('margin_left', 'colour=red', 'margin_left=2km',
                    'hyphenation=maybe', 'paper=A9', 'footer_left=xyz'):
        code, output = run('a.md', '-o', 'a.pdf', '--set', setting)
        assert code == 2 and '--set' in output, setting


def test_CLI_8():
    "CLI-8: --template and --set need -o"
    assert parse_args(['a.md', '-o', 'a.pdf', '--template', 't.txl'])\
        .template == 't.txl'
    for argv in (['a.md', '--template', 't.txl'],
                 ['a.md', '--set', 'paper=A5']):
        code, output = run(*argv)
        assert code == 2 and 'need -o' in output


def test_CLI_9():
    "CLI-9: convert with a template (settings, styles by role) and --set"
    import os
    import tempfile
    import wx
    from ..__main__ import convert
    from ..core.document import Document
    from ..io.importexport import open_file
    from ..plugins import mdfilter  # registers Markdown
    if wx.App.Get() is None:
        wx.App(False)
    template = Document()
    template.basestyles.set('normal', dict(role='normal', font_size=9))
    template.basestyles.set('Title', dict(role='h1', font_size=30))
    template.basestyles.set('plain', dict(font_size=7))  # no role
    template.settings = dict(paper='Letter', margin_left=99.0, title='T')
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, 't.txl')
        template.save(path)
        md = os.path.join(folder, 'a.md')
        with open(md, 'w', encoding='utf-8') as f:
            f.write('# Title\n\nSome text.\n')
        txl = os.path.join(folder, 'a.txl')
        assert convert(md, txl, path, [('margin_left', 50.0)]) == 0
        doc = open_file(txl)
    styles = doc.basestyles
    assert styles.get('h1')['font_size'] == 30  # name stays
    assert styles.get('body')['font_size'] == 9
    assert not styles.contains('Title') and not styles.contains('plain')
    assert doc.settings == dict(paper='Letter', margin_left=50.0)


def test_CLI_10():
    "CLI-10: a template keeps the document's title and author"
    from ..__main__ import apply_template
    from ..core.document import Document
    doc, template = Document(), Document()
    doc.settings = dict(author='A', paper='A5')
    template.settings = dict(title='T', author='B', paper='Letter')
    apply_template(doc, template)
    assert doc.settings == dict(author='A', paper='Letter')
