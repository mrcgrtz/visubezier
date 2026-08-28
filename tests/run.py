#!/usr/bin/env python3
"""Run the VisuBezier test suite.

    python3 tests/run.py

The suite runs outside Sublime Text: the plugin's Sublime API calls are served
by a stub, and everything below the plugin is pure Python with no dependencies.
Tests that verify encoded images against an external decoder are skipped when
ImageMagick is not installed.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

if __name__ == '__main__':
    suite = unittest.defaultTestLoader.discover(HERE, pattern='test_*.py')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
