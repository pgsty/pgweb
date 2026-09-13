"""Render every stored major-version grammar and check its SVG/token coverage."""

from collections import Counter
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand, CommandError

from pgweb.wiki.models import SqlCommand
from pgweb.wiki.sqlcmd_railroad import context


def words(text):
    # Punctuation/keyword coverage is independent of the grammar parser. Meta
    # notation becomes tracks; all literal tokens must remain in the diagrams.
    return Counter(re.findall(r'[^\s\[\]{}|(),\'=.]+|[(),\'=.]', text.replace('...', '')))


def verify(snapshot, railroad):
    source = BeautifulSoup(snapshot['synopsis_html'], 'html.parser')
    for phrase in source.select('.phrase'):
        phrase.decompose()
    expected = words(source.get_text())
    actual, ids, links = Counter(), set(), []
    for rule in railroad['rules']:
        if rule['id'] in ids:
            raise ValueError('Duplicate production id: ' + rule['id'])
        ids.add(rule['id'])
        svg = ET.fromstring(rule['svg'])
        for node in svg.iter():
            tag = node.tag.rsplit('}', 1)[-1]
            if tag not in ('svg', 'g', 'path', 'rect', 'text', 'title', 'a'):
                raise ValueError('Unexpected SVG element: ' + tag)
            if 'style' in node.attrib or any(a.startswith('on') for a in node.attrib):
                raise ValueError('Inline style or handler in SVG')
            if tag == 'text':
                actual.update(words(node.text or ''))
            if tag == 'a':
                links.append(node.attrib['href'])
        if float(svg.attrib['width']) <= 0 or float(svg.attrib['height']) <= 0:
            raise ValueError('Empty SVG bounds')
    if actual != expected:
        raise ValueError('Token coverage: missing={}, extra={}'.format(dict(expected - actual), dict(actual - expected)))
    if any(link[1:] not in ids for link in links):
        raise ValueError('Unresolved production link')
    if not railroad['forms']:
        raise ValueError('No main command diagram')


class Command(BaseCommand):
    help = '生成并校验全部 SQL 命令各大版本的铁道图；不修改数据库。'

    def add_arguments(self, parser):
        parser.add_argument('--report', help='将完整覆盖报告写入 JSON 文件')

    def handle(self, **options):
        rows, errors, versions = [], [], Counter()
        commands = list(SqlCommand.objects.only('slug', 'name', 'versions'))
        for command in commands:
            for major, snapshot in command.versions.items():
                try:
                    railroad = context(snapshot, 'rr-audit-' + command.slug + '-' + major)
                    verify(snapshot, railroad)
                    rows.append({'slug': command.slug, 'version': major, 'digest': railroad['digest'],
                                 'forms': railroad['forms'], 'definitions': railroad['definitions']})
                    versions[major] += 1
                except (ValueError, KeyError, ET.ParseError) as exc:
                    errors.append({'slug': command.slug, 'version': major, 'error': str(exc)})
        report = {'commands': len(commands), 'snapshots': len(rows), 'versions': dict(versions),
                  'unique_syntax': len({r['digest'] for r in rows}),
                  'diagrams': sum(r['forms'] + r['definitions'] for r in rows),
                  'errors': errors, 'coverage': rows}
        if options.get('report'):
            Path(options['report']).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        self.stdout.write(json.dumps({k: v for k, v in report.items() if k != 'coverage'}, ensure_ascii=False))
        if errors or not rows:
            raise CommandError('SQL 铁道图校验未通过')
