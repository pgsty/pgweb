"""消息翻译 pages and JSON API. Everyone can read; saving needs the nls.review permission."""

import json
from functools import wraps

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.gzip import gzip_page
from django.views.decorators.http import require_GET, require_POST

from pgweb.util.decorators import nocache, queryparams

from . import service
from .validate import ValidationError

TITLE = 'PostgreSQL 消息翻译'


ROBOTS = 'noindex, nofollow'   # the table pulls megabytes per component; crawlers stay out (robots.txt too)


def json_response(payload, status=200):
    response = JsonResponse(payload, status=status, json_dumps_params={'ensure_ascii': False})
    response['Cache-Control'] = 'no-store'
    response['X-Robots-Tag'] = ROBOTS
    return response


def api_errors(view):
    """Turn validation problems into 409 JSON the page can show inline."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except ValidationError as exc:
            return json_response({'error': str(exc)}, status=409)
    return wrapper


def reviewer_required(view):
    """Anonymous users get 401 with the login link; signed-in users without the permission get 403."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return json_response({'error': '请登录后再保存。', 'login_url': service.LOGIN_URL}, status=401)
        if not service.can_edit(request.user):
            return json_response({'error': '当前账号没有消息校对权限。'}, status=403)
        return view(request, *args, **kwargs)
    return wrapper


def body(request):
    try:
        data = json.loads(request.body)
    except ValueError:
        raise ValidationError('请求体必须是 JSON。')
    if not isinstance(data, dict):
        raise ValidationError('请求体必须是 JSON 对象。')
    return data


@queryparams('v', 'lang')
@require_GET
@nocache
def index(request):
    response = render(request, 'nls/index.html', {
        'title': TITLE,
        'can_edit': service.can_edit(request.user),
        'login_url': service.LOGIN_URL,
        'seo': {'title': TITLE + ' · pgsql.cc', 'description': 'PostgreSQL 简体与繁体中文消息翻译校准：按语言和大版本逐条对照英文原文、既有译法与校准译文。'},
    })
    response['Cache-Control'] = 'no-store'
    response['X-Robots-Tag'] = ROBOTS
    return response


@queryparams('major', 'lang')
@require_GET
@nocache
@api_errors
def api_bootstrap(request):
    language = service.checked_language(request.GET.get('lang'))
    major = service.checked_major(request.GET.get('major'), language)
    return json_response(service.bootstrap(request.user, major, language))


@queryparams('name', 'major', 'lang')
@require_GET
@gzip_page
@api_errors
def api_component(request):
    language = service.checked_language(request.GET.get('lang'))
    major = service.checked_major(request.GET.get('major'), language)
    return json_response(service.component_table(request.GET.get('name', ''), major, language))


@queryparams('id', 'major', 'lang')
@require_GET
@api_errors
def api_references(request):
    language = service.checked_language(request.GET.get('lang'))
    query = service.Message.objects.filter(language=language)
    if request.GET.get('major') is not None:
        query = query.filter(pg_major=service.checked_major(request.GET['major'], language))
    try:
        message = query.get(pk=request.GET.get('id', ''))
    except service.Message.DoesNotExist:
        raise ValidationError('未知消息。')
    return json_response(service.references(message))


@require_POST
@reviewer_required
@api_errors
def api_decide(request):
    return json_response(service.decide(body(request), request.user))


@require_POST
@reviewer_required
@api_errors
def api_save(request):
    data = body(request)
    language = service.checked_language(data.get('language'))
    return json_response(service.decide_many(data.get('component', ''), data.get('decisions'), request.user,
                                             submit=data.get('submit') is True,
                                             major=service.checked_major(data.get('major'), language), language=language))


@queryparams('major', 'lang')
@require_GET
@reviewer_required
@api_errors
def api_export(request):
    language = service.checked_language(request.GET.get('lang'))
    major = service.checked_major(request.GET.get('major'), language)
    response = json_response(service.export(major, language))
    response['Content-Disposition'] = 'attachment; filename="pg%d-%s-human-review.json"' % (major, language)
    return response
