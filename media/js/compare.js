/* Progressive enhancement: the server always renders the complete report. */
(() => {
  'use strict';
  const root = document.getElementById('pg-compare');
  if (!root) return;
  const query = document.getElementById('compare-query');
  const filters = Array.from(root.querySelectorAll('[data-category]'));
  const releases = Array.from(root.querySelectorAll('.compare-release'));
  const entries = Array.from(root.querySelectorAll('.compare-entry')).map(node => ({
    node,
    kind: node.dataset.kind,
    text: node.textContent.toLocaleLowerCase(),
  }));
  let category = 'all';
  let page = 1;
  let matchedEntries = entries;
  const pageSize = document.getElementById('compare-page-size');
  const params = new URL(window.location.href).searchParams;
  if (filters.some(button => button.dataset.category === params.get('kind'))) {
    category = params.get('kind');
  }
  if (query && params.has('q')) query.value = params.get('q').slice(0, 200);

  root.querySelectorAll('[data-version-select]').forEach(link => {
    const select = document.getElementById(link.dataset.versionSelect);
    if (!select) return;
    const update = () => { link.href = `/docs/compare/?release=${encodeURIComponent(select.value)}`; };
    select.addEventListener('change', update);
    update();
  });

  function shareURL() {
    const url = new URL(root.dataset.shareUrl || window.location.href, window.location.href);
    url.hash = window.location.hash;
    if (query && query.value.trim()) url.searchParams.set('q', query.value.trim());
    else url.searchParams.delete('q');
    if (category !== 'all') url.searchParams.set('kind', category);
    else url.searchParams.delete('kind');
    return url;
  }

  function filterEntries(updateURL = true, resetPage = true) {
    const terms = query ? query.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean) : [];
    matchedEntries = entries.filter(entry => (category === 'all' || entry.kind === category) && terms.every(term => entry.text.includes(term)));
    const count = matchedEntries.length;
    const size = pageSize && pageSize.value !== 'all' ? Number(pageSize.value) : Math.max(count, 1);
    const pages = Math.max(1, Math.ceil(count / size));
    page = resetPage ? 1 : Math.min(page, pages);
    const visibleEntries = new Set(matchedEntries.slice((page - 1) * size, page * size));
    entries.forEach(entry => { entry.node.hidden = !visibleEntries.has(entry); });
    releases.forEach(release => {
      // A release with upgrade notes but no changes still has useful content.
      release.hidden = !release.querySelector('.compare-entry:not([hidden])') &&
        (category !== 'all' || terms.length > 0 || page !== 1 || release.querySelector('.compare-entry') || !release.querySelector('.compare-migration'));
    });
    filters.forEach(button => {
      const active = button.dataset.category === category;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    const status = document.getElementById('compare-filter-status');
    if (status) status.textContent = `匹配 ${count.toLocaleString()} / ${entries.length.toLocaleString()} 项变更${count ? ` · 当前显示 ${(page - 1) * size + 1}–${Math.min(page * size, count)} 项` : ''}`;
    if (pageSize) {
      document.getElementById('compare-page-status').textContent = `${page} / ${pages}`;
      document.getElementById('compare-prev').disabled = page === 1;
      document.getElementById('compare-next').disabled = page === pages;
    }
    const empty = document.getElementById('compare-no-matches');
    if (empty) empty.hidden = count !== 0 || entries.length === 0;
    if (updateURL) window.history.replaceState(null, '', shareURL());
  }

  if (query) {
    document.getElementById('compare-tools').hidden = false;
    query.addEventListener('input', () => filterEntries());
    filters.forEach(button => button.addEventListener('click', () => {
      category = button.dataset.category;
      filterEntries();
    }));
    document.getElementById('compare-reset').addEventListener('click', () => {
      category = 'all';
      query.value = '';
      filterEntries();
      query.focus();
    });
    document.getElementById('compare-expand').addEventListener('click', () => {
      root.querySelectorAll('.compare-entry:not([hidden]), .compare-release:not([hidden]) .compare-migration').forEach(node => { node.open = true; });
    });
    document.getElementById('compare-collapse').addEventListener('click', () => {
      root.querySelectorAll('.compare-entry:not([hidden]), .compare-release:not([hidden]) .compare-migration').forEach(node => { node.open = false; });
    });
    pageSize.addEventListener('change', () => filterEntries());
    document.getElementById('compare-prev').addEventListener('click', () => {
      page -= 1;
      filterEntries(false, false);
      document.getElementById('compare-tools').scrollIntoView({ block: 'start' });
    });
    document.getElementById('compare-next').addEventListener('click', () => {
      page += 1;
      filterEntries(false, false);
      document.getElementById('compare-tools').scrollIntoView({ block: 'start' });
    });
    filterEntries(false);
  }

  const paste = document.getElementById('compare-paste');
  if (paste) {
    paste.hidden = false;
    const input = document.getElementById('compare-version-text');
    const detect = () => {
      const text = input.value.trim();
      const match = text.match(/(?:PostgreSQL\s+|^)(\d{1,2}(?:\.\d+){0,2}(?:(?:beta|rc)\d+|devel)?)(?:\s|$|,)/i);
      const status = document.getElementById('compare-detect-status');
      if (!match) {
        status.textContent = '未识别到 PostgreSQL 版本号，请粘贴 SELECT version(); 的结果或输入版本号。';
        return;
      }
      const rawVersion = match[1].toLowerCase();
      const value = /^\d+$/.test(rawVersion) || /^9\.[0-6]$/.test(rawVersion) ? `${rawVersion}.0` : rawVersion;
      const source = document.getElementById('compare-from');
      const option = Array.from(source.options).find(item => {
        const label = item.label.toLowerCase();
        return item.value.toLowerCase() === value ||
          (label.startsWith(value) && /[\s（(]/.test(label.charAt(value.length) || ' '));
      });
      if (!option) {
        status.textContent = `已识别 PostgreSQL ${match[1]}，当前数据尚未收录此版本。`;
        return;
      }
      source.value = option.value;
      source.dispatchEvent(new Event('change'));
      status.textContent = `已将起始版本设为 PostgreSQL ${option.label}。选择目标版本后，点击“对比版本”。`;
    };
    document.getElementById('compare-detect').addEventListener('click', detect);
    input.addEventListener('keydown', event => {
      if (event.key === 'Enter') { event.preventDefault(); detect(); }
    });
  }

  const share = document.getElementById('compare-share');
  if (share) {
    share.hidden = false;
    share.addEventListener('click', async () => {
      const url = shareURL().href;
      const status = document.getElementById('compare-share-status');
      const fallback = document.getElementById('compare-share-fallback');
      try {
        await navigator.clipboard.writeText(url);
        status.textContent = '分享链接已复制，包含当前版本与筛选条件。';
        fallback.hidden = true;
      } catch (_error) {
        fallback.value = url;
        fallback.hidden = false;
        fallback.focus();
        fallback.select();
        status.textContent = '请复制下方已选中的分享链接。';
      }
      status.hidden = false;
    });
  }

  function openPermalink() {
    if (!window.location.hash) return;
    let id;
    try { id = decodeURIComponent(window.location.hash.slice(1)); } catch (_error) { return; }
    const target = document.getElementById(id);
    if (!target || !target.classList.contains('compare-entry')) return;
    if (!matchedEntries.some(entry => entry.node === target) && query) {
      query.value = '';
      category = 'all';
      filterEntries();
    }
    if (pageSize && pageSize.value !== 'all') {
      page = Math.floor(matchedEntries.findIndex(entry => entry.node === target) / Number(pageSize.value)) + 1;
      filterEntries(false, false);
    }
    target.open = true;
    target.scrollIntoView({ block: 'start' });
  }
  window.addEventListener('hashchange', openPermalink);
  openPermalink();
})();
