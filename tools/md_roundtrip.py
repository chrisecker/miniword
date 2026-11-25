"""Load Markdown files and save them again: what changes?

    python tools/md_roundtrip.py [FILE ...]   (default: test/md_corpus/*.md)

Prints, per file, the changed lines (unified diff) and whether a second
load and save changes the result again (not stable)."""

import difflib
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from miniword.io import mdfilter


def roundtrip(path):
    """(source, saved, saved again) of the file at path."""
    with open(path, encoding='utf-8-sig') as f:
        source = f.read()
    doc = mdfilter._load(path)
    mdfilter._folder = os.path.dirname(os.path.abspath(path))  # as _save
    try:
        saved = mdfilter._doc_to_md(doc)
    finally:
        mdfilter._folder = ''
    return source, saved, mdfilter._doc_to_md(mdfilter._load_mistune(saved))


def main(paths):
    folder = os.path.join(os.path.dirname(__file__), '..', 'test', 'md_corpus')
    paths = paths or sorted(glob.glob(os.path.join(folder, '*.md')))
    for path in paths:
        source, saved, again = roundtrip(path)
        diff = list(difflib.unified_diff(
            source.splitlines(), saved.splitlines(), 'file', 'saved',
            lineterm='', n=0))
        changed = sum(1 for line in diff[2:] if line[0] in '+-')
        state = 'unchanged' if not diff else '%d lines changed' % changed
        if again != saved:
            state += ', NOT STABLE'
        print('=== %s: %s' % (os.path.basename(path), state))
        for line in diff[2:]:
            print('  ' + line)


if __name__ == '__main__':
    main(sys.argv[1:])
