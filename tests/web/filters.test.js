import test from 'node:test';
import assert from 'node:assert/strict';

import {
  DEFAULT_FILTERS,
  REGISTRATION_STATUS_OPTIONS,
  countActiveFilters,
  filterCompetitions,
  filtersFromSearchParams,
  filtersToSearchParams,
  getDerivedRegistrationCounts,
  getFilterOptions,
  matchesSearch,
  sortCompetitions,
} from '../../assets/js/filters.js';

import { getRegistrationDisplay } from '../../assets/js/dates.js';

const NOW = new Date(2026, 9, 24, 12, 0, 0);

const records = [
  {
    id: 'math',
    title: '全国大学生数学建模竞赛',
    organizer: '数学教学指导委员会',
    category: '学科竞赛',
    competition_level: '国家级',
    region: '全国',
    eligible_participants: '本科生',
    description: '数学建模与数据分析综合赛事',
    requirements: '三人组队',
    source_name: '示例高校通知网',
    registration_start: '2026-10-01',
    registration_deadline: '2026-11-10',
    registration_status: 'closed',
    verification_status: 'verified',
    published_at: '2026-10-18',
  },
  {
    id: 'innovation',
    title: '创新创业挑战赛',
    organizer: '创新创业学院',
    category: '创新创业',
    competition_level: '省级',
    region: '华东',
    eligible_participants: '研究生',
    description: '创业计划与路演',
    source_name: '示例教务网',
    registration_start: '2026-10-20',
    registration_deadline: '2026-10-23',
    registration_status: 'open',
    verification_status: 'verified',
    published_at: '2026-10-20',
  },
  {
    id: 'ai',
    title: '人工智能算法赛',
    organizer: '人工智能学院',
    category: '创新创业',
    competition_level: '国家级',
    region: '全国',
    eligible_participants: ['本科生', '研究生'],
    description: '算法设计与工程实践',
    source_name: '示例科研通知',
    registration_start: '2026-11-01',
    registration_deadline: '2026-12-01',
    registration_status: 'open',
    verification_status: 'verified',
    published_at: '2026-10-21',
  },
  {
    id: 'undated',
    title: '待定日期竞赛',
    organizer: '待定学院',
    category: '其他',
    competition_level: '校级',
    region: '校内',
    eligible_participants: '本科生',
    registration_start: null,
    registration_deadline: null,
    registration_status: 'unknown',
    verification_status: 'verified',
    published_at: null,
  },
];

test('search treats whitespace-separated tokens as AND conditions', () => {
  assert.equal(matchesSearch(records[0], '数学 建模'), true);
  assert.equal(matchesSearch(records[0], '数学 创业'), false);
  assert.equal(matchesSearch(records[1], '创新创业学院'), true);
  assert.equal(matchesSearch(records[0], ''), true);
});

test('combined filters apply category, level, region, audience and dynamic status together', () => {
  const result = filterCompetitions(records, {
    query: '数学',
    category: '学科竞赛',
    competitionLevel: '国家级',
    region: '全国',
    eligibleParticipants: '本科生',
    registrationStatus: 'open',
  }, NOW);
  assert.deepEqual(result.map((item) => item.id), ['math']);
});

test('registration status filter uses the same display classification as cards', () => {
  assert.deepEqual(
    filterCompetitions(records, { registrationStatus: 'closed' }, NOW).map((item) => item.id),
    ['innovation'],
  );
  assert.deepEqual(
    filterCompetitions(records, { registrationStatus: 'upcoming' }, NOW).map((item) => item.id),
    ['ai'],
  );
  assert.deepEqual(
    filterCompetitions(records, { registrationStatus: 'unknown' }, NOW).map((item) => item.id),
    ['undated'],
  );
});

test('array audience values can be matched by exact option text', () => {
  const result = filterCompetitions(records, { eligibleParticipants: '研究生' }, NOW);
  assert.deepEqual(result.map((item) => item.id), ['innovation', 'ai']);
});

test('sorting by deadline supports both directions with unknown deadlines last', () => {
  assert.deepEqual(
    sortCompetitions(records, 'deadline_asc').map((item) => item.id),
    ['innovation', 'math', 'ai', 'undated'],
  );
  assert.deepEqual(
    sortCompetitions(records, 'deadline_desc').map((item) => item.id),
    ['ai', 'math', 'innovation', 'undated'],
  );
  assert.deepEqual(
    sortCompetitions(records, 'published_desc').map((item) => item.id),
    ['ai', 'innovation', 'math', 'undated'],
  );
});

test('filter options are unique, flattened and deterministically sorted', () => {
  assert.deepEqual(getFilterOptions(records, 'category'), ['创新创业', '学科竞赛', '其他']);
  assert.deepEqual(
    getFilterOptions(records, 'eligibleParticipants'),
    ['本科生', '研究生'],
  );
  assert.deepEqual(countActiveFilters({ ...DEFAULT_FILTERS, query: '数学', region: '全国' }), 2);
});

test('derived registration counts cover every status', () => {
  const counts = getDerivedRegistrationCounts(records, NOW);
  assert.deepEqual(counts, { open: 1, upcoming: 1, closed: 1, unknown: 1 });
});

test('filter query params round-trip through the hash-compatible representation', () => {
  const filters = {
    ...DEFAULT_FILTERS,
    query: '数学 建模',
    category: '学科竞赛',
    competitionLevel: '国家级',
    region: '全国',
    eligibleParticipants: '本科生',
    registrationStatus: 'open',
    sort: 'deadline_desc',
  };
  const params = filtersToSearchParams(filters);
  assert.equal(params.get('q'), '数学 建模');
  assert.equal(params.get('level'), '国家级');
  assert.equal(params.get('status'), 'open');
  assert.deepEqual(filtersFromSearchParams(params), filters);
});
test('recent discovery sorting falls back to fetched_at when published_at is missing', () => {
  const items = [
    { id: 'published', published_at: '2026-10-20', fetched_at: '2026-10-24' },
    { id: 'fetched', published_at: null, fetched_at: '2026-10-25' },
    { id: 'none', published_at: null, fetched_at: null },
  ];
  assert.deepEqual(
    sortCompetitions(items, 'published_desc').map((item) => item.id),
    ['fetched', 'published', 'none'],
  );
});
test('every registration status option maps to matching card display keys and labels', () => {
  const source = [
    { id: 'open-verified', registration_start: '2026-10-01', registration_deadline: '2026-10-30', verification_status: 'verified' },
    { id: 'open-pending', registration_start: '2026-10-01', registration_deadline: '2026-10-30', verification_status: 'pending' },
    { id: 'open-incomplete', registration_start: '2026-10-01', registration_deadline: '2026-10-30', verification_status: 'incomplete' },
    { id: 'broken', registration_start: '2026-10-01', registration_deadline: '2026-10-30', verification_status: 'broken' },
    { id: 'upcoming-verified', registration_start: '2026-10-28', registration_deadline: '2026-11-02', verification_status: 'verified' },
    { id: 'upcoming-pending', registration_start: '2026-10-28', registration_deadline: '2026-11-02', verification_status: 'pending' },
    { id: 'closed', registration_start: '2026-10-01', registration_deadline: '2026-10-23', verification_status: 'pending' },
    { id: 'unknown-verified', registration_start: null, registration_deadline: null, verification_status: 'verified' },
    { id: 'unknown-pending', registration_start: null, registration_deadline: null, verification_status: 'pending' },
  ];
  const expected = {
    open: ['open-verified'],
    pending_window: ['open-pending', 'open-incomplete'],
    broken: ['broken'],
    upcoming: ['upcoming-verified'],
    pending_upcoming: ['upcoming-pending'],
    closed: ['closed'],
    unknown: ['unknown-verified'],
    pending_unknown: ['unknown-pending'],
  };
  assert.deepEqual(
    REGISTRATION_STATUS_OPTIONS.map((option) => option.value),
    Object.keys(expected),
  );
  for (const option of REGISTRATION_STATUS_OPTIONS) {
    const results = filterCompetitions(source, { registrationStatus: option.value }, NOW);
    assert.deepEqual(results.map((record) => record.id), expected[option.value]);
    for (const record of results) {
      const display = getRegistrationDisplay(record, NOW);
      assert.equal(display.key, option.value);
      assert.equal(display.label, option.label);
    }
  }
});
test('legacy and new registration status query values remain accepted', () => {
  for (const option of REGISTRATION_STATUS_OPTIONS) {
    const params = new URLSearchParams({ status: option.value });
    assert.equal(filtersFromSearchParams(params).registrationStatus, option.value);
  }
  for (const legacyValue of ['open', 'upcoming', 'closed', 'unknown']) {
    const params = new URLSearchParams({ status: legacyValue });
    assert.equal(filtersFromSearchParams(params).registrationStatus, legacyValue);
  }
  assert.equal(
    filtersFromSearchParams(new URLSearchParams({ status: 'not-a-status' })).registrationStatus,
    '',
  );
});