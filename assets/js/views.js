import { icon } from './icons.js';
import {
  displayText,
  escapeHtml as h,
  formatConfidence,
  formatCount,
  formatHash,
  formatTeamSize,
  safeExternalUrl,
} from './html.js';
import {
  deriveRegistrationStatus,
  formatDate,
  formatDateTime,
  formatDateRange,
  formatDuration,
  getDeadlineInfo,
  getRegistrationDisplay,
  parseDateValue,
  sortByDeadline,
} from './dates.js';
import {
  REGISTRATION_STATUS_OPTIONS,
  SORT_OPTIONS,
  countActiveFilters,
  filterCompetitions,
  getDerivedRegistrationCounts,
  getFilterOptions,
  sortCompetitions,
} from './filters.js';
import {
  PROGRESS_OPTIONS,
  getProgressLabel,
  getTrackedItems,
  isFavorite,
} from './storage.js';
import {
  getDataMode,
  hasDemoRecords,
  verificationStatusMeta,
} from './normalize.js';
import { competitionHref } from './router.js';

const FIELD_LABELS = {
  id: '标识',
  title: '标题',
  organizer: '主办方',
  category: '类别',
  competition_level: '竞赛级别',
  eligible_participants: '面向对象',
  team_size: '队伍规模',
  registration_start: '报名开始',
  registration_deadline: '报名截止',
  event_start: '比赛开始',
  event_end: '比赛结束',
  description: '竞赛说明',
  requirements: '参赛要求',
  official_notice_url: '官方通知',
  registration_url: '报名入口',
  source_name: '信息来源',
  source_url: '来源页面',
  published_at: '发布日期',
  fetched_at: '抓取时间',
  last_verified_at: '最后核验',
  verification_status: '核验状态',
  registration_status: '报名状态',
  confidence: '置信度',
  content_hash: '内容指纹',
  region: '地区',
  is_demo: '演示数据',
  missing_fields: '缺失字段',
  verification_notes: '核验说明',
};

const SOURCE_TYPE_LABELS = {
  html_list: 'HTML 列表',
  rss: 'RSS',
  wechat_manual: '人工公众号',
  manual: '人工录入',
  api: 'API',
  demo: '演示来源',
  official: '官方来源',
  official_candidate: '候选官方来源',
  university: '高校来源',
  college: '学院来源',
  media: '公开媒体',
  fixture: '本地测试源',
};

function isMissing(value) {
  return value === null
    || value === undefined
    || (typeof value === 'string' && value.trim() === '')
    || (Array.isArray(value) && value.length === 0);
}

function pending() {
  return '<span class="pending-value">待确认</span>';
}

function text(value, fallback = '待确认') {
  if (isMissing(value)) return `<span class="pending-value">${h(fallback)}</span>`;
  return h(displayText(value, fallback));
}

function count(value) {
  return isMissing(value) ? pending() : h(formatCount(value));
}

function dateValue(value, fallback = '待确认') {
  if (isMissing(value)) return `<span class="pending-value">${h(fallback)}</span>`;
  return h(formatDate(value, fallback));
}

function dateTimeValue(value, fallback = '待确认') {
  if (isMissing(value)) return `<span class="pending-value">${h(fallback)}</span>`;
  return h(formatDateTime(value, fallback));
}

function isDemoRecord(record, ctx) {
  return record?.is_demo === true || ctx?.dataMode === 'demo';
}

function demoBadge(record, ctx) {
  if (!isDemoRecord(record, ctx)) return '';
  return `<span class="badge badge-demo" title="此条记录为演示数据">${icon('alert', { size: 13 })}演示数据</span>`;
}

function demoSourceBadge(source) {
  return source?.is_demo ? `<span class="badge badge-demo">${icon('alert', { size: 13 })}演示来源</span>` : '';
}

function categoryBadge(record) {
  const label = isMissing(record?.category) ? '待确认' : displayText(record.category);
  return `<span class="badge badge-category">${icon('tag', { size: 13 })}${h(label)}</span>`;
}

function levelBadge(record) {
  if (isMissing(record?.competition_level)) return '';
  return `<span class="badge badge-level">${h(displayText(record.competition_level))}</span>`;
}
function registrationPill(record, now) {
  const display = getRegistrationDisplay(record, now);
  return `<span class="status-pill status-${display.tone}"><span class="status-dot" aria-hidden="true"></span>${h(display.label)}</span>`;
}

function verificationPill(status) {
  const meta = verificationStatusMeta(status);
  return `<span class="status-pill status-${meta.tone}"><span class="status-dot" aria-hidden="true"></span>${h(meta.label)}</span>`;
}

function verificationHistoryMarkup(history) {
  if (!Array.isArray(history) || history.length === 0) {
    return '<p class="pending-block">暂无核验记录</p>';
  }
  return `<ol class="verification-history">${history.map((item) => {
    const meta = verificationStatusMeta(item?.status);
    return `<li class="verification-history-item">
      <div class="verification-history-head">
        <span class="status-pill status-${meta.tone}"><span class="status-dot" aria-hidden="true"></span>${h(meta.label)}</span>
        <time>${dateTimeValue(item?.checked_at)}</time>
      </div>
      <div class="verification-history-meta">
        <span>方式：${isMissing(item?.method) ? pending() : h(displayText(item.method))}</span>
        <span>HTTP：${isMissing(item?.http_status) ? pending() : h(String(item.http_status))}</span>
      </div>
      <p>${isMissing(item?.note) ? pending() : h(displayText(item.note))}</p>
    </li>`;
  }).join('')}</ol>`;
}

function sourceState(source) {
  if (!source) return { label: '待确认', tone: 'muted' };
  if (source.enabled === false) return { label: '已停用', tone: 'muted' };
  const status = String(source.status ?? '').toLowerCase();
  const labels = {
    demo: ['演示', 'demo'],
    success: ['抓取成功', 'success'],
    ok: ['抓取成功', 'success'],
    healthy: ['正常', 'success'],
    normal: ['正常', 'success'],
    completed: ['完成', 'success'],
    empty: ['无匹配记录', 'warning'],
    partial: ['部分完成', 'warning'],
    error: ['异常', 'danger'],
    failed: ['失败', 'danger'],
    failure: ['失败', 'danger'],
    fetch_failed: ['抓取失败', 'danger'],
    parse_failed: ['解析失败', 'danger'],
    config_error: ['配置错误', 'danger'],
    robots_blocked: ['robots 阻止', 'warning'],
    broken: ['链接异常', 'danger'],
    timeout: ['请求超时', 'danger'],
    http_error: ['HTTP 异常', 'danger'],
    pending: ['待检查', 'warning'],
    checking: ['检查中', 'info'],
    new: ['待检查', 'warning'],
    never: ['待检查', 'warning'],
    queued: ['排队中', 'info'],
    disabled: ['已停用', 'muted'],
    not_due: ['未到周期', 'info'],
    manual_skipped: ['手动来源跳过', 'info'],
    dry_run: ['试运行', 'info'],
  };
  if (labels[status]) return { label: labels[status][0], tone: labels[status][1] };
  if (source.failure_reason) return { label: '异常', tone: 'danger' };
  return { label: isMissing(source.status_label) ? '待确认' : displayText(source.status_label), tone: 'muted' };
}

function sourceStatePill(source) {
  const state = sourceState(source);
  return `<span class="status-pill status-${state.tone}"><span class="status-dot" aria-hidden="true"></span>${h(state.label)}</span>`;
}

function runState(status) {
  const key = String(status ?? '').toLowerCase();
  if (['success', 'ok', 'completed'].includes(key)) return { label: '成功', tone: 'success' };
  if (['completed_with_errors', 'partial'].includes(key)) return { label: '部分完成', tone: 'warning' };
  if (['failed', 'error', 'failure'].includes(key)) return { label: '失败', tone: 'danger' };
  if (key === 'demo') return { label: '演示', tone: 'demo' };
  if (['running', 'checking'].includes(key)) return { label: '运行中', tone: 'info' };
  return { label: isMissing(status) ? '待确认' : displayText(status), tone: 'muted' };
}

function runStatePill(status) {
  const state = runState(status);
  return `<span class="status-pill status-${state.tone}"><span class="status-dot" aria-hidden="true"></span>${h(state.label)}</span>`;
}

function dataModeMeta(mode) {
  if (mode === 'demo') return { label: '演示数据', tone: 'demo', description: '当前为演示数据模式，不代表真实赛事。' };
  if (mode === 'live') return { label: '公开采集数据', tone: 'live', description: '数据来自公开来源，字段与报名状态仍待人工核验；HTTP 可达不代表报名开放。' };
  return { label: '待确认', tone: 'muted', description: '数据文件未声明数据模式，请以官方来源为准。' };
}

function modeBadge(mode) {
  const meta = dataModeMeta(mode);
  return `<span class="badge badge-mode badge-mode-${meta.tone}">${h(meta.label)}</span>`;
}

function favoriteButton(record, ctx, extraLabel = '') {
  const title = isMissing(record?.title) ? '待确认' : displayText(record.title);
  const pressed = isFavorite(ctx?.userData, record?.id);
  const action = pressed ? '取消收藏' : '收藏';
  return `<button type="button" class="icon-button favorite-button${pressed ? ' is-favorite' : ''}" data-action="toggle-favorite" data-id="${h(record?.id ?? '')}" aria-pressed="${pressed}" aria-label="${h(`${action}：${title}${extraLabel}`)}" title="${h(`${action}：${title}`)}">${icon('bookmark', { size: 18 })}</button>`;
}

function externalButton(url, label, className = 'button button-secondary', demo = false) {
  const safeUrl = safeExternalUrl(url);
  const suffix = demo ? '（演示）' : '';
  if (!safeUrl) {
    return `<span class="button ${h(className.replace('button ', ''))} is-disabled" aria-disabled="true">${h(label)} · 待确认</span>`;
  }
  return `<a class="${h(className)}" href="${h(safeUrl)}" target="_blank" rel="noopener noreferrer">${h(label)}${suffix}${icon('external', { size: 16 })}</a>`;
}

function externalTextLink(url, label, className = 'text-link') {
  const safeUrl = safeExternalUrl(url);
  if (!safeUrl) return `<span class="pending-value">${h(label)}待确认</span>`;
  return `<a class="${h(className)}" href="${h(safeUrl)}" target="_blank" rel="noopener noreferrer">${h(label)}${icon('external', { size: 14 })}</a>`;
}

function emptyState({ title, description, actions = '' }) {
  return `<div class="empty-state">
    <span class="empty-icon" aria-hidden="true">${icon('inbox', { size: 34 })}</span>
    <h2>${h(title)}</h2>
    <p>${h(description)}</p>
    ${actions ? `<div class="empty-actions">${actions}</div>` : ''}
  </div>`;
}
function pageHeader({ eyebrow = 'INTELLIGENCE DESK', title, description = '', actions = '' }) {
  return `<header class="page-head">
    <div class="page-head-copy">
      <p class="eyebrow">${h(eyebrow)}</p>
      <h1 id="page-title">${h(title)}</h1>
      ${description ? `<p class="page-description">${description}</p>` : ''}
    </div>
    ${actions ? `<div class="page-actions">${actions}</div>` : ''}
  </header>`;
}
function dataWarning(ctx) {
  const errors = Array.isArray(ctx?.errors) ? ctx.errors : [];
  if (!errors.length) return '';
  const details = errors.map((error) => `<li><code>${h(error.path ?? '')}</code>：${h(error.message ?? '读取失败')}</li>`).join('');
  return `<div class="notice notice-warning" role="status">
    <span class="notice-icon" aria-hidden="true">${icon('alert', { size: 20 })}</span>
    <div class="notice-body">
      <strong>部分数据未能加载</strong>
      <p>页面不会用虚假内容补位，受影响的统计与字段会显示待确认。</p>
      <ul class="notice-details">${details}</ul>
    </div>
    <button type="button" class="button button-secondary button-small" data-action="retry-load">重新加载</button>
  </div>`;
}
function factItem(label, valueHtml) {
  return `<div class="fact-item"><dt>${h(label)}</dt><dd>${valueHtml}</dd></div>`;
}

function statusRow(label, valueHtml, hint = '') {
  return `<div class="status-row">
    <dt>${h(label)}</dt>
    <dd>${valueHtml}${hint ? `<span class="status-hint">${h(hint)}</span>` : ''}</dd>
  </div>`;
}

function multilineText(value) {
  return isMissing(value)
    ? `<p class="pending-block">${pending()}</p>`
    : `<p class="pre-wrap">${h(displayText(value))}</p>`;
}

function recordPendingFields(record) {
  if (!record) return [];
  const declared = Array.isArray(record.missing_fields) ? record.missing_fields : [];
  const computed = [
    'title', 'organizer', 'category', 'competition_level', 'eligible_participants',
    'team_size', 'registration_start', 'registration_deadline', 'event_start', 'event_end',
    'description', 'requirements', 'official_notice_url', 'registration_url', 'source_name',
    'published_at', 'fetched_at', 'last_verified_at', 'region', 'confidence',
    'verification_notes',
  ].filter((field) => isMissing(record[field]));
  return [...new Set([...declared, ...computed].map(String))];
}

function formatFieldName(field) {
  return FIELD_LABELS[field] ?? String(field ?? '待确认');
}

function optionMarkup(options, selected) {
  return options.map((option) => {
    const value = typeof option === 'string' ? option : option.value;
    const label = typeof option === 'string' ? option : option.label;
    return `<option value="${h(value)}"${String(value) === String(selected) ? ' selected' : ''}>${h(label)}</option>`;
  }).join('');
}
export function renderDashboard(ctx) {
  const records = Array.isArray(ctx.competitions?.records) ? ctx.competitions.records : [];
  const now = ctx.now;
  const statusCounts = getDerivedRegistrationCounts(records, now);
  const pendingCount = records.filter((record) => ['pending', 'incomplete'].includes(record.verification_status)).length;
  const verifiedCount = records.filter((record) => record.verification_status === 'verified').length;
  const demoCount = records.filter((record) => isDemoRecord(record, ctx)).length;
  const favoriteCount = getTrackedItems(ctx.userData).filter((entry) => entry.favorite).length;
  const registrationDisplays = records.map((record) => getRegistrationDisplay(record, now));
  const confirmedOpenCount = registrationDisplays.filter((display) => display.key === 'open').length;
  const confirmedUpcomingCount = registrationDisplays.filter((display) => display.key === 'upcoming').length;
  const unverifiedWindowCount = registrationDisplays.filter(
    (display) => display.key === 'pending_window',
  ).length;
  const closingSoon = records.filter((record) => {
    const info = getDeadlineInfo(record, now);
    return deriveRegistrationStatus(record, now) !== 'closed'
      && info.days !== null
      && info.days >= 0
      && info.days <= 7;
  });
  const deadlineRecords = sortByDeadline(
    records.filter((record) => {
      const info = getDeadlineInfo(record, now);
      return info.deadline && deriveRegistrationStatus(record, now) !== 'closed';
    }),
    'asc',
  ).slice(0, 5);

  const latestDiscoveries = records
    .map((record) => {
      const published = parseDateValue(record.published_at, 'start');
      const fetched = parseDateValue(record.fetched_at, 'start');
      const timestamp = published ?? fetched;
      return { record, published, fetched, timestamp };
    })
    .filter((item) => item.timestamp)
    .sort((left, right) => right.timestamp.getTime() - left.timestamp.getTime())
    .slice(0, 5);

  const sources = Array.isArray(ctx.sources?.sources) ? ctx.sources.sources : null;
  const normalSourceCount = sources
    ? sources.filter((source) => ['success', 'ok', 'healthy', 'normal', 'completed'].includes(String(source.status ?? '').toLowerCase())).length
    : null;
  const failedSourceCount = sources
    ? sources.filter((source) => ['error', 'failed', 'failure', 'broken', 'timeout', 'http_error'].includes(String(source.status ?? '').toLowerCase())).length
    : null;
  const enabledSourceCount = sources ? sources.filter((source) => source.enabled !== false).length : null;

  const categories = new Map();
  for (const record of records) {
    const label = isMissing(record.category) ? '待确认' : displayText(record.category);
    categories.set(label, (categories.get(label) ?? 0) + 1);
  }
  const categoryRows = [...categories.entries()].sort((left, right) => right[1] - left[1]);
  const categoryMax = categoryRows[0]?.[1] ?? 1;
  const mode = dataModeMeta(ctx.dataMode);
  const generatedAt = ctx.competitions?.generated_at;
  const lastRun = ctx.meta?.last_run;

  const stats = [
    {
      iconName: 'layers',
      label: '收录竞赛',
      value: records.length,
      foot: `已核验 ${verifiedCount} 条`,
      tone: 'indigo',
    },
    {
      iconName: 'clock',
      label: '正在报名',
      value: confirmedOpenCount,
      foot: unverifiedWindowCount
        ? `另有 ${unverifiedWindowCount} 条窗口内待核验`
        : `${statusCounts.upcoming} 条即将开始`,
      tone: 'green',
    },
    {
      iconName: 'calendar',
      label: '7 天内截止',
      value: closingSoon.length,
      foot: '包含今天截止的记录',
      tone: 'amber',
    },
    {
      iconName: 'bookmark',
      label: '已收藏',
      value: favoriteCount,
      valueId: 'dashboard-favorite-count',
      foot: '保存在当前浏览器',
      tone: 'indigo',
    },
    {
      iconName: 'shield',
      label: '待核验',
      value: pendingCount,
      foot: demoCount ? `${demoCount} 条演示记录` : `${statusCounts.closed} 条已截止`,
      tone: 'rose',
    },
  ].map((stat) => `<article class="stat-card stat-${stat.tone}">
    <div class="stat-top"><span class="stat-icon" aria-hidden="true">${icon(stat.iconName, { size: 22 })}</span><span class="stat-label">${h(stat.label)}</span></div>
    <p class="stat-value"${stat.valueId ? ` id="${h(stat.valueId)}"` : ''}>${h(formatCount(stat.value))}</p>
    <p class="stat-foot">${h(stat.foot)}</p>
  </article>`).join('');

  const deadlineList = deadlineRecords.length
    ? `<div class="deadline-list">${deadlineRecords.map((record) => {
      const info = getDeadlineInfo(record, now);
      const deadlineDate = parseDateValue(record.registration_deadline, 'end');
      const title = isMissing(record.title) ? '待确认' : displayText(record.title);
      return `<a class="deadline-row" href="${h(competitionHref(record.id))}">
        <span class="deadline-date" aria-hidden="true"><strong>${deadlineDate ? String(deadlineDate.getDate()).padStart(2, '0') : '--'}</strong><span>${deadlineDate ? `${deadlineDate.getMonth() + 1}月` : '待定'}</span></span>
        <span class="deadline-copy">
          <span class="inline-badges">${demoBadge(record, ctx)}${levelBadge(record)}</span>
          <strong>${h(title)}</strong>
          <span>${text(record.organizer)} · ${text(record.region)}</span>
        </span>
        <span class="deadline-side">${registrationPill(record, now)}<span class="deadline-relative">${h(info.label)}</span></span>
      </a>`;
    }).join('')}</div>`
    : `<div class="compact-empty">${icon('calendar', { size: 22 })}<div><strong>暂无带有效截止日期的未截止竞赛</strong><p>不是伪造数据：当前记录中没有可用于提醒的截止日期。</p></div></div>`;

  const latestList = latestDiscoveries.length
    ? `<div class="latest-list">${latestDiscoveries.map((item) => {
      const title = isMissing(item.record.title) ? '待确认' : displayText(item.record.title);
      const timeRows = [
        item.published ? `<span><span class="latest-time-label">发布</span><time>${dateTimeValue(item.record.published_at)}</time></span>` : '',
        item.fetched ? `<span><span class="latest-time-label">采集</span><time>${dateTimeValue(item.record.fetched_at)}</time></span>` : '',
      ].join('');
      return `<a class="latest-row" href="${h(competitionHref(item.record.id))}">
        <span class="latest-main">
          <span class="inline-badges">${demoBadge(item.record, ctx)}${categoryBadge(item.record)}</span>
          <strong>${h(title)}</strong>
          <span>${text(item.record.source_name)} · ${text(item.record.region)}</span>
        </span>
        <span class="latest-times">${timeRows}</span>
      </a>`;
    }).join('')}</div>`
    : `<div class="compact-empty">${icon('clock', { size: 22 })}<div><strong>暂无带发布或采集时间的记录</strong><p>最新发现列表只使用 published_at 或 fetched_at，不推测时间。</p></div></div>`;

  const categoryList = categoryRows.length
    ? `<div class="category-bars">${categoryRows.slice(0, 7).map(([label, value]) => {
      const width = Math.max(4, Math.round((value / categoryMax) * 100));
      return `<div class="category-row">
        <div class="category-copy"><span>${h(label)}</span><strong>${h(formatCount(value))}</strong></div>
        <div class="category-track" aria-hidden="true"><span style="width:${width}%"></span></div>
      </div>`;
    }).join('')}</div>`
    : `<div class="compact-empty"><div><strong>暂无类别统计</strong><p>当前没有可聚合的竞赛记录。</p></div></div>`;

  return `<section class="page" aria-labelledby="page-title">
    ${dataWarning(ctx)}
    ${pageHeader({
      title: '仪表盘',
      description: `把分散的校园竞赛信号收拢到一处。当前共 ${h(formatCount(records.length))} 条记录，数据更新于 ${dateTimeValue(generatedAt)}。`,
      actions: `<a class="button button-primary" href="#/competitions">${icon('trophy', { size: 18 })}浏览竞赛发现</a><a class="button button-secondary" href="#/sources">${icon('database', { size: 18 })}数据状态</a>`,
    })}
    <div class="stats-grid stats-grid-five">${stats}</div>

    <div class="dashboard-feature-grid">
      <section class="panel" aria-labelledby="deadline-heading">
        <div class="panel-header">
          <div><p class="section-kicker">DEADLINE WATCH</p><h2 id="deadline-heading">临近截止</h2></div>
          <a class="text-link" href="#/competitions?sort=deadline_asc">查看全部${icon('arrow-right', { size: 15 })}</a>
        </div>
        ${deadlineList}
      </section>

      <section class="panel" aria-labelledby="latest-heading">
        <div class="panel-header">
          <div><p class="section-kicker">LATEST SIGNALS</p><h2 id="latest-heading">最新发现</h2></div>
          <a class="text-link" href="#/competitions?sort=published_desc">按发现时间查看${icon('arrow-right', { size: 15 })}</a>
        </div>
        ${latestList}
      </section>
    </div>

    <div class="dashboard-grid">
      <div class="stack">
        <section class="panel" aria-labelledby="category-heading">
          <div class="panel-header">
            <div><p class="section-kicker">PORTFOLIO MIX</p><h2 id="category-heading">类别分布</h2></div>
            <span class="panel-meta">${h(formatCount(categoryRows.length))} 个类别</span>
          </div>
          ${categoryList}
        </section>
      </div>

      <aside class="stack">
        <section class="panel" aria-labelledby="data-status-heading">
          <div class="panel-header"><div><p class="section-kicker">DATA HEALTH</p><h2 id="data-status-heading">数据状态</h2></div>${modeBadge(ctx.dataMode)}</div>
          <dl class="status-list">
            ${statusRow('数据模式', `<span class="mode-text mode-${mode.tone}">${h(mode.label)}</span>`, mode.description)}
            ${statusRow('数据生成时间', dateTimeValue(generatedAt))}
            ${statusRow('收录记录', count(records.length), `${confirmedOpenCount} 条已确认报名中 · ${unverifiedWindowCount} 条待核验`)}
            ${statusRow('信息源', sources ? count(`${normalSourceCount ?? 0} / ${sources.length}`) : pending(), sources ? `${enabledSourceCount ?? 0} 个启用 · ${failedSourceCount ?? 0} 个异常` : '信息源数据未加载')}
            ${statusRow('最近一次运行', lastRun?.status ? runStatePill(lastRun.status) : pending(), isMissing(lastRun?.message) ? '' : displayText(lastRun.message))}
          </dl>
          <a class="panel-link" href="#/sources">打开信息源与运行记录${icon('arrow-right', { size: 15 })}</a>
        </section>

        <section class="panel mode-panel mode-panel-${mode.tone}" aria-labelledby="mode-heading">
          <div class="mode-panel-head"><span class="mode-panel-icon" aria-hidden="true">${icon('shield', { size: 22 })}</span><h2 id="mode-heading">${h(mode.label)}</h2></div>
          <p>${h(mode.description)}</p>
          ${ctx.dataMode === 'demo' ? `<p class="mode-warning">${icon('alert', { size: 16 })}演示内容禁止作为真实报名依据。</p>` : `<p class="mode-note">报名前请回到官方通知页面核对资格、时间与材料要求。</p>`}
        </section>
      </aside>
    </div>
  </section>`;
}
function renderCompetitionCard(record, ctx) {
  const now = ctx.now;
  const demo = isDemoRecord(record, ctx);
  const title = isMissing(record.title) ? pending() : h(displayText(record.title));
  const href = isMissing(record.id) ? null : competitionHref(record.id);
  const titleMarkup = href
    ? `<a href="${h(href)}">${title}</a>`
    : `<span>${title}</span>`;
  const info = getDeadlineInfo(record, now);
  const missingCount = Array.isArray(record.missing_fields) ? record.missing_fields.length : 0;
  const officialLink = safeExternalUrl(record.official_notice_url);
  return `<article class="competition-card${demo ? ' is-demo' : ''}">
    <div class="card-topline">
      <div class="badge-row">${categoryBadge(record)}${levelBadge(record)}${demo ? demoBadge(record, ctx) : ''}</div>
      ${favoriteButton(record, ctx)}
    </div>
    <h2 class="card-title">${titleMarkup}</h2>
    <p class="card-organizer">${icon('trophy', { size: 15 })}<span>主办：${text(record.organizer)}</span></p>
    <dl class="card-facts">
      <div><dt>${icon('pin', { size: 14 })}地区</dt><dd>${text(record.region)}</dd></div>
      <div><dt>${icon('users', { size: 14 })}对象</dt><dd>${text(record.eligible_participants)}</dd></div>
      <div><dt>${icon('users', { size: 14 })}队伍</dt><dd>${isMissing(record.team_size) ? pending() : h(formatTeamSize(record.team_size))}</dd></div>
    </dl>
    <div class="card-deadline">
      <div class="card-deadline-line">${registrationPill(record, now)}<span class="deadline-date-text">截止：${dateValue(record.registration_deadline)}</span></div>
      <span class="deadline-relative">${h(info.label)}</span>
    </div>
    <div class="card-footer">
      <span class="card-source">${icon('link', { size: 14 })}来源：${text(record.source_name)}</span>
      ${missingCount ? `<span class="missing-hint" title="记录自报的缺失字段数量">缺 ${h(formatCount(missingCount))} 项</span>` : ''}
    </div>
    <div class="card-actions">
      ${officialLink ? `<a class="text-link" href="${h(officialLink)}" target="_blank" rel="noopener noreferrer">官方通知${icon('external', { size: 14 })}</a>` : `<span class="pending-inline">官方通知：待确认</span>`}
      ${href ? `<a class="card-detail-link" href="${h(href)}">查看详情${icon('arrow-right', { size: 15 })}</a>` : `<span class="pending-inline">详情待确认</span>`}
    </div>
  </article>`;
}
export function renderCompetitionResultsInner(ctx) {
  const records = Array.isArray(ctx.competitions?.records) ? ctx.competitions.records : [];
  const filtered = filterCompetitions(records, ctx.filters, ctx.now);
  const sorted = sortCompetitions(filtered, ctx.filters?.sort ?? 'deadline_asc');
  const countMarkup = `<p id="competition-results-count" class="results-count" role="status" aria-live="polite">当前显示 <strong>${h(formatCount(sorted.length))}</strong> / 共 ${h(formatCount(records.length))} 条记录</p>`;

  if (!records.length) {
    return `<div class="results-toolbar">${countMarkup}</div>
      ${emptyState({
        title: '暂无竞赛数据',
        description: '数据文件已载入，但当前没有任何竞赛记录。页面不会生成虚构记录。',
        actions: `<a class="button button-secondary" href="#/sources">查看信息源状态</a><a class="button button-ghost" href="#/about">读取打开说明</a>`,
      })}`;
  }

  if (!sorted.length) {
    return `<div class="results-toolbar">${countMarkup}<span class="results-hint">已应用组合筛选</span></div>
      ${emptyState({
        title: '没有找到匹配的竞赛',
        description: '可以尝试缩短关键词、减少筛选项，或清空筛选后重新查看全部记录。',
        actions: `<button type="button" class="button button-primary" data-action="clear-filters">${icon('refresh', { size: 17 })}清空筛选</button><a class="button button-secondary" href="#/sources">查看信息源</a>`,
      })}`;
  }

  return `<div class="results-toolbar">${countMarkup}<span class="results-hint">按${h(SORT_OPTIONS.find((option) => option.value === ctx.filters?.sort)?.label ?? '报名截止')}</span></div>
    <div class="competition-grid" aria-label="竞赛结果列表">
      ${sorted.map((record) => renderCompetitionCard(record, ctx)).join('')}
    </div>`;
}

export function renderCompetitions(ctx) {
  const records = Array.isArray(ctx.competitions?.records) ? ctx.competitions.records : [];
  const filters = ctx.filters;
  const activeCount = countActiveFilters(filters);
  const categoryOptions = getFilterOptions(records, 'category');
  const levelOptions = getFilterOptions(records, 'competition_level');
  const regionOptions = getFilterOptions(records, 'region');
  const audienceOptions = getFilterOptions(records, 'eligible_participants');

  return `<section class="page" aria-labelledby="page-title">
    ${dataWarning(ctx)}
    ${pageHeader({
      title: '竞赛发现',
      description: `组合筛选、按报名截止日期排序。共载入 ${h(formatCount(records.length))} 条记录，报名状态按当前时间与核验状态动态推导。`,
      actions: `<a class="button button-secondary" href="#/sources">${icon('database', { size: 18 })}信息源状态</a>`,
    })}
    <section class="panel filter-panel" aria-labelledby="filter-heading">
      <div class="filter-heading-row">
        <div><p class="section-kicker">FILTER & SEARCH</p><h2 id="filter-heading">筛选竞赛</h2></div>
        <span id="filter-active-count" class="filter-active-count">${activeCount ? `已启用 ${h(formatCount(activeCount))} 项条件` : '未启用筛选条件'}</span>
      </div>
      <form id="discovery-filters" class="filter-form" role="search">
        <div class="filter-grid">
          <div class="field field-wide">
            <label for="filter-query">关键词</label>
            <div class="input-with-icon">
              ${icon('search', { size: 18 })}
              <input id="filter-query" name="query" type="search" value="${h(filters.query ?? '')}" placeholder="搜索竞赛、主办方、地区或说明…" autocomplete="off">
            </div>
          </div>
          <div class="field">
            <label for="filter-category">类别</label>
            <select id="filter-category" name="category">
              <option value="">全部类别</option>${optionMarkup(categoryOptions, filters.category)}
            </select>
          </div>
          <div class="field">
            <label for="filter-level">级别</label>
            <select id="filter-level" name="competitionLevel">
              <option value="">全部级别</option>${optionMarkup(levelOptions, filters.competitionLevel)}
            </select>
          </div>
          <div class="field">
            <label for="filter-region">地区</label>
            <select id="filter-region" name="region">
              <option value="">全部地区</option>${optionMarkup(regionOptions, filters.region)}
            </select>
          </div>
          <div class="field">
            <label for="filter-audience">面向对象</label>
            <select id="filter-audience" name="eligibleParticipants">
              <option value="">全部对象</option>${optionMarkup(audienceOptions, filters.eligibleParticipants)}
            </select>
          </div>
          <div class="field">
            <label for="filter-status">报名状态</label>
            <select id="filter-status" name="registrationStatus">
              <option value="">全部状态</option>${optionMarkup(REGISTRATION_STATUS_OPTIONS, filters.registrationStatus)}
            </select>
          </div>
          <div class="field">
            <label for="filter-sort">排序方式</label>
            <select id="filter-sort" name="sort">${optionMarkup(SORT_OPTIONS, filters.sort)}</select>
          </div>
        </div>
        <div class="filter-actions">
          <button type="submit" class="button button-primary">${icon('filter', { size: 17 })}应用筛选</button>
          <button type="button" class="button button-ghost" data-action="clear-filters">${icon('refresh', { size: 17 })}清空筛选</button>
          <span class="filter-help" id="filter-help">下拉选项切换后即时更新；报名状态按卡片徽标分类，已核验报名中与待核验窗口分开筛选。</span>
        </div>
      </form>
    </section>
    <section class="results-section" id="competition-results" aria-label="筛选结果">
      ${renderCompetitionResultsInner(ctx)}
    </section>
  </section>`;
}
export function renderCompetitionDetail(ctx) {
  const records = Array.isArray(ctx.competitions?.records) ? ctx.competitions.records : [];
  const record = records.find((item) => String(item.id) === String(ctx.route?.id));
  const backHref = ctx.discoveryHref || '#/competitions';

  if (!record) {
    return `<section class="page" aria-labelledby="page-title">
      ${dataWarning(ctx)}
      ${pageHeader({ title: '竞赛详情', description: '无法在当前数据集中定位该竞赛记录。', actions: `<a class="button button-secondary" href="${h(backHref)}">${icon('arrow-left', { size: 17 })}返回竞赛发现</a>` })}
      ${emptyState({
        title: '未找到该竞赛',
        description: '记录可能已被移除，或链接中的竞赛标识无效。页面不会补造缺失的详情。',
        actions: `<a class="button button-primary" href="${h(backHref)}">返回竞赛发现</a><a class="button button-secondary" href="#/sources">查看信息源状态</a>`,
      })}
    </section>`;
  }

  const now = ctx.now;
  const demo = isDemoRecord(record, ctx);
  const registrationDisplay = getRegistrationDisplay(record, now);
  const deadlineInfo = getDeadlineInfo(record, now);
  const pendingFields = recordPendingFields(record);
  const title = isMissing(record.title) ? '待确认' : displayText(record.title);
  const sourceUrl = safeExternalUrl(record.source_url);
  const registrationUrl = safeExternalUrl(record.registration_url);
  const officialUrl = safeExternalUrl(record.official_notice_url);

  return `<section class="page" aria-labelledby="page-title">
    ${dataWarning(ctx)}
    <a class="back-link" href="${h(backHref)}">${icon('arrow-left', { size: 16 })}返回竞赛发现</a>

    ${demo ? `<div class="notice notice-demo" role="note">
      <span class="notice-icon" aria-hidden="true">${icon('alert', { size: 20 })}</span>
      <div class="notice-body"><strong>演示数据</strong><p>本记录仅用于展示界面与字段，不代表真实赛事，请勿据此报名或提交材料。</p></div>
    </div>` : ''}

    <header class="detail-hero panel">
      <div class="detail-hero-main">
        <div class="badge-row">${categoryBadge(record)}${levelBadge(record)}${demoBadge(record, ctx)}${verificationPill(record.verification_status)}</div>
        <h1 id="page-title" class="detail-title">${h(title)}</h1>
        <p class="detail-organizer">${icon('trophy', { size: 17 })}<span>主办方：${text(record.organizer)}</span></p>
        <div class="detail-hero-meta">
          ${registrationPill(record, now)}
          <span class="hero-meta-item">${icon('clock', { size: 15 })}${h(deadlineInfo.label)}</span>
          <span class="hero-meta-item">${icon('pin', { size: 15 })}${text(record.region)}</span>
          <span class="hero-meta-item">${icon('users', { size: 15 })}${text(record.eligible_participants)}</span>
        </div>
      </div>
      <div class="detail-hero-side">
        <div class="detail-actions">
          ${favoriteButton(record, ctx)}
          ${externalButton(record.official_notice_url, '查看官方原文', 'button button-secondary', demo)}
          ${externalButton(record.registration_url, '打开报名入口', 'button button-primary', demo)}
        </div>
        <p class="action-note">${registrationUrl ? '报名入口来自数据记录，请以官方通知为准。' : '报名入口待确认；页面不会生成替代链接。'}</p>
      </div>
    </header>

    <div class="detail-layout">
      <div class="stack">
        <section class="panel" aria-labelledby="key-info-heading">
          <div class="panel-header"><div><p class="section-kicker">KEY INTELLIGENCE</p><h2 id="key-info-heading">关键信息</h2></div>${modeBadge(ctx.dataMode)}</div>
          <dl class="detail-facts">
            ${factItem('类别', text(record.category))}
            ${factItem('竞赛级别', text(record.competition_level))}
            ${factItem('地区', text(record.region))}
            ${factItem('面向对象', text(record.eligible_participants))}
            ${factItem('队伍规模', isMissing(record.team_size) ? pending() : h(formatTeamSize(record.team_size)))}
            ${factItem('报名开始', dateValue(record.registration_start))}
            ${factItem('报名截止', dateValue(record.registration_deadline))}
            ${factItem('比赛时间', isMissing(record.event_start) && isMissing(record.event_end) ? pending() : h(formatDateRange(record.event_start, record.event_end)))}
            ${factItem('发布日期', dateValue(record.published_at))}
            ${factItem('抓取时间', dateTimeValue(record.fetched_at))}
          </dl>
        </section>

        <section class="panel" aria-labelledby="description-heading">
          <div class="panel-header"><div><p class="section-kicker">BRIEFING</p><h2 id="description-heading">竞赛说明</h2></div></div>
          <div class="detail-prose">${multilineText(record.description)}</div>
        </section>

        <section class="panel" aria-labelledby="requirements-heading">
          <div class="panel-header"><div><p class="section-kicker">ELIGIBILITY</p><h2 id="requirements-heading">参赛要求</h2></div></div>
          <div class="detail-prose">${multilineText(record.requirements)}</div>
        </section>
      </div>

      <aside class="stack">
        <section class="panel deadline-panel" aria-labelledby="registration-heading">
          <div class="panel-header"><div><p class="section-kicker">REGISTRATION WINDOW</p><h2 id="registration-heading">报名状态</h2></div></div>
          <div class="status-banner status-${registrationDisplay.tone}">
            <span class="status-banner-label">${h(registrationDisplay.label)}</span>
            <strong>${h(deadlineInfo.label)}</strong>
          </div>
          <dl class="status-list">
            ${statusRow('报名开始', dateTimeValue(record.registration_start))}
            ${statusRow('报名截止', dateTimeValue(record.registration_deadline))}
            ${statusRow('比赛时间', isMissing(record.event_start) && isMissing(record.event_end) ? pending() : h(formatDateRange(record.event_start, record.event_end)))}
          </dl>
          <p class="panel-footnote">状态由页面根据报名起止时间和当前时间实时推导，不直接采用数据文件中的静态状态。</p>
        </section>

        <section class="panel" aria-labelledby="verification-heading">
          <div class="panel-header"><div><p class="section-kicker">VERIFICATION</p><h2 id="verification-heading">核验与来源</h2></div>${verificationPill(record.verification_status)}</div>
          <dl class="status-list">
            ${statusRow('核验状态', verificationPill(record.verification_status))}
            ${statusRow('最后核验', dateTimeValue(record.last_verified_at))}
            ${statusRow('置信度', isMissing(record.confidence) ? pending() : h(formatConfidence(record.confidence)))}
            ${statusRow('信息来源', isMissing(record.source_name) ? pending() : h(displayText(record.source_name)))}
            ${statusRow('来源页面', sourceUrl ? externalTextLink(sourceUrl, '打开来源页面') : pending())}
            ${statusRow('官方原文', officialUrl ? externalTextLink(officialUrl, '打开官方原文') : pending())}
            ${statusRow('报名入口', registrationUrl ? externalTextLink(registrationUrl, '打开报名入口') : pending())}
            ${statusRow('内容指纹', isMissing(record.content_hash) ? pending() : `<code class="hash-value">${h(formatHash(record.content_hash, 20))}</code>`)}
          </dl>
          <div class="verification-note">
            <h3>核验说明</h3>
            ${multilineText(record.verification_notes)}
          </div>
          <div class="verification-history-block">
            <h3>核验记录</h3>
            ${verificationHistoryMarkup(record.verification_history)}
          </div>
        </section>

        <section class="panel" aria-labelledby="missing-heading">
          <div class="panel-header"><div><p class="section-kicker">DATA GAPS</p><h2 id="missing-heading">缺失信息</h2></div><span class="panel-meta">${h(formatCount(pendingFields.length))} 项</span></div>
          ${pendingFields.length
            ? `<div class="missing-chips">${pendingFields.map((field) => `<span class="missing-chip">${h(formatFieldName(field))}<span aria-hidden="true">待确认</span></span>`).join('')}</div><p class="panel-footnote">所有缺失字段在页面中均显示为待确认，不做推测补全。</p>`
            : `<p class="status-ok">${icon('circle-check', { size: 17 })}当前记录未发现缺失字段</p>`}
        </section>
      </aside>
    </div>
  </section>`;
}
function trackedSummary(ctx) {
  const tracked = getTrackedItems(ctx?.userData);
  const records = Array.isArray(ctx?.competitions?.records) ? ctx.competitions.records : [];
  const recordMap = new Map(records.map((record) => [String(record.id), record]));
  const found = tracked.filter((entry) => recordMap.has(entry.id));
  const active = found.filter((entry) => {
    const status = deriveRegistrationStatus(recordMap.get(entry.id), ctx.now);
    return status === 'open' || status === 'upcoming';
  }).length;
  return {
    tracked,
    recordMap,
    total: tracked.length,
    favorite: tracked.filter((entry) => entry.favorite).length,
    active,
    withNotes: tracked.filter((entry) => entry.note.trim()).length,
  };
}

export function renderMyStats(ctx) {
  const summary = trackedSummary(ctx);
  const stats = [
    { iconName: 'bookmark', label: '追踪竞赛', value: summary.total, foot: '保存在当前浏览器', tone: 'indigo' },
    { iconName: 'trophy', label: '已收藏', value: summary.favorite, foot: '可通过书签按钮取消', tone: 'green' },
    { iconName: 'clock', label: '进行中', value: summary.active, foot: '报名中或即将开始', tone: 'amber' },
    { iconName: 'file-text', label: '有备注', value: summary.withNotes, foot: '准备事项仅本机可见', tone: 'rose' },
  ];
  return stats.map((stat) => `<article class="stat-card stat-${stat.tone}">
    <div class="stat-top"><span class="stat-icon" aria-hidden="true">${icon(stat.iconName, { size: 22 })}</span><span class="stat-label">${h(stat.label)}</span></div>
    <p class="stat-value">${h(formatCount(stat.value))}</p>
    <p class="stat-foot">${h(stat.foot)}</p>
  </article>`).join('');
}

export function renderMy(ctx) {
  const summary = trackedSummary(ctx);
  const tracked = summary.tracked;

  if (!tracked.length) {
    return `<section class="page" aria-labelledby="page-title">
      ${dataWarning(ctx)}
      ${pageHeader({
        title: '我的竞赛',
        description: '收藏竞赛、记录准备进度与备注。所有个人数据只保存在当前浏览器的 localStorage 中。',
        actions: `<a class="button button-primary" href="#/competitions">${icon('search', { size: 18 })}去发现竞赛</a>`,
      })}
      ${!ctx.storageAvailable ? `<div class="notice notice-warning" role="status"><span class="notice-icon" aria-hidden="true">${icon('alert', { size: 20 })}</span><div class="notice-body"><strong>浏览器本地存储不可用</strong><p>仍可浏览页面，但收藏、进度和备注无法持久保存。请检查隐私浏览或站点存储权限。</p></div></div>` : ''}
      ${emptyState({
        title: '还没有追踪任何竞赛',
        description: '在竞赛卡片或详情页点击书签按钮即可收藏；之后可以在这里记录准备进度和备注。',
        actions: `<a class="button button-primary" href="#/competitions">浏览竞赛发现</a><a class="button button-secondary" href="#/about">了解本地存储</a>`,
      })}
    </section>`;
  }

  const cards = tracked.map((entry, index) => {
    const record = summary.recordMap.get(entry.id);
    const demo = record ? isDemoRecord(record, ctx) : false;
    const title = record
      ? (isMissing(record.title) ? '待确认' : displayText(record.title))
      : '该竞赛记录已不在当前数据中';
    const titleMarkup = record && !isMissing(record.id)
      ? `<a href="${h(competitionHref(record.id))}">${h(title)}</a>`
      : `<span>${h(title)}</span>`;
    const progressOptions = optionMarkup(PROGRESS_OPTIONS, entry.progress);
    const statusMarkup = record ? registrationPill(record, ctx.now) : '';
    const deadlineText = record
      ? `<span>截止：${dateValue(record.registration_deadline)}</span><span class="deadline-relative">${h(getDeadlineInfo(record, ctx.now).label)}</span>`
      : `<span class="pending-inline">当前数据集中无法核对该记录</span>`;
    return `<article class="my-card${demo ? ' is-demo' : ''}">
      <div class="my-card-head">
        <div>
          <div class="badge-row">${record ? categoryBadge(record) : ''}${record ? levelBadge(record) : ''}${demo ? demoBadge(record, ctx) : ''}${entry.favorite ? `<span class="badge badge-favorite">${icon('bookmark', { size: 13 })}已收藏</span>` : `<span class="badge badge-tracking">${icon('clock', { size: 13 })}跟踪中</span>`}</div>
          <h2 class="my-card-title">${titleMarkup}</h2>
          ${record ? `<p class="card-organizer">${icon('trophy', { size: 15 })}<span>主办：${text(record.organizer)}</span></p>` : `<p class="card-organizer">记录 ID：<code>${h(entry.id)}</code></p>`}
          ${record ? `<div class="my-card-meta">${statusMarkup}${deadlineText}<span>${icon('pin', { size: 14 })}${text(record.region)}</span></div>` : ''}
        </div>
        <div class="my-card-actions">
          ${favoriteButton(record ?? { id: entry.id, title }, ctx)}
          <button type="button" class="icon-button" data-action="remove-tracked" data-id="${h(entry.id)}" aria-label="${h(`移出我的竞赛：${title}`)}" title="移出我的竞赛">${icon('close', { size: 18 })}</button>
        </div>
      </div>
      <div class="tracking-controls">
        <div class="field">
          <label for="my-progress-${index}">个人进度</label>
          <select id="my-progress-${index}" data-action="set-progress" data-id="${h(entry.id)}">
            ${progressOptions}
          </select>
          <p class="field-hint">当前：${h(getProgressLabel(entry.progress))}</p>
        </div>
        <div class="field field-notes">
          <label for="my-note-${index}">备注</label>
          <textarea id="my-note-${index}" rows="3" maxlength="2000" data-action="set-note" data-id="${h(entry.id)}" placeholder="记录材料清单、联系人或准备事项…">${h(entry.note)}</textarea>
          <div class="field-hint-row"><span class="field-hint">仅保存在当前浏览器，不会上传。</span><span class="save-status" data-save-status="${h(entry.id)}" aria-live="polite">已加载</span></div>
        </div>
      </div>
      <div class="my-card-foot">
        <span>最后修改：${dateTimeValue(entry.updatedAt)}</span>
        ${record ? `<a class="text-link" href="${h(competitionHref(record.id))}">查看完整详情${icon('arrow-right', { size: 14 })}</a>` : ''}
      </div>
    </article>`;
  }).join('');

  return `<section class="page" aria-labelledby="page-title">
    ${dataWarning(ctx)}
    ${pageHeader({
      title: '我的竞赛',
      description: `共追踪 ${h(formatCount(summary.total))} 条竞赛。收藏、进度与备注均保存在当前浏览器的 localStorage 中。`,
      actions: `<a class="button button-primary" href="#/competitions">${icon('search', { size: 18 })}继续发现</a>`,
    })}
    ${!ctx.storageAvailable ? `<div class="notice notice-warning" role="status"><span class="notice-icon" aria-hidden="true">${icon('alert', { size: 20 })}</span><div class="notice-body"><strong>浏览器本地存储不可用</strong><p>当前修改只在本次页面会话内有效，刷新后可能丢失。</p></div></div>` : ''}
    <div class="stats-grid" id="my-stats">${renderMyStats(ctx)}</div>
    <div class="my-list">${cards}</div>
  </section>`;
}
function manualVerificationLabel(value) {
  if (!value) return '';
  if (typeof value === 'number') return `${formatCount(value)} 项待核验`;
  return '需人工核验';
}

export function renderSources(ctx) {
  const sources = Array.isArray(ctx.sources?.sources) ? ctx.sources.sources : null;
  const meta = ctx.meta;
  const sourceCount = sources ? sources.length : null;
  const enabledCount = sources ? sources.filter((source) => source.enabled !== false).length : null;
  const errorCount = sources
    ? sources.filter((source) => ['error', 'failed', 'failure', 'broken', 'timeout', 'http_error'].includes(String(source.status ?? '').toLowerCase())).length
    : null;
  const demoSourceCount = sources ? sources.filter((source) => source.is_demo || source.status === 'demo').length : null;
  const manualCount = sources ? sources.filter((source) => Boolean(source.needs_manual_verification)).length : null;
  const lastRun = meta?.last_run;
  const history = Array.isArray(meta?.run_history) ? meta.run_history : [];
  const allRecords = Array.isArray(ctx.competitions?.records) ? ctx.competitions.records : [];
  const reviewRecords = allRecords
    .filter((record) => ['pending', 'incomplete', 'broken'].includes(record.verification_status)
      || (Array.isArray(record.missing_fields) && record.missing_fields.length > 0))
    .slice(0, 20);

  const stats = [
    { iconName: 'database', label: '信息源', value: sourceCount, foot: sources ? `${enabledCount ?? 0} 个启用` : '数据未加载', tone: 'indigo' },
    { iconName: 'alert', label: '异常源', value: errorCount, foot: '读取失败或链接异常', tone: 'rose' },
    { iconName: 'shield', label: '需人工核验', value: manualCount, foot: '至少有一条待核验内容', tone: 'amber' },
    { iconName: 'layers', label: '演示来源', value: demoSourceCount, foot: '不进行真实网络采集', tone: 'green' },
  ].map((stat) => `<article class="stat-card stat-${stat.tone}">
    <div class="stat-top"><span class="stat-icon" aria-hidden="true">${icon(stat.iconName, { size: 22 })}</span><span class="stat-label">${h(stat.label)}</span></div>
    <p class="stat-value">${stat.value === null ? pending() : h(formatCount(stat.value))}</p>
    <p class="stat-foot">${h(stat.foot)}</p>
  </article>`).join('');

  const sourceRows = sources?.length
    ? sources.map((source) => {
      const state = sourceState(source);
      const manual = manualVerificationLabel(source.needs_manual_verification);
      const listLink = safeExternalUrl(source.list_url);
      const sourceType = SOURCE_TYPE_LABELS[source.source_type] ?? source.source_type;
      return `<tr>
        <td>
          <div class="table-primary">${text(source.name)}</div>
          <div class="table-secondary">${source.domain ? h(displayText(source.domain)) : pending()}</div>
          <div class="badge-row table-badges">${demoSourceBadge(source)}${source.enabled === false ? `<span class="badge badge-muted">已停用</span>` : source.enabled === true ? `<span class="badge badge-neutral">启用</span>` : ''}</div>
          <div class="table-link">${listLink ? externalTextLink(listLink, '打开源列表') : `<span class="pending-inline">源列表：待确认</span>`}</div>
        </td>
        <td><div>${isMissing(sourceType) ? pending() : h(displayText(sourceType))}</div><div class="table-secondary">${isMissing(source.update_frequency) ? pending() : h(displayText(source.update_frequency))}</div></td>
        <td><span class="status-pill status-${state.tone}"><span class="status-dot" aria-hidden="true"></span>${h(state.label)}</span>${manual ? `<div class="table-secondary">${h(manual)}</div>` : ''}</td>
        <td><div>${dateTimeValue(source.last_checked_at)}</div><div class="table-secondary">成功：${dateTimeValue(source.last_success_at)}</div></td>
        <td><div>发现 ${count(source.records_found)}</div><div class="table-secondary">新增 ${count(source.records_added)}</div></td>
        <td class="source-note-cell">
          <div>${isMissing(source.result) ? pending() : h(displayText(source.result))}</div>
          ${source.failure_reason ? `<div class="table-error">${icon('alert', { size: 14 })}${h(displayText(source.failure_reason))}</div>` : ''}
        </td>
      </tr>`;
    }).join('')
    : '';

  const reviewMarkup = reviewRecords.length
    ? `<div class="review-list">${reviewRecords.map((record) => {
      const title = isMissing(record.title) ? '待确认' : displayText(record.title);
      const missing = Array.isArray(record.missing_fields) ? record.missing_fields.length : 0;
      const note = isMissing(record.verification_notes)
        ? ''
        : displayText(record.verification_notes).slice(0, 110);
      return `<a class="review-item" href="${h(competitionHref(record.id))}">
        <span class="review-main">
          <span class="badge-row">${verificationPill(record.verification_status)}${isDemoRecord(record, ctx) ? demoBadge(record, ctx) : ''}</span>
          <strong>${h(title)}</strong>
          <span class="review-meta">来源：${text(record.source_name)} · 缺失 ${h(formatCount(missing))} 项 · 最后核验：${dateTimeValue(record.last_verified_at)}</span>
          ${note ? `<span class="review-note">${h(note)}</span>` : ''}
        </span>
        <span class="review-action">查看详情${icon('arrow-right', { size: 15 })}</span>
      </a>`;
    }).join('')}</div>`
    : `<div class="compact-empty">${icon('circle-check', { size: 22 })}<div><strong>当前没有待人工核验记录</strong><p>这不等于记录已经过人工核验；请始终查看来源页面和后端采集状态。</p></div></div>`;

  const historyMarkup = history.length
    ? `<ol class="run-list">${history.map((run) => `<li class="run-item">
      <div class="run-marker" aria-hidden="true"></div>
      <div class="run-content">
        <div class="run-head"><div class="badge-row">${runStatePill(run.status)}<span class="run-id">${h(displayText(run.run_id, '未提供运行 ID'))}</span></div><time>${dateTimeValue(run.finished_at)}</time></div>
        <p>${isMissing(run.message) ? pending() : h(displayText(run.message))}</p>
        <div class="run-meta"><span>开始：${dateTimeValue(run.started_at)}</span><span>结束：${dateTimeValue(run.finished_at)}</span><span>新增：${count(run.records_added)}</span><span>更新：${count(run.records_updated)}</span></div>
      </div>
    </li>`).join('')}</ol>`
    : `<div class="compact-empty">${icon('clock', { size: 22 })}<div><strong>暂无运行历史</strong><p>当前 meta.json 未提供 run_history 记录。</p></div></div>`;

  return `<section class="page" aria-labelledby="page-title">
    ${dataWarning(ctx)}
    <div class="notice notice-info" role="note">
      <span class="notice-icon" aria-hidden="true">${icon('info', { size: 20 })}</span>
      <div class="notice-body">
        <strong>纯静态只读管理面板</strong>
        <p>本页只展示已提交的信息源运行状态，不提供远程启用、停用或权限控制。来源配置需在仓库的 <code>collector/sources.json</code> 中修改并重新运行采集。微信公众号不批量抓取；公开文章链接可由维护者通过 <code>python -m collector.wechat --url &lt;公开链接&gt; --output &lt;目录&gt;</code> 进入待核验流程。</p>
      </div>
    </div>
    ${pageHeader({
      title: '信息源与运行',
      description: '查看采集源配置、最近检查结果和定时任务历史。演示来源不会执行真实网络采集。',
      actions: `<button type="button" class="button button-secondary" data-action="retry-load">${icon('refresh', { size: 17 })}重新读取数据</button>`,
    })}
    ${!isMissing(meta?.notice) ? `<div class="notice notice-info" role="note"><span class="notice-icon" aria-hidden="true">${icon('info', { size: 20 })}</span><div class="notice-body"><p>${h(displayText(meta.notice))}</p></div></div>` : ''}
    <div class="stats-grid">${stats}</div>

    <div class="sources-grid">
      <section class="panel" aria-labelledby="last-run-heading">
        <div class="panel-header"><div><p class="section-kicker">LATEST RUN</p><h2 id="last-run-heading">最近一次运行</h2></div>${lastRun?.status ? runStatePill(lastRun.status) : pending()}</div>
        <dl class="status-list">
          ${statusRow('开始时间', dateTimeValue(lastRun?.started_at))}
          ${statusRow('结束时间', dateTimeValue(lastRun?.finished_at))}
          ${statusRow('耗时', formatDuration(lastRun?.started_at, lastRun?.finished_at))}
          ${statusRow('运行说明', isMissing(lastRun?.message) ? pending() : h(displayText(lastRun.message)))}
        </dl>
        <div class="summary-mini">
          <span><strong>${count(meta?.summary?.source_count)}</strong>信息源</span>
          <span><strong>${count(meta?.summary?.success_count)}</strong>成功</span>
          <span><strong>${count(meta?.summary?.failure_count)}</strong>失败</span>
          <span><strong>${count(meta?.summary?.pending_verification_count)}</strong>待核验</span>
        </div>
      </section>

      <section class="panel" aria-labelledby="source-table-heading">
        <div class="panel-header"><div><p class="section-kicker">SOURCE INVENTORY</p><h2 id="source-table-heading">信息源清单</h2></div>${meta ? modeBadge(getDataMode(ctx.competitions, meta)) : ''}</div>
        ${sources === null
          ? `<div class="compact-empty">${icon('alert', { size: 22 })}<div><strong>信息源数据未能加载</strong><p>没有使用内置假数据补位。请根据上方错误提示检查 sources.json。</p></div></div>`
          : sources.length === 0
            ? `<div class="compact-empty">${icon('database', { size: 22 })}<div><strong>暂无信息源</strong><p>sources.json 当前返回空数组。</p></div></div>`
            : `<div class="table-wrap"><table class="source-table">
                <caption class="sr-only">信息源列表及最近检查状态</caption>
                <thead><tr><th scope="col">信息源</th><th scope="col">类型 / 频率</th><th scope="col">状态</th><th scope="col">检查时间</th><th scope="col">记录数</th><th scope="col">检查说明</th></tr></thead>
                <tbody>${sourceRows}</tbody>
              </table></div>`}
      </section>
    </div>

    <section class="panel" aria-labelledby="review-heading">
      <div class="panel-header"><div><p class="section-kicker">MANUAL REVIEW QUEUE</p><h2 id="review-heading">待人工核验记录</h2></div><span class="panel-meta">${h(formatCount(reviewRecords.length))} 条展示</span></div>
      ${reviewMarkup}
    </section>

    <section class="panel" aria-labelledby="history-heading">
      <div class="panel-header"><div><p class="section-kicker">RUN HISTORY</p><h2 id="history-heading">运行记录</h2></div><span class="panel-meta">${h(formatCount(history.length))} 次</span></div>
      ${historyMarkup}
    </section>
  </section>`;
}
export function renderAbout(ctx) {
  const mode = dataModeMeta(ctx.dataMode);
  const summary = ctx.meta?.summary;
  const recordCount = Array.isArray(ctx.competitions?.records) ? ctx.competitions.records.length : null;
  const schemaVersion = ctx.competitions?.schema_version ?? ctx.meta?.schema_version ?? null;
  return `<section class="page" aria-labelledby="page-title">
    ${dataWarning(ctx)}
    ${pageHeader({
      title: '关于与打开说明',
      eyebrow: 'ABOUT THE RADAR',
      description: '赛讯雷达是一个无构建依赖的静态校园竞赛情报界面，用于聚合竞赛记录、报名窗口、信息源状态与核验信息。',
      actions: `<button type="button" class="button button-secondary" data-action="retry-load">${icon('refresh', { size: 17 })}重新读取数据</button>`,
    })}
    ${ctx.dataMode === 'demo' ? `<div class="notice notice-demo" role="note"><span class="notice-icon" aria-hidden="true">${icon('alert', { size: 20 })}</span><div class="notice-body"><strong>当前为演示数据模式</strong><p>应用展示的是明确标注的演示内容，不代表真实赛事。不要依据演示链接报名或提交个人信息。</p></div></div>` : ''}

    <div class="about-grid">
      <section class="panel prose" aria-labelledby="open-heading">
        <p class="section-kicker">QUICK START</p>
        <h2 id="open-heading">本地打开</h2>
        <p>项目没有构建步骤，但仍需通过 HTTP 静态服务器访问，直接双击 <code>index.html</code> 会因浏览器限制而无法 fetch 本地 JSON。</p>
        <ol class="steps">
          <li><strong>进入项目根目录</strong><p>确保当前目录包含 <code>index.html</code> 与 <code>docs/data/</code>。</p></li>
          <li><strong>启动静态服务器</strong><pre><code>npm run serve</code></pre><p>若脚本不可用，可直接执行：</p><pre><code>python -m http.server 4173</code></pre></li>
          <li><strong>在浏览器访问</strong><p><code>http://localhost:4173</code>。所有页面使用 hash 路由，无需服务器重写规则。</p></li>
        </ol>
        <p class="about-note">GitHub Pages：把仓库根目录作为静态站点发布即可。资源使用相对路径；数据 URL 通过 <code>new URL('docs/data/competitions.json', document.baseURI)</code> 解析，因此仓库子路径也能正常工作。</p>
      </section>

      <section class="panel" aria-labelledby="data-heading">
        <div class="panel-header"><div><p class="section-kicker">DATA SNAPSHOT</p><h2 id="data-heading">当前数据状态</h2></div>${modeBadge(ctx.dataMode)}</div>
        <dl class="status-list">
          ${statusRow('数据模式', h(mode.label), mode.description)}
          ${statusRow('Schema 版本', isMissing(schemaVersion) ? pending() : `<code>${h(displayText(schemaVersion))}</code>`)}
          ${statusRow('生成时间', dateTimeValue(ctx.competitions?.generated_at ?? ctx.meta?.generated_at))}
          ${statusRow('竞赛记录', count(recordCount))}
          ${statusRow('信息源', count(summary?.source_count))}
          ${statusRow('待核验', count(summary?.pending_verification_count))}
          ${statusRow('最近运行', ctx.meta?.last_run?.status ? runStatePill(ctx.meta.last_run.status) : pending())}
        </dl>
        <div class="source-data-note">
          <h3>数据读取位置</h3>
          <ul class="code-list">
            <li><code>docs/data/competitions.json</code></li>
            <li><code>docs/data/sources.json</code></li>
            <li><code>docs/data/meta.json</code></li>
          </ul>
        </div>
      </section>

      <section class="panel prose" aria-labelledby="integrity-heading">
        <p class="section-kicker">INTEGRITY RULES</p>
        <h2 id="integrity-heading">数据与界面约定</h2>
        <ul class="plain-list">
          <li><strong>缺失值不补造：</strong>缺失字段在界面中显示「待确认」，统计只使用已加载数据。</li>
          <li><strong>报名状态动态计算：</strong>页面根据报名开始/截止时间与当前时间推导报名中、即将开始、已截止或待确认，并覆盖静态状态。</li>
          <li><strong>演示数据醒目标记：</strong>演示模式全站显示固定横幅，每条演示记录显示「演示数据」徽标。</li>
          <li><strong>核验不等于担保：</strong>核验状态和置信度只是信息完整性提示，报名前仍须查看官方原文。</li>
          <li><strong>失败不伪装：</strong>数据加载失败会显示错误和本地预览命令，不会回退到内置假记录。</li>
        </ul>
      </section>

      <section class="panel prose" aria-labelledby="privacy-heading">
        <p class="section-kicker">LOCAL FIRST</p>
        <h2 id="privacy-heading">本地存储与隐私</h2>
        <p>收藏、个人进度和备注写入浏览器 <code>localStorage</code>，键名为 <code>campus-competition-radar.user.v1</code>。这些数据不会由本静态站点上传到服务器。</p>
        <ul class="plain-list">
          <li>清除浏览器站点数据会同时删除收藏与备注。</li>
          <li>隐私浏览或禁用存储时，修改只在当前页面会话内有效。</li>
          <li>同一浏览器的不同站点路径可能拥有不同存储空间。</li>
          <li>页面不加载远程字体、CDN 脚本或第三方分析服务。</li>
        </ul>
        <p class="about-note">本工具用于信息整理与提醒，不构成报名资格、赛事真实性或截止时间承诺。请始终以官方通知为准。</p>
      </section>
    </div>
  </section>`;
}

export function renderDataError(ctx) {
  const errors = Array.isArray(ctx?.errors) ? ctx.errors : [];
  const details = errors.length
    ? `<ul class="error-list">${errors.map((error) => `<li><strong>${h(error.path ?? '未知文件')}</strong><span>${h(error.message ?? '读取失败')}</span></li>`).join('')}</ul>`
    : '<p class="pending-value">未获得具体错误信息。</p>';
  return `<section class="load-error" aria-labelledby="page-title" role="alert">
    <div class="error-symbol" aria-hidden="true">${icon('alert', { size: 36 })}</div>
    <p class="eyebrow">DATA LOAD FAILURE</p>
    <h1 id="page-title">竞赛数据加载失败</h1>
    <p class="error-lead">页面没有加载竞赛记录，也没有使用伪造或内置兜底数据。请检查静态服务器和 <code>docs/data/</code> 下的数据文件。</p>
    <div class="error-details panel">
      <h2>错误详情</h2>
      ${details}
    </div>
    <div class="error-actions">
      <button type="button" class="button button-primary" data-action="retry-load">${icon('refresh', { size: 17 })}重新加载数据</button>
      <a class="button button-secondary" href="#/about">打开说明</a>
    </div>
    <div class="panel local-preview-help">
      <h2>本地预览命令</h2>
      <p>在项目根目录启动静态服务器，然后访问 <code>http://localhost:4173</code>：</p>
      <pre><code>npm run serve</code></pre>
      <p>若 npm 脚本不可用，可直接使用 Python：</p>
      <pre><code>python -m http.server 4173</code></pre>
      <p class="about-note">不要直接双击打开 <code>index.html</code>。GitHub Pages 部署时请确认 <code>docs/data/</code> 已随站点发布，并保留相对路径结构。</p>
    </div>
  </section>`;
}

export function renderNotFound(ctx) {
  return `<section class="page" aria-labelledby="page-title">
    ${dataWarning(ctx)}
    ${pageHeader({ title: '页面未找到', eyebrow: '404 / LOST SIGNAL', description: '该 hash 路由不存在，或链接格式不正确。' })}
    ${emptyState({
      title: '没有找到这个页面',
      description: '可返回仪表盘继续查看竞赛情报。页面不会根据无效地址生成内容。',
      actions: `<a class="button button-primary" href="#/dashboard">返回仪表盘</a><a class="button button-secondary" href="#/competitions">竞赛发现</a>`,
    })}
  </section>`;
}