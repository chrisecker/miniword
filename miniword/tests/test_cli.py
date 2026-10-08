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
    "CLI-4: --install-desktop (with --markdown), --uninstall-desktop"
    args = parse_args(['--install-desktop', '--markdown'])
    assert args.install_desktop and args.markdown
    assert not args.uninstall_desktop
    assert parse_args(['--uninstall-desktop']).uninstall_desktop
