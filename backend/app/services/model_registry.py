"""本地受信任模型注册、受限数值推理、缓存及失败回退。"""
import hashlib
import json
import logging
import math
import re
import subprocess
import sys
import threading
import time
from collections import Counter, OrderedDict, deque
from pathlib import Path

from backend.app.core.clock import iso_z, utc_now
from backend.app.core.config import PROJECT_ROOT

REGISTRY_PATH = PROJECT_ROOT / 'ml-production/registry.json'
APPROVED_ROOT = PROJECT_ROOT / 'ml-production/approved'
WORKER = PROJECT_ROOT / 'backend/app/ml/maintenance_numeric_worker.py'
INFERENCE_TIMEOUT_SECONDS = 2.0
MAX_ARTIFACT_BYTES = 1_000_000
STATES = {'research_only', 'approved', 'shadow', 'canary', 'active', 'disabled'}
logger = logging.getLogger('repovantage.ml03')
_lock = threading.Lock()
_cache = OrderedDict()
_counters = Counter()
_latencies = deque(maxlen=1000)
_memory_peaks = deque(maxlen=1000)
_health = {'loaded_status': 'not_loaded', 'last_healthcheck': None, 'artifact_sha256': None}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _entry():
    try:
        raw = REGISTRY_PATH.read_bytes()
        if len(raw) > MAX_ARTIFACT_BYTES:
            raise ValueError('registry_too_large')
        body = json.loads(raw)
        entries = [item for item in body['models'] if item.get('model_id') == 'ML-03']
        if body.get('registry_version') != 1 or len(entries) != 1 or entries[0].get('runtime_state') not in STATES:
            raise ValueError('invalid_registry')
        return entries[0], None
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None, 'invalid_or_unavailable_registry'


def registry_status():
    entry, error = _entry()
    if error:
        return {'model_id': 'ML-03', 'status': 'disabled', 'reason': '模型注册表无效或不可用，已回退统计。',
                'loaded_status': 'not_loaded', 'fallback_method': 'statistical_baseline'}
    state = entry['runtime_state']
    if state in {'approved', 'shadow', 'canary', 'active'}:
        try:
            _approved(entry)
        except (OSError, ValueError, TypeError, KeyError, ArithmeticError):
            return {'model_id': 'ML-03', 'status': 'disabled', 'reason': '批准记录、外部验收或模型文件无效，已回退统计。',
                    'version': entry.get('version'), 'artifact_hash': entry.get('artifact_sha256'),
                    'feature_schema_version': entry.get('feature_schema_version'), 'training_data_hash': entry.get('training_data_sha256'),
                    'approval_status': 'invalid', 'loaded_status': 'not_loaded', 'supported_scope': [],
                    'last_healthcheck': None, 'fallback_method': 'statistical_baseline', 'approved_at': None}
    with _lock:
        health = dict(_health)
    loaded = health['loaded_status'] if state in {'shadow', 'canary', 'active'} and health['artifact_sha256'] == entry.get('artifact_sha256') else 'not_loaded'
    return {'model_id': 'ML-03', 'status': state, 'reason': entry.get('reason') or '按注册状态控制推理。',
            'version': entry.get('version'), 'artifact_hash': entry.get('artifact_sha256'),
            'feature_schema_version': entry.get('feature_schema_version'), 'training_data_hash': entry.get('training_data_sha256'),
            'approval_status': ('approved' if state in {'approved', 'shadow', 'canary', 'active'} and entry.get('approval_record')
                                else 'not_checked' if state == 'disabled' and entry.get('approval_record') else 'research_only'),
            'loaded_status': loaded, 'supported_scope': entry.get('supported_repository_ids') or [],
            'last_healthcheck': health['last_healthcheck'] if loaded != 'not_loaded' else None,
            'fallback_method': 'statistical_baseline', 'approved_at': entry.get('approved_at')}


def _read_approved(relative, expected_hash):
    if not isinstance(relative, str) or not isinstance(expected_hash, str) or not re.fullmatch(r'[0-9a-f]{64}', expected_hash):
        raise ValueError('missing_trusted_artifact')
    root = APPROVED_ROOT.resolve()
    path = Path(relative)
    target = (root / path).resolve()
    if path.is_absolute() or not target.is_relative_to(root) or not target.is_file() or target.stat().st_size > MAX_ARTIFACT_BYTES:
        raise ValueError('untrusted_artifact_path')
    data = target.read_bytes()
    if _sha(data) != expected_hash:
        raise ValueError('artifact_hash_mismatch')
    return json.loads(data)


def _approved(entry):
    model_hash = entry.get('artifact_sha256')
    approval = _read_approved(entry.get('approval_record'), entry.get('approval_record_sha256'))
    if not isinstance(approval, dict) or approval.get('decision') != 'approved_for_limited_release' or approval.get('model_sha256') != model_hash:
        raise ValueError('approval_missing_or_mismatch')
    if approval.get('feature_schema_version') != entry.get('feature_schema_version'):
        raise ValueError('approval_feature_schema_mismatch')
    reviewers = approval.get('reviewers')
    if (not isinstance(reviewers, list) or len(reviewers) != 2 or any(not isinstance(value, str) or not value.strip() for value in reviewers)
            or len({value.strip().casefold() for value in reviewers}) < 2 or type(approval.get('reviewed_repository_count')) is not int
            or approval['reviewed_repository_count'] < 40 or approval.get('conflicts_resolved') is not True
            or approval.get('business_review_passed') is not True
            or not isinstance(approval.get('approver'), str) or not approval['approver'].strip()
            or not isinstance(approval.get('approved_at'), str) or approval.get('approved_at') != entry.get('approved_at')):
        raise ValueError('human_review_incomplete')
    external = _read_approved(approval.get('external_result'), approval.get('external_result_sha256'))
    if (not isinstance(external, dict) or external.get('numerical_gate_passed') is not True or external.get('model_sha256') != model_hash
            or not re.fullmatch(r'[0-9a-f]{64}', str(external.get('protocol_sha256', '')))
            or external.get('protocol_sha256') != approval.get('protocol_sha256')
            or external.get('training_data_sha256') != entry.get('training_data_sha256')):
        raise ValueError('external_validation_not_passed')
    reviews = _read_approved(approval.get('review_manifest'), approval.get('review_manifest_sha256'))
    if not isinstance(reviews, dict) or not isinstance(reviews.get('items'), list) or len(reviews['items']) < 40:
        raise ValueError('human_review_evidence_missing')
    external_details = _read_approved(approval.get('external_details'), approval.get('external_details_sha256'))
    if not isinstance(external_details, list):
        raise ValueError('human_review_evidence_invalid')
    external_repositories = {}
    for item in external_details:
        if (not isinstance(item, dict) or type(item.get('repository_id')) is not int or item['repository_id'] <= 0
                or item['repository_id'] in external_repositories or type(item.get('in_domain')) is not bool
                or type(item.get('cluster')) is not int or item['cluster'] < 0):
            raise ValueError('human_review_evidence_invalid')
        external_repositories[item['repository_id']] = item
    seen_repositories = set()
    supported_clusters = set()
    agreement_count = 0
    reviewer_ids = {value.strip().casefold() for value in reviewers}
    for item in reviews['items']:
        if not isinstance(item, dict) or type(item.get('repository_id')) is not int or item['repository_id'] <= 0:
            raise ValueError('human_review_evidence_invalid')
        pair = (item.get('reviewer_a'), item.get('reviewer_b'))
        external_item = external_repositories.get(item['repository_id'])
        if (any(not isinstance(value, str) or not value.strip() for value in pair)
                or {value.strip().casefold() for value in pair} != reviewer_ids
                or item.get('assessment_a') not in {'supports', 'opposes', 'uncertain'}
                or item.get('assessment_b') not in {'supports', 'opposes', 'uncertain'}
                or any(not isinstance(item.get(key), str) or not item[key].strip() for key in ('reason_a', 'reason_b', 'resolution'))
                or not external_item or not external_item['in_domain'] or type(item.get('cluster_id')) is not int
                or item['cluster_id'] != external_item['cluster']):
            raise ValueError('human_review_evidence_invalid')
        seen_repositories.add(item['repository_id'])
        agreement_count += item['assessment_a'] == item['assessment_b']
        if item['assessment_a'] == item['assessment_b'] == 'supports':
            supported_clusters.add(item['cluster_id'])
    if (len(seen_repositories) < 40 or len(seen_repositories) != len(reviews['items'])
            or approval['reviewed_repository_count'] != len(seen_repositories)):
        raise ValueError('human_review_evidence_invalid')
    agreement = approval.get('review_agreement_rate')
    if type(agreement) not in (int, float) or not math.isfinite(agreement) or not math.isclose(agreement, agreement_count / len(reviews['items']), abs_tol=1e-9):
        raise ValueError('human_review_evidence_invalid')
    model = _read_approved(entry.get('approved_artifact'), model_hash)
    if (not isinstance(model, dict) or model.get('feature_schema_version') != entry.get('feature_schema_version')
            or model.get('feature_schema_version') not in {'maintenance-shape-v1', 'maintenance-temporal-shape-v2'}):
        raise ValueError('feature_schema_mismatch')
    from backend.app.ml.maintenance_numeric_worker import predict
    names, lows, highs = model.get('feature_names'), model.get('feature_min'), model.get('feature_max')
    if not isinstance(names, list) or not isinstance(lows, list) or not isinstance(highs, list) or len(names) != len(lows) or len(names) != len(highs):
        raise ValueError('model_schema_invalid')
    if any(type(low) not in (int, float) or type(high) not in (int, float) or not math.isfinite(low) or not math.isfinite(high) or abs(low) > 1e12 or abs(high) > 1e12 for low, high in zip(lows, highs)):
        raise ValueError('model_schema_invalid')
    predict(model, {name: (low + high) / 2 for name, low, high in zip(names, lows, highs)})
    labels = approval.get('cluster_labels')
    centers = model.get('centers')
    if not isinstance(labels, dict) or not isinstance(centers, list) or set(labels) != {str(index) for index in range(len(centers))}:
        raise ValueError('cluster_labels_missing')
    if supported_clusters != set(range(len(centers))):
        raise ValueError('human_review_evidence_invalid')
    for name in labels.values():
        if not isinstance(name, str) or not name.strip() or len(name) > 80 or any(word in name for word in ('高质量', '低质量', '不可靠', '推荐采用', '项目死亡')):
            raise ValueError('invalid_cluster_label')
    scope = entry.get('supported_repository_ids')
    if not isinstance(scope, list) or not scope or any(type(value) is not int or value <= 0 for value in scope):
        raise ValueError('approved_scope_missing')
    return model, labels, set(scope)


def requested_schema():
    entry, error = _entry()
    if error or entry['runtime_state'] not in {'shadow', 'canary', 'active'}:
        return None
    return entry.get('feature_schema_version')


def _record(reason, elapsed_ms, version=None, schema_version=None):
    with _lock:
        _counters['requests'] += 1
        _counters[reason] += 1
        _latencies.append(elapsed_ms)
    logger.info(json.dumps({'event': 'ml03_inference', 'model_version': version, 'feature_schema_version': schema_version,
                            'coverage': 'complete', 'outcome': reason, 'latency_ms': round(elapsed_ms, 3)},
                           ensure_ascii=False, separators=(',', ':')))


def record_data_status(reason):
    with _lock:
        _counters[f'data_{reason}'] += 1
    logger.info(json.dumps({'event': 'ml03_data_status', 'reason': reason}, ensure_ascii=False, separators=(',', ':')))


def infer(repository_id, as_of, source_hash, feature_values, schema_version, evidence=None):
    """仅推理具有完整批准记录的可信版本；记录身份真实性依赖外部审核。"""
    started = time.monotonic()
    entry, error = _entry()
    if error or entry['runtime_state'] not in {'shadow', 'canary', 'active'}:
        _record(error or 'model_not_enabled', (time.monotonic()-started)*1000, schema_version=schema_version)
        return {'status': 'fallback', 'reason': error or 'model_not_enabled'}
    state = entry['runtime_state']
    try:
        model, labels, scope = _approved(entry)
        if repository_id not in scope:
            raise ValueError('repository_outside_approved_scope')
        if schema_version != entry.get('feature_schema_version'):
            raise ValueError('feature_schema_mismatch')
        limits = model.get('applicability', {})
        if not isinstance(limits, dict):
            raise ValueError('applicability_invalid')
        for limit, field in (('commits_52w_min', 'commits_52w'), ('prs_created_52w_min', 'prs_created_52w')):
            if limit in limits:
                minimum = limits[limit]
                actual = evidence.get(field) if isinstance(evidence, dict) else None
                if type(minimum) is not int or minimum < 0 or type(actual) is not int or actual < minimum:
                    _record('below_activity_scope', (time.monotonic()-started)*1000, entry.get('version'), schema_version)
                    return {'status': 'fallback', 'reason': 'below_activity_scope'}
        if not isinstance(source_hash, str) or not re.fullmatch(r'[0-9a-f]{64}', source_hash):
            raise ValueError('source_hash_invalid')
        key = (repository_id, as_of, schema_version, entry['version'], source_hash, entry['artifact_sha256'], entry['approval_record_sha256'])
        with _lock:
            cached = _cache.get(key)
            if cached is not None:
                _cache.move_to_end(key)
        if cached is None:
            payload = json.dumps({'model': model, 'features': feature_values}, allow_nan=False)
            result = subprocess.run([sys.executable, '-I', str(WORKER)], input=payload, text=True,
                                    capture_output=True, timeout=INFERENCE_TIMEOUT_SECONDS,
                                    env={'PATH': '/usr/bin:/bin', 'PYTHONHASHSEED': '0'}, check=False)
            if result.returncode != 0 or len(result.stdout) > 4096:
                raise ValueError('inference_failed')
            answer = json.loads(result.stdout)
            peak = answer.get('peak_rss_bytes')
            if type(peak) is not int or peak < 0 or peak > 128 * 1024 * 1024:
                raise ValueError('memory_budget_exceeded')
            with _lock:
                _memory_peaks.append(peak)
            if answer.get('status') == 'out_of_distribution':
                with _lock:
                    _health.update(loaded_status='loaded', last_healthcheck=iso_z(utc_now()), artifact_sha256=entry['artifact_sha256'])
                _record('out_of_distribution', (time.monotonic()-started)*1000, entry.get('version'), schema_version)
                return {'status': 'unclassified', 'reason': 'out_of_distribution'}
            index = answer.get('cluster')
            if answer.get('status') != 'available' or type(index) is not int or str(index) not in labels:
                raise ValueError('invalid_model_output')
            cached = {'status': 'available', 'model_id': 'ML-03', 'model_version': entry['version'],
                      'pattern_id': f'cluster_{index}', 'pattern_name': labels[str(index)]}
            with _lock:
                _cache[key] = cached
                _cache.move_to_end(key)
                while len(_cache) > 256:
                    _cache.popitem(last=False)
                _health.update(loaded_status='loaded', last_healthcheck=iso_z(utc_now()), artifact_sha256=entry['artifact_sha256'])
            outcome = 'success'
        else:
            outcome = 'cache_hit'
        current, current_error = _entry()
        if current_error or current != entry:
            raise ValueError('registry_changed_during_inference')
        _record(outcome, (time.monotonic()-started)*1000, entry.get('version'), schema_version)
        return {'status': 'shadow', 'reason': 'shadow_only'} if state == 'shadow' else dict(cached)
    except subprocess.TimeoutExpired:
        reason = 'inference_timeout'
    except ValueError as exc:
        known = {'missing_trusted_artifact', 'untrusted_artifact_path', 'artifact_hash_mismatch', 'approval_missing_or_mismatch',
                 'approval_feature_schema_mismatch', 'human_review_incomplete', 'human_review_evidence_missing', 'human_review_evidence_invalid',
                 'external_validation_not_passed', 'feature_schema_mismatch', 'model_schema_invalid', 'cluster_labels_missing',
                 'invalid_cluster_label', 'approved_scope_missing', 'repository_outside_approved_scope', 'source_hash_invalid',
                 'applicability_invalid', 'inference_failed', 'invalid_model_output', 'memory_budget_exceeded', 'registry_changed_during_inference'}
        reason = str(exc) if str(exc) in known else 'model_unavailable_or_invalid'
    except (OSError, TypeError, KeyError, ArithmeticError):
        reason = 'model_unavailable_or_invalid'
    with _lock:
        _health.update(loaded_status='failed', last_healthcheck=iso_z(utc_now()), artifact_sha256=entry.get('artifact_sha256'))
    _record(reason, (time.monotonic()-started)*1000, entry.get('version'), schema_version)
    return {'status': 'fallback', 'reason': reason}


def monitoring():
    with _lock:
        counters, durations, memory, cache_entries = dict(_counters), sorted(_latencies), list(_memory_peaks), len(_cache)
    def percentile(q):
        return durations[min(len(durations)-1, math.ceil(q * len(durations))-1)] if durations else None
    return {'counters': counters, 'latency_ms_p50': percentile(.50), 'latency_ms_p95': percentile(.95),
            'latency_samples': len(durations), 'peak_rss_bytes_max': max(memory) if memory else None, 'cache_entries': cache_entries,
            'note': '进程内诊断数据，重启后清空；不是生产监控服务等级。'}
