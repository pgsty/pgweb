/*
 * Site-wide search palette. On wide screens "/" and ⌘K, the header search
 * box and the manual's search box open a dialog that searches in place.
 * Empty: the categories to browse. Typing: a ranked list, a definition
 * preview beside it when there is room, and fallback actions (manual full
 * text, site-wide search, postgresql.org) at the end of the list. Enter
 * opens the selected row. Narrow screens go straight to /search/.
 */
import { PREVIEW_API, SEARCH_API, TYPED_PREFIX, categoryGrid, contextScope, createScopeField, el, emptyNode, fallbackRows, fetchJSON, renderPreview, resultNode, scopeLabel, searchURL } from './search-ui.js';

const dialog = document.getElementById('pgPalette');
const onSearchPage = Boolean(document.getElementById('doc-search'));
const wide = window.matchMedia('(min-width: 900px)');
const withPreview = window.matchMedia('(min-width: 1100px)');

if (dialog && typeof dialog.showModal === 'function') {
  const input = document.getElementById('pgPaletteInput');
  const list = document.getElementById('pgPaletteList');
  const preview = document.getElementById('pgPalettePreview');
  const status = document.getElementById('pgPaletteStatus');
  const all = document.getElementById('pgPaletteAll');
  const siteSearch = dialog.dataset.siteSearch === '1';
  const LIMIT = 12;
  let state = { results: [] };
  let selected = -1;
  let composing = false;
  let timer = null;
  let searchController = null;
  let previewController = null;
  let revision = 0;
  let previewRevision = 0;
  let closedAt = 0;

  const field = createScopeField({
    chip: document.getElementById('pgPaletteScope'),
    input,
    hidden: document.getElementById('pgPaletteScopeInput'),
    scope: contextScope(),
    onChange: () => schedule(0),
  });

  function open(query = '', scope = contextScope()) {
    if (!wide.matches) {
      location.assign(searchURL(query, scope));
      return;
    }
    field.set(scope, false);
    input.value = query;
    field.tokenize();
    if (!dialog.open) {
      dialog.showModal();
      document.documentElement.classList.add('pg-palette-open');
    }
    input.focus();
    input.select();
    run();
  }

  function close() {
    if (dialog.open) dialog.close();
  }

  function cancelPending() {
    clearTimeout(timer);
    timer = null;
    ++revision;
    ++previewRevision;
    if (searchController) searchController.abort();
    if (previewController) previewController.abort();
  }

  function rows() {
    return Array.from(list.querySelectorAll('[role="option"]'));
  }

  function heading(text) {
    const node = el('div', 'pg-palette__heading', text);
    node.setAttribute('role', 'presentation');
    return node;
  }

  function render() {
    field.update(state);
    // A prefix still in the text is the scope; the chip must not disagree.
    if (TYPED_PREFIX.test(input.value)) field.set('', false);
    const scope = (!state.error && state.scope) || field.value();
    list.replaceChildren();
    preview.replaceChildren();
    selected = -1;
    input.removeAttribute('aria-activedescendant');
    const browse = !state.error && !state.term;
    dialog.classList.toggle('pg-palette--browse', browse);
    all.href = searchURL(input.value, field.value());
    if (browse) {
      list.append(heading('按类别浏览'), categoryGrid(state, scope));
      rows().forEach((node, i) => { node.id = 'pg-palette-row-' + i; });
      status.textContent = scopeLabel(state) + ' · ' + Number(state.all_total || 0).toLocaleString() + ' 个条目';
      return;
    }
    if (state.error) {
      list.append(emptyNode(state.error, '暂时无法检索'));
    } else {
      state.results.forEach((hit) => list.append(resultNode(hit, { compact: true })));
      if (!state.results.length) list.append(emptyNode(state.notice || '没有匹配的名称或定义，试试下面的方式。'));
    }
    const fallbacks = fallbackRows(input.value, scope, { site: siteSearch });
    if (fallbacks.length) {
      list.append(heading(state.results.length ? '继续查找' : '换个范围'));
      fallbacks.forEach((row) => list.append(row));
    }
    rows().forEach((node, i) => { node.id = 'pg-palette-row-' + i; });
    status.textContent = state.error ? '' : scopeLabel(state) + ' · ' + (state.total ? '找到 ' + Number(state.total).toLocaleString() + ' 个结果' : '没有匹配结果');
    if (rows().length) select(0, false);
  }

  async function run() {
    cancelPending();
    const request = ++revision;
    searchController = new AbortController();
    list.setAttribute('aria-busy', 'true');
    try {
      const params = new URLSearchParams({ q: input.value, scope: field.value(), limit: LIMIT });
      state = await fetchJSON(SEARCH_API + '?' + params, searchController.signal);
      if (request !== revision) return;
      render();
    } catch (error) {
      if (error.name !== 'AbortError' && request === revision) {
        list.replaceChildren(emptyNode('请检查连接后重新搜索。', '检索暂时中断'));
        preview.replaceChildren();
        status.textContent = '';
      }
    } finally {
      if (request === revision) list.setAttribute('aria-busy', 'false');
    }
  }

  async function loadPreview(id) {
    if (!withPreview.matches) return;
    if (previewController) previewController.abort();
    previewController = new AbortController();
    const request = ++previewRevision;
    try {
      const data = await fetchJSON(PREVIEW_API + id + '/', previewController.signal);
      if (request === previewRevision) renderPreview(preview, data, { onVersion: loadPreview, onDefinition: loadPreview });
    } catch (error) {
      if (error.name !== 'AbortError' && request === previewRevision) preview.replaceChildren();
    }
  }

  function select(index, scroll = true) {
    const items = rows();
    if (!items.length) {
      selected = -1;
      return;
    }
    selected = Math.max(0, Math.min(index, items.length - 1));
    items.forEach((node, i) => {
      node.classList.toggle('is-selected', i === selected);
      node.setAttribute('aria-selected', i === selected ? 'true' : 'false');
    });
    const node = items[selected];
    input.setAttribute('aria-activedescendant', node.id);
    if (scroll) node.scrollIntoView({ block: 'nearest' });
    if (node.dataset.entry) {
      loadPreview(node.dataset.entry);
    } else {
      ++previewRevision;
      if (previewController) previewController.abort();
      preview.replaceChildren();
    }
  }

  function schedule(delay = 120) {
    cancelPending();
    if (composing) return;
    timer = setTimeout(run, delay);
  }

  input.addEventListener('input', () => schedule());
  input.addEventListener('compositionstart', () => { composing = true; cancelPending(); });
  input.addEventListener('compositionend', () => { composing = false; schedule(); });
  dialog.querySelector('form').addEventListener('submit', (event) => {
    event.preventDefault();
    const items = rows();
    if (selected >= 0 && items[selected] && !timer) {
      items[selected].click();
    } else {
      location.assign(searchURL(input.value, field.value()));
    }
  });
  dialog.addEventListener('keydown', (event) => {
    if (composing || event.isComposing || event.keyCode === 229) return;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      select(selected + (event.key === 'ArrowDown' ? 1 : -1));
    } else if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      location.assign(searchURL(input.value, field.value()));
    }
  });
  list.addEventListener('click', (event) => {
    const link = event.target.closest('[role="option"]');
    if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    // With a preview pane, the first click on a definition selects it; a click on
    // the selected row, or any click without a pane, opens the document.
    const index = rows().indexOf(link);
    if (link.dataset.entry && withPreview.matches && index !== selected) {
      event.preventDefault();
      select(index, false);
    }
  });
  dialog.addEventListener('click', (event) => {
    if (event.target === dialog || event.target.closest('[data-pg-palette-close]')) close();
  });
  dialog.addEventListener('close', () => {
    cancelPending();
    closedAt = Date.now();
    document.documentElement.classList.remove('pg-palette-open');
  });

  // Openers: the header box, the manual's search box, explicit triggers.
  // On the search page itself the header box just hands focus to the page's input.
  document.querySelectorAll('[data-pg-palette-form]').forEach((form) => {
    const target = form.querySelector('input[name="q"]');
    const formScope = form.dataset.pgPaletteScope;
    const trigger = (event) => {
      if (!wide.matches) return;
      event.preventDefault();
      if (onSearchPage) {
        const pageInput = document.getElementById('ds-query');
        if (pageInput) { pageInput.focus(); pageInput.select(); }
        return;
      }
      open(target.value, formScope || contextScope());
      target.blur();
    };
    target.addEventListener('mousedown', trigger);
    target.addEventListener('focus', (event) => {
      // The dialog hands focus back to its opener when it closes; do not reopen from that.
      if (Date.now() - closedAt < 500) return;
      if (!dialog.open && wide.matches && document.hasFocus()) trigger(event);
    });
    target.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && wide.matches) trigger(event);
    });
  });
  document.querySelectorAll('[data-pg-palette-open]').forEach((node) => {
    node.addEventListener('click', (event) => {
      event.preventDefault();
      open(node.dataset.pgPaletteQuery || '', node.dataset.pgPaletteScope || contextScope());
    });
  });
  if (!onSearchPage) {
    document.addEventListener('keydown', (event) => {
      if (dialog.open) return;
      const typing = event.target instanceof Element && event.target.closest('input, textarea, select, [contenteditable="true"]');
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        open('', contextScope());
      } else if (event.key === '/' && !event.metaKey && !event.ctrlKey && !event.altKey && !typing) {
        event.preventDefault();
        open('', contextScope());
      }
    });
  }
  window.pgPalette = { open, close };
}
