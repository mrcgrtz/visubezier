"""Diagnostic for minihtml image support.

The popup, labels and hover detection all work, so when a preview shows as a
blank gap the failure is in how minihtml decodes the image. This command puts
a series of images in one popup, each varying a single property, so that a
single glance identifies which property minihtml rejects.

Run it from the command palette: "VisuBezier: Diagnose Image Support".
"""

import os

import sublime
import sublime_plugin

from .core import gif
from .core import png
from .core import raster
from .core import render

PALETTE = raster.build_palette((45, 45, 48), (215, 215, 215))


def _checker(width, height):
    """A small high-contrast pattern, so a successful decode is unmistakable."""
    pixels = bytearray(width * height)
    for y in range(height):
        for x in range(width):
            pixels[y * width + x] = 31 if (x // 2 + y // 2) % 2 else 0
    return pixels


def _frame(pixels, width, height, delay=25):
    return {'pixels': pixels, 'x': 0, 'y': 0,
            'width': width, 'height': height, 'delay': delay}


def _pad(image, target):
    """Inflate a GIF to `target` bytes with a comment extension.

    Isolates payload size from every other property: the decoded image is
    identical, only the byte count changes.
    """
    if len(image) >= target:
        return image
    filler = b'x' * 255
    comment = bytearray(b'\x21\xFE')
    remaining = target - len(image)
    while remaining > 0:
        block = filler[:min(255, remaining)]
        comment.append(len(block))
        comment += block
        remaining -= len(block) + 1
    comment.append(0)
    # Insert after the header block, before the first frame.
    cut = image.index(b'\x21\xF9')
    return image[:cut] + bytes(comment) + image[cut:]


def _variants():
    """Build the test images, each isolating one property."""
    small = _checker(16, 16)
    wide = _checker(render.WIDTH, render.HEIGHT)

    static_gif = gif.encode([_frame(wide, render.WIDTH, render.HEIGHT)],
                            render.WIDTH, render.HEIGHT, PALETTE)

    # Two full-canvas frames: animation without partial-frame rectangles.
    shifted = bytearray(wide)
    shifted[:len(shifted) // 2] = bytearray(len(shifted) // 2)
    full_frame_animation = gif.encode(
        [_frame(wide, render.WIDTH, render.HEIGHT),
         _frame(shifted, render.WIDTH, render.HEIGHT)],
        render.WIDTH, render.HEIGHT, PALETTE,
    )

    real_animated, _ = render.render('ease-in-out')
    real_static, _ = render.render('ease-in-out', animate=False)

    return [
        ('A  tiny PNG, 16x16',
         png.encode(small, 16, 16, PALETTE), 'image/png', 16, 16),
        ('B  full-size PNG, real preview',
         real_static, 'image/png', render.WIDTH, render.HEIGHT),
        ('C  tiny GIF, 16x16, single frame',
         gif.encode([_frame(small, 16, 16)], 16, 16, PALETTE), 'image/gif', 16, 16),
        ('D  full-size GIF, single frame',
         static_gif, 'image/gif', render.WIDTH, render.HEIGHT),
        ('E  same GIF padded to 40 KB',
         _pad(static_gif, 40000), 'image/gif', render.WIDTH, render.HEIGHT),
        ('F  animated GIF, 2 full-canvas frames',
         full_frame_animation, 'image/gif', render.WIDTH, render.HEIGHT),
        ('G  animated GIF, partial frames (what the plugin ships)',
         real_animated, 'image/gif', render.WIDTH, render.HEIGHT),
    ]


class VisuBezierDiagnoseCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        rows = []
        report = []

        for label, data, mime, width, height in _variants():
            report.append('%-56s %7d bytes' % (label, len(data)))
            rows.append(
                '<div class="label">%s &mdash; %d bytes</div>'
                '<div class="cell"><img src="%s" width="%d" height="%d"></div>'
                % (label, len(data), render.data_uri(data, mime), width, height)
            )

        # A file:// reference, to separate "cannot decode this image" from
        # "cannot handle a data: URL this large".
        try:
            directory = os.path.join(sublime.cache_path(), 'VisuBezier')
            os.makedirs(directory, exist_ok=True)
            path = os.path.join(directory, 'diagnose.gif')
            data, _ = render.render('ease-in-out')
            with open(path, 'wb') as handle:
                handle.write(data)
            rows.append(
                '<div class="label">H  same animated GIF via file:// </div>'
                '<div class="cell"><img src="file://%s" width="%d" height="%d"></div>'
                % (path, render.WIDTH, render.HEIGHT)
            )
            report.append('%-56s %s' % ('H  animated GIF via file://', path))
        except Exception as error:
            report.append('H  file:// variant failed to write: %s' % error)

        print('\nVisuBezier image diagnostic\n' + '\n'.join(report))
        print('\nAny variant showing a blank gap in the popup is unsupported.')

        self.view.show_popup(
            """
            <body id="visubezier-diagnose">
                <style>
                    body { margin: 0; padding: 0.5rem; }
                    .label { font-size: 0.9rem; color: var(--foreground); padding: 0.3rem 0 0.1rem 0; }
                    .cell { background-color: color(var(--foreground) alpha(0.12)); padding: 2px; }
                    img { display: block; }
                </style>
                <p>Each row varies one property. A blank box means minihtml
                rejected that image.</p>
                %s
            </body>
            """ % ''.join(rows),
            sublime.HIDE_ON_MOUSE_MOVE_AWAY,
            location=-1,
            max_width=560,
            max_height=900,
        )
