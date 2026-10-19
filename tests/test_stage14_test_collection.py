"""Administrative tests only: no detector execution or observation statistics."""
from copy import deepcopy
import hashlib
import json
import unittest

from experiments import stage14_test_collection as collection


class CollectionTests(unittest.TestCase):
    def test_paired_design_rejects_missing_duplicate_and_extra(self):
        rows=[dict(order=i*3+j,seed=i,scenario=scenario)
              for i in range(16) for j,scenario in enumerate('BCP')]
        collection.pairing(rows)
        for bad in (rows[:-1], rows+[rows[0]], [rows[0]]+rows[0:-1]):
            with self.assertRaises(ValueError):
                collection.pairing(bad)
        bad=deepcopy(rows);bad[0]['seed']=100
        with self.assertRaises(ValueError):
            collection.pairing(bad)

    def test_operation_log_rejects_extra_attempt(self):
        logs=[json.loads(x) for x in (collection.DIRECTORY/'operations.jsonl').read_text().splitlines()]
        orders=list(range(19,67))
        collection.operations(logs,orders)
        with self.assertRaises(ValueError):
            collection.operations(logs+[next(x for x in logs if x['event']=='entry_start')],orders)

    def test_frozen_collection_reproduces_from_existing_evidence(self):
        inventory,freeze=collection.audit()
        for name,value in [('test_collection_inventory.json',inventory),('test_collection_freeze_manifest.json',freeze)]:
            self.assertEqual((collection.DIRECTORY/name).read_bytes(),collection.encode(value))
            self.assertEqual(collection.encode(value),collection.encode(json.loads(collection.encode(value))))
        self.assertEqual(hashlib.sha256(collection.encode(inventory)).hexdigest(),freeze['inventory']['sha256'])
        self.assertEqual(len(inventory['entries']),48)
        self.assertTrue(all(e['dataset_valid'] and e['analysis_eligible'] and e['attempts']==1 for e in inventory['entries']))
        self.assertFalse(freeze['scientific_evaluation_performed_before_freeze'])


if __name__=='__main__':
    unittest.main()
