"""VisuBezier -- a preview when hovering CSS easing functions in Sublime Text.

Matched easings are underlined in the buffer; hovering one opens a popup with a
plot of the curve and an animation comparing it against a reference easing.
Rendering happens off the UI thread and is cached, because composing the GIF
takes a couple of hundred milliseconds.
"""

import sys
import traceback

import sublime
import sublime_plugin

# Sublime reloads a package's top-level plugin files when they change, but not
# modules inside subdirectories -- those stay cached from the previous import.
# Dropping them here means an updated core/ is picked up along with this file,
# rather than silently running against the previous version until a restart.
_CORE = __package__ + '.core'
for _stale in [n for n in list(sys.modules) if n == _CORE or n.startswith(_CORE + '.')]:
    del sys.modules[_stale]

from .core import detect  # noqa: E402
from .core import render  # noqa: E402

SETTINGS_FILE = 'VisuBezier.sublime-settings'
SETTINGS_KEY = 'visubezier'
REGION_KEY = 'visubezier.easings'

#: Milliseconds to wait after an edit before rescanning the buffer.
RESCAN_DELAY = 500

#: Cap on rendered previews held in memory. An animated preview is a list of
#: stills, on the order of 60 KB once base64-encoded.
CACHE_LIMIT = 24

DEFAULTS = {
    'reference_easing_function': 'linear',
    'duration': '1s',
    'background': '#2d2d30',
    'foreground': '#d7d7d7',
    'animate': True,
    'underline': True,
    'underline_scope': 'region.bluish',
    'selectors': [
        'source.css',
        'source.scss',
        'source.sass',
        'source.less',
        'source.stylus',
        'source.postcss',
        'text.xml',
    ],
    'max_file_size': 1048576,
    'debug': False,
}

_settings = None
_cache = {}
_cache_order = []

#: Incremented on every hover so that a slow render belonging to an earlier
#: hover cannot pop up over a later one, and so that the animation loop of a
#: dismissed popup stops driving updates.
_hover_token = 0

#: Per-view edit counter, used to drop stale debounced rescans.
_pending_scans = {}


def plugin_loaded():
    global _settings
    _settings = sublime.load_settings(SETTINGS_FILE)
    _settings.add_on_change(SETTINGS_KEY, _on_settings_changed)
    sublime.set_timeout_async(_scan_all, 0)


def plugin_unloaded():
    if _settings is not None:
        _settings.clear_on_change(SETTINGS_KEY)
    for window in sublime.windows():
        for view in window.views():
            view.erase_regions(REGION_KEY)


def _log(message):
    """Print to the console when debugging is switched on."""
    if _setting('debug'):
        print('VisuBezier: ' + message)


def _report(message):
    """Surface a failure rather than letting it vanish in a worker thread."""
    print('VisuBezier: ' + message)
    traceback.print_exc()
    sublime.status_message('VisuBezier: ' + message + ' (see console)')


def _setting(name):
    """Read a setting, falling back to the packaged default."""
    if _settings is None:
        return DEFAULTS[name]
    return _settings.get(name, DEFAULTS[name])


def _on_settings_changed():
    """Drop cached previews and rescan, since colours or duration may have moved."""
    _cache.clear()
    del _cache_order[:]
    sublime.set_timeout_async(_scan_all, 0)


def _scan_all():
    """Rescan every open view."""
    for window in sublime.windows():
        for view in window.views():
            _scan(view)


def _selector():
    """Join the configured scope selectors into a single selector expression."""
    selectors = _setting('selectors')
    if not isinstance(selectors, list):
        return ''
    return ', '.join(str(entry) for entry in selectors if entry)


def _scan(view):
    """Find easings in a view and underline them."""
    if view is None or not view.is_valid():
        return

    selector = _selector()
    if not selector:
        view.erase_regions(REGION_KEY)
        return

    size = view.size()
    if size == 0 or size > _setting('max_file_size'):
        view.erase_regions(REGION_KEY)
        return

    # Cheap rejection: a buffer with no matching scope anywhere cannot hold a
    # CSS easing we care about, and this avoids regexing every open file.
    if not view.find_by_selector(selector):
        view.erase_regions(REGION_KEY)
        return

    text = view.substr(sublime.Region(0, size))
    regions = [
        sublime.Region(start, end)
        for start, end, _ in detect.find_easings(text)
        # Re-check per match so embedded CSS inside HTML or XML still works,
        # while easings mentioned in comments or strings elsewhere do not.
        if view.match_selector(start, selector)
    ]

    if not regions:
        view.erase_regions(REGION_KEY)
        return

    # The regions double as the hover index, so they are registered either way;
    # switching the underline off just makes them invisible.
    if _setting('underline'):
        scope = _setting('underline_scope')
        flags = (sublime.DRAW_NO_FILL
                 | sublime.DRAW_NO_OUTLINE
                 | sublime.DRAW_STIPPLED_UNDERLINE
                 | sublime.PERSISTENT)
    else:
        scope = ''
        flags = sublime.HIDDEN | sublime.PERSISTENT

    view.add_regions(REGION_KEY, regions, scope, '', flags)


def _cache_get(key):
    return _cache.get(key)


def _cache_put(key, value):
    """Store a rendered preview, evicting the oldest entry past the limit."""
    if key in _cache:
        return
    _cache[key] = value
    _cache_order.append(key)
    while len(_cache_order) > CACHE_LIMIT:
        del _cache[_cache_order.pop(0)]


def _popup_html(expression, reference, uri):
    """Build the minihtml for the hover popup."""
    return """
        <body id="visubezier">
            <style>
                body { margin: 0; padding: 0.4rem; }
                .label {
                    font-family: system;
                    font-size: 0.9rem;
                    color: color(var(--foreground) alpha(0.75));
                    padding: 0.1rem 0;
                }
                .easing { color: var(--foreground); }
            </style>
            <div class="label">%s</div>
            <div class="preview"><img src="%s" width="%d" height="%d"></div>
            <div class="label easing">%s</div>
        </body>
    """ % (_escape(reference), uri, render.WIDTH, render.HEIGHT, _escape(expression))


def _escape(text):
    """Escape text for inclusion in minihtml."""
    return (str(text)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;'))


def _show(view, point, expression, reference, preview, token):
    """Open the popup, and drive the animation if there is more than one frame.

    minihtml paints only the first frame of an animated GIF, so the animation
    is played by swapping the image with `update_popup` on a timer instead.
    """
    frames = preview['uris']
    view.show_popup(
        _popup_html(expression, reference, frames[0]),
        sublime.HIDE_ON_MOUSE_MOVE_AWAY,
        location=point,
        max_width=560,
        max_height=260,
    )
    if len(frames) > 1:
        _advance(view, token, expression, reference, preview, 1)


def _advance(view, token, expression, reference, preview, index):
    """Schedule the next animation frame."""
    frames = preview['uris']

    def step():
        # Stop as soon as the popup is gone or another hover has taken over,
        # so a dismissed preview leaves no timer running.
        if token != _hover_token or not view.is_valid():
            _log('animation stopped: superseded or view gone')
            return
        if not view.is_popup_visible():
            _log('animation stopped at frame %d: popup no longer visible' % index)
            return
        try:
            view.update_popup(_popup_html(expression, reference, frames[index]))
        except Exception:
            _report('could not update the popup')
            return
        _advance(view, token, expression, reference, preview, (index + 1) % len(frames))

    sublime.set_timeout(step, preview['delay_ms'])


class VisuBezierListener(sublime_plugin.EventListener):
    """Keeps easing regions current and serves the hover preview."""

    def on_load_async(self, view):
        _scan(view)

    def on_activated_async(self, view):
        if not view.get_regions(REGION_KEY):
            _scan(view)

    def on_modified_async(self, view):
        self._schedule_scan(view)

    def on_post_save_async(self, view):
        _scan(view)

    def on_close(self, view):
        _pending_scans.pop(view.id(), None)

    def _schedule_scan(self, view):
        """Debounce rescans so typing does not re-regex the buffer per keystroke."""
        view_id = view.id()
        token = _pending_scans.get(view_id, 0) + 1
        _pending_scans[view_id] = token

        def run():
            if _pending_scans.get(view_id) == token:
                _scan(view)

        sublime.set_timeout_async(run, RESCAN_DELAY)

    def on_hover(self, view, point, hover_zone):
        if hover_zone != sublime.HOVER_TEXT:
            return

        for region in view.get_regions(REGION_KEY):
            if region.contains(point):
                self._preview(view, point, view.substr(region))
                return

    def _preview(self, view, point, expression):
        global _hover_token

        reference = str(_setting('reference_easing_function'))
        key = (
            expression.lower(),
            reference.lower(),
            str(_setting('duration')),
            str(_setting('background')),
            str(_setting('foreground')),
            bool(_setting('animate')),
        )

        _hover_token += 1
        token = _hover_token

        cached = _cache_get(key)
        if cached is not None:
            _show(view, point, expression, reference, cached, token)
            return

        def work():
            try:
                result = render.build(
                    expression,
                    reference=reference,
                    background=str(_setting('background')),
                    foreground=str(_setting('foreground')),
                    duration=str(_setting('duration')),
                    animate=bool(_setting('animate')),
                )
            except Exception:
                _report('failed to render a preview for %r' % expression)
                return
            if result is None:
                _log('no preview: %r did not parse' % expression)
                return
            preview = {
                'uris': [render.data_uri(frame, result['mime'])
                         for frame in result['frames']],
                'delay_ms': result['delay_ms'],
            }
            _log('rendered %r: %d frame(s), %d ms apart'
                 % (expression, len(preview['uris']), preview['delay_ms']))
            _cache_put(key, preview)

            def present():
                # A newer hover has taken over, or the view went away.
                if token != _hover_token or not view.is_valid():
                    _log('discarding a superseded preview for %r' % expression)
                    return
                try:
                    _show(view, point, expression, reference, preview, token)
                except Exception:
                    _report('failed to show the preview for %r' % expression)

            sublime.set_timeout(present, 0)

        sublime.set_timeout_async(work, 0)
