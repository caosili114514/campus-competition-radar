const MS_PER_DAY = 86_400_000;
const DATE_ONLY_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

export function toValidDate(value) {
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : new Date(value.getTime());
  }
  if (typeof value === 'number') {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
  }
  return parseDateValue(value, 'start');
}

export function parseDateValue(value, boundary = 'start') {
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : new Date(value.getTime());
  }
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return null;
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
  }
  if (typeof value !== 'string') return null;

  const text = value.trim();
  if (!text) return null;

  const dateOnly = DATE_ONLY_RE.exec(text);
  if (dateOnly) {
    const year = Number(dateOnly[1]);
    const month = Number(dateOnly[2]) - 1;
    const day = Number(dateOnly[3]);
    const date = boundary === 'end'
      ? new Date(year, month, day, 23, 59, 59, 999)
      : new Date(year, month, day, 0, 0, 0, 0);
    if (
      date.getFullYear() !== year
      || date.getMonth() !== month
      || date.getDate() !== day
    ) {
      return null;
    }
    return date;
  }

  const date = new Date(text);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function getRegistrationStart(record) {
  if (!record || typeof record !== 'object') return null;
  return parseDateValue(record.registration_start, 'start');
}

export function getRegistrationDeadline(record) {
  if (!record || typeof record !== 'object') return null;
  return parseDateValue(record.registration_deadline, 'end');
}

export function deriveRegistrationStatus(record, now = new Date()) {
  const clock = toValidDate(now) ?? new Date();
  const start = getRegistrationStart(record);
  const deadline = getRegistrationDeadline(record);

  if (!start && !deadline) return 'unknown';
  if (deadline && clock.getTime() > deadline.getTime()) return 'closed';
  if (start && clock.getTime() < start.getTime()) return 'upcoming';
  if (deadline || start) return 'open';
  return 'unknown';
}

export function registrationStatusMeta(status) {
  const normalized = String(status ?? 'unknown').toLowerCase();
  const map = {
    open: { key: 'open', label: '报名中', tone: 'success' },
    upcoming: { key: 'upcoming', label: '即将开始', tone: 'info' },
    closed: { key: 'closed', label: '已截止', tone: 'danger' },
    unknown: { key: 'unknown', label: '待确认', tone: 'muted' },
  };
  return map[normalized] ?? map.unknown;
}

export function getRegistrationDisplay(record, now = new Date()) {
  const derivedStatus = deriveRegistrationStatus(record, now);
  const verificationStatus = String(record?.verification_status ?? '').toLowerCase();
  const isVerified = verificationStatus === 'verified';
  const common = { derivedStatus, verificationStatus, confirmedOpen: false };

  if (derivedStatus === 'closed') {
    return { ...common, key: 'closed', label: '已截止', tone: 'danger' };
  }

  if (verificationStatus === 'broken') {
    return { ...common, key: 'broken', label: '链接异常', tone: 'danger' };
  }

  if (derivedStatus === 'open') {
    if (isVerified) {
      return {
        ...common,
        key: 'open',
        label: '报名中（已核验）',
        tone: 'success',
        confirmedOpen: true,
      };
    }
    return {
      ...common,
      key: 'pending_window',
      label: '报名窗口内（待核验）',
      tone: 'warning',
    };
  }

  if (derivedStatus === 'upcoming') {
    if (isVerified) {
      return { ...common, key: 'upcoming', label: '即将开始', tone: 'info' };
    }
    return {
      ...common,
      key: 'pending_upcoming',
      label: '即将开始（待核验）',
      tone: 'warning',
    };
  }

  if (derivedStatus === 'unknown') {
    if (isVerified) {
      return { ...common, key: 'unknown', label: '待确认', tone: 'muted' };
    }
    return { ...common, key: 'pending_unknown', label: '待核验', tone: 'warning' };
  }

  const fallback = registrationStatusMeta(derivedStatus);
  return {
    ...common,
    ...fallback,
    confirmedOpen: false,
  };
}
export function calendarDayDifference(later, earlier) {
  return Math.round(
    (Date.UTC(later.getFullYear(), later.getMonth(), later.getDate())
      - Date.UTC(earlier.getFullYear(), earlier.getMonth(), earlier.getDate()))
    / MS_PER_DAY,
  );
}

export function getDeadlineInfo(record, now = new Date()) {
  const clock = toValidDate(now) ?? new Date();
  const deadline = getRegistrationDeadline(record);
  if (!deadline) {
    return { deadline: null, days: null, label: '待确认', expired: false };
  }

  const expired = clock.getTime() > deadline.getTime();
  const days = calendarDayDifference(deadline, clock);
  let label;
  if (expired) label = '已截止';
  else if (days === 0) label = '今天截止';
  else if (days === 1) label = '明天截止';
  else if (days > 1) label = `剩 ${days} 天`;

  return { deadline, days, label: label ?? '今天截止', expired };
}

export function getDeadlineTimestamp(record) {
  return getRegistrationDeadline(record)?.getTime() ?? null;
}

export function formatDate(value, fallback = '待确认') {
  const date = parseDateValue(value, 'start');
  if (!date) return fallback;
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function formatDateTime(value, fallback = '待确认') {
  const date = parseDateValue(value, 'start');
  if (!date) return fallback;
  if (typeof value === 'string' && DATE_ONLY_RE.test(value.trim())) {
    return formatDate(value, fallback);
  }
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  return `${formatDate(value, fallback)} ${hours}:${minutes}`;
}

export function formatDateRange(startValue, endValue, fallback = '待确认') {
  const start = parseDateValue(startValue, 'start');
  const end = parseDateValue(endValue, 'start');
  if (!start && !end) return fallback;
  if (!start) return `待确认 – ${formatDate(endValue, fallback)}`;
  if (!end) return `${formatDate(startValue, fallback)} – 待确认`;
  if (formatDate(startValue) === formatDate(endValue)) return formatDate(startValue, fallback);
  return `${formatDate(startValue, fallback)} – ${formatDate(endValue, fallback)}`;
}

export function formatDuration(startValue, endValue, fallback = '待确认') {
  const start = parseDateValue(startValue, 'start');
  const end = parseDateValue(endValue, 'start');
  if (!start || !end || end.getTime() < start.getTime()) return fallback;
  const totalMinutes = Math.round((end.getTime() - start.getTime()) / 60_000);
  if (totalMinutes < 1) return '不足 1 分钟';
  if (totalMinutes < 60) return `${totalMinutes} 分钟`;
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return minutes ? `${hours} 小时 ${minutes} 分钟` : `${hours} 小时`;
}

export function sortByDeadline(records, direction = 'asc') {
  const sign = direction === 'desc' ? -1 : 1;
  return [...records].sort((left, right) => {
    const leftTime = getDeadlineTimestamp(left);
    const rightTime = getDeadlineTimestamp(right);
    if (leftTime === null && rightTime === null) return 0;
    if (leftTime === null) return 1;
    if (rightTime === null) return -1;
    if (leftTime === rightTime) {
      return String(left.title ?? '').localeCompare(String(right.title ?? ''), 'zh-CN');
    }
    return (leftTime - rightTime) * sign;
  });
}