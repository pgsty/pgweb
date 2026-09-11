/* 错误码索引页的即时筛选。表格只有两百多行，整页渲染后在前端过滤即可。 */
(function () {
  'use strict';

  var form = document.getElementById('errcode-search');
  var table = document.getElementById('errcode-table');
  if (!form || !table) { return; }

  var query = document.getElementById('errcode-q');
  var count = document.getElementById('errcode-count');
  var empty = document.getElementById('errcode-empty');
  var selects = Array.prototype.slice.call(form.querySelectorAll('[data-errcode-filter]'));
  var groups = Array.prototype.slice.call(table.querySelectorAll('.wiki-classgroup'));
  var rows = Array.prototype.slice.call(table.querySelectorAll('.wiki-coderow'));
  // 每个错误码占两行（第二行是说明），计数只算第一行。
  var total = rows.filter(function (row) { return !row.classList.contains('wiki-coderow--more'); }).length;

  function state() {
    var picked = {};
    selects.forEach(function (select) {
      if (select.value) { picked[select.getAttribute('data-errcode-filter')] = select.value; }
    });
    return { q: (query.value || '').trim().toLowerCase(), picked: picked };
  }

  function matches(row, current) {
    for (var key in current.picked) {
      if (row.getAttribute('data-' + key) !== current.picked[key]) { return false; }
    }
    if (!current.q) { return true; }
    return row.getAttribute('data-text').toLowerCase().indexOf(current.q) !== -1;
  }

  function apply() {
    var current = state();
    var shown = 0;
    rows.forEach(function (row) {
      var ok = matches(row, current);
      row.hidden = !ok;
      if (ok && !row.classList.contains('wiki-coderow--more')) { shown += 1; }
    });
    // 整类都被过滤掉时，连它的标题行一起收起来。
    groups.forEach(function (group) {
      var visible = group.querySelector('.wiki-coderow:not([hidden])');
      group.hidden = !visible;
    });
    var filtered = shown !== total;
    count.hidden = !filtered;
    count.textContent = '匹配 ' + shown + ' / ' + total + ' 个错误码';
    empty.hidden = shown !== 0;
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
      var value = params.get(select.getAttribute('data-errcode-filter'));
      if (value) { select.value = value; }
    });
  }

  form.addEventListener('submit', function (event) { event.preventDefault(); apply(); });
  query.addEventListener('input', apply);
  selects.forEach(function (select) { select.addEventListener('change', apply); });

  readUrl();
  apply();
}());
