"""Locating CSS easing functions in a document.

A port of the composed regular expression from the VS Code extension, with the
number grammars tightened so they cannot match empty strings and the trailing
delimiter turned into a lookahead so that adjacent easings are both found.
"""

import re

# An x coordinate is confined to [0, 1]; a y coordinate is unbounded so that
# overshooting curves such as cubic-bezier(0.4, -0.2, 0.42, 1.2) still match.
_COORD_X = r'(?:0?\.\d+|[01](?:\.\d+)?)'
_COORD_Y = r'(?:[+-]?(?:\d+(?:\.\d+)?|\.\d+))'

_CUBIC_BEZIER = (
    r'cubic-bezier\(\s*' + _COORD_X + r'\s*,\s*' + _COORD_Y +
    r'\s*,\s*' + _COORD_X + r'\s*,\s*' + _COORD_Y + r'\s*\)'
)

_STEPS = r'steps\(\s*[1-9]\d*(?:\s*,\s*(?:start|end|jump-(?:start|end|both|none)))?\s*\)'

# A linear() stop is a value optionally followed by one or two percentages.
_LINEAR_VALUE = r'[+-]?(?:\d+(?:\.\d+)?|\.\d+)'
_LINEAR_POSITION = r'(?:\d+(?:\.\d+)?|\.\d+)%'
_LINEAR_STOP = _LINEAR_VALUE + r'(?:\s+' + _LINEAR_POSITION + r'){0,2}'
_LINEAR = r'linear\(\s*' + _LINEAR_STOP + r'(?:\s*,\s*' + _LINEAR_STOP + r')*\s*\)'

_KEYWORDS = r'linear|ease(?:-in)?(?:-out)?|step-(?:start|end)'

# Functions are tried before bare keywords so that `linear(...)` is not first
# attempted as the `linear` keyword and recovered only by backtracking.
_EASING = '|'.join(['(?:%s)' % part for part in (_CUBIC_BEZIER, _STEPS, _LINEAR, _KEYWORDS)])

# The easing must be delimited on both sides so that identifiers merely
# containing one -- `release`, `--my-ease`, `ease-out-quad` -- are left alone.
# Both delimiters are zero-width, so `ease,ease` yields two matches.
PATTERN = re.compile(
    r'(?<=[:\s,"\'])(?:' + _EASING + r')(?=[\s,;"\')])',
    re.IGNORECASE,
)


def find_easings(text):
    """Find every easing function in `text`.

    :param text: document contents to scan.
    :returns: list of (start, end, expression) tuples, in document order.
    """
    return [(match.start(), match.end(), match.group(0)) for match in PATTERN.finditer(text)]
