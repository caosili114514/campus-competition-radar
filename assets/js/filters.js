import {
  deriveRegistrationStatus,
  getDeadlineTimestamp,
  getRegistrationDisplay,
  parseDateValue,
  sortByDeadline,
} from './dates.js';

export const DEFAULT_FILTERS = Object.freeze({
  query: '',
  category: '',
  competitionLevel: '',
  region: '',
  eligibleParticipants: '',
  registrationStatus: '',
  sort: 'deadline_asc',
});

export const SORT_OPTIONS = Object.freeze([
  { value: 'deadline_asc', label: '报名截止：近 → 远' },
  { value: 'deadline_desc', label: '报名截止：远 → 近' },
  { value: 'published_desc', label: '最近发布/采集优先' },
]);

export const REGISTRATION_STATUS_OPTIONS = Object.freeze([
  { value: 'open', label: '报名中（已核验）' },
  { value: 'pending_window', label: '报名窗口内（待核验）' },
  { value: 'broken', label: '链接异常' },
  { value: 'upcoming', label: '即将开始' },
  { value: 'pending_upcoming', label: '即将开始（待核验）' },
  { value: 'closed', label: '已截止' },
  { value: 'unknown', label: '待确认' },
  { value: 'pending_unknown', label: '待核验' },
]);

export const CATEGORY_ORDER = Object.freeze([
  '创新创业',
  '学科竞赛',
  '人工智能',
  '数字媒体',
  '设计',
  '文化创意',
  '社会实践',
  '思政教育',
  '其他',
  '待确认',
]);

const LEVEL_ORDER = Object.freeze(['国家级', '省级', '校级', '国际级', '其他', '待确认']);

function sortFilterValues(field, values) {
  const fixedOrder = field === 'category'
    ? CATEGORY_ORDER
    : field === 'competition_level'
      ? LEVEL_ORDER
      : null;
  if (!fixedOrder) return values.sort((left, right) => left.localeCompare(right, 'zh-CN'));
  const rank = new Map(fixedOrder.map((value, index) => [value, index]));
  return values.sort((left, right) => {
    const leftRank = rank.get(left) ?? Number.MAX_SAFE_INTEGER;
    const rightRank = rank.get(right) ?? Number.MAX_SAFE_INTEGER;
    if (leftRank !== rightRank) return leftRank - rightRank;
    return left.localeCompare(right, 'zh-CN');
  });
}

const EMPTY_FILTER_VALUES = new Set(['', 'all', '全部', 'any']);

function normalizeText(value) {
  return String(value ?? '')
    .normalize('NFKC')
    .toLocaleLowerCase('zh-CN')
    .trim();
}

function filterValue(value) {
  if (value === null || value === undefined) return '';
  const text = String(value).trim();
  return EMPTY_FILTER_VALUES.has(text.toLocaleLowerCase('zh-CN')) ? '' : text;
}

function recordField(record, field) {
  if (!record || typeof record !== 'object') return null;
  switch (field) {
    case 'competition_level':
    case 'competitionLevel':
    case 'level':
      return record.competition_level ?? record.level ?? null;
    case 'eligible_participants':
    case 'eligibleParticipants':
    case 'audience':
      return record.eligible_participants ?? record.audience ?? null;
    case 'registration_deadline':
    case 'registrationDeadline':
      return record.registration_deadline ?? record.registration_end ?? null;
    case 'registration_status':
    case 'registrationStatus':
      return record.registration_status ?? null;
    case 'requirements':
    case 'work_requirements':
      return record.requirements ?? record.work_requirements ?? null;
    default:
      return record[field] ?? null;
  }
}

function fieldMatches(value, expected) {
  const target = normalizeText(expected);
  if (!target) return true;
  if (Array.isArray(value)) {
    return value.some((item) => normalizeText(item) === target);
  }
  return normalizeText(value) === target;
}

export function getSearchText(record) {
  if (!record || typeof record !== 'object') return '';
  const fields = [
    record.title,
    record.organizer,
    record.category,
    record.competition_level,
    record.level,
    record.region,
    record.eligible_participants,
    record.audience,
    record.description,
    record.requirements,
    record.source_name,
    record.verification_notes,
  ];
  return normalizeText(fields.filter((value) => value !== null && value !== undefined).join(' '));
}

export function matchesSearch(record, query) {
  const tokens = normalizeText(query).split(/\s+/).filter(Boolean);
  if (!tokens.length) return true;
  const haystack = getSearchText(record);
  return tokens.every((token) => haystack.includes(token));
}

export function filterCompetitions(records, filters = {}, now = new Date()) {
  if (!Array.isArray(records)) return [];
  const query = filters.query ?? filters.q ?? filters.keyword ?? '';
  const category = filterValue(filters.category);
  const level = filterValue(
    filters.competitionLevel ?? filters.level ?? filters.competition_level,
  );
  const region = filterValue(filters.region);
  const audience = filterValue(
    filters.eligibleParticipants ?? filters.audience ?? filters.eligible_participants,
  );
  const wantedStatus = normalizeText(
    filters.registrationStatus ?? filters.registration_status ?? filters.status ?? '',
  );

  return records.filter((record) => {
    if (!record || typeof record !== 'object') return false;
    if (!matchesSearch(record, query)) return false;
    if (!fieldMatches(recordField(record, 'category'), category)) return false;
    if (!fieldMatches(recordField(record, 'competition_level'), level)) return false;
    if (!fieldMatches(recordField(record, 'region'), region)) return false;
    if (!fieldMatches(recordField(record, 'eligible_participants'), audience)) return false;
    if (wantedStatus) {
      const display = getRegistrationDisplay(record, now);
      if (normalizeText(display.key) !== wantedStatus) return false;
    }
    return true;
  });
}

function publishedTimestamp(record) {
  return parseDateValue(record?.published_at, 'start')?.getTime()
    ?? parseDateValue(record?.fetched_at, 'start')?.getTime()
    ?? null;
}

export function sortCompetitions(records, sort = 'deadline_asc') {
  if (!Array.isArray(records)) return [];
  if (sort === 'deadline_desc') return sortByDeadline(records, 'desc');
  if (sort === 'published_desc') {
    return [...records].sort((left, right) => {
      const leftTime = publishedTimestamp(left);
      const rightTime = publishedTimestamp(right);
      if (leftTime === null && rightTime === null) return 0;
      if (leftTime === null) return 1;
      if (rightTime === null) return -1;
      if (rightTime === leftTime) {
        return (getDeadlineTimestamp(left) ?? Number.MAX_SAFE_INTEGER)
          - (getDeadlineTimestamp(right) ?? Number.MAX_SAFE_INTEGER);
      }
      return rightTime - leftTime;
    });
  }
  return sortByDeadline(records, 'asc');
}

export function getFilterOptions(records, field) {
  if (!Array.isArray(records)) return [];
  const canonical = {
    competitionLevel: 'competition_level',
    level: 'competition_level',
    eligibleParticipants: 'eligible_participants',
    audience: 'eligible_participants',
  }[field] ?? field;

  const values = new Set();
  for (const record of records) {
    const raw = recordField(record, canonical);
    const items = Array.isArray(raw) ? raw : [raw];
    for (const item of items) {
      if (item === null || item === undefined) continue;
      const text = String(item).trim();
      if (text) values.add(text);
    }
  }
  return sortFilterValues(canonical, [...values]);
}

export function countActiveFilters(filters = {}) {
  const values = [
    filters.query ?? filters.q ?? filters.keyword,
    filters.category,
    filters.competitionLevel ?? filters.level ?? filters.competition_level,
    filters.region,
    filters.eligibleParticipants ?? filters.audience ?? filters.eligible_participants,
    filters.registrationStatus ?? filters.registration_status ?? filters.status,
  ];
  return values.filter((value) => filterValue(value)).length;
}

export function getDerivedRegistrationCounts(records, now = new Date()) {
  const counts = { open: 0, upcoming: 0, closed: 0, unknown: 0 };
  if (!Array.isArray(records)) return counts;
  for (const record of records) {
    const status = deriveRegistrationStatus(record, now);
    if (Object.hasOwn(counts, status)) counts[status] += 1;
    else counts.unknown += 1;
  }
  return counts;
}

export function filtersToSearchParams(filters = {}) {
  const params = new URLSearchParams();
  const mappings = [
    ['q', filters.query ?? filters.q],
    ['category', filters.category],
    ['level', filters.competitionLevel ?? filters.level],
    ['region', filters.region],
    ['audience', filters.eligibleParticipants ?? filters.audience],
    ['status', filters.registrationStatus ?? filters.status],
    ['sort', filters.sort],
  ];
  for (const [key, value] of mappings) {
    const text = filterValue(value);
    if (!text) continue;
    if (key === 'sort' && text === DEFAULT_FILTERS.sort) continue;
    params.set(key, text);
  }
  return params;
}

export function filtersFromSearchParams(queryLike) {
  const get = (key) => {
    if (queryLike instanceof URLSearchParams) return queryLike.get(key) ?? '';
    if (queryLike && typeof queryLike === 'object') return queryLike[key] ?? '';
    return '';
  };
  const sort = filterValue(get('sort'));
  const status = filterValue(get('status')).toLowerCase();
  return {
    ...DEFAULT_FILTERS,
    query: String(get('q') ?? ''),
    category: String(get('category') ?? ''),
    competitionLevel: String(get('level') ?? ''),
    region: String(get('region') ?? ''),
    eligibleParticipants: String(get('audience') ?? ''),
    registrationStatus: REGISTRATION_STATUS_OPTIONS.some((option) => option.value === status)
      ? status
      : '',
    sort: SORT_OPTIONS.some((option) => option.value === sort)
      ? sort
      : DEFAULT_FILTERS.sort,
  };
}