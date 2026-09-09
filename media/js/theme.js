let theme = 'light';
if (localStorage.getItem('theme')) {
  if (localStorage.getItem('theme') === 'dark') {
    theme = 'dark';
    document.documentElement.setAttribute('data-theme', 'dark');
  }
} else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
  theme = 'dark';
  document.documentElement.setAttribute('data-theme', 'dark');
}
// The home-page notice bar is shown on every visit; closing it only hides
// it for the current page. Clear the flag older versions stored.
try { localStorage.removeItem('pgShout'); } catch (e) {}
