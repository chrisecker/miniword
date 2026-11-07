# -*- coding: utf-8 -*-

"""
Writes the desktop entry (miniword.desktop) and the file type of .txl
documents (miniword.xml) for the Linux packages into the folder given
as argument, see packaging/linux/nfpm.yaml. Both come from
miniword/desktop.py, which writes the same for a pip install
(miniword --install-desktop).

    PYTHONPATH=. python packaging/linux/make_desktop_files.py build/linux
"""

import os
import sys

from miniword import desktop


def main(folder):
    os.makedirs(folder, exist_ok=True)
    # a package only offers MiniWord for Markdown ("Open with"); the
    # default application for .md stays the user's choice
    mime_types = [desktop.MIME_TYPE, 'text/markdown']
    entry = desktop.ENTRY.format(exec='miniword',
                                 mime_types=''.join(t + ';'
                                                    for t in mime_types))
    with open(os.path.join(folder, 'miniword.desktop'), 'w',
              encoding='utf-8') as f:
        f.write(entry)
    with open(os.path.join(folder, 'miniword.xml'), 'w',
              encoding='utf-8') as f:
        f.write(desktop.MIME_XML)


if __name__ == '__main__':
    main(sys.argv[1])
