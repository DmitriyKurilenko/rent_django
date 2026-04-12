"""
Custom template filters for boats app
"""
import re

from django import template

register = template.Library()


# ---------------------------------------------------------------------------
# Charter company sentence patterns (per language).
#
# Each regex matches the charter-company mention sentence at the END of a
# boat description.  They are anchored with \Z so they can only fire at the
# very tail of the text.  The leading \s* absorbs whitespace between the
# preceding sentence's period and the charter sentence start.
#
# [^.]+ is used in "middle" segments to prevent the match from accidentally
# spanning across sentence boundaries (periods).  The final .+\Z is allowed
# to cross periods because charter company names may contain them ("Inc.").
# ---------------------------------------------------------------------------
_CHARTER_PATTERNS = [
    # -- EN --
    # "This motor yacht is operated by the charter company X."
    # "This houseboat is operated by the charter company X, which is rated
    #  by our customer's as 8.5/10."
    re.compile(
        r'\s*This\s+(?:motor\s+yacht|sailing\s+yacht|catamaran|'
        r'power\s+catamaran|houseboat|motorboat|gulet|yacht|boat)\s+'
        r'is\s+operated\s+by\s+the\s+charter\s+company\s+.+\Z',
        re.DOTALL,
    ),

    # -- RU --
    # "Яхта находится в парусная яхта и обслуживается Name."
    re.compile(
        r'\s*Яхта\s+находится\s+в\s+[^.]+?\s+и\s+обслуживается\s+.+\Z',
        re.DOTALL,
    ),
    # "Моторная Лодка под управлением компании Name."
    re.compile(
        r'\s*Моторная\s+Лодка\s+под\s+управлением\s+компании\s+.+\Z',
        re.DOTALL,
    ),
    # "Этот гулет находится в стране Турция под управлением компании Name."
    re.compile(
        r'\s*Этот\s+гулет\s+находится\s+в\s+стране\s+[^.]+?\s+под\s+'
        r'управлением\s+компании\s+.+\Z',
        re.DOTALL,
    ),
    # "Хаусбот управляется компанией Name, оценивается … баллов."
    re.compile(
        r'\s*Хаусбот\s+управляется\s+компанией\s+.+\Z',
        re.DOTALL,
    ),

    # -- DE --
    # "Diese Yacht wird in Segelboot Charter Name betrieben."
    re.compile(
        r'\s*Diese\s+Yacht\s+wird\s+in\s+[^.]+?\s+Charter\s+.+\Z',
        re.DOTALL,
    ),
    # "Dieses Hausboot wird von Name betrieben und … bewertet."
    re.compile(
        r'\s*Dieses\s+Hausboot\s+wird\s+von\s+.+?\s+betrieben.+\Z',
        re.DOTALL,
    ),
    # "Das Motorboot gehört zur Name Charter-Flotte."
    # Note: .+? instead of [^.]+? because charter names may contain dots
    re.compile(
        r'\s*Das\s+Motorboot\s+gehört\s+zur\s+.+?Charter-Flotte.+\Z',
        re.DOTALL,
    ),
    # "Dieses Gulet wird in Country von der Chartergesellschaft Name betrieben."
    re.compile(
        r'\s*Dieses\s+Gulet\s+wird\s+in\s+[^.]+?\s+von\s+der\s+'
        r'Chartergesellschaft\s+.+\Z',
        re.DOTALL,
    ),

    # -- ES --
    # "Este yate a motor está gestionado en Country por el chárter Name."
    re.compile(
        r'\s*Est[ea]\s+(?:yate(?:\s+a\s+motor)?|catamarán(?:\s+a\s+motor)?)\s+'
        r'está\s+gestionad[oa]\s+.+\Z',
        re.DOTALL,
    ),
    # "Esta casa flotante es administrada por Name, …"
    re.compile(
        r'\s*Esta\s+casa\s+flotante\s+es\s+administrada\s+por\s+.+\Z',
        re.DOTALL,
    ),
    # "La lancha a motor es operada por Name."
    re.compile(
        r'\s*La\s+lancha\s+a\s+motor\s+es\s+operada\s+por\s+.+\Z',
        re.DOTALL,
    ),
    # "Esta goleta es operada en Country por la empresa de chárter Name."
    re.compile(
        r'\s*Esta\s+goleta\s+es\s+operada\s+en\s+[^.]+?\s+por\s+la\s+'
        r'empresa\s+de\s+chárter\s+.+\Z',
        re.DOTALL,
    ),

    # -- FR --
    # "Ce yacht est opéré par Name."
    re.compile(
        r'\s*Ce\s+yacht\s+est\s+opéré\s+par\s+.+\Z',
        re.DOTALL,
    ),
    # "Le bateau est géré par Name."
    re.compile(
        r'\s*Le\s+bateau\s+est\s+géré\s+par\s+.+\Z',
        re.DOTALL,
    ),
    # "Cette péniche est gérée par Name, noté …"
    re.compile(
        r'\s*Cette\s+péniche\s+est\s+gérée\s+par\s+.+\Z',
        re.DOTALL,
    ),
    # "Cette goélette est louée par Name, Country."
    re.compile(
        r'\s*Cette\s+goélette\s+est\s+louée\s+par\s+.+\Z',
        re.DOTALL,
    ),
]


@register.filter
def strip_charter_company(value):
    """Remove the charter company mention sentence from boat description.

    Boataround.com descriptions end with a sentence naming the charter
    company that operates the boat.  This filter strips that sentence at
    display time (presentation layer) without modifying stored data.
    Works for all supported languages: EN, RU, DE, ES, FR.
    """
    if not value:
        return value

    text = str(value).strip()
    if not text:
        return value

    for pattern in _CHARTER_PATTERNS:
        cleaned = pattern.sub('', text).rstrip()
        if cleaned != text.rstrip():
            return cleaned
    return text


@register.filter
def split(value, delimiter=","):
    """Split string by delimiter, return list."""
    if not value:
        return []
    return value.split(delimiter)


@register.filter
def mul(value, arg):
    """Multiply value by arg"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def add(value, arg):
    """Add arg to value"""
    try:
        return float(value) + float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def currency_format(value, currency="EUR"):
    """Format value as currency"""
    try:
        val = float(value)
        if currency.upper() in ["EUR", "USD", "GBP"]:
            return f"{val:,.0f} {currency}"
        else:
            return f"{val:,.0f} {currency}"
    except (ValueError, TypeError):
        return "N/A"


@register.filter
def boat_price(boat_data, rental_days):
    """Calculate total price for boat based on rental days"""
    try:
        price_per_day = float(boat_data.get('priceFrom', 0)) or 0
        if price_per_day > 0 and rental_days > 0:
            return round(price_per_day * int(rental_days))
        return 0
    except (ValueError, TypeError, AttributeError):
        return 0


@register.filter
def dictget(d, key):
    """Lookup a dictionary value by key: {{ mydict|dictget:item.id }}"""
    if isinstance(d, dict):
        return d.get(key)
    return None
