"""Operational campaign coordinator. TEST execution remains locked by its executor.

No detector, scoring, label parsing or scientific evaluation lives here. The CLI
has no release switch and no selectable executor. Tests inject DEVELOPMENT fakes.
"""
import argparse
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
from datetime import datetime, timezone

from analysis.detection.inputs import ContractError
from experiments import stage14_scientific as scientific


STATES = ('PENDING', 'RUNNING', 'COMPLETED_VALID', 'FAILED', 'INCOMPLETE', 'INVALID')
EXCEPTIONAL = ('FAILED', 'INCOMPLETE', 'INVALID')


def digest(value):
    return hashlib.sha256(scientific.encode(value)).hexdigest()


def atomic_json(path, value):
    """Durable same-directory replace; failure leaves the old checkpoint intact."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(scientific.encode(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise ContractError(f'Unreadable checkpoint/metadata: {path}') from exc


def inventory(root):
    """Byte integrity only; never parses observations or labels."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ContractError('Missing or symlinked scientific output')
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ContractError('Symlink in scientific output')
        if path.is_file():
            result[str(path.relative_to(root))] = dict(size=path.stat().st_size,
                                                      sha256=scientific.sha(path))
        elif not path.is_dir():
            raise ContractError('Non-regular scientific artifact')
    return result


def checked_files(root, records):
    for record in records:
        path = Path(root) / record['path']
        if (not path.resolve().is_relative_to(Path(root).resolve())
                or path.is_symlink() or not path.is_file()
                or scientific.sha(path) != record['sha256']
                or ('bytes' in record and path.stat().st_size != record['bytes'])):
            raise ContractError(f"Technical artifact integrity mismatch: {record['path']}")


class TechnicalFailure(ContractError):
    def __init__(self, state, message):
        if state not in EXCEPTIONAL:
            raise ValueError('Not an exceptional state')
        self.state = state
        super().__init__(message)


class FrozenExecutor:
    """Administrative adapter to the frozen scientific executor, with no release.

    Execution is deliberately fatal today. A future scientific release requires
    a separately reviewed executor contract, not an argument to this runner.
    """
    def __init__(self, binding, binding_sha256, evaluation, evaluation_sha256):
        self.binding = Path(binding).resolve()
        self.binding_sha256 = binding_sha256
        self.evaluation = Path(evaluation).resolve()
        self.evaluation_sha256 = evaluation_sha256

    def plan(self):
        binding, _, _, documents = scientific.load_bundle(self.binding, self.binding_sha256)
        evaluation_ref = dict(path=str(self.evaluation.relative_to(scientific.ROOT)),
                              sha256=self.evaluation_sha256)
        _, evaluation = scientific.checked_reference(evaluation_ref)
        if evaluation['status'] != 'FROZEN' or evaluation['test_execution'] != 'LOCKED':
            raise ContractError('Requires frozen, locked evaluation protocol')
        for key in ('protocol_v2', 'seed_plan', 'matrix'):
            source = 'protocol' if key == 'protocol_v2' else key
            if evaluation[key] != binding['references'][source]:
                raise ContractError('Evaluation/campaign reference mismatch')
        scientific.checked_reference(evaluation['four_method_freeze'])
        current = scientific.observe_environment()
        check = scientific.environment_check(documents['environment_lock']['reference'], current)
        if check['fatal'] or current['dynamic']['git_status']:
            raise ContractError(f"Authority/environment mismatch: {check['fatal']}; clean tree required")
        rows = [r for r in documents['matrix']['runs'] if r['partition'] == 'test']
        paired = evaluation['paired_design']
        if (len(rows) != paired['total_entries']
                or len({r['order'] for r in rows}) != len(rows)
                or any(a['order'] >= b['order'] for a, b in zip(rows, rows[1:]))
                or set(r['seed'] for r in rows) != set(paired['seeds'])
                or any(Counter(r['scenario'] for r in rows if r['seed'] == seed)
                       != Counter(paired['scenarios']) for seed in paired['seeds'])):
            raise ContractError('Frozen TEST pairing/order mismatch')
        authority = dict(head=binding['campaign_git_head'], binding=dict(
            path=str(self.binding.relative_to(scientific.ROOT)), sha256=self.binding_sha256),
            environment=binding['references']['definitive_environment_lock'],
            evaluation_protocol=evaluation_ref, four_method_freeze=evaluation['four_method_freeze'],
            references=binding['references'])
        entries = []
        for row in rows:  # Never sort, regroup, randomize or regenerate the matrix.
            if row['role'] != 'test' or digest(row['config']) != row['config_sha256']:
                raise ContractError('Frozen row role/configuration mismatch')
            destination = scientific.ROOT/scientific.OUTPUT_ROOT / (
                f"{row['order']:02d}_test_{row['seed']}_{row['scenario']}")
            entries.append(dict(order=row['order'], seed=row['seed'], scenario=row['scenario'],
                role=row['role'], matrix_identity=digest(row), config_sha256=row['config_sha256'],
                output=str(destination), configuration=row['config']))
        known = {f"{r['order']:02d}_{r['partition']}_{r['seed']}_{r['scenario']}"
                 for r in documents['matrix']['runs']}
        output_root = scientific.ROOT/scientific.OUTPUT_ROOT
        if output_root.exists() and any(p.name not in known or p.is_symlink() or not p.is_dir()
                                       for p in output_root.iterdir()):
            raise ContractError('Unexpected scientific output identity')
        return dict(authority=authority, entries=entries)

    def require_execution(self):
        # There is intentionally no flag, token, environment variable or alternate
        # backend in the CLI that bypasses the current executor's fatal TEST guard.
        raise ContractError('TEST execution LOCKED: no scientific release capability exists')

    def preflight(self, entry):
        metadata = scientific.preflight_entry(self.binding, self.binding_sha256,
            partition='test', run=entry['order'], seed=entry['seed'], scenario=entry['scenario'],
            configuration=entry['configuration'])
        if metadata['status'] != 'dry_run_ready':
            raise ContractError('Entry preflight rejected')
        return metadata

    def execute(self, entry):
        return scientific.execute_entry(self.binding, self.binding_sha256,
                                       partition='test', run=entry['order'], execute=True)

    def cleanup(self, entry):
        # Resource teardown belongs to the existing executor/run_recorded finally
        # blocks. Never kill unrelated processes or remove scientific evidence.
        current = scientific.observe_environment()
        if current['active_containers'] or current['residual_processes']:
            raise ContractError('Executor cleanup incomplete; operator review required')
        _, _, _, documents = scientific.load_bundle(self.binding, self.binding_sha256)
        if (scientific.environment_check(documents['environment_lock']['reference'], current)['fatal']
                or current['dynamic']['git_status']):
            raise ContractError('Authority changed during execution/cleanup')
        return dict(status='verified_idle', resource_owner='scientific_executor')

    def validate(self, entry):
        """Verify existing technical certificates and lineage; no efficacy analysis."""
        root = Path(entry['output'])
        required = ('scientific_run_after.json', 'raw/run_status.json',
                    'stage8/dataset_manifest.json', 'stage9/validation_report.json',
                    'stage10/feature_manifest.json')
        if any(not (root/p).is_file() for p in required):
            raise TechnicalFailure('INCOMPLETE', 'Missing completion/Stage8/9/10 certificate')
        try:
            # Reject symlinks before opening any certificate through them.
            files = inventory(root)
            after, status, stage8, stage9, stage10 = [read_json(root/p) for p in required]
            if status['status'] != 'completed':
                raise TechnicalFailure('INCOMPLETE', 'Simulation has no normal completion')
            if after['status'] != 'completed':
                raise TechnicalFailure('FAILED', 'Scientific executor did not complete')
            if stage9['dataset_valid'] is not True or stage9['analysis_eligible'] is not True:
                raise TechnicalFailure('INVALID', 'Stage9 not valid/eligible')
            run_id = status['run_id']
            dataset_hash = scientific.sha(root/'stage8/dataset_manifest.json')
            if (after['row']['order'] != entry['order'] or after['role'] != entry['role']
                    or after['configuration'] != entry['configuration']
                    or after['binding']['sha256'] != self.binding_sha256
                    or after['lineage']['run_id'] != run_id
                    or stage8['run_id'] != run_id or stage9['run_id'] != run_id
                    or stage10['source_run_id'] != run_id
                    or stage9['dataset_manifest_sha256'] != dataset_hash
                    or stage10['dataset_manifest_sha256'] != dataset_hash
                    or stage10['window']['planned_duration_seconds']
                       != str(entry['configuration']['duration_seconds'])
                    or not stage10['network_direction']['supported']):
                raise TechnicalFailure('INVALID', 'Run/configuration/Stage8/9/10 lineage mismatch')
            checked_files(root, [dict(path=p, sha256=h)
                                for p, h in after['outputs_sha256'].items()])
            if set(after['outputs_sha256']) != set(files) - {'scientific_run_after.json'}:
                raise TechnicalFailure('INVALID', 'Executor output inventory is not exhaustive')
            checked_files(root/'stage8', stage8['files'])
            checked_files(root/'stage8', stage10['input_files'])
            checked_files(root/'stage10', stage10['outputs'])
            checked_files(root/'stage10', [stage10['stage9_validation_report']])
            if stage10['stage9_validation_report']['sha256'] != scientific.sha(root/'stage9/validation_report.json'):
                raise TechnicalFailure('INVALID', 'Stage9/10 certificate mismatch')
            return dict(status='valid', run_id=run_id, dataset_valid=True,
                        analysis_eligible=True, inventory=files, inventory_sha256=digest(files))
        except TechnicalFailure:
            raise
        except (ContractError, KeyError, TypeError, ValueError, OSError) as exc:
            raise TechnicalFailure('INVALID', f'Technical certificate rejected: {exc}') from exc


@contextmanager
def campaign_lock(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory/'campaign.lock').open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ContractError('Campaign already owned by an active coordinator') from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


class Campaign:
    def __init__(self, directory, executor):
        self.directory = Path(directory)
        self.path = self.directory/'campaign_state.json'
        self.executor = executor

    def log(self, event, **details):
        with (self.directory/'operations.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(at=scientific.now(), event=event, **details), sort_keys=True) + '\n')
            stream.flush()
            os.fsync(stream.fileno())

    def save(self, checkpoint):
        checkpoint['updated_at'] = scientific.now()
        atomic_json(self.path, checkpoint)
        self.log('checkpoint_updated', campaign=checkpoint['campaign_identity'])

    def transition(self, checkpoint, entry, state, **details):
        old = entry['state']
        if not ((old == 'PENDING' and state == 'RUNNING') or
                (old == 'RUNNING' and state in ('COMPLETED_VALID', *EXCEPTIONAL))):
            raise ContractError(f'Forbidden transition: {old} -> {state}')
        entry.update(state=state, **details)
        self.save(checkpoint)
        self.log('transition', order=entry['plan']['order'], seed=entry['plan']['seed'],
                 scenario=entry['plan']['scenario'], previous=old, state=state, **details)

    def initialize(self, plan):
        if self.path.exists() or self.path.is_symlink():
            raise ContractError('Checkpoint exists: use resume; never overwrite')
        if (self.directory/'operations.jsonl').exists() or (self.directory/'stop_requested.json').exists():
            raise ContractError('Administrative directory already used')
        if not plan['entries']:
            raise ContractError('Empty campaign')
        for entry in plan['entries']:
            if Path(entry['output']).exists() or Path(entry['output']).is_symlink():
                raise ContractError('Scientific output collision before initialization')
        checkpoint = dict(schema_version=1, campaign_identity=digest(plan), plan=deepcopy(plan),
            total_entries=len(plan['entries']), created_at=scientific.now(),
            entries=[dict(plan=deepcopy(p), state='PENDING', attempt=1, validation=None,
                          reason=None, started_at=None, finished_at=None) for p in plan['entries']])
        self.save(checkpoint)
        return checkpoint

    def load(self, plan):
        checkpoint = read_json(self.path)
        try:
            entries = checkpoint['entries']
            if (checkpoint['schema_version'] != 1 or checkpoint['campaign_identity'] != digest(plan)
                    or checkpoint['plan'] != plan or checkpoint['total_entries'] != len(plan['entries'])
                    or len(entries) != len(plan['entries'])):
                raise ContractError('Campaign identity/checkpoint mismatch')
            pending_seen = False
            exceptional_seen = False
            pending_entry_seen = False
            for entry, planned in zip(entries, plan['entries']):
                if (entry['plan'] != planned or entry['state'] not in STATES or entry['attempt'] != 1):
                    raise ContractError('Invalid entry identity/state/attempt')
                if entry['state'] != 'COMPLETED_VALID':
                    pending_seen = True
                elif pending_seen:
                    raise ContractError('Out-of-order completed entry')
                if entry['state'] == 'COMPLETED_VALID':
                    if not entry['validation'] or entry['validation']['status'] != 'valid':
                        raise ContractError('Completed entry missing validation')
                if entry['state'] in ('RUNNING', *EXCEPTIONAL):
                    if exceptional_seen or pending_entry_seen:
                        raise ContractError('Invalid execution prefix')
                    exceptional_seen = True
                pending_entry_seen |= entry['state'] == 'PENDING'
        except ContractError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractError('Malformed checkpoint') from exc
        return checkpoint

    def run(self, *, resume=False):
        with campaign_lock(self.directory):
            plan = self.executor.plan()  # Revalidate before checkpoint/output access.
            checkpoint = self.load(plan) if resume else None
            # This gate is before initialization, output reads and RUNNING. CLI
            # cannot start/resume real TEST while the scientific guard is LOCKED.
            self.executor.require_execution()
            if checkpoint is None:
                checkpoint = self.initialize(plan)
            for entry in checkpoint['entries']:
                state = entry['state']
                if state in EXCEPTIONAL:
                    raise ContractError(f'STOP: {state}; explicit human recovery required')
                if state == 'RUNNING':
                    # Exclusive flock proves the previous coordinator no longer
                    # owns this campaign. Scientific completion is unknown; do
                    # not inspect, finish, delete or repeat the orphaned attempt.
                    self.transition(checkpoint, entry, 'INCOMPLETE',
                        reason='Orphan RUNNING checkpoint; scientific completion unknown; human review required',
                        finished_at=scientific.now())
                    raise ContractError('STOP: orphan RUNNING; no automatic recovery/retry')
            # Recheck EVERY completed receipt before advancing any pending row.
            for entry in checkpoint['entries']:
                if entry['state'] == 'COMPLETED_VALID':
                    actual = self.executor.validate(entry['plan'])
                    if actual != entry['validation']:
                        raise ContractError('STOP: completed artifact/receipt hash mismatch')
                elif Path(entry['plan']['output']).exists() or Path(entry['plan']['output']).is_symlink():
                    raise ContractError('STOP: unexpected output for PENDING entry')
            for entry in checkpoint['entries']:
                if entry['state'] == 'COMPLETED_VALID':
                    continue
                if (self.directory/'stop_requested.json').exists():
                    self.log('controlled_stop_before_next_entry', order=entry['plan']['order'])
                    return checkpoint
                if self.executor.plan() != plan:
                    raise ContractError('Authority or ordered plan changed')
                self.executor.require_execution()
                self.executor.preflight(entry['plan'])
                destination = Path(entry['plan']['output'])
                if destination.exists() or destination.is_symlink():
                    raise ContractError('Output collision immediately before RUNNING')
                self.transition(checkpoint, entry, 'RUNNING', started_at=scientific.now(),
                                coordinator_pid=os.getpid())
                try:
                    self.log('entry_start', order=entry['plan']['order'])
                    self.executor.execute(entry['plan'])
                    validation = self.executor.validate(entry['plan'])
                    if validation.get('status') != 'valid':
                        raise TechnicalFailure('INVALID', 'Technical validation did not certify validity')
                    cleanup = self.executor.cleanup(entry['plan'])
                    self.log('technical_validation', order=entry['plan']['order'],
                             status=validation['status'], cleanup=cleanup)
                    self.transition(checkpoint, entry, 'COMPLETED_VALID', validation=validation,
                                    cleanup=cleanup, finished_at=scientific.now())
                except (Exception, KeyboardInterrupt) as exc:
                    # Never downgrade an already durable COMPLETED_VALID after a
                    # logging failure. Resume revalidates it, never reruns it.
                    if entry['state'] == 'COMPLETED_VALID':
                        raise
                    state = (exc.state if isinstance(exc, TechnicalFailure) else
                             'INCOMPLETE' if isinstance(exc, KeyboardInterrupt) else 'FAILED')
                    try:
                        cleanup = self.executor.cleanup(entry['plan'])
                    except Exception as cleanup_error:
                        cleanup = dict(status='operator_review_required', error=str(cleanup_error))
                    self.transition(checkpoint, entry, state, reason=str(exc) or type(exc).__name__,
                                    cleanup=cleanup, finished_at=scientific.now())
                    raise ContractError(f'STOP: {state}; attempt preserved; no retry: {exc}') from exc
            return checkpoint


def status(directory):
    """Read only checkpoint metadata. No environment queries or scientific IO."""
    checkpoint = read_json(Path(directory)/'campaign_state.json')
    try:
        counts = Counter(e['state'] for e in checkpoint['entries'])
        if set(counts) - set(STATES) or sum(counts.values()) != checkpoint['total_entries']:
            raise ValueError('Invalid state counts')
        touched = [e for e in checkpoint['entries'] if e['state'] != 'PENDING']
        elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(checkpoint['created_at'])).total_seconds()
        return dict(campaign_identity=checkpoint['campaign_identity'], total=checkpoint['total_entries'],
            **{s.lower(): counts[s] for s in STATES},
            current_or_last_entry=touched[-1]['plan']['order'] if touched else None,
            created_at=checkpoint['created_at'], updated_at=checkpoint['updated_at'],
            administrative_elapsed_seconds=max(0, elapsed),
            stop_requested=(Path(directory)/'stop_requested.json').exists())
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractError('Malformed checkpoint status') from exc


def request_stop(directory):
    """Stop at next safe entry boundary; never signal/kill a scientific process."""
    directory = Path(directory)
    status(directory)  # Must be an existing campaign. No scientific artifact IO.
    target = directory/'stop_requested.json'
    if not target.exists():
        atomic_json(target, dict(requested_at=scientific.now(), policy='finish_current_then_stop'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('start', 'resume', 'status', 'abort'))
    parser.add_argument('--campaign-dir', type=Path, required=True)
    parser.add_argument('--binding', type=Path)
    parser.add_argument('--binding-sha256')
    parser.add_argument('--evaluation-protocol', type=Path)
    parser.add_argument('--evaluation-sha256')
    args = parser.parse_args()
    directory = args.campaign_dir.resolve()
    scientific_root = (scientific.ROOT/scientific.OUTPUT_ROOT).resolve()
    if directory == scientific_root or scientific_root in directory.parents:
        parser.error('Administrative campaign directory must be outside scientific output root')
    try:
        if args.action == 'status':
            result = status(directory)
        elif args.action == 'abort':
            request_stop(directory)
            result = dict(status='stop_requested_at_entry_boundary')
        else:
            required = (args.binding, args.binding_sha256, args.evaluation_protocol, args.evaluation_sha256)
            if not all(required):
                parser.error('start/resume require explicit binding/evaluation paths and SHA256')
            executor = FrozenExecutor(*required)
            Campaign(directory, executor).run(resume=args.action == 'resume')
            result = status(directory)
        print(json.dumps(result, indent=2))
    except (ContractError, OSError, ValueError) as exc:
        parser.exit(2, f'STOP: {exc}\n')


if __name__ == '__main__':
    main()
