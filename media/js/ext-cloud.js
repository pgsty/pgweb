/* Enhance the same GET pages used without JavaScript; no separate data model. */
(() => {
  'use strict';
  const form = document.getElementById('cloud-form');
  if (!form || !window.fetch || !window.AbortController) return;
  const dialog = document.getElementById('cloud-dialog');
  const announcement = document.getElementById('cloud-announcement');
  let pending;
  let evidencePending;
  let timer;
  let composing = false;
  let returnFocus;

  const scrollButtons = () => {
    const scroller = document.getElementById('cloud-table-scroll');
    for (const button of document.querySelectorAll('[data-cloud-scroll]')) {
      button.disabled = !scroller || (button.dataset.cloudScroll === '-1'
        ? scroller.scrollLeft < 1
        : scroller.scrollLeft >= scroller.scrollWidth - scroller.clientWidth - 1);
    }
  };
  const enhance = () => {
    document.querySelectorAll('[data-cloud-enhance]').forEach(element => { element.hidden = false; });
    document.getElementById('cloud-table-scroll')?.addEventListener('scroll', scrollButtons, { passive: true });
    scrollButtons();
  };
  const cancel = () => {
    clearTimeout(timer);
    pending?.abort();
  };
  const formURL = () => {
    const url = new URL(form.action);
    for (const [key, value] of new FormData(form)) {
      const clean = value.trim();
      if (clean) url.searchParams.append(key, clean);
    }
    return url.pathname + url.search;
  };
  const load = async (url, historyMode = 'push', paging = false) => {
    cancel();
    if (dialog?.open) dialog.close();
    const controller = new AbortController();
    pending = controller;
    const oldResults = document.getElementById('cloud-results');
    oldResults.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch(url, { signal: controller.signal, headers: { 'X-Requested-With': 'XMLHttpRequest' } });
      if (!response.ok) throw new Error('Cloud catalogue request failed');
      const next = new DOMParser().parseFromString(await response.text(), 'text/html');
      if (controller.signal.aborted) return;
      const nextControls = next.getElementById('cloud-controls');
      const nextResults = next.getElementById('cloud-results');
      if (!nextControls || !nextResults) throw new Error('Cloud catalogue content missing');
      const focus = document.activeElement;
      const focusId = focus?.id;
      const selection = focus?.id === 'cloud-query' ? [focus.selectionStart, focus.selectionEnd] : null;
      const chooserOpen = document.getElementById('cloud-services').open;
      const oldScroll = document.getElementById('cloud-table-scroll');
      const position = { left: oldScroll?.scrollLeft || 0, top: paging ? 0 : oldScroll?.scrollTop || 0 };
      document.getElementById('cloud-controls').replaceWith(nextControls);
      oldResults.replaceWith(nextResults);
      document.getElementById('cloud-services').open = chooserOpen;
      const nextScroll = document.getElementById('cloud-table-scroll');
      if (nextScroll) {
        nextScroll.scrollLeft = position.left;
        nextScroll.scrollTop = position.top;
      }
      const nextFocus = focusId ? document.getElementById(focusId) : null;
      nextFocus?.focus({ preventScroll: true });
      if (selection && nextFocus?.setSelectionRange && selection[0] !== null) {
        nextFocus.setSelectionRange(...selection);
      }
      document.title = next.title;
      const nextCanonical = next.querySelector('link[rel="canonical"]');
      const canonical = document.querySelector('link[rel="canonical"]');
      if (canonical && nextCanonical) canonical.href = nextCanonical.href;
      document.querySelector('meta[name="robots"]')?.remove();
      const nextRobots = next.querySelector('meta[name="robots"]');
      if (nextRobots) document.head.append(nextRobots);
      if (historyMode === 'push') history.pushState(null, '', url);
      else if (historyMode === 'replace') history.replaceState(null, '', url);
      enhance();
      announcement.textContent = nextResults.querySelector('.cloud-results-bar p')?.textContent || '筛选已更新';
      if (paging) nextResults.scrollIntoView({ block: 'start', behavior: 'instant' });
    } catch (error) {
      if (!controller.signal.aborted) location.assign(url);
    } finally {
      if (pending === controller) {
        document.getElementById('cloud-results').removeAttribute('aria-busy');
        pending = null;
      }
    }
  };
  const submit = mode => load(formURL(), mode);
  const schedule = () => {
    cancel();
    if (!composing) timer = setTimeout(() => submit('replace'), 250);
  };
  const showEvidence = async link => {
    evidencePending?.abort();
    const controller = new AbortController();
    evidencePending = controller;
    returnFocus = link;
    document.getElementById('cloud-dialog-title').textContent = link.dataset.title;
    const content = document.getElementById('cloud-dialog-content');
    content.textContent = '正在读取来源…';
    content.setAttribute('aria-busy', 'true');
    if (!dialog.open) dialog.showModal();
    try {
      const response = await fetch(link.href, { signal: controller.signal });
      if (!response.ok) throw new Error('Cloud evidence request failed');
      const next = new DOMParser().parseFromString(await response.text(), 'text/html');
      const evidence = next.getElementById('cloud-evidence-content');
      if (!evidence) throw new Error('Cloud evidence content missing');
      if (!controller.signal.aborted) {
        content.replaceChildren(evidence);
        document.getElementById('cloud-dialog-title').textContent = evidence.dataset.title || next.title;
      }
    } catch (error) {
      if (!controller.signal.aborted) location.assign(link.href);
    } finally {
      if (evidencePending === controller) {
        content.removeAttribute('aria-busy');
        evidencePending = null;
      }
    }
  };
  form.addEventListener('submit', event => { event.preventDefault(); submit('push'); });
  form.addEventListener('compositionstart', event => {
    if (event.target.id === 'cloud-query') { composing = true; cancel(); }
  });
  form.addEventListener('compositionend', event => {
    if (event.target.id === 'cloud-query') { composing = false; schedule(); }
  });
  form.addEventListener('input', event => { if (event.target.id === 'cloud-query') schedule(); });
  form.addEventListener('change', event => {
    if (event.target.matches('select, input[type="checkbox"]')) submit('push');
  });
  document.addEventListener('click', event => {
    const selectionButton = event.target.closest('[data-cloud-select]');
    if (selectionButton) {
      const checked = selectionButton.dataset.cloudSelect === 'all';
      form.querySelectorAll('input[name="service"]').forEach(input => { input.checked = checked; });
      submit('push');
      return;
    }
    const scrollButton = event.target.closest('[data-cloud-scroll]');
    if (scrollButton) {
      const scroller = document.getElementById('cloud-table-scroll');
      scroller?.scrollBy({ left: Number(scrollButton.dataset.cloudScroll) * scroller.clientWidth * .75, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
      return;
    }
    const evidenceLink = event.target.closest('[data-cloud-evidence]');
    if (evidenceLink && typeof dialog?.showModal === 'function' && event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) {
      event.preventDefault();
      showEvidence(evidenceLink);
      return;
    }
    if (event.target.closest('[data-cloud-close]')) { dialog.close(); return; }
    if (event.target === dialog) {
      const box = dialog.getBoundingClientRect();
      if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close();
      return;
    }
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest('[data-cloud-filter]');
    if (!link) return;
    const url = new URL(link.href);
    if (url.origin !== location.origin || url.pathname !== new URL(form.action).pathname) return;
    event.preventDefault();
    load(url.pathname + url.search, 'push', Boolean(link.closest('.cloud-pager')));
  });
  dialog?.addEventListener('close', () => { evidencePending?.abort(); returnFocus?.focus({ preventScroll: true }); });
  window.addEventListener('resize', scrollButtons, { passive: true });
  window.addEventListener('popstate', () => load(location.pathname + location.search, 'none'));
  enhance();
})();
