import test from 'node:test';
import assert from 'node:assert/strict';

import {
  deriveRegistrationStatus,
  formatDate,
  getRegistrationDisplay,
  formatDateRange,
  formatDateTime,
  getDeadlineInfo,
  getDeadlineTimestamp,
  parseDateValue,
  registrationStatusMeta,
  sortByDeadline,
} from '../../assets/js/dates.js';

const NOW = new Date(2026, 9, 24, 12, 0, 0);

function record(overrides = {}) {
  return {
    id: 'test-001',
    title: '测试竞赛',
    registration_start: '2026-10-01',
    registration_deadline: '2026-10-30',
    ...overrides,
  };
}

test('date-only values honor start and end boundaries', () => {
  const start = parseDateValue('2026-10-24', 'start');
  const end = parseDateValue('2026-10-24', 'end');
  assert.equal(start.getHours(), 0);
  assert.equal(start.getMinutes(), 0);
  assert.equal(end.getHours(), 23);
  assert.equal(end.getMinutes(), 59);
  assert.equal(end.getSeconds(), 59);
  assert.equal(parseDateValue('2026-02-31', 'start'), null);
  assert.equal(parseDateValue(null), null);
});

test('registration status is derived from current time and ignores stale static status', () => {
  assert.equal(
    deriveRegistrationStatus(record({ registration_status: 'closed' }), NOW),
    'open',
  );
  assert.equal(
    deriveRegistrationStatus(record({
      registration_start: '2026-10-28',
      registration_deadline: '2026-11-02',
      registration_status: 'open',
    }), NOW),
    'upcoming',
  );
  assert.equal(
    deriveRegistrationStatus(record({
      registration_deadline: '2026-10-23',
      registration_status: 'open',
    }), NOW),
    'closed',
  );
});

test('expired deadlines show the exact closed label and missing dates are pending', () => {
  const expired = getDeadlineInfo(record({ registration_deadline: '2026-10-23' }), NOW);
  assert.equal(expired.expired, true);
  assert.equal(expired.label, '已截止');

  const today = getDeadlineInfo(record({ registration_deadline: '2026-10-24' }), NOW);
  assert.equal(today.label, '今天截止');
  assert.equal(today.days, 0);

  const missing = getDeadlineInfo(record({ registration_deadline: null }), NOW);
  assert.equal(missing.label, '待确认');
  assert.equal(missing.deadline, null);
});

test('registration status labels and tone mapping are stable', () => {
  assert.equal(registrationStatusMeta('open').label, '报名中');
  assert.equal(registrationStatusMeta('closed').label, '已截止');
  assert.equal(registrationStatusMeta('unknown').label, '待确认');
  assert.equal(registrationStatusMeta('unexpected').label, '待确认');
});

test('date formatting uses a visible pending fallback instead of fabricating dates', () => {
  assert.equal(formatDate(null), '待确认');
  assert.equal(formatDateTime(undefined), '待确认');
  assert.equal(formatDate('2026-10-24'), '2026-10-24');
  assert.equal(formatDateTime('2026-10-24'), '2026-10-24');
  assert.equal(formatDateRange(null, null), '待确认');
  assert.equal(formatDateRange('2026-10-24', null), '2026-10-24 – 待确认');
  assert.equal(formatDateRange('2026-11-01', '2026-11-03'), '2026-11-01 – 2026-11-03');
});

test('deadline sorting keeps missing values last in both directions and does not mutate input', () => {
  const records = [
    { id: 'none', title: '无截止日期', registration_deadline: null },
    { id: 'late', title: '较晚', registration_deadline: '2026-12-01' },
    { id: 'early', title: '较早', registration_deadline: '2026-11-01' },
  ];
  const originalOrder = records.map((item) => item.id);
  assert.deepEqual(sortByDeadline(records, 'asc').map((item) => item.id), ['early', 'late', 'none']);
  assert.deepEqual(sortByDeadline(records, 'desc').map((item) => item.id), ['late', 'early', 'none']);
  assert.deepEqual(records.map((item) => item.id), originalOrder);
  assert.equal(getDeadlineTimestamp(records[0]), null);
});
test('display status gates unverified and broken records while keeping expired priority', () => {
  const futureWindow = {
    registration_start: '2026-10-01',
    registration_deadline: '2026-10-30',
  };
  const verified = getRegistrationDisplay({ ...futureWindow, verification_status: 'verified' }, NOW);
  assert.equal(verified.key, 'open');
  assert.equal(verified.label, '报名中（已核验）');
  assert.equal(verified.confirmedOpen, true);

  const unverified = getRegistrationDisplay(futureWindow, NOW);
  assert.equal(unverified.key, 'pending_window');
  assert.equal(unverified.label, '报名窗口内（待核验）');
  assert.equal(unverified.confirmedOpen, false);

  const pending = getRegistrationDisplay({ ...futureWindow, verification_status: 'pending' }, NOW);
  assert.equal(pending.key, 'pending_window');
  assert.equal(pending.label, '报名窗口内（待核验）');
  assert.equal(pending.tone, 'warning');
  assert.equal(pending.confirmedOpen, false);

  const incomplete = getRegistrationDisplay({
    registration_start: '2026-10-28',
    registration_deadline: '2026-11-02',
    verification_status: 'incomplete',
  }, NOW);
  assert.equal(incomplete.key, 'pending_upcoming');
  assert.equal(incomplete.label, '即将开始（待核验）');

  const broken = getRegistrationDisplay({ ...futureWindow, verification_status: 'broken' }, NOW);
  assert.equal(broken.label, '链接异常');
  assert.equal(broken.tone, 'danger');

  const brokenExpired = getRegistrationDisplay({
    registration_start: '2026-10-01',
    registration_deadline: '2026-10-23',
    verification_status: 'broken',
  }, NOW);
  assert.equal(brokenExpired.label, '已截止');
  assert.equal(brokenExpired.tone, 'danger');

  const pendingExpired = getRegistrationDisplay({
    registration_start: '2026-10-01',
    registration_deadline: '2026-10-23',
    verification_status: 'pending',
  }, NOW);
  assert.equal(pendingExpired.label, '已截止');
});