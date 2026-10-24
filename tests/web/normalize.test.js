import test from 'node:test';
import assert from 'node:assert/strict';

import {
  DataShapeError,
  normalizeCompetitionsPayload,
  normalizeMetaPayload,
  normalizeRecord,
  normalizeSourcesPayload,
} from '../../assets/js/normalize.js';

test('the authoritative record contract is preserved including verification history', () => {
  const raw = {
    id: 'record-1',
    title: '示例竞赛',
    organizer: '示例主办方',
    category: '学科竞赛',
    competition_level: '国家级',
    eligible_participants: '本科生',
    team_size: '3–5 人',
    registration_start: '2026-10-01',
    registration_deadline: '2026-10-30',
    event_start: '2026-11-10',
    event_end: '2026-11-12',
    description: '说明',
    requirements: '要求',
    official_notice_url: 'https://example.com/notice',
    registration_url: 'https://example.com/register',
    source_name: '示例来源',
    source_url: 'https://example.com/source',
    published_at: '2026-09-20',
    fetched_at: '2026-10-24',
    last_verified_at: '2026-10-23',
    verification_status: 'verified',
    registration_status: 'open',
    confidence: 0.9,
    content_hash: 'abc123',
    region: '全国',
    is_demo: true,
    missing_fields: [],
    verification_notes: '已核对',
    verification_history: [
      {
        checked_at: '2026-10-23T10:00:00+08:00',
        status: 'verified',
        method: 'manual',
        note: '链接可访问',
        http_status: 200,
      },
    ],
  };
  const payload = normalizeCompetitionsPayload({
    schema_version: '1.0.0',
    data_mode: 'demo',
    generated_at: '2026-10-24T20:00:00+08:00',
    records: [raw],
  });
  const record = payload.records[0];
  assert.equal(payload.data_mode, 'demo');
  assert.equal(record.competition_level, '国家级');
  assert.equal(record.eligible_participants, '本科生');
  assert.equal(record.registration_deadline, '2026-10-30');
  assert.equal(record.official_notice_url, 'https://example.com/notice');
  assert.equal(record.registration_url, 'https://example.com/register');
  assert.equal(record.verification_status, 'verified');
  assert.equal(record.verification_history.length, 1);
  assert.equal(record.verification_history[0].http_status, 200);
});

test('legacy field aliases are normalized without inventing a registration URL', () => {
  const record = normalizeRecord({
    id: 42,
    title: '别名测试',
    level: '省级',
    audience: '研究生',
    registration_end: '2026-12-01',
    work_requirements: '提交作品',
    canonical_url: 'https://example.com/original',
    verified: false,
    team_size_min: 2,
    team_size_max: 5,
    last_seen_at: '2026-10-24T12:00:00+08:00',
    is_demo: true,
  });
  assert.equal(record.id, '42');
  assert.equal(record.competition_level, '省级');
  assert.equal(record.eligible_participants, '研究生');
  assert.equal(record.registration_deadline, '2026-12-01');
  assert.equal(record.requirements, '提交作品');
  assert.equal(record.official_notice_url, 'https://example.com/original');
  assert.equal(record.registration_url, null);
  assert.equal(record.verification_status, 'pending');
  assert.equal(record.team_size, '2–5 人');
  assert.equal(record.fetched_at, '2026-10-24T12:00:00+08:00');
  assert.equal(record.is_demo, true);
});

test('meta and sources fallback fields normalize to the documented display contract', () => {
  const meta = normalizeMetaPayload({
    schema_version: '1.0.0',
    data_mode: 'live',
    generated_at: '2026-10-24T20:00:00+08:00',
    enabled_source_count: 3,
    checked_source_count: 3,
    failed_source_count: 1,
    record_count: 8,
    collection_status: 'partial',
    disclaimer: '部分源失败',
  });
  assert.equal(meta.summary.source_count, 3);
  assert.equal(meta.summary.success_count, 2);
  assert.equal(meta.summary.failure_count, 1);
  assert.equal(meta.summary.record_count, 8);
  assert.equal(meta.last_run.status, 'partial');
  assert.equal(meta.notice, '部分源失败');

  const sources = normalizeSourcesPayload({
    schema_version: '1.0.0',
    sources: [{
      id: 'source-1',
      name: '示例源',
      enabled: true,
      verified: false,
      status: 'failed',
      last_error: 'HTTP 500',
      records_found: 4,
      records_new: 2,
    }],
  });
  assert.equal(sources.sources[0].failure_reason, 'HTTP 500');
  assert.equal(sources.sources[0].records_added, 2);
  assert.equal(sources.sources[0].needs_manual_verification, true);
});

test('a malformed competitions payload throws a clear shape error', () => {
  assert.throws(
    () => normalizeCompetitionsPayload({ data_mode: 'live' }),
    (error) => error instanceof DataShapeError && /records/.test(error.message),
  );
});