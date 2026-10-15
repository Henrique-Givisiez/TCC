"""Preparation contracts only: no simulator or scientific data execution."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from experiments.stage14a.prepare import build_plan,encode,EXPECTED,PROTOCOL


class Stage14APreparationTests(unittest.TestCase):
    def test_frozen_protocol_identity_and_determinism(self):
        self.assertEqual(hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),EXPECTED)
        self.assertEqual(encode(build_plan()),encode(build_plan()))

    def test_seed_disjointness_counts_and_pilot_exclusion(self):
        plan=build_plan();parts=plan['partitions']
        self.assertEqual([len(v) for v in parts.values()],[6,12,16])
        values=[s for v in parts.values() for s in v]
        smoke=plan['smoke_development']['seeds']
        self.assertEqual(len(set(values+smoke)),38)
        self.assertFalse(set(values+smoke)&{101,211,307,401,503})
        # Independent known-answer check against the preexisting namespace rule.
        first=int.from_bytes(hashlib.sha256(b'stage14-balanced-v1-seeds:baseline:0').digest()[:4],'big')
        self.assertEqual(parts['baseline'][0],first)

    def test_matrix_physical_configuration_and_no_execution(self):
        plan=build_plan();runs=plan['runs']
        self.assertEqual(len(runs),66);self.assertEqual(plan['nominal_seconds'],12672)
        self.assertEqual([sum(r['partition']==p for r in runs) for p in plan['partitions']],[6,12,48])
        for r in runs:
            c=r['config'];self.assertFalse(r['executed'])
            self.assertEqual(c['duration_seconds'],{'baseline':240,'calibration':360,'test':144}[r['partition']])
            self.assertEqual(c['normal_traffic']['rate'],2)
            self.assertEqual(c['normal_traffic']['clients'],4)
            self.assertEqual(c['attack']['rate'],8)
            self.assertEqual(c['attack']['enabled'],r['scenario']!='B')
            self.assertEqual(c['normal_traffic']['endpoint'],'/medium')
            self.assertFalse(c['autoscaler']['enabled'])
            self.assertEqual(c['infrastructure']['initial_instances'],1)
            if r['scenario']=='P':self.assertEqual(c['attack']['burst'],dict(duration_seconds=2,period_seconds=6))
        for seed in plan['partitions']['test']:
            trio=[r for r in runs if r['partition']=='test' and r['seed']==seed]
            self.assertEqual([r['scenario'] for r in trio],list('BCP'))

    def test_materialized_bytes_reproduce_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs=[Path(tmp)/n for n in ['first','second']]
            for out in outputs:
                subprocess.run(['.venv/bin/python','-B','-m','experiments.stage14a.prepare','--output',str(out)],check=True,capture_output=True)
            a,b=outputs
            for p in a.rglob('*'):
                if p.is_file():self.assertEqual(p.read_bytes(),(b/p.relative_to(a)).read_bytes())
            failed=subprocess.run(['.venv/bin/python','-B','-m','experiments.stage14a.prepare','--output',str(a)],capture_output=True)
            self.assertNotEqual(failed.returncode,0)

    def test_frozen_event_conflict_is_explicit_not_silently_repaired(self):
        plan=build_plan();doc=json.loads(PROTOCOL.read_text())
        self.assertEqual(doc['frozen']['event_truth']['availability_deadline'],'actual_end_inclusive_no_post_event_grace')
        self.assertTrue(any('event' in b for b in plan['blockers']))
