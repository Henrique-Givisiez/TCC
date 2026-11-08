"""Small synthetic direct-80 cases. No Docker, network or calibration data."""
from copy import deepcopy
from decimal import Decimal as D,localcontext,ROUND_UP
from types import SimpleNamespace
from unittest.mock import patch,MagicMock
from contextlib import ExitStack
import tempfile
from pathlib import Path
import unittest
from analysis.detection.scientific import engine,evaluation,protocol as p
from analysis.detection.scientific.direct_metrics import metrics
from analysis.detection.scientific.direct_summary import summarize
from analysis.detection.inputs import read_json

SPEC=read_json(p.ROOT/'docs/scientific_protocol_direct_20261108.json')['specification']

def rows(positive=(),missing=()):
    return [dict(window_start_seconds=i,window_end_seconds=i+1,available_at_seconds=i+1,
                 decision=None if i in missing else i in positive) for i in range(421)]

def truth(end=270):return dict(events=[dict(actual_start_seconds=150,actual_end_seconds=end)])

class DirectMetricsTests(unittest.TestCase):
    def test_control_fpr_only_nominal_not_drain(self):
        m=metrics(rows([31,390,400],missing=[32]),dict(events=[]))
        self.assertEqual(m['control']['expected'],360);self.assertEqual(m['fp'],1)
        self.assertEqual(m['tn'],358);self.assertAlmostEqual(float(m['fpr']),1/359)

    def test_pre_post_separate_and_end_late(self):
        m=metrics(rows([40,151,272,280,400]),truth(275))
        self.assertIsNone(m['fpr']);self.assertEqual(m['pre']['positive'],1)
        self.assertEqual(m['post']['positive'],1);self.assertEqual(m['post_still_offensive_windows'],5)
        self.assertTrue(m['event_detected']);self.assertEqual(m['observed_delay_seconds'],2)
        self.assertEqual(m['post']['expected'],115);self.assertEqual(m['post_positive_duration_seconds'],1)

    def test_prior_alarm_miss_and_inelegible(self):
        m=metrics(rows([149,280]),truth())
        self.assertFalse(m['event_detected']);self.assertIsNone(m['observed_delay_seconds'])
        m=metrics(rows([151]),truth(),False,'CAL_A_INELIGIBLE')
        self.assertIsNone(m['event_detected']);self.assertIsNone(m['fn']);self.assertIsNone(m['recall'])
        self.assertFalse(m['scientifically_evaluated'])

    def test_missing_and_late_decisions(self):
        r=rows([269],missing=range(150,269));r[269]['available_at_seconds']=271
        m=metrics(r,truth())
        self.assertFalse(m['event_detected']);self.assertEqual(m['attack']['unavailable'],119)
        self.assertEqual(m['attack']['available'],1)
        r[269]['available_at_seconds']=270
        self.assertTrue(metrics(r,truth())['event_detected'])

    def test_metric_pairs_use_same_blocks_and_keep_partial(self):
        spec=deepcopy(SPEC);spec['features']=[['service','request_starts']]
        docs=[];planned={}
        for scenario,block in [('L2',1),('A3',1),('F96',1),('A3',2),('F96',3)]:
            eid=scenario+str(block);entry=dict(id=eid,scenario=scenario,block=block)
            planned[eid]=entry
            result={m:metrics(rows([151]),truth() if scenario!='L2' else dict(events=[]),m!='cov') for m in spec['methods']}
            docs.append(dict(entry=entry,feature=['service','request_starts'],results=result))
        out=summarize(docs,planned,spec)
        m=out['results']['request_starts/A3/cov'];self.assertEqual(m['n_ineligible'],2)
        self.assertEqual(m['detection']['n'],0);self.assertEqual(m['misses'],0)
        pairs=out['scenario_contrasts']['request_starts/zscore/A3-F96']
        self.assertEqual(pairs['event_detected']['blocks'],[1])
        self.assertEqual(pairs['fpr']['n_pairs'],0)


class PairEligibilityTests(unittest.TestCase):
    def test_decimal_replay_preserves_frozen_50_digit_context(self):
        thresholds={m:D(1) for m in p.METHODS}
        support={m:[dict(fpr='0.0033333333333333333333333333333333333333333333333333',available_fraction='1')]*8 for m in p.METHODS}
        a=engine.pair_status(thresholds,support,'0.01')
        b=metrics(rows([31],missing=[32]),dict(events=[]))
        with localcontext() as ctx:
            ctx.prec=6;ctx.rounding=ROUND_UP
            self.assertEqual(engine.pair_status(thresholds,support,'0.01'),a)
            self.assertEqual(metrics(rows([31],missing=[32]),dict(events=[])),b)

    def test_real_calibration_grid_partial_verification_and_test_processing(self):
        validate_real=engine.validate_run
        sources=[SimpleNamespace(reference=dict(run_id='A'+str(i),seed=100+i,authority={},partition='CAL_A'),
            series=SimpleNamespace(run_id='A'+str(i),family='service',feature='request_starts',feature_schema_version=2)) for i in range(8)]
        base=dict(authority={},feature=['service','request_starts'],parameters={'synthetic':'fixed'},
                  sources=[dict(run_id='B'+str(i),seed=i,feature_schema_version=2) for i in range(4)])
        model=SimpleNamespace(reference=dict(path='baseline'))
        calls=[]
        def trace(series,method,parameters=None,h=None):
            calls.append((series.run_id,method,h))
            missing=range(30,390) if method=='cov' else ()
            positive=range(30,390) if (method=='cusum-freeze' and h<D(1)) or (series.run_id.startswith('V') and method=='ewma') else ()
            result=rows(positive,missing)[:390]
            for i,r in enumerate(result):
                r.update(window_index=i,score=None if r['decision'] is None else D(0),
                    previous_state=D(0),candidate=D(0),update_accepted=True,posterior_state=D(0))
            return result
        with tempfile.TemporaryDirectory() as folder,ExitStack() as stack:
            for name,value in [('SPEC',SPEC)]:stack.enter_context(patch.object(engine,name,value))
            stack.enter_context(patch.object(engine,'check_sources'))
            stack.enter_context(patch.object(engine,'model_metadata',return_value=base))
            stack.enter_context(patch.object(engine,'check_authority'))
            stack.enter_context(patch.object(engine,'verify_reference'))
            stack.enter_context(patch.object(engine,'publish',side_effect=lambda dest,kind,metadata,**kwargs:metadata))
            candidate=stack.enter_context(patch.object(engine,'publish_candidate',return_value=SimpleNamespace(reference=dict(path='candidate'))))
            stack.enter_context(patch.object(engine,'trace',side_effect=trace))
            c=engine.calibrate(sources,model,Path(folder)/'a',{})
            self.assertTrue(c['pair_status']['zscore']['eligible']);self.assertFalse(c['pair_status']['cov']['eligible'])
            self.assertTrue(c['pair_status']['ewma']['eligible']);self.assertEqual(c['thresholds']['cusum-freeze'],D(1))
            self.assertEqual(candidate.call_count,len(SPEC['h_grid']))
            cal=SimpleNamespace(reference=dict(path='calibration'))
            stack.enter_context(patch.object(engine,'calibration_metadata',return_value=c))
            stack.enter_context(patch.object(engine,'validate_run',side_effect=lambda d:d.doc))
            bsources=[SimpleNamespace(reference=dict(run_id='V'+str(i),seed=200+i,authority={},partition='CAL_B'),
                series=SimpleNamespace(run_id='V'+str(i))) for i in range(8)]
            docs=[dict(source=s.reference,calibration=cal.reference,methods={m:trace(s.series,m,{},c['thresholds'][m]) if c['pair_status'][m]['eligible'] else rows(missing=range(421))[:390] for m in p.METHODS}) for s in bsources]
            before=deepcopy(c['thresholds'])
            artifacts=[SimpleNamespace(reference=dict(path='run'+str(i)),doc=d) for i,d in enumerate(docs)]
            v=engine.verify(bsources,artifacts,cal,Path(folder)/'b',{})
            self.assertTrue(v['method_accepted']['zscore']);self.assertFalse(v['method_accepted']['ewma'])
            self.assertFalse(v['method_accepted']['cov']);self.assertEqual(c['thresholds'],before)
            stack.enter_context(patch.object(engine,'verification_metadata',return_value=v))
            source=SimpleNamespace(reference=dict(run_id='T',seed=999,authority={},entry_id='T',partition='TEST',
                family='service',feature='request_starts',feature_manifest='unused/features/feature_manifest.json',
                dataset_manifest='unused/dataset/dataset_manifest.json',feature_manifest_sha256='x',dataset_manifest_sha256='y',test_release={}),partition='TEST',
                series=SimpleNamespace(run_id='T',family='service',feature='request_starts',feature_schema_version=2,
                    observations=tuple(SimpleNamespace(window_index=i,window_start_seconds=i,window_end_seconds=i+1) for i in range(390))))
            calls.clear()
            result=engine.process(source,model,cal,Path(folder)/'test',{},SimpleNamespace(reference=dict(path='verification')))
            self.assertEqual({m for _,m,_ in calls},{'zscore','cusum-freeze'})
            self.assertFalse(result['method_evaluated']['ewma']);self.assertTrue(result['method_evaluated']['zscore'])
            self.assertTrue(all(r['decision'] is None for r in result['methods']['cov']))
            self.assertEqual(c['thresholds'],before)
            from analysis.detection.scientific import data
            with patch.object(data,'load_source',return_value=source),patch.object(engine,'open_artifact',return_value=SimpleNamespace(read=lambda *args:v)):
                validate_real(SimpleNamespace(read=lambda *args:result))
                changed=deepcopy(result);changed['method_evaluated']['cov']=True
                with self.assertRaisesRegex(ValueError,'eligibility'):
                    validate_real(SimpleNamespace(read=lambda *args:changed))

    def test_partial_cal_a_cal_b_and_fixed_thresholds(self):
        thresholds={m:D(1) for m in p.METHODS}
        good=[dict(fpr='0.01',available_fraction='0.95')]
        bad=[dict(fpr='0.06',available_fraction='1')]
        support={m:good for m in p.METHODS};support['cov']=bad
        a=engine.pair_status(thresholds,support,'0.01')
        self.assertEqual({m:r['eligible'] for m,r in a.items()},dict(zscore=True,cov=False,ewma=True,**{'cusum-freeze':True}))
        b_support={m:good for m in p.METHODS};b_support['ewma']=bad
        b=engine.pair_status(thresholds,b_support,'0.02',prior=a)
        self.assertTrue(b['zscore']['eligible']);self.assertFalse(b['cov']['eligible']);self.assertFalse(b['ewma']['eligible'])
        self.assertEqual({m:r['threshold'] for m,r in b.items()},thresholds)
        with patch.object(engine,'SPEC',SPEC):
            flags=engine.method_flags(dict(pair_status=a),dict(method_accepted={m:r['eligible'] for m,r in b.items()}))
        self.assertTrue(flags['zscore']);self.assertFalse(flags['cov'])

    def test_baseline_failure_does_not_raise_for_request_starts(self):
        source=SimpleNamespace(reference=dict(authority={},partition='BASELINE'),series=SimpleNamespace(
            observations=tuple(SimpleNamespace(value=None) for _ in range(390)),feature='request_starts',family='service'))
        # Preserve fitting code and support checks; bypass only filesystem bindings.
        from analysis.detection.contracts import ObservedSeries,Observation
        source.series=ObservedSeries('r','service','request_starts',D(1),2,tuple(Observation('r',i,D(i),D(i+1),None) for i in range(390)))
        with patch.object(engine,'SPEC',SPEC),patch.object(engine,'check_sources'),patch.object(engine,'artifact',side_effect=lambda d,k,m:m):
            model=engine.fit([source],'unused',{})
        self.assertIsNone(model['parameters']);self.assertIn('95%',model['unavailable_reason'])

    def test_no_threshold_is_not_an_approval(self):
        status=engine.pair_status({m:None for m in p.METHODS},{},'0.01',reason='BASELINE_UNAVAILABLE')
        self.assertTrue(all(not r['eligible'] for r in status.values()))
        self.assertTrue(all(r['reason']=='BASELINE_UNAVAILABLE' for r in status.values()))

    def test_checkpoint_release_allows_rejected_primary_but_checks_ancestry(self):
        from analysis.detection.scientific import data
        from analysis.detection import artifacts
        a=dict(partition='CAL_A',authority={},artifacts={f:dict(path='a_'+f) for _,f in p.FEATURES})
        b=dict(partition='CAL_B',authority={},previous_checkpoint=dict(path='a'),
               artifacts={f:dict(path='b_'+f) for _,f in p.FEATURES})
        objects={'a':a,'b':b}
        for _,f in p.FEATURES:objects['b_'+f]=dict(authority={},calibration=a['artifacts'][f],approved=False,
                                                    method_accepted={m:False for m in p.METHODS})
        def opened(ref,*args):return SimpleNamespace(read=lambda *args:objects[ref['path']])
        with patch.object(data,'SPEC',SPEC),patch.object(artifacts,'open_artifact',side_effect=opened), \
             patch.object(engine,'verification_metadata',side_effect=lambda obj:obj.read()):
            data.validate_test_release(dict(path='b'),{})
            objects['b_request_starts']['calibration']=dict(path='wrong')
            with self.assertRaisesRegex(ValueError,'ancestry'):data.validate_test_release(dict(path='b'),{})

if __name__=='__main__':unittest.main()
