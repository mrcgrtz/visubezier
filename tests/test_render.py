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

    def test_every_supported_easing_renders_a_gif(self):
        for expression in self.EXPRESSIONS:
            result = render.render(expression)
            self.assertIsNotNone(result, expression)
            data, mime = result
            self.assertEqual(mime, 'image/gif', expression)
            self.assertTrue(data.startswith(b'GIF89a'), expression)

    def test_static_mode_renders_a_png(self):
        data, mime = render.render('ease', animate=False)
        self.assertEqual(mime, 'image/png')
        self.assertTrue(data.startswith(b'\x89PNG\r\n\x1a\n'))

    def test_static_output_is_far_smaller_than_animated(self):
        static, _ = render.render('ease', animate=False)
        animated, _ = render.render('ease', animate=True)
        self.assertLess(len(static), len(animated))

    def test_unparseable_expression_renders_nothing(self):
        self.assertIsNone(render.render('wobble'))
        self.assertIsNone(render.render('cubic-bezier(1,2)'))

    def test_unparseable_reference_falls_back_rather_than_failing(self):
        result = render.render('ease', reference='wobble')
        self.assertIsNotNone(result)

    def test_duration_drives_frame_count(self):
        short, _ = render.render('ease', duration='0.2s')
        long, _ = render.render('ease', duration='2s')
        self.assertLess(len(short), len(long))

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
        default, _ = render.render('ease')
        recoloured, _ = render.render('ease', background='#000000', foreground='#ff0000')
        self.assertNotEqual(default, recoloured)

    def test_data_uri_is_well_formed(self):
        data, mime = render.render('ease', animate=False)
        uri = render.data_uri(data, mime)
        self.assertTrue(uri.startswith('data:image/png;base64,'))
        import base64
        self.assertEqual(base64.b64decode(uri.split(',', 1)[1]), data)


if __name__ == '__main__':
    unittest.main()
