"""Audit parser checks independent interface examples, without compiling Metal."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('shader_audit', Path(__file__).resolve().parents[1] / 'tools/audit_shader_interfaces.py')
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class InterfaceAuditTests(unittest.TestCase):
    def test_field_locations_and_interpolation(self):
        text = 'struct main0_in { float4 uv [[user(locn3), centroid_perspective]]; uint2 id [[user(locn8), flat]]; };'
        fields, unknown = audit.fields(text, 'main0_in')
        self.assertEqual(set(fields), {3, 8})
        self.assertEqual(fields[8]['type'], 'uint2')
        self.assertEqual(fields[3]['qualifiers'], 'centroid_perspective')
        self.assertEqual(unknown, [])

    def test_missing_and_type_difference_are_distinct(self):
        vertex = {'outputs': {1: {'type': 'float4', 'qualifiers': ''}}, 'unknowns': []}
        pixel = {'inputs': {1: {'type': 'uint4', 'qualifiers': ''}, 3: {'type': 'float4', 'qualifiers': ''}}, 'unknowns': []}
        result = audit.compare(vertex, pixel)
        self.assertEqual(result['missing_locations'], [3])
        self.assertEqual(result['potential_type_or_interpolation_mismatches'][0]['location'], 1)

    def test_position_only_vertex_does_not_cover_fragment_varyings(self):
        # Same interface shape as actual 56e679... / 76a9b1... failure.
        source = 'struct main0_out { float4 p [[position]]; float size [[point_size]]; };'
        vertex_fields, unknown = audit.fields(source, 'main0_out')
        pixel_fields, _ = audit.fields('struct main0_in { float4 color [[user(locn1)]]; float4 uv [[user(locn3)]]; };', 'main0_in')
        result = audit.compare({'outputs': vertex_fields, 'unknowns': unknown}, {'inputs': pixel_fields, 'unknowns': []})
        self.assertEqual(result['missing_locations'], [1, 3])
        self.assertEqual(result['potential_type_or_interpolation_mismatches'], [])

    def test_unrecognized_declaration_is_not_clean(self):
        _, unknown = audit.fields('struct main0_in { float4 uv[2] [[user(locn3)]]; };', 'main0_in')
        self.assertTrue(unknown)

    def test_success_ledger_accepts_only_known_abi(self):
        raw = bytearray(432)
        raw[:18] = b'0123456789abcdef_b'
        raw[24:42] = b'fedcba9876543210_b'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ledger.tsv'
            path.write_text('R\t' + raw.hex() + '\nR\t00\n')
            pairs, records, _, unknown = audit.read_success_ledger(path)
        self.assertEqual(pairs, {('0123456789abcdef_b', 'fedcba9876543210_b')})
        self.assertEqual(records, 1)
        self.assertEqual(len(unknown), 1)


if __name__ == '__main__':
    unittest.main()
