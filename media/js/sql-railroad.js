// Named productions work on command pages and dynamically replaced previews.
document.addEventListener('click', (event) => {
  const link = event.target.closest('.sql-railroad svg a');
  if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  const href = link.getAttribute('href');
  if (!href || !href.startsWith('#')) return;
  const root = link.closest('.sql-railroad');
  const target = Array.from(root.querySelectorAll('.sql-railroad__rule')).find(rule => '#' + rule.id === href);
  if (!target) return;
  event.preventDefault();
  if (target.tagName === 'DETAILS') target.open = true;
  target.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  target.querySelector('summary, .sql-railroad__scroll')?.focus({ preventScroll: true });
});
