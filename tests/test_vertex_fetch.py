import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('vertex_variants',ROOT/'tools/vertex_fetch_variants.py')
variants=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(variants)


class VertexFetchTransformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=tempfile.TemporaryDirectory()
        cls.helper=Path(cls.directory.name)/'transform'
        subprocess.run(['clang','-O1','-fobjc-arc',str(ROOT/'tests/vertex_fetch_transform.m'),'-framework','Foundation','-o',str(cls.helper)],check=True)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def compare_transform(self,source,signature):
        path=Path(self.directory.name)/'input.metal';path.write_text(source)
        result=subprocess.run([str(self.helper),str(path),f'{signature:x}'],capture_output=True,text=True)
        expected=variants.adapt_source(source,signature)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout,expected)
        return expected

    def test_multiple_formats_preserve_bitcast_width(self):
        source='struct main0_in {uint4 a [[attribute(2)]];float2 b [[attribute(7)]];};\nvertex main0_out main0(main0_in in [[stage_in]]){return use(in.a,in.b);}'
        transformed=self.compare_transform(source,(1<<4)|(3<<14))
        self.assertIn('float4 a [[attribute(2)]]',transformed)
        self.assertIn('int2 b [[attribute(7)]]',transformed)
        self.assertIn('uint4 dm_fetch_a = as_type<uint4>(in.a)',transformed)
        self.assertIn('float2 dm_fetch_b = as_type<float2>(in.b)',transformed)
        self.assertIn('use(dm_fetch_a,dm_fetch_b)',transformed)

    def test_actual_failed_shader_source_parity(self):
        cache=ROOT/'work/build/cache/metal_shader_cache/b-87c50a868147'
        if not cache.exists():self.skipTest('private original shader corpus unavailable')
        for key,signature in [('18f2aadcec113d49_b',0x10),('88ba806f61d19fae_b',4)]:
            self.compare_transform((cache/(key+'.metal')).read_text(),signature)

    def test_unknown_and_redundant_requests_reject(self):
        source='struct main0_in {uint4 a [[attribute(2)]];};\nvertex main0_out main0(main0_in in [[stage_in]]){return use(in.a);}'
        path=Path(self.directory.name)/'bad.metal';path.write_text(source)
        for signature in [1,2<<4]:
            with self.assertRaises(ValueError):variants.adapt_source(source,signature)
            result=subprocess.run([str(self.helper),str(path),f'{signature:x}'],capture_output=True)
            self.assertNotEqual(result.returncode,0)


if __name__=='__main__':unittest.main()
