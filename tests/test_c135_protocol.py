import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from analysis.detection.inputs import digest
from analysis.detection.scientific import protocol as p

NEW=p.ROOT/'docs/scientific_protocol_direct_c135_20261108.json'
OLD=p.ROOT/'docs/scientific_protocol_direct_20261108.json'

class RevisionTests(unittest.TestCase):
    def test_only_explicit_scope_changes_and_parent_preserved(self):
        self.assertEqual(digest(OLD),'be39b12ffcd09699da6311fb7a86ddab342dfba503e699b9df6833f9fed46303')
        a=json.loads(OLD.read_text())['specification'];b=p.load_spec(NEW,digest(NEW))
        self.assertEqual(len(b['features']),4)
        self.assertEqual(b['features'],a['features'][:4])
        for key in ('version','features','descriptive_features','revision'):b.pop(key,None);a.pop(key,None)
        self.assertEqual(a,b)

    def test_selected_version_excludes_cpu_at_loader_and_calibration_boundary(self):
        env=dict(os.environ,SCIENTIFIC_SPEC_PATH=str(NEW),SCIENTIFIC_SPEC_SHA256=digest(NEW))
        script='''
from types import SimpleNamespace
from analysis.detection.scientific import protocol as p,engine,data
from analysis.detection.inputs import ContractError
assert len(p.FEATURES)==4 and len(p.METHODS)==4
assert len(p.expected_slots())==80
s=SimpleNamespace(series=SimpleNamespace(family='infrastructure',feature='mean_cpu_percent'))
try: engine.check_sources([s],'BASELINE',4)
except ContractError as e: assert 'excluded' in str(e)
else: raise AssertionError('CPU accepted')
try: data.load_source({}, {}, 'infrastructure','mean_cpu_percent',authority={})
except ContractError: pass
else: raise AssertionError('CPU accepted')
'''
        result=subprocess.run([sys.executable,'-B','-c',script],env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
