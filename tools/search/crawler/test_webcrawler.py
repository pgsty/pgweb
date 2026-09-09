from configparser import ConfigParser
import unittest
from unittest.mock import patch

import webcrawler


class CrawlerSiteDomainTests(unittest.TestCase):
    def setUp(self):
        config = ConfigParser()
        config.read_dict({'search': {
            'db': 'dbname=unused', 'web': 'pgsql.cc', 'https': 'true',
            'frontendip': '', 'local_baseurl': 'http://127.0.0.1:8000',
        }})
        for target, value in (('cp', config), ('time.sleep', None), ('log', None)):
            mock = patch('webcrawler.' + target, value, create=True) if value is not None else patch('webcrawler.' + target)
            mock.start()
            self.addCleanup(mock.stop)
        connect = patch('webcrawler.psycopg2.connect')
        self.connection = connect.start().return_value
        self.addCleanup(connect.stop)
        self.cursor = self.connection.cursor.return_value
        self.cursor.fetchall.return_value = []

    @patch('webcrawler.SitemapSiteCrawler')
    def test_completed_crawl_publishes_configured_domain(self, crawler):
        webcrawler.doit()
        crawler.assert_called_once_with('pgsql.cc', self.connection, 1, '', True, 'http://127.0.0.1:8000')
        statement, params = self.cursor.execute.call_args_list[0][0]
        self.assertIn('UPDATE sites', statement)
        self.assertEqual(params, {'hostname': 'pgsql.cc', 'baseurl': 'https://pgsql.cc', 'https': True})
        self.connection.commit.assert_called()

    @patch('webcrawler.SitemapSiteCrawler')
    def test_failed_crawl_does_not_publish_domain(self, crawler):
        crawler.return_value.crawl.side_effect = RuntimeError('sitemap unavailable')
        with self.assertRaisesRegex(RuntimeError, 'sitemap unavailable'):
            webcrawler.doit()
        self.cursor.execute.assert_not_called()
        self.connection.commit.assert_not_called()
