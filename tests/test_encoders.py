"""PNG and GIF encoding, verified against an external decoder where available."""

import os
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib

import context  # noqa: F401
from VisuBezier.core import gif, png, raster

MAGICK = shutil.which('magick') or shutil.which('convert')

PALETTE = [(i * 8, (i * 8 + 60) % 256, 255 - i * 8) for i in range(32)]


def pseudo_random_pixels(width, height):
    """A deterministic field mixing noise with flat runs, to exercise LZW."""
    pixels = bytearray(width * height)
    seed = 12345
    for i in range(width * height):
        seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
        pixels[i] = (seed >> 16) % 32 if (i // width) % 3 == 0 else (i // 37) % 32
    return pixels


class PngTest(unittest.TestCase):
    def test_structure_and_signature(self):
        data = png.encode(bytearray([0, 1, 1, 0]), 2, 2, [(0, 0, 0), (255, 255, 255)])
        self.assertTrue(data.startswith(b'\x89PNG\r\n\x1a\n'))
        for tag in (b'IHDR', b'PLTE', b'IDAT', b'IEND'):
            self.assertIn(tag, data)

    def test_chunk_crcs_are_valid(self):
        data = png.encode(pseudo_random_pixels(40, 10), 40, 10, PALETTE)
        offset = 8
        seen = []
        while offset < len(data):
            length = struct.unpack('>I', data[offset:offset + 4])[0]
            tag = data[offset + 4:offset + 8]
            payload = data[offset + 8:offset + 8 + length]
            stored = struct.unpack('>I', data[offset + 8 + length:offset + 12 + length])[0]
            self.assertEqual(stored, zlib.crc32(tag + payload) & 0xFFFFFFFF, tag)
            seen.append(tag)
            offset += 12 + length
        self.assertEqual(seen[0], b'IHDR')
        self.assertEqual(seen[-1], b'IEND')

    def test_rejects_mismatched_buffer(self):
        with self.assertRaises(ValueError):
            png.encode(bytearray(3), 2, 2, [(0, 0, 0)])


@unittest.skipUnless(MAGICK, 'ImageMagick not available')
class DecodeTest(unittest.TestCase):
    """Round-trips encoded images through ImageMagick and compares pixels."""

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix='visubezier-')

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def decode(self, name, data, frames=1, coalesce=False):
        source = os.path.join(self.directory, name)
        target = os.path.join(self.directory, 'out.rgb')
        with open(source, 'wb') as handle:
            handle.write(data)
        command = [MAGICK, source]
        if coalesce:
            command.append('-coalesce')
        command += ['-depth', '8', 'rgb:' + target]
        subprocess.run(command, check=True, capture_output=True)
        with open(target, 'rb') as handle:
            return handle.read()

    def assert_matches(self, raw, expected, palette, offset=0):
        for i, index in enumerate(expected):
            got = tuple(raw[offset + i * 3:offset + i * 3 + 3])
            self.assertEqual(got, palette[index], 'pixel %d' % i)

    def test_png_decodes_to_the_source_pixels(self):
        width, height = 60, 20
        pixels = pseudo_random_pixels(width, height)
        raw = self.decode('t.png', png.encode(pixels, width, height, PALETTE))
        self.assertEqual(len(raw), width * height * 3)
        self.assert_matches(raw, pixels, PALETTE)

    def test_gif_decodes_to_the_source_pixels(self):
        width, height = 480, 100
        pixels = pseudo_random_pixels(width, height)
        frame = {'pixels': pixels, 'x': 0, 'y': 0,
                 'width': width, 'height': height, 'delay': 4}
        raw = self.decode('t.gif', gif.encode([frame], width, height, PALETTE))
        self.assertEqual(len(raw), width * height * 3)
        self.assert_matches(raw, pixels, PALETTE)

    def test_partial_frames_composite_correctly(self):
        width, height = 60, 20
        canvases = []
        for step in range(5):
            canvas = bytearray((x // 7) % 32 for _ in range(height) for x in range(width))
            for y in range(6, 12):
                for x in range(step * 9, step * 9 + 6):
                    canvas[y * width + x] = 31
            canvases.append(canvas)

        frames = [{'pixels': canvases[0], 'x': 0, 'y': 0,
                   'width': width, 'height': height, 'delay': 5}]
        for step in range(1, 5):
            left, right = (step - 1) * 9, step * 9 + 6
            block = bytearray()
            for y in range(6, 12):
                block += canvases[step][y * width + left:y * width + right]
            frames.append({'pixels': block, 'x': left, 'y': 6,
                           'width': right - left, 'height': 6, 'delay': 5})

        raw = self.decode('a.gif', gif.encode(frames, width, height, PALETTE),
                          frames=5, coalesce=True)
        self.assertEqual(len(raw), width * height * 3 * 5)
        for step, canvas in enumerate(canvases):
            self.assert_matches(raw, canvas, PALETTE, offset=step * width * height * 3)


class GifStructureTest(unittest.TestCase):
    def test_header_and_trailer(self):
        frame = {'pixels': bytearray(4), 'x': 0, 'y': 0,
                 'width': 2, 'height': 2, 'delay': 4}
        data = gif.encode([frame], 2, 2, PALETTE)
        self.assertTrue(data.startswith(b'GIF89a'))
        self.assertTrue(data.endswith(b'\x3B'))
        self.assertIn(b'NETSCAPE2.0', data)

    def test_requires_at_least_one_frame(self):
        with self.assertRaises(ValueError):
            gif.encode([], 2, 2, PALETTE)

    def test_rejects_oversized_palette(self):
        with self.assertRaises(ValueError):
            gif.encode([{'pixels': bytearray(1), 'x': 0, 'y': 0,
                         'width': 1, 'height': 1, 'delay': 4}],
                       1, 1, [(0, 0, 0)] * 300)


class PaletteTest(unittest.TestCase):
    def test_ramp_spans_background_to_foreground(self):
        palette = raster.build_palette((0, 0, 0), (255, 255, 255))
        self.assertEqual(len(palette), raster.LEVELS)
        self.assertEqual(palette[0], (0, 0, 0))
        self.assertEqual(palette[-1], (255, 255, 255))

    def test_parses_hex_colours(self):
        self.assertEqual(raster.parse_color('#2d2d30'), (45, 45, 48))
        self.assertEqual(raster.parse_color('#fff'), (255, 255, 255))
        self.assertEqual(raster.parse_color('nonsense', (1, 2, 3)), (1, 2, 3))
        self.assertEqual(raster.parse_color(None, (1, 2, 3)), (1, 2, 3))


class CanvasTest(unittest.TestCase):
    def test_blend_takes_the_maximum_coverage(self):
        canvas = raster.Canvas(4, 4)
        canvas.blend(1, 1, 1.0)
        canvas.blend(1, 1, 0.2)
        self.assertEqual(canvas.pixels[1 * 4 + 1], raster.LEVELS - 1)

    def test_drawing_outside_the_canvas_is_clipped(self):
        canvas = raster.Canvas(4, 4)
        canvas.line(-50, -50, 50, 50, 1.0, 2.0)
        canvas.circle(100, 100, 5)
        self.assertEqual(len(canvas.pixels), 16)

    def test_sub_rect_extracts_the_requested_window(self):
        canvas = raster.Canvas(4, 4)
        canvas.pixels[:] = bytearray(range(16))
        self.assertEqual(bytes(canvas.sub_rect(1, 1, 2, 2)), bytes([5, 6, 9, 10]))


if __name__ == '__main__':
    unittest.main()
