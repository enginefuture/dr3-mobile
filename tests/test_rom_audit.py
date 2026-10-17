#!/usr/bin/env python3
"""Independent malformed-container controls for the read-only audit parser."""
from pathlib import Path
import struct
import sys
from types import SimpleNamespace as NS
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from rom_audit import MachO, checked_slice, validate_archive


def fixture():
    d = bytearray(0x2000)
    base = 0x100000000
    text = struct.pack('<II16sQQQQiiII', 0x19, 72, b'__TEXT', base, 0x1000, 0, 0x1000, 7, 5, 0, 0)
    data = struct.pack('<II16sQQQQiiII', 0x19, 152, b'__DATA', base + 0x1000, 0x1000, 0x1000, 0x1000, 7, 3, 1, 0)
    section = struct.pack('<16s16sQQIIIIIIII', b'swhle', b'__DATA', base + 0x1000, 16, 0x1000, 3, 0, 0, 0, 0, 0, 0)
    fixcmd = struct.pack('<4I', 0x80000034, 16, 0x800, 100)
    cmds = text + data + section + fixcmd
    d[:32] = struct.pack('<8I', 0xfeedfacf, 0x100000c, 0, 2, 3, len(cmds), 0, 0)
    d[32:32 + len(cmds)] = cmds
    d[0x300:0x304] = b'foo\0'
    # No import binds; one pointer chain on the data page, stride 4, slots 0 and 8.
    d[0x800:0x81c] = struct.pack('<7I', 0, 28, 90, 90, 0, 1, 0)
    d[0x81c:0x828] = struct.pack('<3I', 2, 0, 12)
    d[0x828:0x840] = struct.pack('<IHHQIH', 24, 4096, 6, 0x1000, 0, 1) + struct.pack('<H', 0)
    struct.pack_into('<Q', d, 0x1000, 0x300 | (2 << 51))
    struct.pack_into('<Q', d, 0x1008, 0x400)
    return d


class MachOControls(unittest.TestCase):
    def test_positive_real_pointer_chain(self):
        m = MachO(fixture())
        self.assertEqual(m.registry('swhle', 16), [{'name': 'foo'}])
        self.assertEqual(m.pointer_formats, {6})

    def test_negative_layouts(self):
        mutations = [
            (0, '<I', 0xcafebabe),       # fat/foreign magic
            (4, '<I', 7),                # wrong CPU
            (20, '<I', 0xfffffff8),      # oversized commands
            (36, '<I', 0),               # zero-sized command
            (0x81c, '<I', 3),            # fixup segment count mismatch
            (0x82e, '<H', 2),            # wrong chained pointer format
            (0x830, '<Q', 0x2000),       # wrong segment virtual offset
            (0x83e, '<H', 4094),         # pointer straddles page
            (0x83e, '<H', 0x8000),       # unsupported multi-start page
            (0x800, '<I', 1),            # unsupported fixups version
        ]
        for off, fmt, value in mutations:
            with self.subTest(offset=hex(off), value=value):
                d = fixture(); struct.pack_into(fmt, d, off, value)
                with self.assertRaises(ValueError):
                    MachO(d)

    def test_negative_registry_pointers(self):
        for off, word in [(0x1000, (1 << 63) | (2 << 51)), # name bind forbidden
                          (0x1000, 0x3000 | (2 << 51)),  # target outside VM
                          (0x1008, 1 << 63)]:           # invalid import ordinal
            with self.subTest(offset=hex(off), word=word):
                d = fixture(); struct.pack_into('<Q', d, off, word)
                with self.assertRaises(ValueError):
                    MachO(d).registry('swhle', 16)

    def test_negative_registry_missing_chain(self):
        d = fixture(); struct.pack_into('<Q', d, 0x1000, 0x300)
        with self.assertRaisesRegex(ValueError, 'missing fixup'):
            MachO(d).registry('swhle', 16)

    def test_negative_registry_alignment(self):
        with self.assertRaisesRegex(ValueError, 'Misaligned'):
            MachO(fixture()).registry('swhle', 24)

    def test_negative_string_boundary(self):
        d = fixture(); d[0x900:0x1000] = b'x' * 0x700
        struct.pack_into('<Q', d, 0x1000, 0x900 | (2 << 51))
        with self.assertRaisesRegex(ValueError, 'Unterminated'):
            MachO(d).registry('swhle', 16)

    def test_slice_rejects_negative_and_overflow(self):
        for off, size in [(-1, 1), (0, -1), (3, 2), (1 << 64, 1)]:
            with self.assertRaises(ValueError):
                checked_slice(b'abcd', off, size, 'test')


class CPKControls(unittest.TestCase):
    def archive(self):
        return NS(header=NS(file_count=1, loc_count=1, decomp_fs=100), _first_sec=10,
                  _cs2do=[0, 50], entries=[NS(name='Appearance\\lamp.app', loc_count=1, loc_idx=0, offset=90, size=10)])

    def test_positive_exact_extent_end(self):
        validate_archive(self.archive(), 100)

    def test_negative_archive_controls(self):
        mutations = [lambda a: setattr(a.header, 'file_count', 2),
                     lambda a: setattr(a, '_first_sec', 101),
                     lambda a: setattr(a, '_cs2do', []),
                     lambda a: setattr(a, '_cs2do', [50, 0]),
                     lambda a: setattr(a, '_cs2do', [0, 101]),
                     lambda a: setattr(a.entries[0], 'size', 11),
                     lambda a: setattr(a.entries[0], 'offset', -1),
                     lambda a: setattr(a.entries[0], 'loc_idx', 1),
                     lambda a: setattr(a.entries[0], 'loc_count', 2),
                     lambda a: setattr(a.entries[0], 'name', '..\\lamp.app'),
                     lambda a: setattr(a.entries[0], 'name', 'C:lamp.app'),
                     lambda a: setattr(a.entries[0], 'name', '\\lamp.app'),
                     lambda a: setattr(a.entries[0], 'name', '')]
        for index, mutate in enumerate(mutations):
            with self.subTest(control=index):
                a = self.archive(); mutate(a)
                with self.assertRaises(ValueError):
                    validate_archive(a, 100)

if __name__ == '__main__':
    unittest.main()
