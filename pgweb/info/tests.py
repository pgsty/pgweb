import hashlib
import io
import json
import os
import tempfile
from datetime import date

from unittest.mock import patch

from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.test import TestCase

from .highlights import home_highlights
from .importer import item_key, load
from .models import InfoItem


LEAD_SUMMARY = ('Dalibo 发布 PostgreSQL Anonymizer 3.2，修复了自定义类型提权、规则导入 SQL 注入和并行静态脱敏提权'
                '三个漏洞，其中 PostgreSQL 14 及从更早版本升级而来的实例风险最高。新版本默认禁止超级用户执行各类脱敏'
                '操作，并用速度更快的 anon.seeded_* 系列取代 anon.pseudo_*。使用静态脱敏的团队需要先准备专用低权限角色。')
VECTOR_SUMMARY = ('pgvector 0.9 把 HNSW 的建索引过程拆成可并行的分区阶段，官方基准显示一亿行、1536 维数据集的'
                  '耗时从九小时降到四小时出头，内存峰值也随之下降。新版本补齐了 halfvec 的距离算子覆盖，并修复了'
                  '并发写入时召回率偶发下滑的问题。已经在生产使用 HNSW 的用户升级后需要重建索引才能用上新布局。')


def item(tier=1, position=1, **overrides):
    row = {
        'tier': tier,
        'title': {1: 'PostgreSQL Anonymizer 3.2 修复三个高危漏洞', 2: 'Autobase 2.11 收进平台界面',
                  3: 'ClickHouse 26.8 提供 PostgreSQL 线协议端点'}[tier],
        'summary': {1: LEAD_SUMMARY, 2: '新增 pgBackRest 与 WAL-G 的备份恢复 playbook。', 3: ''}[tier],
        'url': 'https://example.org/tier{}'.format(tier),
        'author': 'Dalibo' if tier == 1 else '',
        'source': 'PostgreSQL 新闻' if tier == 1 else '',
        'source_date': '2026-09-09',
        'image': '',
        'domain': 'pg' if tier < 3 else 'db',
        'tags': ['安全', '扩展'] if tier == 1 else [],
        'position': position,
    }
    row.update(overrides)
    return row


def run(*args):
    """call_command with the report captured instead of printed."""
    out = io.StringIO()
    call_command(*args, stdout=out)
    return [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]


def batch(day='2026-09-10', items=None, origin='pgsty-daily', name=None):
    """Write a batch file into a temporary directory and return its path."""
    folder = tempfile.mkdtemp()
    path = os.path.join(folder, name or '{}.json'.format(day))
    payload = {'date': day, 'origin': origin,
               'items': items if items is not None else [item(1, 1), item(2, 2), item(3, 3)]}
    with open(path, 'w', encoding='utf-8') as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
    return path


class ImportTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_first_import_creates_rows_and_a_stable_key(self):
        run('info_import', batch())
        self.assertEqual(InfoItem.objects.count(), 3)
        lead = InfoItem.objects.get(tier=1)
        expected = hashlib.sha1('2026-09-10|https://example.org/tier1'.encode()).hexdigest()[:16]
        self.assertEqual(lead.key, expected)
        self.assertEqual(len(lead.key), 16)
        self.assertEqual(lead.date, date(2026, 9, 10))
        self.assertEqual(lead.status, 'published')
        self.assertEqual(lead.tags, ['安全', '扩展'])
        self.assertEqual(lead.source_date, date(2026, 9, 9))
        self.assertEqual(lead.origin['origin'], 'pgsty-daily')
        self.assertEqual(lead.origin['file'], '2026-09-10.json')
        self.assertIsNotNone(lead.search_vector)

    def test_key_is_the_title_when_an_item_has_no_link(self):
        path = batch(items=[item(3, 1, url='', title='仅标题条目')])
        run('info_import', path)
        self.assertEqual(InfoItem.objects.get().key,
                         hashlib.sha1('2026-09-10|仅标题条目'.encode()).hexdigest()[:16])
        self.assertEqual(item_key('2026-09-10', '', '仅标题条目'), InfoItem.objects.get().key)

    def test_reimport_reports_unchanged_and_edits_report_updated(self):
        path = batch()
        run('info_import', path)
        keys = set(InfoItem.objects.values_list('key', flat=True))
        run('info_import', path)
        self.assertEqual(InfoItem.objects.count(), 3)

        edited = batch(items=[item(1, 1, title='标题改过了'), item(2, 2), item(3, 3)])
        run('info_import', edited)
        self.assertEqual(InfoItem.objects.count(), 3)
        self.assertEqual(set(InfoItem.objects.values_list('key', flat=True)), keys)
        self.assertEqual(InfoItem.objects.get(tier=1).title, '标题改过了')

    def test_check_validates_without_writing(self):
        run('info_import', '--check', batch())
        self.assertEqual(InfoItem.objects.count(), 0)

    def test_hide_missing_retires_items_the_file_no_longer_lists(self):
        run('info_import', batch())
        run('info_import', '--hide-missing', batch(items=[item(1, 1)]))
        self.assertEqual(InfoItem.objects.filter(status='published').count(), 1)
        self.assertEqual(InfoItem.objects.filter(status='hidden').count(), 2)
        # A hidden item that comes back in a later batch is published again.
        run('info_import', batch())
        self.assertEqual(InfoItem.objects.filter(status='published').count(), 3)

    def test_hidden_items_leave_the_public_pages(self):
        run('info_import', batch())
        run('info_import', '--hide-missing', batch(items=[item(1, 1)]))
        response = self.client.get('/info/2026-09-10/')
        self.assertContains(response, 'PostgreSQL Anonymizer 3.2')
        self.assertNotContains(response, 'Autobase 2.11')

    def test_validation_rejects_broken_batches(self):
        cases = {
            'tier 1 without author': [item(1, 1, author='')],
            'tier 1 without source': [item(1, 1, source='')],
            'tier 1 with a short summary': [item(1, 1, summary='太短了。')],
            'tier 1 with a long summary': [item(1, 1, summary='长' * 241)],
            'too many leads': [item(1, n, url='https://example.com/{}'.format(n)) for n in range(1, 14)],
            'too many items': ([item(1, 1)] + [item(3, n, url='https://example.com/{}'.format(n)) for n in range(2, 47)]),
            'tier 2 without url': [item(1, 1), item(2, 2, url='')],
            'tier 2 with a paragraph': [item(1, 1), item(2, 2, summary='长' * 81)],
            'title too long': [item(1, 1, title='标' * 41)],
            'image not https': [item(1, 1, image='http://example.com/a.png')],
            'unknown domain': [item(1, 1, domain='news')],
            'unknown tier': [dict(item(1, 1), tier=4)],
            'tiers out of order': [item(2, 1), item(1, 2)],
            'position not consecutive': [item(1, 1), item(2, 5)],
            'missing title': [item(1, 1, title='')],
            'duplicate link': [item(1, 1), item(1, 2)],
        }
        for label, items in cases.items():
            with self.subTest(label):
                with self.assertRaises(CommandError):
                    run('info_import', batch(items=items))
        self.assertEqual(InfoItem.objects.count(), 0)

    def test_filename_must_agree_with_the_date_field(self):
        with self.assertRaises(CommandError):
            run('info_import', batch(day='2026-09-10', name='2026-09-11.json'))

    def test_a_batch_file_under_another_name_still_loads(self):
        day, _origin, rows = load(batch(day='2026-09-10', name='candidates.json'))
        self.assertEqual(day, date(2026, 9, 10))
        self.assertEqual(len(rows), 3)

    def test_index_rebuild_recomputes_every_vector(self):
        run('info_import', batch())
        InfoItem.objects.update(search_vector=None)
        self.assertEqual(InfoItem.objects.filter(search_vector__isnull=True).count(), 3)
        run('info_index', '--rebuild')
        self.assertEqual(InfoItem.objects.filter(search_vector__isnull=True).count(), 0)

    def test_index_without_rebuild_does_nothing(self):
        with self.assertRaises(CommandError):
            run('info_index')


class ThumbTests(TestCase):
    """data/info/img/<key>.webp is loaded into the row and served at /info/img/<key>.webp."""

    def setUp(self):
        cache.clear()
        from . import importer
        self.folder = tempfile.mkdtemp()
        self.patch = patch.object(importer, 'IMG_DIR', self.folder)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_a_thumbnail_file_is_stored_and_served(self):
        key = item_key('2026-09-10', item(1, 1)['url'], '')
        with open(os.path.join(self.folder, key + '.webp'), 'wb') as stream:
            stream.write(b'RIFF....WEBPVP8 ')
        run('info_import', batch())
        row = InfoItem.objects.get(key=key)
        self.assertEqual(bytes(row.thumb), b'RIFF....WEBPVP8 ')
        response = self.client.get('/info/img/{}.webp'.format(key))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/webp')
        self.assertIn('max-age', response['Cache-Control'])
        page = self.client.get('/info/2026-09-10/')
        self.assertContains(page, '/info/img/{}.webp'.format(key))

    def test_without_a_file_the_source_picture_is_used_and_a_warning_is_reported(self):
        reports = run('info_import', batch(items=[item(1, 1, image='https://example.org/a.png')]))
        self.assertIn('没有本地缩略图', reports[0]['warnings'][-1])
        key = item_key('2026-09-10', item(1, 1)['url'], '')
        self.assertIsNone(InfoItem.objects.get(key=key).thumb)
        self.assertEqual(self.client.get('/info/img/{}.webp'.format(key)).status_code, 404)
        self.assertContains(self.client.get('/info/2026-09-10/'), 'https://example.org/a.png')

    def test_adding_the_file_later_counts_as_an_update(self):
        run('info_import', batch())
        key = item_key('2026-09-10', item(1, 1)['url'], '')
        with open(os.path.join(self.folder, key + '.webp'), 'wb') as stream:
            stream.write(b'RIFF')
        self.assertEqual(run('info_import', batch())[0]['updated'], 1)
        self.assertEqual(run('info_import', batch())[0]['unchanged'], 3)


class PageTests(TestCase):
    def setUp(self):
        cache.clear()
        for day in ('2026-09-04', '2026-09-08', '2026-09-10'):
            run('info_import', batch(day=day))

    def tearDown(self):
        cache.clear()

    def test_stream_lists_days_newest_first_with_items_in_tier_order(self):
        response = self.client.get('/info/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'info/stream.html')
        html = response.content.decode()
        self.assertContains(response, '<h1>PostgreSQL 博览</h1>', html=True)
        self.assertContains(response, '每日精选 PostgreSQL、数据库与云计算资讯')
        # Read positions inside the reading column, not the side card above it.
        body = html.split('<div class="info-column"', 1)[1]
        days = [body.index('id="day-{}"'.format(day)) for day in ('20260910', '20260908', '20260904')]
        self.assertEqual(days, sorted(days))
        tiers = [body.index('example.org/tier{}'.format(n)) for n in (1, 2, 3)]
        self.assertEqual(tiers, sorted(tiers))
        self.assertTrue(days[0] < tiers[0] < days[1])
        self.assertContains(response, '3 条')
        self.assertNotIn('noindex', html.split('</head>', 1)[0])

    def test_stream_paginates_seven_days_and_marks_later_pages_noindex(self):
        for number in range(1, 9):
            run('info_import', batch(day='2026-08-0{}'.format(number), items=[item(1, 1)]))
        first = self.client.get('/info/')
        self.assertEqual(len(first.context['days']), 7)
        self.assertContains(first, 'href="/info/?page=2"')
        second = self.client.get('/info/?page=2')
        self.assertEqual(second.status_code, 200)
        self.assertContains(second, 'noindex,follow')
        self.assertEqual([day['date'] for day in first.context['days']][-1] > second.context['days'][0]['date'], True)

    def test_day_page_groups_the_three_tiers_and_links_neighbouring_days(self):
        response = self.client.get('/info/2026-09-08/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'info/day.html')
        self.assertEqual([row.tier for row in response.context['lead']], [1])
        self.assertEqual([row.tier for row in response.context['brief']], [2])
        self.assertEqual([row.tier for row in response.context['mini']], [3])
        self.assertContains(response, 'href="/info/2026-09-04/"')
        self.assertContains(response, 'href="/info/2026-09-10/"')
        self.assertNotIn('noindex', response.content.decode().split('</head>', 1)[0])

    def test_day_navigation_skips_days_without_content(self):
        response = self.client.get('/info/2026-09-10/')
        self.assertEqual(response.context['previous_day'], date(2026, 9, 8))
        self.assertIsNone(response.context['next_day'])
        earliest = self.client.get('/info/2026-09-04/')
        self.assertIsNone(earliest.context['previous_day'])
        self.assertEqual(earliest.context['next_day'], date(2026, 9, 8))

    def test_anchors_use_the_item_key(self):
        response = self.client.get('/info/2026-09-10/')
        for key in InfoItem.objects.filter(date=date(2026, 9, 10)).values_list('key', flat=True):
            self.assertContains(response, 'id="{}"'.format(key))

    def test_a_valid_day_without_content_gets_an_empty_state(self):
        response = self.client.get('/info/2026-09-09/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '这一天没有收录条目')
        self.assertEqual(response.context['count'], 0)
        self.assertEqual(response.context['previous_day'], date(2026, 9, 8))
        self.assertEqual(response.context['next_day'], date(2026, 9, 10))

    def test_malformed_dates_are_not_found(self):
        for bad in ('2026-13-01', '20260910', 'yesterday', '2026-09-10x'):
            with self.subTest(bad):
                self.assertEqual(self.client.get('/info/{}/'.format(bad)).status_code, 404)

    def test_daily_redirects_to_the_latest_day_with_content(self):
        response = self.client.get('/info/daily/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/info/2026-09-10/')

    def test_daily_falls_back_to_the_stream_when_nothing_is_loaded(self):
        InfoItem.objects.all().delete()
        response = self.client.get('/info/daily/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/info/')

    def test_archive_groups_dates_by_month_with_counts(self):
        response = self.client.get('/info/archive/')
        self.assertEqual(response.status_code, 200)
        months = response.context['months']
        self.assertEqual([month['key'] for month in months], ['2026-09'])
        self.assertEqual(months[0]['count'], 9)
        self.assertEqual([day['date'] for day in months[0]['days']],
                         [date(2026, 9, 10), date(2026, 9, 8), date(2026, 9, 4)])
        self.assertContains(response, 'noindex,follow')

    def test_the_side_card_lists_recent_days_and_marks_the_current_one(self):
        response = self.client.get('/info/2026-09-08/')
        self.assertEqual([day['count'] for day in response.context['sidecard_days']], [3, 3, 3])
        self.assertContains(response, '每日更新')
        self.assertContains(response, 'href="/info/2026-09-08/" aria-current="page"')
        self.assertContains(response, 'href="/info/archive/"')
        self.assertContains(response, 'action="/info/search/"')

    def test_empty_column_renders_without_failing(self):
        InfoItem.objects.all().delete()
        for url in ('/info/', '/info/archive/', '/info/search/', '/info/rss/'):
            with self.subTest(url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_undeclared_query_parameters_are_dropped(self):
        response = self.client.get('/info/?page=1&utm_source=share')
        self.assertEqual(response.status_code, 200)

    def test_navigation_and_footer_carry_the_column(self):
        from pgweb.core.templatetags.pgfilters import nav_active
        from pgweb.util.contexts import sitenav
        self.assertTrue(nav_active('/info/', 'info'))
        self.assertTrue(nav_active('/info/2026-09-10/', 'info'))
        self.assertFalse(nav_active('/info/', 'home'))
        self.assertEqual([entry['link'] for entry in sitenav['info']],
                         ['/info/', '/info/daily/', '/info/archive/', '/info/search/'])
        response = self.client.get('/info/')
        self.assertContains(response, 'href="/info/" class', count=0)
        self.assertContains(response, '博览')


class SearchTests(TestCase):
    def setUp(self):
        cache.clear()
        run('info_import', batch())
        run('info_import', batch(day='2026-09-08', items=[
            item(1, 1, title='pgvector 0.9 引入分区索引构建', url='https://example.org/pgvector',
                 summary=VECTOR_SUMMARY, author='Andrew Kane', source='GitHub'),
        ]))

    def tearDown(self):
        cache.clear()

    def test_an_english_term_finds_the_item_and_marks_the_hit(self):
        response = self.client.get('/info/search/?q=pgvector')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total'], 1)
        self.assertContains(response, '<mark>pgvector</mark>')
        self.assertContains(response, 'href="https://example.org/pgvector"')
        self.assertContains(response, 'href="/info/2026-09-08/#')
        self.assertContains(response, 'noindex,follow')

    def test_a_chinese_term_finds_the_item_and_marks_the_hit(self):
        response = self.client.get('/info/search/?q=%E8%84%B1%E6%95%8F')
        self.assertEqual(response.context['total'], 1)
        self.assertContains(response, '<mark>脱敏</mark>')
        self.assertEqual(response.context['results'][0]['tier'], 1)

    def test_author_and_source_are_searchable(self):
        self.assertEqual(self.client.get('/info/search/?q=Andrew+Kane').context['total'], 1)
        self.assertEqual(self.client.get('/info/search/?q=Dalibo').context['total'], 1)

    def test_hidden_items_are_not_returned(self):
        InfoItem.objects.filter(url='https://example.org/pgvector').update(status='hidden')
        self.assertEqual(self.client.get('/info/search/?q=pgvector').context['total'], 0)
        self.assertContains(self.client.get('/info/search/?q=pgvector'), '没有找到')

    def test_an_empty_query_shows_the_form_only(self):
        response = self.client.get('/info/search/')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['searched'])
        self.assertEqual(response.context['results'], [])
        self.assertContains(response, 'name="q"')
        self.assertNotContains(response, '找到')
        self.assertEqual(self.client.get('/info/search/?q=+').context['searched'], False)

    def test_results_paginate_twenty_per_page(self):
        rows = [item(2, position, title='分页测试条目 {}'.format(position),
                     url='https://example.org/page/{}'.format(position)) for position in range(1, 26)]
        run('info_import', batch(day='2026-09-01', items=rows))
        first = self.client.get('/info/search/?q=%E5%88%86%E9%A1%B5%E6%B5%8B%E8%AF%95')
        self.assertEqual(first.context['total'], 25)
        self.assertEqual(len(first.context['results']), 20)
        self.assertContains(first, 'q=%E5%88%86%E9%A1%B5%E6%B5%8B%E8%AF%95&amp;page=2')
        second = self.client.get('/info/search/?q=%E5%88%86%E9%A1%B5%E6%B5%8B%E8%AF%95&page=2')
        self.assertEqual(len(second.context['results']), 5)

    def test_the_column_stays_out_of_the_document_search(self):
        response = self.client.get('/search/api/?q=pgvector')
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertNotIn('分区索引构建', body)
        self.assertNotIn('example.org/pgvector', body)
        for row in json.loads(body)['results']:
            self.assertNotEqual(row.get('source'), 'info')

    def test_the_palette_and_site_search_do_not_offer_the_column(self):
        page = self.client.get('/info/')
        self.assertNotContains(page, 'data-pg-palette-source="info"')
        from pgweb.search import service
        self.assertNotIn('info', [source for _, source in service.SearchEntry.SOURCES])


class FeedTests(TestCase):
    def setUp(self):
        cache.clear()
        run('info_import', batch())

    def tearDown(self):
        cache.clear()

    def test_the_feed_carries_the_top_two_tiers_with_the_key_as_guid(self):
        response = self.client.get('/info/rss/')
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('PostgreSQL 博览', body)
        self.assertIn('https://example.org/tier1', body)
        self.assertIn('https://example.org/tier2', body)
        self.assertNotIn('https://example.org/tier3', body)
        for key in InfoItem.objects.filter(tier__lte=2).values_list('key', flat=True):
            self.assertIn('<guid isPermaLink="false">{}</guid>'.format(key), body)

    def test_the_feed_is_capped_at_fifty_items(self):
        for day in ('2026-09-01', '2026-09-02'):
            rows = [item(2, position, title='条目 {}'.format(position),
                         url='https://example.org/many/{}/{}'.format(day, position)) for position in range(1, 31)]
            run('info_import', batch(day=day, items=rows))
        self.assertEqual(self.client.get('/info/rss/').content.decode().count('<item>'), 50)


class HomeBlockTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_the_helper_is_empty_and_safe_before_anything_is_loaded(self):
        self.assertEqual(home_highlights(), {'date': None, 'entries': []})

    def test_the_helper_returns_the_latest_day_of_lead_items(self):
        run('info_import', batch(day='2026-09-08'))
        cache.clear()
        run('info_import', batch(day='2026-09-10', items=[
            item(1, 1, title='头条一', url='https://example.org/a'),
            item(1, 2, title='头条二', url='https://example.org/b'),
            item(2, 3),
        ]))
        result = home_highlights()
        self.assertEqual(result['date'], date(2026, 9, 10))
        self.assertEqual([entry['title'] for entry in result['entries']], ['头条一', '头条二'])
        self.assertEqual(result['entries'][0]['url'], 'https://example.org/a')
        self.assertEqual(result['entries'][0]['source'], 'PostgreSQL 新闻')
        self.assertLessEqual(len(result['entries'][0]['summary']), 80)
        # The cached result is reused, so a later limit does not re-query.
        self.assertEqual(len(home_highlights(limit=1)['entries']), 2)

    def test_the_helper_returns_at_most_four_items(self):
        rows = [item(1, position, title='头条 {}'.format(position),
                     url='https://example.org/lead/{}'.format(position)) for position in range(1, 7)]
        run('info_import', batch(items=rows))
        self.assertEqual(len(home_highlights()['entries']), 4)
