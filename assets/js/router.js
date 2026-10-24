function decodeSegment(segment) {
  try {
    return decodeURIComponent(segment);
  } catch {
    return segment;
  }
}

function queryObject(queryString) {
  const params = new URLSearchParams(queryString);
  return Object.fromEntries(params.entries());
}

export function parseRoute(hash = '') {
  let raw = String(hash ?? '').trim();
  if (raw.startsWith('#')) raw = raw.slice(1);
  const questionIndex = raw.indexOf('?');
  const pathPart = questionIndex >= 0 ? raw.slice(0, questionIndex) : raw;
  const queryPart = questionIndex >= 0 ? raw.slice(questionIndex + 1) : '';
  const path = `/${pathPart.replace(/^\/+|\/+$/g, '')}`;
  const query = queryObject(queryPart);
  const segments = path.split('/').filter(Boolean).map(decodeSegment);

  if (!segments.length || segments[0] === 'dashboard') {
    return { name: 'dashboard', path: '/dashboard', segments: [], query, id: null };
  }
  if (segments[0] === 'competitions' && segments.length === 1) {
    return { name: 'competitions', path: '/competitions', segments, query, id: null };
  }
  if (segments[0] === 'competition' && segments.length >= 2) {
    return {
      name: 'competition',
      path: `/competition/${segments.slice(1).join('/')}`,
      segments,
      query,
      id: segments.slice(1).join('/'),
    };
  }
  if (['my', 'sources', 'about'].includes(segments[0]) && segments.length === 1) {
    return { name: segments[0], path: `/${segments[0]}`, segments, query, id: null };
  }
  return { name: 'not-found', path, segments, query, id: null };
}

export function routeTitle(route) {
  const titles = {
    dashboard: '仪表盘',
    competitions: '竞赛发现',
    competition: '竞赛详情',
    my: '我的竞赛',
    sources: '信息源与运行',
    about: '关于与打开说明',
    'not-found': '页面未找到',
  };
  return titles[route?.name] ?? '页面未找到';
}

export function activeNavKey(route) {
  if (route?.name === 'competition') return 'competitions';
  return route?.name ?? '';
}

export function competitionHref(id) {
  return `#/competition/${encodeURIComponent(String(id ?? ''))}`;
}