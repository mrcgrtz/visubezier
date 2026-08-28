#!/usr/bin/env python3
"""Regenerate preview.gif for the README.

    python3 tools/make_preview.py

The plugin itself never emits a GIF -- minihtml paints only the first frame of
one -- but GitHub renders animated GIFs, so the README asset is produced here
with the same renderer.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import render  # noqa: E402

#: A bounce, which exercises overshoot and settling in one image.
EXPRESSION = (
    'linear(0, 0.063, 0.25, 0.563, 1 36.4%, 0.812, 0.75, 0.813, 1 72.7%, '
    '0.953, 0.938, 0.953, 1 90.9%, 0.984, 1 100% 100%)'
)

if __name__ == '__main__':
    data = render.render_gif(EXPRESSION, duration='1.4s')
    target = os.path.join(ROOT, 'preview.gif')
    with open(target, 'wb') as handle:
        handle.write(data)
    print('wrote %s (%d bytes)' % (target, len(data)))
