"""Parsing and evaluation of easing functions."""

import unittest

import context  # noqa: F401  (registers the VisuBezier package)
from VisuBezier.core import easing


class KeywordTest(unittest.TestCase):
    def test_linear_is_the_identity(self):
        fn = easing.parse('linear')
        for x in (0.0, 0.25, 0.5, 0.75, 1.0):
            self.assertAlmostEqual(fn.at(x), x, places=4)

    def test_ease_in_out_is_symmetric(self):
        fn = easing.parse('ease-in-out')
        self.assertAlmostEqual(fn.at(0.5), 0.5, places=4)
        self.assertAlmostEqual(fn.at(0.3) + fn.at(0.7), 1.0, places=4)

    def test_ease_in_lags_and_ease_out_leads(self):
        self.assertLess(easing.parse('ease-in').at(0.5), 0.5)
        self.assertGreater(easing.parse('ease-out').at(0.5), 0.5)

    def test_endpoints_are_pinned(self):
        for keyword in ('ease', 'ease-in', 'ease-out', 'ease-in-out', 'linear'):
            fn = easing.parse(keyword)
            self.assertAlmostEqual(fn.at(0.0), 0.0, places=6)
            self.assertAlmostEqual(fn.at(1.0), 1.0, places=6)

    def test_case_and_whitespace_are_insignificant(self):
        self.assertIsNotNone(easing.parse('  EASE-IN-OUT  '))
        self.assertIsNotNone(easing.parse('CUBIC-BEZIER(0.1, 0.2, 0.3, 0.4)'))


class CubicBezierTest(unittest.TestCase):
    def test_solver_round_trips_x(self):
        for points in [(0.4, -0.2, 0.42, 1.2), (1, 0, 0, 1),
                       (0.25, 0.1, 0.25, 1), (0, 0, 0.58, 1)]:
            curve = easing.CubicBezier(*points)
            for step in range(101):
                x = step / 100
                self.assertAlmostEqual(curve._sample_x(curve._solve_t(x)), x, places=5)

    def test_overshoot_is_preserved(self):
        fn = easing.parse('cubic-bezier(0.4, -0.2, 0.42, 1.2)')
        values = [fn.at(i / 40) for i in range(41)]
        self.assertLess(min(values), 0.0)
        self.assertGreater(max(values), 1.0)

    def test_reports_its_handles(self):
        fn = easing.parse('cubic-bezier(0.1, 0.2, 0.3, 0.4)')
        self.assertEqual(fn.handles(), [(0.1, 0.2), (0.3, 0.4)])


class StepsTest(unittest.TestCase):
    CASES = {
        'steps(4)': [(0, 0), (0.1, 0), (0.3, 0.25), (0.6, 0.5), (0.9, 0.75), (1, 1)],
        'steps(4, jump-start)': [(0, 0.25), (0.3, 0.5), (0.6, 0.75), (0.9, 1), (1, 1)],
        'steps(4, jump-both)': [(0, 0.2), (0.3, 0.4), (0.6, 0.6), (0.9, 0.8), (1, 1)],
        'steps(5, jump-none)': [(0, 0), (0.3, 0.25), (0.5, 0.5), (0.9, 1), (1, 1)],
        'steps(4, start)': [(0, 0.25), (0.9, 1)],
        'steps(4, end)': [(0, 0), (0.9, 0.75)],
        'step-start': [(0, 1), (0.5, 1), (1, 1)],
        'step-end': [(0, 0), (0.5, 0), (1, 1)],
    }

    def test_jumpterm_values(self):
        for expression, table in self.CASES.items():
            fn = easing.parse(expression)
            self.assertIsNotNone(fn, expression)
            for x, expected in table:
                self.assertAlmostEqual(
                    fn.at(x), expected, places=6,
                    msg='%s at %s' % (expression, x),
                )

    def test_staircase_reaches_both_corners(self):
        for expression in self.CASES:
            points = easing.parse(expression).points()
            self.assertAlmostEqual(points[0][0], 0.0, places=6, msg=expression)
            self.assertEqual(points[-1], (1.0, 1.0), msg=expression)


class LinearTest(unittest.TestCase):
    def test_explicit_positions(self):
        fn = easing.parse('linear(0, 0.25 25% 75%, 1)')
        self.assertEqual(
            [(round(p, 4), round(v, 4)) for p, v in fn.stops],
            [(0.0, 0.0), (0.25, 0.25), (0.75, 0.25), (1.0, 1.0)],
        )
        for x, expected in [(0, 0), (0.125, 0.125), (0.25, 0.25),
                            (0.5, 0.25), (0.75, 0.25), (1, 1)]:
            self.assertAlmostEqual(fn.at(x), expected, places=4)

    def test_implicit_positions_spread_evenly(self):
        fn = easing.parse('linear(0, 0.5, 1)')
        self.assertEqual([round(p, 4) for p, _ in fn.stops], [0.0, 0.5, 1.0])

    def test_overshoot_is_preserved(self):
        fn = easing.parse('linear(0 0%, -0.25, 1.25, 1 100%)')
        values = [fn.at(i / 40) for i in range(41)]
        self.assertLess(min(values), 0.0)
        self.assertGreater(max(values), 1.0)

    def test_positions_never_run_backwards(self):
        fn = easing.parse('linear(0, 1 80%, 0.5 20%, 1)')
        positions = [p for p, _ in fn.stops]
        self.assertEqual(positions, sorted(positions))

    def test_bounce_sample_from_the_readme(self):
        fn = easing.parse(
            'linear(0, 0.063, 0.25, 0.563, 1 36.4%, 0.812, 0.75, 0.813, 1 72.7%, '
            '0.953, 0.938, 0.953, 1 90.9%, 0.984, 1 100% 100%)'
        )
        self.assertIsNotNone(fn)
        positions = [p for p, _ in fn.stops]
        self.assertEqual(positions, sorted(positions))
        self.assertAlmostEqual(fn.at(0.0), 0.0, places=4)
        self.assertAlmostEqual(fn.at(1.0), 1.0, places=4)


class RejectionTest(unittest.TestCase):
    GARBAGE = ['', 'wobble', 'cubic-bezier(0,0,1)', 'cubic-bezier(a,b,c,d)',
               'steps(0)', 'steps(3, sideways)', 'steps(1, jump-none)',
               'linear()', 'linear(0 abc, 1)', 'cubic-bezier(var(--x),0,1,1)']

    def test_unparseable_input_returns_none(self):
        for expression in self.GARBAGE:
            self.assertIsNone(easing.parse(expression), expression)


if __name__ == '__main__':
    unittest.main()
