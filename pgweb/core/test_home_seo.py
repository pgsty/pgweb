import json
from datetime import date
from html.parser import HTMLParser
from unittest.mock import MagicMock, patch

from django.template.loader import render_to_string
from django.test import SimpleTestCase, override_settings

from pgweb.util.versions import ParsedVersion


class HomeMarkup(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def values(self, tag, attribute, **matching):
        return [attrs.get(attribute) for name, attrs in self.elements
                if name == tag and all(attrs.get(k) == v for k, v in matching.items())]


@override_settings(SITE_ROOT='https://pgsql.cc', ALLOWED_HOSTS=['testserver', 'preview.example'])
class HomeSEOTests(SimpleTestCase):
    def assertNoOldBrand(self, response):
        """The old pg.center brand must be gone; the *.pg.center data sites the
        百科 column links to (err/guc/wait/cat) are different sites and allowed."""
        import re
        body = re.sub(r'\b(err|guc|wait|cat)\.pg\.center', '', response.content.decode())
        self.assertNotIn('pg.center', body)

    def setUp(self):
        # Exercise the real view and inherited templates without a database.
        queryset = MagicMock()
        for method in ('select_related', 'filter', 'order_by', 'union', '__getitem__'):
            getattr(queryset, method).return_value = queryset
        queryset.count.return_value = 0
        queryset.all.return_value = []
        for model in ('NewsArticle', 'Event', 'Version', 'ImportedRSSItem'):
            manager = patch('pgweb.core.views.' + model + '.objects', queryset)
            manager.start()
            self.addCleanup(manager.stop)
        release = patch('pgweb.core.views.CurrentRelease.get', return_value={
            'date': date(2026, 8, 13),
            'type': 'minor',
            'versions': [ParsedVersion('18.6')],
            'news': {'url': '/about/news/release-3365/'},
        })
        release.start()
        self.addCleanup(release.stop)
        topbar = patch('pgweb.util.contexts._get_topbar_news', return_value=None)
        topbar.start()
        self.addCleanup(topbar.stop)
        manuals = patch('pgweb.docs.versions.manual_groups', return_value={
            'supported': [18, 17, 16, 15, 14], 'historical': [13, 12, 11, 10],
            'testing': [{'major': 19, 'label': 'beta'}], 'devel': 20,
        })
        manuals.start()
        self.addCleanup(manuals.stop)
        highlights = patch('pgweb.info.highlights.home_highlights',
                           return_value={'date': None, 'entries': []})
        highlights.start()
        self.addCleanup(highlights.stop)

    def test_homepage_has_one_consistent_description_and_title(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        head = HomeMarkup(html.split('</head>', 1)[0])
        title = 'PostgreSQL 中文社区｜文档、下载与技术资讯'
        self.assertContains(response, '<title>' + title + '</title>', count=1)
        self.assertEqual(head.values('meta', 'content', property='og:title'), [title])
        self.assertEqual(head.values('meta', 'content', name='twitter:title'), [title])
        descriptions = head.values('meta', 'content', name='description')
        self.assertEqual(descriptions, [
            'pgsql.cc 是由 Pigsty 团队维护的 PostgreSQL 官方网站中文翻译站，提供中文文档、技术资讯、软件目录与知识库。',
        ])
        self.assertNotIn('官方网站中文版', html)
        self.assertEqual(head.values('meta', 'content', property='og:description'), descriptions)
        self.assertEqual(head.values('meta', 'content', name='twitter:description'), descriptions)
        self.assertEqual(head.values('meta', 'content', property='og:type'), ['website'])
        self.assertEqual(head.values('meta', 'content', property='og:locale'), ['zh_CN'])
        self.assertEqual(head.values('meta', 'content', name='twitter:card'), ['summary'])
        self.assertEqual(head.values('meta', 'content', property='og:image'),
                         ['https://pgsql.cc/media/img/about/press/elephant.png'])
        self.assertEqual(head.values('meta', 'content', name='twitter:image'),
                         head.values('meta', 'content', property='og:image'))
        self.assertNotIn('noindex', html.split('</head>', 1)[0])

    def test_canonical_and_site_identity_ignore_request_host_and_query(self):
        for site_root in ('https://pgsql.cc', 'https://pgsql.cc/'):
            with self.subTest(site_root=site_root), override_settings(SITE_ROOT=site_root):
                response = self.client.get('/?utm_source=share', HTTP_HOST='preview.example')
                self.assertEqual(response.status_code, 200)
                html = response.content.decode()
                head = HomeMarkup(html.split('</head>', 1)[0])
                self.assertEqual(head.values('link', 'href', rel='canonical'), ['https://pgsql.cc/'])
                self.assertEqual(head.values('meta', 'content', property='og:url'), ['https://pgsql.cc/'])
                self.assertEqual(head.values('script', 'type', type='application/ld+json'), ['application/ld+json'])
                data = json.loads(html.split('<script type="application/ld+json">')[1].split('</script>')[0])
                self.assertEqual(data['@context'], 'https://schema.org')
                self.assertEqual(data['@type'], 'WebSite')
                self.assertEqual(data['name'], 'pgsql.cc')
                self.assertEqual(data['alternateName'], 'pgsql.cc')
                self.assertEqual(data['url'], 'https://pgsql.cc/')
                self.assertEqual(data['inLanguage'], 'zh-CN')
                self.assertEqual(data['description'], head.values('meta', 'content', name='description')[0])
                self.assertEqual([data['name']], head.values('meta', 'content', property='og:site_name'))
                self.assertNotIn('sameAs', data)

    def test_existing_hero_and_dismissible_notice_remain(self):
        response = self.client.get('/')
        self.assertContains(response, '<h1 class="pg-hero__title">PostgreSQL 世界上最先进的开源关系型数据库</h1>', count=1)
        self.assertContains(response, 'data-pg-shout-close')
        self.assertContains(response, 'class="pg-hero__chip"')
        self.assertContains(response, 'href="/docs/18/index.html"')
        self.assertContains(response, 'href="/docs/10/index.html"')
        self.assertContains(response, 'href="/docs/devel/index.html"')
        self.assertContains(response, '19<sup>beta</sup>')
        self.assertContains(response, 'href="/about/news/release-3365/"')
        self.assertContains(response, '由 <a href="https://pigsty.cc/" target="_blank" rel="noopener">Pigsty</a> 团队维护')
        self.assertNotContains(response, '无隶属关系')
        self.assertContains(response, 'href="/about/pgsql/"')
        self.assertNoOldBrand(response)

    def test_about_page_uses_new_brand_and_old_url_redirects(self):
        response = self.client.get('/about/pgsql/')
        self.assertContains(response, '关于 pgsql.cc')
        self.assertNoOldBrand(response)
        head = HomeMarkup(response.content.decode().split('</head>', 1)[0])
        self.assertEqual(head.values('link', 'href', rel='canonical'), ['https://pgsql.cc/about/pgsql/'])
        old = self.client.get('/about/pgcenter/')
        self.assertEqual(old.status_code, 301)
        self.assertEqual(old['Location'], '/about/pgsql/')

    def test_jsonld_strings_are_escaped(self):
        value = '引号 "、反斜杠 \\、换行\n和 </script><script>alert(1)</script>'
        html = render_to_string('index.html', {
            'title': value,
            'link_root': 'https://pgsql.cc',
            'og': {'title': value, 'sitename': value, 'description': value, 'url': '/'},
        })
        source = html.split('<script type="application/ld+json">')[1].split('</script>')[0]
        data = json.loads(source)
        self.assertEqual(data['name'], value)
        self.assertEqual(data['description'], value)
        self.assertNotIn('<script>alert(1)</script>', html)
