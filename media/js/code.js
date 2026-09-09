/*
 * pg.center code blocks
 * ---------------------------------------------------------------------
 * Wraps every <pre> on content and documentation pages in a
 * framed block with a copy button in the top-right corner (the OINK
 * theme's compact action), and highlights blocks that declare a language
 * (data-lang, a language-* class on the <pre> or its <code>, or
 * class="code", which defaults to bash) with a vendored highlight.js core
 * plus the bash, ini, sql, properties, yaml, diff and json grammars.
 * Loaded as an ES module, so nothing runs until the document is parsed.
 */

import hljs from './vendor/hljs/core.min.js';
import bash from './vendor/hljs/bash.min.js';
import ini from './vendor/hljs/ini.min.js';
import sql from './vendor/hljs/sql.min.js';
import properties from './vendor/hljs/properties.min.js';
import yaml from './vendor/hljs/yaml.min.js';
import diff from './vendor/hljs/diff.min.js';
import json from './vendor/hljs/json.min.js';

/* The stock bash grammar colours keywords, strings, variables and comments
   but leaves the command itself, its flags and URLs plain, which is most
   of what an install snippet is. Put those three in front of it. */
function shell(h) {
  const g = bash(h);
  g.contains = [
    { className: 'built_in', begin: /^[ \t]*(?:sudo[ \t]+)?[\w.\/][\w.\/-]*/ },
    { className: 'params', begin: /(?<=\s)--?[A-Za-z][\w-]*/ },
    { className: 'link', begin: /https?:\/\/[^\s'"<>]+/ },
    ...g.contains,
  ];
  return g;
}

hljs.registerLanguage('bash', shell);
hljs.registerLanguage('ini', ini);
hljs.registerLanguage('sql', sql);
hljs.registerLanguage('properties', properties);
hljs.registerLanguage('yaml', yaml);
hljs.registerLanguage('diff', diff);
hljs.registerLanguage('json', json);

/* Manual pages carry <pre class="programlisting"> without a language; a
   block that opens with a SQL statement is highlighted as SQL. */
const SQL_OPENERS = /^\s*(?:--[^\n]*\n\s*)*(?:SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|WITH|BEGIN|COMMIT|ROLLBACK|GRANT|REVOKE|SET|RESET|SHOW|EXPLAIN|VACUUM|ANALYZE|COPY|TRUNCATE|LISTEN|NOTIFY|PREPARE|EXECUTE|DECLARE|FETCH|LOCK|CLUSTER|REINDEX|CHECKPOINT|COMMENT|DO|CALL|VALUES|TABLE|MERGE|REFRESH|SAVEPOINT|RELEASE|START|END|ABORT|DISCARD|IMPORT|LOAD|MOVE|REASSIGN|SECURITY|UNLISTEN|CLOSE|DEALLOCATE)\b/i;

const ICONS = {
  copy: '<svg class="pg-icon" viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>',
  terminal: '<svg class="pg-icon" viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m4 17 6-6-6-6"/><path d="M12 19h8"/></svg>',
  check: '<svg class="pg-icon pg-icon--check" viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>',
};

const LANG_ALIASES = {
  sh: 'bash', shell: 'bash', zsh: 'bash', console: 'bash', 'shell-session': 'bash',
  conf: 'ini', toml: 'ini', repo: 'ini', cfg: 'ini',
  psql: 'sql', postgresql: 'sql', pgsql: 'sql', plpgsql: 'sql', postgres: 'sql',
  deb822: 'properties', sources: 'properties',
  yml: 'yaml', patch: 'diff', jsonc: 'json', json5: 'json',
};

/* Copy text to the clipboard, with a fallback for browsers without the
   async clipboard API. Shared with main.js (copyScript). */
export function copyText(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    return navigator.clipboard.writeText(text).catch(() => legacyCopy(text));
  }
  return legacyCopy(text);
}

function legacyCopy(text) {
  return new Promise((resolve, reject) => {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand('copy') ? resolve() : reject(new Error('copy failed'));
    } catch (err) {
      reject(err);
    } finally {
      ta.remove();
    }
  });
}

/* Flash the success state on a button for a moment. */
export function flash(button, ok) {
  button.dataset.state = ok ? 'success' : 'error';
  clearTimeout(button._pgFlash);
  button._pgFlash = setTimeout(() => { delete button.dataset.state; }, 2000);
}

window.pgCopyText = copyText;
window.pgFlashButton = flash;

function languageOf(pre) {
  let lang = (pre.dataset.lang || '').toLowerCase();
  if (!lang) {
    const code = pre.querySelector(':scope > code');
    const m = ((pre.className || '') + ' ' + (code ? code.className : '')).match(/\blang(?:uage)?-([a-z0-9+_-]+)/i);
    if (m) lang = m[1].toLowerCase();
  }
  if (!lang && pre.classList.contains('code')) lang = 'bash';
  if (!lang && pre.classList.contains('programlisting') && SQL_OPENERS.test(pre.textContent)) lang = 'sql';
  lang = LANG_ALIASES[lang] || lang;
  return hljs.getLanguage(lang) ? lang : null;
}

const painted = new WeakMap();

function highlight(pre) {
  const lang = languageOf(pre);
  if (!lang) return;
  const text = pre.textContent;
  if (painted.get(pre) === text) return;
  if (!text.trim()) return;
  pre.innerHTML = hljs.highlight(text, { language: lang, ignoreIllegals: true }).value;
  pre.classList.add('hljs');
  painted.set(pre, pre.textContent);
}

function makeButton(icon, title) {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'pg-code__btn';
  b.title = title;
  b.setAttribute('aria-label', title);
  b.innerHTML = ICONS[icon] + ICONS.check;
  return b;
}

/* Restyle an upstream script container (two buttons: copy, copy without
   sudo) into the framed block, keeping the ids download.js binds to. */
function enhanceScriptContainer(box) {
  const pre = box.querySelector('pre');
  if (!pre || box.classList.contains('pg-code')) return;
  box.classList.add('pg-code');
  const actions = document.createElement('div');
  actions.className = 'pg-code__actions';
  box.querySelectorAll('.pg-script-copy-btn').forEach((btn) => {
    const root = btn.classList.contains('pg-script-copy-btn-root');
    btn.classList.add('pg-code__btn');
    btn.innerHTML = (root ? ICONS.terminal : ICONS.copy) + ICONS.check;
    actions.appendChild(btn);
  });
  // The plain copy button reads better as the outermost control.
  const plain = actions.querySelector('.pg-script-copy-btn:not(.pg-script-copy-btn-root)');
  if (plain) actions.appendChild(plain);
  box.appendChild(actions);
  highlight(pre);
  watch(pre);
}

/* Wrap a bare <pre> and give it a verbatim copy button. */
function enhancePre(pre) {
  if (pre.closest('.pg-code')) return;
  const box = document.createElement('div');
  box.className = 'pg-code';
  pre.parentNode.insertBefore(box, pre);
  box.appendChild(pre);
  const actions = document.createElement('div');
  actions.className = 'pg-code__actions';
  const btn = makeButton('copy', '复制');
  btn.addEventListener('click', () => {
    copyText(pre.textContent.replace(/\n$/, '')).then(() => flash(btn, true), () => flash(btn, false));
  });
  actions.appendChild(btn);
  box.appendChild(actions);
  highlight(pre);
  watch(pre);
}

/* Blocks filled by page scripts (the Red Hat repository chooser) get
   re-highlighted when their text changes. */
function watch(pre) {
  if (!languageOf(pre) || pre._pgWatched) return;
  pre._pgWatched = true;
  const mo = new MutationObserver(() => {
    if (painted.get(pre) !== pre.textContent) highlight(pre);
  });
  mo.observe(pre, { childList: true, characterData: true, subtree: true });
}

function init() {
  document.querySelectorAll('.pg-script-container').forEach(enhanceScriptContainer);
  document.querySelectorAll('.pg-page pre, #docContent pre').forEach((pre) => {
    if (pre.closest('.pg-script-container')) return;
    // Skip tiny inline-ish blocks the manual uses for single tokens.
    enhancePre(pre);
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
