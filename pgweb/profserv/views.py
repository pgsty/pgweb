from django.http import Http404

from pgweb.util.contexts import render_pgweb

from .models import ProfessionalService

regions = (
    ('africa', '非洲'),
    ('asia', '亚洲'),
    ('europe', '欧洲'),
    ('northamerica', '北美洲'),
    ('oceania', '大洋洲'),
    ('southamerica', '南美洲'),
)


def root(request, servtype):
    support = servtype == 'support'
    title = support and '专业服务' or '托管方案'
    what = support and 'support' or 'hosting'
    return render_pgweb(request, 'support', 'profserv/root.html', {
        'title': title,
        'support': support,
        'regions': regions,
        'what': what,
    })


def region(request, servtype, regionname):
    regname = [n for r, n in regions if r == regionname]
    if not regname:
        raise Http404
    regname = regname[0]

    support = servtype == 'support'
    what = support and 'support' or 'hosting'
    whatname = support and '专业服务' or '托管方案'
    title = "%s - %s" % (whatname, regname)

    # DB model is a bit funky here, so use the extra-where functionality to filter properly.
    # Field names are cleaned up earlier, so it's safe against injections.
    services = ProfessionalService.objects.select_related('org').filter(approved=True).extra(where=["region_%s AND provides_%s" % (regionname, what), ])

    return render_pgweb(request, 'support', 'profserv/list.html', {
        'title': title,
        'support': support,
        'what': what,
        'whatname': whatname,
        'regionname': regname,
        'services': services,
    })
