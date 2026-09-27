"""
Custom template filters for the naukri app.
Load with {% load naukri_extras %} in templates.
"""

import json
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(is_safe=True)
def safe_json(value):
    """
    Serialize *value* to a JSON string safe for inline JavaScript.

    Usage:  {{ job|safe_json }}
    Escapes </script> sequences so the output is safe to embed inside
    an HTML <script> tag or an onclick attribute.
    """
    dumped = json.dumps(value, ensure_ascii=False, default=str)
    # Prevent </script> from closing an enclosing script block
    dumped = dumped.replace("</", r"<\/")
    return mark_safe(dumped)
