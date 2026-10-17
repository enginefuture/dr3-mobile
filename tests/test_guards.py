"""Exact-build and post-verification tamper guards use synthetic input only."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import dr3


class Guards(unittest.TestCase):
    def test_build_id_and_content_both_required(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            header = bytearray(256)
            header[:4] = b'NSO0'
            header[0x40:0x60] = bytes(range(32))
            (root / 'main').write_bytes(header)
            expected = {'modules': {'main': {'build_id': bytes(range(32)).hex(), 'sha256': dr3.sha(root / 'main')}}}
            with patch.object(dr3, 'profile', return_value=expected):
                dr3.check_modules(root)
                header[255] = 1
                (root / 'main').write_bytes(header)
                with self.assertRaisesRegex(ValueError, 'mismatch'):
                    dr3.check_modules(root)

    def test_run_rejects_image_changed_after_verification(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'verification.json').write_text(json.dumps({'passed': True, 'artifacts': {'main': 'old'}}))
            with patch.object(dr3, 'WORK', root), patch.object(dr3, 'check_modules'), patch.object(dr3, 'fingerprints', return_value={'main': 'new'}):
                with self.assertRaisesRegex(ValueError, 'verification'):
                    dr3.launch(type('Args', (), {'seconds': 1})())


if __name__ == '__main__':
    unittest.main()
