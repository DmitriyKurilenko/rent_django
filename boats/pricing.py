"""Unified pricing logic for search, boat detail, offers and booking."""
from typing import Any, Dict, Optional, Tuple

from boats.helpers import calculate_final_price_with_discounts
from boats.models import BoatPrice


def _to_float(value: Any) -> float:
    """Best-effort float conversion with safe fallback."""
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def extract_price_components(payload: Dict[str, Any]) -> Tuple[float, float, float]:
    """
    Extract base price and discounts from Boataround payload.

    Supports both search payload and /price/<slug> payload.
    Returns: (base_price, discount_without_extra, additional_discount)
    """
    base_price = _to_float(payload.get("price") or payload.get("totalPrice"))
    additional_discount = _to_float(
        payload.get("additional_discount") or payload.get("additionalDiscount")
    )

    explicit_discount_wo_extra = _to_float(payload.get("discount_without_additionalExtra"))
    total_discount = _to_float(payload.get("discount"))

    if explicit_discount_wo_extra > 0:
        discount_without_extra = explicit_discount_wo_extra
    elif total_discount > 0 and additional_discount > 0:
        discount_without_extra = max(total_discount - additional_discount, 0)
    else:
        discount_without_extra = total_discount

    # Fallback: nested policies[0].prices can contain canonical values
    policies = payload.get("policies") or []
    if isinstance(policies, list) and policies:
        first_policy = policies[0] or {}
        prices = first_policy.get("prices") or {}
        if isinstance(prices, dict):
            if base_price <= 0:
                base_price = _to_float(prices.get("price"))
            if discount_without_extra <= 0:
                discount_without_extra = _to_float(prices.get("discount_without_additionalExtra"))
            if additional_discount <= 0:
                additional_discount = _to_float(prices.get("additional_discount"))

    return base_price, discount_without_extra, additional_discount


def build_price_breakdown(
    base_price: float,
    discount_without_extra: float,
    additional_discount: float,
    charter: Optional[Any] = None,
    currency: str = "EUR",
) -> Dict[str, Any]:
    """Calculate final/old/discount prices with a single formula."""
    base_price = _to_float(base_price)
    discount_without_extra = _to_float(discount_without_extra)
    additional_discount = _to_float(additional_discount)

    final_price = _to_float(
        calculate_final_price_with_discounts(
            base_price,
            discount_without_extra,
            additional_discount,
            charter=charter,
        )
    )

    old_price = 0.0
    discount_percent = 0
    if base_price > 0 and final_price > 0 and base_price > final_price:
        old_price = base_price
        try:
            discount_percent = round((base_price - final_price) / base_price * 100)
        except ZeroDivisionError:
            discount_percent = 0

    return {
        "base_price": round(base_price, 2),
        "final_price": round(final_price, 2),
        "discount_without_extra": round(discount_without_extra, 2),
        "additional_discount": round(additional_discount, 2),
        "old_price": round(old_price, 2),
        "discount_percent": int(discount_percent),
        "currency": currency or "EUR",
    }


def get_db_fallback_price(
    slug: str,
    rental_days: Optional[int] = None,
    currency: str = "EUR",
) -> Dict[str, Any]:
    """Fallback to stored boat prices in DB when live API price is unavailable."""
    days = rental_days if rental_days and rental_days > 0 else 7
    db_price = (
        BoatPrice.objects.filter(boat__slug=slug, currency=currency).first()
        or BoatPrice.objects.filter(boat__slug=slug).first()
    )
    if not db_price:
        return {
            "base_price": 0.0,
            "final_price": 0.0,
            "discount_without_extra": 0.0,
            "additional_discount": 0.0,
            "old_price": 0.0,
            "discount_percent": 0,
            "currency": currency,
            "source": "none",
        }

    per_day = _to_float(db_price.price_per_day)
    per_week = _to_float(db_price.price_per_week)
    total = 0.0
    if per_day > 0:
        total = round(per_day * days, 2)
    elif per_week > 0:
        total = round((per_week / 7) * days, 2)

    return {
        "base_price": total,
        "final_price": total,
        "discount_without_extra": 0.0,
        "additional_discount": 0.0,
        "old_price": 0.0,
        "discount_percent": 0,
        "currency": db_price.currency or currency,
        "source": "db",
    }


def resolve_live_or_fallback_price(
    slug: str,
    check_in: str,
    check_out: str,
    lang: str,
    charter: Optional[Any] = None,
    rental_days: Optional[int] = None,
    currency: str = "EUR",
) -> Dict[str, Any]:
    """
    Unified resolver:
    1) Try Boataround live price API
    2) Fallback to DB stored BoatPrice
    """
    from boats.boataround_api import BoataroundAPI

    price_data = BoataroundAPI.get_price(
        slug=slug,
        check_in=check_in,
        check_out=check_out,
        currency=currency,
        lang=lang,
    )
    if price_data:
        base_price, discount_wo_extra, additional_discount = extract_price_components(price_data)
        breakdown = build_price_breakdown(
            base_price=base_price,
            discount_without_extra=discount_wo_extra,
            additional_discount=additional_discount,
            charter=charter,
            currency=currency,
        )
        breakdown["source"] = "api"
        return breakdown

    return get_db_fallback_price(slug=slug, rental_days=rental_days, currency=currency)
