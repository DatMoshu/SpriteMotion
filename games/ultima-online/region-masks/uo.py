"""Read-only classic MUL animation decoding, with explicit source identities."""
import hashlib
import os
import re
import struct
from pathlib import Path
from PIL import Image


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def client_source(path=None):
    """The UO client folder: an explicit path, else SPRITEMOTION_UO_SOURCE."""
    path = path or os.environ.get('SPRITEMOTION_UO_SOURCE')
    if not path:
        raise SystemExit('Set SPRITEMOTION_UO_SOURCE to your UO client folder (or pass --source).')
    return path


class UOReader:
    def __init__(self, directory):
        self.root = Path(directory)
        self.idx = (self.root / 'anim.idx').read_bytes()
        self.mul = (self.root / 'anim.mul').open('rb')
        self.equip = {}
        for line in (self.root / 'Equipconv.def').read_text(errors='replace').splitlines():
            values = line.split('#')[0].split()
            if len(values) >= 5 and all(re.fullmatch(r'-?\d+', x) for x in values[:5]):
                body, original, converted, gump, hue = map(int, values[:5])
                self.equip[body, original] = (converted, hue)
        self.unsupported = set()
        self.conv = {}          # body -> (anim file number 2..5, body id inside that file), from Bodyconv.def
        self._files = {}
        for filename in ['Body.def', 'Bodyconv.def']:
            for line in (self.root / filename).read_text(errors='replace').splitlines():
                values = line.split('#')[0].split()
                if values and values[0].isdigit():
                    if filename == 'Body.def':
                        self.unsupported.add(int(values[0]))
                        continue
                    targets = [(n, int(x)) for n, x in zip((2, 3, 4, 5), values[1:5]) if x.lstrip('-').isdigit() and int(x) >= 0]
                    if targets and (self.root / f'anim{targets[0][0]}.idx').exists():
                        self.conv[int(values[0])] = targets[0]
                    elif targets:                          # remapped into an animN.mul this client lacks
                        self.unsupported.add(int(values[0]))
        self.tiledata = (self.root / 'tiledata.mul').read_bytes()
        if len(self.tiledata) != 3188736:
            raise ValueError('This exporter currently expects the 64-bit tiledata format (3188736 bytes).')

    def item(self, graphic):
        p = 512 * (4 + 32 * 30) + (graphic // 32) * (4 + 32 * 41) + 4 + (graphic % 32) * 41
        return {'graphic': graphic, 'animId': struct.unpack_from('<H', self.tiledata, p+14)[0],
                'layer': self.tiledata[p+9], 'label': self.tiledata[p+21:p+41].split(b'\0')[0].decode('cp1252')}

    def _file(self, n):
        if n not in self._files:
            self._files[n] = ((self.root / f'anim{n}.idx').read_bytes(), (self.root / f'anim{n}.mul').open('rb'))
        return self._files[n]

    @staticmethod
    def _base(n, body):
        """First idx record of a body inside animN (UOFiddler layouts)."""
        if n == 3:
            return body*65 if body < 300 else 33000+(body-300)*110 if body < 400 else 35000+(body-400)*175
        if n == 2:
            return body*110 if body < 200 else 22000+(body-200)*65
        return body*110 if body < 200 else 22000+(body-200)*65 if body < 400 else 35000+(body-400)*175

    def sequence(self, body, action, direction):
        if body in self.unsupported:
            raise ValueError(f'Animation {body} requires a DEF remapping not supported by this classic-only export')
        idx, mul = self.idx, self.mul
        if body in self.conv:                      # Bodyconv.def: this body lives in anim2..5.mul
            n, target = self.conv[body]
            idx, mul = self._file(n)
            record = self._base(n, target) + action*5 + direction
        else:
            if body < 400:
                raise ValueError('Only human/equipment animation IDs >= 400 are supported')
            record = 35000 + (body-400)*175 + action*5 + direction
        if record*12+12 > len(idx):
            return []
        offset, length, _ = struct.unpack_from('<iii', idx, record*12)
        if offset < 0 or length <= 0:
            return []
        mul.seek(offset)
        data = mul.read(length)
        if len(data) != length or length < 516:
            raise ValueError('Truncated animation record')
        palette = struct.unpack_from('<256H', data)
        count = struct.unpack_from('<I', data, 512)[0]
        if not 0 < count < 1000 or 516+count*4 > length:
            raise ValueError('Invalid frame table')
        result = []
        for i in range(count):
            p = 512 + struct.unpack_from('<I', data, 516+i*4)[0]
            cx, cy, w, h = struct.unpack_from('<hhhh', data, p); p += 8
            if w == 0 or h == 0:
                result.append({'image': Image.new('RGBA', (1,1)), 'center': [cx,cy], 'index': i,
                               'direction': direction, 'sourceRecord': record, 'empty': True})
                continue
            if not 0 < w <= 512 or not 0 < h <= 512:
                raise ValueError('Invalid frame dimensions')
            pixels = bytearray(w*h*4)
            while True:
                header = struct.unpack_from('<I', data, p)[0]; p += 4
                if header == 0x7fff7fff:
                    break
                run = header & 4095; x = (header >> 22) & 1023; y = (header >> 12) & 1023
                x = (x-1024 if x & 512 else x)+cx
                y = (y-1024 if y & 512 else y)+cy+h
                if not (0 <= x and x+run <= w and 0 <= y < h and p+run <= length):
                    raise ValueError('Animation run outside frame')
                for k in range(run):
                    v = palette[data[p+k]]
                    rgb = [(v >> 10) & 31, (v >> 5) & 31, v & 31]
                    at = (y*w+x+k)*4
                    pixels[at:at+4] = bytes([(v << 3) | (v >> 2) for v in rgb]+[255])
                p += run
            result.append({'image': Image.frombytes('RGBA', (w,h), bytes(pixels)), 'center': [cx,cy],
                           'index': i, 'direction': direction, 'sourceRecord': record,
                           'sourceRgbaSha256': sha256(pixels)})
        return result

    def close(self):
        self.mul.close()
        for _, handle in self._files.values():
            handle.close()
