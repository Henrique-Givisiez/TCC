"""Read-only Stage 9 checks. No detector, correction, time bins or traffic model."""
import argparse
from collections import Counter
import csv
import hashlib
import ipaddress
import json
import math
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from experiments.dataset_provenance import sha256_file
from experiments.dataset_schema import schema

SCIENTIFIC = {'requests': 'raw/service/request_log.csv', 'rtt': 'raw/service/rtt_log.csv',
              'packets': 'raw/traffic/traffic_capture.csv', 'metrics': 'raw/infrastructure/simulation_metrics.csv',
              'attacks': 'raw/attacks/attack_events.csv'}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def decode_json(text):
    def reject(value):
        raise ValueError(f'Nonfinite JSON number: {value}')
    def number(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError('Nonfinite JSON number')
        return result
    return json.loads(text, object_pairs_hook=unique_object, parse_constant=reject, parse_float=number)


def read_json(path):
    return decode_json(path.read_text(encoding='utf-8'))


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def burst_allows(elapsed, attack):
    start = attack['start_seconds']
    end = start + attack['duration_seconds']
    if not start <= elapsed < end:
        return False
    period, duration = attack['burst']['period_seconds'], attack['burst']['duration_seconds']
    index = max(0, math.floor((elapsed - start) / period))
    beginning = start + index * period
    return beginning <= elapsed < min(beginning + duration, end)


class DatasetValidator:
    def __init__(self, directory):
        self.root = Path(directory).resolve()
        self.checks = []
        self.manifest = None
        self.manifest_sha256 = None
        self.entries = {}
        self.tables = {}

    def check(self, identifier, passed, message, evidence=None, severity='ERROR', stage='semantic', affects=None):
        if affects is None:
            affects = ['dataset_valid'] if severity == 'ERROR' else []
        self.checks.append(dict(check_id=identifier, stage=stage, severity=severity, passed=passed,
                               affects=affects, message=message,
                               evidence=evidence or {}))

    def violations(self, identifier, failures, message, context=None, **kwargs):
        self.check(identifier, not failures, message,
                   dict(context or {}, violation_count=len(failures), examples=failures[:10]), **kwargs)

    def gate(self, identifier, passed, message, evidence=None):
        self.check(identifier, passed, message, evidence, severity='INFO', stage='quality', affects=['analysis_eligible'])

    def safe_path(self, relative):
        if not isinstance(relative, str) or not relative or '\\' in relative:
            return None
        pure = PurePosixPath(relative)
        if pure.is_absolute() or '..' in pure.parts or pure.as_posix() != relative:
            return None
        path = self.root / relative
        try:
            if self.root not in path.resolve().parents:
                return None
        except (OSError, RuntimeError, ValueError):
            return None
        current = path
        while current != self.root:
            if current.is_symlink():
                return None
            current = current.parent
        return path

    def json_artifact(self, relative, kind, required=True):
        path = self.safe_path(relative)
        if path is None or not path.is_file():
            self.check('CANONICAL_ARTIFACT_PRESENT', False, 'Canonical JSON artifact must be safely present',
                       dict(path=relative), stage='structural', severity='ERROR' if required else 'WARNING')
            return None
        try:
            value = read_json(path)
            if not isinstance(value, kind):
                raise ValueError(f'Expected {kind.__name__}')
        except (OSError, ValueError, UnicodeError) as exc:
            self.check('JSON_PARSEABLE', False, 'JSON artifact is malformed', dict(path=relative, reason=str(exc)), stage='structural')
            return None
        self.check('JSON_PARSEABLE', True, 'JSON artifact is parseable', dict(path=relative), stage='structural')
        return value

    def structure(self):
        manifest = self.json_artifact('dataset_manifest.json', dict)
        if manifest is None:
            return None
        self.manifest = manifest
        self.manifest_sha256 = sha256_file(self.root / 'dataset_manifest.json')
        version = manifest.get('schema_version')
        self.check('MANIFEST_SCHEMA_SUPPORTED', type(version) is int and version == 1,
                   'Only dataset schema version 1 is supported', dict(version=version), stage='structural')
        shape = (isinstance(manifest.get('run_id'), str) and bool(manifest['run_id']) and
                 manifest.get('status') in ('completed', 'incomplete') and isinstance(manifest.get('files'), list))
        self.check('MANIFEST_FIELDS_VALID', shape, 'Manifest must identify a run, status and file index', stage='structural')
        if not shape or type(version) is not int or version != 1:
            return None
        safe, duplicate, malformed, absent, hashes, sizes = [], [], [], [], [], []
        for entry in manifest['files']:
            if not isinstance(entry, dict):
                malformed.append(str(entry)); continue
            name = entry.get('path')
            path = self.safe_path(name)
            if path is None:
                safe.append(dict(path=name)); continue
            if name in self.entries:
                duplicate.append(name)
            self.entries[name] = entry
            digest, size = entry.get('sha256'), entry.get('bytes')
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest) or type(size) is not int or size < 0:
                malformed.append(name); continue
            if not path.is_file():
                absent.append(dict(path=name, optional=entry.get('group') == 'evidence')); continue
            try:
                actual_size, actual_hash = path.stat().st_size, sha256_file(path)
                if size != actual_size:
                    sizes.append(dict(path=name, expected=size, observed=actual_size))
                if digest != actual_hash:
                    hashes.append(dict(path=name, expected=digest, observed=actual_hash))
            except OSError as exc:
                hashes.append(dict(path=name, reason=str(exc)))
        for key, failures, message in [
            ('DATASET_PATH_SAFE', safe, 'Indexed paths must stay inside dataset and not traverse symlinks'),
            ('FILE_INDEX_UNIQUE', duplicate, 'Exported file paths must be unique'),
            ('FILE_INDEX_FIELDS_VALID', malformed, 'Every indexed file needs a SHA256 and nonnegative byte size'),
            ('FILE_HASH_MATCH', hashes, 'Present indexed files must match their SHA256'),
            ('FILE_SIZE_MATCH', sizes, 'Present indexed files must match their byte sizes')]:
            self.violations(key, failures, message, stage='structural')
        self.violations('INDEXED_FILE_PRESENT', [x for x in absent if not x['optional']], 'Indexed canonical/scientific files must exist', stage='structural')
        self.violations('OPTIONAL_EVIDENCE_PRESENT', [x for x in absent if x['optional']], 'Missing optional evidence limits auditability', severity='WARNING', stage='structural')
        references = {'configuration': 'metadata/effective_config.json', 'run_status': 'metadata/run_status.json', 'schema': 'schema.json'}
        invalid = [{k: manifest.get(k)} for k, expected in references.items() if manifest.get(k) != expected or expected not in self.entries]
        for key in ('source_inventory', 'export_provenance'):
            if manifest.get(key) is not None and (self.safe_path(manifest[key]) is None or manifest[key] not in self.entries):
                invalid.append({key: manifest[key]})
        self.violations('CANONICAL_REFERENCE_VALID', invalid, 'Canonical references must be indexed paths of the supported layout', stage='structural')
        document = self.json_artifact('schema.json', dict)
        expected = schema()['tables']
        supported = document is not None and type(document.get('schema_version')) is int and document['schema_version'] == 1
        if supported:
            tables = document.get('tables')
            supported = isinstance(tables, dict) and all(isinstance(tables.get(key),dict) and tables[key].get('fields') == value['fields'] for key, value in expected.items())
        self.check('TABLE_SCHEMA_SUPPORTED', supported, 'Scientific field definitions must match version 1; prose may differ', stage='structural')
        status = self.json_artifact('metadata/run_status.json', dict)
        config = self.json_artifact('metadata/effective_config.json', dict)
        if status is None or config is None:
            return None
        self.check('RUN_STATUS_CONSISTENT', status.get('run_id') == manifest['run_id'] and status.get('status') == manifest['status'] and
                   type(status.get('schema_version')) is int and status['schema_version'] == 1,
                   'Manifest and canonical run status must agree', dict(manifest_status=manifest['status'], status=status.get('status'), run_id=status.get('run_id')))
        self.check('EXPERIMENT_ID_CONSISTENT', status.get('experiment_id') == config.get('id'), 'Configuration and status identify the same experiment')
        status_fields = isinstance(status.get('errors'),list) and all(isinstance(e,str) for e in status.get('errors',[]))
        status_fields = status_fields and (status.get('producers_drained') is None or type(status['producers_drained']) is bool)
        status_fields = status_fields and all(status.get(k) is None or finite(status[k]) for k in ('experiment_start_timestamp','experiment_start_monotonic'))
        self.check('RUN_STATUS_FIELDS_VALID', status_fields, 'Run errors, drain certification and available clock anchors have documented types')
        if status.get('status') not in ('completed', 'incomplete'):
            return None
        return config, status

    def load_csv(self, key, relative, required):
        path = self.safe_path(relative)
        exists = path is not None and path.is_file() and relative in self.entries
        self.check('SCIENTIFIC_ARTIFACT_PRESENT', exists, 'Scientific CSV must be indexed and present, or explicitly absent in an incomplete run',
                   dict(table=key, path=relative), severity='ERROR' if required else 'WARNING', stage='structural')
        if not exists:
            return None
        definitions = schema()['tables'][key]['fields']
        try:
            with path.open(encoding='utf-8', newline='') as stream:
                reader = csv.DictReader(stream, strict=True)
                if reader.fieldnames != [f['name'] for f in definitions]:
                    raise ValueError('Header does not match known field order')
                rows = list(reader)
                if any(None in r or any(v is None for v in r.values()) for r in rows):
                    raise ValueError('Wrong number of CSV cells')
        except (OSError, ValueError, UnicodeError, csv.Error) as exc:
            self.check('CSV_PARSEABLE', False, 'Scientific CSV is malformed', dict(path=relative, reason=str(exc)), stage='structural')
            return None
        self.check('CSV_PARSEABLE', True, 'CSV header and record widths are recognized', dict(path=relative, rows=len(rows)), stage='structural')
        converted, bad = [], []
        for index, row in enumerate(rows, 2):
            item = {}
            for definition in definitions:
                name, kind = definition['name'], definition['type']
                value = row[name]
                try:
                    if value == '':
                        if not definition['nullable'] and name != 'active_containers_names':
                            raise ValueError('Nonnullable field is empty')
                        value = '' if name == 'active_containers_names' else None
                    elif kind == 'integer':
                        value = int(value)
                    elif kind == 'number':
                        value = float(value)
                        if not math.isfinite(value):
                            raise ValueError('Nonfinite numeric value')
                    elif kind == 'json_array_of_strings':
                        value = json.loads(value)
                        if not isinstance(value, list) or not all(isinstance(v, str) for v in value) or len(value) != len(set(value)):
                            raise ValueError('Expected unique array of strings')
                    if 'domain' in definition and value not in definition['domain'] and value is not None:
                        raise ValueError('Outside documented domain')
                    item[name] = value
                except (ValueError, TypeError) as exc:
                    bad.append(dict(line=index, field=name, value=row[name], reason=str(exc)))
            converted.append(item)
        self.violations('CSV_FIELD_VALID', bad, 'Scientific types, nullability and domains are respected', context=dict(table=key,path=relative), stage='structural')
        return None if bad else converted

    def configuration(self, config):
        try:
            from simulator.experiment_config import ExperimentConfig
            required = {'normal_traffic': ('clients','rate','endpoint'), 'attack': ('enabled','profile','attackers','rate','start_seconds','duration_seconds','endpoint'),
                        'traffic_sources': ('execution',), 'monitoring': ('interval_seconds',)}
            if any(k not in config for k in ('id','duration_seconds','seed')) or any(not isinstance(config.get(k),dict) or any(f not in config[k] for f in fields) for k,fields in required.items()):
                raise ValueError('Effective configuration lacks canonical run/traffic/monitoring fields; defaults are not substituted')
            ExperimentConfig.from_dict(config)
            valid = True
            reason = None
        except (ValueError, TypeError, KeyError) as exc:
            valid, reason = False, str(exc)
        self.check('CONFIGURATION_VALID', valid, 'Effective configuration satisfies the existing configuration contract', dict(reason=reason))
        return valid

    def sources(self, config, status):
        if config.get('traffic_sources', {}).get('execution') != 'containers':
            self.check('SOURCE_REFERENCE_SCOPE', True, 'Host generators have no container-source inventory; worker indices are checked against configuration', severity='INFO')
            return None
        indexed = self.manifest.get('source_inventory') == 'metadata/source_inventory.json' and 'metadata/source_inventory.json' in self.entries
        self.check('SOURCE_INVENTORY_REFERENCE_VALID', indexed, 'Container source inventory must be a canonical indexed reference',
                   severity='ERROR' if status['status']=='completed' else 'WARNING', stage='structural')
        if not indexed:
            return None
        inventory = self.json_artifact('metadata/source_inventory.json', list, required=status['status'] == 'completed')
        if inventory is None:
            return None
        malformed = []
        for index, source in enumerate(inventory):
            try:
                if not isinstance(source, dict) or not all(isinstance(source.get(k), str) and source[k] for k in ('source_id', 'source_type', 'traffic_class', 'ip', 'container_name', 'container_id')):
                    raise ValueError('Missing source identity/topology fields')
                if source['source_type'] not in ('normal', 'attack') or source['traffic_class'] != {'normal': 'benign', 'attack': 'attack'}[source['source_type']]:
                    raise ValueError('Source type and causal class disagree')
                if type(source.get('worker_index')) is not int or source['worker_index'] < 0:
                    raise ValueError('Invalid worker index')
                ipaddress.IPv4Address(source['ip'])
            except (ValueError, TypeError) as exc:
                malformed.append(dict(index=index, reason=str(exc)))
        self.violations('SOURCE_FIELDS_VALID', malformed, 'Source identity, class, worker index and run IP are explicit')
        if malformed:
            return None
        duplicate = []
        for key in ('source_id', 'ip', 'container_id', 'container_name'):
            duplicate.extend(dict(field=key, value=v) for v, count in Counter(s[key] for s in inventory).items() if count > 1)
        duplicate.extend(dict(field='generator_worker', value=list(v)) for v, count in Counter((s['source_type'], s['worker_index']) for s in inventory).items() if count > 1)
        self.violations('SOURCE_IDENTITY_UNIQUE', duplicate, 'Scientific IDs and source topology associations are unique within run')
        inconsistent = []
        for s in inventory:
            observed = any(r['generator']==s['source_type'] and r['worker_id']==s['worker_index'] for r in self.tables.get('requests') or [])
            unbound_setup = status['status']=='incomplete' and s.get('run_id') is None and not observed
            if s.get('run_id') != self.manifest['run_id'] and not unbound_setup:
                inconsistent.append(s['source_id'])
        self.violations('SOURCE_RUN_ID_CONSISTENT', inconsistent, 'Sources belong to this run; incomplete setup without observations may remain unbound')
        expected = dict(normal=config['normal_traffic']['clients'], attack=config['attack']['attackers'] if config['attack']['enabled'] else 0)
        counts = Counter(s['source_type'] for s in inventory)
        self.check('SOURCE_COUNT_CONFIG_CONSISTENT', all(counts[k] == v for k, v in expected.items()),
                   'Configured source counts match inventory', dict(expected=expected, observed=dict(counts)), severity='ERROR' if status['status'] == 'completed' else 'WARNING')
        return inventory

    def requests(self, config, inventory, events):
        rows = self.tables.get('requests')
        if rows is None:
            return
        self.violations('REQUEST_ID_UNIQUE', [v for v, n in Counter(r['request_id'] for r in rows).items() if n > 1], 'Request IDs are unique within run')
        source_map = {(s['source_type'], s['worker_index']): s for s in inventory or []}
        event_map = {e['event_id']: e for e in events or []}
        temporal, source, causal, references, operations, outcomes = [], [], [], [], [], []
        for r in rows:
            identifier = r['request_id']
            start, end, duration = r['elapsed_seconds'], r['end_elapsed_seconds'], r['duration_ms']
            if start < 0 or (end is not None and (end < start or duration is None or duration < 0 or duration != (end-start)*1000)) or (end is None and duration is not None):
                temporal.append(identifier)
            if (r['end_timestamp'] is None) != (end is None):
                temporal.append(identifier)
            component = r['generator']
            settings = config['normal_traffic'] if component == 'normal' else config['attack']
            count = settings['clients'] if component == 'normal' else settings['attackers'] if settings['enabled'] else 0
            if not 0 <= r['worker_id'] < count or (inventory is not None and (component, r['worker_id']) not in source_map):
                source.append(identifier)
            if r['traffic_class'] != ('benign' if component == 'normal' else 'attack') or (component == 'normal' and (r['event_id'] is not None or r['attack_id'] is not None)):
                causal.append(identifier)
            if component == 'attack' and (r['event_id'] is None or r['attack_id'] is None):
                causal.append(identifier)
            if events is not None and component == 'attack' and (r['event_id'] not in event_map or r['attack_id'] != event_map.get(r['event_id'], {}).get('attack_id')):
                references.append(identifier)
            try:
                url = urlsplit(r['target_url'])
            except ValueError:
                operations.append(dict(request_id=identifier, observed=r['target_url'], reason='Malformed URL'))
                continue
            expected_path = settings.get('endpoint') or '/'
            if url.scheme not in ('http', 'https') or not url.netloc or (url.path or '/') != expected_path:
                operations.append(dict(request_id=identifier, observed=r['target_url'], expected_path=expected_path))
            if inventory is not None and (component, r['worker_id']) in source_map:
                try:
                    logical = urlsplit(source_map[component, r['worker_id']].get('service_endpoint', ''))
                except ValueError:
                    operations.append(dict(request_id=identifier, reason='Malformed logical endpoint'))
                    continue
                if url.scheme != logical.scheme or url.netloc != logical.netloc:
                    operations.append(dict(request_id=identifier, logical_endpoint=logical.geturl(), observed=r['target_url']))
            outcome, http, error = r['outcome'], r['http_status'], r['error_type']
            if (outcome in ('response', 'http_error') and (http is None or not 100 <= http <= 599 or error is not None or end is None or (http >= 400) != (outcome == 'http_error'))) or (outcome in ('transport_error', 'client_error') and (not error or http is not None or end is None)) or (outcome == 'incomplete' and (end is not None or http is not None)):
                outcomes.append(identifier)
        for key, bad, message in [
            ('REQUEST_TEMPORAL_ORDER', temporal, 'Elapsed order and duration arithmetic must agree; epoch drift is not assumed absent'),
            ('SOURCE_REFERENCE_VALID', source, 'Requests reference configured and, when available, inventoried workers'),
            ('REQUEST_CAUSAL_CLASS_VALID', causal, 'Generator determines causal class, independently of attack_active'),
            ('EVENT_REFERENCE_VALID', references, 'Attack requests identify an existing event and its attack_id'),
            ('REQUEST_OPERATION_VALID', operations, 'Observed operation and logical service destination agree with configuration'),
            ('REQUEST_OUTCOME_VALID', outcomes, 'HTTP/transport outcomes and nullable fields agree')]:
            self.violations(key, bad, message)
        errors = [r['request_id'] for r in rows if r['outcome'] != 'response']
        self.violations('REQUEST_FAILURES_OBSERVED', errors, 'Request failures are preserved observations, not automatic dataset corruption', severity='WARNING', stage='quality')
        if events is None:
            self.check('EVENT_REFERENCE_OBSERVABLE', False, 'Absent/unreadable event table prevents reference and temporal-context certification', severity='WARNING', stage='quality')

    def journals(self, config, status, inventory):
        if inventory is None:
            return
        missing, malformed, identity, admissions, reference, absent_requests = [], [], [], [], [], []
        root_requests = {r['request_id']:r for r in self.tables.get('requests') or []}
        for source in inventory:
            relative = f"evidence/sources/{source['source_id']}/output/journal.jsonl"
            path = self.safe_path(relative)
            if relative not in self.entries or path is None or not path.is_file():
                missing.append(source['source_id']); continue
            records = []
            try:
                for line in path.read_text(encoding='utf-8').splitlines():
                    item = decode_json(line)
                    if not isinstance(item,dict) or not isinstance(item.get('payload'),dict) or not isinstance(item.get('kind'),str):
                        raise ValueError('Malformed journal envelope')
                    records.append(item)
            except (ValueError, OSError, UnicodeError) as exc:
                malformed.append(dict(source_id=source['source_id'], reason=str(exc)))
                continue
            for index, record in enumerate(records, 1):
                if record.get('sequence') != index or record.get('source_id') != source['source_id'] or record.get('run_id') != self.manifest['run_id']:
                    identity.append(dict(source_id=source['source_id'], sequence=index))
                if record['kind'] in ('request_begin','request_finish'):
                    payload = record['payload']
                    request = root_requests.get(payload.get('request_id'))
                    if request is None and self.tables.get('requests') is not None:
                        absent_requests.append(dict(source_id=source['source_id'], request_id=payload.get('request_id')))
                    if request is not None:
                        keys = ('generator','worker_id','event_id','elapsed_seconds','target_url')
                        if record['kind']=='request_finish':
                            keys += ('end_elapsed_seconds','duration_ms','outcome')
                        if any(payload.get(k) != request[k] for k in keys) or request['generator'] != source['source_type'] or request['worker_id'] != source['worker_index']:
                            reference.append(dict(source_id=source['source_id'], request_id=payload.get('request_id')))
            from simulator.source_aggregate import identified_admission_errors
            lifecycle_errors = identified_admission_errors(records)
            self.violations('IDENTIFIED_ADMISSIONS_RESOLVED', lifecycle_errors,
                            'Identified admissions have one terminal resolution and matching HTTP starts')
            if source['source_type']=='attack' and config['attack']['profile']=='periodic_burst':
                own_admissions = [r['payload'] for r in records if r['kind']=='admission']
                own_begins = [r['payload'] for r in records if r['kind']=='request_begin' and r['payload'].get('generator')=='attack']
                invalid = [a for a in own_admissions if not finite(a.get('elapsed_seconds')) or not burst_allows(a['elapsed_seconds'], config['attack'])]
                admitted = Counter((a.get('event_id'),a.get('elapsed_seconds')) for a in own_admissions if isinstance(a.get('event_id'),str) and finite(a.get('elapsed_seconds')))
                begun = Counter((a.get('event_id'),a.get('elapsed_seconds')) for a in own_begins if isinstance(a.get('event_id'),str) and finite(a.get('elapsed_seconds')))
                if invalid or admitted != begun or any(r['kind']=='abandoned_admission' for r in records):
                    admissions.append(dict(source_id=source['source_id'], admitted=len(own_admissions), begun=len(own_begins), invalid_admissions=invalid[:10]))
        self.violations('SOURCE_JOURNAL_AVAILABLE', missing, 'Missing journals limit admission/backlog evidence; primary observations remain authoritative', severity='WARNING', stage='quality')
        self.violations('SOURCE_JOURNAL_PARSEABLE', malformed, 'Malformed optional journals limit auditability', severity='WARNING', stage='quality')
        self.violations('SOURCE_JOURNAL_IDENTITY_VALID', identity, 'Parseable source journals preserve identity and sequence')
        self.violations('SOURCE_JOURNAL_REQUEST_REFERENCE', reference, 'Observed journal requests agree with root requests except locally reconciled temporal labels')
        self.violations('SOURCE_JOURNAL_REQUEST_PRESENT', absent_requests, 'Journal requests are present in the primary table; incomplete aggregation may lack observations', severity='ERROR' if status['status']=='completed' else 'WARNING')
        self.violations('PERIODIC_ADMISSION_NO_BACKLOG', admissions, 'When journals are available, periodic admission and beginning share the same observed sample and remain inside allowed windows')

    def events(self, config, status):
        events, requests = self.tables.get('attacks'), self.tables.get('requests')
        if events is None:
            return
        self.violations('EVENT_ID_UNIQUE', [v for v, n in Counter(e['event_id'] for e in events).items() if n > 1], 'Event IDs are unique')
        self.violations('ATTACK_ID_UNIQUE', [v for v, n in Counter(e['attack_id'] for e in events).items() if n > 1], 'Attack IDs are unique for the current one-event contract')
        attack = config['attack']
        expected_event = attack['enabled']
        self.check('EVENT_CONFIG_PRESENCE', len(events) == int(expected_event), 'Enabled attack plans one global event even when rate or source count is zero',
                   dict(expected=int(expected_event), observed=len(events)), severity='ERROR' if status['status']=='completed' else 'WARNING')
        order, correspondence, configuration, patterns = [], [], [], []
        for e in events:
            eid = e['event_id']
            start, end, drain = (e[k] for k in ('actual_start_seconds', 'actual_end_seconds', 'drained_end_seconds'))
            if (start is None and (end is not None or drain is not None)) or (start is not None and (start < 0 or (end is not None and start > end) or (drain is not None and start > drain))):
                order.append(eid)
            if end is not None and e['stop_requested_seconds'] is not None and end < e['stop_requested_seconds']:
                order.append(dict(event_id=eid, reason='Emission certified before admission stop'))
            if e['scheduled_start_seconds'] != attack['start_seconds'] or e['scheduled_end_seconds'] != attack['start_seconds']+attack['duration_seconds'] or e['profile'] != attack['profile'] or e['experiment_id'] != config['id']:
                configuration.append(eid)
            for key in ('experiment_start_timestamp', 'experiment_start_monotonic'):
                if status.get(key) is not None and e[key] != status[key]:
                    configuration.append(dict(event_id=eid, anchor=key))
            own = [r for r in requests or [] if r['event_id']==eid and r['generator']=='attack']
            if requests is not None:
                starts = [r['elapsed_seconds'] for r in own]
                finishes = [r['end_elapsed_seconds'] for r in own if r['end_elapsed_seconds'] is not None]
                if (bool(starts) != (start is not None)) or (starts and (min(starts) != start or max(starts) != e['last_request_start_seconds'])):
                    correspondence.append(dict(event_id=eid, milestone='start/last_start', observed_min=min(starts) if starts else None, actual_start=start))
                if drain is not None and (len(finishes) != len(own) or not finishes or max(finishes) != drain):
                    correspondence.append(dict(event_id=eid, milestone='drain', observed_last=max(finishes) if finishes else None, drained_end=drain))
                for r in own:
                    t = r['elapsed_seconds']
                    valid = start is not None and t >= start and t >= attack['start_seconds'] and (end is None or t < end)
                    if attack['profile'] == 'periodic_burst':
                        valid = valid and burst_allows(t, attack)
                    if not valid:
                        patterns.append(dict(request_id=r['request_id'], event_id=eid, elapsed_seconds=t, profile=attack['profile']))
            if e['status']=='completed' and (start is None or end is None or drain is None):
                order.append(dict(event_id=eid, reason='Completed event lacks lifecycle milestones'))
        self.violations('EVENT_TEMPORAL_ORDER', order, 'Start precedes end and drain independently; no end <= drain requirement')
        self.violations('EVENT_REQUEST_MILESTONES_MATCH', correspondence, 'Recorded event first/last starts and last completion match the observed requests exactly in their shared monotonic domain')
        self.violations('EVENT_CONFIGURATION_CONSISTENT', configuration, 'Profile, planned global interval, experiment and anchors agree')
        self.violations('ATTACK_START_WINDOW_VALID', patterns, 'Periodic starts require active burst/global window; continuous queued starts may extend through effective actual_end')

    @staticmethod
    def event_context(events, elapsed):
        ids, uncertain = [], False
        for e in events:
            start, end = e['actual_start_seconds'], e['actual_end_seconds']
            if start is None:
                if e['status']=='incomplete' and e['activation_requested_seconds'] is not None and elapsed >= e['activation_requested_seconds']:
                    uncertain = True
                continue
            if elapsed < start or (end is not None and elapsed >= end):
                continue
            if end is None and e['status']=='incomplete' and e['last_request_start_seconds'] is not None and elapsed > e['last_request_start_seconds']:
                uncertain = True
            else:
                ids.append(e['event_id'])
        return (1 if ids else None if uncertain else 0), sorted(ids)

    def labels_and_rtt(self):
        events = self.tables.get('attacks')
        if events is not None:
            bad = []
            for key in ('requests', 'metrics', 'packets'):
                for index, row in enumerate(self.tables.get(key) or [], 2):
                    active, ids = self.event_context(events, row['elapsed_seconds'])
                    if active != row['attack_active'] or ids != sorted(row['active_event_ids']):
                        bad.append(dict(table=key, line=index, expected_active=active, observed_active=row['attack_active'], expected_ids=ids, observed_ids=row['active_event_ids']))
            self.violations('GLOBAL_ATTACK_CONTEXT_CONSISTENT', bad, 'Labels follow the global event, including silence; packet labels are checked in their recorded elapsed domain, not matched to request clocks')
        requests, rtts = self.tables.get('requests'), self.tables.get('rtt')
        if requests is not None and rtts is not None:
            by_id = {r['request_id']: r for r in requests}
            bad = []
            for r in rtts:
                target = by_id.get(r['request_id'])
                if target is None or target['outcome'] != 'response' or any(r[a] != target[b] for a, b in [('rtt','duration_ms'), ('timestamp','end_timestamp'), ('elapsed_seconds','end_elapsed_seconds'), ('traffic_class','traffic_class')]):
                    bad.append(r['request_id'])
            expected = Counter(r['request_id'] for r in requests if r['outcome']=='response')
            observed = Counter(r['request_id'] for r in rtts)
            if expected != observed:
                bad.append(dict(expected_responses=sum(expected.values()), observed_durations=sum(observed.values())))
            self.violations('HTTP_DURATION_REFERENCE_VALID', bad, 'RTT table is exactly the response subset at client completion; it is not TCP RTT')

    def provenance(self):
        export_path = self.manifest.get('export_provenance')
        if isinstance(export_path, str) and export_path in self.entries and self.safe_path(export_path) is not None:
            exported = self.json_artifact(export_path, dict)
            self.check('EXPORT_PROVENANCE_SCOPE_VALID', exported is not None and exported.get('scope')=='export' and type(exported.get('schema_version')) is int and exported['schema_version']==1,
                       'Export provenance describes export time, not execution time')
        declaration = self.manifest.get('execution_provenance')
        if not isinstance(declaration, dict) or declaration.get('status') not in ('recorded', 'not_recorded'):
            self.check('PROVENANCE_DECLARATION_VALID', False, 'Manifest must explicitly declare recorded or not_recorded execution provenance')
            return
        if declaration['status'] == 'not_recorded':
            self.check('PROVENANCE_DECLARATION_VALID', not declaration.get('path') and 'metadata/run_provenance.json' not in self.entries,
                       'Unknown execution provenance must not contradict an indexed execution record')
            self.check('EXECUTION_PROVENANCE_AVAILABLE', False, 'Legacy execution provenance is explicitly unknown; export provenance must not replace it', severity='WARNING', stage='quality')
            return
        relative = declaration.get('path')
        if self.safe_path(relative) is None or relative not in self.entries:
            self.check('PROVENANCE_REFERENCE_VALID', False, 'Recorded execution provenance must reference a safe indexed file')
            return
        value = self.json_artifact(relative, dict)
        if value is None:
            return
        code = value.get('code')
        if not isinstance(code, dict) or not isinstance(code.get('git'),dict):
            self.check('EXECUTION_PROVENANCE_CONSISTENT', False, 'Recorded provenance lacks structured code/Git metadata')
            return
        git = code['git']
        bound = value.get('scope') == 'execution_before_invocation' and value.get('run_id') == self.manifest['run_id'] and type(value.get('schema_version')) is int and value['schema_version'] == 1
        if git.get('status') == 'recorded':
            commit = git.get('commit', '')
            bound = bound and isinstance(commit, str) and len(commit)==40 and all(c in '0123456789abcdef' for c in commit) and type(git.get('dirty')) is bool
        elif git.get('status') != 'unavailable':
            bound = False
        files = code.get('runtime_files_sha256')
        digest = code.get('runtime_tree_sha256')
        fingerprint = isinstance(files, dict) and all(isinstance(k,str) and isinstance(v,str) and len(v)==64 and all(c in '0123456789abcdef' for c in v) for k,v in files.items())
        if fingerprint:
            fingerprint = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest() == digest
        self.check('EXECUTION_PROVENANCE_CONSISTENT', bool(bound and fingerprint and isinstance(value.get('host_environment'), dict)),
                   'Execution binding, Git fields and fingerprint are internally coherent; historical file contents are not reconstructed')
        self.check('EXECUTION_CODE_RECORDED', git.get('status') == 'recorded', 'Git unavailable limits reproducibility, without inventing SHA', severity='WARNING', stage='quality')
        self.check('EXECUTION_WORKTREE_CLEAN', git.get('dirty') is False, 'Dirty or unavailable working tree cannot be reconstructed from hashes alone', severity='WARNING', stage='quality')

    def quality(self, config, status, inventory):
        self.gate('RUN_COMPLETED', status['status'] == 'completed', 'Technical incomplete runs are not eligible even when their dataset is intact', dict(status=status['status'], errors=status.get('errors', [])))
        self.gate('RUN_DRAIN_CERTIFIED', status.get('producers_drained') is True, 'Eligibility requires the existing producers_drained certification')
        self.gate('RUN_WITHOUT_OPERATIONAL_FAILURE', not status.get('errors'), 'Operational failures block eligibility; observed request failures alone do not')
        required_usable = all(self.tables.get(k) for k in ('requests', 'metrics', 'packets')) and self.tables.get('attacks') is not None and self.tables.get('rtt') is not None
        self.gate('SCIENTIFIC_OBSERVATIONS_USABLE', bool(required_usable), 'Requests, capture and metrics need observations; event/RTT tables may legitimately be empty')
        attack = config['attack']
        attack_expected = attack['enabled'] and attack['attackers'] > 0 and attack['rate'] > 0
        normal_expected = config['normal_traffic']['clients'] > 0 and config['normal_traffic']['rate'] > 0
        requests = self.tables.get('requests') or []
        classes = Counter(r['traffic_class'] for r in requests)
        self.gate('EXPECTED_TRAFFIC_OBSERVED', (not attack_expected or classes['attack'] > 0) and (not normal_expected or classes['benign'] > 0),
                  'Expected causal traffic exists; no rate × duration request count is required', dict(expected=dict(attack=attack_expected, benign=normal_expected), observed=dict(classes)))
        self.gate('EXPECTED_EVENT_EXECUTED', not attack_expected or any(e['actual_start_seconds'] is not None and e['actual_end_seconds'] is not None and e['drained_end_seconds'] is not None and e['status']=='completed' for e in self.tables.get('attacks') or []), 'Expected event has an observed beginning, effective end and drain')
        self.check('RANDOM_SEED_RECORDED', type(config.get('seed')) is int, 'Missing resolved seed limits reproduction without corrupting observations', severity='WARNING', stage='quality')
        for key, check_id in [('packets','CAPTURE_TEMPORAL_COVERAGE'), ('requests','SERVICE_TEMPORAL_COVERAGE'), ('metrics','METRICS_TEMPORAL_COVERAGE')]:
            values = [r['elapsed_seconds'] for r in self.tables.get(key) or []]
            self.check(check_id, bool(values), 'Observed span only; first/last observations do not prove uninterrupted coverage and no percentage threshold is used',
                       dict(rows=len(values), first=min(values) if values else None, last=max(values) if values else None,
                            observed_span=max(values)-min(values) if values else None, planned_duration=config['duration_seconds'],
                            clock='epoch-derived' if key=='packets' else 'monotonic', monitoring_interval=config['monitoring']['interval_seconds'] if key=='metrics' else None), severity='WARNING', stage='quality')
            if attack_expected and values:
                before = any(t < attack['start_seconds'] for t in values)
                during = any(attack['start_seconds'] <= t < attack['start_seconds']+attack['duration_seconds'] for t in values)
                after = any(t >= attack['start_seconds']+attack['duration_seconds'] for t in values)
                missing = []
                if key=='metrics' or normal_expected:
                    if attack['start_seconds'] > 0 and not before: missing.append('before')
                    if attack['start_seconds']+attack['duration_seconds'] < config['duration_seconds'] and not after: missing.append('after')
                if not during: missing.append('during')
                self.violations('EXPECTED_PHASE_OBSERVATIONS', [dict(table=key, phase=p) for p in missing], 'Missing phase observations limit interpretation, but may follow stochastic generation or incomplete execution', context=dict(table=key), severity='WARNING', stage='quality')
        metrics = self.tables.get('metrics') or []
        self.violations('METRIC_VALUES_PLAUSIBLE', [i+2 for i,r in enumerate(metrics) if any(r[k] < 0 for k in ('num_instances','average_cpu_percent','mem_usage','avg_rtt_ms','host_cpu_percent'))],
                        'Counts, resource observations and durations are nonnegative; no CPU ceiling or degradation requirement')
        self.violations('METRIC_MONOTONIC_ORDER', [i+2 for i in range(1,len(metrics)) if metrics[i]['elapsed_seconds'] < metrics[i-1]['elapsed_seconds']], 'Monitoring elapsed samples are nondecreasing')
        packets = self.tables.get('packets') or []
        self.violations('PACKET_EPOCH_ORDER', [i+2 for i in range(1,len(packets)) if packets[i]['timestamp'] < packets[i-1]['timestamp']], 'Backward capture epoch observations may indicate reordering or clock adjustment', severity='WARNING', stage='quality')
        self.violations('PACKET_FIELDS_PLAUSIBLE', [i+2 for i,p in enumerate(packets) if p['packet_length'] < 0 or not all(0 <= p[k] <= 65535 for k in ('src_port','dst_port'))], 'TCP payload lengths and ports are nonnegative/in range')
        invalid_ips = []
        for i, packet in enumerate(packets, 2):
            try:
                ipaddress.IPv4Address(packet['src_ip']); ipaddress.IPv4Address(packet['dst_ip'])
            except ValueError:
                invalid_ips.append(i)
        self.violations('PACKET_IP_VALID', invalid_ips, 'Packet CSV IPv4 addresses are parseable run attributes')
        anchor = status.get('experiment_start_timestamp')
        if finite(anchor):
            self.violations('PACKET_EPOCH_ALIGNMENT', [i+2 for i,p in enumerate(packets) if p['elapsed_seconds'] != p['timestamp']-anchor],
                            'Capture elapsed uses its exact documented epoch subtraction, not request monotonic timestamps')
        backwards = [r['request_id'] for r in requests if r['end_timestamp'] is not None and r['end_timestamp'] < r['timestamp']]
        self.violations('REQUEST_WALL_CLOCK_ORDER', backwards, 'Backward epoch timestamps may indicate clock adjustment; monotonic duration remains authoritative', severity='WARNING', stage='quality')
        mode = config.get('topology', {}).get('mode', 'proxy')
        metadata_path = f'metadata/topology/{mode}/capture_metadata.json'
        self.check('CAPTURE_TOPOLOGY_UNAMBIGUOUS', not all(f'metadata/topology/{m}/capture_metadata.json' in self.entries for m in ('proxy','direct')),
                   'A run declares at most one capture topology')
        capture = self.json_artifact(metadata_path, dict, required=False) if metadata_path in self.entries else None
        if inventory is not None and packets:
            observed = {p[k] for p in packets for k in ('src_ip','dst_ip')}
            missing = [s['source_id'] for s in inventory if s['ip'] not in observed]
            self.violations('SOURCE_IP_OBSERVED', missing, 'Missing inventoried IPs are a coverage warning, not absence of source identity', severity='WARNING', stage='quality')
            if capture:
                from experiments.capture_topology import capture_destination
                try:
                    proxy, port = capture_destination(capture, config)
                except ValueError as exc:
                    self.check('CAPTURE_TOPOLOGY_VALID', False, str(exc))
                    return
                allowed = {s['ip'] for s in inventory}
                outside = [i+2 for i,p in enumerate(packets) if not ((p['src_ip']==proxy and p['src_port']==port and p['dst_ip'] in allowed) or (p['dst_ip']==proxy and p['dst_port']==port and p['src_ip'] in allowed))]
                self.violations('CAPTURE_SEGMENT_CONSISTENT', outside, 'Declared '+capture['segment']+' capture contains only source/target TCP observations')
        if mode == 'direct':
            self.check('DIRECT_CAPTURE_METADATA_PRESENT', capture is not None, 'Direct collection requires declared source_victim metadata')
        backend_path = f'metadata/topology/{mode}/backend_inventory.json'
        backends = self.json_artifact(backend_path, list, required=False) if backend_path in self.entries else None
        if backends is not None and all(isinstance(b,dict) and isinstance(b.get('name'),str) for b in backends):
            expected = {b['name'] for b in backends}
            named = {name for r in metrics for name in (r['active_containers_names'] or '').split(',') if name}
            unknown = sorted(named - expected)
            self.violations('METRIC_CONTAINER_REFERENCE_VALID', unknown, 'Named monitored victims must exist in backend inventory')
            self.violations('EXPECTED_VICTIM_METRICS_OBSERVED', sorted(expected-named), 'Missing named victims limit infrastructure attribution; startup cache gaps are not invalidity', severity='WARNING', stage='quality')
        pcap = self.entries.get('raw/traffic/traffic_capture.pcap')
        if pcap is not None:
            self.check('RAW_CAPTURE_NONEMPTY', type(pcap.get('bytes')) is int and pcap['bytes'] > 24, 'A classic PCAP with only its 24-byte global header has no observations; this does not assert equality with CSV capture',
                       dict(bytes=pcap.get('bytes')), severity='WARNING', stage='quality')
        self.check('COVERAGE_LIMITATIONS', True, 'No direct packet/request join, continuous clock drift proof, capture completeness guarantee, CPU/RTT degradation expectation or exact stochastic request count', severity='INFO', stage='quality')

    def run(self):
        result = self.structure()
        if result is not None:
            config, status = result
            if self.configuration(config):
                for key, relative in SCIENTIFIC.items():
                    self.tables[key] = self.load_csv(key, relative, required=status['status']=='completed')
                inconsistent = [dict(table=k, line=i+2, run_id=r['run_id']) for k,rows in self.tables.items() for i,r in enumerate(rows or []) if r['run_id'] != self.manifest['run_id']]
                self.violations('RUN_ID_CONSISTENT', inconsistent, 'Scientific observations belong to the manifest run')
                inventory = self.sources(config, status)
                self.requests(config, inventory, self.tables.get('attacks'))
                self.events(config, status)
                self.labels_and_rtt()
                self.journals(config, status, inventory)
                self.provenance()
                self.quality(config, status, inventory)
        failures = [c for c in self.checks if c['passed'] is False]
        dataset_valid = not any(c['severity']=='ERROR' and 'dataset_valid' in c['affects'] for c in failures)
        self.gate('DATASET_VALID_FOR_ANALYSIS', dataset_valid, 'Analysis eligibility requires a valid dataset independently of run status')
        gates = [c for c in self.checks if 'analysis_eligible' in c['affects']]
        eligible = dataset_valid and bool(gates) and all(c['passed'] is True for c in gates)
        return dict(validation_schema_version=1, validator_rules_version=1,
                    validator_sha256=sha256_file(__file__),
                    validator_dependencies_sha256={str(p.relative_to(Path(__file__).resolve().parents[1])):sha256_file(p) for p in
                        [Path(__file__).with_name('dataset_schema.py'), Path(__file__).with_name('dataset_provenance.py'), Path(__file__).resolve().parents[1]/'simulator/experiment_config.py']},
                    dataset_manifest_sha256=self.manifest_sha256,
                    run_id=self.manifest.get('run_id') if self.manifest else None,
                    dataset_schema_version=self.manifest.get('schema_version') if self.manifest else None,
                    dataset_valid=dataset_valid, analysis_eligible=eligible,
                    structural_valid=not any(c['severity']=='ERROR' and c['stage']=='structural' for c in failures),
                    summary=dict(errors=sum(c['severity']=='ERROR' for c in failures), warnings=sum(c['severity']=='WARNING' for c in failures),
                                 info=sum(c['severity']=='INFO' for c in self.checks), eligibility_blockers=[c['check_id'] for c in gates if c['passed'] is not True]),
                    checks=self.checks)


def validate_dataset(directory):
    return DatasetValidator(directory).run()


def write_report(report, output, dataset):
    output, dataset = Path(output).absolute(), Path(dataset).resolve()
    resolved = output.resolve()
    if resolved == dataset or dataset in resolved.parents:
        raise ValueError('Validation report must be outside the read-only dataset')
    if output.exists() or output.is_symlink():
        raise ValueError('Report already exists; no overwriting')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = validate_dataset(args.dataset)
    try:
        write_report(report, args.output, args.dataset)
    except (ValueError, OSError) as exc:
        parser.exit(2, f'{exc}\n')
    label = 'INVALID' if not report['dataset_valid'] else 'VALID / ELIGIBLE' if report['analysis_eligible'] else 'VALID / NOT ELIGIBLE'
    print(f"{label}: {report['run_id']} — {report['summary']['errors']} errors, {report['summary']['warnings']} warnings")
    for check in report['checks']:
        if check['passed'] is False:
            print(f"  {check['severity']} {check['check_id']}: {check['message']}")
    raise SystemExit(0 if report['analysis_eligible'] else 1)


if __name__ == '__main__':
    main()
