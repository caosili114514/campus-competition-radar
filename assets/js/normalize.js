const VERIFICATION_STATUSES = new Set(['verified', 'pending', 'broken', 'expired', 'incomplete']);
const REGISTRATION_STATUSES = new Set(['open', 'upcoming', 'closed', 'unknown']);
const REQUIRED_RECORD_FIELDS = [
  'id', 'title', 'organizer', 'category', 'competition_level', 'eligible_participants',
  'team_size', 'registration_start', 'registration_deadline', 'event_start', 'event_end',
  'description', 'requirements', 'official_notice_url', 'registration_url', 'source_name',
  'source_url', 'published_at', 'fetched_at', 'last_verified_at', 'verification_status',
  'registration_status', 'confidence', 'content_hash', 'region', 'is_demo',
  'missing_fields', 'verification_notes',
];

export class DataShapeError extends Error {
  constructor(message, path = '') {
    super(message);
    this.name = 'DataShapeError';
    this.path = path;
  }
}

function firstPresent(...values) {
  for (const value of values) {
    if (value === null || value === undefined) continue;
    if (typeof value === 'string' && value.trim() === '') continue;
    return value;
  }
  return null;
}

function normalizeTeamSize(raw) {
  const explicit = firstPresent(raw.team_size, raw.teamSize);
  if (explicit !== null) {
    if (typeof explicit === 'number') return `${explicit} 人`;
    if (Array.isArray(explicit)) return explicit.map(String).filter(Boolean).join('–');
    return explicit;
  }
  const min = firstPresent(raw.team_size_min, raw.teamSizeMin);
  const max = firstPresent(raw.team_size_max, raw.teamSizeMax);
  if (min !== null && max !== null) {
    return String(min) === String(max) ? `${min} 人` : `${min}–${max} 人`;
  }
  if (min !== null) return `${min} 人以上`;
  if (max !== null) return `不超过 ${max} 人`;
  return null;
}

function normalizeVerificationStatus(raw) {
  if (VERIFICATION_STATUSES.has(raw.verification_status)) return raw.verification_status;
  if (raw.verified === true) return 'verified';
  if (raw.verified === false) return 'pending';
  return 'incomplete';
}

function normalizeMissingFields(value) {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.filter((item) => typeof item === 'string' && item.trim()).map((item) => item.trim()))];
}

function normalizeVerificationHistory(value) {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item) => item && typeof item === 'object' && !Array.isArray(item))
    .map((item) => ({
      checked_at: firstPresent(item.checked_at, item.checkedAt),
      status: firstPresent(item.status),
      method: firstPresent(item.method),
      note: firstPresent(item.note, item.message),
      http_status: Number.isFinite(Number(item.http_status)) ? Number(item.http_status) : null,
    }));
}

export function normalizeRecord(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new DataShapeError('竞赛记录必须是对象');
  }
  const id = firstPresent(raw.id);
  const record = {
    id: id === null ? '' : String(id),
    title: firstPresent(raw.title),
    organizer: firstPresent(raw.organizer, raw.host),
    category: firstPresent(raw.category),
    competition_level: firstPresent(raw.competition_level, raw.level, raw.competitionLevel),
    eligible_participants: firstPresent(raw.eligible_participants, raw.audience, raw.eligibleParticipants),
    team_size: normalizeTeamSize(raw),
    registration_start: firstPresent(raw.registration_start, raw.registrationStart),
    registration_deadline: firstPresent(raw.registration_deadline, raw.registration_end, raw.registrationEnd),
    event_start: firstPresent(raw.event_start, raw.eventStart),
    event_end: firstPresent(raw.event_end, raw.eventEnd),
    description: firstPresent(raw.description),
    requirements: firstPresent(raw.requirements, raw.work_requirements),
    official_notice_url: firstPresent(raw.official_notice_url, raw.officialNoticeUrl, raw.canonical_url, raw.original_url),
    registration_url: firstPresent(raw.registration_url, raw.registrationUrl, raw.signup_url),
    source_name: firstPresent(raw.source_name, raw.sourceName),
    source_url: firstPresent(raw.source_url, raw.sourceUrl),
    source_id: firstPresent(raw.source_id, raw.sourceId),
    source_type: firstPresent(raw.source_type, raw.sourceType),
    published_at: firstPresent(raw.published_at, raw.publishedAt),
    fetched_at: firstPresent(raw.fetched_at, raw.fetchedAt, raw.last_seen_at, raw.first_seen_at),
    last_verified_at: firstPresent(raw.last_verified_at, raw.lastVerifiedAt),
    verification_status: normalizeVerificationStatus(raw),
    registration_status: REGISTRATION_STATUSES.has(raw.registration_status)
      ? raw.registration_status
      : 'unknown',
    confidence: firstPresent(raw.confidence),
    content_hash: firstPresent(raw.content_hash, raw.contentHash),
    region: firstPresent(raw.region),
    is_demo: raw.is_demo === true || raw.demo === true,
    missing_fields: normalizeMissingFields(raw.missing_fields),
    verification_notes: firstPresent(
      raw.verification_notes,
      raw.verification_note,
      raw.verificationNotes,
    ),
    verification_history: normalizeVerificationHistory(raw.verification_history),
  };
  return record;
}

export function normalizeCompetitionsPayload(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new DataShapeError('competitions.json 顶层必须是对象');
  }
  if (!Array.isArray(raw.records)) {
    throw new DataShapeError('competitions.json 缺少 records 数组');
  }
  const records = raw.records
    .filter((record) => record !== null && record !== undefined)
    .map(normalizeRecord);
  return {
    schema_version: firstPresent(raw.schema_version),
    data_mode: raw.data_mode === 'demo' ? 'demo' : raw.data_mode === 'live' ? 'live' : null,
    generated_at: firstPresent(raw.generated_at),
    notice: firstPresent(raw.notice),
    record_count: Number.isFinite(Number(raw.record_count)) ? Number(raw.record_count) : records.length,
    records,
  };
}

export function normalizeSource(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new DataShapeError('信息源记录必须是对象');
  }
  const enabled = raw.enabled === undefined ? null : raw.enabled === true;
  let manual = raw.needs_manual_verification;
  if (manual === undefined || manual === null) {
    manual = raw.verified === false && enabled === true;
  }
  return {
    id: firstPresent(raw.id) === null ? '' : String(raw.id),
    name: firstPresent(raw.name),
    source_type: firstPresent(raw.source_type, raw.parser),
    domain: firstPresent(raw.domain),
    list_url: firstPresent(raw.list_url),
    enabled,
    update_frequency: firstPresent(raw.update_frequency),
    last_checked_at: firstPresent(raw.last_checked_at),
    last_success_at: firstPresent(raw.last_success_at),
    status: firstPresent(raw.status),
    status_label: firstPresent(raw.status_label),
    result: firstPresent(raw.result),
    failure_reason: firstPresent(raw.failure_reason, raw.last_error),
    records_found: Number.isFinite(Number(raw.records_found)) ? Number(raw.records_found) : null,
    records_added: Number.isFinite(Number(raw.records_added ?? raw.records_new))
      ? Number(raw.records_added ?? raw.records_new)
      : null,
    needs_manual_verification: manual ?? null,
    verified: typeof raw.verified === 'boolean' ? raw.verified : null,
    is_demo: raw.is_demo === true || raw.demo === true,
  };
}

export function normalizeSourcesPayload(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new DataShapeError('sources.json 顶层必须是对象');
  }
  const sources = raw.sources;
  if (!Array.isArray(sources)) throw new DataShapeError('sources.json 缺少 sources 数组');
  return {
    schema_version: firstPresent(raw.schema_version),
    data_mode: raw.data_mode === 'demo' ? 'demo' : raw.data_mode === 'live' ? 'live' : null,
    generated_at: firstPresent(raw.generated_at),
    notice: firstPresent(raw.notice),
    sources: sources.map(normalizeSource),
  };
}

function numericOrNull(value) {
  return Number.isFinite(Number(value)) ? Number(value) : null;
}

export function normalizeMetaPayload(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new DataShapeError('meta.json 顶层必须是对象');
  }
  const summaryRaw = raw.summary && typeof raw.summary === 'object' ? raw.summary : {};
  const checked = numericOrNull(raw.checked_source_count);
  const failed = numericOrNull(raw.failed_source_count);
  const derivedSuccess = checked !== null && failed !== null
    ? Math.max(0, checked - failed)
    : null;
  const summary = {
    source_count: numericOrNull(summaryRaw.source_count ?? raw.enabled_source_count ?? raw.source_count),
    success_count: numericOrNull(summaryRaw.success_count ?? derivedSuccess),
    failure_count: numericOrNull(summaryRaw.failure_count ?? raw.failed_source_count),
    record_count: numericOrNull(summaryRaw.record_count ?? raw.record_count),
    pending_verification_count: numericOrNull(
      summaryRaw.pending_verification_count ?? raw.pending_verification_count,
    ),
  };
  const lastRunRaw = raw.last_run && typeof raw.last_run === 'object' ? raw.last_run : {};
  const lastRun = {
    started_at: firstPresent(lastRunRaw.started_at),
    finished_at: firstPresent(lastRunRaw.finished_at, raw.generated_at),
    status: firstPresent(lastRunRaw.status, raw.collection_status),
    message: firstPresent(lastRunRaw.message, raw.disclaimer),
  };
  return {
    ...raw,
    schema_version: firstPresent(raw.schema_version),
    data_mode: raw.data_mode === 'demo' ? 'demo' : raw.data_mode === 'live' ? 'live' : null,
    generated_at: firstPresent(raw.generated_at),
    notice: firstPresent(raw.notice, raw.disclaimer),
    last_run: lastRun,
    summary,
    run_history: Array.isArray(raw.run_history) ? raw.run_history : [],
  };
}

export function getDataMode(competitions, meta) {
  const explicit = competitions?.data_mode ?? meta?.data_mode;
  if (explicit === 'demo' || explicit === 'live') return explicit;
  if (competitions?.records?.some((record) => record.is_demo === true)) return 'demo';
  return 'unknown';
}

export function hasDemoRecords(competitions) {
  return competitions?.records?.some((record) => record.is_demo === true) ?? false;
}

export function verificationStatusMeta(status) {
  const map = {
    verified: { label: '已核验', tone: 'success' },
    pending: { label: '待核验', tone: 'warning' },
    broken: { label: '链接失效', tone: 'danger' },
    expired: { label: '已过期', tone: 'muted' },
    incomplete: { label: '信息不全', tone: 'warning' },
  };
  return map[status] ?? { label: '待确认', tone: 'muted' };
}

export { REQUIRED_RECORD_FIELDS };