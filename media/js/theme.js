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
// The home-page notice bar stays hidden once the reader has closed it.
try {
  if (localStorage.getItem('pgShout') === 'off') {
    document.documentElement.setAttribute('data-shout', 'off');
  }
} catch (e) {}
