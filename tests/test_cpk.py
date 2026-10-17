import struct
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
import zlib
import random

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from cpk_shaders import StrictReader, decrypt


class CpkBoundaries(unittest.TestCase):
    def reader(self, payload, damaged=False, partial=False):
        if partial:
            compressor = zlib.compressobj()
            chunk = compressor.compress(payload) + compressor.flush(zlib.Z_SYNC_FLUSH)
        else:
            chunk = zlib.compress(payload)
        if damaged:
            chunk = b'XX' + chunk[2:]
        data = struct.pack('<HHH', len(payload) & 0xffff, len(payload) >> 16, len(chunk)) + chunk
        reader = StrictReader.__new__(StrictReader)
        reader.mapping = data + bytes(16384 - len(data))
        reader.archive = SimpleNamespace(header=SimpleNamespace(comp_sector=16384, fmt_const=2),
                                         _cs2do=[0], _first_sec=0, path='synthetic')
        return reader

    def test_sector_zero_keeps_first_real_chunk(self):
        payload = b'first shader payload' * 100
        reader = self.reader(payload)
        self.assertEqual(reader.sector(0), payload)
        reader.sector.cache_clear()

    def test_sync_flush_fragment_requires_exact_output_size(self):
        payload = b'fragment payload' * 100
        reader = self.reader(payload, partial=True)
        self.assertEqual(reader.sector(0), payload)
        reader.sector.cache_clear()

    def test_corrupt_stream_fails_instead_of_zero_padding(self):
        reader = self.reader(b'shader bytes' * 100, damaged=True)
        with self.assertRaisesRegex(ValueError, 'inflate'):
            reader.sector(0)
        reader.sector.cache_clear()

    def test_cipher_numeric_initializer_and_eight_byte_feedback(self):
        self.assertEqual(decrypt(bytes(range(16))), bytes.fromhex('61d6133fe1ed3c800808080808080808'))

    def overlapping_reader(self, *, different=False, final=False, missing=False):
        # A reproducible valid DEFLATE prefix that exactly fills a 16 KiB
        # physical sector. Its independently restarted successor repeats the
        # encoded lookahead, as observed in the shipped archive sectors.
        source = random.Random(27).randbytes(18000)
        compressed = zlib.compress(source)
        fragment = compressed[:16378]
        decoder = zlib.decompressobj()
        expanded = decoder.decompress(fragment)
        self.assertFalse(decoder.eof)
        self.assertFalse(decoder.unconsumed_tail)
        expected = len(expanded) - 93
        following = expanded[expected:] + b'following independent block'
        if different:
            following = bytes([following[0] ^ 1]) + following[1:]
        if final:
            # This stream ends normally, but its logical declaration is short.
            # Use stored DEFLATE with exact full-sector compressed length.
            expanded = random.Random(28).randbytes(16367)
            fragment = zlib.compress(expanded, 0)
            self.assertEqual(len(fragment), 16378)
            expected = len(expanded) - 93
            following = expanded[expected:]
        first = struct.pack('<HHH', expected & 0xffff, expected >> 16, len(fragment)) + fragment
        c = zlib.compress(following)
        second = struct.pack('<HHH', len(following), 0, len(c)) + c
        reader = StrictReader.__new__(StrictReader)
        reader.mapping = first if missing else first + second + bytes(16384 - len(second))
        offsets = [0] if missing else [0, expected]
        reader.archive = SimpleNamespace(header=SimpleNamespace(comp_sector=16384,
                                          decomp_fs=expected if missing else expected + len(following)),
                                          _cs2do=offsets, _first_sec=0, path='synthetic-overlap')
        self.addCleanup(reader.sector.cache_clear)
        return reader, expanded[:expected], following

    def test_full_fragment_overlap_is_verified_against_next_stream(self):
        reader, payload, following = self.overlapping_reader()
        self.assertEqual(reader.sector(0), payload)
        self.assertEqual(reader.last_sector_notes['overlap_bytes'], 93)
        self.assertEqual(reader.sector(1), following)

    def test_full_fragment_overlap_must_not_discard_disagreement(self):
        reader, _, _ = self.overlapping_reader(different=True)
        with self.assertRaisesRegex(ValueError, 'overlap mismatch'):
            reader.sector(0)

    def test_full_fragment_overlap_must_not_extend_past_archive(self):
        reader, _, _ = self.overlapping_reader(missing=True)
        with self.assertRaisesRegex(ValueError, 'outside logical stream'):
            reader.sector(0)

    def test_complete_stream_cannot_use_overlap_exception(self):
        reader, _, _ = self.overlapping_reader(final=True)
        with self.assertRaisesRegex(ValueError, 'inflate mismatch'):
            reader.sector(0)

    def test_normal_chunk_output_size_remains_exact(self):
        reader = self.reader(b'ordinary complete stream')
        damaged = bytearray(reader.mapping)
        struct.pack_into('<H', damaged, 0, 5)
        reader.mapping = damaged
        with self.assertRaisesRegex(ValueError, 'inflate mismatch'):
            reader.sector(0)
        reader.sector.cache_clear()


if __name__ == '__main__':
    unittest.main()
