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

  // Shadow under the sticky header once the page has scrolled.
  if (header) {
    const onScroll = () => header.classList.toggle('pg-scrolled', window.scrollY > 4);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
  }
})();


/* Copy a script from an HTML element to the clipboard,
 * removing comments and blank lines.
 * Arguments:
 *   trigger: The button calling the function, whose icon will be updated
 *   elem: The element containing the script to copy
 *   stripSudo: If true, remove 'sudo ' from the start of lines
 */

function copyScript(trigger, elem, stripSudo = false) {
    const raw = document.getElementById(elem).innerHTML;

    // Create a scratch div to copy from
    const scratch = document.createElement("div");
    document.body.appendChild(scratch);

    // Copy the contents of the script box into the scratch div, removing
    // comments and blank lines, and optionally stripping sudo
    const lines = raw.split("\n");
    let output = '';
    for (let l = 0; l < lines.length; l++) {
        if (lines[l][0] != '#' && lines[l].trim() != '') {
            let line = lines[l];
            if (stripSudo) {
                line = line.replace(/^(\s*)sudo /, '$1');
            }
            output += line + '<br />';
        }
    }
    scratch.innerHTML = output.trim();

    // Perform the copy
    if(document.body.createTextRange) {
        // IE 11
        const range = document.body.createTextRange();
        range.moveToElementText(scratch);
        range.select();
        document.execCommand("Copy");
        document.getSelection().removeAllRanges()
    }
    else if(window.getSelection) {
        // Sane browsers
        const selection = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(scratch);
        selection.removeAllRanges();
        selection.addRange(range);
        document.execCommand("Copy");
        selection.removeAllRanges();
    }

    // Remove the scratch div
    scratch.parentNode.removeChild(scratch);

    // Indicate to the user that the script was copied
    const icon = trigger.querySelector('i');
    const originalClass = stripSudo ? 'fa-terminal' : 'fa-copy';
    icon.classList.remove(originalClass);
    icon.classList.add('fa-check');
    trigger.classList.add('copied');

    setTimeout(function() {
        icon.classList.remove('fa-check');
        icon.classList.add(originalClass);
        trigger.classList.remove('copied');
    }, 3000);
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
