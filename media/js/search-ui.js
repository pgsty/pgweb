/*
 * Shared pieces of the document search: the search page (docsearch.js) and
 * the site-wide palette (palette.js) render results, the scope token, the
 * category grid, fallback actions and definition previews the same way.
 * Icons come from the SVG sprite in templates/search/icons.html.
 */

export const SEARCH_API = '/search/api/';
export const PREVIEW_API = '/search/preview/';

export const GROUP_ICON = {
  all: 'layers', guc: 'sliders', sql: 'terminal-square', function: 'sigma', type: 'braces',
  relation: 'table', error: 'alert', waitevent: 'layers', tool: 'terminal', psql: 'backslash',
  extension: 'blocks', guide: 'book',
};

export function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

export function icon(name, className = 'ds-icon') {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', className);
  svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', '#pgi-' + name);
  svg.append(use);
  return svg;
}

export function kindBadge(group) {
  const badge = el('span', 'ds-kind ds-kind-' + (group || 'guide'));
  badge.append(icon(GROUP_ICON[group] || 'book'));
  return badge;
}

/* The version being read on a manual page, as a scope key ("pg17"), else
   "pg". Manual pages carry the major on #docContent (the development
   snapshot lives at /docs/devel/, so the URL alone is not enough). */
export function contextScope() {
  const node = document.querySelector('[data-pg-doc-version]');
  if (node && /^\d+$/.test(node.dataset.pgDocVersion)) return 'pg' + node.dataset.pgDocVersion;
  const match = location.pathname.match(/^\/docs\/(\d+)\//);
  return match ? 'pg' + match[1] : 'pg';
}

export function scopeLabel(state) {
  if (state.scope === 'ex') return '扩展目录';
  return 'PG ' + (state.version || '');
}

export function searchURL(query, scope, kind = '') {
  const params = new URLSearchParams({ q: query || '', scope: scope || 'pg' });
  if (kind) params.set('kind', kind);
  return '/search/?' + params;
}

export async function fetchJSON(url, signal) {
  const response = await fetch(url, { signal, headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error('检索服务暂时不可用。');
  return response.json();
}

/* ---- scope token ----------------------------------------------------- */

const PREFIX_TOKEN = /^\s*(pg\d*|ex|ext|pgext)\s*:\s+/i;
/* A typed prefix with or without the trailing space: while it is in the text,
   the text (not the chip) decides the scope. */
export const TYPED_PREFIX = /^\s*(pg\d*|ex|ext|pgext)\s*:/i;

function scopeKey(raw) {
  const key = raw.toLowerCase();
  return key === 'ext' || key === 'pgext' ? 'ex' : key;
}

export function scopeLabelFor(key, current) {
  if (key === 'ex') return '扩展目录';
  if (key === 'pg') return current ? 'PG ' + current : 'PG';
  return 'PG ' + key.slice(2);
}

function scopeText(key, current) {
  if (key === 'ex') return 'ex:';
  if (key === 'pg') return 'pg' + (current || '') + ':';
  return key + ':';
}

/*
 * A scope shown as a token in front of the input. Backspace at the start
 * of the input turns the token back into plain text ("pg18:") that can be
 * edited or deleted; typing a prefix followed by a space ("pg17: ") turns
 * it into a token again. Clicking the token lists the available scopes.
 * Create it before adding your own `input` listener so the token is
 * consumed before the query runs.
 */
export function createScopeField({ chip, input, hidden, scope = 'pg', onChange }) {
  const wrap = chip.parentElement;
  const menu = el('div', 'ds-scope-menu');
  menu.hidden = true;
  menu.setAttribute('role', 'menu');
  wrap.append(menu);
  let current = null;
  let choices = [];

  function paint() {
    chip.hidden = !scope;
    chip.replaceChildren(el('span', '', scopeLabelFor(scope, current)), icon('chevron-down', 'ds-icon ds-chip__caret'));
    hidden.value = scope || 'pg';
    menu.querySelectorAll('[data-scope]').forEach((item) => item.classList.toggle('is-active', item.dataset.scope === scope));
  }

  function closeMenu() {
    menu.hidden = true;
    chip.setAttribute('aria-expanded', 'false');
  }

  function openMenu() {
    if (!choices.length) return;
    menu.hidden = false;
    chip.setAttribute('aria-expanded', 'true');
  }

  function set(next, notify = true) {
    scope = next;
    closeMenu();
    paint();
    if (notify && onChange) onChange();
  }

  function tokenize() {
    const match = input.value.match(PREFIX_TOKEN);
    if (!match) return false;
    input.value = input.value.slice(match[0].length);
    scope = scopeKey(match[1]);
    paint();
    return true;
  }

  function detokenize() {
    const text = scopeText(scope, current);
    const rest = input.value.replace(/^\s+/, '');
    input.value = text + (rest ? ' ' + rest : '');
    scope = '';
    paint();
    input.setSelectionRange(text.length, text.length);
    if (onChange) onChange();
  }

  function buildMenu() {
    menu.replaceChildren();
    choices.forEach((choice) => {
      const item = el('button', 'ds-scope-menu__item', choice.label);
      item.type = 'button';
      item.dataset.scope = choice.key;
      item.setAttribute('role', 'menuitem');
      item.addEventListener('click', () => {
        input.value = input.value.replace(PREFIX_TOKEN, '');
        set(choice.key);
        input.focus();
      });
      menu.append(item);
    });
    paint();
  }

  chip.setAttribute('aria-haspopup', 'menu');
  chip.addEventListener('click', () => (menu.hidden ? openMenu() : closeMenu()));
  input.addEventListener('input', () => { tokenize(); });
  input.addEventListener('keydown', (event) => {
    if (event.isComposing || event.keyCode === 229) return;
    if (event.key === 'Backspace' && scope && input.selectionStart === 0 && input.selectionEnd === 0) {
      event.preventDefault();
      detokenize();
    } else if (event.key === 'Escape' && !menu.hidden) {
      // Cancelled here so the dialog does not close as well.
      event.preventDefault();
      event.stopPropagation();
      closeMenu();
    }
  });
  document.addEventListener('click', (event) => {
    if (!wrap.contains(event.target)) closeMenu();
  });
  paint();

  return {
    get scope() { return scope; },
    set,
    tokenize,
    value() { return scope || 'pg'; },
    update(state) {
      if (state.current) current = state.current;
      if (state.versions) {
        choices = state.versions.map((v) => ({ key: v.key, label: 'PG ' + v.version + (v.current ? ' · 当前' : v.testing ? ' · 测试版' : '') }));
        choices.push({ key: 'ex', label: '扩展目录' });
      }
      buildMenu();
    },
  };
}

/* ---- rows ------------------------------------------------------------ */

/* One result row. `compact` drops the snippet (palette rows). */
export function resultNode(hit, { compact = false } = {}) {
  const link = el('a', 'ds-result');
  link.href = hit.url;
  link.dataset.entry = hit.id;
  link.id = 'ds-entry-' + hit.id;
  link.setAttribute('role', 'option');
  link.append(kindBadge(hit.group));
  const body = el('span', 'ds-result-body');
  const title = el('span', 'ds-result-title');
  // name_html and snippet are escaped by the API; only its <mark> tags come through.
  if (hit.name_html) title.innerHTML = hit.name_html; else title.textContent = hit.name;
  const meta = el('span', 'ds-result-meta', hit.label);
  meta.append(el('i', '', hit.source_label));
  body.append(title, meta);
  if (!compact) {
    const snippet = el('span', 'ds-result-snippet');
    snippet.innerHTML = hit.snippet || '';
    body.append(snippet, el('span', 'ds-result-path', hit.heading));
  } else if (hit.heading && hit.heading !== hit.name) {
    body.append(el('span', 'ds-result-path', hit.heading));
  }
  link.append(body);
  return link;
}

function actionNode(iconName, label, query, href, external = false) {
  const link = el('a', 'ds-result ds-result--action');
  link.href = href;
  link.setAttribute('role', 'option');
  if (external) {
    link.target = '_blank';
    link.rel = 'noopener';
  }
  const badge = el('span', 'ds-kind ds-kind-action');
  badge.append(icon(iconName));
  const body = el('span', 'ds-result-body');
  const title = el('span', 'ds-result-title', label + ' ');
  title.append(el('q', '', query));
  body.append(title);
  link.append(badge, body, icon(external ? 'arrow-up-right' : 'arrow-right', 'ds-icon ds-result__go'));
  return link;
}

/*
 * Fallbacks when the ranked list is not enough: the manual's full text on
 * the search page, the site-wide search (news, pages), and postgresql.org.
 */
export function fallbackRows(query, scope, { site = true } = {}) {
  const term = (query || '').replace(PREFIX_TOKEN, '').trim();
  if (!term) return [];
  const rows = [actionNode('book', '在手册全文中检索', term, searchURL(term, scope, 'guide'))];
  if (site) rows.push(actionNode('layers', '在站内新闻与页面中搜索', term, '/search/?' + new URLSearchParams({ q: term, site: '1' })));
  rows.push(actionNode('arrow-up-right', '在 postgresql.org 搜索', term, 'https://www.postgresql.org/search/?q=' + encodeURIComponent(term), true));
  return rows;
}

/* Category cards for an empty query. */
export function categoryGrid(state, scope) {
  const grid = el('div', 'ds-cats');
  grid.setAttribute('role', 'group');
  grid.setAttribute('aria-label', '按类别浏览');
  (state.facets || []).forEach((facet) => {
    const card = el('a', 'ds-cat');
    card.href = searchURL('', scope, facet.key);
    card.setAttribute('role', 'option');
    card.append(kindBadge(facet.key));
    const body = el('span', 'ds-cat__body');
    body.append(el('strong', '', facet.label), el('span', '', facet.hint || ''));
    card.append(body, el('small', '', Number(facet.count).toLocaleString()));
    grid.append(card);
  });
  return grid;
}

export function emptyNode(message, title = '没有找到匹配内容') {
  const box = el('div', 'ds-empty');
  box.append(el('h2', '', title), el('p', '', message));
  return box;
}

/* ---- preview --------------------------------------------------------- */

/* Wrap tables so wide ones scroll inside the preview, then run the site's
   code-block enhancer (copy button, highlighting). */
function polish(doc) {
  doc.querySelectorAll('table').forEach((table) => {
    if (table.closest('.pg-table-scroll')) return;
    const wrap = el('div', 'pg-table-scroll');
    table.replaceWith(wrap);
    wrap.append(table);
  });
  doc.querySelectorAll('a.id_link, a.indexterm').forEach((node) => node.remove());
  if (window.pgEnhanceCode) window.pgEnhanceCode(doc);
}

/* Version line in the manual's own style: "版本 19 / 18 / 17 …", the one
   being read marked, each link switching the preview in place. */
function versionLine(data, onVersion) {
  const line = el('div', 'ds-preview-versions');
  line.append(el('span', 'ds-preview-versions__label', '版本'));
  data.versions.forEach((item, index) => {
    if (index) line.append(el('span', 'ds-preview-versions__sep', '/'));
    const link = el('a', item.current ? 'is-current' : '', String(item.version));
    link.href = item.url;
    link.title = 'PostgreSQL ' + (item.label || item.version);
    if (item.current) link.setAttribute('aria-current', 'true');
    link.dataset.previewEntry = item.id;
    link.addEventListener('click', (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      if (!item.current) onVersion(item.id, item.version);
    });
    line.append(link);
  });
  return line;
}

function catalogCard(entry) {
  const card = el('a', 'ds-catalog-card');
  card.href = entry.url;
  card.append(kindBadge('extension'));
  const body = el('span', 'ds-catalog-card__body');
  body.append(el('strong', '', entry.name), el('span', '', '扩展目录中的条目' + (entry.signature ? ' · ' + entry.signature : '')));
  card.append(body, icon('arrow-right'));
  return card;
}

/*
 * Render a definition preview into `container`.
 * options.onVersion(id, version): load another version's definition in place.
 * options.onDefinition(id): load an overload / another definition.
 * options.back(): shown on narrow layouts to return to the list.
 */
export function renderPreview(container, data, options = {}) {
  container.replaceChildren();
  const head = el('div', 'ds-preview-head');
  const bar = el('div', 'ds-preview-bar');
  if (options.back) {
    const back = el('button', 'ds-preview-back', '结果');
    back.type = 'button';
    back.prepend(icon('chevron-left'));
    back.addEventListener('click', options.back);
    bar.append(back);
  }
  const kind = el('span', 'ds-preview-kind');
  kind.append(kindBadge(data.group), el('span', '', data.kind_label || data.label));
  bar.append(kind);
  const open = el('a', 'ds-preview-open', data.source === 'ext' ? '打开扩展页' : (data.source === 'errcode' || data.source === 'catalog' || data.source === 'guc' || data.source === 'wait' || data.source === 'sqlcmd' || data.source === 'func') ? '打开词条' : '打开文档');
  open.href = data.url;
  open.append(icon('arrow-up-right'));
  bar.append(open);
  head.append(bar);
  head.append(el('h2', 'ds-preview-title', data.name));
  if (data.signature && data.kind !== 'guide' && data.source !== 'ext') head.append(el('p', 'ds-preview-signature', data.signature));
  if (data.heading && data.heading !== data.name) head.append(el('p', 'ds-preview-path', data.heading));
  if (data.versions && data.versions.length) head.append(versionLine(data, options.onVersion || (() => {})));
  container.append(head);

  const doc = el('article', 'ds-doc pg-prose');
  // Preview HTML is sanitized server-side; links are resolved to reader URLs there.
  doc.innerHTML = data.html;
  container.append(doc);
  polish(doc);

  if (data.catalog) {
    const section = el('div', 'ds-related');
    section.append(el('h3', '', '扩展目录'), catalogCard(data.catalog));
    container.append(section);
  }
  if (data.definitions && data.definitions.length && data.kind !== 'guide') {
    const section = el('div', 'ds-related');
    section.append(el('h3', '', '同版本的其他定义'));
    data.definitions.forEach((item) => {
      const link = el('a', 'ds-related__definition', item.signature || item.heading);
      link.href = item.url;
      link.dataset.previewEntry = item.id;
      link.addEventListener('click', (event) => {
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || !options.onDefinition) return;
        event.preventDefault();
        options.onDefinition(item.id);
      });
      section.append(link);
    });
    container.append(section);
  }
  container.scrollTop = 0;
}
