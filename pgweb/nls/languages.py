"""Catalog languages; the site's interface language is independent of these."""

DEFAULT_LANGUAGE = 'zh_CN'
LANGUAGES = (('zh_CN', '简体中文'), ('zh_TW', '繁體中文'))


def checked_language(value=None):
    from .validate import ValidationError

    language = DEFAULT_LANGUAGE if value is None else value
    if not isinstance(language, str) or language not in dict(LANGUAGES):
        raise ValidationError('不支持的消息语言。')
    return language
