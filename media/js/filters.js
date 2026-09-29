/* Shared GET filters. Changing a selection applies it; typing waits for a
 * short pause. The ordinary submit button remains usable without JavaScript. */
(function () {
  'use strict';
  document.querySelectorAll('form[data-autosubmit]').forEach(function (form) {
    let timer = null;
    let composing = false;
    function prepare() {
      window.clearTimeout(timer);
      const target = form.querySelector('[data-compare-target]');
      if (target) form.action = target.selectedOptions[0].dataset.url;
    }
    function submit() {
      prepare();
      if (composing) return;
      if (form.requestSubmit) form.requestSubmit();
      else form.submit();
    }
    function schedule() {
      window.clearTimeout(timer);
      if (!composing) timer = window.setTimeout(submit, 350);
    }
    form.addEventListener('submit', prepare);
    form.addEventListener('formdata', function (event) {
      const target = form.querySelector('[data-compare-target]');
      if (target) event.formData.delete(target.name);
      for (const [name, value] of Array.from(event.formData.entries())) {
        if (value === '') event.formData.delete(name);
      }
    });
    form.querySelectorAll('select').forEach(function (field) {
      field.addEventListener('change', submit);
    });
    form.querySelectorAll('input[type="search"], input[type="text"]').forEach(function (field) {
      field.addEventListener('compositionstart', function () {
        composing = true;
        window.clearTimeout(timer);
      });
      field.addEventListener('compositionend', function () {
        composing = false;
        schedule();
      });
      field.addEventListener('input', schedule);
      field.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' && !event.isComposing && !composing) {
          event.preventDefault();
          submit();
        }
      });
    });
    form.querySelectorAll('[data-autosubmit-fallback]').forEach(function (button) {
      button.hidden = true;
    });
    // History restores the previous results and URL. Browsers may also keep
    // the selection that submitted the next page; reset it to this page's
    // server-rendered defaults so the controls describe the visible results.
    window.addEventListener('pagehide', function () { window.clearTimeout(timer); });
    window.addEventListener('pageshow', function (event) {
      const navigation = window.performance.getEntriesByType('navigation')[0];
      if (event.persisted || (navigation && navigation.type === 'back_forward')) {
        composing = false;
        form.reset();
      }
    });
  });
})();
