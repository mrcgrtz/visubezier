"""Parsing and evaluation of CSS easing functions.

The VS Code extension only ever had to *draw* an easing -- the animation itself
was handed to the browser engine as a CSS string. minihtml has no animation
support, so previews are rendered frame by frame here and every easing must be
evaluated numerically as well as plotted.
"""

import math

#: Keyword easings, as their cubic-bezier control points.
KEYWORD_EASINGS = {
    'linear': (0.0, 0.0, 1.0, 1.0),
    'ease': (0.25, 0.1, 0.25, 1.0),
    'ease-in': (0.42, 0.0, 1.0, 1.0),
    'ease-out': (0.0, 0.0, 0.58, 1.0),
    'ease-in-out': (0.42, 0.0, 0.58, 1.0),
}

#: Keyword step easings, as (count, jumpterm).
KEYWORD_STEPS = {
    'step-start': (1, 'jump-start'),
    'step-end': (1, 'jump-end'),
}

#: Legacy jumpterm spellings accepted by the steps() grammar.
_JUMP_ALIASES = {'start': 'jump-start', 'end': 'jump-end'}


class CubicBezier:
    """A ``cubic-bezier()`` easing with two control points."""

    def __init__(self, x1, y1, x2, y2):
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2
        # Polynomial coefficients for the 1-D Bezier in each axis.
        self._cx = 3.0 * x1
        self._bx = 3.0 * (x2 - x1) - self._cx
        self._ax = 1.0 - self._cx - self._bx
        self._cy = 3.0 * y1
        self._by = 3.0 * (y2 - y1) - self._cy
        self._ay = 1.0 - self._cy - self._by

    def _sample_x(self, t):
        return ((self._ax * t + self._bx) * t + self._cx) * t

    def _sample_y(self, t):
        return ((self._ay * t + self._by) * t + self._cy) * t

    def _slope_x(self, t):
        return (3.0 * self._ax * t + 2.0 * self._bx) * t + self._cx

    def _solve_t(self, x, epsilon=1e-6):
        """Find the parameter t whose curve x-coordinate is `x`."""
        # Newton-Raphson converges in a couple of steps for well-behaved curves.
        t = x
        for _ in range(8):
            error = self._sample_x(t) - x
            if abs(error) < epsilon:
                return t
            slope = self._slope_x(t)
            if abs(slope) < 1e-9:
                break
            t -= error / slope

        # Fall back to bisection where the curve is flat and Newton stalls.
        low, high, t = 0.0, 1.0, x
        while low < high:
            value = self._sample_x(t)
            if abs(value - x) < epsilon:
                return t
            if x > value:
                low = t
            else:
                high = t
            t = (high - low) / 2.0 + low
        return t

    def at(self, progress):
        """Output value for an input time in [0, 1]."""
        if progress <= 0.0:
            return 0.0
        if progress >= 1.0:
            return 1.0
        return self._sample_y(self._solve_t(progress))

    def points(self, samples=96):
        """Sample the curve as (time, value) pairs for plotting."""
        return [
            (self._sample_x(i / samples), self._sample_y(i / samples))
            for i in range(samples + 1)
        ]

    def handles(self):
        """The two control-point coordinates, for drawing handle markers."""
        return [(self.x1, self.y1), (self.x2, self.y2)]


class Steps:
    """A ``steps()`` easing."""

    def __init__(self, count, jumpterm='jump-end'):
        self.count = count
        self.jumpterm = jumpterm

    def _interval_value(self, index):
        """Output value held across the `index`-th of `count` intervals."""
        n = self.count
        if self.jumpterm == 'jump-start':
            return (index + 1) / n
        if self.jumpterm == 'jump-both':
            return (index + 1) / (n + 1)
        if self.jumpterm == 'jump-none':
            # A single step with jump-none has nowhere to jump to.
            return 0.0 if n <= 1 else index / (n - 1)
        return index / n

    def at(self, progress):
        if progress <= 0.0 and self.jumpterm in ('jump-end', 'jump-none'):
            return 0.0
        if progress >= 1.0:
            return 1.0
        index = min(int(progress * self.count), self.count - 1)
        return self._interval_value(index)

    def points(self):
        """Corner points of the staircase, as (time, value) pairs."""
        result = []
        for index in range(self.count):
            value = self._interval_value(index)
            result.append((index / self.count, value))
            result.append(((index + 1) / self.count, value))
        # jump-end and jump-both still have a final riser up to 1.
        if result[-1][1] != 1.0:
            result.append((1.0, 1.0))
        return result

    def handles(self):
        return []


class Linear:
    """A ``linear()`` easing: a polyline through explicit stops."""

    def __init__(self, stops):
        #: List of (position, value) pairs, positions ascending across [0, 1].
        self.stops = stops

    def at(self, progress):
        stops = self.stops
        if progress <= stops[0][0]:
            return stops[0][1]
        for i in range(1, len(stops)):
            position, value = stops[i]
            if progress <= position:
                prev_position, prev_value = stops[i - 1]
                span = position - prev_position
                if span <= 0:
                    return value
                ratio = (progress - prev_position) / span
                return prev_value + (value - prev_value) * ratio
        return stops[-1][1]

    def points(self):
        return list(self.stops)

    def handles(self):
        return []


def _parse_number(text):
    try:
        return float(text)
    except ValueError:
        return None


def _parse_position(text):
    """Parse a percentage stop position such as ``25%`` into a fraction.

    Returns False -- distinct from the None used for an omitted position -- when
    the token is present but not a valid percentage.
    """
    token = text.strip()
    if not token.endswith('%'):
        return False
    value = _parse_number(token[:-1])
    return False if value is None else value / 100.0


def _split_arguments(body):
    """Split a function body on commas, dropping empty entries."""
    return [part.strip() for part in body.split(',') if part.strip()]


def _function_body(text, name):
    """Return the argument text inside ``name(...)``, or None."""
    prefix = name + '('
    if not text.startswith(prefix) or not text.endswith(')'):
        return None
    return text[len(prefix):-1]


def parse_linear_stops(arguments):
    """Normalise ``linear()`` arguments into ascending (position, value) pairs.

    Implements the CSS Easing Level 2 normalisation: missing positions are
    distributed evenly between their explicit neighbours, the first and last
    default to 0 and 1, and the resulting list is forced to be non-decreasing.
    """
    entries = []
    for argument in arguments:
        parts = argument.split()
        value = _parse_number(parts[0]) if parts else None
        if value is None:
            return None

        if len(parts) == 1:
            entries.append([None, value])
        elif len(parts) in (2, 3):
            # Two positions for one value describe a flat run at that value.
            for token in parts[1:]:
                position = _parse_position(token)
                if position is False:
                    return None
                entries.append([position, value])
        else:
            return None

    if not entries:
        return None

    # Anchor the ends so every gap has explicit neighbours to interpolate between.
    if entries[0][0] is None:
        entries[0][0] = 0.0
    if entries[-1][0] is None:
        entries[-1][0] = 1.0

    for index, entry in enumerate(entries):
        if entry[0] is not None:
            continue
        previous = index - 1
        while entries[previous][0] is None:
            previous -= 1
        following = index + 1
        while entries[following][0] is None:
            following += 1
        span = entries[following][0] - entries[previous][0]
        entry[0] = entries[previous][0] + span * (index - previous) / (following - previous)

    # Positions may not run backwards.
    for index in range(1, len(entries)):
        if entries[index][0] < entries[index - 1][0]:
            entries[index][0] = entries[index - 1][0]

    return [(position, value) for position, value in entries]


def parse(text):
    """Parse an easing function or keyword.

    :param text: an easing such as ``ease-in``, ``cubic-bezier(...)``,
        ``steps(...)`` or ``linear(...)``. Case and surrounding space are
        insignificant.
    :returns: a CubicBezier, Steps or Linear instance, or None if unparseable.
    """
    if not text:
        return None
    normalised = ' '.join(text.lower().split())

    if normalised in KEYWORD_EASINGS:
        return CubicBezier(*KEYWORD_EASINGS[normalised])
    if normalised in KEYWORD_STEPS:
        return Steps(*KEYWORD_STEPS[normalised])

    body = _function_body(normalised, 'cubic-bezier')
    if body is not None:
        arguments = _split_arguments(body)
        if len(arguments) != 4:
            return None
        numbers = [_parse_number(argument) for argument in arguments]
        if any(number is None for number in numbers):
            return None
        return CubicBezier(*numbers)

    body = _function_body(normalised, 'steps')
    if body is not None:
        arguments = _split_arguments(body)
        if not 1 <= len(arguments) <= 2:
            return None
        try:
            count = int(arguments[0])
        except ValueError:
            return None
        if count < 1:
            return None
        jumpterm = arguments[1] if len(arguments) == 2 else 'jump-end'
        jumpterm = _JUMP_ALIASES.get(jumpterm, jumpterm)
        if jumpterm not in ('jump-start', 'jump-end', 'jump-both', 'jump-none'):
            return None
        # jump-none needs at least two steps to describe a jump at all.
        if jumpterm == 'jump-none' and count < 2:
            return None
        return Steps(count, jumpterm)

    body = _function_body(normalised, 'linear')
    if body is not None:
        stops = parse_linear_stops(_split_arguments(body))
        if not stops or len(stops) < 2:
            return None
        return Linear(stops)

    return None
