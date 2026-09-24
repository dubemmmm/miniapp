from django import template

from properties.seo import absolute_url

register = template.Library()


@register.filter
def absolute(value):
    """Turn a path or media URL into an absolute URL on the canonical site."""
    return absolute_url(str(value or ''))
