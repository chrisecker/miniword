# -*- coding: utf-8 -*-

"""
Writes miniword.desktop and miniword.xml (file type .txl) for the Linux
packages into the given folder, from miniword/desktop.py:

    PYTHONPATH=. python packaging/linux/make_desktop_files.py build/linux
"""

import os
import sys

from miniword import desktop


def main(folder):
    os.makedirs(folder, exist_ok=True)
    # Markdown only under "Open with", not as default application
    entry = desktop.ENTRY.format(
        exec='miniword', mime_types=desktop.MIME_TYPE + ';text/markdown;')
    with open(os.path.join(folder, 'miniword.desktop'), 'w',
              encoding='utf-8') as f:
        f.write(entry)
    with open(os.path.join(folder, 'miniword.xml'), 'w',
              encoding='utf-8') as f:
        f.write(desktop.MIME_XML)


if __name__ == '__main__':
    main(sys.argv[1])
