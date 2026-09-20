"""Public market registry: the neighbourhoods that get their own public page.

Two kinds of market:
  * 'area'  the broad areas we already store in Property.location (Ikoyi, ...).
  * 'sub'   named sub-markets (Banana Island, Ikate, ...) that sit inside an
            area. They are matched by looking for keywords in a project's
            address or name, so they need no Airtable or schema change and
            they overlap their parent area by design.

A market with fewer than MARKET_MIN_PROJECTS tracked projects is "limited":
its page still resolves, but it carries a limited-data notice and noindex, and
it is left out of listings, the index and the nearby-comparison table.
"""
from dataclasses import dataclass

from django.db.models import Q

from .location_utils import LOCATION_CHOICES, TRACKED_LOCATION_SLUGS
from .models import Property

MARKET_MIN_PROJECTS = 3


@dataclass(frozen=True)
class Market:
    slug: str
    label: str
    kind: str                # 'area' or 'sub'
    location: str = ''       # Property.location value (areas only)
    keywords: tuple = ()     # address/name substrings (sub-markets only)
    parent: str = ''         # parent area slug (sub-markets only)
    nearby: tuple = ()       # slugs shown in the "nearby markets" comparison


# Geography for the nearby comparison is an editorial judgement; review it.
_NEARBY = {
    'ikoyi': ('banana-island', 'victoria-island'),
    'banana-island': ('ikoyi', 'victoria-island'),
    'victoria-island': ('ikoyi', 'oniru', 'eko-atlantic', 'lekki-phase-1'),
    'oniru': ('victoria-island', 'lekki-phase-1', 'eko-atlantic'),
    'eko-atlantic': ('victoria-island', 'oniru'),
    'lekki-phase-1': ('oniru', 'victoria-island', 'ikate', 'lekki'),
    'ikate': ('lekki-phase-1', 'lekki'),
    'lekki': ('lekki-phase-1', 'ikate'),
    'orange-island': ('lekki-phase-1', 'ikate', 'oniru'),
}

_LABELS = dict(LOCATION_CHOICES)

_AREAS = tuple(
    Market(slug=slug, label=_LABELS[value], kind='area', location=value, nearby=_NEARBY.get(slug, ()))
    for slug, value in TRACKED_LOCATION_SLUGS.items()
)

_SUBS = (
    Market('banana-island', 'Banana Island', 'sub', keywords=('banana island',), parent='ikoyi', nearby=_NEARBY['banana-island']),
    Market('oniru', 'Oniru', 'sub', keywords=('oniru',), parent='victoria-island', nearby=_NEARBY['oniru']),
    Market('eko-atlantic', 'Eko Atlantic', 'sub', keywords=('eko atlantic',), parent='victoria-island', nearby=_NEARBY['eko-atlantic']),
    Market('ikate', 'Ikate', 'sub', keywords=('ikate',), parent='lekki', nearby=_NEARBY['ikate']),
    Market('orange-island', 'Orange Island', 'sub', keywords=('orange island',), parent='lekki-phase-1', nearby=_NEARBY['orange-island']),
)

MARKETS = _AREAS + _SUBS
MARKET_BY_SLUG = {m.slug: m for m in MARKETS}


def market_from_slug(slug):
    return MARKET_BY_SLUG.get(slug)


def market_properties(market):
    """Active properties belonging to this market."""
    qs = Property.objects.filter(is_active=True)
    if market.kind == 'area':
        return qs.filter(location=market.location)
    q = Q()
    for kw in market.keywords:
        q |= Q(address__icontains=kw) | Q(name__icontains=kw)
    return qs.filter(q)


def market_summaries():
    """[(market, project_count)] for every market, in registry order."""
    return [(m, market_properties(m).count()) for m in MARKETS]


def qualifying_markets():
    """Markets with enough tracked projects to be listed and indexed."""
    return [m for m, n in market_summaries() if n >= MARKET_MIN_PROJECTS]
