import test from 'node:test';
import assert from 'node:assert/strict';

import { DEFAULT_FILTERS } from '../../assets/js/filters.js';
import { renderDashboard, renderSources, renderCompetitionResultsInner } from '../../assets/js/views.js';

test('live mode uses public-collection wording and never claims verified real data', () => {
  const now = new Date(2026, 9, 24, 21, 0, 0);
  const html = renderDashboard({
    competitions: {
      schema_version: '1.0.0',
      data_mode: 'live',
      generated_at: '2026-10-24T20:00:00+08:00',
      records: [],
    },
    sources: { sources: [] },
    meta: {
      data_mode: 'live',
      generated_at: '2026-10-24T20:00:00+08:00',
      summary: {},
      last_run: { status: 'success', message: '示例运行' },
      run_history: [],
    },
    errors: [],
    route: { name: 'dashboard', id: null, query: {} },
    filters: { ...DEFAULT_FILTERS },
    now,
    dataMode: 'live',
    userData: { version: 1, competitions: {} },
    storageAvailable: true,
    discoveryHref: '#/competitions',
  });

  assert.equal(html.includes('公开采集数据'), true);
  assert.equal(html.includes('数据来自公开来源，字段与报名状态仍待人工核验；HTTP 可达不代表报名开放。'), true);
  assert.equal(html.includes('真实数据'), false);
  assert.equal(html.includes('实时数据'), false);
});

test('sources page is explicitly read-only and documents the manual WeChat path', () => {
  const html = renderSources({
    competitions: { data_mode: 'demo', records: [{ id: 'demo-review', title: '【模拟】待核验竞赛', source_name: '演示来源', verification_status: 'broken', missing_fields: ['registration_url'], last_verified_at: null, is_demo: true }] },
    sources: { sources: [] },
    meta: { data_mode: 'demo', summary: {}, last_run: {}, run_history: [] },
    errors: [],
    route: { name: 'sources', id: null, query: {} },
    now: new Date(2026, 9, 24, 21, 0, 0),
    dataMode: 'demo',
    userData: { version: 1, competitions: {} },
    storageAvailable: true,
  });
  assert.equal(html.includes('纯静态只读管理面板'), true);
  assert.equal(html.includes('不提供远程启用、停用或权限控制'), true);
  assert.equal(html.includes('collector.wechat'), true);
  assert.equal(html.includes('待人工核验记录'), true);
  assert.equal(html.includes('待核验竞赛'), true);
});


test('empty combined-filter results render a friendly state and clear action', () => {
  const html = renderCompetitionResultsInner({
    competitions: {
      data_mode: 'demo',
      records: [{
        id: 'demo-x', title: '【模拟】测试竞赛', organizer: '演示主办方', category: '创新创业',
        competition_level: '校级', eligible_participants: '本科生', team_size: '3人',
        registration_start: '2026-10-01T09:00:00+08:00',
        registration_deadline: '2026-11-01T23:59:59+08:00',
        verification_status: 'verified', registration_status: 'open', is_demo: true,
        published_at: '2026-10-01T09:00:00+08:00', fetched_at: '2026-10-01T09:00:00+08:00',
        confidence: 0.5, missing_fields: [],
      }],
    },
    sources: { sources: [] },
    meta: { summary: {}, last_run: {}, run_history: [] },
    errors: [],
    route: { name: 'competitions', id: null, query: {} },
    filters: { ...DEFAULT_FILTERS, query: '完全不存在的关键词' },
    now: new Date(2026, 9, 24, 21, 0, 0),
    dataMode: 'demo',
    userData: { version: 1, competitions: {} },
    storageAvailable: true,
  });
  assert.equal(html.includes('没有找到匹配的竞赛'), true);
  assert.equal(html.includes('data-action="clear-filters"'), true);
  assert.equal(html.includes('清空筛选'), true);
});
