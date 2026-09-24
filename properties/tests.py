import json
import re
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import Property, PropertyConfiguration, SharedPropertyList

SITE = 'https://offplan.cwlagos.com'


def _jsonld_blocks(html):
    return [json.loads(m) for m in re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


@override_settings(SEO_SITE_URL=SITE, ALLOWED_HOSTS=['testserver', '18.188.180.17'])
class SEOTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.props = []
        for i, name in enumerate(['Eko Pearl Towers', 'Ikoyi Gardens', 'Bourdillon Court']):
            prop = Property.objects.create(
                name=name, address=f'{i} Bourdillon Road, Ikoyi, Lagos', location='Ikoyi',
                latitude='6.450000', longitude='3.430000',
            )
            PropertyConfiguration.objects.create(
                property=prop, type='2BR', bedrooms=2, square_footage=120, price=450_000_000)
            PropertyConfiguration.objects.create(
                property=prop, type='4BR', bedrooms=4, square_footage=260, price=1_200_000_000)
            cls.props.append(prop)
        cls.prop = cls.props[0]
        cls.inactive = Property.objects.create(
            name='Hidden Project', address='Lekki, Lagos', location='Lekki', is_active=False)

    def test_robots_txt_blocks_private_areas_and_points_to_sitemap(self):
        resp = self.client.get('/robots.txt')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/plain')
        body = resp.content.decode()
        self.assertIn('Disallow: /crm/', body)
        self.assertIn('Disallow: /dashboard/', body)
        self.assertNotIn('Disallow: /shared/', body)
        self.assertIn(f'Sitemap: {SITE}/sitemap.xml', body)

    def test_sitemap_lists_canonical_public_urls_only(self):
        # A request on the raw IP must still produce canonical-domain URLs.
        resp = self.client.get('/sitemap.xml', HTTP_HOST='18.188.180.17')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn(f'<loc>{SITE}/</loc>', body)
        self.assertIn(f'<loc>{SITE}/neighbourhoods/ikoyi/</loc>', body)
        self.assertIn(f'<loc>{SITE}{self.prop.get_absolute_url()}</loc>', body)
        self.assertNotIn(str(self.inactive.pk) + '/hidden-project', body)
        self.assertNotIn('18.188.180.17', body)
        # Lekki has fewer than MARKET_MIN_PROJECTS active projects: limited, noindex, not listed.
        self.assertNotIn('/neighbourhoods/lekki/', body)

    def test_property_url_uses_slug(self):
        self.assertEqual(self.prop.get_absolute_url(), f'/property/{self.prop.pk}/eko-pearl-towers/')

    def test_legacy_and_stale_property_urls_301_to_canonical(self):
        canonical = self.prop.get_absolute_url()
        resp = self.client.get(f'/property/{self.prop.pk}/')
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(resp['Location'], canonical)

        resp = self.client.get(f'/property/{self.prop.pk}/old-name/?utm_source=wa')
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(resp['Location'], canonical + '?utm_source=wa')

    def test_property_page_meta_and_structured_data(self):
        resp = self.client.get(self.prop.get_absolute_url())
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('<title>Eko Pearl Towers, Ikoyi: 2 to 4-Bed Off-Plan Homes | CW Real Estate</title>', html)
        self.assertIn(f'<link rel="canonical" href="{SITE}{self.prop.get_absolute_url()}">', html)
        self.assertIn('<meta name="description" content="Eko Pearl Towers is an off-plan development in Ikoyi', html)
        self.assertIn('<meta property="og:image" content="https://', html)

        blocks = {b['@type']: b for b in _jsonld_blocks(html)}
        listing = blocks['RealEstateListing']
        self.assertEqual(listing['url'], SITE + self.prop.get_absolute_url())
        self.assertEqual(listing['offers']['priceCurrency'], 'NGN')
        self.assertEqual(listing['offers']['lowPrice'], '450000000.00')
        self.assertEqual(listing['contentLocation']['geo']['latitude'], 6.45)
        crumbs = [c['name'] for c in blocks['BreadcrumbList']['itemListElement']]
        self.assertEqual(crumbs, ['Market', 'Neighbourhoods', 'Ikoyi', 'Eko Pearl Towers'])

    def test_homepage_has_canonical_and_organization(self):
        html = self.client.get('/').content.decode()
        self.assertIn(f'<link rel="canonical" href="{SITE}/">', html)
        self.assertNotIn('CW Intelligence', html)
        org = next(b for b in _jsonld_blocks(html) if b['@type'] == 'RealEstateAgent')
        self.assertEqual(org['name'], 'CW Real Estate')

    def test_neighbourhood_canonical_ignores_query_string_and_request_host(self):
        html = self.client.get('/neighbourhoods/ikoyi/?sort=price&page=1',
                               HTTP_HOST='18.188.180.17').content.decode()
        self.assertIn(f'<link rel="canonical" href="{SITE}/neighbourhoods/ikoyi/">', html)
        self.assertNotIn('name="robots"', html)
        types = [b['@type'] for b in _jsonld_blocks(html)]
        self.assertIn('BreadcrumbList', types)

    def test_limited_neighbourhood_is_noindex(self):
        html = self.client.get('/neighbourhoods/lekki/').content.decode()
        self.assertIn('<meta name="robots" content="noindex, follow">', html)

    def test_shared_list_is_noindex(self):
        user = User.objects.create_user('agent', password='x')
        shared = SharedPropertyList.objects.create(
            name='For Ada', created_by=user, expires_at=timezone.now() + timedelta(days=7))
        shared.properties.add(self.prop)
        resp = self.client.get(f'/shared/{shared.token}/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('<meta name="robots" content="noindex, nofollow">', resp.content.decode())
