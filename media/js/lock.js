/* Progressive enhancement for the lock encyclopedia; no inline code or style. */
(() => {
  'use strict';
  const root = document.getElementById('locks');
  if (!root) return;
  root.classList.add('is-enhanced');

  const version = root.querySelector('[data-lock-version]');
  if (version) version.addEventListener('change', () => {
    const option = version.selectedOptions[0];
    if (option && option.dataset.url) window.location.assign(option.dataset.url);
    else version.form.submit();
  });

  root.querySelectorAll('[data-lock-matrix]').forEach(matrix => {
    const buttons = Array.from(matrix.querySelectorAll('[data-lock-cell]'));
    const width = matrix.querySelectorAll('thead [data-lock-column]').length;
    const readout = matrix.querySelector('[data-lock-readout]');
    let selected = null;

    function highlight(button, announce) {
      const cell = button.closest('td');
      const row = cell.dataset.lockRowSlug;
      const column = cell.dataset.lockColSlug;
      matrix.querySelectorAll('[data-lock-row-slug]').forEach(item => {
        item.classList.toggle('is-axis', item.dataset.lockRowSlug === row || item.dataset.lockColSlug === column);
        item.classList.toggle('is-active', item === cell);
      });
      matrix.querySelectorAll('[data-lock-column]').forEach(item => {
        item.classList.toggle('is-axis', item.dataset.lockColumn === column);
      });
      matrix.querySelectorAll('[data-lock-row]').forEach(item => {
        item.classList.toggle('is-axis', item.dataset.lockRow === row);
      });
      if (announce && readout) readout.textContent = button.dataset.lockLabel;
    }

    function select(button) {
      selected = button;
      buttons.forEach(item => { item.tabIndex = item === button ? 0 : -1; });
      highlight(button, true);
    }

    buttons.forEach((button, index) => {
      button.addEventListener('focus', () => select(button));
      button.addEventListener('click', () => select(button));
      button.addEventListener('pointerenter', () => highlight(button, true));
      button.addEventListener('keydown', event => {
        const row = Math.floor(index / width);
        const column = index % width;
        let target = index;
        if (event.key === 'ArrowRight') target = row * width + Math.min(width - 1, column + 1);
        else if (event.key === 'ArrowLeft') target = row * width + Math.max(0, column - 1);
        else if (event.key === 'ArrowDown') target = Math.min(buttons.length - width + column, index + width);
        else if (event.key === 'ArrowUp') target = Math.max(column, index - width);
        else if (event.key === 'Home') target = event.ctrlKey ? 0 : row * width;
        else if (event.key === 'End') target = event.ctrlKey ? buttons.length - 1 : row * width + width - 1;
        else return;
        event.preventDefault();
        buttons[target].focus();
      });
    });
    matrix.addEventListener('pointerleave', () => {
      if (selected) highlight(selected, true);
      else matrix.querySelectorAll('.is-axis, .is-active').forEach(item => item.classList.remove('is-axis', 'is-active'));
    });
  });

  const commandChoice = root.querySelector('[data-lock-command-choice]');
  const commandRows = Array.from(root.querySelectorAll('[data-lock-command-row]'));
  if (commandChoice) {
    root.querySelector('[data-lock-explorer]').hidden = false;
    const note = root.querySelector('[data-lock-selection]');
    const defaultNote = note.textContent;
    function selectCommand() {
      const option = commandChoice.selectedOptions[0];
      const slugs = new Set((option.dataset.lockModes || '').trim().split(/\s+/).filter(Boolean));
      root.querySelectorAll('[data-lock-mode]').forEach(item => {
        item.classList.toggle('is-associated', slugs.has(item.dataset.lockMode));
      });
      root.querySelectorAll('[data-lock-column], [data-lock-row]').forEach(item => {
        const axisModes = (item.dataset.lockModeSlugs || item.dataset.lockColumn || item.dataset.lockRow).trim().split(/\s+/).filter(Boolean);
        item.classList.toggle('is-associated', axisModes.length > 0 && axisModes.every(slug => slugs.has(slug)));
      });
      commandRows.forEach(row => row.classList.toggle('is-selected', row.dataset.lockChoiceKey === commandChoice.value && Boolean(commandChoice.value)));
      note.textContent = commandChoice.value ? `${option.dataset.lockCommandLabel}：${option.dataset.note}` : defaultNote;
    }
    commandChoice.addEventListener('change', selectCommand);
    root.querySelector('[data-lock-clear]').addEventListener('click', () => {
      commandChoice.value = '';
      selectCommand();
      commandChoice.focus();
    });
    root.querySelectorAll('[data-lock-show-command]').forEach(button => {
      button.hidden = false;
      button.addEventListener('click', () => {
        commandChoice.value = button.dataset.lockShowCommand;
        selectCommand();
        commandChoice.focus({preventScroll: true});
        root.querySelector('[data-lock-explorer]').scrollIntoView({block: 'start'});
      });
    });
  }

  const search = root.querySelector('[data-lock-search]');
  if (search) {
    root.querySelector('[data-lock-filter-wrap]').hidden = false;
    const count = root.querySelector('[data-lock-count]');
    const empty = root.querySelector('[data-lock-empty]');
    const texts = commandRows.map(row => row.dataset.lockSearchText.toLocaleLowerCase());
    function filterCommands() {
      const terms = search.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
      let visible = 0;
      commandRows.forEach((row, index) => {
        row.hidden = !terms.every(term => texts[index].includes(term));
        if (!row.hidden) visible += 1;
      });
      count.textContent = terms.length ? `匹配 ${visible} / ${commandRows.length} 条命令及变体` : `共 ${commandRows.length} 条命令及变体`;
      empty.hidden = visible !== 0;
    }
    search.addEventListener('input', filterCommands);
    search.addEventListener('keydown', event => {
      if (event.key === 'Escape') {
        search.value = '';
        filterCommands();
      }
    });
  }
})();
