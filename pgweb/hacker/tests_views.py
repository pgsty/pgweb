from django.core.cache import cache
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from .models import HackerProfile
from .struct import get_struct
from .presentation import safe_url


class PublicLinkTests(SimpleTestCase):
    def test_excludes_archive_hosts_and_unsafe_links(self):
        for url in ('https://pgnexus.ai/c/person', 'https://www.PGNEXUS.ai./u/person',
                    'javascript:alert(1)', 'https://user:pass@example.org/'):
            self.assertEqual(safe_url(url), '')
        self.assertEqual(safe_url('https://www.linkedin.com/in/person/'), 'https://www.linkedin.com/in/person/')


class DirectoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.profile = HackerProfile.objects.create(
            source_id='4', slug='amit-kapila-4', name='Amit Kapila', organization='Fujisu', country='IN',
            bio='PostgreSQL developer <script>alert(1)</script>', source_fetched_at=timezone.now(),
            texts={'zh': {'bio': '研究并行查询的开发者 <script>alert(1)</script>', 'organization': 'Fujitsu',
                          'position': '数据库工程师', 'location': '印度', 'review_note': '人物身份尚待核实。'}},
            content_hash='a' * 64, avatar=b'test-avatar', avatar_content_type='image/webp', avatar_sha256='b' * 64,
            data={'source_url': 'https://pgnexus.ai/c/amit-kapila-4',
                  'emails': [{'email': 'amit@example.org', 'source_url': 'https://www.postgresql.org/community/contributors/'}],
                  'links': [{'label': 'GitHub', 'url': 'https://github.com/example'},
                            {'label': 'Unsafe', 'url': 'javascript:alert(1)'},
                            {'label': 'PGNexus', 'url': 'https://pgnexus.ai/c/amit-kapila-4'}],
                  'official': {'organization': 'Fujitsu', 'role': 'Major Contributor', 'contribution': 'Parallel query.',
                               'source_url': 'https://www.postgresql.org/community/contributors/'},
                  'review_notes': [{'note': '来源身份尚待核实。'}],
                  'sections': {'DiscussionsSection': {'items': [
                      {'subject': 'Discussion', 'subject_zh': '公开讨论', 'summary_zh': '讨论摘要', 'url': 'https://example.org/thread'}
                  ], 'total': 1}}},
        )
        cls.other = HackerProfile.objects.create(source_id='16', slug='tom-lane-16', name='Tom Lane', organization='Snowflake',
                                                 country='US', source_fetched_at=timezone.now(), content_hash='c' * 64)

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_standard_page_navigation_metadata_and_escaping(self):
        response = self.client.get('/developer/hacker/')
        self.assertContains(response, 'PostgreSQL 开发者大全')
        self.assertTemplateUsed(response, 'base/page.html')
        self.assertEqual(response.context['total'], 2)
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertNotContains(response, 'https://www.postgresql.org/developer/hacker/')
        self.assertContains(response, 'href="/developer/hacker/amit-kapila-4/"')
        from pgweb.core.templatetags.pgfilters import nav_active
        self.assertTrue(nav_active('/developer/hacker/amit-kapila-4/', 'developer'))
        self.assertEqual(response.context['navmenu'][-1]['title'], '消息翻译')

    def test_combined_filters_email_search_empty_and_pagination(self):
        response = self.client.get('/developer/hacker/', {'q': 'amit@example.org', 'organization': 'Fujitsu', 'country': 'IN'})
        self.assertEqual([p.source_id for p in response.context['page']], ['4'])
        self.assertTrue(response.context['noindex'])
        self.assertContains(self.client.get('/developer/hacker/?q=missing'), '没有找到匹配的开发者')
        for i in range(25):
            HackerProfile.objects.create(source_id=str(100 + i), slug='person-' + str(i), name='Person ' + str(i),
                                         organization='Fujitsu', country='IN', source_fetched_at=timezone.now(), content_hash='d' * 64)
        response = self.client.get('/developer/hacker/', {'organization': 'Fujitsu', 'country': 'IN', 'page': 'invalid'})
        self.assertEqual(response.context['page'].number, 1)
        self.assertIn('organization=Fujitsu', response.context['next_url'])
        self.assertIn('country=IN', response.context['next_url'])
        self.assertEqual(self.client.get(response.context['next_url']).context['page'].number, 2)

    def test_chinese_profile_icons_sources_and_removed_activity(self):
        response = self.client.get('/developer/hacker/amit-kapila-4/')
        for value in ('Fujitsu', '研究并行查询', 'mailto:amit@example.org', 'fa-envelope', 'fa-github', '人物身份尚待核实。'):
            self.assertContains(response, value)
        for value in ('pgnexus', 'PGNexus', '参与讨论', '讨论摘要', '提交的补丁', '资料采集于', '联系方式',
                      '联系与链接', 'Parallel query.', 'PostgreSQL developer', 'javascript:'):
            self.assertNotContains(response, value)
        self.assertContains(response, 'aria-label="GitHub"')
        self.assertContains(response, 'https://www.postgresql.org/community/contributors/')
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertEqual(response.context['seo']['canonical'], '/developer/hacker/amit-kapila-4/')
        self.assertEqual(self.client.get('/developer/hacker/does-not-exist/').status_code, 404)
        self.assertEqual(self.client.post('/developer/hacker/').status_code, 405)
        self.assertRedirects(self.client.get('/developer/hacker'), '/developer/hacker/', status_code=301)
        self.assertEqual([p.source_id for p in self.client.get('/developer/hacker/?q=并行查询').context['page']], ['4'])

    def test_avatar_content_caching_and_missing(self):
        response = self.client.get('/developer/hacker/amit-kapila-4/avatar/')
        self.assertEqual(response.content, b'test-avatar')
        self.assertEqual(response['Content-Type'], 'image/webp')
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        cached = self.client.get('/developer/hacker/amit-kapila-4/avatar/', HTTP_IF_NONE_MATCH=response['ETag'])
        self.assertEqual(cached.status_code, 304)
        self.assertEqual(self.client.get('/developer/hacker/tom-lane-16/avatar/').status_code, 404)
        self.assertEqual(self.client.get('/developer/hacker/missing/avatar/').status_code, 404)

    def test_legacy_urls_redirect_to_canonical_paths_with_query(self):
        for path in ('', 'amit-kapila-4/', 'amit-kapila-4/avatar/'):
            with self.subTest(path=path):
                self.assertRedirects(self.client.get('/hacker/' + path),
                                     '/developer/hacker/' + path, status_code=301)
        query = 'q=Amit+Kapila&country=IN&page=1'
        self.assertRedirects(self.client.get('/hacker/?' + query),
                             '/developer/hacker/?' + query, status_code=301)

    def test_listing_does_not_fetch_full_source_archive_or_portrait(self):
        with CaptureQueriesContext(connection) as captured:
            self.client.get('/developer/hacker/')
        queries = [q['sql'] for q in captured if 'FROM "hacker_profile"' in q['sql']]
        self.assertTrue(queries)
        for query in queries:
            self.assertNotIn('"hacker_profile"."data"', query)
            self.assertNotIn('"hacker_profile"."avatar"', query)

    def test_sitemap_covers_people_and_excludes_avatar_routes(self):
        urls = [url for url, _ in get_struct()]
        self.assertEqual(set(urls), {'developer/hacker/', 'developer/hacker/amit-kapila-4/', 'developer/hacker/tom-lane-16/'})
