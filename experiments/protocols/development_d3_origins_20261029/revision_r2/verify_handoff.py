"""Read-only validation of the R2 handoff; never invokes operational preflight."""
from unittest.mock import patch
import json
from experiments import development_d3_origins_revision as revision
from experiments import development_d3_origins_revision_ops as ops


def main():
    with ops.release_context():
        plan,validated=ops.get_plan();handoff=revision.validate_handoff(plan)
        with patch.object(ops.previous,'REVIEWED_SHA256',handoff['review_sha256']):
            predecessors=ops.previous.check_predecessors(plan,1)
            assert predecessors[-1]['entry']==revision.FIRST
        with patch.object(ops.previous,'REVIEWED_SHA256',plan['processing_revision']['original_review']['sha256']):
            try:ops.previous.check_predecessors(plan,1)
            except ValueError as exc:assert 'reviewed-sha256' in str(exc)
            else:raise AssertionError('Old failed review must not authorize the next entry')
        expected=revision.handoff_record(plan)
        wrong={**expected,'review_sha256':'0'*64}
        with patch.object(revision.origins,'read',side_effect=lambda path:wrong if str(path).endswith('/handoff.json') else original_read(path)):
            try:revision.validate_handoff(plan)
            except ValueError as exc:assert 'handoff' in str(exc)
            else:raise AssertionError('Changed handoff must be rejected')
        entry_ops=revision.ROOT/plan['results_root']/'operations'/revision.FIRST
        try:ops.previous.operations.ensure_single_experimental_attempt(entry_ops)
        except RuntimeError as exc:assert 'retries' in str(exc)
        else:raise AssertionError('Consumed N1 attempt must block retry')
    print(json.dumps(dict(prospective_predecessor_gate_passed=True,old_review_hash_rejected=True,
        altered_handoff_rejected=True,consumed_attempt_retry_rejected=True,
        next_entry=handoff['next_entry'],review_sha256=handoff['review_sha256'],preflight_executed=False,docker_accessed=False)))


original_read=revision.origins.read
if __name__=='__main__':main()
