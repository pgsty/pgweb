from django.core.validators import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect

from pgweb.util.contexts import render_pgweb
from pgweb.util.markup import pgmarkdown
from pgweb.util.seo import summarize_html

from pgweb.core.models import Version
from .models import SecurityPatch


def GetPatchesList(filt):
    return SecurityPatch.objects.raw("SELECT p.*, array_agg(CASE WHEN v.tree >= 10 THEN v.tree::int ELSE v.tree END ORDER BY v.tree DESC) AS affected, array_agg(CASE WHEN v.tree >= 10 THEN v.tree::int ELSE v.tree END || '.' || fixed_minor ORDER BY v.tree DESC) AS fixed FROM security_securitypatch p INNER JOIN security_securitypatchversion sv ON p.id=sv.patch_id INNER JOIN core_version v ON v.id=sv.version_id WHERE p.public AND {0} GROUP BY p.id ORDER BY cvenumber DESC".format(filt))


def _list_patches(request, filt, version=None):
    patches = GetPatchesList(filt)
    if version:
        page_title = '安全信息：版本 {}'.format(version.numtree)
        page_description = 'PostgreSQL {} 安全信息：影响该大版本的公开安全漏洞、修复版本和 CVSS 信息。'.format(version.numtree)
    else:
        page_title = '安全信息'
        page_description = 'PostgreSQL 安全信息：已知漏洞、影响版本、修复版本和 CVSS 信息。'

    return render_pgweb(request, 'support', 'security/security.html', {
        'patches': patches,
        'supported': Version.objects.filter(supported=True),
        'unsupported': Version.objects.filter(supported=False, tree__gt=0).extra(
            where=["EXISTS (SELECT 1 FROM security_securitypatchversion pv WHERE pv.version_id=core_version.id)"],
        ),
        'version': version,
        'page_title': page_title,
        'og': {
            'url': request.path,
            'title': page_title,
            'description': page_description,
            'type': 'article',
            'sitename': 'PostgreSQL 安全信息',
        },
    })


def details(request, cve_prefix, cve):
    """Provides additional details about a specific CVE"""
    # First determine if the entrypoint of the URL is a lowercase "cve". If it
    # is, redirect to the uppercase
    if cve_prefix != "CVE":
        return redirect('/support/security/CVE-{}/'.format(cve), permanent=True)
    # Get the CVE number from the CVE ID string so we can look it up
    # against the database. This shouldn't fail due to an ill-formatted CVE,
    # as both use the same validation check, but we will wrap it just in case.
    #
    # However, we do need to ensure that the CVE does both exist and
    # is published.
    try:
        security_patch = get_object_or_404(
            SecurityPatch,
            cvenumber=int(cve.split('-')[0]) * 100000 + int(cve.split('-')[1]),
            public=True,
        )
    except ValidationError:
        raise Http404()

    page_title = 'CVE-{}: {}'.format(security_patch.cve, security_patch.description)
    page_description = summarize_html(
        pgmarkdown(security_patch.details or security_patch.description, allow_relative_links=True),
        max_length=180,
    ) or security_patch.description

    return render_pgweb(request, 'support', 'security/details.html', {
        'security_patch': security_patch,
        'versions': security_patch.securitypatchversion_set.select_related('version').order_by('-version__tree').all(),
        'page_title': page_title,
        'og': {
            'url': '/support/security/CVE-{}/'.format(security_patch.cve),
            'title': page_title,
            'description': page_description,
            'type': 'article',
            'sitename': 'PostgreSQL 安全信息',
        },
    })


def index(request):
    # Show all supported versions
    return _list_patches(request, "v.supported")


def version(request, numtree):
    version = get_object_or_404(Version, tree=numtree)
    # It's safe to pass in the value since we get it from the module, not from
    # the actual querystring.
    return _list_patches(request, "EXISTS (SELECT 1 FROM security_securitypatchversion svv WHERE svv.version_id={0} AND svv.patch_id=p.id)".format(version.id), version)
