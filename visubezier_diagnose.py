"""Diagnostic for minihtml image support.

Round one showed every image blank -- including a 188-byte PNG and a file://
reference -- while the <img> boxes were still laid out at their declared sizes.
So minihtml parses the tag and reserves the box, then paints nothing, for every
format and both URL schemes.

That rules out the encoders as the sole cause, so this round leads with images
this package did not produce: the upstream icon already in the repository, and
the canonical 1x1 PNG data URI. It also varies the markup and the URL scheme,
and renders the same set as a phantom, since phantoms and popups take different
paths to the screen.

Run it from the command palette: "VisuBezier: Diagnose Image Support".
"""

import base64
import os
import struct
import zlib
from urllib.parse import quote

import sublime
import sublime_plugin

from . import visubezier as plugin  # noqa: F401  (ensures the package imports)
from .core import png
from .core import raster
from .core import render

#: The canonical 1x1 PNG data URI. Not produced by this package.
CANONICAL_1X1 = (
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQ'
    'DwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
)

PALETTE = raster.build_palette((45, 45, 48), (215, 215, 215))


def _chunk(tag, payload):
    return (struct.pack('>I', len(payload)) + tag + payload
            + struct.pack('>I', zlib.crc32(tag + payload) & 0xFFFFFFFF))


def _truecolor_png(size=16):
    """A colour-type-2 PNG, to test whether palette PNGs specifically are refused."""
    raw = bytearray()
    for y in range(size):
        raw.append(0)
        for x in range(size):
            raw += bytes((255, 0, 0) if (x // 2 + y // 2) % 2 else (0, 0, 255))
    return (b'\x89PNG\r\n\x1a\n'
            + _chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0))
            + _chunk(b'IDAT', zlib.compress(bytes(raw), 9))
            + _chunk(b'IEND', b''))


def _indexed_png(size=16):
    pixels = bytearray(31 if (x // 2 + y // 2) % 2 else 0
                       for y in range(size) for x in range(size))
    return png.encode(pixels, size, size, PALETTE)


def _file_url(path):
    """A file:// URL with the path percent-encoded.

    The packages and cache directories both contain a space ("Sublime Text"),
    which an unescaped URL would truncate.
    """
    return 'file://' + quote(path)


def _rows():
    """Build the test rows, strongest controls first."""
    icon = os.path.join(sublime.packages_path(), 'VisuBezier', 'visubezier.png')
    animated, _ = render.render('ease-in-out')
    static, _ = render.render('ease-in-out', animate=False)

    return [
        ('I  upstream icon via res://  (not our encoder, not a data URL)',
         'res://Packages/VisuBezier/visubezier.png', 128, 128),
        ('J  upstream icon via file:// (percent-encoded)',
         _file_url(icon), 128, 128),
        ('K  canonical 1x1 PNG data URL, scaled  (not our encoder)',
         'data:image/png;base64,' + CANONICAL_1X1, 64, 64),
        ('L  truecolor PNG data URL  (colour type 2)',
         render.data_uri(_truecolor_png(), 'image/png'), 64, 64),
        ('M  indexed PNG data URL  (colour type 3)',
         render.data_uri(_indexed_png(), 'image/png'), 64, 64),
        ('N  full-size static preview PNG',
         render.data_uri(static, 'image/png'), render.WIDTH, render.HEIGHT),
        ('O  full-size animated preview GIF',
         render.data_uri(animated, 'image/gif'), render.WIDTH, render.HEIGHT),
    ]


def _markup_variants(url):
    """The same known image, marked up three different ways."""
    return [
        ('P  no width/height attributes', '<img src="%s">' % url),
        ('Q  self-closing tag', '<img src="%s" />' % url),
        ('R  sized with CSS instead of attributes',
         '<img src="%s" style="width: 64px; height: 64px;">' % url),
    ]


class VisuBezierDiagnoseCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        report = ['', 'VisuBezier image diagnostic (round 2)', '']
        blocks = []

        for label, url, width, height in _rows():
            report.append('%-62s %s' % (label, url[:72]))
            blocks.append(
                '<div class="label">%s</div>'
                '<div class="cell"><img src="%s" width="%d" height="%d"></div>'
                % (label, url, width, height)
            )

        control = 'res://Packages/VisuBezier/visubezier.png'
        for label, markup in _markup_variants(control):
            report.append('%-62s markup variant' % label)
            blocks.append('<div class="label">%s</div><div class="cell">%s</div>'
                          % (label, markup))

        body = """
            <body id="visubezier-diagnose">
                <style>
                    body { margin: 0; padding: 0.5rem; }
                    .label { font-size: 0.9rem; color: var(--foreground); padding: 0.3rem 0 0.1rem 0; }
                    .cell { background-color: color(var(--foreground) alpha(0.12)); padding: 2px; }
                </style>
                <p>Rows I-K use images this package did not produce.</p>
                %s
            </body>
        """ % ''.join(blocks)

        print('\n'.join(report))
        print('\nIf I, J and K are also blank, the popup is not rendering any '
              'image at all and the encoders are not the cause.')

        self.view.show_popup(body, sublime.HIDE_ON_MOUSE_MOVE_AWAY,
                             location=-1, max_width=600, max_height=900)

        # Phantoms reach the screen by a different path than popups; if images
        # appear here but not above, the problem is specific to popups.
        self.phantoms = sublime.PhantomSet(self.view, 'visubezier.diagnose')
        self.phantoms.update([sublime.Phantom(
            sublime.Region(self.view.sel()[0].begin()),
            '<body><div>PHANTOM: icon via res://, then the preview GIF</div>'
            '<div><img src="res://Packages/VisuBezier/visubezier.png" '
            'width="64" height="64"></div><div><img src="%s" width="%d" '
            'height="%d"></div></body>'
            % (render.data_uri(render.render('ease-in-out')[0], 'image/gif'),
               render.WIDTH, render.HEIGHT),
            sublime.LAYOUT_BLOCK,
        )])


class VisuBezierDiagnoseClearCommand(sublime_plugin.TextCommand):
    """Removes the diagnostic phantom."""

    def run(self, edit):
        sublime.PhantomSet(self.view, 'visubezier.diagnose').update([])
