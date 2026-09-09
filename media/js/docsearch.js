/*
 * The document search page: category filters, instant results, and a
 * definition preview. Server-rendered results are already in the page;
 * this script takes over navigation without reloading. Rendering is
 * shared with the site palette (search-ui.js).
 */
import { PREVIEW_API, SEARCH_API, TYPED_PREFIX, createScopeField, el, emptyNode, fallbackRows, fetchJSON, kindBadge, renderPreview, resultNode, scopeLabel } from './search-ui.js';

const root = document.getElementById('doc-search');
if (root) {
  const form = document.getElementById('ds-form');
  const query = document.getElementById('ds-query');
  const scopeSelect = document.getElementById('ds-scope');
  const kind = document.getElementById('ds-kind');
  const results = document.getElementById('ds-results');
  const facets = document.getElementById('ds-facets');
  const panel = document.getElementById('ds-preview');
  const more = document.getElementById('ds-more');
  const status = document.getElementById('ds-status');
  const notice = document.getElementById('ds-notice');
  const intro = panel.firstElementChild;
  const siteSearch = root.dataset.siteSearch === '1';
  let state = JSON.parse(document.getElementById('ds-initial').textContent);
  let selected = -1;
  let composing = false;
  let timer = null;
  let searchController = null;
  let previewController = null;
  let revision = 0;
  let previewRevision = 0;
  let typingHistory = false;

  root.classList.add('ds-live');
  // The scope token replaces the no-script <select>.
  scopeSelect.disabled = true;
  const scopeValue = el('input');
  scopeValue.type = 'hidden';
  scopeValue.name = 'scope';
  form.append(scopeValue);
  const field = createScopeField({
    chip: document.getElementById('ds-scope-chip'),
    input: query,
    hidden: scopeValue,
    scope: state.error ? scopeSelect.value || 'pg' : state.scope || 'pg',
    onChange: () => { typingHistory = false; run(); },
  });
  field.update(state);
  // The server-rendered query may still carry its prefix ("pg17: work_mem").
  field.tokenize();

  function params(offset = 0) {
    const value = new URLSearchParams({ q: query.value, scope: field.value() });
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
    const all = { key: '', label: '全部', count: state.all_total || 0 };
    [all, ...(state.facets || [])].forEach((facet) => {
      const link = el('a', 'ds-facet' + (state.kind === facet.key ? ' is-active' : ''));
      const p = params();
      if (facet.key) p.set('kind', facet.key); else p.delete('kind');
      link.href = '/search/?' + p;
      link.dataset.kind = facet.key;
      if (state.kind === facet.key) link.setAttribute('aria-current', 'true');
      if (facet.hint) link.title = facet.hint;
      link.append(kindBadge(facet.key || 'all'), el('span', '', facet.label), el('small', '', Number(facet.count).toLocaleString()));
      facets.append(link);
    });
  }

  function showIntro() {
    panel.replaceChildren(intro);
    panel.setAttribute('aria-label', '定义预览');
    root.classList.remove('ds-show-preview');
  }

  function render(append = false, previousCount = 0) {
    renderFacets();
    field.update(state);
    if (TYPED_PREFIX.test(query.value)) field.set('', false);
    const scope = (!state.error && state.scope) || field.value();
    document.getElementById('ds-results-title').textContent = state.term || state.error ? '检索结果' : state.kind ? '分类索引' : '常用条目';
    document.getElementById('ds-result-count').textContent = Number(state.total).toLocaleString();
    status.textContent = state.error || (scopeLabel(state) + ' · ' + (state.term ? '找到 ' + state.total + ' 个结果' : '按类别浏览，或输入名称与关键词'));
    notice.textContent = state.notice || '';
    notice.hidden = !state.notice;
    more.hidden = state.next_offset === null || state.next_offset === undefined;
    more.href = '/search/?' + params(state.next_offset || 0);
    if (!append) {
      results.replaceChildren();
      selected = -1;
      showIntro();
    }
    state.results.slice(append ? previousCount : 0).forEach((hit) => results.append(resultNode(hit)));
    if (!state.results.length) {
      results.append(emptyNode(state.error || state.notice || '没有匹配的名称或定义，试试下面的方式。', state.error ? '暂时无法检索' : undefined));
      if (!state.error) fallbackRows(query.value, scope, { site: siteSearch }).forEach((row) => results.append(row));
    }
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
    if (updateHistory) writeHistory(historyMode);
    try {
      const next = await fetchJSON(SEARCH_API + '?' + params(append ? state.next_offset : 0), searchController.signal);
      if (request !== revision) return;
      const previous = append ? state.results : [];
      state = { ...next, results: [...previous, ...next.results] };
      if (!state.error) kind.value = state.kind;
      render(append, previous.length);
    } catch (error) {
      if (error.name !== 'AbortError' && request === revision) {
        status.textContent = '检索服务暂时不可用，请重试。';
        state.results = [];
        selected = -1;
        more.hidden = true;
        showIntro();
        results.replaceChildren(emptyNode('请检查连接后重新搜索。', '检索暂时中断'));
      }
    } finally {
      if (request === revision) {
        root.classList.remove('ds-loading');
        results.setAttribute('aria-busy', 'false');
      }
    }
  }

  async function loadPreview(id) {
    if (previewController) previewController.abort();
    previewController = new AbortController();
    const request = ++previewRevision;
    panel.setAttribute('aria-busy', 'true');
    try {
      const data = await fetchJSON(PREVIEW_API + id + '/', previewController.signal);
      if (request !== previewRevision) return;
      renderPreview(panel, data, {
        onVersion: loadPreview,
        onDefinition: loadPreview,
        back: () => { root.classList.remove('ds-show-preview'); results.focus({ preventScroll: true }); },
      });
      panel.setAttribute('aria-label', data.name + '，定义预览');
    } catch (error) {
      if (error.name !== 'AbortError' && request === previewRevision) {
        panel.replaceChildren(emptyNode('该条目可能已更新。请重新搜索，或打开完整文档。', '暂时无法预览'));
      }
    } finally {
      if (request === previewRevision) panel.setAttribute('aria-busy', 'false');
    }
  }

  function select(index, reveal = true, scroll = true) {
    if (!state.results.length) return;
    selected = Math.max(0, Math.min(index, state.results.length - 1));
    const hit = state.results[selected];
    results.querySelectorAll('.ds-result').forEach((node, i) => {
      node.classList.toggle('is-selected', i === selected);
      node.setAttribute('aria-selected', i === selected ? 'true' : 'false');
    });
    const active = results.querySelector('[data-entry="' + hit.id + '"]');
    if (scroll && active) active.scrollIntoView({ block: 'nearest' });
    if (reveal) root.classList.add('ds-show-preview');
    loadPreview(hit.id);
  }

  function cancelPending() {
    clearTimeout(timer);
    timer = null;
    ++revision;
    ++previewRevision;
    if (searchController) searchController.abort();
    if (previewController) previewController.abort();
  }

  function schedule() {
    cancelPending();
    if (composing) return;
    timer = setTimeout(() => {
      run({ historyMode: typingHistory ? 'replace' : 'push' });
      typingHistory = true;
    }, 150);
  }

  query.addEventListener('input', schedule);
  query.addEventListener('compositionstart', () => { composing = true; cancelPending(); });
  query.addEventListener('compositionend', () => { composing = false; schedule(); });
  query.addEventListener('blur', () => { typingHistory = false; });
  form.addEventListener('submit', (event) => { event.preventDefault(); typingHistory = false; run(); });
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
  });
  root.addEventListener('keydown', (event) => {
    if (composing || event.isComposing || event.keyCode === 229) return;
    if (event.target.closest('#ds-preview') && event.key !== 'Escape') return;
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
    } else if (event.key === '/' && !event.metaKey && !event.ctrlKey && !event.altKey && !(event.target instanceof Element && event.target.closest('input, textarea, select, [contenteditable="true"]'))) {
      event.preventDefault(); query.focus();
    }
  });
  window.addEventListener('popstate', () => {
    const p = new URLSearchParams(location.search);
    query.value = p.get('q') || ''; field.set(p.get('scope') || 'pg', false); kind.value = p.get('kind') || '';
    field.tokenize();
    typingHistory = false; run({ updateHistory: false });
  });
  render();
}
