import { loadSiteData } from './data.js';
import {
  DEFAULT_FILTERS,
  SORT_OPTIONS,
  countActiveFilters,
  filtersFromSearchParams,
  filtersToSearchParams,
} from './filters.js';
import {
  STORAGE_KEY,
  createUserStore,
  getProgressLabel,
  getTrackedItems,
  isFavorite,
} from './storage.js';
import { activeNavKey, parseRoute, routeTitle } from './router.js';
import { formatDateTime } from './dates.js';
import { getDataMode, hasDemoRecords } from './normalize.js';
import * as views from './views.js';

const state = {
  competitions: null,
  sources: null,
  meta: null,
  errors: [],
  route: parseRoute(''),
  filters: { ...DEFAULT_FILTERS },
  now: new Date(),
  dataMode: 'unknown',
  userData: null,
  userStore: null,
  storageAvailable: false,
  isLoading: false,
};

let elements = {};
let noteSaveTimer = null;
let queryFilterTimer = null;
let toastTimer = null;
let lastFocusBeforeNav = null;

function ensureRouteHash() {
  if (window.location.hash && window.location.hash !== '#' && window.location.hash !== '#/') return;
  try {
    window.history.replaceState(null, '', '#/dashboard');
  } catch {
    window.location.hash = '#/dashboard';
  }
}

function probeLocalStorage() {
  try {
    const key = '__campus_radar_storage_probe__';
    window.localStorage.setItem(key, '1');
    window.localStorage.removeItem(key);
    return window.localStorage;
  } catch {
    return null;
  }
}

function initUserStore() {
  const storage = probeLocalStorage();
  state.storageAvailable = Boolean(storage);
  state.userStore = createUserStore(storage);
  state.userData = state.userStore.read();
}

function syncFiltersFromRoute(route) {
  if (route?.name === 'competitions') {
    state.filters = filtersFromSearchParams(route.query);
  }
}

function buildDiscoveryHash(filters) {
  const params = filtersToSearchParams(filters);
  const query = params.toString();
  return `#/competitions${query ? `?${query}` : ''}`;
}

function currentContext() {
  return {
    competitions: state.competitions,
    sources: state.sources,
    meta: state.meta,
    errors: state.errors,
    route: state.route,
    filters: state.filters,
    now: state.now,
    dataMode: state.dataMode,
    userData: state.userData,
    storageAvailable: state.storageAvailable,
    discoveryHref: buildDiscoveryHash(state.filters),
  };
}

function modeLabel(mode) {
  if (mode === 'demo') return '演示数据';
  if (mode === 'live') return '公开采集数据';
  return '数据模式待确认';
}

function applyGlobalMode() {
  const mode = getDataMode(state.competitions, state.meta);
  state.dataMode = mode;
  const containsDemo = mode === 'demo' || hasDemoRecords(state.competitions);
  const showBanner = Boolean(state.competitions) && containsDemo;

  document.body.classList.toggle('demo-mode', showBanner);
  elements.demoBanner.hidden = !showBanner;
  if (showBanner) {
    const bannerText = mode === 'demo'
      ? '当前为演示数据模式，所有内容仅用于产品展示，不代表真实赛事或报名信息。'
      : '当前数据中包含演示记录，相关条目均带演示徽标，不代表真实赛事。';
    const textNode = elements.demoBanner.querySelector('[data-demo-banner-text]');
    if (textNode) textNode.textContent = bannerText;
  }

  if (!state.competitions) {
    elements.dataModeChip.hidden = true;
    elements.topbarStatusText.textContent = '数据加载失败';
    elements.sidebarDataStatus.textContent = '数据未加载';
    return;
  }

  elements.dataModeChip.hidden = false;
  elements.dataModeChip.textContent = mode === 'live' && hasDemoRecords(state.competitions)
    ? '公开采集数据 · 含演示'
    : modeLabel(mode);
  elements.dataModeChip.className = `mode-chip mode-chip-${mode === 'unknown' ? 'unknown' : mode}${mode === 'live' && hasDemoRecords(state.competitions) ? ' mode-chip-mixed' : ''}`;

  const generated = formatDateTime(state.competitions.generated_at, '时间待确认');
  elements.topbarStatusText.textContent = state.errors.length
    ? `更新：${generated} · 部分数据缺失`
    : `更新：${generated}`;
  const records = Array.isArray(state.competitions.records) ? state.competitions.records.length : 0;
  elements.sidebarDataStatus.textContent = `${modeLabel(mode)} · ${records} 条竞赛记录`;
}

function updateNavigation() {
  const activeKey = activeNavKey(state.route);
  document.querySelectorAll('.nav-link[data-nav]').forEach((link) => {
    const active = link.dataset.nav === activeKey;
    link.classList.toggle('is-active', active);
    if (active) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });

  const competitionCount = Array.isArray(state.competitions?.records) ? state.competitions.records.length : null;
  const trackedCount = getTrackedItems(state.userData).length;
  document.querySelectorAll('[data-nav-count]').forEach((badge) => {
    const kind = badge.dataset.navCount;
    const value = kind === 'competitions' ? competitionCount : kind === 'my' ? trackedCount : null;
    const show = Number.isFinite(value) && value > 0;
    badge.hidden = !show;
    badge.textContent = show ? String(value) : '';
  });
}

function updateTopSearchValue() {
  if (!elements.globalSearchInput) return;
  elements.globalSearchInput.value = state.route.name === 'competitions'
    ? (state.filters.query ?? '')
    : '';
}

function updateMyStatsView() {
  const container = document.getElementById('my-stats');
  if (!container) return;
  state.now = new Date();
  container.innerHTML = views.renderMyStats(currentContext());
}

function updateDashboardFavoriteCount() {
  const value = document.getElementById('dashboard-favorite-count');
  if (!value) return;
  const favoriteCount = getTrackedItems(state.userData).filter((entry) => entry.favorite).length;
  value.textContent = new Intl.NumberFormat('zh-CN').format(favoriteCount);
}

function loadingMarkup() {
  return `<div class="loading-state" role="status" aria-live="polite">
    <span class="loading-icon" aria-hidden="true">
      <svg viewBox="0 0 48 48" width="44" height="44" fill="none" focusable="false"><circle cx="24" cy="24" r="19" stroke="currentColor" stroke-width="2" opacity=".25"/><circle cx="24" cy="24" r="11" stroke="currentColor" stroke-width="2" opacity=".55"/><circle cx="24" cy="24" r="3.5" fill="currentColor"/><path d="M24 5v6M43 24h-6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
    </span>
    <p>正在读取竞赛情报数据…</p>
    <p class="loading-hint">数据通过相对路径从 docs/data/ 加载。</p>
  </div>`;
}

function renderCurrentView({ focus = false, announce = true } = {}) {
  if (state.isLoading) return;
  state.now = new Date();
  applyGlobalMode();
  updateNavigation();
  updateTopSearchValue();

  let html = '';
  if (!state.competitions) {
    html = views.renderDataError(currentContext());
  } else {
    const ctx = currentContext();
    switch (state.route.name) {
      case 'dashboard':
        html = views.renderDashboard(ctx);
        break;
      case 'competitions':
        html = views.renderCompetitions(ctx);
        break;
      case 'competition':
        html = views.renderCompetitionDetail(ctx);
        break;
      case 'my':
        html = views.renderMy(ctx);
        break;
      case 'sources':
        html = views.renderSources(ctx);
        break;
      case 'about':
        html = views.renderAbout(ctx);
        break;
      default:
        html = views.renderNotFound(ctx);
        break;
    }
  }

  elements.main.innerHTML = html;
  document.title = `${routeTitle(state.route)} · 赛讯雷达`;
  if (announce) {
    elements.routeAnnouncer.textContent = `${routeTitle(state.route)}页面已加载`;
  }
  if (focus) {
    elements.main.focus({ preventScroll: true });
    window.scrollTo({ top: 0, behavior: 'auto' });
  }
}

async function loadDataAndRender({ focus = false, announce = true, retry = false } = {}) {
  if (state.isLoading) return;
  state.isLoading = true;
  elements.main.innerHTML = loadingMarkup();
  elements.topbarStatusText.textContent = '正在读取数据…';
  elements.dataModeChip.hidden = true;

  try {
    const result = await loadSiteData();
    state.competitions = result.competitions;
    state.sources = result.sources;
    state.meta = result.meta;
    state.errors = result.errors;
  } catch (error) {
    state.competitions = null;
    state.sources = null;
    state.meta = null;
    state.errors = [{
      key: 'competitions',
      path: 'docs/data/competitions.json',
      message: error instanceof Error ? error.message : String(error),
    }];
  }

  state.isLoading = false;
  if (!state.competitions) {
    state.dataMode = 'unknown';
  }
  renderCurrentView({ focus, announce });
}
function showToast(message, tone = 'info', duration = 4200) {
  if (!elements.toastRegion) return;
  window.clearTimeout(toastTimer);
  elements.toastRegion.textContent = message;
  elements.toastRegion.className = `toast-region is-visible toast-${tone}`;
  toastTimer = window.setTimeout(() => {
    elements.toastRegion.textContent = '';
    elements.toastRegion.className = 'toast-region';
  }, duration);
}

function setSaveStatus(id, message, tone = 'is-saved') {
  document.querySelectorAll('[data-save-status]').forEach((status) => {
    if (status.dataset.saveStatus !== String(id)) return;
    status.textContent = message;
    status.className = `save-status ${tone}`;
  });
}

function markStorageUnavailable(message = '浏览器本地存储写入失败，修改只在当前页面会话内有效。') {
  state.storageAvailable = false;
  showToast(message, 'error', 6000);
}

function getRecordById(id) {
  const records = Array.isArray(state.competitions?.records) ? state.competitions.records : [];
  return records.find((record) => String(record.id) === String(id)) ?? null;
}

function updateFavoriteButtons(id) {
  const pressed = isFavorite(state.userData, id);
  const record = getRecordById(id);
  const title = record?.title ? String(record.title) : '待确认';
  document.querySelectorAll('[data-action="toggle-favorite"]').forEach((button) => {
    if (button.dataset.id !== String(id)) return;
    const label = `${pressed ? '取消收藏' : '收藏'}：${title}`;
    button.classList.toggle('is-favorite', pressed);
    button.setAttribute('aria-pressed', String(pressed));
    button.setAttribute('aria-label', label);
    button.title = label;
  });
}

function handleFavorite(button) {
  const id = button.dataset.id;
  if (!id) {
    showToast('该记录缺少有效标识，无法收藏。', 'error');
    return;
  }
  const result = state.userStore.toggleFavorite(id);
  state.userData = result.data;
  if (!result.saved) markStorageUnavailable();
  updateFavoriteButtons(id);
  updateNavigation();
  updateDashboardFavoriteCount();

  if (state.route.name === 'my') {
    renderCurrentView({ focus: false, announce: false });
    const replacement = [...document.querySelectorAll('[data-action="toggle-favorite"]')]
      .find((candidate) => candidate.dataset.id === String(id));
    replacement?.focus();
  } else {
    updateMyStatsView();
  }

  if (!result.saved) {
    showToast('收藏状态已更新，但写入 localStorage 失败；刷新后可能丢失。', 'error', 6000);
  } else if (result.favorite) {
    showToast('已加入我的竞赛。');
  } else if (result.entry) {
    showToast('已取消收藏，已填写的进度与备注仍保留。');
  } else {
    showToast('已从我的竞赛移除。');
  }
}

function handleRemoveTracked(button) {
  const id = button.dataset.id;
  const result = state.userStore.removeEntry(id);
  state.userData = result.data;
  if (!result.saved) markStorageUnavailable();
  updateNavigation();
  updateDashboardFavoriteCount();
  if (state.route.name === 'my') {
    renderCurrentView({ focus: false, announce: false });
  }
  showToast(
    result.saved ? '已从我的竞赛移除。' : '已在当前页面移除，但本地存储写入失败。',
    result.saved ? 'info' : 'error',
  );
}

function readFiltersFromForm() {
  const form = document.getElementById('discovery-filters');
  if (!form) return { ...state.filters };
  const data = new FormData(form);
  const sort = String(data.get('sort') ?? '');
  const status = String(data.get('registrationStatus') ?? '');
  return {
    ...DEFAULT_FILTERS,
    query: String(data.get('query') ?? '').trim(),
    category: String(data.get('category') ?? '').trim(),
    competitionLevel: String(data.get('competitionLevel') ?? '').trim(),
    region: String(data.get('region') ?? '').trim(),
    eligibleParticipants: String(data.get('eligibleParticipants') ?? '').trim(),
    registrationStatus: status,
    sort: SORT_OPTIONS.some((option) => option.value === sort) ? sort : DEFAULT_FILTERS.sort,
  };
}

function activeFilterText(filters) {
  const count = countActiveFilters(filters);
  return count ? `已启用 ${count} 项条件` : '未启用筛选条件';
}

function refreshDiscoveryResults() {
  if (state.route.name !== 'competitions') return;
  state.filters = readFiltersFromForm();
  state.now = new Date();
  const nextHash = buildDiscoveryHash(state.filters);
  try {
    if (window.location.hash !== nextHash) {
      window.history.replaceState(null, '', nextHash);
    }
    state.route = parseRoute(nextHash);
  } catch {
    state.route = parseRoute(nextHash);
  }

  const results = document.getElementById('competition-results');
  if (results) results.innerHTML = views.renderCompetitionResultsInner(currentContext());
  const activeCount = document.getElementById('filter-active-count');
  if (activeCount) activeCount.textContent = activeFilterText(state.filters);
  updateTopSearchValue();
}

function handleClearFilters() {
  window.clearTimeout(queryFilterTimer);
  state.filters = { ...DEFAULT_FILTERS };
  state.now = new Date();
  const nextHash = '#/competitions';
  try {
    window.history.replaceState(null, '', nextHash);
  } catch {
    window.location.hash = nextHash;
  }
  state.route = parseRoute(nextHash);
  renderCurrentView({ focus: false, announce: true });
  document.getElementById('filter-query')?.focus();
}

function handleProgressChange(select) {
  const id = select.dataset.id;
  if (!id) return;
  const result = state.userStore.setProgress(id, select.value);
  state.userData = result.data;
  if (!result.saved) markStorageUnavailable();
  const fieldHint = select.closest('.field')?.querySelector('.field-hint');
  if (fieldHint) fieldHint.textContent = `当前：${getProgressLabel(select.value)}`;
  setSaveStatus(
    id,
    result.saved ? '已保存 · 仅本机' : '未持久化 · 仅本次会话',
    result.saved ? 'is-saved' : 'is-error',
  );
  updateNavigation();
  updateMyStatsView();
  if (!result.entry && state.route.name === 'my') {
    renderCurrentView({ focus: false, announce: false });
  }
}

function saveNoteField(field) {
  const id = field.dataset.id;
  if (!id) return;
  const result = state.userStore.setNote(id, field.value);
  state.userData = result.data;
  if (!result.saved) markStorageUnavailable();
  setSaveStatus(
    id,
    result.saved ? '已保存 · 仅本机' : '未持久化 · 仅本次会话',
    result.saved ? 'is-saved' : 'is-error',
  );
  updateNavigation();
  updateMyStatsView();
}

function openMobileNav() {
  lastFocusBeforeNav = document.activeElement;
  elements.sidebar.classList.add('is-open');
  elements.sidebarBackdrop.hidden = false;
  elements.mobileMenuButton.setAttribute('aria-expanded', 'true');
  document.body.classList.add('nav-open');
  const target = elements.sidebar.querySelector('.nav-link.is-active')
    ?? elements.sidebar.querySelector('a[href], button:not([disabled])');
  target?.focus();
}

function closeMobileNav({ restoreFocus = true } = {}) {
  const wasOpen = elements.sidebar.classList.contains('is-open');
  elements.sidebar.classList.remove('is-open');
  elements.sidebarBackdrop.hidden = true;
  elements.mobileMenuButton.setAttribute('aria-expanded', 'false');
  document.body.classList.remove('nav-open');
  if (wasOpen && restoreFocus) {
    const fallback = elements.mobileMenuButton;
    (lastFocusBeforeNav?.isConnected ? lastFocusBeforeNav : fallback)?.focus();
  }
  if (wasOpen) lastFocusBeforeNav = null;
}

function trapSidebarFocus(event) {
  if (event.key !== 'Tab' || !elements.sidebar.classList.contains('is-open')) return;
  const focusable = [...elements.sidebar.querySelectorAll('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])')]
    .filter((element) => element.getClientRects().length > 0);
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function handleDocumentSubmit(event) {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;

  if (form.id === 'global-search') {
    event.preventDefault();
    const query = elements.globalSearchInput.value.trim();
    const params = filtersToSearchParams({ ...DEFAULT_FILTERS, query });
    const hash = `#/competitions${params.toString() ? `?${params.toString()}` : ''}`;
    if (window.location.hash === hash) {
      state.route = parseRoute(hash);
      syncFiltersFromRoute(state.route);
      renderCurrentView({ focus: true, announce: true });
    } else {
      window.location.hash = hash;
    }
    return;
  }

  if (form.id === 'discovery-filters') {
    event.preventDefault();
    window.clearTimeout(queryFilterTimer);
    refreshDiscoveryResults();
  }
}

function handleDocumentChange(event) {
  const target = event.target;
  if (!(target instanceof Element)) return;

  if (target.matches('#discovery-filters select')) {
    window.clearTimeout(queryFilterTimer);
    refreshDiscoveryResults();
    return;
  }
  if (target.matches('[data-action="set-progress"]')) {
    handleProgressChange(target);
    return;
  }
  if (target.matches('[data-action="set-note"]')) {
    window.clearTimeout(noteSaveTimer);
    saveNoteField(target);
  }
}

function handleDocumentInput(event) {
  const target = event.target;
  if (!(target instanceof Element)) return;

  if (target.id === 'filter-query') {
    window.clearTimeout(queryFilterTimer);
    queryFilterTimer = window.setTimeout(() => {
      refreshDiscoveryResults();
    }, 240);
    return;
  }
  if (target.matches('[data-action="set-note"]')) {
    const id = target.dataset.id;
    setSaveStatus(id, '编辑中 · 等待自动保存', 'is-dirty');
    window.clearTimeout(noteSaveTimer);
    noteSaveTimer = window.setTimeout(() => {
      saveNoteField(target);
    }, 700);
  }
}

function handleDocumentClick(event) {
  const target = event.target;
  if (!(target instanceof Element)) return;
  const actionElement = target.closest('[data-action]');
  if (!actionElement) return;

  switch (actionElement.dataset.action) {
    case 'skip-to-main':
      event.preventDefault();
      elements.main.focus();
      break;
    case 'toggle-mobile-nav':
      if (elements.sidebar.classList.contains('is-open')) closeMobileNav();
      else openMobileNav();
      break;
    case 'close-mobile-nav':
      closeMobileNav();
      break;
    case 'retry-load':
      if (!state.isLoading) loadDataAndRender({ focus: true, announce: true, retry: true });
      break;
    case 'toggle-favorite':
      handleFavorite(actionElement);
      break;
    case 'remove-tracked':
      handleRemoveTracked(actionElement);
      break;
    case 'clear-filters':
      handleClearFilters();
      break;
    default:
      break;
  }
}

function handleKeydown(event) {
  if (event.key === 'Escape' && elements.sidebar.classList.contains('is-open')) {
    event.preventDefault();
    closeMobileNav();
    return;
  }
  trapSidebarFocus(event);
}

function handleHashChange() {
  ensureRouteHash();
  state.route = parseRoute(window.location.hash);
  syncFiltersFromRoute(state.route);
  closeMobileNav({ restoreFocus: false });
  if (!state.isLoading) {
    renderCurrentView({ focus: true, announce: true });
  }
}

function handleResize() {
  if (window.innerWidth > 900 && elements.sidebar.classList.contains('is-open')) {
    closeMobileNav({ restoreFocus: false });
  }
}

function handleStorageChange(event) {
  if (event.key !== STORAGE_KEY && event.key !== null) return;
  state.userData = state.userStore.read();
  updateNavigation();
  updateDashboardFavoriteCount();
  if (!state.isLoading && ['dashboard', 'competitions', 'competition', 'my'].includes(state.route.name)) {
    renderCurrentView({ focus: false, announce: false });
  }
}

function bindEvents() {
  document.addEventListener('submit', handleDocumentSubmit);
  document.addEventListener('change', handleDocumentChange);
  document.addEventListener('input', handleDocumentInput);
  document.addEventListener('click', handleDocumentClick);
  document.addEventListener('keydown', handleKeydown);
  window.addEventListener('hashchange', handleHashChange);
  window.addEventListener('resize', handleResize);
  window.addEventListener('storage', handleStorageChange);
  elements.sidebar.querySelectorAll('a[href]').forEach((link) => {
    link.addEventListener('click', () => closeMobileNav({ restoreFocus: false }));
  });
}

function init() {
  elements = {
    main: document.getElementById('main-content'),
    demoBanner: document.getElementById('demo-banner'),
    dataModeChip: document.getElementById('data-mode-chip'),
    topbarStatusText: document.getElementById('topbar-status-text'),
    sidebarDataStatus: document.getElementById('sidebar-data-status'),
    sidebar: document.getElementById('sidebar'),
    sidebarBackdrop: document.getElementById('sidebar-backdrop'),
    mobileMenuButton: document.getElementById('mobile-menu-button'),
    globalSearchInput: document.getElementById('global-search-input'),
    globalSearchForm: document.getElementById('global-search'),
    routeAnnouncer: document.getElementById('route-announcer'),
    toastRegion: document.getElementById('toast-region'),
  };

  initUserStore();
  ensureRouteHash();
  state.route = parseRoute(window.location.hash);
  syncFiltersFromRoute(state.route);
  bindEvents();
  updateNavigation();
  loadDataAndRender({ focus: true, announce: true });
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
}