import struct
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
import zlib
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from audit_cpk_payloads import audited_sector, check_decoded_sector, expected_sector_bytes, check_resume, check_payload_crc
from cpk_shaders import StrictReader


class PayloadAuditControls(unittest.TestCase):
    def reader(self, data):
        r = StrictReader.__new__(StrictReader)
        r.mapping = data
        r.archive = NS(header=NS(comp_sector=16384), _first_sec=0, _cs2do=[0], path='synthetic')
        self.addCleanup(r.sector.cache_clear)
        return r

    def chunk(self, payload):
        compressed = zlib.compress(payload)
        return struct.pack('<HHH', len(payload), 0, len(compressed)) + compressed

    def test_nonempty_sector_uses_original_inflate(self):
        payload = b'audit data' * 100
        raw, adapted = audited_sector(self.reader(self.chunk(payload)), 0)
        self.assertEqual(raw, payload)
        self.assertFalse(adapted)

    def test_empty_encrypted_marker_preserves_all_decoded_data(self):
        payload = b'audit data' * 100
        data = self.chunk(payload) + struct.pack('<HHH', 0, 0, 0x8000) + bytes(17)
        raw, adapted = audited_sector(self.reader(data), 0)
        self.assertEqual(raw, payload)
        self.assertTrue(adapted)
        self.assertEqual(check_decoded_sector(raw, [0], len(payload), 0), len(payload))

    def test_zero_output_archive(self):
        raw, adapted = audited_sector(self.reader(bytes(16)), 0)
        self.assertEqual(check_decoded_sector(raw, [0], 0, 0), 0)
        self.assertFalse(adapted)

    def test_nonzero_padding_not_accepted(self):
        data = self.chunk(b'hello') + struct.pack('<HHH', 0, 0, 0x8000) + b'\x01'
        with self.assertRaisesRegex(ValueError, 'Nonzero'):
            audited_sector(self.reader(data), 0)

    def test_marker_cannot_hide_declared_payload(self):
        data = struct.pack('<HHH', 100, 0, 0x8000)
        with self.assertRaises(ValueError):
            audited_sector(self.reader(data), 0)

    def test_marker_cannot_hide_corrupt_compressed_data(self):
        data = struct.pack('<HHH', 50, 0, 5) + b'bad!!' + struct.pack('<HHH', 0, 0, 0x8000)
        with self.assertRaisesRegex(ValueError, 'inflate'):
            audited_sector(self.reader(data), 0)

    def test_declared_adjacent_boundary_mismatch_rejected(self):
        for raw, offsets, total, index in [(b'ab', [0, 3], 5, 0), (b'ab', [0, 3], 6, 1),
                                           (b'ab', [0, 6], 5, 0), (b'ab', [3, 0], 5, 0)]:
            with self.subTest(offsets=offsets, total=total, index=index):
                with self.assertRaises(ValueError):
                    check_decoded_sector(raw, offsets, total, index)

    def test_out_of_range_sector_rejected(self):
        for index in (-1, 2):
            with self.assertRaises(ValueError):
                expected_sector_bytes([0], 10, index)

    def test_resume_rejects_stale_decoder_results(self):
        inputs = {'archive': {'file_bytes': 25, 'mtime_ns': 30}}
        decoder = {'policy': 'verified', 'sources': {'reader.py': 'hash1'}}
        check_resume({'inputs': inputs, 'decoder_identity': decoder}, inputs, decoder)
        for stale in (None, {'policy': 'verified', 'sources': {'reader.py': 'hash2'}}):
            with self.subTest(stale=stale):
                with self.assertRaisesRegex(ValueError, 'Decoder identity'):
                    check_resume({'inputs': inputs, 'decoder_identity': stale}, inputs, decoder)
        with self.assertRaisesRegex(ValueError, 'Input inventory'):
            check_resume({'inputs': {} , 'decoder_identity': decoder}, inputs, decoder)

    def test_audit_diagnostics_are_correct_after_a_cache_hit(self):
        first = self.chunk(b'first') + struct.pack('<HHH', 0, 0, 0x8000)
        first += bytes(16384 - len(first))
        second = self.chunk(b'second')
        reader = self.reader(first + second)
        reader.archive._cs2do = [0, 5]
        reader.sector(0)
        reader.sector(1)
        raw, marker = audited_sector(reader, 0)
        self.assertEqual(raw, b'first')
        self.assertTrue(marker)

    def test_stored_payload_crc_checks_encoded_bytes_and_padding(self):
        prefix = b'header and index'
        payload = self.chunk(b'checked data') + bytes(20000)
        expected = zlib.crc32(payload)
        self.assertEqual(check_payload_crc(prefix + payload, len(prefix), expected), expected)
        # Header/index bytes do not participate in this specific checksum.
        self.assertEqual(check_payload_crc(b'X' * len(prefix) + payload, len(prefix), expected), expected)
        for offset in (7, len(payload) - 1):
            damaged = bytearray(prefix + payload)
            damaged[len(prefix) + offset] ^= 1
            with self.subTest(offset=offset):
                with self.assertRaisesRegex(ValueError, 'CRC mismatch'):
                    check_payload_crc(damaged, len(prefix), expected)
        for start in (-1, len(prefix + payload) + 1):
            with self.assertRaisesRegex(ValueError, 'range outside'):
                check_payload_crc(prefix + payload, start, expected)

if __name__ == '__main__':
    unittest.main()
