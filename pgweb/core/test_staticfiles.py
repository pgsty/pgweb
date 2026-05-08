import os
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase, override_settings


class StaticFilesRouteTests(SimpleTestCase):
    def test_files_url_serves_file_from_static_checkout(self):
        with TemporaryDirectory() as static_root:
            fixture_path = os.path.join(static_root, 'documentation', 'pdf')
            os.makedirs(fixture_path)
            with open(os.path.join(fixture_path, 'sample.txt'), 'wb') as f:
                f.write(b'static payload')

            with override_settings(STATIC_CHECKOUT=static_root):
                response = self.client.get('/files/documentation/pdf/sample.txt')
                content = b''.join(response.streaming_content) if response.streaming else response.content

        self.assertEqual(response.status_code, 200)
        self.assertEqual(content, b'static payload')
