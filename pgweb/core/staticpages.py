"""Public static page boundaries shared by fallback routing and the sitemap."""


PUBLIC_SECTIONS = {'about', 'community', 'developer', 'docs', 'download', 'support'}
AUXILIARY_PAGES = {'account/markdown_submission', 'account/profile/change_email/done'}


def is_public_static_page(path):
    parts = path.strip('/').split('/')
    return (
        bool(parts) and parts[0] in PUBLIC_SECTIONS and
        not any(part in {'base', 'include', 'account'} or part.startswith('_') for part in parts)
    )
