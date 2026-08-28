"""Enough of the Sublime Text API to drive the plugin outside the editor."""
import sys, types

HOVER_TEXT, HOVER_GUTTER, HOVER_MARGIN = 1, 2, 3
DRAW_NO_FILL, DRAW_NO_OUTLINE = 32, 512
DRAW_STIPPLED_UNDERLINE, PERSISTENT, HIDDEN = 8, 16, 128
HIDE_ON_MOUSE_MOVE_AWAY = 3

deferred = []   # queued set_timeout / set_timeout_async callbacks


class Region:
    def __init__(self, a, b=None):
        self.a, self.b = a, a if b is None else b
    def begin(self): return min(self.a, self.b)
    def end(self): return max(self.a, self.b)
    def contains(self, p): return self.begin() <= p <= self.end()
    def __repr__(self): return 'Region(%d, %d)' % (self.a, self.b)


class _Settings:
    def __init__(self, values): self.values = values; self.cb = {}
    def get(self, k, d=None): return self.values.get(k, d)
    def set(self, k, v): self.values[k] = v
    def add_on_change(self, key, cb): self.cb[key] = cb
    def clear_on_change(self, key): self.cb.pop(key, None)
    def fire(self):
        for cb in list(self.cb.values()): cb()


SETTINGS = _Settings({})


def load_settings(name): return SETTINGS
def set_timeout(fn, delay=0): deferred.append(fn)
def set_timeout_async(fn, delay=0): deferred.append(fn)
def windows(): return [_WINDOW]


def drain(limit=500):
    """Run queued callbacks, including ones they queue in turn.

    Bounded, because the animation loop reschedules itself for as long as the
    popup stays visible.
    """
    runs = 0
    while deferred and runs < limit:
        deferred.pop(0)(); runs += 1
    return runs


class View:
    _next_id = [1]

    def __init__(self, text, scope='source.css'):
        self.text = text
        self.scope = scope
        self.regions = {}
        self.region_flags = {}
        self.region_scopes = {}
        self.popups = []
        self.updates = []
        self.popup_visible = False
        self._id = View._next_id[0]; View._next_id[0] += 1

    def id(self): return self._id
    def is_valid(self): return True
    def size(self): return len(self.text)
    def substr(self, r): return self.text[r.begin():r.end()]
    def add_regions(self, key, regs, scope='', icon='', flags=0):
        self.regions[key] = regs
        self.region_flags[key] = flags
        self.region_scopes[key] = scope
    def get_regions(self, key): return self.regions.get(key, [])
    def erase_regions(self, key):
        self.regions.pop(key, None); self.region_flags.pop(key, None)
    def match_selector(self, point, selector):
        return any(self.scope.startswith(s.strip()) for s in selector.split(','))
    def find_by_selector(self, selector):
        return [Region(0, len(self.text))] if self.match_selector(0, selector) else []
    def show_popup(self, content, flags=0, location=-1, max_width=320, max_height=240):
        self.popup_visible = True
        self.popups.append({'content': content, 'location': location,
                            'max_width': max_width, 'max_height': max_height})
    def update_popup(self, content):
        self.updates.append(content)
    def is_popup_visible(self):
        return self.popup_visible
    def hide_popup(self):
        self.popup_visible = False


class _Window:
    def __init__(self): self._views = []
    def views(self): return self._views


_WINDOW = _Window()


def install():
    """Register the stubs as the `sublime` and `sublime_plugin` modules."""
    sys.modules['sublime'] = sys.modules[__name__]
    sp = types.ModuleType('sublime_plugin')
    sp.EventListener = type('EventListener', (), {})
    sp.TextCommand = type('TextCommand', (), {})
    sys.modules['sublime_plugin'] = sp
