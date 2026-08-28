"""Locating easing functions in document text."""

import unittest

import context  # noqa: F401
from VisuBezier.core import detect, easing

SAMPLE = '''button {
	transition-timing-function: ease;
	transition-timing-function: ease-in;
	transition-timing-function: ease-out;
	transition-timing-function: ease-in-out;
	transition-timing-function: cubic-bezier(0.4, -0.2, 0.42, 1.2);
	transition-timing-function: steps(7);
	transition-timing-function: steps(5, jump-none);
	transition-timing-function: steps(8, jump-both);
	transition-timing-function: steps(4, jump-start);
	transition-timing-function: steps(2, jump-end);
	transition-timing-function: step-start;
	transition-timing-function: step-end;
	transition-timing-function: linear(0, 0.25 25% 75%, 1);
	transition-timing-function: ease, steps(3), cubic-bezier(1, 0, 0, 1), linear(0 0%, -0.25, 1.25, 1 100%);
}'''


class DetectionTest(unittest.TestCase):
    def test_finds_every_easing_in_the_readme_sample(self):
        found = detect.find_easings(SAMPLE)
        self.assertEqual(len(found), 17)

    def test_offsets_delimit_the_easing_exactly(self):
        for start, end, expression in detect.find_easings(SAMPLE):
            self.assertEqual(SAMPLE[start:end], expression)

    def test_everything_found_is_parseable(self):
        for _, _, expression in detect.find_easings(SAMPLE):
            self.assertIsNotNone(easing.parse(expression), expression)

    def test_ignores_identifiers_that_merely_contain_a_keyword(self):
        text = ('a { --my-ease: 1; } .release { x: ease-out-quad; } '
                'b { c: nonlinear; } d { e: teaser; }')
        self.assertEqual(detect.find_easings(text), [])

    def test_finds_adjacent_easings(self):
        # The delimiters are zero-width, so a shared comma does not hide the
        # second easing the way a consuming match would.
        self.assertEqual([e for _, _, e in detect.find_easings('a: ease,ease;')],
                         ['ease', 'ease'])

    def test_finds_easings_in_quoted_and_shorthand_contexts(self):
        cases = {
            'x: "ease-in";': ['ease-in'],
            "y: 'steps(4)';": ['steps(4)'],
            'animation: 1s ease-in-out infinite;': ['ease-in-out'],
            'a: cubic-bezier(.42,0,.58,1);': ['cubic-bezier(.42,0,.58,1)'],
            'z: linear(0, 1);': ['linear(0, 1)'],
        }
        for text, expected in cases.items():
            self.assertEqual([e for _, _, e in detect.find_easings(text)], expected, text)

    def test_rejects_out_of_range_bezier_coordinates(self):
        # x is confined to [0, 1]; y is not.
        self.assertEqual(detect.find_easings('a: cubic-bezier(9,9,9,9);'), [])
        self.assertEqual([e for _, _, e in detect.find_easings('a: cubic-bezier(0,9,1,-9);')],
                         ['cubic-bezier(0,9,1,-9)'])

    def test_does_not_match_empty_arguments(self):
        for text in ['a: cubic-bezier(,,,);', 'a: steps();', 'a: linear();']:
            self.assertEqual(detect.find_easings(text), [], text)


if __name__ == '__main__':
    unittest.main()
