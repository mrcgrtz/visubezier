"""A tiny indexed-colour canvas with anti-aliased drawing primitives.

Previews use exactly two colours -- a background and a foreground -- so the
palette is a single ramp of the foreground composited over the background at
increasing opacity. Every drawing call therefore addresses a pixel by coverage
alone, and the same buffer can be handed to either the PNG or the GIF encoder.
"""

import math

#: Number of steps in the foreground-over-background ramp. 32 keeps GIF's LZW
#: code size at 5 bits while leaving plenty of gradations for anti-aliasing.
LEVELS = 32

_MAX_LEVEL = LEVELS - 1


def build_palette(background, foreground):
    """Build the ramp palette for a background/foreground colour pair.

    :param background: (r, g, b) tuple painted at coverage 0.
    :param foreground: (r, g, b) tuple painted at coverage 1.
    :returns: list of LEVELS (r, g, b) tuples.
    """
    palette = []
    for level in range(LEVELS):
        alpha = level / _MAX_LEVEL
        palette.append(tuple(
            int(round(background[i] + (foreground[i] - background[i]) * alpha))
            for i in range(3)
        ))
    return palette


def parse_color(value, fallback=(0, 0, 0)):
    """Parse a ``#rgb`` or ``#rrggbb`` string into an (r, g, b) tuple."""
    if not isinstance(value, str):
        return fallback
    text = value.strip().lstrip('#')
    if len(text) == 3:
        text = ''.join(c * 2 for c in text)
    if len(text) != 6:
        return fallback
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError:
        return fallback


class Canvas:
    """A flat row-major buffer of palette indices."""

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.pixels = bytearray(width * height)

    def copy(self):
        clone = Canvas(self.width, self.height)
        clone.pixels[:] = self.pixels
        return clone

    def sub_rect(self, x, y, width, height):
        """Extract a rectangle as a flat buffer, for GIF's partial frames."""
        out = bytearray()
        for row in range(y, y + height):
            start = row * self.width
            out += self.pixels[start + x:start + x + width]
        return out

    def blend(self, x, y, alpha):
        """Raise a pixel's coverage to `alpha`, never lowering it.

        Taking the maximum rather than compositing keeps overlapping strokes
        from darkening each other, which matters where the curve crosses the
        grid lines.
        """
        if alpha <= 0 or x < 0 or y < 0 or x >= self.width or y >= self.height:
            return
        level = int(round(min(alpha, 1.0) * _MAX_LEVEL))
        offset = y * self.width + x
        if level > self.pixels[offset]:
            self.pixels[offset] = level

    def fill_rect(self, x, y, width, height, alpha=1.0):
        """Fill an axis-aligned rectangle, anti-aliasing fractional edges."""
        left, right = x, x + width
        top, bottom = y, y + height
        for py in range(int(math.floor(top)), int(math.ceil(bottom))):
            # Vertical coverage of this pixel row against the rectangle.
            cover_y = min(bottom, py + 1) - max(top, py)
            if cover_y <= 0:
                continue
            for px in range(int(math.floor(left)), int(math.ceil(right))):
                cover_x = min(right, px + 1) - max(left, px)
                if cover_x <= 0:
                    continue
                self.blend(px, py, alpha * cover_x * cover_y)

    def circle(self, cx, cy, radius, alpha=1.0):
        """Fill a circle, estimating edge coverage by 4x4 supersampling."""
        for py in range(int(math.floor(cy - radius)), int(math.ceil(cy + radius)) + 1):
            for px in range(int(math.floor(cx - radius)), int(math.ceil(cx + radius)) + 1):
                hits = 0
                for sy in range(4):
                    for sx in range(4):
                        dx = px + (sx + 0.5) / 4 - cx
                        dy = py + (sy + 0.5) / 4 - cy
                        if dx * dx + dy * dy <= radius * radius:
                            hits += 1
                if hits:
                    self.blend(px, py, alpha * hits / 16.0)

    def _wu_line(self, x0, y0, x1, y1, alpha):
        """Draw a one-pixel anti-aliased line (Xiaolin Wu)."""
        steep = abs(y1 - y0) > abs(x1 - x0)
        if steep:
            x0, y0 = y0, x0
            x1, y1 = y1, x1
        if x0 > x1:
            x0, x1 = x1, x0
            y0, y1 = y1, y0

        dx = x1 - x0
        dy = y1 - y0
        gradient = 1.0 if dx == 0 else dy / dx

        def plot(px, py, cover):
            if steep:
                self.blend(int(py), int(px), alpha * cover)
            else:
                self.blend(int(px), int(py), alpha * cover)

        # Endpoints get their own handling so the line does not overshoot.
        for is_start in (True, False):
            ex, ey = (x0, y0) if is_start else (x1, y1)
            xend = math.floor(ex + 0.5)
            yend = ey + gradient * (xend - ex)
            xgap = (1 - ((ex + 0.5) % 1)) if is_start else ((ex + 0.5) % 1)
            ypxl = math.floor(yend)
            plot(xend, ypxl, (1 - (yend % 1)) * xgap)
            plot(xend, ypxl + 1, (yend % 1) * xgap)
            if is_start:
                intery = yend + gradient
                xstart = xend + 1
            else:
                xstop = xend

        for px in range(int(xstart), int(xstop)):
            ypxl = math.floor(intery)
            plot(px, ypxl, 1 - (intery % 1))
            plot(px, ypxl + 1, intery % 1)
            intery += gradient

    def line(self, x0, y0, x1, y1, alpha=1.0, width=1.0):
        """Draw a line of the given stroke width.

        Widths above one pixel are built from parallel Wu lines offset along the
        segment normal, which is cheaper than a general polygon rasteriser and
        indistinguishable at these sizes.
        """
        if width <= 1.0:
            self._wu_line(x0, y0, x1, y1, alpha)
            return

        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        if length == 0:
            self.circle(x0, y0, width / 2, alpha)
            return

        nx, ny = -dy / length, dx / length
        passes = max(2, int(math.ceil(width * 2)))
        for i in range(passes):
            offset = (i / (passes - 1) - 0.5) * (width - 1)
            self._wu_line(x0 + nx * offset, y0 + ny * offset,
                          x1 + nx * offset, y1 + ny * offset, alpha)

    def polyline(self, points, alpha=1.0, width=1.0):
        """Draw a connected run of line segments."""
        for i in range(len(points) - 1):
            x0, y0 = points[i]
            x1, y1 = points[i + 1]
            self.line(x0, y0, x1, y1, alpha, width)
