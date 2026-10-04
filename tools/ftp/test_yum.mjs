import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const template = readFileSync(new URL('../../templates/downloads/js/yum.js', import.meta.url), 'utf8');
const platforms = {
  'EL-6': [{ arch: 'x86_64', versions: ['9.6'] }],
  'EL-7': [{ arch: 'x86_64', versions: ['15', '14', '13', '12'] }],
  'EL-8': [{ arch: 'x86_64', versions: ['14', '18', '17'] }, { arch: 'i386', versions: ['9.6'] }],
  'EL-9': [{ arch: 'x86_64', versions: ['18'] }, { arch: 'aarch64', versions: ['18'] }],
  'EL-9.8': [{ arch: 'x86_64', versions: ['18'] }],
  'EL-10': [{ arch: 'x86_64', versions: ['18'] }],
  'F-43': [{ arch: 'x86_64', versions: ['18'] }],
  'F-44': [{ arch: 'x86_64', versions: ['18'] }],
  'AL-2023': [{ arch: 'x86_64', versions: ['17', '18'] }, { arch: 'aarch64', versions: ['18'] }],
  'UNKNOWN-1': [{ arch: 'x86_64', versions: ['18'] }],
};

function chooser(data = platforms) {
  const boxes = {};
  const copied = [];
  for (const id of ['distribution', 'platform', 'arch', 'version', 'script-box', 'copy-btn', 'copy-btn-root']) {
    const classes = new Set();
    const box = boxes[id] = {
      options: [],
      selected: null,
      events: {},
      disabled: false,
      textContent: '',
      classList: { add: name => classes.add(name), remove: name => classes.delete(name), contains: name => classes.has(name) },
      get value() { return this.selected ?? this.options[0]?.value ?? ''; },
      set value(value) { this.selected = value; },
      set innerHTML(value) { throw new Error('Repository values must never be inserted as HTML'); },
      add(option) { this.options.push(option); },
      addEventListener(name, handler) { this.events[name] = handler; },
    };
    box.options.remove = function (index) {
      if (this[index]?.value === box.selected) box.selected = null;
      this.splice(index, 1);
    };
  }
  let ready;
  vm.runInNewContext(template.replace('{{json|safe}}', JSON.stringify({ platforms: data }))
    .replace('{{supported_versions}}', '14,15,16,17,18'), {
    document: {
      getElementById: id => boxes[id],
      createElement: () => ({}),
      addEventListener: (name, handler) => { ready = handler; },
    },
    copyScript: (...args) => copied.push(args),
  });
  ready();
  return {
    boxes,
    copied,
    values: id => boxes[id].options.map(option => option.value),
    select(id, value) {
      assert(boxes[id].options.some(option => option.value === value), `${id} does not offer ${value}`);
      boxes[id].value = value;
      boxes[id].events.change();
    },
  };
}

test('dependent selections and copy buttons start unavailable', () => {
  const ui = chooser();
  for (const id of ['platform', 'arch', 'version']) assert.equal(ui.boxes[id].disabled, true);
  for (const id of ['copy-btn', 'copy-btn-root']) assert(ui.boxes[id].classList.contains('d-none'));
  assert.deepEqual(ui.values('distribution'), ['-1', 'EL', 'F', 'AL']);
});

for (const arch of ['x86_64', 'aarch64']) {
  test(`Amazon Linux 2023 generates the correct RPM and dnf commands for ${arch}`, () => {
    const ui = chooser();
    ui.select('distribution', 'AL');
    assert.equal(ui.boxes.platform.value, 'AL-2023');
    ui.select('arch', arch);
    ui.select('version', '18');
    const script = ui.boxes['script-box'].textContent;
    assert(script.includes(`sudo dnf install -y https://download.postgresql.org/pub/repos/yum/reporpms/AL-2023-${arch}/pgdg-amazonlinux-repo-latest.noarch.rpm`));
    assert(script.includes('sudo dnf install -y postgresql18-server'));
    assert(script.includes('/usr/pgsql-18/bin/postgresql-18-setup initdb'));
    assert(!script.includes('module disable'));
  });
}

test('EL8 keeps supported-architecture filtering, numeric ordering and module disabling', () => {
  const ui = chooser();
  ui.select('distribution', 'EL');
  assert.deepEqual(ui.values('platform'), ['-1', 'EL-10', 'EL-9', 'EL-8', 'EL-7']);
  ui.select('platform', 'EL-8');
  assert.deepEqual(ui.values('arch'), ['x86_64']);
  assert.deepEqual(ui.values('version'), ['-1', '18', '17', '14']);
  ui.select('version', '18');
  assert(ui.boxes['script-box'].textContent.includes('sudo dnf -qy module disable postgresql'));
  assert(ui.boxes['script-box'].textContent.includes('/EL-8-x86_64/pgdg-redhat-repo-latest.noarch.rpm'));
});

test('EL9 ARM64 and EL10 use the major repository without a misleading minor pin', () => {
  const ui = chooser();
  ui.select('distribution', 'EL');
  assert(!ui.values('platform').includes('EL-9.8'));
  ui.select('platform', 'EL-9');
  ui.select('arch', 'aarch64');
  ui.select('version', '18');
  assert(ui.boxes['script-box'].textContent.includes('/EL-9-aarch64/pgdg-redhat-repo-latest.noarch.rpm'));
  assert(!ui.boxes['script-box'].textContent.includes('module disable'));
  ui.select('platform', 'EL-10');
  ui.select('version', '18');
  assert(ui.boxes['script-box'].textContent.includes('/EL-10-x86_64/pgdg-redhat-repo-latest.noarch.rpm'));
});

test('retained RHEL7 PostgreSQL packages remain available without implying Rocky or AlmaLinux 7 exists', () => {
  const ui = chooser();
  ui.select('distribution', 'EL');
  assert.equal(ui.boxes.platform.options.find(option => option.value === 'EL-7').text, '7（RHEL）');
  ui.select('platform', 'EL-7');
  assert.deepEqual(ui.values('version'), ['-1', '15', '14']);
  ui.select('version', '15');
  assert(ui.boxes['script-box'].textContent.includes('sudo yum install -y postgresql15-server'));
  assert(!ui.boxes['script-box'].textContent.includes('module disable'));
});

test('changing distribution clears old commands and resets dependent selections', () => {
  const ui = chooser();
  ui.select('distribution', 'EL');
  ui.select('platform', 'EL-10');
  ui.select('version', '18');
  assert(!ui.boxes['copy-btn'].classList.contains('d-none'));
  ui.select('distribution', 'F');
  assert.deepEqual(ui.values('platform'), ['-1', 'F-44', 'F-43']);
  assert.equal(ui.boxes.version.disabled, true);
  assert(!ui.boxes['script-box'].textContent.includes('sudo'));
  assert(ui.boxes['copy-btn'].classList.contains('d-none'));
  ui.select('platform', 'F-44');
  ui.select('version', '18');
  assert(ui.boxes['script-box'].textContent.includes('/F-44-x86_64/pgdg-fedora-repo-latest.noarch.rpm'));
});

test('repository data is rendered as plain text, and existing copy actions stay wired', () => {
  const arch = 'x86_64<img src=x onerror=alert(1)>';
  const ui = chooser({ 'AL-2023': [{ arch, versions: ['18'] }] });
  ui.select('distribution', 'AL');
  ui.select('version', '18');
  assert(ui.boxes['script-box'].textContent.includes(arch));
  ui.boxes['copy-btn'].events.click();
  ui.boxes['copy-btn-root'].events.click();
  assert.equal(ui.copied[0][1], 'script-box');
  assert.equal(ui.copied[0][2], undefined);
  assert.equal(ui.copied[1][2], true);
});
