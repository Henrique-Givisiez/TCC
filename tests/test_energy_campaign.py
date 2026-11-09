"""Offline guard/orchestration tests. No containers, HTTP or OS changes."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch,Mock
import json
import unittest

from experiments import energy_control as h, energy_campaign as c
from experiments.energy_pilot_analysis import occupancy,stats


def observation():
    return dict(utc='fixture',policy=dict(profile='power-saver',acpi_profile='low-power',
        external_power={'AC':'1'},policies={'policy0':dict(scaling_governor='powersave',
        energy_performance_preference='power')},boot_id='boot',affinity=[0,1],kernel='fixture',intel_pstate={}),
        instantaneous=dict(frequency_khz={'policy0':'400000'},temperatures_millicelsius={}))


class EnergyTests(unittest.TestCase):
    def test_policy_drift_fails_but_instantaneous_changes_do_not(self):
        ref=observation();h.validate(ref,ref)
        for path,value in [('profile','performance'),('acpi_profile','balanced'),('boot_id','other'),('affinity',[0])]:
            bad=deepcopy(ref);bad['policy'][path]=value
            with self.subTest(path=path),self.assertRaises(h.EnvironmentChanged):h.validate(bad,ref)
        changed=deepcopy(ref);changed['instantaneous']['frequency_khz']['policy0']='4700000'
        h.validate(changed,ref)

    def test_ac_required_and_unverifiable_fails(self):
        for supplies in ({},{'AC':'0'},{'AC':'unknown'}):
            bad=observation();bad['policy']['external_power']=supplies
            with self.assertRaises(h.EnvironmentChanged):h.validate(bad)

    def test_epp_and_governor_change_fails(self):
        ref=observation()
        for field in ('scaling_governor','energy_performance_preference'):
            bad=deepcopy(ref);bad['policy']['policies']['policy0'][field]='different'
            with self.assertRaises(h.EnvironmentChanged):h.validate(bad,ref)

    def test_suspend_detection(self):
        ref=observation();ref['instantaneous']['suspend_offset_seconds']=0
        changed=deepcopy(ref);changed['instantaneous']['suspend_offset_seconds']=10
        with self.assertRaisesRegex(h.EnvironmentChanged,'Suspend'):h.validate(changed,ref)

    def test_plan_draft_preserves_80_slots_calibration_and_paired_seeds(self):
        from analysis.detection.scientific.direct_contract import draft_entries,configuration
        from analysis.detection.scientific import protocol as p
        spec=c.read(c.PARENT)['specification']
        rows=draft_entries(spec,{42},'offline-energy-fixture')
        self.assertEqual(len(rows),80)
        self.assertEqual([r['partition'] for r in rows[:20]],['BASELINE']*4+['CAL_A']*8+['CAL_B']*8)
        for block in range(1,21):
            own=[r for r in rows if r['partition']=='TEST' and r['block']==block]
            self.assertEqual({r['scenario'] for r in own},{'L2','A3','F96'})
            self.assertEqual(len({r['seed'] for r in own}),1)
        self.assertNotIn(42,{r['seed'] for r in rows})
        cfg=configuration(spec,'F96','fixture',123)
        self.assertEqual(cfg['duration_seconds'],390)
        self.assertEqual((cfg['attack']['start_seconds'],cfg['attack']['duration_seconds']),(150,120))
        self.assertFalse(spec['eligibility']['global_test_block'])
        self.assertEqual((spec['cal_a_mean_max'],spec['cal_b_mean_max']),('0.01','0.02'))

    def test_current_bad_profile_cannot_consume_pilot_or_contact_docker(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);cfg=root/'A3.json';c.save(cfg,{'seed':7});c.save(root/'pilot-policy.json',{})
            c.save(root/'preparation.json',dict(pilots={'A3':dict(path=str(cfg),sha256=c.digest(cfg))},
                pilot_policy_sha256=c.digest(root/'pilot-policy.json'),runtime_hashes={}))
            bad=observation();bad['policy']['profile']='performance'
            with patch.object(c,'BUNDLE',root),patch.object(c,'PILOTS',root/'pilot'),patch.object(h,'snapshot',return_value=bad),\
                 patch('analysis.detection.scientific.protocol.runtime_hashes',return_value={}),patch('docker.DockerClient') as docker:
                with self.assertRaises(h.EnvironmentChanged):c.pilot('A3')
                docker.assert_not_called();self.assertFalse((root/'pilot').exists())

    def test_unauthorized_campaign_does_not_contact_docker_or_write(self):
        with patch('docker.DockerClient') as docker,patch.object(c,'load_control') as load:
            with self.assertRaises(PermissionError):c.run('irrelevant','yes')
            load.assert_not_called();docker.assert_not_called()

    def test_frozen_control_tamper_rejected(self):
        with TemporaryDirectory() as folder,patch.object(c,'BUNDLE',Path(folder)):
            c.save(Path(folder)/'control.json',dict(identity=c.IDENTITY,plan=dict(path=str(Path(folder)/'plan.json'))))
            expected=c.digest(Path(folder)/'control.json');c.load_control(expected)
            (Path(folder)/'control.json').write_text('{}')
            with self.assertRaises(ValueError):c.load_control(expected)

    def test_append_only_artifacts(self):
        with TemporaryDirectory() as folder:
            f=Path(folder)/'accepted.json';c.save(f,dict(run='a'))
            with self.assertRaises(FileExistsError):c.save(f,dict(run='b'))
            self.assertEqual(c.read(f),dict(run='a'))

    def test_sampling_violation_terminates_child_and_seals_invalid(self):
        with TemporaryDirectory() as folder:
            proc=Mock();proc.poll.side_effect=[None,0];proc.returncode=-15
            bad=observation();bad['policy']['profile']='performance'
            with patch.object(c,'checked'),patch.object(h,'provenance',return_value={}),\
                 patch.object(h,'snapshot',return_value=bad),patch.object(h,'container_observations',return_value=[]),\
                 patch.object(c.subprocess,'Popen',return_value=proc),patch.object(c.os,'killpg') as kill:
                proc.pid=123
                with self.assertRaises(h.EnvironmentChanged):
                    c.supervised(['fixture'],Path(folder),observation(),Mock(),{},240)
                kill.assert_called_once_with(123,c.signal.SIGTERM)
            seal=c.read(Path(folder)/'environment-complete.json')
            self.assertFalse(seal['valid']);self.assertIn('power-saver',seal['error'])

    def test_successful_process_still_needs_post_environment_check(self):
        with TemporaryDirectory() as folder:
            proc=Mock();proc.poll.return_value=0;proc.returncode=0
            with patch.object(c,'checked',side_effect=[observation(),h.EnvironmentChanged('post drift')]),\
                 patch.object(h,'provenance',return_value={}),patch.object(h,'snapshot',return_value=observation()),\
                 patch.object(h,'container_observations',return_value=[]),patch.object(c.subprocess,'Popen',return_value=proc):
                with self.assertRaisesRegex(h.EnvironmentChanged,'post drift'):
                    c.supervised(['fixture'],Path(folder),observation(),Mock(),{},240)
            self.assertFalse(c.read(Path(folder)/'environment-complete.json')['valid'])

    def test_exact_occupancy_and_nearest_rank(self):
        value=occupancy([(0,10),(5,15)],0,20)
        self.assertEqual(value['mean'],1);self.assertEqual(value['peak'],2)
        self.assertEqual(value['two_fraction'],.25)
        self.assertEqual(stats(range(1,21))['p95'],19)

    def test_sequence_order_resumption_and_failure_halt(self):
        # Exercise the real adapter loop with an entirely offline controller.
        for fail in (False,True):
            with self.subTest(fail=fail),TemporaryDirectory() as folder:
                root=Path(folder);calls=[]
                class FakeBackend:
                    def __init__(self,plan):self.plan=plan
                class FakeCampaign:
                    def __init__(self,*args,**kw):self.cps={'BASELINE':{'manifest_sha256':'baseline'}}
                    def locked(self):
                        from contextlib import nullcontext
                        root.mkdir(exist_ok=True);return nullcontext()
                    def checkpoints(self):return dict(self.cps)
                    def run_partition(self,part,auth,previous):
                        calls.append((part,auth,previous))
                        if fail:raise RuntimeError('fixture failure')
                        self.cps[part]={'manifest_sha256':part}
                cfg=root/'fixture-plan.json';c.save(cfg,{})
                control=dict(reference=observation(),plan=dict(path=str(cfg),sha256=c.digest(cfg)))
                with patch.object(c,'RESULT',root),patch.object(c,'load_control',return_value=control),\
                     patch('experiments.scientific_campaign.Campaign',FakeCampaign),\
                     patch('experiments.scientific_collection.DockerBackend',FakeBackend),\
                     patch('docker.DockerClient'),patch.object(h,'snapshot',return_value=observation()):
                    if fail:
                        with self.assertRaises(RuntimeError):c.run('hash',c.IDENTITY)
                        self.assertEqual(len(calls),1)
                    else:
                        self.assertTrue(c.run('hash',c.IDENTITY)['complete'])
                        self.assertEqual(calls,[('CAL_A','CAL_A','baseline'),('CAL_B','CAL_B','CAL_A'),('TEST','TEST','CAL_B')])
                        with self.assertRaisesRegex(ValueError,'--resume'):c.run('hash',c.IDENTITY)


if __name__=='__main__':unittest.main()
