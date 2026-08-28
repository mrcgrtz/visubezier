"""Composition of the hover preview.

The preview pairs a plot of the easing with an animation comparing it against a
reference easing. Because minihtml has no animation support, the animation is
baked into a looping GIF: each frame is composed on a copy of a pre-rendered
static background, and only the rectangle that actually changed is encoded.

Text labels are deliberately absent from the raster -- the plugin renders them
as real minihtml text so they pick up the user's colour scheme and font.
"""

import base64
import re

from . import easing as easing_module
from . import gif
from . import png
from . import raster

#: Overall preview size, matching the proportions of the original SVG.
WIDTH = 480
HEIGHT = 100

#: The animation track occupies the left portion, the plot the right.
TRACK_WIDTH = 320
SQUARE_SIZE = 32

#: Value 0 sits at TRACK_ORIGIN, value 1 at TRACK_ORIGIN + TRACK_TRAVEL. The
#: margins either side leave room for a little overshoot to stay visible before
#: the square is clamped inside the track.
TRACK_ORIGIN = 24
TRACK_TRAVEL = 240

DEFAULT_ROW_Y = 8
CUSTOM_ROW_Y = 60
DIVIDER_Y = 50

#: The plot box, centred in the space to the right of the track.
BOX_SIZE = 60
BOX_X = TRACK_WIDTH + (WIDTH - TRACK_WIDTH - BOX_SIZE) // 2
BOX_Y = (HEIGHT - BOX_SIZE) // 2

HANDLE_RADIUS = 2.5
GRID_ALPHA = 0.35
STROKE_WIDTH = 2.0

#: Animation sampling. Frame count is derived from the duration and clamped so
#: that neither very short nor very long durations produce a silly frame count.
TARGET_FPS = 20
MIN_FORWARD_FRAMES = 4
MAX_FORWARD_FRAMES = 48

#: Animation frames are transient and re-encoded on every cache miss, so they
#: trade size for latency. The static preview is kept small instead.
FRAME_COMPRESSION = 6
STATIC_COMPRESSION = 9

#: Number of strobe positions drawn when animation is switched off.
STATIC_SAMPLES = 9

_DURATION_PATTERN = re.compile(r'^\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*(m?s)\s*$', re.IGNORECASE)


def parse_duration(text, fallback=1.0):
    """Parse a CSS time such as ``1s`` or ``500ms`` into seconds."""
    if not isinstance(text, str):
        return fallback
    match = _DURATION_PATTERN.match(text)
    if not match:
        return fallback
    value = float(match.group(1))
    if match.group(2).lower() == 'ms':
        value /= 1000.0
    return value if value > 0 else fallback


def _plot_point(time, value):
    """Map a unit-space (time, value) pair into canvas coordinates."""
    return (BOX_X + time * BOX_SIZE, BOX_Y + BOX_SIZE - value * BOX_SIZE)


def _draw_plot(canvas, easing):
    """Draw the grid, box and easing curve into the plot area."""
    # Box outline.
    canvas.line(BOX_X, BOX_Y, BOX_X + BOX_SIZE, BOX_Y, GRID_ALPHA)
    canvas.line(BOX_X, BOX_Y + BOX_SIZE, BOX_X + BOX_SIZE, BOX_Y + BOX_SIZE, GRID_ALPHA)
    canvas.line(BOX_X, BOX_Y, BOX_X, BOX_Y + BOX_SIZE, GRID_ALPHA)
    canvas.line(BOX_X + BOX_SIZE, BOX_Y, BOX_X + BOX_SIZE, BOX_Y + BOX_SIZE, GRID_ALPHA)

    # Quarter divisions on both axes.
    for fraction in (0.25, 0.5, 0.75):
        offset = BOX_SIZE * fraction
        canvas.line(BOX_X, BOX_Y + offset, BOX_X + BOX_SIZE, BOX_Y + offset, GRID_ALPHA)
        canvas.line(BOX_X + offset, BOX_Y, BOX_X + offset, BOX_Y + BOX_SIZE, GRID_ALPHA)

    # Control-point handles, for cubic-bezier only.
    handles = easing.handles()
    if handles:
        start = _plot_point(0.0, 0.0)
        end = _plot_point(1.0, 1.0)
        first = _plot_point(*handles[0])
        second = _plot_point(*handles[1])
        canvas.line(start[0], start[1], first[0], first[1], 1.0)
        canvas.line(end[0], end[1], second[0], second[1], 1.0)
        canvas.circle(first[0], first[1], HANDLE_RADIUS)
        canvas.circle(second[0], second[1], HANDLE_RADIUS)

    points = [_plot_point(time, value) for time, value in easing.points()]
    canvas.polyline(points, 1.0, STROKE_WIDTH)


def _draw_track(canvas):
    """Draw the static furniture of the animation track."""
    canvas.line(0, DIVIDER_Y, TRACK_WIDTH, DIVIDER_Y, 1.0)
    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        x = TRACK_ORIGIN + TRACK_TRAVEL * fraction
        canvas.line(x, 0, x, HEIGHT, GRID_ALPHA)


def _square_x(value):
    """Canvas x for a square at the given easing output, clamped to the track."""
    x = TRACK_ORIGIN + value * TRACK_TRAVEL
    return max(0.0, min(x, TRACK_WIDTH - SQUARE_SIZE))


def _frame_geometry(duration):
    """Choose a frame count and per-frame delay in milliseconds."""
    forward = int(round(duration * TARGET_FPS))
    forward = max(MIN_FORWARD_FRAMES, min(forward, MAX_FORWARD_FRAMES))
    return forward, max(20, int(round(duration * 1000.0 / forward)))


def _timeline(forward):
    """Sample times for one `alternate` cycle, without repeating either end."""
    times = [i / (forward - 1) for i in range(forward)]
    return times + list(reversed(times[1:-1]))


def _base_canvas(custom, palette):
    """The static furniture: track, grid and the easing plot."""
    canvas = raster.Canvas(WIDTH, HEIGHT)
    _draw_track(canvas)
    _draw_plot(canvas, custom)
    return canvas


def _compose(base, default, custom, time):
    """Copy the static background and place both squares for a moment in time."""
    canvas = base.copy()
    for row_y, fn in ((DEFAULT_ROW_Y, default), (CUSTOM_ROW_Y, custom)):
        canvas.fill_rect(_square_x(fn.at(time)), row_y, SQUARE_SIZE, SQUARE_SIZE)
    return canvas


def _parse_pair(expression, reference):
    """Parse the previewed easing and its reference, or None if the first fails."""
    custom = easing_module.parse(expression)
    if custom is None:
        return None
    # An unparseable reference should not stop the preview; fall back to linear.
    default = easing_module.parse(reference) or easing_module.parse('linear')
    return default, custom


def _draw_strobe(canvas, default, custom):
    """Draw both rows as a motion trail of evenly time-spaced positions.

    Used when animation is switched off: samples bunch up where the easing is
    slow and spread out where it is fast, so the shape stays readable at rest.
    Opacity rises with time to show which way the motion runs.
    """
    for index in range(STATIC_SAMPLES):
        time = index / (STATIC_SAMPLES - 1)
        alpha = 0.25 + 0.75 * time
        for row_y, fn in ((DEFAULT_ROW_Y, default), (CUSTOM_ROW_Y, custom)):
            canvas.fill_rect(_square_x(fn.at(time)), row_y, SQUARE_SIZE, SQUARE_SIZE, alpha)


def build(expression, reference='linear', background='#2d2d30', foreground='#d7d7d7',
          duration='1s', animate=True):
    """Render the hover preview.

    minihtml paints only the first frame of an animated GIF, so animation is
    delivered as a sequence of stills that the plugin cycles through with
    `update_popup` instead. A static preview is a single-frame sequence.

    :param expression: the easing to preview.
    :param reference: easing drawn alongside it for comparison.
    :param background: preview background colour, as a hex string.
    :param foreground: preview foreground colour, as a hex string.
    :param duration: animation duration, as a CSS time string.
    :param animate: when False, produce one static strobe frame.
    :returns: dict with `frames` (list of PNG byte strings), `mime` and
        `delay_ms`, or None if the expression could not be parsed.
    """
    parsed = _parse_pair(expression, reference)
    if parsed is None:
        return None
    default, custom = parsed

    palette = raster.build_palette(
        raster.parse_color(background, (45, 45, 48)),
        raster.parse_color(foreground, (215, 215, 215)),
    )
    base = _base_canvas(custom, palette)

    if not animate:
        _draw_strobe(base, default, custom)
        frame = png.encode(base.pixels, WIDTH, HEIGHT, palette, STATIC_COMPRESSION)
        return {'frames': [frame], 'mime': 'image/png', 'delay_ms': 0}

    forward, delay_ms = _frame_geometry(parse_duration(duration))
    frames = [
        png.encode(_compose(base, default, custom, time).pixels,
                   WIDTH, HEIGHT, palette, FRAME_COMPRESSION)
        for time in _timeline(forward)
    ]
    return {'frames': frames, 'mime': 'image/png', 'delay_ms': delay_ms}


def render_gif(expression, reference='linear', background='#2d2d30',
               foreground='#d7d7d7', duration='1s'):
    """Render the preview as an animated GIF.

    Unused by the plugin, since minihtml will not animate it. Kept for
    generating the animated preview in the README -- see tools/make_preview.py.
    """
    parsed = _parse_pair(expression, reference)
    if parsed is None:
        return None
    default, custom = parsed

    palette = raster.build_palette(
        raster.parse_color(background, (45, 45, 48)),
        raster.parse_color(foreground, (215, 215, 215)),
    )
    base = _base_canvas(custom, palette)
    forward, delay_ms = _frame_geometry(parse_duration(duration))
    delay = max(2, int(round(delay_ms / 10.0)))

    frames = []
    previous = None
    for index, time in enumerate(_timeline(forward)):
        canvas = _compose(base, default, custom, time)
        positions = [_square_x(fn.at(time)) for fn in (default, custom)]
        if index == 0:
            frames.append({'pixels': canvas.pixels, 'x': 0, 'y': 0,
                           'width': WIDTH, 'height': HEIGHT, 'delay': delay})
        else:
            # Ship only the region the squares vacated or entered. Anti-aliased
            # edges spill a pixel either side, so pad the bounds by one.
            xs = positions + previous
            left = max(0, int(min(xs)) - 1)
            right = min(WIDTH, int(max(xs)) + SQUARE_SIZE + 2)
            top = max(0, DEFAULT_ROW_Y - 1)
            bottom = min(HEIGHT, CUSTOM_ROW_Y + SQUARE_SIZE + 1)
            frames.append({
                'pixels': canvas.sub_rect(left, top, right - left, bottom - top),
                'x': left, 'y': top,
                'width': right - left, 'height': bottom - top, 'delay': delay,
            })
        previous = positions

    return gif.encode(frames, WIDTH, HEIGHT, palette)


def data_uri(image, mime='image/png'):
    """Wrap encoded image bytes in a data: URI for use in a minihtml <img>."""
    return 'data:%s;base64,%s' % (mime, base64.b64encode(image).decode('ascii'))
