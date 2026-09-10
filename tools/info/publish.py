#!/usr/bin/env python3
"""Import 博览 batch files into the local or production PGWeb database.

    tools/info/publish.py 2026-09-10                    # local import
    tools/info/publish.py 2026-09-10 --check            # validate only
    tools/info/publish.py 2026-09-10 --target production
    tools/info/publish.py data/info/2026-09-1*.json --target production

A date argument means data/info/DATE.json. Locally this runs
`manage.py info_import`; for production the file is streamed over ssh and
imported with the remote checkout's Django settings, so it works before the
commit that adds the file has been pulled. Only the standard library is used.
"""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def resolve(arg):
    return os.path.join(ROOT, 'data', 'info', arg + '.json') if DATE.match(arg) else arg


def import_args(options):
    extra = []
    if options.check:
        extra.append('--check')
    if options.hide_missing:
        extra.append('--hide-missing')
    return extra


def run_local(files, options):
    command = [os.path.join(ROOT, '.venv', 'bin', 'python'), 'manage.py', 'info_import', *files, *import_args(options)]
    return subprocess.run(command, cwd=ROOT).returncode


def run_remote(files, options):
    """Copy each file to a temp dir on the host under its own name (the importer
    checks that the file name matches the date), import, clean up."""
    rc = 0
    for path in files:
        name = os.path.basename(path)
        with open(path, 'rb') as stream:
            payload = stream.read()
        json.loads(payload.decode('utf-8'))  # fail here rather than on the host
        remote = ('set -e; d=$(mktemp -d); trap \'rm -rf "$d"\' EXIT; cat > "$d"/{name}; '
                  'cd {root} && .venv/bin/python manage.py info_import "$d"/{name} {extra}').format(
            name=shlex.quote(name), root=shlex.quote(options.remote_root), extra=shlex.join(import_args(options)))
        result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '--', options.ssh_host, remote], input=payload)
        rc = rc or result.returncode
    return rc


def main():
    parser = argparse.ArgumentParser(description='导入博览批次文件到本地或生产')
    parser.add_argument('files', nargs='+', help='日期 YYYY-MM-DD（取 data/info/DATE.json）或批次文件路径')
    parser.add_argument('--target', choices=['local', 'production'], default='local')
    parser.add_argument('--check', action='store_true', help='只校验不写入')
    parser.add_argument('--hide-missing', action='store_true', help='把该日批次里已删除的条目置为 hidden')
    parser.add_argument('--ssh-host', default='pg')
    parser.add_argument('--remote-root', default='/data/app/pgsql.cc')
    options = parser.parse_args()
    files = [resolve(arg) for arg in options.files]
    missing = [f for f in files if not os.path.isfile(f)]
    if missing:
        print('批次文件不存在：' + ', '.join(missing), file=sys.stderr)
        return 2
    if options.target == 'production':
        return run_remote(files, options)
    return run_local(files, options)


if __name__ == '__main__':
    sys.exit(main())
