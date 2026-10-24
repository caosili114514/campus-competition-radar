export const PENDING = '待确认';

export function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function isMissing(value) {
  return value === null
    || value === undefined
    || (typeof value === 'string' && value.trim() === '')
    || (Array.isArray(value) && value.length === 0);
}

export function displayText(value, fallback = PENDING) {
  if (isMissing(value)) return fallback;
  if (Array.isArray(value)) {
    const items = value
      .map((item) => displayText(item, ''))
      .filter((item) => item !== '');
    return items.length ? items.join('、') : fallback;
  }
  if (typeof value === 'boolean') return value ? '是' : '否';
  if (typeof value === 'object') return fallback;
  return String(value);
}

export function formatCount(value, fallback = PENDING) {
  if (isMissing(value)) return fallback;
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return displayText(value, fallback);
  return new Intl.NumberFormat('zh-CN').format(numeric);
}

export function formatTeamSize(value, fallback = PENDING) {
  if (isMissing(value)) return fallback;
  if (typeof value === 'number' && Number.isFinite(value)) return `${value} 人`;
  if (typeof value === 'object' && !Array.isArray(value)) {
    const min = value.min ?? value.minimum ?? value.team_size_min;
    const max = value.max ?? value.maximum ?? value.team_size_max;
    if (min !== null && min !== undefined && max !== null && max !== undefined) {
      return min === max ? `${min} 人` : `${min}–${max} 人`;
    }
    if (min !== null && min !== undefined) return `${min} 人以上`;
    if (max !== null && max !== undefined) return `不超过 ${max} 人`;
  }
  if (Array.isArray(value)) return displayText(value, fallback);
  return displayText(value, fallback);
}

export function formatConfidence(value, fallback = PENDING) {
  if (isMissing(value)) return fallback;
  const numeric = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(numeric)) return displayText(value, fallback);
  const percent = numeric >= 0 && numeric <= 1 ? numeric * 100 : numeric;
  if (percent < 0 || percent > 100) return displayText(value, fallback);
  return `${Math.round(percent)}%`;
}

export function safeExternalUrl(value) {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (/^https?:\/\//i.test(trimmed)) {
    try {
      const parsed = new URL(trimmed);
      return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : null;
    } catch {
      return null;
    }
  }
  if (trimmed.startsWith('/') || trimmed.startsWith('./') || trimmed.startsWith('../')) {
    return trimmed;
  }
  return null;
}

export function formatHash(value, visible = 16) {
  const text = displayText(value, '');
  if (!text) return PENDING;
  if (text.length <= visible) return text;
  return `${text.slice(0, visible)}…`;
}