"""Plugin behaviour, driven against a stubbed Sublime Text API."""

import unittest

import context
import stub_sublime as stub

stub.install()

import sublime  # noqa: E402  (resolves to the stub)

DEFAULTS = context.load_settings_defaults()

SAMPLE = '''button {
	transition-timing-function: ease;
	transition-timing-function: cubic-bezier(0.4, -0.2, 0.42, 1.2);
	transition-timing-function: steps(5, jump-none);
	transition-timing-function: linear(0, 0.25 25% 75%, 1);
	transition-timing-function: ease, steps(3), cubic-bezier(1, 0, 0, 1);
}'''

EXPECTED = ['ease', 'cubic-bezier(0.4, -0.2, 0.42, 1.2)', 'steps(5, jump-none)',
            'linear(0, 0.25 25% 75%, 1)', 'ease', 'steps(3)', 'cubic-bezier(1, 0, 0, 1)']


class PluginTestCase(unittest.TestCase):
    """Resets plugin and stub state around each test."""

    def setUp(self):
        import importlib
        self.plugin = importlib.import_module('VisuBezier.visubezier')
        stub.SETTINGS.values = dict(DEFAULTS)
        del stub.deferred[:]
        del stub._WINDOW._views[:]
        self.plugin._cache.clear()
        del self.plugin._cache_order[:]
        self.plugin.plugin_loaded()
        stub.drain()

        self.view = stub.View(SAMPLE)
        stub._WINDOW._views.append(self.view)
        self.plugin._scan(self.view)
        self.listener = self.plugin.VisuBezierListener()

    def tearDown(self):
        self.plugin.plugin_unloaded()

    def regions(self):
        return self.view.get_regions(self.plugin.REGION_KEY)

    def texts(self):
        return [self.view.substr(region) for region in self.regions()]

    def hover(self, index, offset=1):
        point = self.regions()[index].begin() + offset
        self.listener.on_hover(self.view, point, sublime.HOVER_TEXT)
        stub.drain()
        return point


class ScanTest(PluginTestCase):
    def test_finds_the_easings_in_a_css_buffer(self):
        self.assertEqual(self.texts(), EXPECTED)

    def test_underlines_by_default(self):
        flags = self.view.region_flags[self.plugin.REGION_KEY]
        self.assertTrue(flags & sublime.DRAW_STIPPLED_UNDERLINE)
        self.assertEqual(self.view.region_scopes[self.plugin.REGION_KEY], 'region.bluish')

    def test_ignores_buffers_outside_the_configured_scopes(self):
        other = stub.View('a { transition: ease; }', scope='text.plain')
        self.plugin._scan(other)
        self.assertEqual(other.get_regions(self.plugin.REGION_KEY), [])

    def test_skips_buffers_over_the_size_limit(self):
        stub.SETTINGS.set('max_file_size', 10)
        self.plugin._scan(self.view)
        self.assertEqual(self.regions(), [])

    def test_empty_selector_list_disables_scanning(self):
        stub.SETTINGS.set('selectors', [])
        self.plugin._scan(self.view)
        self.assertEqual(self.regions(), [])

    def test_regions_survive_the_underline_being_switched_off(self):
        stub.SETTINGS.set('underline', False)
        self.plugin._scan(self.view)
        self.assertEqual(len(self.regions()), len(EXPECTED))
        self.assertTrue(self.view.region_flags[self.plugin.REGION_KEY] & sublime.HIDDEN)


class HoverTest(PluginTestCase):
    def test_shows_a_popup_with_an_animated_preview(self):
        self.hover(1)
        self.assertEqual(len(self.view.popups), 1)
        html = self.view.popups[-1]['content']
        self.assertIn('data:image/gif;base64,', html)
        self.assertIn('cubic-bezier(0.4, -0.2, 0.42, 1.2)', html)
        self.assertIn('>linear<', html)

    def test_pins_the_image_to_the_rendered_size(self):
        self.hover(0)
        self.assertIn('width="480" height="100"', self.view.popups[-1]['content'])

    def test_ignores_hovers_outside_the_text_area(self):
        self.listener.on_hover(self.view, self.regions()[0].begin(), sublime.HOVER_GUTTER)
        stub.drain()
        self.assertEqual(self.view.popups, [])

    def test_ignores_hovers_away_from_an_easing(self):
        self.listener.on_hover(self.view, 0, sublime.HOVER_TEXT)
        stub.drain()
        self.assertEqual(self.view.popups, [])

    def test_escapes_markup_in_the_reference_setting(self):
        stub.SETTINGS.set('reference_easing_function', '<b>&x')
        self.hover(0)
        html = self.view.popups[-1]['content']
        self.assertIn('&lt;b&gt;&amp;x', html)
        self.assertNotIn('<b>&x', html)

    def test_static_mode_serves_a_png(self):
        stub.SETTINGS.set('animate', False)
        self.hover(0)
        self.assertIn('data:image/png;base64,', self.view.popups[-1]['content'])


class CacheTest(PluginTestCase):
    def test_repeat_hover_reuses_the_cached_render(self):
        self.hover(1)
        calls = []
        real = self.plugin.render.render
        self.plugin.render.render = lambda *a, **k: calls.append(1) or real(*a, **k)
        try:
            self.hover(1)
            self.assertEqual(calls, [])
            self.hover(2)
            self.assertEqual(len(calls), 1)
        finally:
            self.plugin.render.render = real

    def test_changing_settings_clears_the_cache_and_rescans(self):
        self.hover(1)
        self.assertTrue(self.plugin._cache)
        stub.SETTINGS.set('foreground', '#ff0000')
        stub.SETTINGS.fire()
        stub.drain()
        self.assertEqual(len(self.plugin._cache), 0)
        self.assertEqual(len(self.regions()), len(EXPECTED))

    def test_cache_is_bounded(self):
        for index in range(self.plugin.CACHE_LIMIT + 5):
            self.plugin._cache_put(('key', index), 'value')
        self.assertEqual(len(self.plugin._cache), self.plugin.CACHE_LIMIT)


class ConcurrencyTest(PluginTestCase):
    def test_a_superseded_hover_does_not_pop_up(self):
        first = self.regions()[0].begin() + 1
        second = self.regions()[3].begin() + 1
        self.listener.on_hover(self.view, first, sublime.HOVER_TEXT)
        self.listener.on_hover(self.view, second, sublime.HOVER_TEXT)
        stub.drain()
        self.assertEqual(len(self.view.popups), 1)
        self.assertIn('linear(0, 0.25 25% 75%, 1)', self.view.popups[-1]['content'])

    def test_rapid_edits_collapse_into_a_single_rescan(self):
        scans = []
        real = self.plugin._scan
        self.plugin._scan = lambda view: scans.append(1) or real(view)
        try:
            for _ in range(5):
                self.listener.on_modified_async(self.view)
            stub.drain()
            self.assertEqual(len(scans), 1)
        finally:
            self.plugin._scan = real


if __name__ == '__main__':
    unittest.main()
