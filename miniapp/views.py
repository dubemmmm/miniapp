from django.http import HttpResponse
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

from properties.seo import absolute_url

# Private app areas crawlers should not spend time on. Shared lists (/shared/)
# stay crawlable on purpose so search engines can read their noindex tag.
ROBOTS_DISALLOW = (
    '/admin/',
    '/crm/',
    '/api/',
    '/accounts/',
    '/login/',
    '/logout/',
    '/register/',
    '/employee-register/',
    '/google-oauth-signup/',
    '/dashboard/',
    '/favorites/',
    '/manage-shares/',
    '/portfolio/',
    '/reports/',
    '/temp2/',
    '/property/*/pdf/',
)


@require_GET
@cache_control(max_age=86400, public=True)
def robots_txt(request):
    lines = ['User-agent: *']
    lines += [f'Disallow: {path}' for path in ROBOTS_DISALLOW]
    lines += ['', f"Sitemap: {absolute_url('/sitemap.xml')}", '']
    return HttpResponse('\n'.join(lines), content_type='text/plain')
