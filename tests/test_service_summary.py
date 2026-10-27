"""Synthetic requests only; no experiment execution or frozen TEST evaluation."""
import csv
from copy import deepcopy
from decimal import Decimal as D
from fractions import Fraction as F
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from experiments.summarize_service import summarize
from simulator.request_logger import REQUEST_FIELDS


FIXTURES = Path(__file__).parent / 'fixtures' / 'service_summary'


class ServiceSummaryTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((FIXTURES / 'phases.json').read_text())
        self.source = FIXTURES / 'request_log.csv'

    def row(self, result, phase, cls='benign'):
        return next(r for r in result['rows'] if r['phase'] == phase and r['traffic_class'] == cls)

    def test_reconciliation_and_distinct_clocks(self):
        result = summarize(self.source, self.plan)
        self.assertEqual(result['reconciliation'], dict(input_rows=9, included_starts=9,
            ignored_starts_at_or_after_cutoff=0, known_ends=8, open_as_of=1,
            starts_equal_known_ends_plus_open=True))
        pre, active, post, drain = [self.row(result, p) for p in ('PRE', 'ACTIVE', 'POST', 'DRAIN')]
        self.assertEqual((pre['starts'], pre['known_ends'], pre['completed_cross_phase']), (2, 1, 1))
        self.assertEqual((active['starts'], active['known_ends']), (4, 4))
        self.assertEqual(active['cohort_outcomes'], dict(success_2xx=1, other_response=1,
            http_error=1, transport_error=1, client_error=0))
        self.assertEqual((post['starts'], post['known_ends'], post['cohort_open_as_of']), (2, 1, 1))
        self.assertEqual(post['cohort_incomplete_no_end'], 1)
        self.assertEqual(drain['known_ends'], 1)
        self.assertEqual(drain['starts'], 0)
        self.assertIsNone(drain['cohort_fractions']['success_2xx_per_started'])
        boundary = self.row(result, '__at_observation_end__', 'attack')
        self.assertEqual(boundary['known_ends'], 1)
        self.assertIsNone(boundary['rates_per_second']['known_ends'])
        # Summing classes/phases is a conservation equation; individual phase
        # starts and ends need not match because requests cross boundaries.
        for row in result['rows']:
            self.assertEqual(row['starts'], row['cohort_known_ends'] + row['cohort_open_as_of'])
            self.assertEqual(row['known_ends'], sum(row['end_outcomes'].values()))

    def test_success_durations_start_cohort_and_type7(self):
        result = summarize(self.source, self.plan)
        pre = self.row(result, 'PRE')['duration_success_2xx_ms']
        self.assertEqual((pre['n'], pre['mean'], pre['p50'], pre['p95']), (2, D(1000), D(1000), D(1000)))
        active = self.row(result, 'ACTIVE')['duration_success_2xx_ms']
        self.assertEqual((active['n'], active['mean']), (1, D(500)))
        self.assertEqual(self.row(result, 'POST')['duration_success_2xx_ms']['mean'], D(3000))
        self.assertIsNone(self.row(result, 'DRAIN')['duration_success_2xx_ms']['p95'])
        from experiments.summarize_service import quantile
        self.assertEqual(quantile([D(100), D(300)], '.95'), D(290))

    def test_snapshot_open_cohorts_and_drain(self):
        result = summarize(self.source, self.plan, as_of='7')
        active = self.row(result, 'ACTIVE')
        self.assertEqual(active['cohort_open_as_of'], 1)  # timeout ends at8
        self.assertEqual(active['cohort_end_after_cutoff'], 1)
        self.assertEqual(active['cohort_outcomes']['transport_error'], 0)
        self.assertFalse(active['cohort_fractions']['final'])
        self.assertEqual(active['cohort_fractions']['failures_per_started'], D('.25'))
        self.assertAlmostEqual(active['cohort_fractions']['failures_per_known_end'], D(1) / D(3))
        post = self.row(result, 'POST')
        self.assertEqual(post['starts'], 1)
        self.assertEqual(post['cohort_open_as_of'], 1)
        self.assertIsNone(post['duration_success_2xx_ms']['mean'])
        self.assertEqual(post['open_crossed_phase_boundary'], 0)
        self.assertEqual(active['open_crossed_phase_boundary'], 1)
        self.assertEqual(result['reconciliation']['ignored_starts_at_or_after_cutoff'], 2)
        final = summarize(self.source, self.plan)
        self.assertEqual(self.row(final, 'ACTIVE')['cohort_outcomes']['transport_error'], 1)
        self.assertEqual(self.row(final, 'POST')['duration_success_2xx_ms']['n'], 1)
        self.assertEqual(self.row(final, 'POST')['cohort_open_as_of'], 1)  # incomplete stays unresolved
        self.assertEqual(self.row(final, 'POST')['open_crossed_phase_boundary'], 1)

    def test_empty_log_null_denominators_and_cutoff_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'empty.csv'
            path.write_text(','.join(REQUEST_FIELDS) + '\n')
            result = summarize(path, self.plan)
            self.assertEqual(result['reconciliation']['included_starts'], 0)
            for row in result['rows']:
                self.assertIsNone(row['duration_success_2xx_ms']['mean'])
                self.assertIsNone(row['cohort_fractions']['failures_per_known_end'])
        result = summarize(self.source, self.plan, as_of='0')
        self.assertTrue(all(row['rates_per_second']['starts'] is None for row in result['rows']))

    def test_invalid_inputs_rejected(self):
        with self.source.open(newline='') as stream:
            original = list(csv.DictReader(stream))
        mutations = [lambda rs: rs.append(rs[0].copy()),
                     lambda rs: rs[0].update(run_id='other'),
                     lambda rs: rs[0].update(traffic_class='attack'),
                     lambda rs: rs[0].update(duration_ms='NaN'),
                     lambda rs: rs[0].update(duration_ms='9000'),
                     lambda rs: rs[0].update(http_status='500'),
                     lambda rs: rs[7].update(end_elapsed_seconds='10', duration_ms='1')]
        for mutate in mutations:
            rows = deepcopy(original)
            mutate(rows)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'bad.csv'
                with path.open('w', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=REQUEST_FIELDS)
                    writer.writeheader(); writer.writerows(rows)
                with self.assertRaises(ValueError):
                    summarize(path, self.plan)
        plan = deepcopy(self.plan)
        plan['phases'][1]['start_seconds'] = '4'
        with self.assertRaises(ValueError):
            summarize(self.source, plan)
        with self.assertRaises(ValueError):
            summarize(self.source, self.plan, as_of='13')

    def test_cli_deterministic_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'result.json'
            cmd = [sys.executable, '-B', '-m', 'experiments.summarize_service', str(self.source),
                   '--phases', str(FIXTURES / 'phases.json'), '--output', str(output)]
            subprocess.run(cmd, check=True, capture_output=True)
            actual = json.loads(output.read_text())
            self.assertEqual(actual['reconciliation']['known_ends'], 8)
            before = output.read_bytes()
            second = Path(directory) / 'second.json'
            subprocess.run(cmd[:-1] + [str(second)], check=True, capture_output=True)
            self.assertEqual(second.read_bytes(), before)
            self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            self.assertEqual(output.read_bytes(), before)

    def test_historical_event_rule_contract_and_synthetic_evaluator(self):
        # Import has no execution; call only the pure event function on synthetic objects.
        from experiments.stage15b_evaluation import FrozenDecision, FrozenEvent, event_metrics
        protocol = json.loads(Path('experiments/protocols/stage14_test_evaluation_protocol_v1.json').read_text())
        self.assertFalse(protocol['event_level']['require_available_at_before_or_at_actual_end'])
        event = FrozenEvent('synthetic', F('48.25'), F('48.75'), 'continuous')
        decision = FrozenDecision(48, F(48), F(49), F(49), True)
        result = event_metrics((decision,), event)
        self.assertTrue(result['event_detected'])
        self.assertEqual(result['detection_delay_seconds'], F('.75'))
        self.assertGreater(result['detection_time'], event.end)
        from experiments.stage15b_reproduce import independent_event
        self.assertEqual(independent_event((decision,), event), result)
        touching = FrozenDecision(49, F(49), F(50), F(50), True)
        self.assertFalse(event_metrics((touching,), event)['event_detected'])

    def test_documentary_development_plan_uses_real_fields_and_is_not_executable(self):
        from simulator.experiment_config import ExperimentConfig
        plan = json.loads(Path('experiments/protocols/development_service_plan_20261027.json').read_text())
        self.assertFalse(plan['runnable'])
        with self.assertRaises(ValueError):
            ExperimentConfig.from_dict(plan)
        config = ExperimentConfig()
        field_paths = set(plan['fixed_configuration_fields_proposed']) | set(plan['configuration_fields_to_resolve_before_generation'])
        for block in plan['blocks']:
            field_paths.update(block['fixed_fields'])
            field_paths.update(block['factor_fields'])
            field_paths.update(block.get('matched_fields', []))
            field_paths.update(block.get('control_overrides', {}))
        for path in field_paths:
            value = config
            for key in path.split('.'):
                value = getattr(value, key)


if __name__ == '__main__':
    unittest.main()
