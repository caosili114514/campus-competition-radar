import test from 'node:test';
import assert from 'node:assert/strict';

import {
  STORAGE_KEY,
  createDefaultUserData,
  createUserStore,
  getProgressLabel,
  getTrackedItems,
  isFavorite,
  loadUserData,
  saveUserData,
  PROGRESS_OPTIONS,
} from '../../assets/js/storage.js';

class MemoryStorage {
  constructor(initial = {}) {
    this.map = new Map(Object.entries(initial));
  }

  getItem(key) {
    return this.map.has(key) ? this.map.get(key) : null;
  }

  setItem(key, value) {
    this.map.set(key, String(value));
  }

  removeItem(key) {
    this.map.delete(key);
  }
}

function memoryStorage(initial = {}) {
  return new MemoryStorage(initial);
}

test('favorites persist through localStorage and survive a fresh store instance', () => {
  const storage = memoryStorage();
  const firstStore = createUserStore(storage);
  const result = firstStore.toggleFavorite('demo-001', new Date('2026-10-24T12:00:00Z'));

  assert.equal(result.saved, true);
  assert.equal(result.favorite, true);
  assert.equal(isFavorite(result.data, 'demo-001'), true);
  assert.ok(storage.getItem(STORAGE_KEY));

  const secondStore = createUserStore(storage);
  const loaded = secondStore.read();
  assert.equal(isFavorite(loaded, 'demo-001'), true);
  assert.deepEqual(getTrackedItems(loaded).map((entry) => entry.id), ['demo-001']);
});

test('progress and notes persist locally and remain after unfavoriting', () => {
  const storage = memoryStorage();
  const store = createUserStore(storage);
  store.toggleFavorite('contest-a', new Date('2026-10-24T10:00:00Z'));
  const progressResult = store.setProgress('contest-a', 'preparing', new Date('2026-10-24T11:00:00Z'));
  const noteResult = store.setNote('contest-a', '准备项目计划书与路演视频。', new Date('2026-10-24T12:00:00Z'));
  assert.equal(progressResult.saved, true);
  assert.equal(noteResult.saved, true);

  const unfavoriteResult = store.toggleFavorite('contest-a', new Date('2026-10-24T13:00:00Z'));
  assert.equal(unfavoriteResult.favorite, false);
  assert.ok(unfavoriteResult.entry, 'progress and note must keep the entry tracked');

  const reloaded = createUserStore(storage).read();
  const entry = reloaded.competitions['contest-a'];
  assert.equal(entry.favorite, false);
  assert.equal(entry.progress, 'preparing');
  assert.equal(entry.note, '准备项目计划书与路演视频。');
  assert.equal(getProgressLabel(entry.progress), '准备中');
});

test('an entry with no favorite, progress or note is removed cleanly', () => {
  const storage = memoryStorage();
  const store = createUserStore(storage);
  store.setNote('contest-b', '临时备注', new Date('2026-10-24T10:00:00Z'));
  assert.deepEqual(getTrackedItems(store.read()).map((entry) => entry.id), ['contest-b']);
  const cleared = store.setNote('contest-b', '', new Date('2026-10-24T11:00:00Z'));
  assert.equal(cleared.entry, null);
  assert.deepEqual(getTrackedItems(cleared.data), []);
});

test('malformed storage JSON falls back to an empty valid model without throwing', () => {
  const storage = memoryStorage({ [STORAGE_KEY]: '{broken json' });
  assert.deepEqual(loadUserData(storage), createDefaultUserData());
  assert.doesNotThrow(() => createUserStore(storage).read());
});

test('storage writes report failure instead of throwing when quota is exceeded', () => {
  const storage = memoryStorage();
  storage.setItem = () => {
    throw new Error('QuotaExceededError');
  };
  const store = createUserStore(storage);
  const result = store.toggleFavorite('quota-test');
  assert.equal(result.saved, false);
  assert.equal(result.favorite, true);
  assert.equal(isFavorite(result.data, 'quota-test'), true);
});

test('saveUserData sanitizes unknown progress and dangerous object keys', () => {
  const storage = memoryStorage();
  const saved = saveUserData(storage, {
    version: 1,
    competitions: {
      '__proto__': { favorite: true, progress: 'registered', note: '', updatedAt: null },
      safe: { favorite: true, progress: 'not-a-real-progress', note: '保留我', updatedAt: null },
    },
  });
  assert.equal(saved, true);
  const loaded = loadUserData(storage);
  assert.equal(Object.hasOwn(loaded.competitions, '__proto__'), false);
  assert.equal(loaded.competitions.safe.progress, 'none');
  assert.equal(loaded.competitions.safe.note, '保留我');
});

test('required application progress states are available and persist', () => {
  const required = ['preparing', 'registered', 'submitted', 'ended'];
  const labels = new Map(PROGRESS_OPTIONS.map((option) => [option.value, option.label]));
  for (const value of required) assert.equal(labels.has(value), true);
  assert.equal(labels.get('ended'), '已结束');
  const storage = memoryStorage();
  const store = createUserStore(storage);
  for (const value of required) {
    const result = store.setProgress('demo-001', value, new Date('2026-10-24T12:00:00Z'));
    assert.equal(result.entry?.progress, value);
    assert.equal(createUserStore(storage).read().competitions['demo-001'].progress, value);
  }
});
