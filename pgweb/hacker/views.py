"""The developer directory: one row per person, with source-attributed profiles."""

import re
from urllib.parse import urlencode

from babel import Locale
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.db.models import Q, TextField
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Coalesce
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import condition, require_safe

from pgweb.util.contexts import get_nav_menu
from pgweb.util.decorators import queryparams

from .models import HackerProfile
from .presentation import link_identity, safe_url


COUNTRIES = Locale('zh').territories
def country_label(value):
    return COUNTRIES.get(value.upper(), value) if value else ''


def page_context(title, description, canonical):
    nav = get_nav_menu('developer')
    for item in nav:
        item['active'] = item['link'] == '/developer/hacker/'
    return {
        'title': title, 'navmenu': nav,
        'seo': {'title': title, 'description': description, 'canonical': canonical, 'lang': 'zh'},
        'og': {'sitename': 'PGSQL.CC', 'type': 'website'},
    }


@queryparams('q', 'organization', 'country', 'page')
@require_safe
def index(request):
    query = request.GET.get('q', '').strip()[:200]
    organization = request.GET.get('organization', '')[:250]
    country = request.GET.get('country', '')[:100]
    # Neither the full activity archive nor image bytes belong in a card query.
    all_profiles = HackerProfile.objects.defer('data', 'avatar').annotate(
        organization_label=Coalesce(KeyTextTransform.from_lookup('texts__zh__organization'), 'organization', output_field=TextField()))
    profiles = all_profiles
    if query:
        profiles = profiles.filter(Q(name__icontains=query) | Q(texts__zh__bio__icontains=query) |
                                   Q(texts__zh__position__icontains=query) |
                                   Q(organization_label__icontains=query) | Q(country__icontains=query) |
                                   Q(data__emails__icontains=query))
    if organization:
        profiles = profiles.filter(organization_label=organization)
    if country:
        profiles = profiles.filter(country=country)
    page = Paginator(profiles, 24).get_page(request.GET.get('page'))
    for profile in page:
        profile.country_label = country_label(profile.country)
    selected = {'q': query, 'organization': organization, 'country': country}

    def page_url(number):
        params = {key: value for key, value in selected.items() if value}
        if number != 1:
            params['page'] = number
        return '/developer/hacker/' + ('?' + urlencode(params) if params else '')

    context = page_context('PostgreSQL 开发者大全', '认识 PostgreSQL 开发者与贡献者，浏览简介、公开联系信息和社区贡献。', '/developer/hacker/')
    context.update(
        page=page, total=all_profiles.count(), result_count=page.paginator.count,
        query=query, selected=selected,
        organizations=list(all_profiles.exclude(organization_label='').order_by('organization_label')
                           .values_list('organization_label', flat=True).distinct()),
        countries=[{'code': code, 'label': country_label(code)} for code in
                   all_profiles.exclude(country='').order_by('country').values_list('country', flat=True).distinct()],
        pagination=[{'label': n, 'current': n == page.number, 'url': page_url(n) if isinstance(n, int) else ''}
                    for n in page.paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1)],
        previous_url=page_url(page.previous_page_number()) if page.has_previous() else '',
        next_url=page_url(page.next_page_number()) if page.has_next() else '',
        noindex=bool(query or organization or country or page.number > 1),
    )
    return render(request, 'hacker/index.html', context)


def contacts(data, bio=''):
    emails, seen = [], set()
    for entry in data.get('emails', []):
        value = entry.get('email', '') if isinstance(entry, dict) else entry
        try:
            validate_email(value)
        except (ValidationError, TypeError):
            continue
        if value.casefold() not in seen:
            seen.add(value.casefold())
            emails.append({'email': value, 'source_url': safe_url(entry.get('source_url', '')) if isinstance(entry, dict) else ''})
    links, seen = [], set()
    entries = list(data.get('links', []))
    entries.extend({'url': url.rstrip('.,;，。；')} for url in re.findall(r'https?://[^\s<>"()]+', bio))
    entries.extend({'url': 'https://twitter.com/' + handle}
                   for handle in re.findall(r'Twitter:\s*@([A-Za-z0-9_]+)', bio))
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        url = safe_url(entry.get('url', ''))
        if url and url not in seen:
            seen.add(url)
            label, icon = link_identity(url)
            links.append({'url': url, 'label': label, 'icon': icon})
    return emails, links


@queryparams()
@require_safe
def detail(request, slug):
    profile = get_object_or_404(HackerProfile.objects.defer('avatar'), slug=slug)
    data = profile.data
    emails, links = contacts(data, profile.bio)
    official = data.get('official', {})
    role_labels = {'Core Team': '核心团队', 'Committer': '代码提交者', 'Major Contributors': '主要贡献者',
                   'Significant Contributors': '重要贡献者', 'Past Contributors': '历史贡献者'}
    roles = []
    sources = []
    seen = set()

    def add_source(url, label):
        url = safe_url(url)
        if url and url not in seen:
            seen.add(url)
            sources.append({'url': url, 'label': label})

    for entry in official.get('roles', [{'role': official.get('role', ''), 'source_url': official.get('source_url', '')}]):
        if isinstance(entry, dict) and entry.get('role') in role_labels:
            label = role_labels[entry['role']]
            roles.append(label)
            add_source(entry.get('source_url'), 'PostgreSQL ' + label + '名录')
    add_source(official.get('source_url'), 'PostgreSQL 贡献者名录')
    for entry in data.get('external_sources', []):
        if isinstance(entry, dict):
            add_source(entry.get('url'), '人物介绍')
    # Professional profile links also identify the public source of biographies.
    for link in links:
        add_source(link['url'], link['label'])
    context = page_context(profile.name + ' · PostgreSQL 开发者大全',
                           profile.zh.get('bio') or 'PostgreSQL 开发者与贡献者档案。', profile.get_absolute_url())
    context.update(profile=profile, country=country_label(profile.country), emails=emails, links=links,
                   roles=roles, sources=sources,
                   organization=profile.zh.get('organization', profile.organization),
                   organization_url=safe_url(official.get('organization_url')))
    return render(request, 'hacker/detail.html', context)


def avatar_etag(request, slug):
    return HackerProfile.objects.filter(slug=slug).values_list('avatar_sha256', flat=True).first() or None


@queryparams()
@require_safe
@condition(etag_func=avatar_etag)
def avatar(request, slug):
    profile = get_object_or_404(HackerProfile.objects.only('avatar', 'avatar_content_type'), slug=slug)
    if not profile.avatar:
        raise Http404('No portrait')
    response = HttpResponse(bytes(profile.avatar), content_type=profile.avatar_content_type)
    response['Cache-Control'] = 'public, max-age=86400'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
