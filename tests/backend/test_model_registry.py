import hashlib
import json
import logging
import subprocess
from pathlib import Path

import pytest

from backend.app.services import model_registry as registry
from scripts.disable_ml03 import disable


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def configured(monkeypatch, tmp_path):
    root = tmp_path/'approved'
    registry_path = tmp_path/'registry.json'
    monkeypatch.setattr(registry, 'APPROVED_ROOT', root)
    monkeypatch.setattr(registry, 'REGISTRY_PATH', registry_path)
    registry._cache.clear(); registry._counters.clear(); registry._latencies.clear()
    registry._health.update(loaded_status='not_loaded', last_healthcheck=None, artifact_sha256=None)
    artifact = {'format':'trusted-numeric-kmeans-v1', 'feature_schema_version':'maintenance-shape-v1',
                'feature_names':['commit_active_fraction'], 'scale_mean':[0.0], 'scale_scale':[1.0],
                'feature_min':[0.0], 'feature_max':[1.0], 'centers':[[0.0],[0.8]], 'distance_p99':[0.3,0.3]}
    model_hash = write(root/'v-test/model.json', artifact)
    external_hash = write(root/'v-test/external.json', {'numerical_gate_passed':True, 'model_sha256':model_hash, 'protocol_sha256':'d'*64, 'training_data_sha256':'f'*64})
    details = [{'repository_id':i+1, 'in_domain':True, 'cluster':i%2} for i in range(40)]
    details_hash = write(root/'v-test/details.json', details)
    reviews = {'items':[{'repository_id':i+1,'cluster_id':i%2,'reviewer_a':'test-reviewer-a','reviewer_b':'test-reviewer-b',
                         'assessment_a':'supports','assessment_b':'supports','reason_a':'test','reason_b':'test','resolution':'test'} for i in range(40)]}
    review_hash = write(root/'v-test/reviews.json', reviews)
    approval = {'decision':'approved_for_limited_release','model_sha256':model_hash,'reviewers':['test-reviewer-a','test-reviewer-b'],
                'reviewed_repository_count':40,'conflicts_resolved':True,'business_review_passed':True,'review_agreement_rate':1.0,
                'approver':'test-owner','approved_at':'2026-11-09T00:00:00Z',
                'external_result':'v-test/external.json','external_result_sha256':external_hash,
                'external_details':'v-test/details.json','external_details_sha256':details_hash,
                'cluster_labels':{'0':'低频活动','1':'间歇活动'}, 'feature_schema_version':'maintenance-shape-v1', 'protocol_sha256':'d'*64,
                'review_manifest':'v-test/reviews.json','review_manifest_sha256':review_hash}
    approval_hash = write(root/'v-test/approval.json', approval)
    entry = {'model_id':'ML-03','version':'fixture-v1','runtime_state':'active','artifact_sha256':model_hash,
             'feature_schema_version':'maintenance-shape-v1','training_data_sha256':'f'*64,'approved_artifact':'v-test/model.json',
             'approval_record':'v-test/approval.json','approval_record_sha256':approval_hash,
             'supported_repository_ids':[123], 'approved_at':'2026-11-09T00:00:00Z'}
    write(registry_path, {'registry_version':1,'models':[entry]})
    return entry, registry_path, root


def call(value=.1, repository_id=123, source='a'*64):
    return registry.infer(repository_id, '2026-11-09T00:00:00Z', source, {'commit_active_fraction':value}, 'maintenance-shape-v1')


def test_research_only_model_is_never_read_or_loaded(configured, monkeypatch):
    entry, path, _ = configured
    entry['runtime_state'] = 'research_only'
    write(path, {'registry_version':1,'models':[entry]})
    monkeypatch.setattr(registry, '_read_approved', lambda *_: (_ for _ in ()).throw(AssertionError('research artifact loaded')))
    assert call()['status'] == 'fallback'
    assert registry.registry_status()['loaded_status'] == 'not_loaded'


def test_approved_without_traffic_and_shadow_do_not_expose_a_label(configured):
    entry, path, _ = configured
    entry['runtime_state'] = 'approved'
    write(path, {'registry_version':1,'models':[entry]})
    assert call() == {'status':'fallback', 'reason':'model_not_enabled'}
    assert registry.registry_status()['loaded_status'] == 'not_loaded'
    entry['runtime_state'] = 'shadow'
    write(path, {'registry_version':1,'models':[entry]})
    assert call() == {'status':'shadow', 'reason':'shadow_only'}
    assert registry.registry_status()['loaded_status'] == 'loaded'


def test_approved_synthetic_fixture_runs_in_isolated_worker_and_disabling_rolls_back(configured, tmp_path):
    entry, path, _ = configured
    first = call()
    assert first['status'] == 'available' and first['pattern_id'] == 'cluster_0'
    assert call() == first
    assert registry.monitoring()['counters']['cache_hit'] == 1
    assert call(value=2, source='b'*64)['status'] == 'unclassified'
    events = tmp_path/'events.jsonl'
    assert disable(path, events, 'test rollback') is True
    assert call()['status'] == 'fallback'
    status = registry.registry_status()
    assert status['loaded_status'] == 'not_loaded' and status['approval_status'] == 'not_checked'
    assert json.loads(events.read_text())['from'] == 'active'
    assert disable(path, events, 'test rollback') is False
    assert len(events.read_text().splitlines()) == 1


def test_wrong_hash_missing_approval_and_scope_fail_closed(configured):
    entry, path, root = configured
    assert call(repository_id=999)['status'] == 'fallback'
    (root/'v-test/model.json').write_text('{}')
    assert call()['status'] == 'fallback'
    assert registry.registry_status()['status'] == 'disabled'
    entry['runtime_state'] = 'active'; entry['approval_record'] = '../outside.json'
    write(path, {'registry_version':1,'models':[entry]})
    assert call()['status'] == 'fallback'


@pytest.mark.parametrize('failure', ['business_decision', 'agreement', 'cluster_support', 'external_eligibility', 'review_reason'])
def test_incomplete_or_unsubstantiated_human_review_is_not_served(configured, failure):
    entry, path, root = configured
    review_path = root/'v-test/reviews.json'
    details_path = root/'v-test/details.json'
    approval_path = root/'v-test/approval.json'
    reviews = json.loads(review_path.read_text())
    details = json.loads(details_path.read_text())
    approval = json.loads(approval_path.read_text())
    if failure == 'business_decision':
        approval['business_review_passed'] = False
    elif failure == 'agreement':
        approval['review_agreement_rate'] = .8
    elif failure == 'cluster_support':
        for row in reviews['items']:
            if row['cluster_id'] == 1:
                row['assessment_a'] = row['assessment_b'] = 'opposes'
    elif failure == 'external_eligibility':
        details[0]['in_domain'] = False
    elif failure == 'review_reason':
        reviews['items'][0]['reason_a'] = ''
    approval['review_manifest_sha256'] = write(review_path, reviews)
    approval['external_details_sha256'] = write(details_path, details)
    entry['approval_record_sha256'] = write(approval_path, approval)
    write(path, {'registry_version':1,'models':[entry]})
    assert call()['status'] == 'fallback'
    assert registry.registry_status()['status'] == 'disabled'


def test_schema_and_quality_label_mismatch_are_not_served(configured):
    entry, path, root = configured
    entry['feature_schema_version'] = 'other-schema'
    write(path, {'registry_version':1,'models':[entry]})
    assert call()['status'] == 'fallback'
    entry['feature_schema_version'] = 'maintenance-shape-v1'
    approval_path = root/'v-test/approval.json'
    approval = json.loads(approval_path.read_text())
    approval['cluster_labels']['0'] = '高质量'
    entry['approval_record_sha256'] = write(approval_path, approval)
    write(path, {'registry_version':1,'models':[entry]})
    assert call()['status'] == 'fallback'
    assert registry.registry_status()['status'] == 'disabled'


def test_worker_timeout_is_reported_and_falls_back(configured, monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 2)
    monkeypatch.setattr(registry.subprocess, 'run', timeout)
    result = call()
    assert result == {'status':'fallback','reason':'inference_timeout'}
    assert registry.monitoring()['counters']['inference_timeout'] == 1


def test_monitoring_log_contains_operational_context_without_raw_features(configured, caplog):
    with caplog.at_level(logging.INFO, logger='repovantage.ml03'):
        assert call()['status'] == 'available'
    event = json.loads(caplog.records[-1].getMessage())
    assert event['event'] == 'ml03_inference' and event['coverage'] == 'complete'
    assert event['model_version'] == 'fixture-v1' and event['feature_schema_version'] == 'maintenance-shape-v1'
    assert event['outcome'] == 'success' and event['latency_ms'] >= 0
    assert 'commit_active_fraction' not in caplog.text and 'a'*64 not in caplog.text


def test_extreme_but_hashed_model_parameters_fail_closed(configured):
    entry, path, root = configured
    model_path = root/'v-test/model.json'
    model = json.loads(model_path.read_text())
    model['scale_scale'] = [1e-300]
    model_hash = write(model_path, model)
    external_path = root/'v-test/external.json'
    external = json.loads(external_path.read_text())
    external['model_sha256'] = model_hash
    external_hash = write(external_path, external)
    approval_path = root/'v-test/approval.json'
    approval = json.loads(approval_path.read_text())
    approval.update(model_sha256=model_hash, external_result_sha256=external_hash)
    entry.update(artifact_sha256=model_hash, approval_record_sha256=write(approval_path, approval))
    write(path, {'registry_version':1,'models':[entry]})
    assert call()['status'] == 'fallback'
    assert registry.registry_status()['status'] == 'disabled'
