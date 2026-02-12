"""
Custom template filters for boats app
"""
from django import template

register = template.Library()


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
            return int(price_per_day * int(rental_days))
        return 0
    except (ValueError, TypeError, AttributeError):
        return 0
