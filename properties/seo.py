"""SEO helpers: canonical URLs, brand name and schema.org JSON-LD.

Every absolute URL a search engine sees (canonical tags, Open Graph, JSON-LD,
sitemap.xml) is built from settings.SEO_SITE_URL, never from the request host,
so the site's IP addresses and http/www variants all point at one address.
"""
import json

from django.conf import settings
from django.templatetags.static import static


def site_url():
    return settings.SEO_SITE_URL.rstrip('/')


def absolute_url(path_or_url):
    """A path ('/x/') or already-absolute URL -> an absolute URL on the canonical site."""
    if not path_or_url:
        return ''
    if path_or_url.startswith(('http://', 'https://')):
        return path_or_url
    if path_or_url.startswith('//'):
        return 'https:' + path_or_url
    return site_url() + '/' + path_or_url.lstrip('/')


def dump_jsonld(data):
    """JSON for a <script type="application/ld+json"> block, safe to mark |safe."""
    return json.dumps(data, ensure_ascii=False).replace('</', '<\\/')


def seo_context(request):
    """Template context processor."""
    return {
        'SEO_SITE_URL': site_url(),
        'SEO_BRAND_NAME': settings.SEO_BRAND_NAME,
    }


def organization_jsonld():
    return dump_jsonld({
        "@context": "https://schema.org",
        "@type": "RealEstateAgent",
        "name": settings.SEO_BRAND_NAME,
        "url": site_url() + '/',
        "logo": absolute_url(static('logo/CW-logo.jpeg')),
        "image": absolute_url(static('logo/CW-logo.jpeg')),
        "areaServed": {"@type": "City", "name": "Lagos"},
    })


def breadcrumb_jsonld(crumbs):
    """crumbs: [(name, path), ...] from the site root down to the current page."""
    return dump_jsonld({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "name": name, "item": absolute_url(path)}
            for i, (name, path) in enumerate(crumbs, start=1)
        ],
    })
