/*
 * pg.center site chrome
 * ---------------------------------------------------------------------
 * Header drawer, search shortcut, scrolled-header shadow and the light/dark
 * theme switch. `theme` is declared by theme.js, which runs in <head> so the
 * first paint already carries the stored preference.
 */

(function () {
  'use strict';

  const header = document.getElementById('pgHeader');
  const drawer = document.getElementById('pgDrawer');
  const drawerToggles = document.querySelectorAll('[data-pg-drawer-toggle]');
  const searchOpeners = document.querySelectorAll('[data-pg-search-open]');
  const drawerSearch = drawer ? drawer.querySelector('[data-pg-drawer-search]') : null;
  const headerSearch = document.querySelector('.pg-nav__search input');

  function drawerIsOpen() {
    return drawer && !drawer.hidden;
  }

  function setDrawer(open) {
    if (!drawer) return;
    drawer.hidden = !open;
    document.body.classList.toggle('pg-drawer-open', open);
    drawerToggles.forEach((b) => b.setAttribute('aria-expanded', open ? 'true' : 'false'));
    searchOpeners.forEach((b) => b.setAttribute('aria-expanded', open ? 'true' : 'false'));
  }

  drawerToggles.forEach((btn) => {
    btn.addEventListener('click', () => setDrawer(!drawerIsOpen()));
  });

  searchOpeners.forEach((btn) => {
    btn.addEventListener('click', () => {
      setDrawer(true);
      if (drawerSearch) drawerSearch.focus();
    });
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && drawerIsOpen()) {
      setDrawer(false);
      return;
    }
    if (document.getElementById('doc-search')) return;
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      const version = location.pathname.match(/^\/docs\/(\d+)\//);
      location.assign('/search/' + (version ? '?scope=pg' + version[1] : ''));
      return;
    }
    // "/" focuses the site search unless the reader is already typing.
    if (e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const t = e.target;
      const typing = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable);
      if (typing) return;
      const visible = headerSearch && headerSearch.offsetParent !== null;
      if (visible) {
        headerSearch.focus();
        e.preventDefault();
      } else if (drawer && drawerSearch) {
        setDrawer(true);
        drawerSearch.focus();
        e.preventDefault();
      }
    }
  });

  // Close the drawer when the viewport grows back into the desktop tiers.
  window.addEventListener('resize', () => {
    if (drawerIsOpen() && window.innerWidth >= 992) setDrawer(false);
  });

  // Notice bar: the close control hides it and remembers the choice.
  document.querySelectorAll('[data-pg-shout-close]').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.documentElement.setAttribute('data-shout', 'off');
      try { localStorage.setItem('pgShout', 'off'); } catch (e) {}
    });
  });

  // Shadow under the sticky header once the page has scrolled.
  if (header) {
    const onScroll = () => header.classList.toggle('pg-scrolled', window.scrollY > 4);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
  }
})();


/*
 * Testimonial carousel (the about page). Bootstrap's JS is not loaded,
 * so this drives the markup: previous/next buttons, indicator dots,
 * keyboard arrows, and a slow auto-advance that pauses while hovered
 * or focused.
 */
document.querySelectorAll('[data-pg-carousel]').forEach((root) => {
  const items = Array.from(root.querySelectorAll('.carousel-item'));
  const dots = Array.from(root.querySelectorAll('[data-pg-slide-to]'));
  if (items.length < 2) return;
  const interval = parseInt(root.dataset.interval, 10) || 9000;
  let index = Math.max(0, items.findIndex((el) => el.classList.contains('active')));
  let timer = null;

  function show(next) {
    index = (next + items.length) % items.length;
    items.forEach((el, i) => el.classList.toggle('active', i === index));
    dots.forEach((el, i) => {
      el.classList.toggle('active', i === index);
      el.setAttribute('aria-current', i === index ? 'true' : 'false');
    });
  }

  function play() {
    stop();
    timer = setInterval(() => show(index + 1), interval);
  }

  function stop() {
    if (timer) clearInterval(timer);
    timer = null;
  }

  root.querySelectorAll('[data-pg-slide]').forEach((btn) => {
    btn.addEventListener('click', () => {
      show(index + (btn.dataset.pgSlide === 'prev' ? -1 : 1));
      play();
    });
  });
  dots.forEach((dot) => {
    const go = () => { show(parseInt(dot.dataset.pgSlideTo, 10)); play(); };
    dot.addEventListener('click', go);
    dot.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); }
    });
  });
  root.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft') { show(index - 1); play(); }
    if (e.key === 'ArrowRight') { show(index + 1); play(); }
  });
  root.addEventListener('mouseenter', stop);
  root.addEventListener('mouseleave', play);
  root.addEventListener('focusin', stop);
  root.addEventListener('focusout', play);
  document.addEventListener('visibilitychange', () => (document.hidden ? stop() : play()));

  show(index);
  play();
});


/* Copy a script from an HTML element to the clipboard,
 * removing comments and blank lines.
 * Arguments:
 *   trigger: The button calling the function, whose icon will be updated
 *   elem: The element containing the script to copy
 *   stripSudo: If true, remove 'sudo ' from the start of lines
 */

function copyScript(trigger, elem, stripSudo = false) {
    // Plain text of the block (highlighting wraps tokens in spans, so
    // innerHTML is no longer the script itself).
    const raw = document.getElementById(elem).textContent;
    const lines = [];
    raw.split("\n").forEach((line) => {
        if (line.trim() === '' || line.trim()[0] === '#') return;
        lines.push(stripSudo ? line.replace(/^(\s*)sudo /, '$1') : line);
    });
    const text = lines.join("\n");
    const done = (ok) => {
        if (window.pgFlashButton) {
            window.pgFlashButton(trigger, ok);
        } else {
            trigger.classList.toggle('copied', ok);
            setTimeout(() => trigger.classList.remove('copied'), 2000);
        }
    };
    const copier = window.pgCopyText || ((t) => navigator.clipboard.writeText(t));
    copier(text).then(() => done(true), () => done(false));
}


/*
 * showDistros shows / hides the individual distributions of particular OS
 * families on the Download page
 */
function showDistros(btn, osDiv) {
    // Disable everything
    document.getElementById('btn-download-bsd').classList.remove("btn-download-active");;
    document.getElementById('download-subnav-bsd').style.display = 'none';
    document.getElementById('btn-download-linux').classList.remove("btn-download-active");
    document.getElementById('download-subnav-linux').style.display = 'none';

    // Enable the one we want
    btn.classList.add("btn-download-active");
    document.getElementById(osDiv).style.display = 'block';
}


/*
 * Register a confirm handler for forms that, well, requires confirmation
 * for someting.
 */
document.querySelectorAll('button[data-confirm]').forEach((button) => {
    button.addEventListener('click', (event) => {
        if (confirm(event.target.dataset.confirm)) {
            return true;
        }
        event.preventDefault();
        return false;
    });
});


/*
 * Theme switching. The buttons carry both a moon and a sun glyph; the
 * stylesheet shows the one that matches the current theme.
 */
function theme_apply() {
  'use strict';
  if (theme === 'light') {
    document.documentElement.setAttribute('data-theme', 'light');
    localStorage.setItem('theme', 'light');
  } else {
    document.documentElement.setAttribute('data-theme', 'dark');
    localStorage.setItem('theme', 'dark');
  }
  document.querySelectorAll('[data-pg-theme-toggle]').forEach((btn) => {
    btn.setAttribute('aria-pressed', theme === 'dark' ? 'true' : 'false');
  });
}

theme_apply();

function theme_switch() {
  'use strict';
  if (theme === 'light') {
    theme = 'dark';
  } else {
    theme = 'light';
  }
  theme_apply();
}

let theme_OS = window.matchMedia('(prefers-color-scheme: light)');
theme_OS.addEventListener('change', function (e) {
  'use strict';
  if (e.matches) {
    theme = 'light';
  } else {
    theme = 'dark';
  }
  theme_apply();
});

document.querySelectorAll('[data-pg-theme-toggle]').forEach((btn) => {
  btn.addEventListener('click', theme_switch);
});
