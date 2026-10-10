"""Write the canonical model's embedded RGBA frames as a portable PNG atlas (stdlib only)."""
import base64
import json
import struct
import zlib


def write_reference(document, directory):
    width, height = document['tile']
    if (width, height) != (136, 120):
        raise ValueError('Expected native 136 x 120 original frames')
    keys = sorted(document['frames'], key=lambda key: tuple(map(int, key.split(','))))
    cols = 35
    rows = (len(keys) + cols - 1) // cols
    pixels = bytearray(cols * width * rows * height * 4)
    tiles = {}
    stride = cols * width * 4
    for i, key in enumerate(keys):
        x, y = i % cols, i // cols
        raw = zlib.decompress(base64.b64decode(document['frames'][key]))
        if len(raw) != width * height * 4:
            raise ValueError('Invalid original frame: ' + key)
        tiles[key] = [x, y]
        for line in range(height):
            offset = (y * height + line) * stride + x * width * 4
            pixels[offset:offset + width * 4] = raw[line * width * 4:(line + 1) * width * 4]
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    scanlines = b''.join(b'\0' + pixels[i:i + stride] for i in range(0, len(pixels), stride))
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', cols * width, rows * height, 8, 6, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(scanlines)) + chunk(b'IEND', b'')
    (directory / 'reference.png').write_bytes(png)
    (directory / 'reference.json').write_text(json.dumps({'image': 'reference.png', 'tile': [width, height], 'tiles': tiles}), encoding='utf-8')
