/* Dash-style manual explorer; no client-side corpus or third-party requests. */
(() => {
  'use strict';
  const root = document.getElementById('doc-search');
  if (!root) return;
  const form = document.getElementById('ds-form');
  const query = document.getElementById('ds-query');
  const scope = document.getElementById('ds-scope');
  const kind = document.getElementById('ds-kind');
  const results = document.getElementById('ds-results');
  const facets = document.getElementById('ds-facets');
  const panel = document.getElementById('ds-preview');
  const more = document.getElementById('ds-more');
  const status = document.getElementById('ds-status');
  const notice = document.getElementById('ds-notice');
  const welcome = panel.innerHTML;
  let state = JSON.parse(document.getElementById('ds-initial').textContent);
  let selected = -1;
  let composing = false;
  let timer;
  let searchController;
  let previewController;
  let revision = 0;
  let previewRevision = 0;
  let typingHistory = false;

  function node(tag, className, value) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (value !== undefined) el.textContent = value;
    return el;
  }

  function params(offset = 0) {
    const value = new URLSearchParams({ q: query.value, scope: scope.value });
    if (kind.value) value.set('kind', kind.value);
    if (offset) value.set('offset', offset);
    return value;
  }

  function writeHistory(mode = 'push') {
    const url = '/search/?' + params();
    if (location.pathname + location.search === url) return;
    history[mode === 'replace' ? 'replaceState' : 'pushState'](null, '', url);
  }

  function renderFacets() {
    facets.replaceChildren();
    const all = { key: '', label: '全部内容', icon: '⌕', count: state.all_total || 0 };
    [all, ...(state.facets || [])].forEach((facet) => {
      const link = node('a', 'ds-facet' + (state.kind === facet.key ? ' is-active' : ''));
      const p = params();
      if (facet.key) p.set('kind', facet.key); else p.delete('kind');
      link.href = '/search/?' + p;
      link.dataset.kind = facet.key;
      link.setAttribute('aria-current', state.kind === facet.key ? 'true' : 'false');
      if (facet.hint) link.title = facet.hint;
      link.append(node('span', 'ds-kind-icon ds-kind-' + (facet.key || 'all'), facet.icon),
        node('span', '', facet.label), node('small', '', Number(facet.count).toLocaleString()));
      facets.append(link);
    });
  }

  function resultNode(hit) {
    const link = node('a', 'ds-result');
    link.href = hit.url;
    link.dataset.entry = hit.id;
    link.id = 'ds-result-' + hit.id;
    link.append(node('span', 'ds-kind-icon ds-kind-' + hit.kind, hit.icon));
    const body = node('div', 'ds-result-body');
    const title = node('div', 'ds-result-title');
    // These two fields are escaped by the API; only its <mark> tags are inserted.
    title.innerHTML = hit.name_html;
    const meta = node('div', 'ds-result-meta', hit.label);
    meta.append(node('span', '', 'PG' + hit.version));
    const excerpt = node('p');
    excerpt.innerHTML = hit.snippet;
    body.append(title, meta, excerpt, node('div', 'ds-result-path', hit.heading));
    link.append(body, node('span', 'ds-result-arrow', '›'));
    return link;
  }

  function empty(message, title = '没有找到匹配内容') {
    const box = node('div', 'ds-empty');
    box.append(node('span', '', '⌕'), node('h2', '', title), node('p', '', message));
    return box;
  }

  function render(append = false, previousCount = 0) {
    renderFacets();
    document.getElementById('ds-scope-chip').textContent = state.error ? '未执行检索' : 'pg' + (state.version || '') + ':';
    document.getElementById('ds-results-title').textContent = state.term || state.error ? '检索结果' : state.kind ? '分类索引' : '常用入口';
    document.getElementById('ds-result-count').textContent = Number(state.total).toLocaleString() + ' 个条目';
    document.getElementById('ds-timing').textContent = state.elapsed_ms + ' ms';
    status.textContent = state.error || (state.term ? '找到 ' + state.total + ' 个结果' : '按类别浏览，或直接搜索完整手册');
    notice.textContent = state.notice || '';
    notice.hidden = !state.notice;
    more.hidden = state.next_offset === null || state.next_offset === undefined;
    more.href = '/search/?' + params(state.next_offset || 0);
    if (!append) {
      results.replaceChildren();
      selected = -1;
      query.removeAttribute('aria-activedescendant');
      panel.innerHTML = welcome;
      panel.setAttribute('aria-label', '文档定义预览');
      panel.setAttribute('aria-busy', 'false');
      root.classList.remove('ds-show-preview');
    }
    state.results.slice(append ? previousCount : 0).forEach((hit) => results.append(resultNode(hit)));
    if (!state.results.length) results.append(empty(state.error || '试试更短的名称、中文关键词，或切换文档版本。', state.error ? '暂时无法检索' : undefined));
    if (!append) {
      results.scrollTop = 0;
      if (state.results.length && state.term) select(0, false, false);
    }
  }

  async function run({ append = false, historyMode = 'push', updateHistory = true } = {}) {
    clearTimeout(timer);
    timer = null;
    if (searchController) searchController.abort();
    if (!append) {
      ++previewRevision;
      if (previewController) previewController.abort();
    }
    const request = ++revision;
    searchController = new AbortController();
    root.classList.add('ds-loading');
    results.setAttribute('aria-busy', 'true');
    status.textContent = '正在检索…';
    if (updateHistory) writeHistory(historyMode);
    try {
      const response = await fetch(root.dataset.searchApi + '?' + params(append ? state.next_offset : 0), { signal: searchController.signal });
      if (!response.ok) throw new Error('检索服务暂时不可用。');
      const next = await response.json();
      if (request !== revision) return;
      const previous = append ? state.results : [];
      state = { ...next, results: [...previous, ...next.results] };
      if (!state.error) {
        scope.value = state.scope;
        kind.value = state.kind;
      }
      render(append, previous.length);
    } catch (error) {
      if (error.name !== 'AbortError' && request === revision) {
        status.textContent = '检索服务暂时不可用，请重试。';
        state.results = [];
        selected = -1;
        more.hidden = true;
        panel.innerHTML = welcome;
        panel.setAttribute('aria-label', '文档定义预览');
        panel.setAttribute('aria-busy', 'false');
        root.classList.remove('ds-show-preview');
        results.replaceChildren(empty('请检查连接后重新搜索。', '检索暂时中断'));
      }
    } finally {
      if (request === revision) {
        root.classList.remove('ds-loading');
        results.setAttribute('aria-busy', 'false');
      }
    }
  }

  function related(title, items, definitions = false) {
    const section = node('div', 'ds-related' + (definitions ? ' ds-related-definitions' : ''));
    section.append(node('h3', '', title));
    items.forEach((hit) => {
      const link = node('a', '', definitions ? hit.signature || hit.heading : 'PG' + hit.version);
      link.href = hit.url;
      link.dataset.previewEntry = hit.id;
      section.append(link);
    });
    return section;
  }

  function showPreview(data) {
    const toolbar = node('div', 'ds-preview-toolbar');
    const left = node('div');
    const back = node('button', 'ds-preview-back', '‹ 结果');
    back.type = 'button';
    back.addEventListener('click', () => { root.classList.remove('ds-show-preview'); results.focus({ preventScroll: true }); });
    left.append(back, node('span', '', '定义预览'));
    const open = node('a', 'ds-open-doc', '打开完整文档 ↗');
    open.href = data.url;
    toolbar.append(left, open);
    const content = node('div', 'ds-preview-content');
    const badges = node('div', 'ds-preview-badges');
    badges.append(node('span', 'ds-kind-icon ds-kind-' + data.kind, data.icon), node('span', '', data.label), node('span', 'ds-scope-chip', 'PG' + data.version));
    content.append(badges, node('h2', '', data.name), node('div', 'ds-preview-path', data.heading));
    const source = node('div', 'ds-preview-source');
    source.append(node('span', '', '来源 · PostgreSQL ' + data.version + ' 官方手册'));
    content.append(source);
    const doc = node('div', 'ds-doc');
    // Preview HTML is sanitized server-side and relative links are resolved there.
    doc.innerHTML = data.html;
    content.append(doc);
    if (data.definitions.length && data.kind !== 'guide') content.append(related('同版本的其他定义与签名', data.definitions, true));
    if (data.other_versions.length) content.append(related('其他版本的对应定义', data.other_versions));
    panel.replaceChildren(toolbar, content);
    panel.scrollTop = 0;
    panel.setAttribute('aria-label', data.name + '，文档定义预览');
  }

  async function loadPreview(id) {
    if (previewController) previewController.abort();
    previewController = new AbortController();
    const request = ++previewRevision;
    panel.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch(root.dataset.previewApi + id + '/', { signal: previewController.signal });
      if (!response.ok) throw new Error('预览暂时不可用');
      const data = await response.json();
      if (request === previewRevision) showPreview(data);
    } catch (error) {
      if (error.name !== 'AbortError' && request === previewRevision) {
        panel.replaceChildren(empty('该条目可能已更新。请重新搜索，或打开完整文档。', '暂时无法预览'));
      }
    } finally {
      if (request === previewRevision) panel.setAttribute('aria-busy', 'false');
    }
  }

  function select(index, reveal = true, scroll = true) {
    if (!state.results.length) return;
    selected = Math.max(0, Math.min(index, state.results.length - 1));
    const hit = state.results[selected];
    results.querySelectorAll('.ds-result').forEach((el, i) => {
      el.classList.toggle('is-selected', i === selected);
      el.setAttribute('aria-current', i === selected ? 'true' : 'false');
    });
    const active = results.querySelector('[data-entry="' + hit.id + '"]');
    if (scroll && active) active.scrollIntoView({ block: 'nearest' });
    if (reveal) root.classList.add('ds-show-preview');
    loadPreview(hit.id);
  }

  function schedule() {
    clearTimeout(timer);
    if (composing) return;
    // Invalidate in-flight responses immediately, not only after the debounce elapses.
    ++revision;
    ++previewRevision;
    if (searchController) searchController.abort();
    if (previewController) previewController.abort();
    timer = setTimeout(() => {
      run({ historyMode: typingHistory ? 'replace' : 'push' });
      typingHistory = true;
    }, 150);
  }

  query.addEventListener('input', schedule);
  query.addEventListener('compositionstart', () => {
    composing = true;
    clearTimeout(timer);
    timer = null;
    ++revision;
    ++previewRevision;
    if (searchController) searchController.abort();
    if (previewController) previewController.abort();
  });
  query.addEventListener('compositionend', () => { composing = false; schedule(); });
  query.addEventListener('blur', () => { typingHistory = false; });
  form.addEventListener('submit', (event) => { event.preventDefault(); typingHistory = false; run(); });
  scope.addEventListener('change', () => {
    // A visible version selection replaces a typed PG prefix, so it cannot silently win.
    query.value = query.value.replace(/^pg(?:\d+)?:\s*/i, '');
    typingHistory = false;
    run();
  });
  facets.addEventListener('click', (event) => {
    const link = event.target.closest('[data-kind]');
    if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    kind.value = link.dataset.kind;
    query.value = query.value.replace(/(^|\s)kind:[a-z]+\s*/i, '$1');
    typingHistory = false;
    run();
  });
  document.getElementById('ds-clear').addEventListener('click', () => {
    query.value = ''; kind.value = ''; typingHistory = false; query.focus(); run();
  });
  more.addEventListener('click', (event) => { event.preventDefault(); run({ append: true, updateHistory: false }); });
  results.addEventListener('click', (event) => {
    const link = event.target.closest('[data-entry]');
    if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    select(state.results.findIndex((hit) => hit.id === Number(link.dataset.entry)));
  });
  results.addEventListener('dblclick', (event) => {
    const link = event.target.closest('[data-entry]');
    if (link) location.assign(link.href);
  });
  panel.addEventListener('click', (event) => {
    const example = event.target.closest('[data-query]');
    if (example) {
      query.value = example.dataset.query; kind.value = ''; typingHistory = false; query.focus(); run();
    }
    const definition = event.target.closest('[data-preview-entry]');
    if (definition && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) {
      event.preventDefault(); loadPreview(Number(definition.dataset.previewEntry));
    }
  });
  root.addEventListener('keydown', (event) => {
    if (composing || event.isComposing || event.keyCode === 229) return;
    if (event.target === scope || (event.target.closest('#ds-preview') && event.key !== 'Escape')) return;
    if (['ArrowDown', 'ArrowUp'].includes(event.key) && (event.target === query || results.contains(event.target))) {
      event.preventDefault(); select(selected + (event.key === 'ArrowDown' ? 1 : -1), false);
    } else if (event.key === 'Enter' && event.target === query && selected >= 0 && !timer && !root.classList.contains('ds-loading')) {
      event.preventDefault(); location.assign(state.results[selected].url);
    } else if (event.key === 'Enter' && results.contains(event.target)) {
      const link = event.target.closest('[data-entry]');
      if (link || selected >= 0) {
        event.preventDefault(); location.assign(link ? link.href : state.results[selected].url);
      }
    } else if (event.key === 'Escape') {
      root.classList.remove('ds-show-preview'); query.focus();
    }
  });
  document.addEventListener('keydown', (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault(); query.focus(); query.select();
    } else if (event.key === '/' && !event.metaKey && !event.ctrlKey && !event.altKey && !event.target.closest('input, textarea, select, [contenteditable="true"]')) {
      event.preventDefault(); query.focus();
    }
  });
  window.addEventListener('popstate', () => {
    const p = new URLSearchParams(location.search);
    query.value = p.get('q') || ''; scope.value = p.get('scope') || 'pg'; kind.value = p.get('kind') || '';
    typingHistory = false; run({ updateHistory: false });
  });
  render();
})();
