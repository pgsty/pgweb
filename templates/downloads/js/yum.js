var repodata = {{json|safe}};
var supported_versions = [{{supported_versions}}];

const distributions = [
  ['EL', 'RHEL / Rocky Linux / AlmaLinux'],
  ['F', 'Fedora'],
  ['AL', 'Amazon Linux'],
];

function sortVersionDesc(a, b) {
  const x = a.split('.').map(Number);
  const y = b.split('.').map(Number);
  for (let i = 0; i < Math.max(x.length, y.length); i++) {
    if ((x[i] || 0) !== (y[i] || 0))
      return (y[i] || 0) - (x[i] || 0);
  }
  return 0;
}

function split_platform(plat) {
  const i = plat.indexOf('-');
  return [plat.substring(0, i), plat.substring(i + 1)];
}

function get_major(plat) {
  return parseInt(split_platform(plat)[1], 10);
}

function get_rpm_prefix(plat) {
   if (plat.startsWith('EL-'))
       return 'redhat';
    else if (plat.startsWith('F-'))
	return 'fedora';
    else if (plat.startsWith('AL-'))
	return 'amazonlinux';
    return 'unknown';
}

function get_installer(plat) {
    if (plat.startsWith('F-') || plat.startsWith('AL-'))
	return 'dnf';
    else if (plat.startsWith('EL-')) {
	if (get_major(plat) >= 8)
	    return 'dnf';
    }
    return 'yum';
}

function disable_module_on(plat) {
    if (plat.startsWith('EL-')) {
	if (get_major(plat) === 8)
	    return true;
    }
    return false;
}

function uses_systemd(plat) {
    if (plat.startsWith('EL-')) {
	if (get_major(plat) < 7)
	    return false;
    }
    return true;
}

function get_arch_text(arch) {
  return arch === 'aarch64' ? 'aarch64（ARM64）' : arch;
}

function get_platform_text(plat) {
  const [prefix, version] = split_platform(plat);
  // Rocky Linux and AlmaLinux start at EL8; retained EL7 packages are for RHEL.
  return prefix === 'EL' && get_major(plat) < 8 ? version + '（RHEL）' : version;
}

function get_supported_platforms(dist) {
  return Object.keys(repodata['platforms']).filter((plat) => {
    const [prefix, version] = split_platform(plat);
    // Since PGDG repo RPM 42.0-69, EL minor-specific links provide the same
    // package as the major link. They no longer pin a system to that minor.
    return prefix === dist && !version.includes('.') && get_supported_arches(plat).length > 0;
  }).sort((a, b) => sortVersionDesc(split_platform(a)[1], split_platform(b)[1]));
}

function get_supported_arches(plat) {
  return repodata['platforms'][plat]
    .filter((entry) => entry['versions'].some((version) => supported_versions.includes(parseInt(version, 10))))
    .sort((a, b) => a['arch'].localeCompare(b['arch']));
}

function get_supported_versions_for_arch(plat, arch) {
  for (const a in repodata['platforms'][plat]) {
    if (repodata['platforms'][plat][a]['arch'] === arch) {
      return repodata['platforms'][plat][a]['versions'].filter((version) => supported_versions.includes(parseInt(version, 10)));
    }
  }
  return [];
}

function clear_options(box) {
  while (box.options.length > 0) {
    box.options.remove(0);
  }
}

function add_option(box, text, value) {
  const opt = document.createElement('option');
  opt.text = text;
  opt.value = value;
  box.add(opt);
}

function distChanged() {
  const dist = document.getElementById('distribution').value;
  const platbox = document.getElementById('platform');
  clear_options(platbox);
  platbox.disabled = !dist || dist === '-1';

  if (platbox.disabled) {
    add_option(platbox, '请先选择发行版', '-1');
  } else {
    const platforms = get_supported_platforms(dist);
    if (platforms.length > 1)
      add_option(platbox, '请选择系统版本', '-1');
    for (const plat of platforms)
      add_option(platbox, get_platform_text(plat), plat);
  }
  platChanged();
}

function platChanged() {
  const plat = document.getElementById('platform').value;
  const archbox = document.getElementById('arch');

  clear_options(archbox);
  archbox.disabled = !plat || plat === '-1';

  if (archbox.disabled) {
    add_option(archbox, '请先选择系统版本', '-1');
    archChanged();
    return;
  }

  const arches = get_supported_arches(plat);
  if (arches.length > 1)
    add_option(archbox, '请选择处理器架构', '-1');
  for (const entry of arches)
    add_option(archbox, get_arch_text(entry['arch']), entry['arch']);

  archChanged();
}

function archChanged() {
  const plat = document.getElementById('platform').value;
  const arch = document.getElementById('arch').value;
  const verbox = document.getElementById('version');

  clear_options(verbox);
  verbox.disabled = !arch || arch === '-1';

  if (verbox.disabled) {
    add_option(verbox, '请先选择处理器架构', '-1');
    verChanged();
    return;
  }

  add_option(verbox, '请选择 PostgreSQL 版本', '-1');
  const versions = get_supported_versions_for_arch(plat, arch).sort(sortVersionDesc);
  for (const version of versions)
    add_option(verbox, version, version);

  verChanged();
}

function verChanged() {
  var ver = document.getElementById('version').value;
  var plat = document.getElementById('platform').value;
  var arch = document.getElementById('arch').value;
  var scriptBox = document.getElementById('script-box');

  if (!ver || ver === "-1") {
     document.getElementById('copy-btn').classList.add('d-none');
     document.getElementById('copy-btn-root').classList.add('d-none');
     scriptBox.textContent = '请先选择发行版、系统版本、处理器架构和 PostgreSQL 版本。';
     return;
  }

  var shortver = ver.replace('.', '');

  var url = 'https://download.postgresql.org/pub/repos/yum/reporpms/' + plat + '-' + arch + '/pgdg-' + get_rpm_prefix(plat) +'-repo-latest.noarch.rpm';

  var installer = get_installer(plat);
  var script = '# 安装 PGDG 仓库配置包：\n';
  script += 'sudo ' + installer + ' install -y ' + url + '\n\n';

  if (disable_module_on(plat)) {
    script += '# 禁用发行版自带的 PostgreSQL 模块：\n';
    script += 'sudo dnf -qy module disable postgresql\n\n';
  }

  script += '# 安装 PostgreSQL：\n';
  script += 'sudo ' + installer + ' install -y postgresql' + shortver + '-server\n\n';

  script += '# 可选：初始化数据库、启用开机启动并启动服务：\n';
  if (uses_systemd(plat)) {
    var setupcmd = 'postgresql-' + shortver + '-setup';
    if (ver < 10) {
      setupcmd = 'postgresql' + shortver + '-setup';
    }
    script += 'sudo /usr/pgsql-' + ver + '/bin/' + setupcmd + ' initdb\nsudo systemctl enable postgresql-' + ver + '\nsudo systemctl start postgresql-' + ver;
  }
  else {
    script += 'sudo service postgresql-' + ver + ' initdb\nsudo chkconfig postgresql-' + ver + ' on\nsudo service postgresql-' + ver + ' start';
  }

  scriptBox.textContent = script;
  document.getElementById('copy-btn').classList.remove('d-none');
  document.getElementById('copy-btn-root').classList.remove('d-none');
}

/* Event handlers */
function setupHandlers() {
    document.getElementById('copy-btn').addEventListener('click', function () {
        copyScript(this, 'script-box');
    });
    document.getElementById('copy-btn-root').addEventListener('click', function () {
        copyScript(this, 'script-box', true);
    });
    document.getElementById('version').addEventListener('change', verChanged);
    document.getElementById('distribution').addEventListener('change', distChanged);
    document.getElementById('platform').addEventListener('change', platChanged);
    document.getElementById('arch').addEventListener('change', archChanged);

    const distbox = document.getElementById('distribution');
    clear_options(distbox);
    add_option(distbox, '请选择发行版', '-1');
    for (const [prefix, name] of distributions) {
      if (get_supported_platforms(prefix).length > 0)
        add_option(distbox, name, prefix);
    }
    distChanged();
}

document.addEventListener("DOMContentLoaded", setupHandlers);
