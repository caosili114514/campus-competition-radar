import {
  normalizeCompetitionsPayload,
  normalizeMetaPayload,
  normalizeSourcesPayload,
} from './normalize.js';

export const DATA_FILES = Object.freeze({
  competitions: 'docs/data/competitions.json',
  sources: 'docs/data/sources.json',
  meta: 'docs/data/meta.json',
});

export class DataLoadError extends Error {
  constructor(message, { path = '', status = null, cause = null } = {}) {
    super(message);
    this.name = 'DataLoadError';
    this.path = path;
    this.status = status;
    this.cause = cause;
  }
}

function defaultBaseUri() {
  if (typeof document !== 'undefined' && document.baseURI) return document.baseURI;
  if (typeof location !== 'undefined' && location.href) return location.href;
  return 'http://localhost:4173/';
}

export function resolveDataUrl(relativePath, baseURI = defaultBaseUri()) {
  return new URL(relativePath, baseURI).href;
}

export async function fetchJson(relativePath, options = {}) {
  const fetchImpl = options.fetchImpl ?? globalThis.fetch;
  const baseURI = options.baseURI ?? defaultBaseUri();
  if (typeof fetchImpl !== 'function') {
    throw new DataLoadError(`当前环境不支持 fetch，无法读取 ${relativePath}`, { path: relativePath });
  }

  const url = resolveDataUrl(relativePath, baseURI);
  let response;
  try {
    response = await fetchImpl(url, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    });
  } catch (error) {
    throw new DataLoadError(
      `无法获取 ${relativePath}。请确认已通过本地静态服务器打开，并检查文件是否存在。`,
      { path: relativePath, cause: error },
    );
  }

  if (!response || !response.ok) {
    throw new DataLoadError(
      `读取 ${relativePath} 失败：HTTP ${response?.status ?? '未知状态'}`,
      { path: relativePath, status: response?.status ?? null },
    );
  }

  try {
    return await response.json();
  } catch (error) {
    throw new DataLoadError(
      `${relativePath} 不是有效的 JSON 文件。`,
      { path: relativePath, cause: error },
    );
  }
}

export async function loadSiteData(options = {}) {
  const tasks = [
    {
      key: 'competitions',
      path: DATA_FILES.competitions,
      normalize: normalizeCompetitionsPayload,
    },
    {
      key: 'sources',
      path: DATA_FILES.sources,
      normalize: normalizeSourcesPayload,
    },
    {
      key: 'meta',
      path: DATA_FILES.meta,
      normalize: normalizeMetaPayload,
    },
  ];

  const results = await Promise.allSettled(
    tasks.map(async (task) => {
      const payload = await fetchJson(task.path, options);
      return task.normalize(payload);
    }),
  );

  const values = { competitions: null, sources: null, meta: null };
  const errors = [];
  results.forEach((result, index) => {
    const task = tasks[index];
    if (result.status === 'fulfilled') {
      values[task.key] = result.value;
      return;
    }
    const reason = result.reason;
    errors.push({
      key: task.key,
      path: task.path,
      message: reason instanceof Error ? reason.message : String(reason),
      status: reason?.status ?? null,
    });
  });

  return { ...values, errors };
}