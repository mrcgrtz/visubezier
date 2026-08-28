"""Minimal animated GIF89a encoder.

minihtml cannot run CSS animations, so the easing comparison is baked into a
looping GIF instead. Only the subset VisuBezier needs is implemented: a single
global colour table, no transparency, and frames that may cover a sub-rectangle
of the canvas so that unchanged pixels are not re-encoded.
"""

import struct

MAX_CODE = 4096

# Leave already-painted pixels alone when moving to the next frame. Combined
# with sub-rectangle frames this lets each frame ship only its dirty region.
DISPOSAL_NONE = 1


class _BitWriter:
    """Packs variable-width LZW codes least-significant-bit first, as GIF requires."""

    def __init__(self):
        self.bytes = bytearray()
        self._acc = 0
        self._bits = 0

    def write(self, code, width):
        self._acc |= code << self._bits
        self._bits += width
        while self._bits >= 8:
            self.bytes.append(self._acc & 0xFF)
            self._acc >>= 8
            self._bits -= 8

    def flush(self):
        if self._bits > 0:
            self.bytes.append(self._acc & 0xFF)
            self._acc = 0
            self._bits = 0


def _lzw_compress(indices, min_code_size):
    """LZW-compress a run of palette indices into a GIF image data stream."""
    clear_code = 1 << min_code_size
    end_code = clear_code + 1

    def fresh_table():
        return {(i,): i for i in range(clear_code)}

    table = fresh_table()
    next_code = end_code + 1
    code_size = min_code_size + 1

    out = _BitWriter()
    out.write(clear_code, code_size)

    prefix = ()
    for index in indices:
        candidate = prefix + (index,)
        if candidate in table:
            prefix = candidate
            continue

        out.write(table[prefix], code_size)
        if next_code < MAX_CODE:
            table[candidate] = next_code
            next_code += 1
            # Widen only once the highest assigned code no longer fits. The
            # decoder builds its table one entry behind the encoder, so a
            # stricter test here desynchronises the two and corrupts the stream.
            if next_code > (1 << code_size) and code_size < 12:
                code_size += 1
        else:
            out.write(clear_code, code_size)
            table = fresh_table()
            next_code = end_code + 1
            code_size = min_code_size + 1
        prefix = (index,)

    if prefix:
        out.write(table[prefix], code_size)
    out.write(end_code, code_size)
    out.flush()

    return bytes(out.bytes)


def _sub_blocks(payload):
    """Split a byte string into the length-prefixed sub-blocks GIF streams use."""
    out = bytearray()
    for start in range(0, len(payload), 255):
        block = payload[start:start + 255]
        out.append(len(block))
        out += block
    out.append(0)
    return bytes(out)


def _table_bits(palette_size):
    """Smallest colour-table exponent that can address the palette (GIF floors it at 2)."""
    bits = 2
    while (1 << bits) < palette_size:
        bits += 1
    if bits > 8:
        raise ValueError('palette holds %d entries, GIF allows 256' % palette_size)
    return bits


def encode(frames, width, height, palette, loop=0):
    """Encode a looping animated GIF.

    :param frames: list of dicts with keys ``pixels`` (flat bytearray of palette
        indices for the frame's own rect), ``x``, ``y``, ``width``, ``height``
        and ``delay`` (hundredths of a second).
    :param width: logical screen width.
    :param height: logical screen height.
    :param palette: list of (r, g, b) tuples.
    :param loop: repeat count; 0 means forever.
    :returns: the complete GIF file as bytes.
    """
    if not frames:
        raise ValueError('an animation needs at least one frame')

    bits = _table_bits(len(palette))
    table_size = 1 << bits

    out = bytearray(b'GIF89a')

    # Logical screen descriptor: global colour table present, 8-bit colour
    # resolution, unsorted, sized 2**(bits).
    packed = 0x80 | ((8 - 1) << 4) | (bits - 1)
    out += struct.pack('<HHBBB', width, height, packed, 0, 0)

    for entry in palette:
        out += struct.pack('BBB', *entry)
    for _ in range(table_size - len(palette)):
        out += b'\x00\x00\x00'

    # NETSCAPE2.0 application extension: the de facto way to request looping.
    out += b'\x21\xFF\x0BNETSCAPE2.0\x03\x01' + struct.pack('<H', loop) + b'\x00'

    min_code_size = max(2, bits)
    for frame in frames:
        out += b'\x21\xF9\x04' + struct.pack(
            '<BHBB', DISPOSAL_NONE << 2, frame['delay'], 0, 0
        )
        # Image descriptor: no local colour table, not interlaced.
        out += b'\x2C' + struct.pack(
            '<HHHHB', frame['x'], frame['y'], frame['width'], frame['height'], 0
        )
        out += bytes([min_code_size])
        out += _sub_blocks(_lzw_compress(frame['pixels'], min_code_size))

    out += b'\x3B'
    return bytes(out)
