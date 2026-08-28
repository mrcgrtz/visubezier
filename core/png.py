"""Minimal indexed-colour PNG encoder.

Sublime's minihtml renders PNG, JPG and GIF only, and the plugin host ships no
imaging library, so previews are encoded here by hand. Only what VisuBezier
needs is implemented: colour type 3 (palette), bit depth 8, no interlacing.
"""

import struct
import zlib


def _chunk(tag, payload):
    """Frame a payload as a PNG chunk: length, tag, data, CRC-32 of tag+data."""
    return (
        struct.pack('>I', len(payload))
        + tag
        + payload
        + struct.pack('>I', zlib.crc32(tag + payload) & 0xFFFFFFFF)
    )


def encode(pixels, width, height, palette, level=9):
    """Encode an indexed-colour image as PNG bytes.

    :param pixels: flat row-major bytearray of palette indices, len == w * h.
    :param width: image width in pixels.
    :param height: image height in pixels.
    :param palette: list of (r, g, b) tuples, at most 256 entries.
    :param level: zlib compression level. Animation frames are transient and
        favour latency over size, so they compress at a lower level.
    :returns: the complete PNG file as bytes.
    """
    if len(pixels) != width * height:
        raise ValueError('pixel buffer is %d bytes, expected %d' % (len(pixels), width * height))
    if len(palette) > 256:
        raise ValueError('palette holds %d entries, PNG allows 256' % len(palette))

    # Each scanline is prefixed with its filter type. The images are flat colour
    # over long runs, which DEFLATE already handles, so filter 0 (None) is used
    # throughout rather than paying to search for a better filter per row.
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        raw += pixels[y * width:(y + 1) * width]

    ihdr = struct.pack('>IIBBBBB', width, height, 8, 3, 0, 0, 0)
    plte = b''.join(struct.pack('BBB', *entry) for entry in palette)

    return (
        b'\x89PNG\r\n\x1a\n'
        + _chunk(b'IHDR', ihdr)
        + _chunk(b'PLTE', plte)
        + _chunk(b'IDAT', zlib.compress(bytes(raw), level))
        + _chunk(b'IEND', b'')
    )
