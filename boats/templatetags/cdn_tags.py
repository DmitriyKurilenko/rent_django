from django import template
from datetime import datetime
import re

register = template.Library()


@register.filter
def cdn_url(value):
    """Converts local boat image paths to CDN URL.

    Supported inputs:
    - ImageFieldFile (has .name)
    - string paths like 'boats/<boat_id>/<filename>'
    - URLs (http/https) - returned as-is

    Result format: https://cdn2.prvms.ru/<boat_id>/<filename>
    """
    if not value:
        return ''

    # If it's an object with .name (ImageFieldFile)
    name = None
    try:
        name = getattr(value, 'name', None)
    except Exception:
        name = None

    if not name and isinstance(value, str):
        name = value

    if not name:
        return ''

    name = str(name).lstrip('/')

    # If already a full URL, return as-is
    if name.startswith('http://') or name.startswith('https://'):
        return name

    # Normalize known prefixes
    # Possible stored forms: 'boats/<boat_id>/<file>', 'media/boats/<boat_id>/<file>'
    if name.startswith('media/boats/'):
        name = name[len('media/boats/'):]
    elif name.startswith('boats/'):
        name = name[len('boats/'):]
    elif name.startswith('media/'):
        # strip media/ and use remaining path
        name = name[len('media/'):]

    parts = name.split('/')
    if len(parts) >= 2:
        boat_id = parts[0]
        filename = '/'.join(parts[1:])
        # Keep only the filename portion for CDN path (no nested folders)
        filename = filename.split('/')[-1]
        return f"https://cdn2.prvms.ru/{boat_id}/{filename}"

    # Fallback - return original cleaned name joined to CDN
    safe_name = name.replace('../', '').replace('./', '')
    return f"https://cdn2.prvms.ru/{safe_name}"


@register.simple_tag
def nights_between(check_in, check_out):
    """Calculates the number of nights between check_in and check_out dates"""
    if not check_in or not check_out:
        return 0
    
    # Convert to datetime if they're date objects
    if hasattr(check_in, 'date'):
        check_in = check_in.date() if hasattr(check_in, 'date') else check_in
    if hasattr(check_out, 'date'):
        check_out = check_out.date() if hasattr(check_out, 'date') else check_out
    
    try:
        delta = check_out - check_in
        return max(0, delta.days)
    except (TypeError, AttributeError):
        return 0

