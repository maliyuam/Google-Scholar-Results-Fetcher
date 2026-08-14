"""Make the package importable when the tests are run from a checkout.

Replaces the per-file sys.path hack that used to sit at the top of every test
module. Redundant once the package is pip-installed, but harmless, so `pytest`
works in a bare checkout too.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
