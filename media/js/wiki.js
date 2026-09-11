/* 百科索引页的即时筛选。表格只有几百行，整页渲染后在前端过滤即可。 */
(function () {
  'use strict';

  // 整行可点：点在链接上走链接，点在别处也跳到该条记录。
  // 错误码的表按类名认，系统目录的表标了 data-rowlink，后面新增栏目用后者即可。
  document.querySelectorAll('table.wiki-errcodes, table[data-rowlink]').forEach(function (node) {
    node.addEventListener('click', function (event) {
      if (event.target.closest('a')) { return; }
      var row = event.target.closest('tr[data-href]');
      if (row) { window.location.href = row.getAttribute('data-href'); }
    });
  });

  /* 索引页筛选。两个栏目共用一套逻辑，差别都在 opts 里：
     prefix   表单、输入框、表格、计数与空状态的 id 前缀，也是下拉的 data 属性名
     group    一组（类别）的选择器，整组被过滤空时连标题行一起收起
     sub      可选，组内子分类分隔行的选择器，本子分类被过滤空时这行也收起
     row      记录行的选择器
     more     第二行（说明行）的类名
     noun     计数文案里的量词
     tokens   取值是空格分隔的多值属性，按「包含」而不是「相等」匹配

     一条记录占两行。筛选条件只读第一行的 data 属性，第二行跟着第一行一起显隐，
     省掉整整一份重复的 data-text —— 索引页有一百多条记录，这份重复不小。 */
  function wireFilter(opts) {
    var form = document.getElementById(opts.prefix + '-search');
    var table = document.getElementById(opts.prefix + '-table');
    if (!form || !table) { return; }

    var attribute = 'data-' + opts.prefix + '-filter';
    var query = document.getElementById(opts.prefix + '-q');
    var count = document.getElementById(opts.prefix + '-count');
    var empty = document.getElementById(opts.prefix + '-empty');
    var selects = Array.prototype.slice.call(form.querySelectorAll('[' + attribute + ']'));
    var groups = Array.prototype.slice.call(table.querySelectorAll(opts.group));
    var rows = Array.prototype.slice.call(
      table.querySelectorAll(opts.row + ':not(.' + opts.more + ')'));
    var tokens = opts.tokens || [];
    var total = rows.length;

    function companion(row) {
      var next = row.nextElementSibling;
      return next && next.classList.contains(opts.more) ? next : null;
    }

    function state() {
      var picked = {};
      selects.forEach(function (select) {
        if (select.value) { picked[select.getAttribute(attribute)] = select.value; }
      });
      return { q: (query.value || '').trim().toLowerCase(), picked: picked };
    }

    function matches(row, current) {
      for (var key in current.picked) {
        var value = row.getAttribute('data-' + key) || '';
        if (tokens.indexOf(key) !== -1) {
          if (value.split(/\s+/).indexOf(current.picked[key]) === -1) { return false; }
        } else if (value !== current.picked[key]) {
          return false;
        }
      }
      if (!current.q) { return true; }
      return (row.getAttribute('data-text') || '').toLowerCase().indexOf(current.q) !== -1;
    }

    function apply() {
      var current = state();
      var shown = 0;
      rows.forEach(function (row) {
        var ok = matches(row, current);
        var mate = companion(row);
        row.hidden = !ok;
        if (mate) { mate.hidden = !ok; }
        if (ok) { shown += 1; }
      });
      // 一个子分类下没有可见记录时，连它的分隔行一起收起来。分隔行管到下一条分隔行
      // 或者本组结尾为止（同组的行都在一个 tbody 里，nextElementSibling 到头自然是 null）。
      if (opts.sub) {
        Array.prototype.slice.call(table.querySelectorAll(opts.sub)).forEach(function (mark) {
          var node = mark.nextElementSibling;
          var visible = false;
          while (node && !node.matches(opts.sub)) {
            if (node.matches(opts.row) && !node.hidden) { visible = true; break; }
            node = node.nextElementSibling;
          }
          mark.hidden = !visible;
        });
      }
      // 整组都被过滤掉时，连它的标题行一起收起来。
      groups.forEach(function (group) {
        group.hidden = !group.querySelector(opts.row + ':not([hidden])');
      });
      var filtered = shown !== total;
      if (count) {
        count.hidden = !filtered;
        count.textContent = '匹配 ' + shown + ' / ' + total + ' ' + opts.noun;
      }
      if (empty) { empty.hidden = shown !== 0; }
      writeUrl(current);
    }

    function writeUrl(current) {
      if (!window.history || !window.history.replaceState) { return; }
      var params = new URLSearchParams();
      if (current.q) { params.set('q', current.q); }
      for (var key in current.picked) { params.set(key, current.picked[key]); }
      var search = params.toString();
      window.history.replaceState(null, '', search ? '?' + search : window.location.pathname);
    }

    function readUrl() {
      var params = new URLSearchParams(window.location.search);
      if (params.get('q')) { query.value = params.get('q'); }
      selects.forEach(function (select) {
        var value = params.get(select.getAttribute(attribute));
        if (value) { select.value = value; }
      });
    }

    form.addEventListener('submit', function (event) { event.preventDefault(); apply(); });
    query.addEventListener('input', apply);
    selects.forEach(function (select) { select.addEventListener('change', apply); });

    readUrl();
    apply();
  }

  wireFilter({
    prefix: 'errcode', group: '.wiki-classgroup', row: '.wiki-coderow',
    more: 'wiki-coderow--more', noun: '个错误码',
  });

  wireFilter({
    prefix: 'catalog', group: '.cat-group', row: '.cat-row',
    more: 'cat-row--more', noun: '个关系', tokens: ['present'],
  });

  wireFilter({
    prefix: 'guc', group: '.guc-group', sub: '.guc-subrow', row: '.guc-row',
    more: 'guc-row--more', noun: '个参数', tokens: ['present'],
  });

  wireFilter({
    prefix: 'waitevent', group: '.we-group', row: '.we-row',
    more: 'we-row--more', noun: '个等待事件', tokens: ['present'],
  });

  /* 代码块的复制按钮：data-copy-target 指向 <pre> 的 id。
     clipboard 只在安全上下文里有，不可用或被拒时只改按钮文案，不弹窗。 */
  document.querySelectorAll('[data-copy-target]').forEach(function (button) {
    var original = button.textContent;
    var timer = null;

    function settle(ok) {
      button.textContent = ok ? '已复制' : '复制失败';
      button.classList.toggle('is-done', ok);
      button.classList.toggle('is-failed', !ok);
      if (timer) { window.clearTimeout(timer); }
      timer = window.setTimeout(function () {
        button.textContent = original;
        button.classList.remove('is-done');
        button.classList.remove('is-failed');
      }, 1500);
    }

    button.addEventListener('click', function () {
      var target = document.getElementById(button.getAttribute('data-copy-target'));
      if (!target) { return; }
      if (!navigator.clipboard || !navigator.clipboard.writeText) { settle(false); return; }
      navigator.clipboard.writeText(target.textContent).then(
        function () { settle(true); },
        function () { settle(false); }
      );
    });
  });
}());
