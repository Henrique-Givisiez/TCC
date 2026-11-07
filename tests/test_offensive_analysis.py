import copy
import unittest
from experiments.offensive_analysis import http_metrics, state_before, cadence, characterize
from tests.test_protected_compositions import configuration
import json


def request(start=30,end=61,cls='attack'):
    return dict(request_id='r',run_id='run',generator='attack' if cls=='attack' else 'normal',
        traffic_class=cls,event_id='e' if cls=='attack' else None,elapsed_seconds=start,
        end_elapsed_seconds=end,duration_ms=(end-start)*1000 if end is not None else None,
        http_status=200 if end is not None else None,outcome='response' if end is not None else 'incomplete',error_type=None)


def events():
    return [dict(kind=kind,at=at,sequence=i+1,operation_id='op',traffic_class='attack',request_id='r',run_id='run',event_id='e',
                 work_started_at=59,work_finished_at=61,work_cpu_seconds=.2)
            for i,(kind,at) in enumerate([('work_submitted',58),('work_started',59),('work_completed',61)])]

class OffensiveAnalysisTests(unittest.TestCase):
    def test_empty_http(self):
        m=http_metrics([],30,60,2)
        self.assertEqual(m['realized_start_rps'],0);self.assertIsNone(m['duration_ms']['p95'])
    def test_start_at_S(self):self.assertEqual(http_metrics([request()],30,60,2)['starts_in_window'],1)
    def test_start_at_E(self):self.assertEqual(http_metrics([request(60)],30,60,2)['starts_in_window'],0)
    def test_late_http_completion(self):self.assertEqual(http_metrics([request()],30,60,2)['completions_after_end'],1)
    def test_censored(self):
        m=http_metrics([request(end=None)],30,60,2)
        self.assertEqual(m['incomplete'],1);self.assertIsNone(m['duration_ms']['mean'])
    def test_residual_at_E(self):
        state=state_before(events(),60,True)
        self.assertEqual(state['counts']['attack']['running'],1)
        self.assertEqual(state_before(events(),62,True)['counts']['attack']['pending'],0)
    def test_pending_at_close(self):self.assertEqual(state_before(events()[:2],62,True)['counts']['attack']['pending'],1)
    def test_incomplete(self):self.assertIsNone(state_before(events(),62,False)['counts'])
    def test_duplicates(self):self.assertEqual(state_before(events()+[events()[-1]],62,True)['status'],'unknown')
    def test_missing_start(self):self.assertEqual(state_before(events()[::2],62,True)['status'],'unknown')
    def test_sparse_cpu(self):
        c=cadence([0,6,12],{'pre':[0,10],'post':[10,20]})
        self.assertEqual(c['intervals_seconds']['median'],6);self.assertEqual(c['phase_samples']['pre'],2)
    def analyze(self,composition,clock=True):
        c=json.loads(configuration(composition).to_json());ev=events()
        ev.append(dict(kind='computation_observation_closed',at=150,sequence=4,observation_complete=True))
        requests=[request(59)]
        if composition=='combined':requests.append(dict(request(5,6,'benign'),request_id='n'))
        return characterize(c,requests,[],ev,[],[],0,clock,{'complete':True,'observation_complete':True,'written':4})
    def test_isolated(self):
        s,t=self.analyze('offensive');self.assertEqual(s['groups']['benign']['starts_total'],0)
        self.assertEqual(s['residual']['completions_after_E'],1);self.assertEqual(len(t),450)
    def test_combined(self):
        s,t=self.analyze('combined');self.assertEqual(s['groups']['benign']['starts_total'],1)
    def test_no_clock_proof(self):
        s,t=self.analyze('offensive',False);self.assertIsNone(s['residual']['state_at_E']['counts'])

    def test_exported_fixture_without_diagnostics(self):
        from tests.test_dataset_validation import ScientificValidationTests
        from experiments.offensive_analysis import analyze
        fixture=ScientificValidationTests();fixture.setUp();self.addCleanup(fixture.temporary.cleanup)
        fixture.test_valid_continuous()
        result=analyze(fixture.dataset,fixture.root/'analysis')
        self.assertTrue(result['validation']['dataset_valid'])
        self.assertEqual(result['residual']['state_at_E']['status'],'unknown')
        self.assertTrue(result['missing_inputs'])
    def test_corrupt_hash_rejected(self):
        from tests.test_dataset_validation import ScientificValidationTests
        from experiments.offensive_analysis import analyze
        fixture=ScientificValidationTests();fixture.setUp();self.addCleanup(fixture.temporary.cleanup)
        fixture.test_valid_continuous()
        with (fixture.dataset/'raw/service/request_log.csv').open('a') as f:f.write('corrupt\n')
        with self.assertRaises(ValueError):analyze(fixture.dataset,fixture.root/'analysis')

class ReviewTests(unittest.TestCase):
    def test_http_end_is_not_response(self):
        rows=[request(),dict(request(),http_status=503,outcome='http_error'),
              dict(request(),http_status=None,outcome='transport_error',error_type='ReadTimeout'),
              dict(request(),http_status=None,outcome='transport_error',error_type='ConnectionError'),
              request(end=None)]
        m=http_metrics(rows,30,60,2)
        self.assertEqual((m['attempts_started'],m['attempts_ended_known'],m['responses_received']),(5,4,2))
        self.assertEqual((m['http_error_responses'],m['timeouts'],m['connection_errors']),(1,1,1))
        self.assertEqual((m['duration_observations'],m['attempts_without_observed_end']),(4,1))
    def test_S_and_E_and_close_exactly(self):
        from experiments.offensive_analysis import state_at
        ev=events();ev[0]['at']=30;ev[1]['at']=30;ev[2]['at']=60
        self.assertEqual(state_before(ev,30,True)['counts']['attack']['pending'],0)
        self.assertEqual(state_at(ev,30,True)['counts']['attack']['running'],1)
        self.assertEqual(state_before(ev,60,True)['counts']['attack']['running'],1)
        self.assertEqual(state_at(ev,60,True)['counts']['attack']['completed'],1)
        closure=dict(kind='computation_observation_closed',at=60,observation_complete=True)
        self.assertEqual(state_at(ev+[closure],60,True)['counts']['attack']['pending'],0)
    def test_classification_order_independent(self):
        from experiments.offensive_analysis import classify_operations
        ev=events();ev[0].pop('traffic_class')
        a=classify_operations(ev,[request()]);b=classify_operations(list(reversed(ev)),[request()])
        self.assertEqual(a[1],b[1]);self.assertEqual(a[1]['op'],'attack')
    def test_conflict_is_unknown(self):
        from experiments.offensive_analysis import classify_operations
        for key,value in [('traffic_class','benign'),('run_id','other'),('event_id','other'),('request_id','other')]:
            ev=events();ev[1][key]=value
            normalized,classes,integrity=classify_operations(ev,[request()])
            self.assertEqual(classes['op'],'unknown');self.assertTrue(integrity['conflicts'])
            self.assertTrue(all(e['traffic_class']=='unknown' for e in normalized))
    def test_orphan_and_many_operations(self):
        from experiments.offensive_analysis import classify_operations
        ev=events()
        self.assertTrue(classify_operations(ev,[])[2]['conflicts'])
        second=[dict(e,operation_id='op2') for e in ev]
        integrity=classify_operations(ev+second,[request()])[2]
        self.assertEqual(integrity['correlated_requests'],0)
        self.assertTrue(all('multiple_operations_for_request' in c['reasons'] for c in integrity['conflicts']))
    def test_missing_request_is_insufficient_not_conflict(self):
        from experiments.offensive_analysis import classify_operations
        ev=events()
        for e in ev:e.pop('request_id')
        _,classes,integrity=classify_operations(ev,[request()])
        self.assertEqual(classes['op'],'unknown');self.assertFalse(integrity['conflicts'])
        self.assertTrue(integrity['insufficient_evidence'])
        self.assertEqual(integrity['requests_without_observed_submission'],['r'])
    def test_sweep_matches_reducer_at_all_boundaries(self):
        from experiments.offensive_analysis import states_before_boundaries
        ev=events()+[dict(e,operation_id='op2',traffic_class='benign',at=e['at']+.25) for e in events()]
        boundaries=[58,59,59.25,60,61,61.25,62]
        sweep=states_before_boundaries(ev,boundaries,True)
        for b in boundaries:self.assertEqual(sweep[b]['counts'],state_before(ev,b,True)['counts'])
    def test_shared_reducer_not_modified_and_pending_valid(self):
        from experiments.offensive_analysis import classify_operations
        _,classes,integrity=classify_operations(events()[:2],[request(end=None)])
        self.assertFalse(integrity['conflicts']);self.assertEqual(classes['op'],'attack')
        self.assertEqual(state_before(events()[:2],150,True)['counts']['attack']['pending'],1)

    def test_insufficient_identity_not_claimed_correlated(self):
        from experiments.offensive_analysis import classify_operations
        ev=events()
        for e in ev:e.pop('run_id')
        _,classes,integrity=classify_operations(ev,[request()])
        self.assertEqual(classes['op'],'unknown');self.assertEqual(integrity['correlated_requests'],0)
    def test_characterize_close_includes_exact_completion(self):
        c=json.loads(configuration('offensive').to_json()); ev=events()
        ev[-1]['at']=60;ev[-1]['work_finished_at']=60
        ev.append(dict(kind='computation_observation_closed',at=60,sequence=4,observation_complete=True))
        s,_=characterize(c,[request()],[],ev,[],[],0,True,dict(complete=True,observation_complete=True,written=4))
        self.assertEqual(s['residual']['state_before_E']['counts']['attack']['running'],1)
        self.assertEqual(s['residual']['state_after_events_at_E']['counts']['attack']['completed'],1)
        self.assertEqual(s['residual']['final_state']['counts']['attack']['pending'],0)
    def test_missing_operation_id_is_unknown(self):
        c=json.loads(configuration('offensive').to_json());ev=events();ev[0].pop('operation_id')
        ev.append(dict(kind='computation_observation_closed',at=150,sequence=4,observation_complete=True))
        s,_=characterize(c,[request()],[],ev,[],[],0,True,dict(complete=True,observation_complete=True,written=4))
        self.assertFalse(s['integrity']['computation_complete'])
        self.assertEqual(s['residual']['final_state']['status'],'unknown')
