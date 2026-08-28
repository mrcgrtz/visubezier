"""Import setup shared by the tests.

Sublime loads a package's plugins under the package directory's name, so the
plugin uses relative imports (``from .core import ...``). Outside Sublime the
repository is not on the import path under that name, so a synthetic package is
registered here pointing at the repository root.
"""

import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = 'VisuBezier'

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if PACKAGE not in sys.modules:
    package = types.ModuleType(PACKAGE)
    package.__path__ = [ROOT]
    sys.modules[PACKAGE] = package


def load_settings_defaults():
    """Parse the shipped settings file, stripping its line comments."""
    import json
    path = os.path.join(ROOT, 'VisuBezier.sublime-settings')
    with open(path) as handle:
        body = ''.join(
            line for line in handle if not line.strip().startswith('//')
        )
    return json.loads(body)
