export const STORAGE_KEY = 'campus-competition-radar.user.v1';

export const PROGRESS_OPTIONS = Object.freeze([
  { value: 'none', label: '未设置' },
  { value: 'interested', label: '关注中' },
  { value: 'preparing', label: '准备中' },
  { value: 'registered', label: '已报名' },
  { value: 'submitted', label: '已提交' },
  { value: 'completed', label: '已完成' },
  { value: 'ended', label: '已结束' },
]);

const VALID_PROGRESS = new Set(PROGRESS_OPTIONS.map((option) => option.value));
const UNSAFE_KEYS = new Set(['__proto__', 'constructor', 'prototype']);
const MAX_NOTE_LENGTH = 4000;

export function createDefaultUserData() {
  return { version: 1, competitions: {} };
}

function normalizeEntryId(id) {
  if (id === null || id === undefined) return '';
  const value = String(id).trim();
  return UNSAFE_KEYS.has(value) ? '' : value;
}

function normalizeEntry(entry) {
  if (!entry || typeof entry !== 'object' || Array.isArray(entry)) return null;
  const progress = VALID_PROGRESS.has(entry.progress) ? entry.progress : 'none';
  const note = typeof entry.note === 'string' ? entry.note.slice(0, MAX_NOTE_LENGTH) : '';
  const result = {
    favorite: entry.favorite === true,
    progress,
    note,
    updatedAt: typeof entry.updatedAt === 'string' ? entry.updatedAt : null,
  };
  return result.favorite || result.progress !== 'none' || result.note.trim()
    ? result
    : null;
}

export function sanitizeUserData(raw) {
  const cleaned = createDefaultUserData();
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return cleaned;
  const source = raw.competitions && typeof raw.competitions === 'object'
    ? raw.competitions
    : raw.items && typeof raw.items === 'object'
      ? raw.items
      : {};
  for (const [rawId, rawEntry] of Object.entries(source)) {
    const id = normalizeEntryId(rawId);
    if (!id) continue;
    const entry = normalizeEntry(rawEntry);
    if (entry) cleaned.competitions[id] = entry;
  }
  return cleaned;
}

function cloneData(data) {
  return {
    version: 1,
    competitions: Object.fromEntries(
      Object.entries(data.competitions ?? {}).map(([id, entry]) => [id, { ...entry }]),
    ),
  };
}

export function loadUserData(storage, key = STORAGE_KEY) {
  if (!storage || typeof storage.getItem !== 'function') return createDefaultUserData();
  try {
    const raw = storage.getItem(key);
    if (!raw) return createDefaultUserData();
    return sanitizeUserData(JSON.parse(raw));
  } catch {
    return createDefaultUserData();
  }
}

export function saveUserData(storage, data, key = STORAGE_KEY) {
  if (!storage || typeof storage.setItem !== 'function') return false;
  try {
    storage.setItem(key, JSON.stringify(sanitizeUserData(data)));
    return true;
  } catch {
    return false;
  }
}

export function getEntry(userData, id) {
  const key = normalizeEntryId(id);
  if (!key) return null;
  const entry = userData?.competitions?.[key];
  return entry ? { ...entry } : null;
}

export function isFavorite(userData, id) {
  return getEntry(userData, id)?.favorite === true;
}

export function getProgressLabel(value) {
  return PROGRESS_OPTIONS.find((option) => option.value === value)?.label ?? '未设置';
}

export function getTrackedItems(userData) {
  const entries = userData?.competitions && typeof userData.competitions === 'object'
    ? Object.entries(userData.competitions)
    : [];
  return entries
    .map(([id, rawEntry]) => {
      const entry = normalizeEntry(rawEntry);
      return entry ? { id: normalizeEntryId(id), ...entry } : null;
    })
    .filter((entry) => entry && entry.id)
    .sort((left, right) => {
      const leftTime = Date.parse(left.updatedAt ?? '');
      const rightTime = Date.parse(right.updatedAt ?? '');
      if (Number.isFinite(leftTime) && Number.isFinite(rightTime) && leftTime !== rightTime) {
        return rightTime - leftTime;
      }
      if (Number.isFinite(leftTime) && !Number.isFinite(rightTime)) return -1;
      if (!Number.isFinite(leftTime) && Number.isFinite(rightTime)) return 1;
      return left.id.localeCompare(right.id, 'zh-CN');
    });
}

function toIsoString(value) {
  const date = value instanceof Date ? value : new Date(value ?? Date.now());
  return Number.isNaN(date.getTime()) ? new Date().toISOString() : date.toISOString();
}

function meaningful(entry) {
  return entry.favorite || entry.progress !== 'none' || entry.note.trim() !== '';
}

export function createUserStore(storage, { key = STORAGE_KEY } = {}) {
  let fallbackMode = !storage
    || typeof storage.getItem !== 'function'
    || typeof storage.setItem !== 'function';
  let fallbackData = null;

  function read() {
    if (fallbackMode) return cloneData(fallbackData ?? createDefaultUserData());
    try {
      const raw = storage.getItem(key);
      const parsed = raw ? sanitizeUserData(JSON.parse(raw)) : createDefaultUserData();
      fallbackData = parsed;
      return cloneData(parsed);
    } catch {
      fallbackMode = true;
      return cloneData(fallbackData ?? createDefaultUserData());
    }
  }

  function write(data) {
    const sanitized = sanitizeUserData(data);
    fallbackData = sanitized;
    if (fallbackMode) return false;
    try {
      storage.setItem(key, JSON.stringify(sanitized));
      return true;
    } catch {
      fallbackMode = true;
      return false;
    }
  }

  function updateEntry(id, updater, now = new Date()) {
    const entryId = normalizeEntryId(id);
    const data = read();
    if (!entryId) return { data, entry: null, saved: false };

    const current = normalizeEntry(data.competitions[entryId]) ?? {
      favorite: false,
      progress: 'none',
      note: '',
      updatedAt: null,
    };
    const next = updater({ ...current });
    const result = normalizeEntry({ ...next, updatedAt: toIsoString(now) });
    if (result) data.competitions[entryId] = result;
    else delete data.competitions[entryId];

    const saved = write(data);
    return {
      data: cloneData(data),
      entry: result ? { id: entryId, ...result } : null,
      saved,
    };
  }

  return {
    key,
    read,
    toggleFavorite(id, now = new Date()) {
      const result = updateEntry(id, (entry) => ({ ...entry, favorite: !entry.favorite }), now);
      return {
        ...result,
        favorite: result.entry?.favorite === true,
      };
    },
    setProgress(id, progress, now = new Date()) {
      const nextProgress = VALID_PROGRESS.has(progress) ? progress : 'none';
      return updateEntry(id, (entry) => ({ ...entry, progress: nextProgress }), now);
    },
    setNote(id, note, now = new Date()) {
      const safeNote = typeof note === 'string' ? note.slice(0, MAX_NOTE_LENGTH) : '';
      return updateEntry(id, (entry) => ({ ...entry, note: safeNote }), now);
    },
    removeEntry(id) {
      const entryId = normalizeEntryId(id);
      const data = read();
      if (!entryId || !Object.hasOwn(data.competitions, entryId)) {
        return { data: cloneData(data), removed: false, saved: true };
      }
      delete data.competitions[entryId];
      const saved = write(data);
      return { data: cloneData(data), removed: true, saved };
    },
  };
}