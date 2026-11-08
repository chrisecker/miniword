"""
Smoke test of an installed Linux package, run by the job "linux" in a
container: MiniWord uses the included uharfbuzz and mistune, reads
Markdown and starts.
"""

import subprocess
import sys

sys.path.insert(0, '/usr/share/miniword')  # as packaging/linux/miniword
import cairocffi, mistune, uharfbuzz, wx  # noqa: E401

for module in (mistune, uharfbuzz):
    assert module.__file__.startswith('/usr/share/miniword/'), module
from miniword.plugins import mdfilter
doc = mdfilter._load_mistune('# Test\n\nSome **bold** text.\n')
assert doc.textmodel.get_text().startswith('Test\n')
print(subprocess.run(['miniword', '--version'], check=True,
                     capture_output=True, text=True).stdout.strip(),
      'wx', wx.version(), 'mistune', mistune.__version__,
      'uharfbuzz', uharfbuzz.__version__)
