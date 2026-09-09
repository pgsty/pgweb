from django import template


register = template.Library()


@register.simple_tag(takes_context=True)
def seo_values(context):
    # Keep values unescaped until the final HTML attribute is rendered, so
    # truncation cannot split an escaped entity such as &quot; in the middle.
    seo = context.get('seo') or {}
    og = context.get('og') or {}
    title = seo.get('title')
    if not title:
        title = og.get('title') or ''
        if title and not title.startswith('PostgreSQL'):
            title = 'PostgreSQL ' + title
    return {
        'description': seo.get('description') or og.get('description') or '',
        'canonical': seo.get('canonical') or og.get('url') or '',
        'title': title,
    }
