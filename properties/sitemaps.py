"""sitemap.xml: the public, indexable pages only.

URLs are built on settings.SEO_SITE_URL rather than the django.contrib.sites
record, so the sitemap always lists the canonical domain.
"""
from itertools import combinations
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from .location_utils import TRACKED_LOCATION_SLUGS, pair_slug
from .markets import MARKET_MIN_PROJECTS, market_from_slug, market_properties, qualifying_markets
from .models import Property


class CanonicalSitemap(Sitemap):
    def get_protocol(self, protocol=None):
        return urlsplit(settings.SEO_SITE_URL).scheme or 'https'

    def get_domain(self, site=None):
        return urlsplit(settings.SEO_SITE_URL).netloc


class StaticPagesSitemap(CanonicalSitemap):
    changefreq = 'daily'

    def items(self):
        return ['home', 'neighbourhood_index', 'compare_neighbourhoods_index', 'request_access']

    def location(self, item):
        return reverse(item)

    def priority(self, item):
        return 1.0 if item == 'home' else 0.7


class NeighbourhoodSitemap(CanonicalSitemap):
    """Markets with enough projects; limited ones are noindex, so left out."""
    changefreq = 'daily'
    priority = 0.9

    def items(self):
        return qualifying_markets()

    def location(self, market):
        return reverse('neighbourhood_detail', kwargs={'location_slug': market.slug})


class ComparisonSitemap(CanonicalSitemap):
    """Area-vs-area comparisons where both sides have enough projects."""
    changefreq = 'weekly'
    priority = 0.6

    def items(self):
        slugs = sorted(
            s for s in TRACKED_LOCATION_SLUGS
            if market_from_slug(s) and market_properties(market_from_slug(s)).count() >= MARKET_MIN_PROJECTS
        )
        return [pair_slug(a, b) for a, b in combinations(slugs, 2)]

    def location(self, pair):
        return reverse('compare_neighbourhoods', kwargs={'pair': pair})


class PropertySitemap(CanonicalSitemap):
    changefreq = 'weekly'
    priority = 0.8

    def items(self):
        return Property.objects.filter(is_active=True).only('pk', 'slug', 'name', 'updated_at').order_by('pk')

    def lastmod(self, prop):
        return prop.updated_at


SITEMAPS = {
    'pages': StaticPagesSitemap,
    'neighbourhoods': NeighbourhoodSitemap,
    'compare': ComparisonSitemap,
    'properties': PropertySitemap,
}
