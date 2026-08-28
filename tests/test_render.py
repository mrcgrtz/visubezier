"""Preview composition."""

import unittest

import context  # noqa: F401
from VisuBezier.core import render


class DurationTest(unittest.TestCase):
    def test_parses_seconds_and_milliseconds(self):
        self.assertAlmostEqual(render.parse_duration('1s'), 1.0)
        self.assertAlmostEqual(render.parse_duration('0.5s'), 0.5)
        self.assertAlmostEqual(render.parse_duration('500ms'), 0.5)
        self.assertAlmostEqual(render.parse_duration(' 250MS '), 0.25)

    def test_falls_back_on_nonsense(self):
        for text in ('', 'soon', '5', '1 s x', None, 0, '-1s', '0s'):
            self.assertAlmostEqual(render.parse_duration(text, 1.0), 1.0, msg=repr(text))


class RenderTest(unittest.TestCase):
    EXPRESSIONS = [
        'ease', 'ease-in-out', 'linear',
        'cubic-bezier(0.4, -0.2, 0.42, 1.2)',
        'steps(7)', 'steps(5, jump-none)', 'steps(4, jump-start)',
        'steps(8, jump-both)', 'step-start', 'step-end',
        'linear(0, 0.25 25% 75%, 1)',
        'linear(0 0%, -0.25, 1.25, 1 100%)',
    ]

    def test_every_supported_easing_renders_frames(self):
        for expression in self.EXPRESSIONS:
            result = render.build(expression)
            self.assertIsNotNone(result, expression)
            self.assertEqual(result['mime'], 'image/png', expression)
            self.assertGreater(len(result['frames']), 1, expression)
            for frame in result['frames']:
                self.assertTrue(frame.startswith(b'\x89PNG\r\n\x1a\n'), expression)

    def test_frames_differ_from_one_another(self):
        # A sequence of identical stills would animate into nothing.
        frames = render.build('ease-in-out')['frames']
        self.assertGreater(len(set(frames)), len(frames) // 2)

    def test_animation_has_a_usable_frame_delay(self):
        result = render.build('ease', duration='1s')
        self.assertGreaterEqual(result['delay_ms'], 20)
        self.assertLessEqual(result['delay_ms'] * len(result['frames']), 4000)

    def test_static_mode_renders_one_frame(self):
        result = render.build('ease', animate=False)
        self.assertEqual(result['mime'], 'image/png')
        self.assertEqual(len(result['frames']), 1)
        self.assertEqual(result['delay_ms'], 0)
        self.assertTrue(result['frames'][0].startswith(b'\x89PNG\r\n\x1a\n'))

    def test_static_output_is_far_smaller_than_animated(self):
        static = sum(len(f) for f in render.build('ease', animate=False)['frames'])
        animated = sum(len(f) for f in render.build('ease', animate=True)['frames'])
        self.assertLess(static, animated)

    def test_unparseable_expression_renders_nothing(self):
        self.assertIsNone(render.build('wobble'))
        self.assertIsNone(render.build('cubic-bezier(1,2)'))

    def test_unparseable_reference_falls_back_rather_than_failing(self):
        self.assertIsNotNone(render.build('ease', reference='wobble'))

    def test_duration_drives_frame_count(self):
        short = render.build('ease', duration='0.2s')['frames']
        long = render.build('ease', duration='2s')['frames']
        self.assertLess(len(short), len(long))

    def test_gif_export_still_works_for_the_readme_asset(self):
        data = render.render_gif('ease-in-out')
        self.assertTrue(data.startswith(b'GIF89a'))
        self.assertIsNone(render.render_gif('wobble'))

    def test_frame_geometry_is_clamped(self):
        for duration, expected in ((0.01, render.MIN_FORWARD_FRAMES),
                                   (100.0, render.MAX_FORWARD_FRAMES)):
            frames, delay = render._frame_geometry(duration)
            self.assertEqual(frames, expected)
            self.assertGreaterEqual(delay, 2)

    def test_overshoot_stays_inside_the_track(self):
        # The known issue in the VS Code extension was squares escaping the
        # preview area; positions are clamped to the track instead.
        for value in (-5.0, -0.5, 0.0, 0.5, 1.0, 1.5, 5.0):
            x = render._square_x(value)
            self.assertGreaterEqual(x, 0.0)
            self.assertLessEqual(x + render.SQUARE_SIZE, render.TRACK_WIDTH)

    def test_colour_settings_change_the_output(self):
        default = render.build('ease')['frames']
        recoloured = render.build('ease', background='#000000',
                                  foreground='#ff0000')['frames']
        self.assertNotEqual(default, recoloured)

    def test_data_uri_is_well_formed(self):
        result = render.build('ease', animate=False)
        data, mime = result['frames'][0], result['mime']
        uri = render.data_uri(data, mime)
        self.assertTrue(uri.startswith('data:image/png;base64,'))
        import base64
        self.assertEqual(base64.b64decode(uri.split(',', 1)[1]), data)


if __name__ == '__main__':
    unittest.main()
