/* Search and filters update the ordinary catalogue page in place. */
(() => {
  'use strict';
  const form = document.getElementById('ext-search-form');
  if (!form) return;
  const input = form.querySelector('[name=q]');
  const tooltip = document.getElementById('ext-tooltip');
  let activeCell;
  let pending;
  let timer;
  let composing = false;

  const hideTooltip = () => {
    tooltip.hidden = true;
    activeCell?.removeAttribute('aria-describedby');
    activeCell = null;
  };
  const showTooltip = cell => {
    if (cell === activeCell) return;
    hideTooltip();
    activeCell = cell;
    tooltip.querySelector('[data-ext-tooltip-name]').textContent = cell.dataset.name;
    tooltip.querySelector('[data-ext-tooltip-description]').textContent = cell.dataset.description;
    tooltip.querySelector('[data-ext-tooltip-metadata]').textContent = cell.dataset.metadata;
    tooltip.hidden = false;
    cell.setAttribute('aria-describedby', tooltip.id);
    const rect = cell.getBoundingClientRect();
    const left = Math.max(12, Math.min(rect.left, window.innerWidth - tooltip.offsetWidth - 12));
    const below = rect.bottom + 10;
    const top = below + tooltip.offsetHeight <= window.innerHeight - 12 ? below : rect.top - tooltip.offsetHeight - 10;
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${Math.max(12, top)}px`;
  };
  for (const type of ['pointerover', 'focusin']) document.addEventListener(type, event => {
    const cell = event.target.closest('.ext-cell');
    if (cell) showTooltip(cell);
  });
  for (const type of ['pointerout', 'focusout']) document.addEventListener(type, event => {
    if (activeCell && activeCell.contains(event.target) && !activeCell.contains(event.relatedTarget)) hideTooltip();
  });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') hideTooltip(); });
  document.addEventListener('scroll', hideTooltip, true);
  window.addEventListener('resize', hideTooltip);

  const cancel = () => {
    clearTimeout(timer);
    if (pending) pending.abort();
  };
  const load = async (url, historyMode = 'push', scroll = false) => {
    cancel();
    hideTooltip();
    const controller = new AbortController();
    pending = controller;
    document.getElementById('ext-results').setAttribute('aria-busy', 'true');
    try {
      const response = await fetch(url, { signal: controller.signal });
      if (!response.ok) throw new Error('catalogue request failed');
      const next = new DOMParser().parseFromString(await response.text(), 'text/html');
      if (controller.signal.aborted) return;
      const focusId = document.activeElement.id;
      for (const id of ['ext-filters', 'ext-field', 'ext-results', 'pgSideNav']) {
        const replacement = next.getElementById(id);
        if (!replacement) throw new Error('catalogue content missing');
        document.getElementById(id).replaceWith(replacement);
      }
      input.value = next.querySelector('#ext-query').value;
      if (focusId !== input.id) document.getElementById(focusId)?.focus({ preventScroll: true });
      document.title = next.title;
      const canonical = document.querySelector('link[rel=canonical]');
      const nextCanonical = next.querySelector('link[rel=canonical]');
      if (canonical && nextCanonical) canonical.href = nextCanonical.href;
      const robots = document.querySelector('meta[name=robots]');
      const nextRobots = next.querySelector('meta[name=robots]');
      if (robots) robots.remove();
      if (nextRobots) document.head.append(nextRobots);
      if (historyMode === 'replace') history.replaceState(null, '', url);
      else if (historyMode === 'push') history.pushState(null, '', url);
      if (scroll) document.getElementById('ext-results').scrollIntoView({ block: 'start' });
    } catch (error) {
      if (!controller.signal.aborted) location.assign(url);
    } finally {
      if (pending === controller) document.getElementById('ext-results').removeAttribute('aria-busy');
    }
  };
  const submit = (mode = 'push') => {
    const url = new URL(form.action);
    for (const [key, value] of new FormData(form)) if (value.trim()) url.searchParams.set(key, value.trim());
    load(url.pathname + url.search, mode);
  };
  const schedule = () => {
    cancel();
    if (!composing) timer = setTimeout(() => submit('replace'), 250);
  };
  input.addEventListener('compositionstart', () => { composing = true; cancel(); });
  input.addEventListener('compositionend', () => { composing = false; schedule(); });
  input.addEventListener('input', schedule);
  form.addEventListener('submit', event => { event.preventDefault(); submit(); });
  form.addEventListener('change', event => { if (event.target.matches('select')) submit(); });
  document.addEventListener('click', event => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest('#pgSideNav a, #ext-results a');
    if (!link || link.target === '_blank') return;
    const url = new URL(link.href);
    if (url.origin !== location.origin || url.pathname !== '/ext/') return;
    event.preventDefault();
    if (link.closest('#pgSideNav')) {
      for (const [key, value] of new FormData(form)) {
        if (key === 'category') continue;
        if (value.trim()) url.searchParams.set(key, value.trim());
        else url.searchParams.delete(key);
      }
    }
    load(url.pathname + url.search, 'push', Boolean(link.closest('.ext-pager')));
  });
  window.addEventListener('popstate', () => load(location.pathname + location.search, 'none'));
})();
