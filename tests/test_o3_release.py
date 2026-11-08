import json
import unittest
from copy import deepcopy
from pathlib import Path
from analysis.detection.scientific.protocol import ROOT,load_spec
from analysis.detection.scientific.direct_contract import validate_spec
from analysis.detection.inputs import digest,ContractError

class ReleaseTests(unittest.TestCase):
    def test_release_changes_only_authority(self):
        base=json.loads((ROOT/'docs/scientific_protocol_direct_c135_20261108.json').read_text())['specification']
        path=ROOT/'docs/scientific_protocol_direct_c135_o3_20261108.json'
        released=load_spec(path,digest(path))
        self.assertFalse(base.pop('execution_release')['allowed'])
        self.assertTrue(released.pop('execution_release')['allowed'])
        self.assertEqual(base,released)
    def test_unbound_authority_rejected(self):
        spec=json.loads((ROOT/'docs/scientific_protocol_direct_c135_o3_20261108.json').read_text())['specification']
        spec['execution_release']['base_sha256']='wrong'
        with self.assertRaises(ContractError):validate_spec(spec,ROOT)
    def test_scientific_changes_rejected(self):
        spec=json.loads((ROOT/'docs/scientific_protocol_direct_c135_o3_20261108.json').read_text())['specification']
        spec['alpha']='0.02'
        with self.assertRaises(ContractError):validate_spec(spec,ROOT)
