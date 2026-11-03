"""Behavioral checks for the portable FPGA skill, including CLI exit codes."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
TOOLS=ROOT/'skill/fpga-accelerator-validation/scripts'
sys.path.insert(0,str(TOOLS))
from check_manifest import verify
from compare_tensors import compare
from read_timing import parse


class SkillTools(unittest.TestCase):
    def setUp(self):
        base=ROOT/'build/work/skill_tests';base.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base)
        self.work=Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self):
        p=self.work/'input.bin';p.write_bytes(b'known input')
        return {'artifacts':[{'path':'input.bin','sha256':sha256(p.read_bytes()).hexdigest(),'bytes':11}]}

    def test_manifest_identity_and_changes(self):
        m=self.fixture();self.assertEqual(verify(self.work,m)['status'],'PASS')
        (self.work/'input.bin').write_bytes(b'other input')
        self.assertEqual(verify(self.work,m)['failures'][0]['error'],'hash_mismatch')

    def test_manifest_size_and_missing(self):
        m=self.fixture();m['artifacts'][0]['bytes']=10
        self.assertEqual(verify(self.work,m)['failures'][0]['error'],'size_mismatch')
        (self.work/'input.bin').unlink()
        self.assertEqual(verify(self.work,m)['failures'][0]['error'],'missing')

    def test_manifest_paths_and_duplicates(self):
        m=self.fixture();m['artifacts']*=2
        self.assertEqual(verify(self.work,m)['failures'][0]['error'],'duplicate_path')
        m['artifacts']=[{'path':'../outside.bin','sha256':'0'*64}]
        self.assertEqual(verify(self.work,m)['failures'][0]['error'],'outside_root')
        m['artifacts']=[{'path':'C:/outside.bin','sha256':'0'*64}]
        self.assertEqual(verify(self.work,m)['failures'][0]['error'],'outside_root')

    def test_manifest_malformed(self):
        for m in [{}, {'artifacts':[]}, {'artifacts':[None]}, {'artifacts':[{'path':'input.bin','sha256':'wrong'}]}]:
            self.assertEqual(verify(self.work,m)['status'],'FAIL')

    def test_current_routed_timing(self):
        result=parse(ROOT/'build/reports/vivado_timing.rpt')
        self.assertTrue(result['setup_met'] and result['hold_met'])
        self.assertEqual(result['wns_ns'],.175)
        self.assertTrue(any(abs(c['frequency_mhz']-125)<.01 for c in result['clocks']))

    def test_negative_and_unsupported_timing(self):
        text=(ROOT/'build/reports/vivado_timing.rpt').read_text()
        bad=self.work/'bad.rpt';bad.write_text(text.replace('0.175','-0.175'))
        self.assertFalse(parse(bad)['setup_met'])
        bad.write_text('synthesis finished successfully')
        with self.assertRaises(ValueError):parse(bad)

    def arrays(self,expected,actual):
        e,a=self.work/'expected.npy',self.work/'actual.npy'
        np.save(e,expected);np.save(a,actual)
        return e,a

    def test_integer_extremes_and_mismatch(self):
        x=np.array([-2147483648,2147483647,0],dtype=np.int32)
        e,a=self.arrays(x,x)
        self.assertEqual(compare(e,a)['status'],'PASS')
        np.save(a,np.array([2147483647,-2147483648,0],dtype=np.int32))
        result=compare(e,a)
        self.assertEqual(result['mismatches'],2)
        self.assertEqual(result['max_abs_error_finite'],4294967295)
        self.assertEqual(result['first_mismatch_flat_indices'],[0,1])

    def test_shape_dtype_and_integer_tolerance(self):
        e,a=self.arrays(np.zeros((2,2),np.int8),np.zeros(4,np.int8))
        with self.assertRaises(ValueError):compare(e,a)
        np.save(a,np.zeros((2,2),np.float32))
        with self.assertRaises(ValueError):compare(e,a)
        np.save(a,np.zeros((2,2),np.int8))
        with self.assertRaises(ValueError):compare(e,a,atol=1)

    def test_float_tolerance_and_nonfinite(self):
        e,a=self.arrays(np.array([1.,2.],np.float32),np.array([1.000001,2.],np.float32))
        self.assertEqual(compare(e,a)['status'],'FAIL')
        self.assertEqual(compare(e,a,atol=.00001)['status'],'PASS')
        np.save(a,np.array([np.nan,np.inf],np.float32))
        result=compare(e,a,atol=.00001)
        self.assertEqual(result['status'],'FAIL');self.assertEqual(result['nonfinite_elements'],2)

    def test_binary_contract(self):
        e,a=self.work/'expected.bin',self.work/'actual.bin'
        data=np.array([-1,0,127],dtype='<i4').tobytes();e.write_bytes(data);a.write_bytes(data)
        self.assertEqual(compare(e,a,'int32')['status'],'PASS')
        with self.assertRaises(ValueError):compare(e,a)
        a.write_bytes(b'partial')
        with self.assertRaises(ValueError):compare(e,a,'int32')

    def test_empty_and_unsupported_dtype(self):
        e,a=self.arrays(np.array([],np.int8),np.array([],np.int8))
        with self.assertRaises(ValueError):compare(e,a)
        np.save(e,np.array([2**63-1],np.int64));np.save(a,np.array([2**63-1],np.int64))
        with self.assertRaises(ValueError):compare(e,a)

    def test_cli_exit_codes(self):
        def run(script,*args):
            return subprocess.run([sys.executable,str(TOOLS/script),*map(str,args)],capture_output=True,text=True)
        manifest=self.work/'manifest.json';manifest.write_text(json.dumps(self.fixture()))
        self.assertEqual(run('check_manifest.py',manifest,'--root',self.work).returncode,0)
        (self.work/'input.bin').write_bytes(b'changed')
        self.assertEqual(run('check_manifest.py',manifest,'--root',self.work).returncode,1)
        manifest.write_text('{invalid json')
        self.assertEqual(run('check_manifest.py',manifest,'--root',self.work).returncode,2)
        e,a=self.arrays(np.array([1],np.int8),np.array([2],np.int8))
        self.assertEqual(run('compare_tensors.py',e,a).returncode,1)
        self.assertEqual(run('read_timing.py',manifest).returncode,2)


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(SkillTools)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    record={'status':'PASS' if result.wasSuccessful() else 'FAIL','checks':result.testsRun,
            'coverage':['manifest_identity_paths_sizes_and_format','Vivado_setup_hold_and_rejection',
                        'integer_float_tensor_comparison','binary_shape_dtype_contract','CLI_exit_codes_0_1_2']}
    (ROOT/'sim/results/skill_tools_validation.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
