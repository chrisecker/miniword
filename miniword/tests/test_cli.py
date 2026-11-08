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
