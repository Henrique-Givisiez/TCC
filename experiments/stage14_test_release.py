"""Hash-bound, campaign-specific collection authority. Never releases analysis."""
from datetime import datetime
from pathlib import Path

from analysis.detection.inputs import ContractError


OPERATIONS = ['scientific_execution', 'technical_validation']
PROHIBITIONS = dict(fitting=True, calibration=True, tuning=True,
                    scientific_scoring=True, scientific_evaluation=True,
                    detector_changes=True, threshold_changes=True, automatic_retry=True)


def campaign_identity(plan):
    # The campaign is identified before release issuance. The complete plan in
    # the checkpoint additionally pins the release SHA, avoiding self-reference.
    from experiments.stage14_campaign import digest
    return digest({k: v for k, v in plan.items() if k != 'release'})


def release_document(plan, *, authorized_at, authorization):
    """Administrative constructor only; validation independently reloads inputs."""
    return dict(release_version=1, status='AUTHORIZED', partition='test',
        campaign_identity=campaign_identity(plan), authority=plan['authority'],
        expected_runs=len(plan['entries']), ordered_matrix_identities=[
            e['matrix_identity'] for e in plan['entries']],
        scientific_execution_authorized=True, allowed_operations=list(OPERATIONS),
        prohibitions=dict(PROHIBITIONS), authorized_at_utc=authorized_at,
        human_authorization=authorization)


def validate_release(path, expected_sha256, *, binding_path, binding_sha256,
                     evaluation_path=None, evaluation_sha256=None,
                     operation='scientific_execution', run=None):
    """Reload frozen metadata/environment; absent or mismatched release is fatal.

    This routine opens no observations or labels and never launches a process.
    The default binding stays LOCKED: this explicit artifact is a separate,
    narrowly scoped authorization, not a mutation of historical authority.
    """
    if path is None or not expected_sha256:
        raise ContractError('TEST locked: scientific execution forbidden; execution LOCKED; explicit campaign release path and SHA256 required')
    from experiments import stage14_scientific as scientific
    from experiments.stage14_campaign import FrozenExecutor
    try:
        ref = dict(path=str(Path(path).resolve().relative_to(scientific.ROOT.resolve())),
                   sha256=expected_sha256)
        _, release = scientific.checked_reference(ref)
        authority = release['authority']
        binding_ref = dict(path=str(Path(binding_path).resolve().relative_to(scientific.ROOT.resolve())),
                           sha256=binding_sha256)
        if authority['binding'] != binding_ref:
            raise ContractError('Release binding mismatch')
        evaluation = authority['evaluation_protocol']
        if evaluation_path is not None and evaluation != dict(
                path=str(Path(evaluation_path).resolve().relative_to(scientific.ROOT.resolve())),
                sha256=evaluation_sha256):
            raise ContractError('Release evaluation protocol mismatch')
        # No release argument here: reconstruct the frozen, pre-release identity.
        plan = FrozenExecutor(binding_path, binding_sha256,
            scientific.ROOT/evaluation['path'], evaluation['sha256']).plan()
        if authority != plan['authority']:
            raise ContractError('Release HEAD/environment/protocol/matrix/seed/freeze authority mismatch')
        if (type(release['release_version']) is not int or release['release_version'] != 1
                or release['status'] != 'AUTHORIZED' or release['partition'] != 'test'
                or release['scientific_execution_authorized'] is not True
                or release['allowed_operations'] != OPERATIONS
                or release['prohibitions'] != PROHIBITIONS
                or any(value is not True for value in release['prohibitions'].values())
                or operation not in OPERATIONS
                or release['campaign_identity'] != campaign_identity(plan)
                or type(release['expected_runs']) is not int
                or release['expected_runs'] != len(plan['entries'])
                or release['ordered_matrix_identities'] != [e['matrix_identity'] for e in plan['entries']]
                or not isinstance(release['human_authorization'], str)
                or not release['human_authorization'].strip()
                or datetime.fromisoformat(release['authorized_at_utc']).utcoffset() is None):
            raise ContractError('Invalid campaign release scope/identity/permissions')
        if run is not None and run not in [e['order'] for e in plan['entries']]:
            raise ContractError('Run outside released campaign')
        return dict(reference=ref, campaign_identity=release['campaign_identity'],
                    authority=authority, execution_authorized=True,
                    allowed_operations=list(OPERATIONS), prohibitions=dict(PROHIBITIONS))
    except ContractError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ContractError(f'Invalid campaign release: {exc}') from exc
