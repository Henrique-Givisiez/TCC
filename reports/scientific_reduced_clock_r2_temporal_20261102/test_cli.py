"""Testes da seleção/apresentação; não importam ou executam detectores."""
import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('temporal_figures_cli', Path(__file__).with_name('generate.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
BASE = ['--repo', '.', '--plan', 'plan.json', '--checkpoint', 'manifest.json',
        '--checkpoint-sha256', '0'*64, '--output', '/tmp/clock-r2-cli-test']


class SelectionTests(unittest.TestCase):
    def parse(self, *options):
        return module.parse_args(BASE + list(options))

    def test_legacy_keeps_distinct_temporal_and_map_support(self):
        a = self.parse()
        self.assertTrue(a.legacy)
        self.assertEqual(a.features, ['request_starts', 'mean_duration_ms'])
        self.assertEqual(a.scenarios, ['M16', 'E16'])
        self.assertEqual(a.temporal_blocks, [1])
        self.assertEqual(a.heatmap_blocks, list(range(1, 13)))

    def test_cpu_single_execution(self):
        a = self.parse('--features', 'mean_cpu_percent', '--scenarios', 'E16',
                       '--blocks', '1', '--plots', 'temporal')
        self.assertFalse(a.legacy)
        self.assertEqual(a.features, ['mean_cpu_percent'])
        self.assertEqual(a.temporal_blocks, [1])
        self.assertEqual(a.plots, ['temporal'])

    def test_all_expands_each_universe(self):
        a = self.parse('--features', 'all', '--scenarios', 'all', '--blocks', 'all', '--plots', 'all')
        self.assertEqual(a.features, module.ALL_FEATURES)
        self.assertEqual(a.scenarios, module.SCENARIOS)
        self.assertEqual(a.blocks, list(range(1, 13)))
        self.assertEqual(a.plots, module.PLOTS)

    def test_blocks_are_numeric_sorted_and_have_distinct_filenames(self):
        a = self.parse('--blocks', '12', '3', '1', '--plots', 'heatmap')
        self.assertEqual(a.heatmap_blocks, [1, 3, 12])
        self.assertEqual(module.block_tag(a.blocks), 'B01_B03_B12')
        self.assertNotEqual(module.block_tag([1, 12]), module.block_tag(list(range(1, 13))))

    def test_partial_blocks_with_delay_warn_without_claiming_subset(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            a = self.parse('--blocks', '2', '--plots', 'delay')
        self.assertIn('suporte completo B01–B12', stderr.getvalue())
        self.assertEqual(a.blocks, [2])

    def test_invalid_arguments_fail_before_artifact_io(self):
        invalid = [('--features', 'rtt'), ('--scenarios', 'M17'), ('--plots', 'context'),
                   ('--blocks', '0'), ('--blocks', '13'), ('--blocks', 'B01'),
                   ('--features',), ('--blocks',), ('--plots',), ('--scenarios',),
                   ('--blocks', 'all', '1'), ('--features', 'all', 'request_starts'),
                   ('--blocks', '1', '1'), ('--plots', 'temporal', 'temporal')]
        for options in invalid:
            with self.subTest(options=options), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as exc:
                    self.parse(*options)
                self.assertEqual(exc.exception.code, 2)

    def test_consumed_reference_rejects_wrong_hash(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / 'input.json'
            p.write_text('{}')
            reader = module.Inputs(Path(root))
            with self.assertRaisesRegex(ValueError, 'SHA256 divergente'):
                reader.read(p, '0'*64)


if __name__ == '__main__':
    unittest.main()
