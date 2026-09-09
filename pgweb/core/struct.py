import os
from django.urls import resolve
from django.views.generic import RedirectView

from .staticpages import is_public_static_page
from pgweb.util.seo import page_metadata


def get_struct():
    yield ('', None)
    yield ('about/', None)
    yield ('community/', None)
    yield ('support/versioning/', None)
    yield ('developer/beta/', None)

    # Enumerate all the templates that will generate pages
    pages_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../templates/pages/'))
    for root, dirs, files in os.walk(pages_dir):
        # Cut out the reference to the absolute root path
        r = '' if root == pages_dir else os.path.relpath(root, pages_dir)
        for f in files:
            if f.endswith('.html'):
                path = os.path.join(r, f)[:-5] + '/'
                if not is_public_static_page(path):
                    continue
                view_class = getattr(resolve('/' + path).func, 'view_class', None)
                if view_class and issubclass(view_class, RedirectView):
                    continue
                canonical = page_metadata('/' + path).get('canonical', '/' + path)
                if canonical == '/' + path:
                    yield (path, None)
